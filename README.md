MyTracks2Cal
============

Makes entries in Google Calendar based on the KML files generated by MyTracks

The [Android MyTracks](https://play.google.com/store/apps/details?id=com.google.android.maps.mytracks) application has an option to sync all tracks with Google Drive.
This script takes the files synced to Google Drive and adds corresponding events to Google Calendar.

Permissions
===========

This script downloads files from Google Drive and creates Google Calendar events.
It therefore requires read-only access to your Google Drive and read/write access to Google Calendar.

No existing Calendar events are deleted, only new ones added.

Installing the Prerequisites
============================

* `apt-get install python2.7 python2.7-dev`
* `apt-get install gcc`
* `apt-get install libxml2-dev libxslt1-dev`
* `apt-get install python-pip`
* `pip install virtualenv`

Virtual Environment
===================

* Create: `virtualenv --distribute venv`
* Activate: `source venv/bin/activate`
* Deactivate `deactivate`

Install pip Packages
====================

* `pip install -r requirements.txt`

OAuth
=====

This project uses OAuth to connect to Google

`client_secrets.json` is used for storing OAuth information

Until I figure out a way to properly distribute this data, it won't be included in the repository.

Running the Script
==================

1.  Register for API access at `https://code.google.com/apis/console` and download the `client_secrets.json` file into the repository.
2.  Activate the virtual environment.
3.  Optional - Open the script and modify the `folder_name` and `cal_name` parameters to suit your setup.
4.  Run the script.
5.  Authorize the project to access your Google Drive and Google Calender.
6.  Wait for all the KML files to be parsed and added to your calendar.
