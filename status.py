#!/usr/bin/env python

from __future__ import unicode_literals, division, absolute_import, print_function

import evelink
import requests
import dataset
from datetime import datetime
import sqlite3
import os.path
import sys

DB_DIR = 'db'

if not os.path.exists(DB_DIR):
    os.mkdir(DB_DIR)

EVE_DB = 'rub11-sqlite3-v1.db'
EVE_DB_PATH = os.path.join(DB_DIR, EVE_DB)

# Make sure the static db exists
if not os.path.exists(EVE_DB_PATH):
    print("Please download the latest database by running the following commands:")
    print("cd db")
    print("wget http://zofu.no-ip.de/rub11/%s.bz2" % EVE_DB)
    print("bunzip2 %s.bz2" % EVE_DB)
    sys.exit(1)


conn = sqlite3.connect(EVE_DB_PATH) # Eve online static db
db = dataset.connect("sqlite:///%s/evetools.db" % DB_DIR) # evetools cache db


def to_roman(n):
    return ['I', 'II', 'III', 'IV', 'V'][n - 1]


def timestamp_to_string(timestamp, reverse=False):
    completion = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    if reverse:
        age = now - completion
    else:
        age = completion - now
    agestr = []
    if age.days > 0:
        agestr.append("%dd" % age.days)
    secs = age.seconds
    hours, minutes, seconds = secs // 3600, secs // 60 % 60, secs % 60
    if hours > 0:
        agestr.append("%02dh" % hours)
    if minutes > 0:
        agestr.append("%02dm" % minutes)
    if seconds > 0:
        agestr.append("%02ds" % seconds)
    return " ".join(agestr)


def dbquery(sql, uid):
    c = conn.cursor()

    c.execute(sql % uid)
    res = c.fetchone()
    c.close()
    return res[0]


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
    active_jobs = [v for v in char.industry_jobs().result.values() if v['delivered'] == False]

    if not active_jobs: return

    print("Industry Jobs:")

    for v in active_jobs:
        print("   %s" % locationid_to_string(v['container_id']))
        print("      %s | %s | %s" % (activityid_to_string(v['activity_id']),
                                   typeid_to_string(v['output']['type_id']),
                                   timestamp_to_string(v['end_ts'])))


def print_orders(char, api):
    """List active orders"""
    
    active_orders = [order for id, order in char.orders().result.iteritems() if order['status'] == 'active']

    if not active_orders: return

    print("Orders:")

    import locale
    locale.setlocale(locale.LC_ALL, '')

    total_isk = 0

    for order in active_orders:
        total_isk += order['price'] * order['amount_left']
        print("  %-50s  %14s %4d units" % (typeid_to_string(order['type_id']),
                                                 "{0:n} ISK".format(order['price']).replace(',', ' '),
                                                 order['amount_left']))

    print("Total: %10s" % "{0:n} ISK".format(int(total_isk)).replace(',', ' '))


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
    import locale
    locale.setlocale(locale.LC_ALL, '')
    balance = "{0:n} ISK".format(balance).replace(',', ' ')
    print("Wallet:", balance)

    # Skill points and clone
    char_skillpoints = character_sheet['skillpoints']
    char_clone_skillpoints = character_sheet['clone']['skillpoints']
    print("Skillpoints:", char_skillpoints)
    print("Clone Skillpoints:", char_clone_skillpoints)
    if char_clone_skillpoints < char_skillpoints:
        print("WARNING: CLONE UPDATE REQUIRED")

    # Skill queue
    print("Skill queue: ")
    print("%29s %17s %19s" % (format("Skill", '^25'),
                              format("ETA", '^17'),
                              format("Finish", '^19')))
    for skill in char.skill_queue().result:
        print("%30s %3s %17s %19s" % (typeid_to_string(skill['type_id']),
                                      to_roman(skill['level']),
                                      timestamp_to_string(skill['end_ts']), datetime.fromtimestamp(skill['end_ts'])))

def main(apikey):
    from evelink.cache.sqlite import SqliteCache
    evelink_cache = SqliteCache('db/evelink_cache.db')

    api = evelink.api.API(api_key=apikey,
                          cache=evelink_cache)

    a = evelink.account.Account(api)

    for char_id in a.characters().result:
        print("-" * 30)
        char = evelink.char.Char(char_id, api)
        print_charactersheet(char, api)
        print_industry_jobs(char, api)
        print_orders(char, api)


if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("config.yml not found")
        print("please edit config_example.yml and rename it to config.yml")

        sys.exit(1)

    import yaml
    config = yaml.load(file('config.yml'))

    main((config['key'], config['verification']))
