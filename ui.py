#!/usr/bin/env python
# coding=UTF-8

import npyscreen
import curses

# http://npyscreen.readthedocs.org/introduction.html

# Updating widgets live:
# https://groups.google.com/forum/#!msg/npyscreen/rshTAUyp0pY/0XNlT7HFZcMJ

import evelink
import requests
import dataset
from datetime import datetime
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


class CharacterSummary(npyscreen.ActionForm):
    """Display a summary of all available characters"""

    GRID_WIDTH = 80

    def while_waiting(self):
        pass

    def on_ok(self):
        self.parentApp.switchForm(None)

    def change_forms(self, *args, **keywords):
        npyscreen.notify_wait(self.name)
        if self.name == "MAIN":
            change_to = "Detailed"
        else:
            change_to = "MAIN"

        self.parentApp.change_form(change_to)

    def create(self):
        self.framed = False


        self.add_handlers({"^T": self.change_forms,
                           "^R": self.display,
                           curses.ascii.ESC: self.on_ok})


        a = evelink.account.Account(self.parentApp.api)

        self.add(npyscreen.FixedText, value=datetime.now(), editable=False, width=self.GRID_WIDTH)

        for char_id in a.characters().result:
            if self.name == "MAIN":
                self.display_character(char_id)
                self.separator()
            else:
                self.display_character(char_id)
                self.display_skill_queue(char_id)
                self.display_orders(char_id)
                self.display_industry_jobs(char_id)
                self.separator()


    def separator(self):
        self.add(npyscreen.FixedText, value="."*self.GRID_WIDTH, editable=False)
        self.add(npyscreen.FixedText, value=" "*self.GRID_WIDTH, editable=False)

    def display_character(self, char_id):

        char = evelink.char.Char(char_id, self.parentApp.api)

        character_sheet = char.character_sheet().result
        character_info = evelink.eve.EVE(api=self.parentApp.api).character_info_from_id(char.char_id).result

        self.add(npyscreen.TitleFixedText, name="Name:", value="%s [%s]" % (character_sheet['name'], character_sheet['corp']['name']), editable=False )
        self.add(npyscreen.TitleFixedText, name="Age:", value=timestamp_to_string(character_sheet['create_ts'], True), editable=False )
        self.add(npyscreen.TitleFixedText, name="Location:", value=character_info['location'], editable=False )

        # Balance
        balance = int(character_sheet['balance'])
        import locale
        locale.setlocale(locale.LC_ALL, '')
        balance = "{0:n} ISK".format(balance).replace(',', ' ')
        self.add(npyscreen.TitleFixedText, name="Wallet:", value=balance, editable=False)

        # Skill points and clone
        char_skillpoints = character_sheet['skillpoints']
        char_clone_skillpoints = character_sheet['clone']['skillpoints']
        self.add(npyscreen.TitleFixedText, name="Skillpoints:", value=char_skillpoints, editable=False)
        self.add(npyscreen.TitleFixedText, name="Clone SP:", value=char_clone_skillpoints, editable=False)

        # TODO: current training skill as slider
        #self.add(npyscreen.TitleSlider, name="Spaceship Command  IV", value=58, editable=False, label=True)

    def display_industry_jobs(self, char_id):
        char = evelink.char.Char(char_id, self.parentApp.api)

        active_jobs = [v for v in char.industry_jobs().result.values() if v['delivered'] == False]
        if not active_jobs: return


        items = []
        titles = ['Type', 'Item', 'ETA']

        for job in active_jobs:
            items.append([activityid_to_string(v['activity_id']),
                         typeid_to_string(v['output']['type_id']),
                         timestamp_to_string(v['end_ts'])])

        self._display_grid(items, titles)

    def display_orders(self, char_id):
        char = evelink.char.Char(char_id, self.parentApp.api)

        active_orders = [order for id, order in char.orders().result.iteritems() if order['status'] == 'active']

        if not active_orders: return

        import locale
        locale.setlocale(locale.LC_ALL, '')

        total_isk = 0

        items = []
        titles = ['Item', 'à ISK', 'Amount']

        for order in active_orders:
            total_isk += order['price'] * order['amount_left']
            items.append([typeid_to_string(order['type_id']),
                          "{0:n} ISK".format(order['price']).replace(',', ' '),
                           order['amount_left']])

        self._display_grid(items, titles)

        total_isk = "{0:n} ISK".format(int(total_isk)).replace(',', ' ')
        self.add(npyscreen.TitleFixedText, name="Total:", value=total_isk, editable=False)


    def display_skill_queue(self, char_id):
        char = evelink.char.Char(char_id, self.parentApp.api)

        items = []
        titles = ['Skill', 'ETA', 'Finish']

        for skill in char.skill_queue().result:
            items.append(["%s %s" % (typeid_to_string(skill['type_id']), to_roman(skill['level'])),
                                timestamp_to_string(skill['end_ts']),
                                datetime.fromtimestamp(skill['end_ts'])])

        self._display_grid(items, titles)


    def _display_grid(self, items, titles):
        gcol = self.add(npyscreen.GridColTitles,
                        col_titles=titles,
                        width=self.GRID_WIDTH,
                        height=len(items)+3,
                        editable=False,
                        column_width=25)

        gcol.values = items


#        if char_clone_skillpoints < char_skillpoints:
#            print("WARNING: CLONE UPDATE REQUIRED")


class EveStatus(npyscreen.NPSAppManaged):
    index = 0
    apikey = (2959322, 'dMkRERzI7inBlOE5ikUYbW2NitYnBK8fqHQLlgz68XXaagxNSyj5ItjAD2In1KxE')
    api = None

    keypress_timeout_default = 50

    def while_waiting(self):
        # app -level updates here
        pass

    def change_form(self, name):
        self.switchForm(name)
        self.resetHistory()


    def onStart(self):
        if not os.path.exists('config.yml'):
            print("config.yml not found")
            print("please edit config_example.yml and rename it to config.yml")
            sys.exit(1)

        import yaml
        config = yaml.load(file('config.yml'))

        apikey = (config['key'], config['verification'])

        from evelink.cache.sqlite import SqliteCache
        evelink_cache = SqliteCache('db/evelink_cache.db')

        self.api = evelink.api.API(api_key=apikey, cache=evelink_cache)

        self.addForm("MAIN", CharacterSummary, name="MAIN")
        self.addForm("Detailed", CharacterSummary, name="Detailed")

    def onCleanExit(self):
        pass


if __name__ == '__main__':
    app = EveStatus()
    app.run()
