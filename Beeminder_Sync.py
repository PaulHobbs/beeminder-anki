# -*- coding: utf-8 -*-
# by: muflax <mail@muflax.com>, 2012
# License: GNU GPLv3 (or later) <http://www.gnu.org/copyleft/gpl.html>

# This add-on sends your review stats to Beeminder (beeminder.com) and so keeps
# your graphs up-to-date.
#
# Experimental! Use at your own risk.
#
# 1. Create goal at Beeminder.
# 2. Use type Odometer.
# 3. Set variables in add-on file.
# 4. Review!
# 5. Sync to AnkiWeb.

####################################################
# Adjust these variables to your beeminder config. #
####################################################
# Login Info
ACCOUNT = "your account" # beeminder account name
TOKEN   = "your token"   # available at <https://www.beeminder.com/api/v1/auth_token.json>

# Goal names - Set either to "" if you don't use this kind of goal. The name is the short part in the URL.
REP_GOAL = "anki" # Goal for total reviews / day, e.g. "anki" if your goal is called "anki".
NEW_GOAL = ""     # goal for new cards / day, e.g. "anki-new".

# Offsets - Skip that many earlier reps so your graph can start at 0 (for old decks - set to 0 if unsure).
REP_OFFSET = 0
NEW_OFFSET = 0

#####################
# Code starts here. #
#####################

# Debug - Skip this.
SEND_DATA = True # set to True to actually send data

from anki.hooks import wrap
import anki.sync
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, openLink

import json
import datetime
import httplib, urllib
import logging
import os

log = logging.getLogger()
LOG_FILE = os.path.join(os.path.dirname(__file__),
                        'Beeminder_Sync.log')
FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT, filename=LOG_FILE, level=logging.DEBUG)


def checkCollection(col=None, force=False):
    """Check for unreported cards and send them to beeminder."""
    col = col or mw.col
    if col is None:
        return

    def checkStat(count_type, goal, offset, select_query, timestamp_query):
        new_cards      = col.db.first(select_query)[0]
        last_timestamp = col.conf.get(count_type + 'Timestamp', 0)
        timestamp      = col.db.first(timestamp_query)
        if timestamp is not None:
            timestamp = timestamp[0]
        reportCards(col, new_cards, timestamp, count_type + 'Total', goal, offset)

        if (force or timestamp != last_timestamp) and SEND_DATA:
            col.conf[count_type + 'Timestamp'] = timestamp
            col.setMod()

    # reviews
    if REP_GOAL:
        checkStat(
            count_type="beeminderRep",
            goal=REP_GOAL,
            offset=REP_OFFSET,
            select_query="select count() from revlog where type = 0",
            timestamp_query="select id/1000 from revlog order by id desc limit 1")

    # new cards
    if NEW_GOAL:
        checkStat(
            count_type="beeminderNew",
            goal=NEW_GOAL,
            offset=NEW_OFFSET,
            select_query="select count(distinct(id)) from revlog where type = 0",
            timestamp_query="select id/1000 from revlog where type = 0 order by id desc limit 1")

    if force and (REP_GOAL or NEW_GOAL):
        showInfo("Synced with Beeminder.")


def reportCards(col, total, timestamp, count_type, goal, offset=0, force=False):
    """Sync card counts and send them to beeminder."""

    if not SEND_DATA:
        print "type:", count_type, "count:", total

    # get last count and new total
    last_total = col.conf.get(count_type, 0)
    total      = max(0, total - offset)

    if not force and (total <= 0 or total == last_total):
        if not SEND_DATA:
            print "nothing to report..."
        return

    if total < last_total: #something went wrong
        raise Exception("Beeminder total smaller than before")

    # build data
    date = "%d" % timestamp
    comment = "anki update (+%d)" % (total - last_total)
    data = {
        "date": date,
        "value": total,
        "comment": comment,
    }

    if SEND_DATA:
        account = ACCOUNT
        token = TOKEN
        postData(goal, data)
        col.conf[count_type] = total
    else:
        print "would send:"
        print data

def sendApi(account, token, cmd, method='POST', data=None):
    base = "www.beeminder.com"
    api = "/api/v1/users/%s/goals/%s.json" % (account, cmd)

    headers = {"Content-type": "application/x-www-form-urlencoded",
               "Accept": "text/plain"}

    params = {"auth_token": token}
    params.update(data or {})
    params = urllib.urlencode(params)

    conn = httplib.HTTPSConnection(base)
    log.info("%sing %s", method, api)
    conn.request(method, api, params, headers)
    response = conn.getresponse()
    if not response.status == 200:
        raise Exception("transmission failed:", response.status, response.reason, response.read())
    content = response.read()
    conn.close()
    return content


def currentValue(goal):
    return json.loads(
        sendApi(ACCOUNT, TOKEN, goal, method='GET'))


def postData(goal, data):
    old = currentValue(goal)['curval']
    log.debug("Current value for goal %s is %s", goal, old)
    log.debug("Checking to see if we should replace with %s", data['value'])
    if old != data['value']:
        sendApi(ACCOUNT, TOKEN, '%s/datapoints' % goal, data=data)


def beeminderUpdate(obj, _old=None):
    ret = _old(obj)
    col = mw.col or mw.syncer.thread.col
    if col is not None:
        checkCollection(col)

    return ret

# convert time to timestamp because python sucks
def timestamp(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = time - epoch
    timestamp = "%d" % delta.total_seconds()
    return timestamp

# run update whenever we sync a deck
anki.sync.Syncer.sync = wrap(anki.sync.Syncer.sync, beeminderUpdate, "around")
