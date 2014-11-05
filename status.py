#!/usr/bin/env python

from __future__ import unicode_literals, division, absolute_import, print_function

from datetime import datetime
from dateutil.relativedelta import *
import sqlite3
import os.path
import sys

import evelink
import dataset

from util import *

DB_DIR = 'db'

if not os.path.exists(DB_DIR):
    os.mkdir(DB_DIR)

# latest zofu's db dump
EVE_DB = 'rub112-sqlite3-v1.db'
EVE_DB_PATH = os.path.join(DB_DIR, EVE_DB)

# Make sure the static db exists
if not os.path.exists(EVE_DB_PATH):
    print("Please download the latest database by running the following commands:")
    print("cd db")
    print("wget http://zofu.no-ip.de/rub112/%s.bz2" % EVE_DB)
    print("bunzip2 %s.bz2" % EVE_DB)
    sys.exit(1)


conn = sqlite3.connect(EVE_DB_PATH) # Eve online static db
db = dataset.connect("sqlite:///%s/evetools.db" % DB_DIR) # evetools cache db


def dbquery(sql, uid):
    c = conn.cursor()

    c.execute(sql % uid)
    res = c.fetchone()
    c.close()
    if res:
        return res[0]
    else:
        return "Unknown(%d)" % uid


def activityid_to_string(uid):
    return dbquery("select activityName from ramActivities where activityID = %d;", uid)


def locationid_to_string(uid):
    return dbquery("select stationName from staStations where stationID = %d;", uid)


def typeid_to_string(uid):
    return dbquery("select typeName from invTypes where typeID = %d;", uid)


def print_contracts(char, api):
    for k, v in char.contracts().result.iteritems():
        print (k, v)


def print_industry_jobs(char, api):
    """List active industry jobs"""
    #active_jobs = [v for v in char.industry_jobs().result.values() if v['delivered'] == False and v['status'] != "failed"]

    active_jobs = None
    if not active_jobs: return

    print("Industry Jobs:")

    for job in active_jobs:
        print("   %s" % locationid_to_string(job['container_id']))
        print("      %s | %s | %s" % (activityid_to_string(job['activity_id']),
                                   typeid_to_string(job['output']['type_id']),
                                   timestamp_to_string(job['end_ts'])))


def print_orders(char, api):
    """List active orders"""

    active_orders = [order for oid, order in char.orders().result.iteritems() if order['status'] == 'active']
    if not active_orders: return

    # sort by timestamp, first ones to expire on top
    active_orders = sorted(active_orders, key=lambda item: item['timestamp'], reverse=False)

    print("Orders (%d):" % len(active_orders))

    total_isk = 0

    for order in active_orders:
        total_isk += order['price'] * order['amount_left']

        td = relativedelta((datetime.fromtimestamp(order['timestamp']) + relativedelta(days=order['duration'])), datetime.now())
        tdstr = "%dd %dh %dm" % (td.days, td.hours, td.minutes)

        msg = (u"  %-50s  %17s %4d units end: %s" % (typeid_to_string(order['type_id']),
                                                     format_currency(order['price']),
                                                     order['amount_left'],
                                                     tdstr))
        print(msg.encode('utf-8'))

    print("Total: %s" % format_currency(total_isk))


def print_assets(char, api):
    for k, v in char.assets().result.iteritems():
        print("Location: ", locationid_to_string(v['location_id']))
        for item in v['contents']:
            print("   %-53s %d" % (typeid_to_string(item['item_type_id']), item['quantity']))
            for subitem in item.get('contents', []):
                print("      %-50s %d" % (typeid_to_string(subitem['item_type_id']), subitem['quantity']))


def print_charactersheet(char, api):
    # Character info needs to be fetched from two separate places..
    character_sheet = char.character_sheet().result
    character_info = evelink.eve.EVE(api=api).character_info_from_id(char.char_id).result

    print("Name: %s [%s] | Age: %s" % (character_sheet['name'],
                                       character_sheet['corp']['name'],
                                       timestamp_to_string(character_sheet['create_ts'], True)))

    print("Location: %s Ship: %s (%s)" % (character_info['location'], character_info['ship']['type_name'], character_info['ship']['name']))

    # Balance
    balance = int(character_sheet['balance'])
    print("Wallet:", format_currency(balance))

    # Skill points and clone
    char_skillpoints = character_sheet['skillpoints']
    char_clone_skillpoints = character_sheet['clone']['skillpoints']
    print("Skillpoints:", char_skillpoints)
    print("Clone Skillpoints:", char_clone_skillpoints)
    if char_clone_skillpoints < char_skillpoints:
        print("WARNING: CLONE UPDATE REQUIRED")

    # Skill queue
    skill_queue = char.skill_queue().result

    # Don't print empty or paused skill queue
    if not skill_queue[0]['end_ts']: return

    if len(skill_queue) > 5:
        print("Skill queue (%d skills total): " % len(skill_queue))
    else:
        print("Skill queue: ")
    print("%29s %17s %19s" % (format("Skill", '^25'),
                              format("ETA", '^17'),
                              format("Finish", '^19')))
    queue_length = relativedelta()
    now = datetime.now()

    for skill in skill_queue[:5]:
        if skill['end_ts']:
            end = datetime.fromtimestamp(skill['end_ts'])
            # skip skills that have already been trained , but are in the cache
            if end < now: continue

            delta = relativedelta(end, now)
            queue_length += delta

            eta = timestamp_to_string(skill['end_ts'])
            finish = datetime.fromtimestamp(skill['end_ts'])
        else:
            eta = "None"
            finish = "Never"
            queue_length=relativedelta(hours=+72)

        print("%30s %3s %17s %19s" % (typeid_to_string(skill['type_id']),
                                      to_roman(skill['level']),
                                      eta,
                                      finish))

    if queue_length.days == 0 and queue_length.hours < 24:
        print("Free room in skill queue!")

def main(apikey):
    from evelink.cache.sqlite import SqliteCache
    evelink_cache = SqliteCache('db/evelink_cache.db')

    api = evelink.api.API(api_key=apikey,
                          cache=evelink_cache)

    a = evelink.account.Account(api)

    try:
        for char_id in a.characters().result:
            print("-" * 30)
            char = evelink.char.Char(char_id, api)
            print_charactersheet(char, api)
            print_industry_jobs(char, api)
            print_orders(char, api)
    except evelink.api.APIError, e:
        print("Api Error:", e)



if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("config.yml not found")
        print("please edit config_example.yml and rename it to config.yml")

        sys.exit(1)

    import yaml
    config = yaml.load(file('config.yml'))

    # Just one account specified
    if 'key' in config and 'verification' in config:
        main((config['key'], config['verification']))
    else:
        for account in config.keys():
            main((config[account]['key'], config[account]['verification']))
