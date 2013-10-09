#!/usr/bin/python

from flask import Flask, session, request, render_template, redirect
from oauth2client.client import OAuth2WebServerFlow, credentials_from_code
from tracks2cal import Tracks2Cal

import pickle
import logging
import json

CONFIG = json.load(open("config.json", "r"))

OAUTH_SCOPE =[
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar",
]

app = Flask(__name__)
app.secret_key = CONFIG["session_key"]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/auth", methods=["POST"])
def auth():
    # Redirect to OAuth flow
    flow = OAuth2WebServerFlow(CONFIG["client_id"], CONFIG["client_secret"], OAUTH_SCOPE, request.url_root + "run")
    return redirect(flow.step1_get_authorize_url())

@app.route("/run", methods=['GET'])
def run():

    code = request.args.get('code', None)
    if code:
        credentials = credentials_from_code(CONFIG["client_id"], CONFIG["client_secret"], OAUTH_SCOPE, code, request.url_root + "run")
        #Tracks2Cal(credentials).run()
        return "DONE", 200
    else:
        return "ERROR: " + request.args.get("error", ""), 500
    

if __name__ == "__main__":
    app.run(debug=True)
