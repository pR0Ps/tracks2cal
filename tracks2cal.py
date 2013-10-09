#!/usr/bin/python

import httplib2
import logging
import os
import sys
import json

from apiclient.discovery import build
from apiclient import errors
from oauth2client.file import Storage
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.tools import run

from lxml import etree

import datetime

TIME_OUT_FMT = "%Y-%m-%dT%H:%M:%SZ"
TIME_IN_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"

CLIENT_SECRETS = "client_secrets.json"

FLOW = flow_from_clientsecrets(CLIENT_SECRETS,
    scope=[
      'https://www.googleapis.com/auth/drive.readonly',
      'https://www.googleapis.com/auth/calendar',
    ],
    message="Couldn't find client secrets file at %s" % (CLIENT_SECRETS,))


class Tracks2Cal(object):

    def __init__(self, folder_name="My Tracks", cal_name="My Tracks"):
        """Log in and create authorized service to use the Google API"""

        # Get/store OAuth crediendials
        storage = Storage('creds.dat')
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            credentials = run(FLOW, storage)

        # Authorize an http object to make the requests
        http = httplib2.Http()
        http = credentials.authorize(http)

        # Make the API service objects
        self.drive_service = build('drive', 'v2', http=http)
        self.cal_service = build('calendar', 'v3', http=http)

        # Store options
        self.folder_name = folder_name
        self.cal_name = cal_name
        self.cal_id = self.get_calendar_id()
        self.events = self.get_existing_events()

    def _get_paginated_data(self, fcn, kwargs={}):
        """Handles pagination and returns all the data at once"""
        page = None
        items = []
        while True:
            r = fcn(pageToken=page, **kwargs).execute()
            items.extend(r["items"])
            page = r.get("nextPageToken", None)
            if not page:
                return items

    def get_calendar_id(self):
        """Get the calendar id to use when adding events"""

        # Look for the calendar (use pagination)
        items = self._get_paginated_data(self.cal_service.calendarList().list)

        for x in items:
            if x["summary"] == self.cal_name:
                return x["id"]
        else:
            logging.info("No calendar named '%s' found, creating one" % (self.cal_name,))

            cal_data = {
                "summary": self.cal_name
            }
            r = self.cal_service.calendars().insert(body=cal_data).execute()
            return r["id"]

    def get_existing_events(self):
        """Get the events currently in the tracks calendar"""
        temp = self._get_paginated_data(self.cal_service.events().list, dict(calendarId=self.cal_id))
        ret = []
        for x in temp:
            ret.append((x["summary"],
                datetime.datetime.strptime(x["start"]["dateTime"], TIME_OUT_FMT),
                datetime.datetime.strptime(x["end"]["dateTime"], TIME_OUT_FMT)))

        return ret

    def _get_placemark_time(self, placemark, ns):
        """Returns a datetime object representuing the time set in the placemark"""
        text = placemark.find("{%s}TimeStamp" % ns).find("{%s}when" % ns).text
        return datetime.datetime.strptime(text, TIME_IN_FMT)

    def parse_kml_data(self, data):
        """Parse the KML data and return a (start, end, coords, description) tuple"""

        logging.debug("Parsing KML data")

        kml_root = etree.fromstring(data)

        # Get the default namespace
        ns = kml_root.nsmap[None]

        # Get the placemarks (start, tour, end)
        temp_placemarks = kml_root.find("{%s}Document" % ns).findall("{%s}Placemark" % ns)

        # Get the data from the placemarks
        # styleURLs "#start", "#track", and "#end" define the different placemarks
        placemarks = {}
        for p in temp_placemarks:
            style = p.find("{%s}styleUrl" % ns)
            if style is not None:
                placemarks[style.text] = p

        desc = placemarks["#end"].find("{%s}description" % ns).text

        coords = {}
        times = {}
        for x in ("start", "end"):
            # Convert "long,lat[,altitude]" to "lat,long"
            temp = placemarks["#" + x].find("{%s}Point" % ns).find("{%s}coordinates" % ns).text
            coords[x] = ",".join(temp.split(",")[1::-1])
            
            # Get start/end times
            times[x] = self._get_placemark_time(placemarks["#" + x], ns)

        desc += "\nStart Location: https://maps.google.ca/maps?q=%(start)s" \
        "\nEnd Location: https://maps.google.ca/maps?q=%(end)s" % (coords)

        return times, coords, desc

    def kml_file_data(self):
        """
        Generator for KML file data

        Grabs the KML data from Google Drive and generates (filename, file_data) objects
        """
        try:
            logging.debug("Opening the '%s' folder in Google Drive" % (self.folder_name,))

            # Get folder(s) matching the folder name
            kwargs = dict(q="mimeType='application/vnd.google-apps.folder' and title='%s' and trashed=False" % (self.folder_name,))
            folders = self._get_paginated_data(self.drive_service.files().list, kwargs)

            # Filter out non-root folders
            folders = [f for f in folders if [p for p in f["parents"] if p["isRoot"]]]

            # Check for no/multiple folders
            if not folders:
                logging.critical("No '%s' folder found in the Google Drive root folder, exiting", (self.folder_name,))
                return
            elif len(folders) > 1:
                logging.critical("More than 1 '%s' folders found, exiting" % (self.folder_name,))
                return

            # Get the ID of the folder to work inside
            folder_id = folders[0]["id"]

            logging.debug("Getting kml files in the folder")

            # Get the children of the My Tracks folder
            kwargs = dict(folderId=folder_id, q="mimeType='application/vnd.google-earth.kml+xml' and trashed=False")
            items = self._get_paginated_data(self.drive_service.children().list, kwargs)

            for x in items:
                file_ = self.drive_service.files().get(fileId=x["id"]).execute()

                filename_ext = file_["title"]

                # Remove extension of filename
                filename = "".join(filename_ext.split(".")[:-1])

                logging.debug("Downloading data from '%s'" % (filename_ext,))

                # Download the data of the kml file
                r, data = self.drive_service._http.request(file_["downloadUrl"])
                if r.status == 200:
                    yield filename, data
                else:
                    logging.warning("Error occurred downloading KML file: %s" % (str(r),))

        except (errors.HttpError, KeyError), e:
            logging.critical("Error occurred: %s" % (str(e),))
            return

    def event_exists(self, title, times):
        """Checks if the event already exists in Google Calendar"""

        logging.debug("Checking if event '%s' exists..." % (title,))

        fuzz = datetime.timedelta(seconds=2)

        # Format for events = tuple(name, start, end)
        for x in self.events:
            
            # Check if any events with the same name as this event are at the same time
            if x[0] == title and (x[1] - times["start"]) < fuzz and (x[2] - times["end"]) < fuzz:
                logging.debug("Event already exists, not adding")
                return True

        logging.debug("Event doesn't exist")
        return False

    def add_event(self, title, times, coords={}, desc=""):
        """Adds an event to Google Calendar"""

        logging.debug("Adding event '%s' to calendar" % (title,))

        # Set up event properties
        event = {
            "summary": title,
            "location": coords.get("start",""),
            "description": desc,
        }
        # Add start + end times
        for k, v in times.iteritems():
            event[k] = dict(dateTime=v.strftime(TIME_OUT_FMT)),

        r = self.cal_service.events().insert(calendarId=self.cal_id, body=event).execute()

        logging.debug("Event '%s' created" % (r["summary"],))

    def run(self):
        """
        Finds all MyTracks files in Google Drive and creates events in
        Google Calendar according to their properties
        """
        total = 0
        added = 0
        for filename, file_data in self.kml_file_data():
            times, coords, desc = self.parse_kml_data(file_data)
            total += 1
            if not self.event_exists(filename, times):
                self.add_event(filename, times, coords, desc)
                added += 1

        logging.critical("Finished successfully!")
        logging.critical("KML files were taken from the folder '%s' and added to the calendar '%s'" % (self.folder_name, self.cal_name))
        logging.critical("%d new entries were added (from a total of %d parsed)" % (added, total,))

def main():
    try:
        Tracks2Cal().run()
    except AccessTokenRefreshError:
        logging.critical("The credentials have been revoked or expired, please re-run the application to re-authorize")


if __name__ == '__main__':
    logging.basicConfig(format="[%(asctime)s][%(levelname)s]: %(message)s", level=logging.DEBUG)

    main()
