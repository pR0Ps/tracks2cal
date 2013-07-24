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

    def __init__(self, folder_name="My Tracks", cal_name="Logging"):
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

    def get_calendar_id(self):
        """Get the calendar id to use when adding events"""

        # TODO: pagination
        for x in self.cal_service.calendarList().list().execute()["items"]:
            if x["summary"] == self.cal_name:
                return x["id"]
        else:
            logging.info("No calendar named '%s' found, creating one" % (self.cal_name,))

            cal_data = {
                "summary": self.cal_name
            }
            r = self.cal_service.calendars().insert(body=cal_data).execute()
            return r["id"]

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
        placemarks = kml_root.find("{%s}Document" % ns).findall("{%s}Placemark" % ns)

        # Get the data from the placemarks
        # TODO: Use the 'styleURL' ("#start", "#track", "#end") instead of indecies
        start_time = self._get_placemark_time(placemarks[0], ns)
        end_time = self._get_placemark_time(placemarks[2], ns)
        desc = placemarks[2].find("{%s}description" % ns).text

        # Convert "long,lat[,altitude]" to "lat,long"
        temp = placemarks[0].find("{%s}Point" % ns).find("{%s}coordinates" % ns).text
        coords = ",".join(temp.split(",")[1::-1])

        return start_time, end_time, coords, desc

    def kml_file_data(self):
        """
        Generator for KML file data

        Grabs the KML data from Google Drive and generates (filename, file_data) objects
        """
        try:
            logging.debug("Opening the 'My Tracks' folder in Google Drive")

            # Get the "My Tracks" folder id
            folder = self.drive_service.files().list(q="mimeType='application/vnd.google-apps.folder' and title='%s'" % (self.folder_name,)).execute()["items"]
            if not folder:
                logging.critical("No '%s' folder found in Google Drive, exiting", (self.folder_name,))
                return

            folder_id = folder[0]["id"]

            logging.debug("Getting kml files in the folder")

            # Get the children of the My Tracks folder
            # TODO: Pagination
            for x in self.drive_service.children().list(folderId=folder_id, q="mimeType='application/vnd.google-earth.kml+xml' and trashed=False").execute()["items"]:
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

    def event_exists(self, title, start, end):
        """Checks if the event already exists in Google Calendar"""

        logging.debug("Checking if event '%s' exists..." % (title,))

        # Fuzz the times a bit to take rounding into account
        fuzz = datetime.timedelta(seconds=1)
        timeMin = (start + fuzz).strftime(TIME_OUT_FMT)
        timeMax = (start + 2 * fuzz).strftime(TIME_OUT_FMT)

        # Get all events that exist in the start+fuzz to start+2*fuzz window
        r = self.cal_service.events().list(calendarId=self.cal_id, timeMin=timeMin, timeMax=timeMax).execute()["items"]

        # If any of the events at this time have the same title as the event, it already exists
        if [x for x in r if x["summary"] == title]:
            logging.debug("Event exists")
            return True

        logging.debug("Event doesn't exist")
        return False

    def add_event(self, title, start, end, loc="", desc=""):
        """Adds an event to Google Calendar"""

        logging.debug("Adding event '%s' to calendar" % (title,))

        # Set up event properties
        event = {
            "summary": title,
            "location": loc,
            "description": desc,
            "start": dict(dateTime=start.strftime(TIME_OUT_FMT)),
            "end": dict(dateTime=end.strftime(TIME_OUT_FMT)),
        }

        r = self.cal_service.events().insert(calendarId=self.cal_id, body=event).execute()

        logging.debug("Event '%s' created" % (r["summary"],))

    def run(self):
        """
        Finds all MyTracks files in Google Drive and creates events in
        Google Calendar according to their properties
        """
        for filename, file_data in self.kml_file_data():
            start, end, coords, desc = self.parse_kml_data(file_data)
            if not self.event_exists(filename, start, end):
                self.add_event(filename, start, end, coords, desc)

def main():

    try:
        Tracks2Cal(cal_name="TEST_CAL").run()
    except AccessTokenRefreshError:
        logging.critical("The credentials have been revoked or expired, please re-run the application to re-authorize")


if __name__ == '__main__':
    # https://google-api-client-libraries.appspot.com/documentation/drive/v2/python/latest/
    # https://google-api-client-libraries.appspot.com/documentation/calendar/v3/python/latest/
    logging.basicConfig(format="[%(asctime)s][%(levelname)s]: %(message)s", level=logging.DEBUG)
    main()
