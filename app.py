#!/usr/bin/python

from flask import Flask, session, request, render_template, redirect
from oauth2client.client import OAuth2WebServerFlow, Credentials, credentials_from_code
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
    return render_template("index.html", need_auth=("creds" not in session))

@app.route("/logout")
def logout():
    if "creds" in session:
        del session["creds"]
    return redirect("/")

@app.route("/doauth", methods=["POST"])
def doauth():
    # Redirect to OAuth flow
    flow = OAuth2WebServerFlow(CONFIG["client_id"], CONFIG["client_secret"], OAUTH_SCOPE, request.url_root + "authcallback")
    return redirect(flow.step1_get_authorize_url())

@app.route("/authcallback")
def authcallback():
    code = request.args.get('code', None)
    if code:
        temp = credentials_from_code(CONFIG["client_id"], CONFIG["client_secret"], OAUTH_SCOPE, code, request.url_root + "authcallback")
        session["creds"] = temp.to_json()
        return redirect("/")
    else:
        return render_template("error.html", message=request.args.get("error", ""))

@app.route("/run", methods=["POST"])
def run():
    if "creds" in session:
        creds = Credentials.new_from_json(session["creds"])
        #Tracks2Cal(creds).run()
        return "DONE", 200
    else:
        return render_template("error.html", message="No auth token found")

if __name__ == "__main__":
    app.run(debug=True)
