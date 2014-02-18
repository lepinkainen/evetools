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


class CharacterFactory(object):
    @staticmethod
    def create_character(api, char_id):
        char = evelink.char.Char(char_id, api)
        character_sheet = char.character_sheet().result
        character_info = evelink.eve.EVE(api=api).character_info_from_id(char.char_id).result

        c = Character()
        c.cid = char_id
        c.name = character_sheet['name']
        c.corporation = character_sheet['corp']['name']
        c.age = character_sheet['create_ts']
        c.location = character_info['location']
        c.balance = int(character_sheet['balance'])
        c.skillpoints = character_sheet['skillpoints']
        c.clone_skillpoints = character_sheet['clone']['skillpoints']
        c.skill_queue = char.skill_queue().result
        c.active_jobs = [v for v in char.industry_jobs().result.values() if v['delivered'] == False]
        c.active_orders = [order for order in char.orders().result.values() if order['status'] == 'active']

        return c

class Character(object):
    cid = None
    name = None
    corporation = None
    age = None
    location = None
    balance = None
    skillpoints = None
    clone_skillpoints = None
    active_jobs = None
    active_orders = None
    skill_queue = None

    def get_balance_formatted(self):
        import locale
        locale.setlocale(locale.LC_ALL, '')
        return "{0:n} ISK".format(self.balance).replace(',', ' ')


    def get_skill_queue_items(self):
        items = []
        # skill name skill level, time to end, end time
        for skill in self.skill_queue:
            items.append(["%s %s" % (typeid_to_string(skill['type_id']), to_roman(skill['level'])),
                                timestamp_to_string(skill['end_ts']),
                                datetime.fromtimestamp(skill['end_ts'])])

        return items

    def get_active_jobs_items(self):
        items = []

        for job in self.active_jobs:
            items.append([activityid_to_string(job['activity_id']),
                         typeid_to_string(job['output']['type_id']),
                         timestamp_to_string(job['end_ts'])])

        return items



class CharacterSummary(npyscreen.ActionForm):
    """Display a summary of all available characters"""

    GRID_WIDTH = 80

    last_updated_field = None
    character_fields = {}

    def while_waiting(self):
        self.last_updated_field.value = datetime.now()
        for char_id in self.account.characters().result:
            c = CharacterFactory.create_character(self.parentApp.api, char_id)
            self.update_character(c)
        self.display()

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

        self.account = evelink.account.Account(self.parentApp.api)

        self.last_updated_field = self.add(npyscreen.TitleFixedText, name="Last Update", editable=False, width=self.GRID_WIDTH)
        self.last_updated_field.value = datetime.now()
        self.separator()

        # store all character fields for updating
        self.character_fields = {}

        for char_id in self.account.characters().result:
            c = CharacterFactory.create_character(self.parentApp.api, char_id)

            self.display_character(c)
            self.update_character(c)
            self.display_skill_queue(c)
            self.update_skill_queue(c)
            self.display_industry_jobs(c)
            self.separator()


    def separator(self):
        self.add(npyscreen.FixedText, value="."*self.GRID_WIDTH, editable=False)
        self.add(npyscreen.FixedText, value=" "*self.GRID_WIDTH, editable=False)


    def update_character(self, character):
        fields = self.character_fields[character.cid]
        fields['name_corp'].value = "%s [%s]" % (character.name, character.corporation)
        fields['age'].value = timestamp_to_string(character.age, True)
        fields['location'].value = character.location
        fields['balance'].value = character.get_balance_formatted()
        fields['skillpoints'].value = character.skillpoints
        fields['clone_skillpoints'].value = character.clone_skillpoints

        # adjust height and set updated items

        #npyscreen.notify_wait(fields.keys())

        items = character.get_skill_queue_items()
        try:
            fields['skill_queue'].height=len(items)+5
            fields['skill_queue'].value = items
        except:
            pass

        items = character.get_active_jobs_items()
        try:
            fields['active_jobs'].height=len(items)+3
            fields['active_jobs'].value = items
        except:
            pass

    def display_character(self, character):
        fields = {}

        # Basic information
        fields['name_corp'] = self.add(npyscreen.TitleFixedText, name="Name:", editable=False)  #  static data
        fields['age'] = self.add(npyscreen.TitleFixedText, name="Age:", editable=False)
        fields['location'] = self.add(npyscreen.TitleFixedText, name="Location:", editable=False)

        # Balance
        fields['balance'] = self.add(npyscreen.TitleFixedText, name="Wallet:", editable=False)

        # Skill points and clone
        fields['skillpoints'] = self.add(npyscreen.TitleFixedText, name="Skillpoints:", editable=False)
        fields['clone_skillpoints'] = self.add(npyscreen.TitleFixedText, name="Clone SP:", editable=False)

        self.character_fields[character.cid] = fields


    def update_skill_queue(self, character):
        items = character.get_skill_queue_items()
        self.character_fields[character.cid]['skill_queue'].height = len(items)+3
        self.character_fields[character.cid]['skill_queue'].value = items


    def display_skill_queue(self, character):
        titles = ['Skill', 'ETA', 'Finish']
        #npyscreen.notify_wait("Before %s" % self.character_fields[character.cid].keys())
        self.character_fields[character.cid]['skill_queue'] = self._display_grid(titles)
        #npyscreen.notify_wait("After %s" % self.character_fields[character.cid].keys())
        self.update_skill_queue(character)


    def display_industry_jobs(self, character):
        items = character.get_active_jobs_items()
        if not items: return
        titles = ['Type', 'Item', 'ETA']
        self.character_fields[character.cid]['active_jobs'] = self._display_grid(titles)

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

    def _display_grid(self, titles):
        return self.add(npyscreen.GridColTitles,
                        col_titles=titles,
                        width=self.GRID_WIDTH,
                        height=3,
                        editable=False,
                        column_width=25)

class EveStatus(npyscreen.NPSAppManaged):
    index = 0
    api = None

    keypress_timeout_default = 20

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

        # API with cache and correct api key
        self.api = evelink.api.API(api_key=apikey, cache=evelink_cache)

        self.addForm("MAIN", CharacterSummary, name="MAIN")
        self.addForm("Detailed", CharacterSummary, name="Detailed")

    def onCleanExit(self):
        pass

def class_test():
    if not os.path.exists('config.yml'):
        print("config.yml not found")
        print("please edit config_example.yml and rename it to config.yml")
        sys.exit(1)

    import yaml
    config = yaml.load(file('config.yml'))

    print "Config loaded"

    apikey = (config['key'], config['verification'])

    from evelink.cache.sqlite import SqliteCache
    evelink_cache = SqliteCache('db/evelink_cache.db')

    # API with cache and correct api key
    api = evelink.api.API(api_key=apikey, cache=evelink_cache)

    print "API connected"

    # account data
    a = evelink.account.Account(api)

    # loop through character id's in api
    for char_id in a.characters().result:
        print "Creating character", char_id
        c = CharacterFactory.create_character(api, char_id)
        print c.name
        print c.get_skill_queue_items()
        print c.get_active_jobs_items()


if __name__ == '__main__':
    #class_test()
    app = EveStatus()
    app.run()
