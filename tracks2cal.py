#!/usr/lib/python

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
    
        #self.parse_kml_data(open("test.kml", "r").read())

    def get_calendar_id(self):
        """Get the calendar id to use when adding events"""

        # TODO: pagination
        for x in self.cal_service.calendarList().list().execute()["items"]:
            if x["summary"] == self.cal_name:
                return x["id"]
        else:
            print ("No calendar named '%s' found, creating one" % (self.cal_name,))
            resp = self.cal_service.calendars().insert(body={"summary": self.cal_name}).execute()
            return resp["id"]

    def parse_kml_data(self, data):
        """Parse the KML data and return a (start, end, coords, description) tuple"""
        kml_root = etree.fromstring(data)
        ns = kml_root.nsmap

        print ns

        pms = kml_root.find("Document").findall("Placemark")

        print pms

        start_time = pms[0].find("TimeStamp").find("when").text
        end_time = pms[2].find("TimeStamp").find("when").text
        desc = pms[2].find("description").text

        # Convert "long,lat[,altitude]" to "lat,long"
        temp = pms.find("Point").find("coordinates").text
        coords = ",".join(temp.split(",")[1::-1])

        print start_time
        print end_time
        print coords
        print desc

        return start_time, end_time, coords, desc

    def kml_file_data(self):
        """
        Generator for KML file data
        
        Grabs the KML data from Google Drive and generates (filename, file_data) objects
        """
        try:
            # Get the "My Tracks" folder id
            folder = self.drive_service.files().list(q="mimeType='application/vnd.google-apps.folder' and title='%s'" % (self.folder_name,)).execute()["items"]
            if not folder:
                print ("No '%s' folder found, exiting", (self.folder_name,))
                return

            folder_id = folder[0]["id"]

            # Get the children of the my tracks folder
            for x in self.drive_service.children().list(folderId=folder_id, q="mimeType='application/vnd.google-earth.kml+xml' and trashed=False").execute()["items"]:
                file_ = self.drive_service.files().get(fileId=x["id"]).execute()

                # Download the data of the kml file
                r, data = self.drive_service._http.request(file_["downloadUrl"])
                if r.status == 200:
                    yield file_["title"], data
                else:
                    print ("Error occurred downloading KML file: %s" % (str(r),))
                

        except (errors.HttpError, KeyError), e:
            print ("Error occurred: %s" % (str(e),))
            return

    def event_exists(self, title, start, end):
        """Checks if the event already exists in Google Calendar"""

        # TODO?: Add to start, subtract from end
        self.cal_service.events().list(timeMax=start, timeMin=end).execute()

    def add_event(self, title, start, end, loc="", desc=""):
        """Adds an event to Google Calendar"""

        return
        event = {
            "summary": title,
            "location": loc,
            "description": desc,
            "start": dict(datetime=start), #convert to string, ex: '2011-06-03T10:00:00.000-07:00'
            "end": dict(datetime=end), #convert to string, ex: '2011-06-03T10:00:00.000-07:00'
        }

        self.cal_service.events().insert(calendarDd=self.cal_id, body=event)

    def run(self):
        """
        Finds all MyTracks files in Google Drive and creates events in
        Google Calendar according to their properties
        """
        return
        for filename, file_data in self.kml_file_data(drive_service):
            start, end, coords, desc = self.parse_kml_data(file_data)
            if not self.event_exists(filename, start, end):
                self.add_event(filename, start, end, coords, desc)

def main():

    try:
        Tracks2Cal(cal_name="TEST_CAL").run()
    except AccessTokenRefreshError:
        print ("The credentials have been revoked or expired, please re-run the application to re-authorize")


if __name__ == '__main__':
    # https://google-api-client-libraries.appspot.com/documentation/drive/v2/python/latest/
    # https://google-api-client-libraries.appspot.com/documentation/calendar/v3/python/latest/
    
    main()
