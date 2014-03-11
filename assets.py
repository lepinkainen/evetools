#!/usr/bin/env python

from __future__ import unicode_literals, division, absolute_import, print_function

import evelink
import requests
import dataset
from datetime import datetime
import time
import sqlite3
import os.path
import sys
from util import *

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

def buy_price_from_evecentral(typeid):
    table = db['buy_prices']

    # check cache first
    pricedata = table.find_one(typeid=typeid)
    if pricedata:
        timestamp = pricedata.get("timestamp")
        age = time.time() - timestamp

        # cache things for 1 hour
        if age < 3600:
            return float(pricedata.get("median"))

    # cached data not found, get it online
    import xml.etree.ElementTree as ET
    r = requests.get("http://api.eve-central.com/api/marketstat?typeid=%s" % typeid)
    xml = r.content
    root = ET.fromstring(xml)

    median_price = root.findall(".//buy/median")[0].text
    avg_price = root.findall(".//buy/avg")[0].text
    min_price = root.findall(".//buy/min")[0].text
    max_price = root.findall(".//buy/max")[0].text

    # cache
    table.upsert(dict(typeid=typeid,
                      median=float(median_price),
                      avg=float(avg_price),
                      min=float(min_price),
                      max=float(max_price),
                      timestamp=time.time()),
                 ['typeid'])
    return float(median_price)


def print_assets(char, api):
    assets = db['assets']

    asset_data = []
    grand_total = 0

    for k, v in char.assets().result.iteritems():
        print("Location: ", locationid_to_string(v['location_id']))
        for item in v['contents']:
            quantity = item['quantity']
            price_median = buy_price_from_evecentral(item['item_type_id'])

            price_total = quantity * price_median
            grand_total += price_total

            print("   %-53s %5d %10.2f ISK | %.2f ISK" % (typeid_to_string(item['item_type_id']), quantity, price_median, price_total))

            asset_data.append(dict(char_id=char.char_id,
                               container_id = None,
                               container_name = None,
                               location_id = v['location_id'],
                               location_name = locationid_to_string(v['location_id']),
                               type_id = item['item_type_id'],
                               name = typeid_to_string(item['item_type_id']),
                               quantity = quantity,
                               price_median = price_median,
                               timestamp=time.time()
                               ))

            # insert subitems if the item is a container
            for subitem in item.get('contents', []):
                quantity = subitem['quantity']
                price_median = buy_price_from_evecentral(subitem['item_type_id'])

                price_total = quantity * price_median
                grand_total += price_total


                asset_data.append(dict(char_id=char.char_id,
                                   # parent item
                                   container_id = item['item_type_id'],
                                   container_name = typeid_to_string(item['item_type_id']),
                                   # location of this item (And the parent of course)
                                   location_id = v['location_id'],
                                   location_name = locationid_to_string(v['location_id']),
                                   # item ID, name, quantity and approximate price
                                   type_id = subitem['item_type_id'],
                                   name = typeid_to_string(subitem['item_type_id']),
                                   quantity = quantity,
                                   price_median = price_median,
                                   timestamp=time.time()
                                   ))

                print("      %-50s %5d %10.2f ISK | %.2f ISK" % (typeid_to_string(subitem['item_type_id']), subitem['quantity'], price_median, price_total))

    assets.insert_many(asset_data)

    return grand_total


def main(apikey):
    from evelink.cache.sqlite import SqliteCache
    evelink_cache = SqliteCache('db/evelink_cache.db')

    api = evelink.api.API(api_key=apikey,
                          cache=evelink_cache)

    a = evelink.account.Account(api)

    # clear the table, makes easier to keep it up to date
    # updating would work, but removing items that no longer exists is a pain
    db['assets'].drop()

    try:
        for char_id in a.characters().result:
            print("-" * 30)
            char = evelink.char.Char(char_id, api)
            grand_total = print_assets(char, api)

            print("*" * 30)
            print(grand_total, "ISK")
            print("*" * 30)
    except evelink.api.APIError, e:
        print("Api Error:", e)



if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("config.yml not found")
        print("please edit config_example.yml and rename it to config.yml")

        sys.exit(1)

    import yaml
    config = yaml.load(file('config.yml'))

    main((config['key'], config['verification']))
