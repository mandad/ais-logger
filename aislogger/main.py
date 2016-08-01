#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# main.py (part of "AIS Logger")
# Simple AIS logging and display software
#
# Copyright (c) 2006-2009 Erik I.J. Olsson <olcai@users.sourceforge.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

version = 'VERSION_TAG'

# Imports from the Python Standard Library
import sys, os, glob, optparse, logging
import time, datetime
import threading, Queue, collections
import socket, SocketServer
import pickle, codecs, csv, string
import hashlib
import decimal
import time, random
import gettext

# Import add-on Python packages
import sqlite3 as sqlite
import numpy
import serial
import wx
import wx.lib.mixins.listctrl as listmix
from wx.lib.floatcanvas import NavCanvas, FloatCanvas, Resources, Utilities
import wx.lib.colourdb

# Import external (bundled) packages
import external.pydblite as pydblite
from external.configobj import ConfigObj

# Import own modules
import decode
from util import *


# Function for returning the package directory
def package_home(gdict):
    fs_enc = sys.getfilesystemencoding()
    filename = unicode(gdict["__file__"], fs_enc)
    # Hack for py2exe which returns aislogger.exe in path
    if filename.find(".exe") != -1:
        while filename.find(".exe") != -1:
            filename = os.path.split(filename)[0]
        return filename
    return os.path.dirname(filename)



### Fetch command line arguments
# A list of possible config files
configfiles = []

# Create optparse object
cmdlineparser = optparse.OptionParser()
# Add an option for supplying a different config file than the default one
cmdlineparser.add_option("-c", "--config", dest="configfile", help="Specify a config file other than the default")
cmdlineparser.add_option("-n", "--nogui", action="store_true", dest="nogui", default=False, help="Run without GUI, i.e. as a server and logger")
# Parse the arguments
(cmdlineoptions, cmdlineargs) = cmdlineparser.parse_args()
if cmdlineoptions.configfile:
    # Try to open the supplied config file
    try:
        testopen = open(cmdlinepoptions.configfile, 'r')
        testopen.close()
        configfiles = [os.path.abspath(cmdlineoptions.configfile)]
    except (IOError, IndexError):
        # Could not read the file, aborting program
        sys.exit("Unable to open config file. Aborting.")

### Gettext call
gettext.install('aislogger', ".", unicode=False)
#self.presLan_en = gettext.translation("aislogger", "./locale", languages=['en'])
#self.presLan_en.install()
#self.locale = wx.Locale(wx.LANGUAGE_ENGLISH)
#locale.setlocale(locale.LC_ALL, 'EN')

### Load or create configuration
# Create a dictionary containing all available columns (for display)
# as 'dbcolumn': ['description', size-in-pixels]
columnsetup = {'mmsi': [_("MMSI"), 80],
               'mid': [_("Nation"), 55],
               'imo': [_("IMO"), 80],
               'name': [_("Name"), 150],
               'type': [_("Type nbr"), 45],
               'typename': [_("Type"), 80],
               'callsign': [_("CS"), 65],
               'latitude': [_("Latitude"), 110],
               'longitude': [_("Longitude"), 115],
               'georef': [_("GEOREF"), 85],
               'creationtime': [_("Created"), 75],
               'time': [_("Updated"), 75],
               'sog': [_("Speed"), 60],
               'cog': [_("Course"), 60],
               'heading': [_("Heading"), 70],
               'destination': [_("Destination"), 150],
               'eta': [_("ETA"), 80],
               'length': [_("Length"), 45],
               'width': [_("Width"), 45],
               'draught': [_("Draught"), 90],
               'rateofturn': [_("ROT"), 60],
               'navstatus': [_("NavStatus"), 150],
               'posacc': [_("PosAcc"), 55],
               'transponder_type': [_("Transponder type"), 90],
               'bearing': [_("Bearing"), 65],
               'distance': [_("Distance"), 70],
               'remark': [_("Remark"), 150]}

# Set default keys and values
defaultconfig = {'common': {'listmakegreytime': 600,
                            'deleteitemtime': 3600,
                            'showbasestations': True,
                            'showclassbstations': True,
                            'showafterupdates': 3,
                            'updatetime': 2,
                            'listcolumns': 'mmsi, mid, name, typename, callsign, georef, creationtime, time, sog, cog, destination, navstatus, bearing, distance, remark',
                            'alertlistcolumns': 'mmsi, mid, name, typename, callsign, georef, creationtime, time, sog, cog, destination, navstatus, bearing, distance, remark'},
                 'logging': {'logging_on': False,
                             'logtime': '600',
                             'logfile': 'aislogger.db',
                             'logbasestations': False,
                             'logexceptions': False},
                 'iddb_logging': {'logging_on': False,
                                  'logtime': '600',
                                  'logfile': 'id.idb'},
                 'alert': {'remarkfile_on': False,
                           'remarkfile': '',
                           'alertsound_on': False,
                           'alertsoundfile': '',
                           'maxdistance_on': False,
                           'maxdistance': '0'},
                 'position': {'override_on': False,
                              'latitude': '0',
                              'longitude': '0',
                              'position_format': 'dms',
                              'use_position_from': 'any'},
                 'serial_a': {'serial_on': False,
                              'port': '',
                              'baudrate': '38400',
                              'rtscts': False,
                              'xonxoff': False,
                              'send_to_serial_server': False,
                              'send_to_network_server': False},
                 'serial_server': {'server_on': False,
                                   'port': '',
                                   'baudrate': '38400',
                                   'rtscts': False,
                                   'xonxoff': False},
                 'network': {'server_on': False,
                             'server_address': 'localhost',
                             'server_port': '23000',
                             'clients_on': "",
                             'client_addresses': "",
                             'clients_to_serial': "",
                             'clients_to_server': ""},
                 'map': {'object_color': 'Yellow',
                         'old_object_color': 'Grey',
                         'selected_object_color': 'Pink',
                         'alerted_object_color': 'Indian Red',
                         'background_color': 'Cornflower blue',
                         'shoreline_color': 'White',
                         'mapfile': os.path.join(package_home(globals()), 'data/world.dat')}}

# Create a ConfigObj based on dict defaultconfig
config = ConfigObj(defaultconfig, indent_type='', encoding='utf-8')
config.filename = 'default.ini'

# Set the intial comment for the config file
config.initial_comment = ['Autogenerated config file for AIS Logger', "You may edit if you're careful"]

# Set comments for each section and key - only used in config file
config.comments['common'] = ['', 'Common settings for the GUI']
config.comments['logging'] = ['', 'Settings for logging to file']
config.comments['iddb_logging'] = ['', 'Settings for logging the identification database to file']
config.comments['alert'] = ['', 'Settings for alerts and remarks']
config.comments['position'] = ['', 'Set manual position (overrides decoded own position)']
config.comments['serial_a'] = ['', 'Settings for input from serial device A']
config.comments['serial_server'] = ['', 'Settings for sending data through a serial port']
config.comments['network'] = ['', 'Settings for sending/receiving data through a network connection']
config.comments['map'] = ['', 'Map settings']
config['common'].comments['listmakegreytime'] = ['Number of s between last update and greying out an item']
config['common'].comments['deleteitemtime'] = ['Number of s between last update and removing an item from memory']
config['common'].comments['showbasestations'] = ['Enable display of base stations']
config['common'].comments['showclassbstations'] = ['Enable display of AIS Class B stations (small ships)']
config['common'].comments['showafterupdates'] = ['Number of updates to an object before displaying it']
config['common'].comments['listcolumns'] = ['Define visible columns in list view using db column names']
config['common'].comments['alertlistcolumns'] = ['Define visible columns in alert list view using db column names']
config['common'].comments['updatetime'] = ['Number of s between updating the GUI with new data']
config['logging'].comments['logging_on'] = ['Enable file logging']
config['logging'].comments['logtime'] = ['Number of s between writes to log file']
config['logging'].comments['logfile'] = ['Filename of log file']
config['logging'].comments['logbasestations'] = ['Enable logging of base stations']
config['logging'].comments['logexceptions'] = ['Enable exception logging to file (for debugging)']
config['iddb_logging'].comments['logging_on'] = ['Enable IDDB file logging']
config['iddb_logging'].comments['logtime'] = ['Number of s between writes to log file']
config['iddb_logging'].comments['logfile'] = ['Filename of log file']
config['alert'].comments['remarkfile_on'] = ['Enable loading of remark file at program start']
config['alert'].comments['remarkfile'] = ['Filename of remark file']
config['alert'].comments['alertsound_on'] = ['Enable audio alert']
config['alert'].comments['alertsoundfile'] = ['Filename of wave sound file for audio alert']
config['alert'].comments['maxdistance_on'] = ['Enable use of maximum distance for alerts']
config['alert'].comments['maxdistance'] = ['The maximum distance to an object before marking it']
config['position'].comments['override_on'] = ['Enable manual position override']
config['position'].comments['position_format'] = ['Define the position presentation format in DD, DM or DMS']
config['position'].comments['latitude'] = ['Latitude in decimal degrees (DD)']
config['position'].comments['longitude'] = ['Longitude in decimal degrees (DD)']
config['position'].comments['use_position_from'] = ['Define the source to get GPS position from']
config['network'].comments['server_on'] = ['Enable network server']
config['network'].comments['server_address'] = ['Server hostname or IP (server side)']
config['network'].comments['server_port'] = ['Server port (server side)']
config['network'].comments['clients_on'] = ['List of server:port to enable reading from']
config['network'].comments['client_addresses'] = ['List of server:port to connect and use data from']
config['network'].comments['clients_to_serial'] = ['List of server:port to send data to serial out']
config['network'].comments['clients_to_server'] = ['List of server:port to send data to network server']
config['map'].comments['object_color'] = ['Color of map objects']
config['map'].comments['old_object_color'] = ['Color of old (grey-outed) map objects']
config['map'].comments['selected_object_color'] = ['Color of a selected map object']
config['map'].comments['alerted_object_color'] = ['Color of a alerted map object']
config['map'].comments['background_color'] = ['Color of map background']
config['map'].comments['shoreline_color'] = ['Color of map shorelines']
config['map'].comments['mapfile'] = ['Filename of map in MapGen format']


## Define global variables (somewhat ugly)
# Map three digit MID code to ISO country
mid = {}
# Map three digit MID code to full country name
midfull = {}
# Map two digit type code to human-readable name
typecode = {}

# Set start time to start_time - used for uptime measurement
start_time = datetime.datetime.now()

# Function for loading and merging a given config file
def loadconfig(cfile):
    # Read or create the config file object
    userconfig = ConfigObj(cfile)
    # Merge the settings in the config file with the defaults. Even if
    # there are no config file, all config values have safe defaults.
    config.merge(userconfig)
    config.filename = cfile

# Class for displaying a dialog when several config files are
# available.
class ChooseConfig(wx.App):
    def __init__(self, files):
        # Display choice dialog
        dlg = wx.SingleChoiceDialog(None, message=_("There are multiple configuration files in the AIS Logger directory.\nPlease choose which one to use."), caption=_("Choose configuration file to use"), choices=files)
        # If user presses ok, load config file and return
        if dlg.ShowModal() == wx.ID_OK:
            loadconfig(os.path.join(package_home(globals()), unicode(dlg.GetStringSelection())))
            dlg.Destroy()
            return
        # User pressed cancel, warn them about it
        dlg.Destroy()
        dlg = wx.MessageDialog(None, _("No configuration file was chosen.\nFalling back to defaults."), _("No file was chosen"), wx.OK|wx.ICON_WARNING)
        dlg.ShowModal()
        dlg.Destroy()
 
# If no command line config files, get dir listing
if len(configfiles) == 0:
    # Get config files in directory
    configfiles = glob.glob(os.path.join(package_home(globals()), u'*.ini'))
    # Only use relative file names
    configfiles = map(os.path.basename, configfiles)
# Check for more than one config file -> display dialog
if len(configfiles) > 1:
    test = wx.App()
    testframe = ChooseConfig(configfiles)
    test.MainLoop()
# Only one config file, load it
elif len(configfiles) == 1:
    loadconfig(os.path.join(package_home(globals()), unicode(configfiles[0])))

 
class MainWindow(wx.Frame):
    # Intialize a set, a dict and a list
    # active_set for the MMSI numers who are active,
    # grey_dict for grey-outed MMSI numbers (and distance)
    # last_own_pos for last own position
    active_set = set()
    grey_dict = {}
    last_own_pos = []

    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(800,500))

        # Set icon
        ib=wx.IconBundle()
        try:
            ib.AddIconFromFile(os.path.join(package_home(globals()), u"data/icon.ico"), wx.BITMAP_TYPE_ANY)
            self.SetIcons(ib)
        except: pass
        
        # Create status row
        statusbar = wx.StatusBar(self, -1)
        statusbar.SetFieldsCount(2)
        self.SetStatusBar(statusbar)
        self.SetStatusWidths([-2, -1])
        self.SetStatusText(_("Own position:"),0)
        self.SetStatusText(_("Total nr of objects / old: "),1)

        # Create menu
        menubar = wx.MenuBar()
        file = wx.Menu()

        load_raw = wx.MenuItem(file, 103, _("Load &raw data...\tCtrl+R"), _("Loads a file containing raw (unparsed) messages"))
        file.AppendItem(load_raw)
        file.AppendSeparator()

        quit = wx.MenuItem(file, 104, _("E&xit\tCtrl+X"), _("Exit program"))
        file.AppendItem(quit)

        view = wx.Menu()
        showmap = wx.MenuItem(view, 200, _("Show map window\tF5"), _("Shows or hides the map window"))
        view.AppendItem(showmap)

        showsplit = wx.MenuItem(view, 201, _("Show &alert view\tF8"), _("Shows or hides the alert view"))
        view.AppendItem(showsplit)
        view.AppendSeparator()

        showrawdata = wx.MenuItem(view, 203, _("Show raw &data window..."), _("Shows a window containing the incoming raw (unparsed) data"))
        view.AppendItem(showrawdata)

        calchorizon = wx.MenuItem(view, 204, _("Show s&tatistics..."), _("Shows a window containing various statistics"))
        view.AppendItem(calchorizon)

        tools = wx.Menu()
        setalerts = wx.MenuItem(tools, 301, _("Set &alerts and remarks...\tCtrl+A"), _("Shows a window where one can set alerts and remarks"))
        tools.AppendItem(setalerts)

        settings = wx.MenuItem(tools, 302, _("&Settings...\tCtrl+S"), ("Opens the settings window"))
        tools.AppendItem(settings)

        help = wx.Menu()
        about = wx.MenuItem(help, 401, _("&About...\tF1"), _("About the software"))
        help.AppendItem(about)

        menubar.Append(file, _("&File"))
        menubar.Append(view, _("&View"))
        menubar.Append(tools, _("&Tools"))
        menubar.Append(help, _("&Help"))

        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self.OnLoadRawFile, id=103)
        self.Bind(wx.EVT_MENU, self.Quit, id=104)
        self.Bind(wx.EVT_CLOSE, self.Quit)
        self.Bind(wx.EVT_MENU, self.OnShowMap, id=200)
        self.Bind(wx.EVT_MENU, self.OnShowSplit, id=201)
        self.Bind(wx.EVT_MENU, self.OnShowRawdata, id=203)
        self.Bind(wx.EVT_MENU, self.OnStatistics, id=204)
        self.Bind(wx.EVT_MENU, self.OnSetAlerts, id=301)
        self.Bind(wx.EVT_MENU, self.OnSettings, id=302)
        self.Bind(wx.EVT_MENU, self.OnAbout, id=401)

        # Read type codes and MID codes from file
        self.readmid()
        self.readtype()

        # Create and split two windows, a list window and an alert window
        self.split = wx.SplitterWindow(self, -1, style=wx.SP_3D)
        self.splist = ListWindow(self.split, -1)
        self.spalert = AlertWindow(self.split, -1)
        self.split.SetSashGravity(0.5)
        self.splitwindows()

        # Start a timer to get new messages at a fixed interval
        self.timer = wx.Timer(self, -1)
        self.Bind(wx.EVT_TIMER, self.GetMessages, self.timer)
        if config['common'].as_int('updatetime') >= 1:
            updatetime = config['common'].as_int('updatetime') * 1000
        else:
            updatetime = 1000
        self.timer.Start(updatetime)

        # Set some dlg pointers to None
        self.set_alerts_dlg = None
        self.stats_dlg = None
        self.raw_data_dlg = None

        # Fire off the map
        self.map = MapFrame(self, -1, "AIS Logger - Map", wx.DefaultPosition,(700,500))

        # A dict for keeping track of open Detail Windows
        self.detailwindow_dict = {}

    def GetMessages(self, event):
        # Get messages from main thread
        messages = main_thread.ReturnOutgoing()
        # See what to do with them
        for message in messages:
            if 'update' in message:
                # "Move" from grey_dict to active_set
                if message['update']['mmsi'] in self.grey_dict:
                    del self.grey_dict[message['update']['mmsi']]
                self.active_set.add(message['update']['mmsi'])
                # Update lists
                self.splist.Update(message)
                self.spalert.Update(message)
                # Update map
                if self.map:
                    self.map.UpdateMap(message)
                # See if we should send to a detail window
                if message['update']['mmsi'] in self.detailwindow_dict:
                    self.detailwindow_dict[message['update']['mmsi']].DoUpdate(message['update'])
            elif 'insert' in message:
                # Insert to active_set
                self.active_set.add(message['insert']['mmsi'])
                # Refresh status row
                self.OnRefreshStatus()
                # Update lists
                self.splist.Update(message)
                self.spalert.Update(message)
                # Update map
                if self.map:
                    self.map.UpdateMap(message)
            elif 'old' in message:
                # "Move" from active_set to grey_dict
                distance = message['old'].get('distance', None)
                if message['old']['mmsi'] in self.active_set:
                    self.active_set.discard(message['old']['mmsi'])
                    self.grey_dict[message['old']['mmsi']] = distance
                # Refresh status row
                self.OnRefreshStatus()
                # Update lists
                self.splist.Update(message)
                self.spalert.Update(message)
                # Update map
                if self.map:
                    self.map.UpdateMap(message)
            elif 'remove' in message:
                # Remove from grey_dict (and active_set to be sure)
                self.active_set.discard(message['remove'])
                if message['remove'] in self.grey_dict:
                    del self.grey_dict[message['remove']]
                # Refresh status row
                self.OnRefreshStatus()
                # Update lists
                self.splist.Update(message)
                self.spalert.Update(message)
                # Update map
                if self.map:
                    self.map.UpdateMap(message)
            elif 'own_position' in message:
                # Refresh status row with own_position
                self.OnRefreshStatus(message['own_position'])
                # Update map
                if self.map:
                    self.map.UpdateMap(message)
            elif 'query' in message:
                # See if we should send to a detail window
                if message['query']['mmsi'] in self.detailwindow_dict:
                    self.detailwindow_dict[message['query']['mmsi']].DoUpdate(message['query'])
            elif 'remarkdict' in message:
                # See if we should send to set alert window
                if self.set_alerts_dlg:
                    self.set_alerts_dlg.GetData(message)
            elif 'iddb' in message:
                # See if we should send to set alert window
                if self.set_alerts_dlg:
                    self.set_alerts_dlg.GetData(message)
            elif 'error' in message:
                # Create a dialog and display error
                self.ShowErrorMsg(message['error'])
        # Refresh the listctrls (by sorting)
        self.splist.Refresh()
        self.spalert.Refresh()
        # Update the map if shown
        if self.map.IsShown():
            self.map.Canvas.Draw()
        # See if we should fetch statistics data from CommHubThread
        # Also add data in grey_dict and nbr of items
        if self.stats_dlg:
            self.stats_dlg.SetData([comm_hub_thread.ReturnStats(), self.grey_dict, len(self.active_set)])
        # See if we should fetch raw data from CommHubThread
        if self.raw_data_dlg:
            self.raw_data_dlg.SetData(comm_hub_thread.ReturnRaw())

    def splitwindows(self, window=None):
        if self.split.IsSplit(): self.split.Unsplit(window)
        else: self.split.SplitHorizontally(self.splist, self.spalert, 0)

    def ShowErrorMsg(self, messagestring):
        # Format and show a message dialog displaying the error and
        # the last line from the traceback (internal exception message)
        messagelist = messagestring.splitlines(True)
        message = messagelist[0]
        if len(messagelist) > 1:
            traceback = messagelist[-1]
        else:
            traceback = ''
        dlg = wx.MessageDialog(self, "\n" +message+ "\n" +traceback, caption="Error", style=wx.OK|wx.ICON_ERROR)
        dlg.ShowModal()

    def AddDetailWindow(self, window, mmsi):
        # If there already is a window open with the same MMSI number,
        # destroy the new window. Else add window dict
        if mmsi in self.detailwindow_dict:
            window.Destroy()
        else:
            self.detailwindow_dict[mmsi] = window

    def RemoveDetailWindow(self, mmsi):
        # Remove window from the dict
        del self.detailwindow_dict[mmsi]

    def readmid(self):
        # Read a list from MID to nation from file mid.lst
        try:
            f = open(os.path.join(package_home(globals()), u'data/mid.lst'), 'r')
        except:
                logging.error("Could not read data from MID file", exc_info=True)
                return
        for line in f:
            # For each line, strip any whitespace and then split the data using ','
            row = line.strip().split(',')
            # Try to map MID to 2-character ISO
            try: mid[row[0]] = row[1]
            except: continue
            # Try to map MID to full country name
            try: midfull[row[0]] = row[2]
            except: continue
        f.close()

    def readtype(self):
        # Read a list with ship type codes from typecode.lst
        try:
            f = open(os.path.join(package_home(globals()), u'data/typecode.lst'), 'r')
        except:
                logging.error("Could not read data from type code file", exc_info=True)
                return
        for line in f:
            # For each line, strip any whitespace and then split the data using ','
            row = line.strip().split(',')
            # Try to read line as ASCII/UTF-8, if error, try cp1252
            try:
                typecode[row[0]] = unicode(row[1], 'utf-8')
            except:
                typecode[row[0]] = unicode(row[1], 'cp1252')
        f.close()

    def OnRefreshStatus(self, own_pos=False):
        # Update the status row
        # Get total number of items by taking the length of the union
        # between active_set and grey_dict
        nbrgreyitems = len(self.grey_dict)
        nbritems = len(self.active_set) + nbrgreyitems
        # See if we should update the position row
        if own_pos:
            # Get human-readable position and save to variable
            self.last_own_pos = [PositionConversion(own_pos['ownlatitude'],own_pos['ownlongitude']).default, own_pos['owngeoref']]
        if self.last_own_pos:
            # Set text with own position
            self.SetStatusText(_("Own position: ") + self.last_own_pos[0][0] + '  ' + self.last_own_pos[0][1] + '  (' + self.last_own_pos[1] + ')', 0)
        # Set number of objects and old objects
        self.SetStatusText(_("Total nbr of objects / old: ") + str(nbritems) + ' / ' + str(nbrgreyitems), 1)

    def OnShowRawdata(self, event):
        self.raw_data_dlg = RawDataWindow(None, -1)
        self.raw_data_dlg.Show()

    def OnStatistics(self, event):
        self.stats_dlg = StatsWindow(None, -1)
        self.stats_dlg.Show()

    def OnLoadRawFile(self, event):
        path = ''
        wcd = _('All files (*)|*|Text files (*.txt)|*.txt')
        dir = os.getcwd()
        open_dlg = wx.FileDialog(self, message=_("Choose a raw data file"), defaultDir=dir, defaultFile='', wildcard=wcd, style=wx.OPEN)
        if open_dlg.ShowModal() == wx.ID_OK:
            path = open_dlg.GetPath()
        open_dlg.Destroy()
        if len(path) > 0:
            try:
                self.rawfileloader(path)
            except IOError, error:
                dlg = wx.MessageDialog(self, _("Could not open file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
                dlg.Destroy()
            except UnicodeDecodeError, error:
                dlg = wx.MessageDialog(self, _("Could not open file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
                dlg.Destroy()

    def rawfileloader(self, filename):
        # Load raw data from file and queue it to the CommHubThread

        # Open file
        f=open(filename, 'r')

        # Get total number of lines in file
        num_lines = 0
        for line in f:
            num_lines += 1
        f.seek(0)

        # Create a progress dialog
        progress = wx.ProgressDialog(_("Loading file..."), _("Loading file..."), num_lines)

        # Step through each row in the file
        name = 'File'
        lastupdate_line = 0
        for linenumber, line in enumerate(f):

            # If indata contains raw data, pass it along
            if line[0] == '!' or line[0] == '$':
                # Put it in CommHubThread's queue
                comm_hub_thread.put([name,line])

            # Update the progress dialog for each 100 rows
            if lastupdate_line + 100 < linenumber:
                progress.Update(linenumber)
                lastupdate_line = linenumber

        # Close file
        f.close()
        progress.Destroy()

    def Quit(self, event):
        for window in self.detailwindow_dict.itervalues():
            window.Destroy()
        try:
            self.set_alerts_dlg.Destroy()
            self.stats_dlg.Destroy()
            self.raw_data_dlg.Destroy()
        except: pass
        self.map.Destroy()
        self.Destroy()

    def OnShowSplit(self, event):
        self.splitwindows(self.spalert)

    def OnShowMap(self, event, zoomtobb=True):
        # Toggle showing map
        if self.map.IsShown():
            self.map.Hide()
        else:
            self.map.DrawMap(zoomtobb)
            self.map.Show()
            self.map.Canvas.SetFocus()
            # Workaround: for ZoomToBB() to work after loading the
            # map, we need to do it after doing Show()
            if not self.map.mapIsLoaded:
                self.map.ZoomToBB()

    def OnAbout(self, event):
        aboutstring = 'AIS Logger ('+version+')\n(C) Erik I.J. Olsson 2006-2009\n\naislog.py\ndecode.py\nutil.py'
        dlg = wx.MessageDialog(self, aboutstring, _("About"), wx.OK|wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def OnSetAlerts(self, event):
        self.set_alerts_dlg = SetAlertsWindow(None, -1)
        self.set_alerts_dlg.Show()

    def OnSettings(self, event):
        dlg = SettingsWindow(None, -1)
        dlg.Show()


class MapFrame(wx.Frame):
    def __init__(self,parent, id, title, position, size):
        wx.Frame.__init__(self,parent, id, title, position, size)

        self.CreateStatusBar()

        # Add the Canvas
        NC = NavCanvas.NavCanvas(self,
                                 Debug = False,
                                 BackgroundColor = config['map']['background_color'])

        # Reference the contained FloatCanvas
        self.Canvas = NC.Canvas

        self.ObjectWindow = wx.Panel(self)

        # Reference the parent control
        self.parent = parent

        # Create a sizer to manage the Canvas and object window
        MainSizer = wx.BoxSizer(wx.VERTICAL)
        MainSizer.Add(NC, 4, wx.EXPAND)
        MainSizer.Add(self.ObjectWindow, 0, wx.EXPAND)

        self.SetSizer(MainSizer)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)

        self.Canvas.Bind(FloatCanvas.EVT_MOTION, self.OnMove) 
        self.Canvas.Bind(FloatCanvas.EVT_MOUSEWHEEL, self.OnWheel)
        self.Canvas.Bind(FloatCanvas.EVT_LEFT_DOWN, self.OnCanvasClick)
        self.Canvas.Bind(wx.EVT_KEY_UP, self.OnKey)

        # Set up selected object box
        box = wx.StaticBox(self.ObjectWindow,-1,_(" Selected object information "))
        self.objectbox_panel = wx.Panel(self.ObjectWindow, -1)
        self.objectbox_panel.SetMinSize((500,45))
        self.objectbox_sizer = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        self.objectbox_sizer.Add(self.objectbox_panel, wx.EXPAND)
        self.ObjectWindow.SetSizer(self.objectbox_sizer)
        # Create text objects
        self.box_mmsi = wx.StaticText(self.objectbox_panel, -1, _("MMSI:"), pos=(10,5))
        self.box_name = wx.StaticText(self.objectbox_panel, -1, _("Name:"), pos=(150,5))
        self.box_georef = wx.StaticText(self.objectbox_panel, -1, _("GEOREF:"), pos=(400,5))
        self.box_bearing = wx.StaticText(self.objectbox_panel, -1, _("Bearing:"), pos=(540,5))
        self.box_lat = wx.StaticText(self.objectbox_panel, -1, _("Lat:"), pos=(10,25))
        self.box_long = wx.StaticText(self.objectbox_panel, -1, _("Long:"), pos=(150,25))
        self.box_course = wx.StaticText(self.objectbox_panel, -1, _("Course:"), pos=(310,25))
        self.box_sog = wx.StaticText(self.objectbox_panel, -1, _("Speed:"), pos=(400,25))
        self.box_distance = wx.StaticText(self.objectbox_panel, -1, _("Distance:"), pos=(540,25))
        # Make window disabled
        self.ObjectWindow.Enable(False)

        # Add button to toolbar
        toolbar = NC.ToolBar
        toolbar.AddSeparator()
        self.detail_button = wx.Button(toolbar, label=_("Open selected in &Detail Window") + ' (F2)')
        self.detail_button.Bind(wx.EVT_BUTTON, self.OpenDetailWindow)
        self.detail_button.Enable(False)
        toolbar.AddControl(self.detail_button)
        toolbar.Realize()

        # Set empty object holder
        self.itemMap = {}
        # Map MainWindow's grey_dict
        self.grey_dict = parent.grey_dict
        # Set no selected object
        self.selected = None
        # Set "own" object
        self.own_object = None
        # Set variable to see if the map is loaded
        self.mapIsLoaded = False
        # Set 'workaround' variable to zoom to BB in next update
        self.zoomNext = False

        # Initialize
        self.Canvas.InitAll()
        self.Canvas.SetProjectionFun("FlatEarth")

    def OnWheel(self, event):
        Rot = event.GetWheelRotation()
        Rot = Rot / abs(Rot) * 0.1
        if event.ControlDown(): # move left-right
            self.Canvas.MoveImage( (Rot, 0), "Panel" )
        else: # move up-down
            self.Canvas.MoveImage( (0, Rot), "Panel" )

    def OnMove(self, event):
        # Get mouse coordinates
        try:
            long = event.Coords[0]
            lat = event.Coords[1]
            human_pos = PositionConversion(lat,long).default
            # Try to get own position
            if self.own_object:
                ownpos = self.own_object.XY
                dist = VincentyDistance((ownpos[1], ownpos[0]), (lat, long)).all
            else:
                dist['bearing'] = 0
                dist['km'] = 0
            # Set data tuple
            pos = (human_pos[0], human_pos[1], georef(lat, long), dist['bearing'], dist['km'])
            # Print status text
            self.SetStatusText(_("Mouse position:") + u" Lat: %s   Long: %s   GEOREF: %s   Bearing: %.1f°   Distance %.1f km" %(pos))
        except:
            self.SetStatusText(_("Mouse position:") +u" %.4f, %.4f" %(tuple(event.Coords)))
        event.Skip()

    def OnKey(self, event):
        # Deselect object if escape is pressed
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.DeselectObject()
        # Open selected in Detail window if F2 is pressed
        elif event.GetKeyCode() == wx.WXK_F2:
            self.OpenDetailWindow()

    def OnCanvasClick(self, event):
        self.DeselectObject()

    def OnObjectClick(self, event):
        self.SelectObject(event)

    def ZoomToFit(self,event):
        self.Canvas.ZoomToBB()

    def OnCloseWindow(self, event):
        self.Hide()

    def ZoomToObject(self, mmsi):
        # Zooms to an object
        if mmsi in self.itemMap:
            # Get object position
            pos = getattr(self.itemMap[mmsi][0], 'XY', None)
            if not pos == None:
                # Get x and y
                x = pos[0]
                y = pos[1]
                # Create a bounding box that has it's corners 0.5
                # degrees around the position
                bbox = Utilities.BBox.asBBox([[x-0.5,y-0.5],[x+0.5,y+0.5]])
                # Zoom to the bounding box
                try:
                    self.Canvas.ZoomToBB(bbox)
                except:
                    pass

    def SelectObject(self, map_object, fromlist=False):
        # See if we have a previous selected object
        if self.selected:
            self.DeselectObject(fromlist)
        # Set selected to object
        self.selected = getattr(map_object, 'mmsi')
        # Mark object as selected with a different color
        # (don't update the color attribute - we want to retain
        # the original color)
        self.itemMap[self.selected][0].SetColor(config['map']['selected_object_color'])
        self.itemMap[self.selected][1].SetLineColor(config['map']['selected_object_color'])
        # Make window enabled
        self.ObjectWindow.Enable(True)
        # Enable detail window button
        self.detail_button.Enable(True)
        # Update window
        self.UpdateObjectWindow(map_object)
        # If the selection doesn't come from the list views
        if not fromlist:
            # Try to select object in list views
            self.parent.splist.list.SetSelected(self.selected, True)
            self.parent.spalert.list.SetSelected(self.selected, True)

    def DeselectObject(self, fromlist=False):
        # Deselect if we have a selected object
        if self.selected:
            # Clear window
            self.ClearObjectWindow()
            # Mark object as deselected with the old object color
            obj_color = getattr(self.itemMap[self.selected][1], 'color')
            # See if object is greyed-out
            if self.selected in self.grey_dict:
                obj_color = config['map']['old_object_color']
            self.itemMap[self.selected][0].SetColor(obj_color)
            self.itemMap[self.selected][1].SetLineColor(obj_color)
            # Disable detail window button
            self.detail_button.Enable(False)
            # Set selected to None
            self.selected = None
            # If the selection doesn't come from the list views
            if not fromlist:
                # Deselect all objects in list views
                self.parent.splist.list.DeselectAll()
                self.parent.spalert.list.DeselectAll()

    def SetSelected(self, mmsi, fromlist=False):
        # Select MMSI on map
        if mmsi in self.itemMap:
            self.SelectObject(self.itemMap[mmsi][1], fromlist)

    def OpenDetailWindow(self, map_object=None):
        # Try to get mmsi if a map object
        mmsi = getattr(map_object, 'mmsi', None)
        # If not, see if we have a selected object to use
        if not mmsi and self.selected:
            mmsi = self.selected
        if mmsi:
            # Open the detail window
            frame = DetailWindow(self, -1, mmsi)
            frame.Show()

    def DrawMap(self, zoomtobb=True):
        # Only load data if we haven't done it before
        if not self.mapIsLoaded:
            # Tell the user we're busy
            wx.BusyCursor()
            # Load shorelines from file
            try:
                Shorelines = self.Read_MapGen(unicode(config['map']['mapfile'], 'utf-8'))
                for segment in Shorelines:
                    i = self.Canvas.AddLine(segment, LineColor=config['map']['shoreline_color'])
            except:
                logging.error("Failed reading map data from file", exc_info=True)
            # Set variable to map is loaded
            self.mapIsLoaded = True
            # Not busy any more
            wx.BusyCursor()
            # Set variable to zoom to bounding box in next update
            # (workaround: ZoomToBB() wouldn't work directly)
            if zoomtobb:
                self.zoomNext = True

    def UpdateMap(self, message):
        # Update map with new data
        if 'update' in message:
            data = message['update']
            mmsi = data['mmsi']
            alert = message.get('alert', False)
            mapdata = self.GetMessageData(mmsi, data, alert)
            if mapdata and mmsi in self.itemMap:
                self.UpdateObject(self.itemMap[mmsi], *mapdata)
            # See if object is selected and if so send arrow data
            # (contains heading, speed, position)
            if self.selected and self.selected == mmsi:
                self.UpdateObjectWindow(self.itemMap[mmsi][1])
        elif 'insert' in message:
            data = message['insert']
            mmsi = data['mmsi']
            alert = message.get('alert', False)
            mapdata = self.GetMessageData(mmsi, data, alert)
            if mapdata:
                self.itemMap[mmsi] = self.CreateObject(*mapdata)
        elif 'remove' in message:
            # Get the MMSI number
            mmsi = message['remove']
            # If the object we want to remove is selected,
            # deselect it
            if self.selected == mmsi:
                self.DeselectObject()
            # Remove object
            if mmsi in self.itemMap:
                self.RemoveObject(self.itemMap[mmsi])
                del self.itemMap[mmsi]
        elif 'old' in message:
            # Get the MMSI number
            mmsi = message['old']['mmsi']
            # Don't update color now if selected or doesn't exist
            if not self.selected == mmsi and mmsi in self.itemMap:
                self.itemMap[mmsi][0].SetColor(config['map']['old_object_color'])
                self.itemMap[mmsi][1].SetLineColor(config['map']['old_object_color'])
        elif 'own_position' in message:
            self.SetOwnObject(message['own_position'])
        # See if we need to zoom to bounding box
        # (workaround after drawing map)
        if self.zoomNext:
            self.Canvas.ZoomToBB()
            self.zoomNext = False

    def GetMessageData(self, mmsi, data, alert):
        # Extract info from data and format it to be used
        # on the map.

        # Get name
        name = data.get('name', None)
        # Extract position
        lat = data['latitude']
        long = data['longitude']
        if long is None or long == 'N/A' or lat is None or lat == 'N/A':
            return False
        # Extract distance and bearing
        bearing = data['bearing']
        distance = data['distance']
        # Extract cog, speed
        cog = data['cog']
        if cog is None or cog == 'N/A':
            cog = 0
        sog = data['sog']
        if sog is None or sog == 'N/A':
            sog = 0
        else:
            sog = int(sog * decimal.Decimal('1.5'))
        # See what type of transponder we have
        transponder_type = data['transponder_type']
        if transponder_type and transponder_type == 'base':
            basestation = True
        else:
            basestation = False
        # Return values
        return mmsi, name, lat, long, bearing, distance, cog, sog, basestation, alert

    def UpdateObjectWindow(self, map_object):
        # Set data in Object Window
        # Get data from map_object
        mmsi = getattr(map_object, 'mmsi', None)
        name = getattr(map_object, 'name', None)
        course = getattr(map_object, 'Direction', None)
        sog = getattr(map_object, 'Length', None)
        pos = getattr(map_object, 'XY', None)
        bearing = getattr(map_object, 'bearing', None)
        distance = getattr(map_object, 'distance', None)
        # See if None, if so set strings to '-'
        if not name: name = '-'
        if not course or course == '0.0': course = '-'
        else: course = str(int(course)) + u'°'
        if not sog or sog == '0.0': sog = '-'
        else: sog = str(int(float(sog) / 1.5)) + ' kn'
        if not bearing: bearing = '-'
        else: bearing = str(bearing) + u'°'
        if not distance: distance = '-'
        else: distance = str(distance) + u' km'
        # See if we can get position data
        try:
            human_pos = PositionConversion(pos[1],pos[0]).default
            lat = human_pos[0]
            long = human_pos[1]
            georef_v = georef(pos[1], pos[0])
        except:
            lat = '-'; long = '-'; georef_v = '-'
        # Set labels
        self.box_mmsi.SetLabel(_("MMSI: ") + str(mmsi))
        self.box_name.SetLabel(_("Name: ") + name)
        self.box_georef.SetLabel(_("GEOREF: ") + georef_v)
        self.box_bearing.SetLabel(_("Bearing: ") + bearing)
        self.box_lat.SetLabel(_("Lat: ") + lat)
        self.box_long.SetLabel(_("Long: ") + long)
        self.box_course.SetLabel(_("Course: ") + course)
        self.box_sog.SetLabel(_("Speed: ") + sog)
        self.box_distance.SetLabel(_("Distance: ") + distance)

    def ClearObjectWindow(self):
        # Set empty labels
        self.box_mmsi.SetLabel(_("MMSI: "))
        self.box_name.SetLabel(_("Name: "))
        self.box_georef.SetLabel(_("GEOREF: "))
        self.box_bearing.SetLabel(_("Bearing: "))
        self.box_lat.SetLabel(_("Lat: "))
        self.box_long.SetLabel(_("Long: "))
        self.box_course.SetLabel(_("Course: "))
        self.box_sog.SetLabel(_("Speed: "))
        self.box_distance.SetLabel(_("Distance:"))
        # Make window disabled
        self.ObjectWindow.Enable(False)

    def CreateObject(self, mmsi, name, y, x, bearing, distance, heading, speed, basestation, alert):
        # Create a ship using data, return the objects

        Canvas = self.Canvas
        # Set color based on alerted or not
        if alert:
            obj_color = config['map']['alerted_object_color']
        else:
            obj_color = config['map']['object_color']
        # Create a round point for non-base station transponders
        # or a squared point for base stations
        if basestation:
            Point = Canvas.AddSquarePoint((x, y), Size=5, Color=obj_color, InForeground=True)
        else:
            Point = Canvas.AddPoint((x, y), Diameter=4, Color=obj_color, InForeground=True)
        # Create an arrow based on objects speed and heading
        Arrow = Canvas.AddArrow((x, y), Length=speed, Direction=heading, LineColor=obj_color, LineWidth=1, ArrowHeadSize=0, InForeground = True)
        # Make it possible to actually hit the object :-)
        Arrow.HitLineWidth = 15
        # Set events for clicking on object
        Arrow.Bind(FloatCanvas.EVT_FC_LEFT_DOWN, self.OnObjectClick)
        Arrow.Bind(FloatCanvas.EVT_FC_LEFT_DCLICK, self.OpenDetailWindow)
        # Set extended attributes
        setattr(Arrow, 'mmsi', mmsi)
        setattr(Arrow, 'name', name)
        setattr(Arrow, 'bearing', bearing)
        setattr(Arrow, 'distance', distance)
        setattr(Arrow, 'color', obj_color)
        return (Point,Arrow)

    def UpdateObject(self, Object, mmsi, name, y, x, bearing, distance, heading, speed, basestation, alert):
        # Update the Object with fresh data

        # Map objects
        Point = Object[0]
        Arrow = Object[1]

        # Update the data
        Point.SetPoint((x,y))
        Arrow.SetPoint((x,y))
        Arrow.SetLengthDirection(speed,heading)
        # Update color
        if not self.selected == mmsi:
            obj_color = getattr(Arrow, 'color')
            Point.SetColor(obj_color)
            Arrow.SetLineColor(obj_color)
        # Set new data
        setattr(Arrow, 'name', name)
        setattr(Arrow, 'bearing', bearing)
        setattr(Arrow, 'distance', distance)

    def RemoveObject(self, Object):
        # Remove the Object

        # Map objects
        Point = Object[0]
        Arrow = Object[1]

        # Remove
        self.Canvas.RemoveObject(Point)
        self.Canvas.RemoveObject(Arrow)

    def SetOwnObject(self, owndata):
        # Sets a square point at the own position
        try:
            y = owndata['ownlatitude']
            x = owndata['ownlongitude']
        except TypeError:
            return None
        # See if we have an old object
        if self.own_object:
            self.own_object.SetPoint((x,y))
        else:
            # Create object
            self.own_object = self.Canvas.AddSquarePoint((x, y), Size=7, Color=config['map']['object_color'], InForeground=True)

    def Read_MapGen(self, filename):
        # Function for reading a MapGen Format file.
        # It returns a list of NumPy arrays with the line segments
        # in them.
        # Shamelessly stolen from the FloatCanvas demo...

        import string
        file = open(filename,'rt')
        data = file.readlines()
        data = map(string.strip,data)

        Shorelines = []
        segment = []
        for line in data:
            if line:
                if line == "# -b": #New segment beginning
                    if segment: Shorelines.append(numpy.array(segment))
                    segment = []
                else:
                    segment.append(map(float,string.split(line)))
        if segment: Shorelines.append(numpy.array(segment))

        return Shorelines


class ListWindow(wx.Panel):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id, style=wx.CLIP_CHILDREN)

        # Read config and extract columns
        # Create a list from the comma-separated string in config (removing all whitespace)
        alertlistcolumns_as_list = config['common']['listcolumns'].replace(' ', '').split(',')
        # A really complicated list comprehension... ;-)
        # For each item in the alertlistcolumns_as_list, extract the corresponding items from columnsetup and create a list
        used_columns = [ [x, columnsetup[x][0], columnsetup[x][1]] for x in alertlistcolumns_as_list ]

        # Reference the parent control
        self.parent = parent

        # Create the listctrl
        self.list = VirtualList(self, columns=used_columns)

        # Create a small panel on top
        panel2 = wx.Panel(self, -1, size=(1,1))

        # Set the layout
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(panel2, 0, wx.EXPAND)
        box.Add(self.list, 1, wx.EXPAND)
        box.InsertSpacer(2, (0,5)) # Add some space between the list and the handle
        self.SetSizer(box)
        self.Layout()

    def Update(self, message):
        # Update the underlying listctrl data with message
        self.list.OnUpdate(message)

    def Refresh(self):
        # Refresh the listctrl by sorting
        self.list.SortListItems()


class AlertWindow(wx.Panel):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id, style=wx.CLIP_CHILDREN)

        # Read config and extract columns
        # Create a list from the comma-separated string in config (removing all whitespace)
        alertlistcolumns_as_list = config['common']['alertlistcolumns'].replace(' ', '').split(',')
        # A really complicated list comprehension... ;-)
        # For each item in the alertlistcolumns_as_list, extract the corresponding items from columnsetup and create a list
        used_columns = [ [x, columnsetup[x][0], columnsetup[x][1]] for x in alertlistcolumns_as_list ]

        # Reference the parent control
        self.parent = parent

        # Create the listctrl
        self.list = VirtualList(self, columns=used_columns)

        # Create a small panel on top
        panel2 = wx.Panel(self, -1, size=(4,4))

        # Set the layout
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(panel2, 0, wx.EXPAND)
        box.Add(self.list, 1, wx.EXPAND)
        self.SetSizer(box)
        self.Layout()

        # Create a set to keep track of alerted objects
        self.alertitems = set()

    def Update(self, message):
        # Match on message type and pass on relevant messages
        if 'update' in message:
            mmsi = message['update']['mmsi']
            if message.get('alert', False):
                # The object is alerted
                self.alertitems.add(mmsi)
                self.list.OnUpdate(message)
            elif mmsi in self.alertitems:
                # The object is not alerted but has been
                self.alertitems.discard(mmsi)
                self.list.OnUpdate({'remove': mmsi})
        elif 'insert' in message and message.get('alert', False):
            # The new object is alerted
            self.alertitems.add(message['insert']['mmsi'])
            self.list.OnUpdate(message)
        elif 'old' in message:
            self.list.OnUpdate(message)
        elif 'remove' in message:
            self.alertitems.discard(message['remove'])
            self.list.OnUpdate(message)
        # Sound an alert for selected objects
        if message.get('soundalert', False):
            self.soundalert()

    def Refresh(self):
        # Refresh the listctrl by sorting
        self.list.SortListItems()

    def soundalert(self):
        # Play sound if config is set
        sound = wx.Sound()
        if config['alert'].as_bool('alertsound_on') and len(config['alert']['alertsoundfile']) > 0 and sound.Create(config['alert']['alertsoundfile']):
            sound.Play(wx.SOUND_ASYNC)


class VirtualList(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin, listmix.ColumnSorterMixin):
    def __init__(self, parent, columns):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL)

        # Define and retreive two arrows, one upwards, the other downwards
        self.imagelist = wx.ImageList(16, 16)
        self.sm_up = self.imagelist.Add(getSmallUpArrowBitmap())
        self.sm_dn = self.imagelist.Add(getSmallDnArrowBitmap())
        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

        # Iterate over the given columns and create the specified ones
        self.columnlist = []
        for i, k in enumerate(columns):
            self.InsertColumn(i, k[1]) # Insert the column
            self.SetColumnWidth(i, k[2]) # Set the width
            self.columnlist.append(k[0]) # Append each column name to a list

        # Use the mixins
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        listmix.ColumnSorterMixin.__init__(self, len(self.columnlist))

        # Set object-wide data holders
        self.itemDataMap = {}
        self.itemIndexMap = []
        self.selected = -1
        # A simple semafor to control when updating selection
        # internally
        self.selectedlock = False
        # Do initial sorting on column 0, ascending order (1)
        self.SortListItems(0, 1)
        # Define one set for alert items and one for grey items
        self.alertitems = set()
        self.greyitems = set()

        # Define popup menu
        self.menu = wx.Menu()
        self.menu.Append(1,_("&Show in Detail window")+"\tF2")
        self.menu.Append(2,_("&Zoom to object on map")+"\tF3")
        # Set menu handlers
        wx.EVT_MENU(self.menu, 1, self.OnItemActivated)
        wx.EVT_MENU(self.menu, 2, self.ZoomToObject)

        # Define events
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClick)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected)
        self.Bind(wx.EVT_KEY_UP, self.OnKey)

    def OnItemActivated(self, event):
        # Get the MMSI number associated with the row activated
        if getattr(event, 'm_itemIndex', False):
            itemmmsi = self.itemIndexMap[event.m_itemIndex]
        # If no such attribute, get selected
        elif self.selected != -1:
            itemmmsi = self.selected
        else:
            return
        # Open the detail window
        frame = DetailWindow(self, -1, itemmmsi)
        frame.Show()

    def OnItemSelected(self, event):
        # When an object is selected, extract the MMSI number and
        # put it in self.selected
        self.selected = self.itemIndexMap[event.m_itemIndex]
        # If the user doesn't select a new one, don't send update
        if not self.selectedlock:
            # Set object as selected on map too
            app.frame.map.SetSelected(self.selected, fromlist=True)

    def OnItemDeselected(self, event):
        self.selected = -1
        # If the user doesn't select a new one, don't send update
        if not self.selectedlock:
            # Deselect object on map too
            app.frame.map.DeselectObject(fromlist=True)

    def SetSelected(self, mmsi, ensurevisible=False):
        # If MMSI in list, select it
        if mmsi in self.itemDataMap:
            try:
                # Find position in list
                pos = self.itemIndexMap.index(mmsi)
            except:
                self.DeselectAll()
                return
            # Set selected state
            self.selectedlock = True
            self.SetItemState(pos, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED)
            self.selectedlock = False
            # Make sure object is visible if flag is set
            if ensurevisible:
                self.EnsureVisible(pos)
        # If not, deselect all objects
        else:
            self.DeselectAll()

    def DeselectAll(self):
        # Deselect all objects
        for i in range(self.GetItemCount()):
            self.SetItemState(i, 0, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED)

    def ZoomToObject(self, event):
        if self.selected != -1:
            # Show map if not shown
            if not app.frame.map.IsShown():
                app.frame.OnShowMap(None, zoomtobb=False)
            # Set object as selected
            app.frame.map.SetSelected(self.selected)
            # Zoom to object on map
            app.frame.map.ZoomToObject(self.selected)

    def OnKey(self, event):
        # Deselect all objects if escape is pressed
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            for i in range(self.GetItemCount()):
                self.SetItemState(i, 0, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED)
            self.selected = -1
        # Show Detail window if F2 is pressed
        elif event.GetKeyCode() == wx.WXK_F2:
            self.OnItemActivated(None)
        # Zoom to object on map if F3 is pressed
        elif event.GetKeyCode() == wx.WXK_F3:
            self.ZoomToObject(None)

    def OnRightClick(self, event):
        # Call PopupMenu at the position of mouse
        self.PopupMenu(self.menu, event.GetPoint())

    def OnUpdate(self, message):
        # See what message we should work with
        if 'update' in message:
            data = message['update']
            mmsi = data['mmsi']
            # See if object is not in list
            if not mmsi in self.itemDataMap:
                # Set a new item count in the listctrl
                self.SetItemCount(self.GetItemCount()+1)
            # Remove object from grey item set
            self.greyitems.discard(mmsi)
            # If alert, put it in alert item set
            if message.get('alert', False):
                self.alertitems.add(mmsi)
            else:
                self.alertitems.discard(mmsi)
            # Get the data formatted
            self.itemDataMap[mmsi] = self.FormatData(data)
        elif 'insert' in message:
            # Set a new item count in the listctrl
            self.SetItemCount(self.GetItemCount()+1)
            data = message['insert']
            # If alert, put it in alert item set
            if message.get('alert', False):
                self.alertitems.add(data['mmsi'])
            # Get the data formatted
            self.itemDataMap[data['mmsi']] = self.FormatData(data)
        elif 'remove' in message:
            # Get the MMSI number
            mmsi = message['remove']
            # Remove object from sets
            self.greyitems.discard(mmsi)
            self.alertitems.discard(mmsi)
            # Remove object if possible
            if mmsi in self.itemDataMap:
                # Set a new item count in the listctrl
                self.SetItemCount(self.GetItemCount()-1)
                # Remove object from list dict
                del self.itemDataMap[mmsi]
        elif 'old' in message:
            # Get the MMSI number
            mmsi = message['old']['mmsi']
            # Add object to set if already in lists
            if mmsi in self.itemDataMap:
                self.greyitems.add(message['old']['mmsi'])

        # Extract the MMSI numbers as keys for the data
        self.itemIndexMap = self.itemDataMap.keys()

    def FormatData(self, data):
        # Create a temporary dict to hold data in the order of
        # self.columnlist so that the virtual listctrl can use it
        new = []
        latpos = None
        longpos = None
        # Loop over the columns we will show
        for i, col in enumerate(self.columnlist):
            # Append the list
            new.append(None)
            # If we have the data, fine!
            if col in data:
                # Set new[position] to the info in data
                # If Nonetype, set an empty string (for sorting reasons)
                if not data[col] == None:
                    new[i] = data[col]
                else:
                    new[i] = u''
                # Some special formatting cases
                if col == 'creationtime':
                    try: new[i] = data[col].isoformat()[11:19]
                    except: new[i] = ''
                elif col == 'time':
                    try: new[i] = data[col].isoformat()[11:19]
                    except: new[i] = ''
                elif col == 'latitude':
                    latpos = i
                elif col == 'longitude':
                    longpos = i
                elif col == 'navstatus':
                    navstatus = data[col]
                    if navstatus == None: navstatus = ''
                    elif navstatus == 0: navstatus = _("Under Way")
                    elif navstatus == 1: navstatus = _("At Anchor")
                    elif navstatus == 2: navstatus = _("Not Under Command")
                    elif navstatus == 3: navstatus = _("Restricted Manoeuvrability")
                    elif navstatus == 4: navstatus = _("Constrained by her draught")
                    elif navstatus == 5: navstatus = _("Moored")
                    elif navstatus == 6: navstatus = _("Aground")
                    elif navstatus == 7: navstatus = _("Engaged in Fishing")
                    elif navstatus == 8: navstatus = _("Under way sailing")
                    new[i] = navstatus
                elif col == 'posacc':
                    if data[col] == 0: new[i] = _('GPS')
                    elif data[col] == 1: new[i] = _('DGPS')
                    else: new[i] = ''
                elif col == 'transponder_type':
                    if data[col] == 'A': new[i] = _('Class A')
                    elif data[col] == 'B': new[i] = _('Class B')
                    elif data[col] == 'base': new[i] = _('Base station')
        # Get position in a more human-readable format
        if data.get('latitude',False) and data.get('longitude',False) and data['latitude'] != 'N/A' and data['longitude'] != 'N/A':
            pos = PositionConversion(data['latitude'],data['longitude']).default
            if latpos:
                new[latpos] = pos[0]
            if longpos:
                new[longpos] = pos[1]
        return new

    def OnGetItemText(self, item, col):
        # Return the text in item, col
        try:
            mmsi = self.itemIndexMap[item]
            string = unicode(self.itemDataMap[mmsi][col])
        except IndexError:
            string == None
        # If string is a Nonetype, replace with an empty string
        if string == None:
            string = u''
        return string

    def OnGetItemAttr(self, item):
        # Return an attribute
        # Get the mmsi of the item
        try:
            mmsi = self.itemIndexMap[item]
        except IndexError:
            mmsi = 0
        # Create the attribute
        self.attr = wx.ListItemAttr()
        
        # If item is in alertitems: make background red
        if mmsi in self.alertitems:
            self.attr.SetBackgroundColour("TAN")

        # If item is old enough, make the text grey
        if mmsi in self.greyitems:
            self.attr.SetTextColour("LIGHT GREY")
        return self.attr

    def SortItems(self,sorter=cmp):
        # Sort items
        items = list(self.itemDataMap.keys())
        try:
            items.sort(sorter)
        except UnicodeEncodeError:
            pass
        self.itemIndexMap = items

        # Workaround for updating listctrl on Windows
        if os.name == 'nt':
            self.Refresh(False)

        # Check for a previous selected object and select it again
        if self.selected != -1:
            self.SetSelected(self.selected)

    def OnSortOrderChanged(self):
        # When user has changed sort col, make a selected object
        # visible if there is one
        self.SetSelected(self.selected, True)
                
    # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
    def GetListCtrl(self):
        return self

    # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
    def GetSortImages(self):
        return (self.sm_dn, self.sm_up)


class DetailWindow(wx.Frame):
    def __init__(self, parent, id, itemmmsi):
        # Set self.itemmmsi to itemmmsi
        self.itemmmsi = itemmmsi

        # Define the dialog
        wx.Frame.__init__(self, parent, id, title=str(itemmmsi)+' - '+_("Detail window"))
        # Create panels
        shipdata_panel = wx.Panel(self, -1)
        voyagedata_panel = wx.Panel(self, -1)
        transponderdata_panel = wx.Panel(self, -1)
        objinfo_panel = wx.Panel(self, -1)
        self.remark_panel = wx.Panel(self, -1)
        # Create static boxes
        wx.StaticBox(shipdata_panel,-1,_(" Ship data "),pos=(3,5),size=(380,205))
        wx.StaticBox(voyagedata_panel,-1,_(" Voyage data "),pos=(3,5),size=(320,205))
        wx.StaticBox(transponderdata_panel,-1,_(" Received transponder data "),pos=(3,5),size=(380,85))
        wx.StaticBox(objinfo_panel,-1,_(" Object information "),pos=(3,5),size=(320,155))
        wx.StaticBox(self.remark_panel,-1,_(" Remark "), pos=(3,5),size=(380,65))
        self.remark_panel.Enable(False)
        # Ship data
        wx.StaticText(shipdata_panel,-1,_("MMSI nbr: "),pos=(12,25),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("IMO nbr: "),pos=(12,45),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Nation: "),pos=(12,65),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Name: "),pos=(12,85),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Type: "),pos=(12,105),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Callsign: "),pos=(12,125),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Length: "),pos=(12,145),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Width: "),pos=(12,165),size=(150,16))
        wx.StaticText(shipdata_panel,-1,_("Draught: "),pos=(12,185),size=(150,16))
        # Voyage data
        wx.StaticText(voyagedata_panel,-1,_("Destination: "),pos=(12,25),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("ETA: "),pos=(12,45),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Latitude: "),pos=(12,65),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Longitude: "),pos=(12,85),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("GEOREF: "),pos=(12,105),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Speed: "),pos=(12,125),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Course: "),pos=(12,145),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Heading: "),pos=(12,165),size=(150,16))
        wx.StaticText(voyagedata_panel,-1,_("Rate of turn: "),pos=(12,185),size=(150,16))
        # Transponder data
        wx.StaticText(transponderdata_panel,-1,_("Navigational Status: "),pos=(12,25),size=(150,16))
        wx.StaticText(transponderdata_panel,-1,_("Position Accuracy: "),pos=(12,45),size=(150,16))
        wx.StaticText(transponderdata_panel,-1,_("Transponder Type: "),pos=(12,65),size=(150,16))
        # Object information such as bearing and distance
        wx.StaticText(objinfo_panel,-1,_("Bearing: "),pos=(12,25),size=(150,16))
        wx.StaticText(objinfo_panel,-1,_("Distance: "),pos=(12,45),size=(150,16))
        wx.StaticText(objinfo_panel,-1,_("Updates: "),pos=(12,65),size=(150,16))
        wx.StaticText(objinfo_panel,-1,_("Source: "),pos=(12,85),size=(150,16))
        wx.StaticText(objinfo_panel,-1,_("Created: "),pos=(12,105),size=(150,16))
        wx.StaticText(objinfo_panel,-1,_("Updated: "),pos=(12,125),size=(150,16))

        # Set ship data
        self.text_mmsi = wx.StaticText(shipdata_panel,-1,'',pos=(100,25),size=(280,16))
        self.text_imo = wx.StaticText(shipdata_panel,-1,'',pos=(100,45),size=(280,16))
        self.text_country = wx.StaticText(shipdata_panel,-1,'',size=(280,16),pos=(100,65))
        self.text_name = wx.StaticText(shipdata_panel,-1,'',pos=(100,85),size=(280,16))
        self.text_type = wx.StaticText(shipdata_panel,-1,'',pos=(100,105),size=(280,16))
        self.text_callsign = wx.StaticText(shipdata_panel,-1,'',pos=(100,125),size=(280,16))
        self.text_length = wx.StaticText(shipdata_panel,-1,'',pos=(100,145),size=(280,16))
        self.text_width = wx.StaticText(shipdata_panel,-1,'',pos=(100,165),size=(280,16))
        self.text_draught = wx.StaticText(shipdata_panel,-1,'',pos=(100,185),size=(280,16))
        # Set voyage data
        self.text_destination = wx.StaticText(voyagedata_panel,-1,'',pos=(100,25),size=(215,16))
        self.text_etatime = wx.StaticText(voyagedata_panel,-1,'',pos=(100,45),size=(215,16))
        self.text_latitude = wx.StaticText(voyagedata_panel,-1,'',pos=(100,65),size=(215,16))
        self.text_longitude = wx.StaticText(voyagedata_panel,-1,'',pos=(100,85),size=(215,16))
        self.text_georef = wx.StaticText(voyagedata_panel,-1,'',pos=(100,105),size=(215,16))
        self.text_sog = wx.StaticText(voyagedata_panel,-1,'',pos=(100,125),size=(215,16))
        self.text_cog = wx.StaticText(voyagedata_panel,-1,'',pos=(100,145),size=(215,16))
        self.text_heading = wx.StaticText(voyagedata_panel,-1,'',pos=(100,165),size=(215,16))
        self.text_rateofturn = wx.StaticText(voyagedata_panel,-1,'',pos=(100,185),size=(215,16))
        # Set transponderdata
        self.text_navstatus = wx.StaticText(transponderdata_panel,-1,'',pos=(145,25),size=(125,16))
        self.text_posacc = wx.StaticText(transponderdata_panel,-1,'',pos=(145,45),size=(125,16))
        self.text_transpondertype = wx.StaticText(transponderdata_panel,-1,'',pos=(145,65),size=(125,16))
        # Set object information
        self.text_bearing = wx.StaticText(objinfo_panel,-1,'',pos=(105,25),size=(215,16))
        self.text_distance = wx.StaticText(objinfo_panel,-1,'',pos=(105,45),size=(215,16))
        self.text_updates = wx.StaticText(objinfo_panel,-1,'',pos=(105,65),size=(215,16))
        self.text_source = wx.StaticText(objinfo_panel,-1,'',pos=(105,85),size=(215,16))
        self.text_creationtime = wx.StaticText(objinfo_panel,-1,'',pos=(105,105),size=(215,16))
        self.text_time = wx.StaticText(objinfo_panel,-1,'',pos=(105,125),size=(215,16))
        # Set remark text
        self.text_remark = wx.StaticText(self.remark_panel,-1,'',pos=(12,25),size=(350,40),style=wx.ST_NO_AUTORESIZE)

        # Add window to the message detail window send list
        main_window.AddDetailWindow(self, itemmmsi)

        # Set query in MainThread's queue
        main_thread.put({'query': itemmmsi})

        # Buttons & events
        button_panel = wx.Panel(self, -1)
        zoombutton = wx.Button(button_panel,1,_("&Zoom to object on map (F3)"))
        closebutton = wx.Button(button_panel,10,_("&Close"))
        closebutton.SetFocus()
        self.Bind(wx.EVT_BUTTON, self.OnZoom, id=1)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=10)
        self.Bind(wx.EVT_KEY_UP, self.OnKey)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Sizer setup
        mainsizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.FlexGridSizer(2,2)
        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer_button = wx.BoxSizer(wx.HORIZONTAL)
        # Sizer1 is the sizer positioning the different panels (and static boxes)
        # Sizer2 is an inner sizer for the transponder data panel and remark panel
        # Sizer_button is a sizer for the buttons in the bottom
        sizer1.Add(shipdata_panel, 1, wx.EXPAND)
        sizer1.Add(voyagedata_panel, 0)
        sizer2.Add(transponderdata_panel, 0)
        sizer2.Add(self.remark_panel, 0)
        sizer1.Add(sizer2, 0)
        sizer1.Add(objinfo_panel, 0)
        sizer_button.AddStretchSpacer()
        sizer_button.Add(zoombutton, 0, wx.ALIGN_RIGHT)
        sizer_button.AddSpacer((80,0))
        sizer_button.Add(closebutton, 0)
        button_panel.SetSizer(sizer_button)
        mainsizer.Add(sizer1, 0, wx.EXPAND)
        mainsizer.Add(button_panel, 1, wx.EXPAND)
        self.SetSizerAndFit(mainsizer)

    def OnKey(self, event):
        # Close dialog if escape is pressed
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.OnClose(event)
        # Zoom to object on map if F3 is pressed
        elif event.GetKeyCode() == wx.WXK_F3:
            self.OnZoom(None)

    def OnZoom(self, event):
        # Show map if not shown
        if not app.frame.map.IsShown():
            app.frame.OnShowMap(None, zoomtobb=False)
        # Zoom to object on map
        app.frame.map.ZoomToObject(self.itemmmsi)
        # Set object as selected
        app.frame.map.SetSelected(self.itemmmsi)

    def DoUpdate(self, data):
        # Set ship data
        self.text_mmsi.SetLabel(str(data['mmsi']))
        if data['imo']: self.text_imo.SetLabel(str(data['imo']))
        if data['mid']: country = data['mid']
        else: country = _("[Non ISO]")
        if str(data['mmsi'])[0:3] in midfull: country += ' - ' + midfull[str(data['mmsi'])[0:3]]
        self.text_country.SetLabel(country)
        if data['name']: self.text_name.SetLabel(data['name'])
        if data['type']: type = str(data['type'])
        else: type = ''
        if data['typename']: type += ' - ' + unicode(data['typename'])
        self.text_type.SetLabel(type)
        if data['callsign']: self.text_callsign.SetLabel(data['callsign'])
        if data['length'] == 'N/A': self.text_length.SetLabel('N/A')
        elif not data['length'] is None: self.text_length.SetLabel(str(data['length'])+' m')
        if data['width'] == 'N/A': self.text_width.SetLabel('N/A')
        elif not data['width'] is None: self.text_width.SetLabel(str(data['width'])+' m')
        if data['draught'] == 'N/A': self.text_draught.SetLabel('N/A')
        elif not data['draught'] is None: self.text_draught.SetLabel(str(data['draught'])+' m')
        # Set voyage data
        if data['destination']: self.text_destination.SetLabel(data['destination'])
        if data['eta']:
            try:
                etatime = 0,int(data['eta'][0:2]),int(data['eta'][2:4]),int(data['eta'][4:6]),int(data['eta'][6:8]),1,1,1,1
                fulletatime = time.strftime(_("%d %B at %H:%M"),etatime)
            except: fulletatime = data['eta']
            if fulletatime == '00002460': fulletatime = 'N/A'
            self.text_etatime.SetLabel(fulletatime)
        if data.get('latitude',False) and data.get('longitude',False) and data['latitude'] != 'N/A' and data['longitude'] != 'N/A':
            pos = PositionConversion(data['latitude'],data['longitude']).default
            self.text_latitude.SetLabel(pos[0])
            self.text_longitude.SetLabel(pos[1])
        elif not data['latitude'] is None and not data['longitude'] is None:
            self.text_latitude.SetLabel(data['latitude'])
            self.text_longitude.SetLabel(data['longitude'])
        if data['georef']: self.text_georef.SetLabel(data['georef'])
        if data['sog'] == 'N/A': self.text_sog.SetLabel('N/A')
        elif not data['sog'] is None: self.text_sog.SetLabel(str(data['sog'])+' kn')
        if data['cog'] == 'N/A': self.text_cog.SetLabel('N/A')
        elif not data['cog'] is None: self.text_cog.SetLabel(str(data['cog'])+u'°')
        if data['heading'] == 'N/A':  self.text_heading.SetLabel('N/A')
        elif not data['heading'] is None: self.text_heading.SetLabel(str(data['heading'])+u'°')
        if data['rot'] == 'N/A': self.text_rateofturn.SetLabel('N/A')
        elif not data['rot'] is None: self.text_rateofturn.SetLabel(str(data['rot'])+u'°/m')
        # Set transponder data
        navstatus = data['navstatus']
        if navstatus == None: navstatus = ''
        elif navstatus == 0: navstatus = _("Under Way")
        elif navstatus == 1: navstatus = _("At Anchor")
        elif navstatus == 2: navstatus = _("Not Under Command")
        elif navstatus == 3: navstatus = _("Restricted Manoeuvrability")
        elif navstatus == 4: navstatus = _("Constrained by her draught")
        elif navstatus == 5: navstatus = _("Moored")
        elif navstatus == 6: navstatus = _("Aground")
        elif navstatus == 7: navstatus = _("Engaged in Fishing")
        elif navstatus == 8: navstatus = _("Under way sailing")
        else: navstatus = str(navstatus)
        self.text_navstatus.SetLabel(navstatus)
        if not data['posacc'] is None:
            if data['posacc']: posacc = _("Very good / DGPS")
            else: posacc = _("Good / GPS")
            self.text_posacc.SetLabel(posacc)
        if not data.get('transponder_type', None) is None:
            if data['transponder_type'] == 'A': transponder_type = _("Class A")
            elif data['transponder_type'] == 'B': transponder_type = _("Class B")
            elif data['transponder_type'] == 'base': transponder_type = _("Base station")
            else: transponder_type = data['transponder_type']
            self.text_transpondertype.SetLabel(transponder_type)
        # Set local info
        if data['bearing'] and data['distance']:
            self.text_bearing.SetLabel(str(data['bearing'])+u'°')
            self.text_distance.SetLabel(str(data['distance'])+' km')
        if data['creationtime']:
            self.text_creationtime.SetLabel(data['creationtime'].strftime('%Y-%m-%d %H:%M:%S'))
        if data['time']:
            self.text_time.SetLabel(data['time'].strftime('%Y-%m-%d %H:%M:%S'))
        if not data['__version__'] is None:
            self.text_updates.SetLabel(str(data['__version__']))
        if data['source']:
            self.text_source.SetLabel(str(data['source']))
        # Set remark text
        if data['remark']:
            self.remark_panel.Enable(True)
            self.text_remark.SetLabel(unicode(data['remark']))

    def OnClose(self, event):
        # Remove window to the message detail window send list
        main_window.RemoveDetailWindow(self.itemmmsi)
        # Destory dialog
        self.Destroy()


class StatsWindow(wx.Dialog):
    def __init__(self, parent, id):
        # Define the dialog
        wx.Dialog.__init__(self, parent, id, title=_("Statistics"))
        # Create panels
        objects_panel = wx.Panel(self, -1)
        objects_panel.SetMinSize((280,-1))
        horizon_panel = wx.Panel(self, -1)
        horizon_panel.SetMinSize((210,-1))
        self.input_panel = wx.Panel(self, -1)
        self.input_panel.SetMinSize((450,-1))
        uptime_panel = wx.Panel(self, -1)
        # Create static boxes
        box_objects = wx.StaticBox(objects_panel,-1,_(" Objects "))
        box_horizon = wx.StaticBox(horizon_panel,-1,_(" Radio Horizon (calculated) "))
        box_input = wx.StaticBox(self.input_panel,-1,_(" Inputs "))
        box_uptime = wx.StaticBox(uptime_panel,-1,_(" Uptime "))

        # Object panels, texts and sizers
        obj_panel_left = wx.Panel(objects_panel)
        obj_panel_right = wx.Panel(objects_panel)
        wx.StaticText(obj_panel_left,-1,_("Number of objects:"),pos=(-1,0))
        wx.StaticText(obj_panel_left,-1,_("Number of old objects:"),pos=(-1,20))
        wx.StaticText(obj_panel_left,-1,_("Objects with a calculated distance:"),pos=(-1,40))
        self.text_object_nbr = wx.StaticText(obj_panel_right,-1,'',pos=(-1,0))
        self.text_object_grey_nbr = wx.StaticText(obj_panel_right,-1,'',pos=(-1,20))
        self.text_object_distance_nbr = wx.StaticText(obj_panel_right,-1,'',pos=(-1,40))
        obj_sizer = wx.StaticBoxSizer(box_objects, wx.HORIZONTAL)
        obj_sizer.AddSpacer(5)
        obj_sizer.Add(obj_panel_left)
        obj_sizer.AddSpacer(10)
        obj_sizer.Add(obj_panel_right, wx.EXPAND)
        objects_panel.SetSizer(obj_sizer)

        # Horizon panels, texts and sizers
        hor_panel_left = wx.Panel(horizon_panel)
        hor_panel_right = wx.Panel(horizon_panel)
        wx.StaticText(hor_panel_left,-1,_("Minimum:"),pos=(-1,0))
        wx.StaticText(hor_panel_left,-1,_("Maximum:"),pos=(-1,20))
        wx.StaticText(hor_panel_left,-1,_("Mean value:"),pos=(-1,40))
        wx.StaticText(hor_panel_left,-1,_("Median value:"),pos=(-1,60))
        self.text_horizon_min = wx.StaticText(hor_panel_right,-1,'',pos=(-1,0))
        self.text_horizon_max = wx.StaticText(hor_panel_right,-1,'',pos=(-1,20))
        self.text_horizon_mean = wx.StaticText(hor_panel_right,-1,'',pos=(-1,40))
        self.text_horizon_median = wx.StaticText(hor_panel_right,-1,'',pos=(-1,60))
        hor_sizer = wx.StaticBoxSizer(box_horizon, wx.HORIZONTAL)
        hor_sizer.AddSpacer(5)
        hor_sizer.Add(hor_panel_left)
        hor_sizer.AddSpacer(10)
        hor_sizer.Add(hor_panel_right, wx.EXPAND)
        horizon_panel.SetSizer(hor_sizer)

        # Initial input panel and sizer
        # The sub-boxes are created on request in Update
        self.maininput_sizer = wx.StaticBoxSizer(box_input, wx.VERTICAL)
        self.input_sizer = wx.GridSizer(0, 2, 10, 10)
        self.maininput_sizer.Add(self.input_sizer, 0, wx.EXPAND)
        self.input_panel.SetSizer(self.maininput_sizer)

        # Uptime panels, texts and sizers
        up_panel_left = wx.Panel(uptime_panel)
        up_panel_right = wx.Panel(uptime_panel)
        wx.StaticText(up_panel_left,-1,_("Uptime:"),pos=(-1,0))
        wx.StaticText(up_panel_left,-1,_("Up since:"),pos=(-1,20))
        self.text_uptime_delta = wx.StaticText(up_panel_right,-1,'',pos=(-1,0))
        self.text_uptime_since = wx.StaticText(up_panel_right,-1,'',pos=(-1,20))
        up_sizer = wx.StaticBoxSizer(box_uptime, wx.HORIZONTAL)
        up_sizer.AddSpacer(5)
        up_sizer.Add(up_panel_left)
        up_sizer.AddSpacer(10)
        up_sizer.Add(up_panel_right, wx.EXPAND)
        uptime_panel.SetSizer(up_sizer)

        # Buttons & events
        closebutton = wx.Button(self,1,_("&Close"),pos=(490,438))
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=1)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Sizer setup
        self.mainsizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer_button = wx.BoxSizer(wx.HORIZONTAL)
        # Sizer1 is the sizer positioning the different panels and boxes
        # Sizer2 is an inner sizer for the objects data and update panels
        sizer2.Add(objects_panel, 0)
        sizer2.AddSpacer(5)
        sizer2.Add(uptime_panel, 0, wx.EXPAND)
        sizer1.Add(sizer2)
        sizer1.AddSpacer(5)
        sizer1.Add(horizon_panel, 0, wx.EXPAND)
        self.mainsizer.Add(sizer1)
        self.mainsizer.AddSpacer(5)
        self.mainsizer.Add(self.input_panel, 0, wx.EXPAND)
        self.mainsizer.AddSpacer((0,10))
        sizer_button.Add(closebutton, 0)
        self.mainsizer.Add(sizer_button, flag=wx.ALIGN_RIGHT)
        self.SetSizerAndFit(self.mainsizer)

        # Define dict for storing input boxes
        self.input_boxes = {}

        # Set variables to hold data for calculating parse rate
        self.LastUpdateTime = 0
        self.OldParseStats = {}

    def MakeInputStatBox(self, panel, boxlabel):
        # Creates a StaticBoxSizer and the StaticText in it
        box = wx.StaticBox(panel, -1, boxlabel)
        sizer = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        panel_left = wx.Panel(panel)
        panel_right = wx.Panel(panel)
        wx.StaticText(panel_left,-1,_("Received:"),pos=(-1,0))
        wx.StaticText(panel_left,-1,_("Parsed:"),pos=(-1,20))
        wx.StaticText(panel_left,-1,_("Parsed rate:"),pos=(-1,40))
        received = wx.StaticText(panel_right,-1,'',pos=(-1,0))
        parsed = wx.StaticText(panel_right,-1,'',pos=(-1,20))
        rate = wx.StaticText(panel_right,-1,'',pos=(-1,40))
        sizer.AddSpacer(5)
        sizer.Add(panel_left, 0)
        sizer.AddSpacer(10)
        sizer.Add(panel_right, 1, wx.EXPAND)
        return {'sizer': sizer, 'received': received, 'parsed': parsed, 'rate': rate}

    def Update(self, input_stats, grey_dict, nbr_tot_items):
        # Update data in the window
        horizon = self.CalcHorizon(grey_dict)
        # Objects text
        self.text_object_nbr.SetLabel(str(nbr_tot_items))
        self.text_object_grey_nbr.SetLabel(str(horizon[0]))
        self.text_object_distance_nbr.SetLabel(str(horizon[1]))
        # Horizon text
        self.text_horizon_min.SetLabel(str(round(horizon[2],1)) + " km")
        self.text_horizon_max.SetLabel(str(round(horizon[3],1)) + " km")
        self.text_horizon_mean.SetLabel(str(round(horizon[4],1)) + " km")
        self.text_horizon_median.SetLabel(str(round(horizon[5],1)) + " km")
        # Uptime text
        uptime = datetime.datetime.now() - start_time
        up_since = start_time.isoformat()[:19]
        self.text_uptime_delta.SetLabel(str(uptime).split('.')[0])
        self.text_uptime_since.SetLabel(str(up_since.replace('T', " "+_("at")+" ")))
        # Iterate over items in the statistics dict
        for (name, data) in input_stats.iteritems():
            if name in self.input_boxes:
                # Just update the box
                box = self.input_boxes[name]
                if 'received' in data:
                    box['received'].SetLabel(str(data['received'])+_(" msgs"))
                if 'parsed' in data:
                    box['parsed'].SetLabel(str(data['parsed'])+_(" msgs"))
                    rate = self.CalcParseRate(name, data['parsed'])
                    box['rate'].SetLabel(str(rate)+_(" msgs/sec"))
            else:
                # New input name, redraw input panel
                self.input_boxes[name] = self.MakeInputStatBox(self.input_panel, " " + name + " ")
                self.input_sizer.Add(self.input_boxes[name]['sizer'], 1, wx.EXPAND)
                self.maininput_sizer.Layout()
                self.SetSizerAndFit(self.mainsizer)
        # Set current time to LastUpdateTime
        self.LastUpdateTime = time.time()
                
    def CalcParseRate(self, name, nbrparsed):
        # Compare data from five runs ago with new data and calculate
        # a parse rate
        rate = 0
        # If there are a LastUpdateTime, check for input_stats
        if self.LastUpdateTime:
            # Calculate a timediff (in seconds)
            timediff = time.time() - self.LastUpdateTime
            # Check if OldParseStats are available
            if name in self.OldParseStats:
                # Calculate a rate based on the oldest of the five
                # previous updates
                diff = nbrparsed - self.OldParseStats[name][0]
                # Calculate the rate
                rate = round((diff / (timediff * 5)), 1)
            else:
                # Set the list to current values
                self.OldParseStats[name] = [nbrparsed,nbrparsed,nbrparsed,nbrparsed,nbrparsed]
            # Set new stats to the OldParseStats list
            self.OldParseStats[name].append(nbrparsed)
            # Remove the oldest (first) item
            del self.OldParseStats[name][0]
        # Return rate
        return rate

    def CalcHorizon(self, grey_dict):
        # Calculate a "horizon", the distance to greyed out objects
        # Set as initial values
        nbrgreyitems = 0
        nbrhorizonitems = 0
        totaldistance = 0
        distancevalues = []
        # Extract values from grey_dict
        for distance in grey_dict.itervalues():
            nbrgreyitems += 1
            if distance:
                totaldistance += float(distance)
                distancevalues.append(float(distance))
                nbrhorizonitems += 1
        # Calculate median
        median = 0
        # Calculate meanvalue
        if totaldistance > 0: mean = (totaldistance/nbrhorizonitems)
        else: mean = 0
        # Sort the list and take the middle element.
        n = len(distancevalues)
        # Make sure that "numbers" keeps its original order
        copy = distancevalues[:]
        copy.sort()
        if n > 2:
            # If there is an odd number of elements
            if n & 1:
                median = copy[n // 2]
            else:
                median = (copy[n // 2 - 1] + copy[n // 2]) / 2
        # Calculate minimum and maximum
        minimum = 0
        maximum = 0
        try:
            minimum = min(distancevalues)
            maximum = max(distancevalues)
        except: pass
        # Return strings
        return nbrgreyitems, nbrhorizonitems, minimum, maximum, mean, median

    def SetData(self, data):
        # Make an update with the new data
        # data[0] is the stats dict
        # data[1] is the grey dict
        # data[2] is the total nbr of items
        self.Update(data[0], data[1], data[2])

    def OnClose(self, event):
        self.Destroy()


class SetAlertsWindow(wx.Dialog):
    # Make a dict for the list ctrl data
    list_data = {}

    def __init__(self, parent, id):
        # Define the dialog
        wx.Dialog.__init__(self, parent, id, title=_("Set alerts and remarks"))
        # Create panels
        filter_panel = wx.Panel(self, -1)
        list_panel = wx.Panel(self, -1, style=wx.CLIP_CHILDREN)
        self.object_panel = wx.Panel(self, -1)
        action_panel = wx.Panel(self, -1)
        # Create static boxes
        wx.StaticBox(filter_panel, -1, _(" Filter "), pos=(3,5), size=(700,100))
        list_staticbox = wx.StaticBox(list_panel, -1, _(" List view "), pos=(3,5), size=(700,280))
        wx.StaticBox(self.object_panel, -1, _(" Selected object "), pos=(3,5), size=(570,160))
        wx.StaticBox(action_panel, -1, _(" Actions "), pos=(3,5), size=(130,160))

        # Create objects on the filter panel
        wx.StaticText(filter_panel, -1, _("Filter using the checkboxes or by typing in the text box"), pos=(20,28))
        self.checkbox_filteralerts = wx.CheckBox(filter_panel, -1, _("Only show objects with alerts"), pos=(10,50))
        self.checkbox_filterremarks = wx.CheckBox(filter_panel, -1, _("Only show objects with remarks"), pos=(10,70))
        self.combobox_filtercolumn = wx.ComboBox(filter_panel, -1, pos=(300,60), size=(100,-1), value="Name", choices=("MMSI", "IMO", "Callsign", "Name"), style=wx.CB_READONLY)
        self.textctrl_filtertext = wx.TextCtrl(filter_panel, -1, pos=(415,60),size=(250,-1))

        # Define class-wide variable containing current filtering
        # If filter_query is empty, no filter is set
        # If filter_alerts is true, only show rows where alerts are set.
        # If filter_rermarks is true, only show rows where remarks are set.
        self.current_filter = {}

        # Create the object information objects
        wx.StaticText(self.object_panel, -1, _("MMSI nbr:"), pos=(20,25))
        self.statictext_mmsi = wx.StaticText(self.object_panel, -1, '', pos=(20,45))
        wx.StaticText(self.object_panel, -1, _("IMO nbr:"), pos=(120,25))
        self.statictext_imo = wx.StaticText(self.object_panel, -1, '', pos=(120,45))
        wx.StaticText(self.object_panel, -1, _("Callsign:"), pos=(220,25))
        self.statictext_cs = wx.StaticText(self.object_panel, -1, '', pos=(220,45))
        wx.StaticText(self.object_panel, -1, _("Name:"), pos=(320,25))
        self.statictext_name = wx.StaticText(self.object_panel, -1, '', pos=(320,45))
        statictext_remark = wx.StaticText(self.object_panel, -1, _("Remark field:"), pos=(25,73))
        statictext_remark.SetFont(wx.Font(10, wx.NORMAL, wx.NORMAL, wx.NORMAL))
        self.textctrl_remark = wx.TextCtrl(self.object_panel, -1, pos=(20,90), size=(300,60), style=wx.TE_MULTILINE)
        self.radiobox_alert = wx.RadioBox(self.object_panel, -1, _(" Alert "), pos=(340,70), choices=(_("&No"), _("&Yes"), _("&Sound")))
        self.update_button = wx.Button(self.object_panel, 10, _("&Update object"), pos=(350,120))
        self.object_panel.Enable(False)

        # Create the list control
        self.lc = self.List(list_panel, self)

        # Create buttons
        wx.Button(action_panel, 20, _("&Insert new..."), pos=(20,50))
        wx.Button(action_panel, 22, _("&Export list..."), pos=(20,90))
        self.apply_button = wx.Button(self, 31, _("&Apply changes"))
        self.apply_button.Enable(False)
        self.save_button = wx.Button(self, 32, _("&Save changes"))
        self.save_button.Enable(False)
        close_button = wx.Button(self, 30, _("&Close"))

        # Create sizers
        mainsizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        mainsizer.Add(filter_panel, 1, wx.EXPAND, 0)
        mainsizer.Add(list_panel, 0)
        lowsizer = wx.BoxSizer(wx.HORIZONTAL)
        lowsizer.Add(self.object_panel, 1)
        lowsizer.Add(action_panel, 0, wx.EXPAND)
        mainsizer.Add(lowsizer, 0)
        mainsizer.AddSpacer((0,10))
        mainsizer.Add(sizer2, 0, flag=wx.ALIGN_RIGHT)
        sizer2.Add(self.apply_button, 0)
        sizer2.AddSpacer((15,0))
        sizer2.Add(self.save_button, 0)
        sizer2.AddSpacer((50,0))
        sizer2.Add(close_button, 0)
        self.SetSizerAndFit(mainsizer)
        mainsizer.Layout()

        # Define events
        self.Bind(wx.EVT_CHECKBOX, self.OnFilter, self.checkbox_filteralerts)
        self.Bind(wx.EVT_CHECKBOX, self.OnFilter, self.checkbox_filterremarks)
        self.Bind(wx.EVT_TEXT, self.OnFilter, self.textctrl_filtertext)
        self.Bind(wx.EVT_TEXT, self.OnObjectEdit, self.textctrl_remark)
        self.Bind(wx.EVT_RADIOBOX, self.OnObjectEdit, self.radiobox_alert)
        self.Bind(wx.EVT_BUTTON, self.OnObjectUpdate, id=10)
        self.Bind(wx.EVT_BUTTON, self.OnInsertNew, id=20)
        self.Bind(wx.EVT_BUTTON, self.OnExportList, id=22)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=30)
        self.Bind(wx.EVT_BUTTON, self.OnApplyChanges, id=31)
        self.Bind(wx.EVT_BUTTON, self.OnSaveChanges, id=32)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Set queries in MainThread's queue
        main_thread.put({'remarkdict_query': None})
        main_thread.put({'iddb_query': None})

        # Tell the user that we're busy
        wx.BusyCursor()

    def GetData(self, message):
        # Update the list ctrl dict with new data
        # If remarks, put in alerts and remarks in dict
        if 'remarkdict' in message:
            for mmsi, (alert,remark) in message['remarkdict'].iteritems():
                row = self.list_data.get(mmsi, {})
                row['alert'] = alert
                row['remark'] = remark
                self.list_data[mmsi] = row
        # If IDDB data, put in metadata in dict
        elif 'iddb' in message:
            for object in message['iddb']:
                mmsi = object['mmsi']
                row = self.list_data.get(mmsi, {})
                row['imo'] = object['imo']
                row['callsign'] = object['callsign']
                row['name'] = object['name']
                self.list_data[mmsi] = row
        # Update the listctrl
        self.lc.OnUpdate()
        # We're not busy anymore
        wx.BusyCursor()

    def PopulateObject(self, objectinfo):
        # Populate the object_panel with info from the currently
        # selected list row
        if objectinfo:
            self.object_panel.Enable(True)
            self.update_button.Enable(False)
            self.loaded_objectinfo = objectinfo
            self.statictext_mmsi.SetLabel(unicode(objectinfo[0]))
            self.statictext_imo.SetLabel(unicode(objectinfo[1]))
            self.statictext_cs.SetLabel(unicode(objectinfo[2]))
            self.statictext_name.SetLabel(unicode(objectinfo[3]))
            self.radiobox_alert.SetSelection(int(objectinfo[4]))
            self.textctrl_remark.ChangeValue(unicode(objectinfo[5]))
        else:
            self.object_panel.Enable(False)
            self.update_button.Enable(False)
            self.loaded_objectinfo = None
            self.statictext_mmsi.SetLabel('')
            self.statictext_imo.SetLabel('')
            self.statictext_cs.SetLabel('')
            self.statictext_name.SetLabel('')
            self.radiobox_alert.SetSelection(0)
            self.textctrl_remark.ChangeValue('')

    def OnObjectEdit(self, event):
        # Enable update button
        self.update_button.Enable(True)

    def OnObjectUpdate(self, event):
        # Check if variable exist, if not, return
        try:
            assert self.loaded_objectinfo
        except: return
        # Read in the object information to be saved
        mmsi = int(self.loaded_objectinfo[0])
        alert_box = self.radiobox_alert.GetSelection()
        remark_box = unicode(self.textctrl_remark.GetValue()).strip().replace(",",";")
        # Set alert
        if alert_box == 1:
            alert = 'A'
        elif alert_box == 2:
            alert = 'AS'
        else:
            alert = ''
        self.list_data[mmsi]['alert'] = alert
        # Set remark
        if remark_box.isspace():
            # Set remark to empty if it only contains whitespace
            self.list_data[mmsi]['remark'] = ''
        else:
            # Set remark
            self.list_data[mmsi]['remark'] = remark_box
        # Update the listctrl
        self.lc.OnUpdate()
        # Make main save and apply buttons enabled
        self.save_button.Enable(True)
        self.apply_button.Enable(True)
        # Make object update button disabled
        self.update_button.Enable(False)
        # Update the text ctrl
        self.textctrl_remark.ChangeValue(remark_box)

    def OnFilter(self, event):
        # Read values from the filter controls and set appropriate
        # values in self.current_filter
        self.current_filter["filter_alerts"] = self.checkbox_filteralerts.GetValue()
        self.current_filter["filter_remarks"] = self.checkbox_filterremarks.GetValue()
        # If the text control contains text, set a query from the value
        # in the combobox and the text control. Replace dangerous char (,)
        # Else, set the filter query to empty.
        if len(self.textctrl_filtertext.GetValue()) > 0:
            self.current_filter["filter_column"] = self.combobox_filtercolumn.GetValue()
            self.current_filter["filter_query"] = self.textctrl_filtertext.GetValue().replace(",","").upper()
        else:
            self.current_filter["filter_column"] = ""
            self.current_filter["filter_query"] = ""
        # Update the listctrl
        self.lc.OnUpdate()

    def OnInsertNew(self, event):
        # Create a dialog with a textctrl, a checkbox and two buttons
        dlg = wx.Dialog(self, -1, _("Insert new MMSI number"), size=(250,130))
        wx.StaticText(dlg, -1, _("Enter the MMSI number to insert:"), pos=(20,10), size=(200,30))
        textbox = wx.TextCtrl(dlg, -1, pos=(20,40), size=(150,-1))
        buttonsizer = dlg.CreateStdDialogButtonSizer(wx.CANCEL|wx.OK)
        buttonsizer.SetDimension(80, 70, 120, 40)
        textbox.SetFocus()
        # If user press OK, check that the textbox only contains digits,
        # check if the number already exists and if not, create object
        if dlg.ShowModal() == wx.ID_OK:
            new_mmsi = textbox.GetValue()
            if not new_mmsi.isdigit() or len(new_mmsi) > 9:
                dlg = wx.MessageDialog(self, _("Only nine digits are allowed in a MMSI number! Insert failed."), _("Error"), wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
            elif int(new_mmsi) in self.list_data:
                dlg = wx.MessageDialog(self, _("The specified MMSI number already exists! Insert failed."), _("Error"), wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
            else:
                self.list_data[int(new_mmsi)] = {}
            # Update list ctrl
            self.lc.OnUpdate()
            # Set active item
            self.lc.SetSelectedItem(int(new_mmsi))

    def OnApplyChanges(self, event):
        # Applies changes by sending them to MainThread
        alertdict = {}
        # Iterate over the data and pick out alerts and remarks
        for mmsi, entry in self.list_data.iteritems():
            # Get alert
            alert = entry.get('alert','')
            # Get remark
            remark = entry.get('remark','')
            # If neither remark or alert is set, don't save
            if len(alert) == 0 and len(remark) == 0:
                pass
            else:
                # For each entry split the data using ','
                alertdict[mmsi] = (alert, remark)
        # Send to main thread
        main_thread.put({'update_remarkdict': alertdict})
        # Make apply disabled
        self.apply_button.Enable(False)

    def OnSaveChanges(self, event):
        # Saves alerts and remarks to the loaded keyfile.
        # First, apply changes
        self.OnApplyChanges(None)
        # Save file
        remark_file = unicode(config['alert']['remarkfile'], 'utf-8')
        if config['alert'].as_bool('remarkfile_on'):
            # Saves remarks to a supplied file
            if len(remark_file) > 0:
                try:
                    # Open file
                    output = codecs.open(os.path.join(package_home(globals()), remark_file), 'w', encoding='cp1252')
                    # Loop over data
                    for mmsi, entry in self.list_data.iteritems():
                        # Get alert
                        alert = entry.get('alert','')
                        # Get remark
                        remark = entry.get('remark','')
                        # If neither remark or alert is set, don't save
                        if len(alert) == 0 and len(remark) == 0:
                            pass
                        else:
                            # For each entry split the data using ','
                            output.write(str(mmsi) + "," + alert + "," + remark + "\r\n")
                    output.close()
                    # Make save button and apply button disabled
                    self.save_button.Enable(False)
                    self.apply_button.Enable(False)
                except IOError, error:
                    dlg = wx.MessageDialog(self, _("Cannot save remark file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                    dlg.ShowModal()
                except Exception, error:
                    dlg = wx.MessageDialog(self, _("Cannot save remark file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                    dlg.ShowModal()
        else:
            dlg = wx.MessageDialog(self, _("Cannot save remark file. No remark file is loaded.") + "\n" + _("Edit the remark file settings and restart the program."), style=wx.OK|wx.ICON_ERROR)
            dlg.ShowModal()

    def OnExportList(self, event):
        # Exports the current list view to a CSV-like file.
        exportdata = ""
        for mmsi, row in self.lc.itemDataMap.iteritems():
            alert = row[4]
            if alert == 0:
                alert = "No"
            elif alert == 1:
                alert = "Yes"
            elif alert == 2:
                alert = "Yes/Sound"
            exportdata += str(mmsi) + "," + str(row[1]) + "," + row[2] + "," + row[3] + "," + alert + "," + row[5] + "\n"
        # Create file dialog
        file = ''
        wcd = _("CSV files (*.csv)|*.csv|All files (*)|*")
        dir = os.getcwd()
        open_dlg = wx.FileDialog(self, message=_("Choose file to save current list"), defaultDir=dir, defaultFile='list.csv', wildcard=wcd, style=wx.SAVE)
        if open_dlg.ShowModal() == wx.ID_OK:
            file = unicode(open_dlg.GetPath())
        if len(file) > 0:
            # Save the data
            try:
                output = codecs.open(file, 'w', encoding='cp1252')
                output.write(exportdata)
                output.close()
            except IOError, error:
                dlg = wx.MessageDialog(self, _("Cannot save file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()
            except error:
                dlg = wx.MessageDialog(self, _("Cannot save file") + "\n" + str(error), style=wx.OK|wx.ICON_ERROR)
                dlg.ShowModal()


    class List(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin, listmix.ColumnSorterMixin):
        def __init__(self, parent, topparent):
            wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL, size=(650,230), pos=(20,30))

            self.topparent = topparent

            # Define and retreive two arrows, one upwards, the other downwards
            self.imagelist = wx.ImageList(16, 16)
            self.sm_up = self.imagelist.Add(getSmallUpArrowBitmap())
            self.sm_dn = self.imagelist.Add(getSmallDnArrowBitmap())
            self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

            # Iterate over the given columns and create the specified ones
            self.InsertColumn(0, _("MMSI nbr"))
            self.InsertColumn(1, _("IMO nbr"))
            self.InsertColumn(2, _("CS"))
            self.InsertColumn(3, _("Name"))
            self.InsertColumn(4, _("Alert"))
            self.InsertColumn(5, _("Remark"))
            self.SetColumnWidth(0, 90)
            self.SetColumnWidth(1, 80)
            self.SetColumnWidth(2, 60)
            self.SetColumnWidth(3, 150)
            self.SetColumnWidth(4, 70)
            self.SetColumnWidth(5, 190)

            # Use the mixins
            listmix.ListCtrlAutoWidthMixin.__init__(self)
            listmix.ColumnSorterMixin.__init__(self, 6)

            # Set selected object to none
            self.selected = -1
            
            # Do inital update
            self.OnUpdate()
            # Do initial sorting on column 0, ascending order (1)
            self.SortListItems(0, 1)

            # Define events
            self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
            self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected)

        def OnItemSelected(self, event):
            # When an object is selected, extract the MMSI number and
            # put it in self.selected
            self.selected = self.itemIndexMap[event.m_itemIndex]
            # Populate the object box
            self.topparent.PopulateObject(self.itemDataMap[self.selected])

        def OnItemDeselected(self, event):
            # Deselect objects
            self.selected = -1
            # Depopulate the object box
            self.topparent.PopulateObject(None)

        def SetSelectedItem(self, mmsi):
            # Set selected
            self.selected = mmsi
            # Refresh ctrl
            self.SortListItems()
            # Populate the object box
            self.topparent.PopulateObject(self.itemDataMap[mmsi])

        def OnUpdate(self):
            # Set empty dict
            list_dict = {}

            # Get current filter settings
            filter = self.topparent.current_filter.copy()
            filter_alerts = filter.get('filter_alerts',False)
            filter_remarks = filter.get('filter_remarks',False)
            filter_column = filter.get('filter_column','')
            filter_query = filter.get('filter_query','')

            # Populate the list dict with data
            for mmsi, value in self.topparent.list_data.iteritems():
                # The row list has data according to list
                # [mmsi, imo, callsign, name, alert, remark]
                row =  [mmsi, None, None, None, None, None]
                row[1] = value.get('imo','')
                row[2] = value.get('callsign','')
                row[3] = value.get('name','')
                alert = value.get('alert','')
                if alert == 'A':
                    # Alert active
                    row[4] = 1
                elif alert == 'AS':
                    # Alert+sound active
                    row[4] = 2
                else:
                    # No alert
                    row[4] = 0
                row[5] = value.get('remark','')
                # See if we should add mmsi to dict
                # Filter on columns, alerts and remarks
                if filter_query and filter_column == 'MMSI' and unicode(mmsi).find(filter_query) == -1:
                    pass
                elif filter_query and filter_column == 'IMO' and unicode(row[1]).find(filter_query) == -1:
                    pass
                elif filter_query and filter_column == 'Callsign' and unicode(row[2]).find(filter_query) == -1:
                    pass
                elif filter_query and filter_column == 'Name' and unicode(row[3]).find(filter_query) == -1:
                    pass
                elif filter_alerts and not alert:
                    pass
                elif filter_remarks and not row[5]:
                    pass
                else:
                    list_dict[mmsi] = row

            # Set new ItemCount for the list ctrl if different from the current number
            nbrofobjects = len(list_dict)
            if self.GetItemCount() != nbrofobjects:
                self.SetItemCount(nbrofobjects)

            # Assign to variables for the virtual list ctrl
            self.itemDataMap = list_dict.copy()
            self.itemIndexMap = list_dict.keys()

            # If no objects in list, deselect all
            if nbrofobjects == 0:
                # Deselect objects
                self.selected = -1
                # Depopulate the object box
                self.topparent.PopulateObject(None)

            self.SortListItems()

        def OnGetItemText(self, item, col):
            # Return the text in item, col
            mmsi = self.itemIndexMap[item]
            string = self.itemDataMap[mmsi][col]
            # If column with alerts, map 0, 1 and 2 to text strings
            if col == 4:
                if string == 0: string = _("No")
                elif string == 1: string = _("Yes")
                elif string == 2: string = _("Yes/Sound")
            # If string is a Nonetype, replace with an empty string
            elif string == None:
                string = u''
            return unicode(string)

        def SortItems(self,sorter=cmp):
            items = list(self.itemDataMap.keys())
            items.sort(sorter)
            self.itemIndexMap = items

            # Workaround for updating listctrl on Windows
            if os.name == 'nt':
                self.Refresh()

            # See if the previous selected row exists after the sort
            # If the MMSI number is found, set the new position as
            # selected and visible. If not found, deselect all objects
            # and depopulate the object box
            try:
                if self.selected in self.itemDataMap:
                    new_position = self.FindItem(-1, unicode(self.selected))
                    self.SetItemState(new_position, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
                    self.EnsureVisible(new_position)
                else:
                    for i in range(self.GetItemCount()):
                        self.SetItemState(i, 0, wx.LIST_STATE_SELECTED)
                        self.selected = -1
                        # Depopulate the object box
                        self.topparent.PopulateObject(None)
            except: pass

        # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
        def GetListCtrl(self):
            return self

        # Overrides the normal __ColumnSorter due to unicode bug with
        # locale.strcoll
        def GetColumnSorter(self):
            return self.myColumnSorter

        def myColumnSorter(self, key1, key2):
            col = self._col
            ascending = self._colSortFlag[col]
            item1 = self.itemDataMap[key1][col]
            item2 = self.itemDataMap[key2][col]
            cmpVal = cmp(item1, item2)
            # If the items are equal then pick something else to make
            # the sort value unique
            if cmpVal == 0:
                cmpVal = apply(cmp, self.GetSecondarySortValues(col, key1, key2))
            if ascending:
                return cmpVal
            else:
                return -cmpVal

        # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
        def GetSortImages(self):
            return (self.sm_dn, self.sm_up)

    def OnClose(self, event):
        self.Destroy()


class SettingsWindow(wx.Dialog):
    def __init__(self, parent, id):
        wx.Dialog.__init__(self, parent, id, title=_("Settings"))
        # Define a notebook
        notebook = wx.Notebook(self, -1)
        # Define panels for each tab in the notebook
        common_panel = wx.Panel(notebook, -1)
        serial_panel = wx.Panel(notebook, -1)
        network_panel = wx.Panel(notebook, -1)
        logging_panel = wx.Panel(notebook, -1)
        alert_panel = wx.Panel(notebook, -1)
        listview_panel = wx.Panel(notebook, -1)
        alertlistview_panel = wx.Panel(notebook, -1)
        map_panel = wx.Panel(notebook, -1)

        # Populate panel for common options
        # Common GUI settings
        commonlist_panel = wx.Panel(common_panel, -1)
        wx.StaticBox(commonlist_panel, -1, _(" General GUI settings "), pos=(10,5), size=(450,225))
        wx.StaticText(commonlist_panel, -1, _("Threshold for greying-out objects (s):"), pos=(20,35))
        self.commonlist_greytime = wx.SpinCtrl(commonlist_panel, -1, pos=(320,30), min=10, max=604800)
        wx.StaticText(commonlist_panel, -1, _("Threshold for removal of objects (s):"), pos=(20,72))
        self.commonlist_deletetime = wx.SpinCtrl(commonlist_panel, -1, pos=(320,65), min=10, max=604800)
        wx.StaticText(commonlist_panel, -1, _("Time between updating GUI with new data (s):"), pos=(20,107))
        self.commonlist_updatetime = wx.SpinCtrl(commonlist_panel, -1, pos=(320,100), min=1, max=604800)
        wx.StaticText(commonlist_panel, -1, _("Number of updates to an object before displaying:"), pos=(20,144))
        self.commonlist_showafterupdates = wx.SpinCtrl(commonlist_panel, -1, pos=(320,135), min=1, max=100000)
        self.commonlist_classbtoggle = wx.CheckBox(commonlist_panel, -1, _("Enable display of Class B stations"), pos=(20,174))
        self.commonlist_basestationtoggle = wx.CheckBox(commonlist_panel, -1, _("Enable display of base stations"), pos=(20,199))
        # Position config
        manualpos_panel = wx.Panel(common_panel, -1)
        wx.StaticBox(manualpos_panel, -1, _(" Position settings "), pos=(10,5), size=(450,210))
        self.manualpos_format = wx.RadioBox(manualpos_panel, -1, _(" Position display format "), pos=(20,20), choices=(u"DD (0.0°)", u"DM (0° 00')", u"DMS (0° 00' 00'')"))
        wx.StaticText(manualpos_panel, -1, _("Use position data from source: "), pos=(20,75))
        self.manualpos_datasource = wx.ComboBox(manualpos_panel, -1, pos=(210,70), size=(230,-1), value='Any', style=wx.CB_READONLY)
        self.manualpos_overridetoggle = wx.CheckBox(manualpos_panel, -1, _("Use the supplied manual position and ignore position messages:"), pos=(20,103))
        wx.StaticText(manualpos_panel, -1, _("Latitude:"), pos=(20,140))
        self.manualpos_latdeg = wx.SpinCtrl(manualpos_panel, -1, pos=(90,134), size=(55,-1), min=0, max=89)
        wx.StaticText(manualpos_panel, -1, _("deg"), pos=(150,140))
        self.manualpos_latmin = wx.SpinCtrl(manualpos_panel, -1, pos=(180,134), size=(55,-1), min=0, max=59)
        wx.StaticText(manualpos_panel, -1, _("min"), pos=(240,140))
        self.manualpos_latsec = wx.SpinCtrl(manualpos_panel, -1, pos=(270,134), size=(55,-1), min=0, max=59)
        wx.StaticText(manualpos_panel, -1, _("sec"), pos=(330,140))
        self.manualpos_latquad = wx.ComboBox(manualpos_panel, -1, pos=(370,134), size=(55,-1), choices=('N', 'S'), style=wx.CB_READONLY)
        wx.StaticText(manualpos_panel, -1, _("Longitude:"), pos=(20,180))
        self.manualpos_longdeg = wx.SpinCtrl(manualpos_panel, -1, pos=(90,174), size=(55,-1), min=0, max=179)
        wx.StaticText(manualpos_panel, -1, _("deg"), pos=(150,180))
        self.manualpos_longmin = wx.SpinCtrl(manualpos_panel, -1, pos=(180,174), size=(55,-1), min=0.0, max=59)
        wx.StaticText(manualpos_panel, -1, _("min"), pos=(240,180))
        self.manualpos_longsec = wx.SpinCtrl(manualpos_panel, -1, pos=(270,174), size=(55,-1), min=0, max=59)
        wx.StaticText(manualpos_panel, -1, _("sec"), pos=(330,180))
        self.manualpos_longquad = wx.ComboBox(manualpos_panel, -1, pos=(370,174), size=(55,-1), choices=('E', 'W'), style=wx.CB_READONLY)
        # Add panels to main sizer
        common_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        common_panel_sizer.Add(commonlist_panel, 0)
        common_panel_sizer.Add(manualpos_panel, 0)
        common_panel.SetSizer(common_panel_sizer)

        # Populate panel for serial port config
        # Choose port to config
        serialchoose_panel = wx.Panel(serial_panel, -1)
        wx.StaticBox(serialchoose_panel, -1, _(" Choose serial port to configure "), pos=(10,5), size=(450,125))
        self.serialchoose_port = wx.ListBox(serialchoose_panel, -1, pos=(25,30), size=(220,80), style=wx.LB_SINGLE)
        self.serialchoose_remove = wx.Button(serialchoose_panel, 20, _("&Remove port"), pos=(280,35))
        self.serialchoose_insert = wx.Button(serialchoose_panel, 21, _("&Insert new port"), pos=(280,80))
        self.serialchoose_remove.Enable(False)
        # Serial port config
        self.port_panel = wx.Panel(serial_panel, -1)
        self.port_name = wx.StaticBox(self.port_panel, -1, _(" Serial port settings "), pos=(10,5), size=(450,160))
        self.port_serialon = wx.CheckBox(self.port_panel, -1, _("Activate reading data from this serial port"), pos=(20,20))
        self.port_sendtoserial = wx.CheckBox(self.port_panel, -1, _("Send data to serial server"), pos=(20,40))
        self.port_sendtonetwork = wx.CheckBox(self.port_panel, -1, _("Send data to network server"), pos=(20,60))
        wx.StaticText(self.port_panel, -1, _("Port: "), pos=(20,95))
        self.port_port = wx.ComboBox(self.port_panel, -1, pos=(110,90), size=(100,-1), choices=('Com1', 'Com2', 'Com3', 'Com4'))
        wx.StaticText(self.port_panel, -1, _("Speed: "), pos=(20,125))
        self.port_speed = wx.ComboBox(self.port_panel, -1, pos=(110,120), size=(100,-1), choices=('9600', '38400'))
        self.port_xonxoff = wx.CheckBox(self.port_panel, -1, _("Software flow control:"), pos=(240,95), style=wx.ALIGN_RIGHT)
        self.port_rtscts = wx.CheckBox(self.port_panel, -1, _("RTS/CTS flow control:"), pos=(240,125), style=wx.ALIGN_RIGHT)
        self.port_panel.Enable(False)
        # Serial server config
        serialserver_panel = wx.Panel(serial_panel, -1)
        wx.StaticBox(serialserver_panel, -1, _(" Settings for acting as a serial server "), pos=(10,5), size=(450,115))
        self.serialserver_serialon = wx.CheckBox(serialserver_panel, -1, _("Activate serial server (relay incoming data)"), pos=(20,20))
        wx.StaticText(serialserver_panel, -1, _("Port: "), pos=(20,55))
        self.serialserver_port = wx.ComboBox(serialserver_panel, -1, pos=(110,50), size=(100,-1), choices=('Com1', 'Com2', 'Com3', 'Com4'))
        wx.StaticText(serialserver_panel, -1, _("Speed: "), pos=(20,85))
        self.serialserver_speed = wx.ComboBox(serialserver_panel, -1, pos=(110,80), size=(100,-1), choices=('9600', '38400'))
        self.serialserver_xonxoff = wx.CheckBox(serialserver_panel, -1, _("Software flow control:"), pos=(240,55), style=wx.ALIGN_RIGHT)
        self.serialserver_rtscts = wx.CheckBox(serialserver_panel, -1, _("RTS/CTS flow control:"), pos=(240,85), style=wx.ALIGN_RIGHT)
        # Add panels to main sizer
        serial_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        serial_panel_sizer.Add(serialchoose_panel, 0)
        serial_panel_sizer.Add(self.port_panel, 0)
        serial_panel_sizer.Add(serialserver_panel, 0)
        serial_panel.SetSizer(serial_panel_sizer)

        # Populate panel for network config
        # Choose server to config
        networkchoose_panel = wx.Panel(network_panel, -1)
        wx.StaticBox(networkchoose_panel, -1, _(" Choose network server to configure "), pos=(10,5), size=(450,125))
        self.networkchoose_server = wx.ListBox(networkchoose_panel, -1, pos=(25,30), size=(250,80), style=wx.LB_SINGLE)
        self.networkchoose_remove = wx.Button(networkchoose_panel, 30, _("&Remove server"), pos=(310,35))
        self.networkchoose_insert = wx.Button(networkchoose_panel, 31, _("&Insert new server"), pos=(310,80))
        self.networkchoose_remove.Enable(False)
        # Network receive config
        self.netrec_panel = wx.Panel(network_panel, -1)
        wx.StaticBox(self.netrec_panel, -1, _(" Settings for reading from a network server "), pos=(10,5), size=(450,155))
        self.netrec_clienton = wx.CheckBox(self.netrec_panel, -1, _("Activate reading data from this network server"), pos=(20,20))
        self.netrec_sendtoserial = wx.CheckBox(self.netrec_panel, -1, _("Send data to serial server"), pos=(20,40))
        self.netrec_sendtonetwork = wx.CheckBox(self.netrec_panel, -1, _("Send data to network server"), pos=(20,60))
        wx.StaticText(self.netrec_panel, -1, _("Address of streaming host (IP):"), pos=(20,95))
        self.netrec_clientaddress = wx.TextCtrl(self.netrec_panel, -1, pos=(230,90), size=(165,-1))
        wx.StaticText(self.netrec_panel, -1, _("Port of streaming host:"), pos=(20,130))
        self.netrec_clientport = wx.SpinCtrl(self.netrec_panel, -1, pos=(230,125), min=0, max=65535)
        self.netrec_panel.Enable(False)
        # Network send config
        netsend_panel = wx.Panel(network_panel, -1)
        wx.StaticBox(netsend_panel, -1, _(" Settings for acting as a network server "), pos=(10,5), size=(450,120))
        self.netsend_serveron = wx.CheckBox(netsend_panel, -1, _("Activate network server (relay incoming data)"), pos=(20,20))
        wx.StaticText(netsend_panel, -1, _("Server address (this server) (IP):"), pos=(20,55))
        self.netsend_serveraddress = wx.TextCtrl(netsend_panel, -1, pos=(220,48), size=(175,-1))
        wx.StaticText(netsend_panel, -1, _("Server port (this server):"), pos=(20,90))
        self.netsend_serverport = wx.SpinCtrl(netsend_panel, -1, pos=(220,83), min=0, max=65535)
        # Add panels to main sizer
        network_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        network_panel_sizer.Add(networkchoose_panel, 0)
        network_panel_sizer.Add(self.netrec_panel, 0)
        network_panel_sizer.Add(netsend_panel, 0)
        network_panel.SetSizer(network_panel_sizer)

        # Populate panel for log config
        # Log config
        filelog_panel = wx.Panel(logging_panel, -1)
        wx.StaticBox(filelog_panel, -1, _(" Logging to file "), pos=(10,5), size=(450,160))
        self.filelog_logtoggle = wx.CheckBox(filelog_panel, -1, _("Activate logging to database file"), pos=(20,28))
        self.filelog_logbasestationstoggle = wx.CheckBox(filelog_panel, -1, _("Enable logging of base stations"), pos=(20,53))
        wx.StaticText(filelog_panel, -1, _("Time between loggings (s):"), pos=(20,85))
        self.filelog_logtime = wx.SpinCtrl(filelog_panel, -1, pos=(230,80), min=1, max=604800)
        wx.StaticText(filelog_panel, -1, _("Log file"), pos=(20,125))
        self.filelog_logfile = wx.TextCtrl(filelog_panel, -1, pos=(75,119), size=(275,-1))
        self.filelog_logfileselect = wx.Button(filelog_panel, -1, _("&Browse..."), pos=(365,115))
        self.Bind(wx.EVT_BUTTON, self.OnLogFileDialog, self.filelog_logfileselect)
        # Identification DB config
        iddblog_panel = wx.Panel(logging_panel, -1)
        wx.StaticBox(iddblog_panel, -1, _(" Logging to identification database (IDDB) "), pos=(10,5), size=(450,140))
        self.iddblog_logtoggle = wx.CheckBox(iddblog_panel, -1, _("Activate logging to IDDB file"), pos=(20,28))
        wx.StaticText(iddblog_panel, -1, _("Time between loggings (s):"), pos=(20,65))
        self.iddblog_logtime = wx.SpinCtrl(iddblog_panel, -1, pos=(230,60), min=1, max=604800)
        wx.StaticText(iddblog_panel, -1, _("IDDB file:"), pos=(20,105))
        self.iddblog_logfile = wx.TextCtrl(iddblog_panel, -1, pos=(75,99), size=(275,-1))
        self.iddblog_logfileselect = wx.Button(iddblog_panel, -1, _("&Browse..."), pos=(365,95))
        self.Bind(wx.EVT_BUTTON, self.OnIDDBFileDialog, self.iddblog_logfileselect)
        # Exception logging
        exceptionlog_panel = wx.Panel(logging_panel, -1)
        wx.StaticBox(exceptionlog_panel, -1, _(" Exception logging (debugging) "), pos=(10,5), size=(450,70))
        self.exceptionlog_logtoggle = wx.CheckBox(exceptionlog_panel, -1, _("Activate exception logging to file (for debugging)"), pos=(20,28))
        # Add panels to main sizer
        logging_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        logging_panel_sizer.Add(filelog_panel, 0)
        logging_panel_sizer.Add(iddblog_panel, 0)
        logging_panel_sizer.Add(exceptionlog_panel, 0)
        logging_panel.SetSizer(logging_panel_sizer)

        # Populate panel for alert config
        # Alert file config
        alertfile_panel = wx.Panel(alert_panel, -1)
        wx.StaticBox(alertfile_panel, -1, _(" Alert/remark file "), pos=(10,5), size=(450,100))
        self.alertfile_toggle = wx.CheckBox(alertfile_panel, -1, _("Read alert/remark file at program startup"), pos=(20,28))
        wx.StaticText(alertfile_panel, -1, _("Alert/remark file:"), pos=(20,65))
        self.alertfile_file = wx.TextCtrl(alertfile_panel, -1, pos=(125,61), size=(220,-1))
        self.alertfile_fileselect = wx.Button(alertfile_panel, -1, _("&Browse..."), pos=(365,55))
        self.Bind(wx.EVT_BUTTON, self.OnAlertFileDialog, self.alertfile_fileselect)
        # Alert sound file config
        alertsoundfile_panel = wx.Panel(alert_panel, -1)
        wx.StaticBox(alertsoundfile_panel, -1, _(" Sound alert settings "), pos=(10,5), size=(450,100))
        self.alertsoundfile_toggle = wx.CheckBox(alertsoundfile_panel, -1, _("Activate sound alert"), pos=(20,23))
        wx.StaticText(alertsoundfile_panel, -1, _("Sound alert file:"), pos=(20,60))
        self.alertsoundfile_file = wx.TextCtrl(alertsoundfile_panel, -1, pos=(125,56), size=(220,-1))
        self.alertsoundfile_fileselect = wx.Button(alertsoundfile_panel, -1, _("&Browse..."), pos=(365,50))
        self.Bind(wx.EVT_BUTTON, self.OnAlertSoundFileDialog, self.alertsoundfile_fileselect)
        # Maximum alert distance config
        alertdistance_panel = wx.Panel(alert_panel, -1)
        wx.StaticBox(alertdistance_panel, -1, _(" Maximum distance for alert objects "), pos=(10,5), size=(450,100))
        self.alertdistance_toggle = wx.CheckBox(alertdistance_panel, -1, _("Activate maximum distance"), pos=(20,23))
        wx.StaticText(alertdistance_panel, -1, _("Maximum distance to alert object (km):"), pos=(20,60))
        self.alertdistance_distance = wx.SpinCtrl(alertdistance_panel, -1, pos=(305,56), min=1, max=100000)
        # Add panels to main sizer
        alert_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        alert_panel_sizer.Add(alertfile_panel, 0)
        alert_panel_sizer.Add(alertsoundfile_panel, 0)
        alert_panel_sizer.Add(alertdistance_panel, 0)
        alert_panel.SetSizer(alert_panel_sizer)

        # Populate panel for list view column setup
        # List view column config
        listcolumn_panel = wx.Panel(listview_panel, -1)
        wx.StaticBox(listcolumn_panel, -1, _(" Choose active columns in list view "), pos=(10,5), size=(450,280))
        wx.StaticText(listcolumn_panel, -1, _("Not active columns:"), pos=(35,40))
        self.listcolumn_notactive = wx.ListBox(listcolumn_panel, -1, pos=(30,60), size=(130,200), style=wx.LB_SINGLE|wx.LB_SORT)
        wx.Button(listcolumn_panel, 50, '-->', pos=(180,120), size=(50,-1))
        wx.Button(listcolumn_panel, 51, '<--', pos=(180,170), size=(50,-1))
        wx.StaticText(listcolumn_panel, -1, _("Active columns:"), pos=(255,40))
        self.listcolumn_active = wx.ListBox(listcolumn_panel, -1, pos=(250,60), size=(130,200), style=wx.LB_SINGLE)
        wx.Button(listcolumn_panel, 52, _("Up"), pos=(395,120), size=(50,-1))
        wx.Button(listcolumn_panel, 53, _("Down"), pos=(395,170), size=(50,-1))
        # Add panels to main sizer
        listview_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        listview_panel_sizer.Add(listcolumn_panel, 0)
        listview_panel.SetSizer(listview_panel_sizer)

        # Populate panel for alert list view column setup
        # Alert list view column config
        alertlistcolumn_panel = wx.Panel(alertlistview_panel, -1)
        wx.StaticBox(alertlistcolumn_panel, -1, _(" Choose active columns in alert list view "), pos=(10,5), size=(450,280))
        wx.StaticText(alertlistcolumn_panel, -1, _("Not active columns:"), pos=(35,40))
        self.alertlistcolumn_notactive = wx.ListBox(alertlistcolumn_panel, -1, pos=(30,60), size=(130,200), style=wx.LB_SINGLE|wx.LB_SORT)
        wx.Button(alertlistcolumn_panel, 60, '-->', pos=(180,120), size=(50,-1))
        wx.Button(alertlistcolumn_panel, 61, '<--', pos=(180,170), size=(50,-1))
        wx.StaticText(alertlistcolumn_panel, -1, _("Active columns:"), pos=(255,40))
        self.alertlistcolumn_active = wx.ListBox(alertlistcolumn_panel, -1, pos=(250,60), size=(130,200), style=wx.LB_SINGLE)
        wx.Button(alertlistcolumn_panel, 62, _("Up"), pos=(395,120), size=(50,-1))
        wx.Button(alertlistcolumn_panel, 63, _("Down"), pos=(395,170), size=(50,-1))
        # Add panels to main sizer
        alertlistview_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        alertlistview_panel_sizer.Add(alertlistcolumn_panel, 0)
        alertlistview_panel.SetSizer(alertlistview_panel_sizer)

        # Populate panel for map config
        # Map file config
        mapfile_panel = wx.Panel(map_panel, -1)
        wx.StaticBox(mapfile_panel, -1, _(" Map file "), pos=(10,5), size=(450,70))
        wx.StaticText(mapfile_panel, -1, _("Map file:"), pos=(20,35))
        self.mapfile_file = wx.TextCtrl(mapfile_panel, -1, pos=(125,31), size=(220,-1))
        self.mapfile_fileselect = wx.Button(mapfile_panel, -1, _("&Browse..."), pos=(365,25))
        self.Bind(wx.EVT_BUTTON, self.OnMapFileDialog, self.mapfile_fileselect)
        # Map color config
        mapcolor_panel = wx.Panel(map_panel, -1)
        wx.StaticBox(mapcolor_panel, -1, _(" Map color setup "), pos=(10,5), size=(450,275))
        wx.StaticText(mapcolor_panel, -1, _("Map background color:"), pos=(20,38))
        self.mapcolor_background = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,30), size=(80,30))
        wx.StaticText(mapcolor_panel, -1, _("Map shoreline color:"), pos=(20,78))
        self.mapcolor_shoreline = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,70), size=(80,30))
        wx.StaticText(mapcolor_panel, -1, _("Map object color:"), pos=(20,118))
        self.mapcolor_object = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,110), size=(80,30))
        wx.StaticText(mapcolor_panel, -1, _("Map old object color:"), pos=(20,158))
        self.mapcolor_old = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,150), size=(80,30))
        wx.StaticText(mapcolor_panel, -1, _("Map selected object color:"), pos=(20,198))
        self.mapcolor_selected = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,190), size=(80,30))
        wx.StaticText(mapcolor_panel, -1, _("Map alerted object color:"), pos=(20,238))
        self.mapcolor_alerted = wx.ColourPickerCtrl(mapcolor_panel, -1, 'White', pos=(200,230), size=(80,30))
        # Add panels to main sizer
        map_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        map_panel_sizer.Add(mapfile_panel, 0)
        map_panel_sizer.Add(mapcolor_panel, 0)
        map_panel.SetSizer(map_panel_sizer)

        # Dialog buttons
        but1 = wx.Button(self,1,_("&Save"))
        but2 = wx.Button(self,2,_("&Apply"))
        but3 = wx.Button(self,3,_("&Close"))

        # Sizer and notebook setup
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        notebook.AddPage(common_panel, _("Common"))
        notebook.AddPage(serial_panel, _("Serial ports"))
        notebook.AddPage(network_panel, _("Network"))
        notebook.AddPage(logging_panel, _("Logging"))
        notebook.AddPage(alert_panel, _("Alerts/remarks"))
        notebook.AddPage(listview_panel, _("List view"))
        notebook.AddPage(alertlistview_panel, _("Alert view"))
        notebook.AddPage(map_panel, _("Map"))
        sizer.Add(notebook, 1, wx.EXPAND, 0)
        sizer.AddSpacer((0,10))
        sizer.Add(sizer2, flag=wx.ALIGN_RIGHT)
        sizer2.Add(but1, 0)
        sizer2.AddSpacer((10,0))
        sizer2.Add(but2, 0)
        sizer2.AddSpacer((50,0))
        sizer2.Add(but3, 0)
        self.SetSizerAndFit(sizer)

        # Events
        self.Bind(wx.EVT_BUTTON, self.OnSave, id=1)
        self.Bind(wx.EVT_BUTTON, self.OnApply, id=2)
        self.Bind(wx.EVT_BUTTON, self.OnAbort, id=3)
        self.Bind(wx.EVT_BUTTON, self.OnSerialRemove, id=20)
        self.Bind(wx.EVT_BUTTON, self.OnSerialInsert, id=21)
        self.serialchoose_port.Bind(wx.EVT_LISTBOX, self.PopulateSerialConfig)
        self.Bind(wx.EVT_BUTTON, self.OnNetworkRemove, id=30)
        self.Bind(wx.EVT_BUTTON, self.OnNetworkInsert, id=31)
        self.networkchoose_server.Bind(wx.EVT_LISTBOX, self.PopulateNetworkConfig)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=50)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=51)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=52)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=53)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=60)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=61)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=62)
        self.Bind(wx.EVT_BUTTON, self.OnColumnChange, id=63)
        self.Bind(wx.EVT_CLOSE, self.OnAbort)

        # Set lists for holding serial and network data
        self.seriallist = []
        self.networklist = []
        # Set variables to hold current selection
        self.serialselected = -1
        self.networkselected = -1

        # Get values and update controls
        self.GetConfig()

    def GetConfig(self):
        # Get values from ConfigObj and set corresponding values in the controls
        # Common list settings
        self.commonlist_greytime.SetValue(config['common'].as_int('listmakegreytime'))
        self.commonlist_deletetime.SetValue(config['common'].as_int('deleteitemtime'))
        self.commonlist_updatetime.SetValue(config['common'].as_int('updatetime'))
        self.commonlist_showafterupdates.SetValue(config['common'].as_int('showafterupdates'))
        self.commonlist_classbtoggle.SetValue(config['common'].as_bool('showclassbstations'))
        self.commonlist_basestationtoggle.SetValue(config['common'].as_bool('showbasestations'))
        # Manual position settings
        if config['position']['position_format'].lower() == 'dd':
            self.manualpos_format.SetSelection(0)
        elif config['position']['position_format'].lower() == 'dm':
            self.manualpos_format.SetSelection(1)
        else:
            self.manualpos_format.SetSelection(2)
        self.manualpos_overridetoggle.SetValue(config['position'].as_bool('override_on'))
        # Calculate position
        latitude = float(config['position']['latitude'])
        longitude = float(config['position']['longitude'])
        latdeg = int(latitude)
        longdeg = int(longitude)
        latmin = (latitude - latdeg) * 60
        longmin = (longitude - longdeg) * 60
        latsec = (latmin - int(latmin)) * 60
        longsec = (longmin - int(longmin)) * 60
        if latitude > 0: latquad = 'N'
        else: latquad = 'S'
        if longitude > 0: longquad = 'E'
        else: longquad = 'W'
        # Set position
        self.manualpos_latdeg.SetValue(abs(latdeg))
        self.manualpos_latmin.SetValue(abs(latmin))
        self.manualpos_latsec.SetValue(abs(latsec))
        self.manualpos_latquad.SetValue(latquad)
        self.manualpos_longdeg.SetValue(abs(longdeg))
        self.manualpos_longmin.SetValue(abs(longmin))
        self.manualpos_longsec.SetValue(abs(longsec))
        self.manualpos_longquad.SetValue(longquad)
        # Set serial port list
        # Get all ports starting with serial
        ports = [ port for port in config.iterkeys()
                  if port.find('serial') != -1 ]
        # Iterate over ports
        for port in ports:
            if port == 'serial_server': continue
            # Get config
            conf = config[port]
            # Append to list
            self.seriallist.append([port, conf])
        # Update listbox
        self.UpdateSerialList()
        # Settings for serial server
        self.serialserver_serialon.SetValue(config['serial_server'].as_bool('server_on'))
        self.serialserver_port.SetValue(config['serial_server']['port'])
        self.serialserver_speed.SetValue(config['serial_server']['baudrate'])
        self.serialserver_xonxoff.SetValue(config['serial_server'].as_bool('xonxoff'))
        self.serialserver_rtscts.SetValue(config['serial_server'].as_bool('rtscts'))
        # Network settings
        clients = config['network']['client_addresses'].replace(' ', '').split(',')
        clients_enabled = config['network']['clients_on'].replace(' ', '').split(',')
        clients_to_serial = config['network']['clients_to_serial'].replace(' ', '').split(',')
        clients_to_server = config['network']['clients_to_server'].replace(' ', '').split(',')
        # If one of the config lists is empty, don't continue
        if not clients == ['']:
            for client in clients:
                if client in clients_enabled: status = True
                else: status = False
                if client in clients_to_serial: serial = True
                else: serial = False
                if client in clients_to_server: server = True
                else: server = False
                client_data = client.split(':')
                # Append IP, port, status, serial, network to list
                self.networklist.append([client_data[0], int(client_data[1]), status, serial, server])
        # Update listbox
        self.UpdateNetworkList()
        # Network server settings
        self.netsend_serveron.SetValue(config['network'].as_bool('server_on'))
        self.netsend_serveraddress.SetValue(config['network']['server_address'])
        self.netsend_serverport.SetValue(config['network'].as_int('server_port'))
        # Log settings
        self.filelog_logtoggle.SetValue(config['logging'].as_bool('logging_on'))
        self.filelog_logbasestationstoggle.SetValue(config['logging'].as_bool('logbasestations'))
        self.filelog_logtime.SetValue(config['logging'].as_int('logtime'))
        self.filelog_logfile.SetValue(config['logging']['logfile'])
        # IDDB log settings
        self.iddblog_logtoggle.SetValue(config['iddb_logging'].as_bool('logging_on'))
        self.iddblog_logtime.SetValue(config['iddb_logging'].as_int('logtime'))
        self.iddblog_logfile.SetValue(config['iddb_logging']['logfile'])
        # Exception log settings
        self.exceptionlog_logtoggle.SetValue(config['logging'].as_bool('logexceptions'))
        # Alert/remark settings
        self.alertfile_toggle.SetValue(config['alert'].as_bool('remarkfile_on'))
        self.alertfile_file.SetValue(config['alert']['remarkfile'])
        self.alertsoundfile_toggle.SetValue(config['alert'].as_bool('alertsound_on'))
        self.alertsoundfile_file.SetValue(config['alert']['alertsoundfile'])
        self.alertdistance_toggle.SetValue(config['alert'].as_bool('maxdistance_on'))
        self.alertdistance_distance.SetValue(config['alert'].as_int('maxdistance'))
        # List views column settings
        # Extract as list from comma separated list from dict
        self.listcolumns_as_list = config['common']['listcolumns'].replace(' ','').split(',')
        self.alertlistcolumns_as_list = config['common']['alertlistcolumns'].replace(' ', '').split(',')
        self.UpdateListColumns()
        self.UpdateAlertListColumns()
        # Map settings
        self.mapfile_file.SetValue(config['map']['mapfile'])
        self.mapcolor_background.SetColour(config['map']['background_color'])
        self.mapcolor_shoreline.SetColour(config['map']['shoreline_color'])
        self.mapcolor_object.SetColour(config['map']['object_color'])
        self.mapcolor_old.SetColour(config['map']['old_object_color'])
        self.mapcolor_selected.SetColour(config['map']['selected_object_color'])
        self.mapcolor_alerted.SetColour(config['map']['alerted_object_color'])
        # GPS data source
        self.manualpos_datasource.Append('Any')
        for s in self.seriallist:
            self.manualpos_datasource.Append(s[0])
        self.manualpos_datasource.SetValue(config['position']['use_position_from'])

    def UpdateSerialList(self):
        # Update the serial reader's listbox with data from
        # self.seriallist
        portlist = []
        for entry in self.seriallist:
            # Get enabled/disabled status
            if self.getConfigBool(entry[1], 'serial_on'): status = 'On'
            else: status = 'Off'
            portlist.append(entry[0] + " on port " + entry[1]['port'] + " (" + status + ")")
        self.serialchoose_port.Set(portlist)

    def UpdateNetworkList(self):
        # Update the network client's listbox with data from
        # self.networklist
        clientlist = []
        for entry in self.networklist:
            if entry[2]: status = 'On'
            else: status = 'Off'
            clientlist.append(entry[0] + " on port " + str(entry[1]) + " (" + status + ")")
        self.networkchoose_server.Set(clientlist)

    def PopulateSerialConfig(self, event, empty=False):
        # Populates the serial config panel
        # See if we have a previous selected item
        if self.serialselected != -1:
            self.SetSerialConfig()
        # See if we empty the panel
        if empty:
            # Disable panel
            self.port_panel.Enable(False)
            # Disable remove button
            self.serialchoose_remove.Enable(False)
            # Set empty data
            data = ' '
            conf = {'port': '', 'baudrate': ''}
        else:
            # Enable panel
            self.port_panel.Enable(True)
            # Enable remove button
            self.serialchoose_remove.Enable(True)
            # Set selection
            self.serialselected = event.GetSelection()
            self.serialchoose_port.SetSelection(self.serialselected)
            # Get list item data
            try:
                data = self.seriallist[event.GetSelection()]
                conf = data[1]
            except IndexError:
                # Index not in self.seriallist
                return
        # Try to get config values, set default ones if missing
        enabled = self.getConfigBool(conf, 'serial_on')
        to_serial = self.getConfigBool(conf, 'send_to_serial_server')
        to_network= self.getConfigBool(conf, 'send_to_network_server')
        baudrate = conf.get('baudrate', '38400')
        xonxoff = self.getConfigBool(conf, 'xonxoff')
        rtscts = self.getConfigBool(conf, 'rtscts')
        # Update controls
        self.port_name.SetLabel(_(" Serial port ") + data[0] + _(" settings"))
        self.port_serialon.SetValue(enabled)
        self.port_sendtoserial.SetValue(to_serial)
        self.port_sendtonetwork.SetValue(to_network)
        self.port_port.SetValue(conf['port'])
        self.port_speed.SetValue(baudrate)
        self.port_xonxoff.SetValue(xonxoff)
        self.port_rtscts.SetValue(rtscts)

    def PopulateNetworkConfig(self, event, empty=False):
        # Populates the serial config panel
        # See if we have a previous selected item
        if self.networkselected != -1:
            self.SetNetworkConfig()
        # See if we empty the panel
        if empty:
            # Disable panel
            self.netrec_panel.Enable(False)
            # Disable remove button
            self.networkchoose_remove.Enable(False)
            # Set empty data
            data = ['', 0, False, False, False]
        else:
            # Enable panel
            self.netrec_panel.Enable(True)
            # Enable remove button
            self.networkchoose_remove.Enable(True)
            # Set selection
            self.networkselected = event.GetSelection()
            self.networkchoose_server.SetSelection(self.networkselected)
            # Get list item data
            try:
                data = self.networklist[event.GetSelection()]
            except IndexError:
                # Index not in self.networklist
                return
        # Update controls
        self.netrec_clienton.SetValue(data[2])
        self.netrec_sendtoserial.SetValue(data[3])
        self.netrec_sendtonetwork.SetValue(data[4])
        self.netrec_clientaddress.SetValue(data[0])
        self.netrec_clientport.SetValue(data[1])

    def SetSerialConfig(self):
        # Reads data in the serial conf widget and sets self.seriallist
        # Set temp dict
        temp = {}
        # Get data from controls
        temp['serial_on'] = self.port_serialon.GetValue()
        temp['send_to_serial_server'] = self.port_sendtoserial.GetValue()
        temp['send_to_network_server'] = self.port_sendtonetwork.GetValue()
        temp['port'] = self.port_port.GetValue()
        temp['baudrate'] = self.port_speed.GetValue()
        temp['xonxoff'] = self.port_xonxoff.GetValue()
        temp['rtscts'] = self.port_rtscts.GetValue()
        # Update list
        self.seriallist[self.serialselected][1] = temp.copy()
        # Update listbox
        self.UpdateSerialList()
        
    def SetNetworkConfig(self):
        # Reads data in the network client conf widget and sets
        # self.networklist
        # Set temp list
        temp = [False, False, False, False, False]
        # Get data from controls
        temp[2] = self.netrec_clienton.GetValue()
        temp[3] = self.netrec_sendtoserial.GetValue()
        temp[4] = self.netrec_sendtonetwork.GetValue()
        temp[0] = self.netrec_clientaddress.GetValue()
        temp[1] = self.netrec_clientport.GetValue()
        # Update list
        self.networklist[self.networkselected] = temp
        # Update listbox
        self.UpdateNetworkList()

    def OnSerialRemove(self, event):
        # Removes an item in the serial listbox
        # Ask user if he/she insits
        dlg = wx.MessageDialog(self, _("Are you sure you want to remove the selected serial port entry?"), _("Confirm removal"), wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            # Remove port from list
            del self.seriallist[self.serialselected]
            # Set no selection
            self.serialselected = -1
            # Update listbox
            self.UpdateSerialList()
            # Set panel to empty
            self.PopulateSerialConfig(None, empty=True)
        dlg.Destroy()

    def OnNetworkRemove(self, event):
        # Removes an item in the network listbox
        # Ask user if he/she insits
        dlg = wx.MessageDialog(self, _("Are you sure you want to remove the selected server entry?"), _("Confirm removal"), wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            # Remove server from list
            del self.networklist[self.networkselected]
            # Set no selection
            self.networkselected = -1
            # Update listbox
            self.UpdateNetworkList()
            # Set panel to empty
            self.PopulateNetworkConfig(None, empty=True)
        dlg.Destroy()

    def OnSerialInsert(self, event):
        # Inserts an item in the serial listbox
        # See if we have a previous selected item
        if self.serialselected != -1:
            self.SetSerialConfig()
        # Get current port names in self.seriallist
        ports = [port[0] for port in self.seriallist]
        # Iterate over alphabet, compare to current port names and
        # set nextchr to next available
        for c in string.lowercase:
            if not 'serial_' + c in ports:
                nextchr = c
                break
        # Insert new item in list
        self.seriallist.append(['serial_'+c, {'serial_on': True, 'port': '', 'send_to_serial_server': True, 'send_to_network_server': True}])
        # Set selection to empty
        self.serialselected = -1
        # Update listbox
        self.UpdateSerialList()
        # Set selected to new port (ugly hack)
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_LISTBOX_SELECTED, -1)
        evt.GetSelection = lambda: len(self.seriallist) - 1
        self.PopulateSerialConfig(evt)

    def OnNetworkInsert(self, event):
        # Inserts an item in the network listbox
        # See if we have a previous selected item
        if self.networkselected != -1:
            self.SetNetworkConfig()
        # Insert new item in list
        self.networklist.append(['', 0, True, True, True])
        # Set selection to empty
        self.networkselected = -1
        # Update listbox
        self.UpdateNetworkList()
        # Set selected to new port (ugly hack)
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_LISTBOX_SELECTED, -1)
        evt.GetSelection = lambda: len(self.networklist) - 1
        self.PopulateNetworkConfig(evt)

    def UpdateListColumns(self):
        # Take all possible columns from columnsetup
        allcolumns = set(columnsetup.keys())
        # Create a list of differences between all possible columns and the active columns
        possible = list(allcolumns.difference(self.listcolumns_as_list))
        # Update list boxes
        self.listcolumn_active.Set(self.listcolumns_as_list)
        self.listcolumn_notactive.Set(possible)

    def UpdateAlertListColumns(self):
        # Take all possible columns from columnsetup
        allcolumns = set(columnsetup.keys())
        # Create a list of differences between all possible columns and the active columns
        possible = list(allcolumns.difference(self.alertlistcolumns_as_list))
        # Update list boxes
        self.alertlistcolumn_active.Set(self.alertlistcolumns_as_list)
        self.alertlistcolumn_notactive.Set(possible)

    def OnColumnChange(self, event):
        # Map objects depending on pressed button
        if wx.Event.GetId(event) >= 50 and wx.Event.GetId(event) < 60:
            listcolumn_list = self.listcolumns_as_list
            notactive = self.listcolumn_notactive
            selection_notactive = notactive.GetStringSelection()
            active = self.listcolumn_active
            selection_active = active.GetStringSelection()
        if wx.Event.GetId(event) >= 60 and wx.Event.GetId(event) < 70:
            listcolumn_list = self.alertlistcolumns_as_list
            notactive = self.alertlistcolumn_notactive
            selection_notactive = notactive.GetStringSelection()
            active = self.alertlistcolumn_active
            selection_active = active.GetStringSelection()
        # Move a column from non-active to active listbox
        if (wx.Event.GetId(event) == 50 or wx.Event.GetId(event) == 60) and len(selection_notactive) > 0:
            listcolumn_list.append(selection_notactive)
        # Move a column from active to non-active listbox
        elif (wx.Event.GetId(event) == 51 or wx.Event.GetId(event) == 61) and len(selection_active) > 0:
            listcolumn_list.remove(selection_active)
        # Move a column upwards in the active listbox
        elif (wx.Event.GetId(event) == 52 or wx.Event.GetId(event) == 62) and len(selection_active) > 0:
            # Get index number in listbox
            original_number = listcolumn_list.index(selection_active)
            # Check that column not is first in listbox
            if original_number > 0:
                # Remove the column
                listcolumn_list.remove(selection_active)
                # Insert the column at the previous position - 1
                listcolumn_list.insert((original_number-1), selection_active)
        # Move a column downwards in the active listbox
        elif (wx.Event.GetId(event) == 53 or wx.Event.GetId(event) == 63) and len(selection_active) > 0:
            # Get index number in listbox
            original_number = listcolumn_list.index(selection_active)
            # Remove the column
            listcolumn_list.remove(selection_active)
            # Insert the column at the previous position + 1
            listcolumn_list.insert((original_number+1), selection_active)
        # Update all columns to reflect eventual changes
        self.UpdateListColumns()
        self.UpdateAlertListColumns()
        # Make sure a moved item in the acive listbox stays selected
        active.SetStringSelection(selection_active)

    def OnLogFileDialog(self, event):
        try: self.filelog_logfile.SetValue(self.FileDialog(_("Choose log file"), _("Log file (*.db)|*.db|All files (*)|*"), config['logging']['logfile']))
        except: return

    def OnIDDBFileDialog(self, event):
        try: self.iddblog_logfile.SetValue(self.FileDialog(_("Choose IDDB file)"), _("ID database file (*.idb)|*.idb|All files (*)|*"), config['iddb_logging']['logfile']))
        except: return

    def OnAlertFileDialog(self, event):
        try: self.alertfile_file.SetValue(self.FileDialog(_("Choose alert/remark file"), _("Alert file (*.alt)|*.alt|All files (*)|*"), config['alert']['remarkfile']))
        except: return

    def OnAlertSoundFileDialog(self, event):
        try: self.alertsoundfile_file.SetValue(self.FileDialog(_("Choose sound alert file"), _("Wave file (*.wav)|*.wav|All files (*)|*"), config['alert']['alertsoundfile']))
        except: return

    def OnMapFileDialog(self, event):
        try: self.mapfile_file.SetValue(self.FileDialog(_("Choose map file"), _("MapGen file (*.dat)|*.dat|All files (*)|*"), config['map']['mapfile']))
        except: return

    def FileDialog(self, label, wc, df):
        # Create a file dialog
        open_dlg = wx.FileDialog(self, label, wildcard=wc, defaultFile=os.path.normpath(df))
        # If user pressed open, update text control
        if open_dlg.ShowModal() == wx.ID_OK:
            return(unicode(open_dlg.GetPath()))

    def UpdateConfig(self):
        # Update the config dictionary with data from the window
        config['common']['listmakegreytime'] =  self.commonlist_greytime.GetValue()
        config['common']['deleteitemtime'] =  self.commonlist_deletetime.GetValue()
        config['common']['updatetime'] = self.commonlist_updatetime.GetValue()
        config['common']['showafterupdates'] =  self.commonlist_showafterupdates.GetValue()
        config['common']['showclassbstations'] = self.commonlist_classbtoggle.GetValue()
        config['common']['showbasestations'] = self.commonlist_basestationtoggle.GetValue()
        if self.manualpos_format.GetSelection() == 0:
            config['position']['position_format'] = 'dd'
        elif self.manualpos_format.GetSelection() == 1:
            config['position']['position_format'] = 'dm'
        else:
            config['position']['position_format'] = 'dms'
        config['position']['use_position_from'] = self.manualpos_datasource.GetValue()
        config['position']['override_on'] = self.manualpos_overridetoggle.GetValue()
        # Get own position
        latdeg = self.manualpos_latdeg.GetValue()
        latmin = self.manualpos_latmin.GetValue()
        latsec = self.manualpos_latsec.GetValue()
        if self.manualpos_latquad.GetValue() == 'N':
            lat = "%.5f" %(float(latdeg) + float(latmin) / 60 + float(latsec) / 3600)
        elif self.manualpos_latquad.GetValue() == 'S':
            lat = "%.5f" %(-float(latdeg) - float(latmin) / 60 - float(latsec) / 3600)
        longdeg = self.manualpos_longdeg.GetValue()
        longmin = self.manualpos_longmin.GetValue()
        longsec = self.manualpos_longsec.GetValue()
        if self.manualpos_longquad.GetValue() == 'E':
            long = "%.5f" %(float(longdeg) + float(longmin) / 60 + float(longsec) / 3600)
        elif self.manualpos_longquad.GetValue() == 'W':
            long = "%.5f" %(-float(longdeg) - float(longmin) / 60 - float(longsec) / 3600)
        config['position']['latitude'] = lat
        config['position']['longitude'] = long
        config['common']['listcolumns'] = ', '.join(self.listcolumns_as_list)
        config['common']['alertlistcolumns'] = ', '.join(self.alertlistcolumns_as_list)
        # Serial client config
        # Get all ports currently starting with serial
        ports = [ port for port in config.iterkeys()
                  if port.find('serial') != -1 ]
        # Iterate over ports and delete them all
        for port in ports:
            if port == 'serial_server': continue
            del config[port]
        # Iterate over ports in self.seriallist and set config
        for port in self.seriallist:
            config[port[0]] = port[1]
        # Network client config
        client_addresses = []; clients_enabled = []; clients_to_serial = []; clients_to_server = []
        for client in self.networklist:
            address = client[0]+':'+str(client[1])
            client_addresses.append(address)
            if client[2]: clients_enabled.append(address)
            if client[3]: clients_to_serial.append(address)
            if client[4]: clients_to_server.append(address)
        config['network']['client_addresses'] = ','.join(client_addresses)
        config['network']['clients_on'] = ','.join(clients_enabled)
        config['network']['clients_to_serial'] = ','.join(clients_to_serial)
        config['network']['clients_to_server'] = ','.join(clients_to_server)
        config['network']['server_on'] = self.netsend_serveron.GetValue()
        config['network']['server_address'] = self.netsend_serveraddress.GetValue()
        config['network']['server_port'] = self.netsend_serverport.GetValue()
        config['logging']['logging_on'] = self.filelog_logtoggle.GetValue()
        config['logging']['logbasestations'] = self.filelog_logbasestationstoggle.GetValue()
        config['logging']['logtime'] = self.filelog_logtime.GetValue()
        config['logging']['logfile'] = self.filelog_logfile.GetValue()
        config['logging']['logexceptions'] = self.exceptionlog_logtoggle.GetValue()
        config['iddb_logging']['logging_on'] = self.iddblog_logtoggle.GetValue()
        config['iddb_logging']['logtime'] = self.iddblog_logtime.GetValue()
        config['iddb_logging']['logfile'] = self.iddblog_logfile.GetValue()
        config['alert']['remarkfile_on'] = self.alertfile_toggle.GetValue()
        config['alert']['remarkfile'] = self.alertfile_file.GetValue()
        config['alert']['alertsound_on'] = self.alertsoundfile_toggle.GetValue()
        config['alert']['alertsoundfile'] = self.alertsoundfile_file.GetValue()
        config['alert']['maxdistance_on'] = self.alertdistance_toggle.GetValue()
        config['alert']['maxdistance'] = self.alertdistance_distance.GetValue()
        config['map']['mapfile'] = self.mapfile_file.GetValue()
        config['map']['background_color'] = self.mapcolor_background.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)
        config['map']['shoreline_color'] = self.mapcolor_shoreline.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)
        config['map']['object_color'] = self.mapcolor_object.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)
        config['map']['old_object_color'] = self.mapcolor_old.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)
        config['map']['selected_object_color'] = self.mapcolor_selected.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)
        config['map']['alerted_object_color'] = self.mapcolor_alerted.GetColour().GetAsString(wx.C2S_CSS_SYNTAX)

    def OnSave(self, event):
        # Create file dialog
        wcd = _("ini files (*.ini)|*.ini")
        save_dlg = wx.FileDialog(self, message=_("Choose file to save configuration to"), defaultFile=os.path.join(package_home(globals()), config.filename), wildcard=wcd, style=wx.SAVE)
        if save_dlg.ShowModal() == wx.ID_OK and len(save_dlg.GetPath()) > 0:
            # Ensure good config state
            self.BeforeSerialAndNetworkSave()
            # Update and save program config
            self.UpdateConfig()
            try:
                # Write config
                config.filename = unicode(save_dlg.GetPath())
                config.write()
            except:
                logging.error("Could not save configuration to file", exc_info=True)
                return
            save_dlg.Destroy()
            # Display warning
            dlg = wx.MessageDialog(self, _("Your settings have been saved, but the program can only make use of some changed settings when running.\n\nPlease restart the program to be able to use all the updated settings."), 'Please restart', wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()

    def OnApply(self, event):
        # Ensure good config state
        self.BeforeSerialAndNetworkSave()
        # Update program config
        self.UpdateConfig()
        dlg = wx.MessageDialog(self, _("The program can only make use of some changed settings when running.\n\nPlease save your changes and restart the program to be able to use all the updated settings."), 'WARNING', wx.OK | wx.ICON_WARNING)
        dlg.ShowModal()
        dlg.Destroy()

    def BeforeSerialAndNetworkSave(self):
        # This function ensures that the config options currently
        # displayed is used and clears the serial and network
        # config windows
        # Update serial
        # See if we have a selected item
        if self.serialselected != -1:
            self.SetSerialConfig()
        # Set no selection
        self.serialselected = -1
        # Update listbox
        self.UpdateSerialList()
        # Set panel to empty
        self.PopulateSerialConfig(None, empty=True)
        # Update network
        # See if we have a selected item
        if self.networkselected != -1:
            self.SetNetworkConfig()
        # Set no selection
        self.networkselected = -1
        # Update listbox
        self.UpdateNetworkList()
        # Set panel to empty
        self.PopulateNetworkConfig(None, empty=True)

    def OnAbort(self, event):
        self.Destroy()

    def getConfigBool(self, conf, key):
        # Try to get a particular config key as a bool, return
        # False if the key doesn't exist
        try:
            return conf.as_bool(key)
        except AttributeError:
            return conf.get(key, False)
        except:
            return False

class RawDataWindow(wx.Dialog):
    def __init__(self, parent, id):
        wx.Dialog.__init__(self, parent, id, title=_("Raw data"))#, size=(618,395))
        panel = wx.Panel(self, -1)
        wx.StaticBox(panel,-1,_(" Incoming raw data "),pos=(3,5),size=(915,390))
        # Create the textbox
        self.textbox = wx.TextCtrl(panel,-1,pos=(15,25),size=(895,355),style=(wx.TE_MULTILINE | wx.TE_READONLY))
        # Buttons
        self.pausebutton = wx.ToggleButton(self,1,_("&Pause"), size=(-1,35))
        self.pause = False
        self.closebutton = wx.Button(self,2,_("&Close"), size=(-1,35))

        # Sizers
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(panel, 1, wx.EXPAND, 0)
        sizer.AddSpacer((0,10))
        sizer.Add(sizer2, flag=wx.ALIGN_RIGHT)
        sizer2.Add(self.pausebutton, 0)
        sizer2.AddSpacer((150,0))
        sizer2.Add(self.closebutton, 0)
        self.SetSizerAndFit(sizer)

        # Events
        self.Bind(wx.EVT_TOGGLEBUTTON, self.OnPause, id=1)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=2)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def Update(self, data):
        updatetext = ''
        # Get data and add string to updatetext (make sure it's ascii)
        for line in data:
            sentence = unicode(line[3], 'ascii', 'replace').rstrip('\r\n')
            updatetext += sentence + '  => message ' + str(line[1]) + ', mmsi ' + str(line[2]) + ', source ' + str(line[0]) + '\n'
        # Write updatetext from the top of the box
        self.textbox.SetInsertionPoint(0)
        self.textbox.WriteText(updatetext)
        # Get total number of characters in box
        numberofchars = self.textbox.GetLastPosition()
        # Remove all characters over the limit (at the bottom)
        if numberofchars > 20000:
            self.textbox.Remove(20000, numberofchars)
            self.textbox.ShowPosition(0)

    def SetData(self, data):
        # If not paused, update
        if not self.pause:
            self.Update(data)

    def OnPause(self, event):
        # Set pause to togglebutton value
        self.pause = self.pausebutton.GetValue()

    def OnClose(self, event):
        self.Destroy()


class PositionConversion(object):
    # Makes position conversions from position in a DD format
    # to human-readable strings in DD, DM or DMS format
    # Input must be of type decimal.Decimal
    def __init__(self, lat, long):
        self.latitude = lat
        self.longitude = long

    @property
    def default(self):
        # Extract the format we should use from configuration, and
        # return the right function
        format = config['position']['position_format'].lower()
        if format == 'dms':
            return self.dms
        elif format == 'dm':
            return self.dm
        elif format == 'dd':
            return self.dd

    @property
    def dd(self):
        # Return a human-readable DD position
        if self.latitude > 0:
            lat = str(abs(self.latitude)) + u'°N'
        elif self.latitude < 0:
            lat = str(abs(self.latitude)) + u'°S'
        if self.longitude > 0:
            long = str(abs(self.longitude)) + u'°E'
        elif self.longitude < 0:
            long = str(abs(self.longitude)) + u'°W'
        return lat, long

    @property
    def dm(self):
        # Return a human-readable DM position
        latdegree = int(self.latitude)
        longdegree = int(self.longitude)
        latmin = (self.latitude - latdegree) * 60
        longmin = (self.longitude - longdegree) * 60
        if self.latitude > 0:
            lat = u"%(deg)02d° %(min)07.4f'N" %{'deg': abs(latdegree), 'min': abs(latmin)}
        elif self.latitude < 0:
            lat = u"%(deg)02d° %(min)07.4f'S" %{'deg': abs(latdegree), 'min': abs(latmin)}
        if self.longitude > 0:
            long = u"%(deg)03d° %(min)07.4f'E" %{'deg': abs(longdegree), 'min': abs(longmin)}
        elif self.longitude < 0:
            long = u"%(deg)03d° %(min)07.4f'W" %{'deg': abs(longdegree), 'min': abs(longmin)}
        return lat, long

    @property
    def dms(self):
        # Return a human-readable DMS position
        latdegree = int(self.latitude)
        longdegree = int(self.longitude)
        latmin = (self.latitude - latdegree) * 60
        longmin = (self.longitude - longdegree) * 60
        latsec = (latmin - int(latmin)) * 60
        longsec = (longmin - int(longmin)) * 60
        if self.latitude > 0:
            lat = u"%(deg)02d° %(min)02d' %(sec)05.2f''N" %{'deg': abs(latdegree), 'min': abs(latmin), 'sec': abs(latsec)}
        elif self.latitude < 0:
            lat = u"%(deg)02d° %(min)02d' %(sec)05.2f''S" %{'deg': abs(latdegree), 'min': abs(latmin), 'sec': abs(latsec)}
        if self.longitude > 0:
            long = u"%(deg)03d° %(min)02d' %(sec)05.2f''E" %{'deg': abs(longdegree), 'min': abs(longmin), 'sec': abs(longsec)}
        elif self.longitude < 0:
            long = u"%(deg)03d° %(min)02d' %(sec)05.2f''W" %{'deg': abs(longdegree), 'min': abs(longmin), 'sec': abs(longsec)}
        return lat, long


class GUI(wx.App):
    def OnInit(self):
        self.frame = MainWindow(None, -1, 'AIS Logger')
        self.frame.Show(True)
        return True

    def GetFrame(self):
        return self.frame


class SerialThread:
    queue = Queue.Queue()
    # Define a queue for inserting data to send
    comqueue = Queue.Queue(500)

    def reader(self, name, s):
        # Set empty queueitem
        queueitem = ''
        # Start loop
        while True:
            # See if we shall stop
            try:
                queueitem = self.queue.get_nowait()
            # If no data in queue, sleep (prevents 100% CPU drain)
            except Queue.Empty:
                time.sleep(0.001)
            if queueitem == 'stop':
                s.close()
                break

            data = ''
            try:
                # Try to read data from serial port
                data = s.readline()
            except serial.SerialException:
                # On timeout or other errors, reopen port
                logging.debug("%(port)s timed out" %{'port': name}, exc_info=True)
                s.close()
                s.open()
                time.sleep(1)
                continue

            # If data contains raw data, pass it along
            try:
                if data[0] == '!' or data[0] == '$':
                    # Put it in CommHubThread's queue
                    comm_hub_thread.put([name,data])
            except IndexError:
                pass


    def server(self):
        # See if we should act as a serial server
        if config['serial_server'].as_bool('server_on'):
            port = config['serial_server']['port']
            baudrate = config['serial_server']['baudrate']
            rtscts = config['serial_server']['rtscts']
            xonxoff = config['serial_server']['xonxoff']
            try:
                serial_server = serial.Serial(port, baudrate, rtscts=rtscts, xonxoff=xonxoff, timeout=5)
            except serial.SerialException:
                logging.error("Could not open serial port %(port)s to act as a serial server" %{'port': port}, exc_info=True)
                return False
        else:
            # Server is not on, exit thread
            return False
        # Set empty queueitem
        queueitem = ''
        # Start loop
        while True:
            # See if we shall stop
            try:
                queueitem = self.queue.get_nowait()
            # If no data in queue, sleep (prevents 100% CPU drain)
            except Queue.Empty:
                time.sleep(0.1)
            if queueitem == 'stop':
                serial_server.flushOutput()
                serial_server.close()
                break
            # Do we have carrier?
            if serial_server.getCD():
                lines = []
                # Try to get data from queue
                while True:
                    try:
                        lines.append(self.comqueue.get_nowait())
                    except Queue.Empty:
                        break
                # Write to port
                try:
                    serial_server.write(''.join(lines))
                except serial.SerialException:
                    # Don't handle error, port should be open
                    pass
        
    def ReturnStats(self):
        return self.stats

    def put(self, item):
        self.queue.put(item)

    def put_send(self, item):
        try:
            self.comqueue.put_nowait(item)
        except Queue.Full:
            self.comqueue.get_nowait()
            self.comqueue.put_nowait(item)

    def start(self):
        try:
            # Fire off server thread
            server = threading.Thread(target=self.server)
            server.setDaemon(1)
            server.start()

            # See what reader threads we should start
            # Get all entries in config starting with 'serial'
            conf_ports = [ port for port in config.iterkeys()
                      if port.find('serial') != -1 ]
            # Iterate over ports and set port data
            for port_data in conf_ports:
                # Don't send serial data from server to itself...
                if port_data == 'serial_server':
                    continue
                # Get config
                conf = config[port_data]
                # Ok, set up port
                if 'serial_on' in conf and conf.as_bool('serial_on') and 'port' in conf:
                    # Try to get these values, if not, use standard
                    baudrate = 38400
                    rtscts = False
                    xonxoff = False
                    try:
                        # Baudrate
                        baudrate = conf.as_int('baudrate')
                        # RTS/CTS
                        rtscts = conf.as_bool('rtscts')
                        # XON/XOFF
                        xonxoff = conf.as_bool('xonxoff')
                    except: pass
                    # Create port name (the part after 'serial_')
                    portname = 'Serial port ' + port_data[7:] + ' (' + conf['port'] + ')'
                    # OK, try to open serial port, and add to serial_ports dict
                    try:
                        s = serial.Serial(conf['port'], baudrate, rtscts=rtscts, xonxoff=xonxoff, timeout=60)
                    except serial.SerialException:
                        logging.error("Could not open serial port %(port)s to read data from" %{'port': conf['port']}, exc_info=True)
                        continue
                    # Fire off reader thread
                    read = threading.Thread(target=self.reader, args=(portname, s))
                    read.setDaemon(1)
                    read.start()
            return True
        except:
            return False

    def stop(self):
        # Get everything in queue and send stop string
        try:
            while True:
                self.queue.get_nowait()
        except Queue.Empty:
            try:
                while True:
                    self.comqueue.get_nowait()
            except Queue.Empty:
                for i in range(0,100):
                    self.put('stop')
                    self.put_send('stop')


class NetworkServerThread:
    # Define a queue for inserting data to send
    comqueue = Queue.Queue(500)

    class NetworkClientHandler(SocketServer.BaseRequestHandler):
        def handle(self):
            message = ''
            # Define an instance collection
            self.indata = collections.deque()
            # Notify the NetworkFeeder that we have liftoff...
            NetworkServerThread().put(('started', self))
            while True:
                try:
                    # Try to pop message from the collection
                    message = self.indata.popleft()
                except IndexError:
                    # If no data in collection, sleep (prevents 100% CPU drain)
                    time.sleep(0.05)
                    continue
                except: pass
                # If someone tells us to stop, stop.
                if message == 'stop': break
                # If message length is > 1, send message to socket
                if len(message) > 1:
                    try:
                        self.request.send(str(message))
                    except:
                        break
            # Stop, please.
            NetworkServerThread().put(('stopped', self))
            self.indata.clear()
            self.request.close()


    def server(self):
        # Spawn network servers as clients request connection
        server_address = config['network']['server_address']
        server_port = config['network'].as_int('server_port')
        try:
            server = SocketServer.ThreadingTCPServer((server_address, server_port), self.NetworkClientHandler)
            server.serve_forever()
        except:
            logging.error("Could not start the network server on address %(address)s and port %(port)s" %{'address': server_address, 'port': server_port}, exc_info=True)

    def feeder(self):
        # This function tracks each server thread and feeds them
        # with data from the queue
        queueitem = ''
        servers = []
        while True:
            try:
                queueitem = self.comqueue.get_nowait()
                # If a server started, add to servers
                if queueitem[0] == 'started':
                    servers.append(queueitem[1])
                # If a server stopped, remove from servers
                elif queueitem[0] == 'stopped':
                    servers.remove(queueitem[1])
                # If someone wants to stop us, send stop to servers
                elif queueitem == 'stop':
                    for server in servers:
                        for i in range(0,100):
                            server.indata.append('stop')
                    break
            # If no data in queue, sleep (prevents 100% CPU drain)
            except Queue.Empty:
                time.sleep(0.05)
                continue
            # If something in queue, but not in form of a list, pass
            except IndexError: pass

            # If queueitem length is > 1, send message to socket
            if len(queueitem) > 1:
                for server in servers:
                    server.indata.append(queueitem)

    def start(self):
        try:
            feeder = threading.Thread(target=self.feeder, name='NetworkFeeder')
            feeder.setDaemon(1)
            feeder.start()
            server = threading.Thread(target=self.server, name='NetworkServer')
            server.setDaemon(1)
            server.start()
            return True
        except:
            return False

    def stop(self):
        # Get everything in queue and send stop string
        try:
            while True:
                self.comqueue.get_nowait()
        except Queue.Empty:
            for i in range(0,100):
                self.put('stop')

    def put(self, item):
        try:
            self.comqueue.put_nowait(item)
        except Queue.Full:
            self.comqueue.get_nowait()
            self.comqueue.put_nowait(item)


class NetworkClientThread:
    queue = Queue.Queue()

    def client(self):
        # Set empty queueitem
        queueitem = ''
        # Get config data and set empty dicts
        connection_params = config['network']['client_addresses'].replace(' ', '').split(',')
        connection_enabled = config['network']['clients_on'].replace(' ', '').split(',')
        connection_list = []
        connections = {}
        remainder = {}
        # If one of the config lists is empty, return
        if connection_params == [''] or connection_enabled == ['']:
            return
        # Build list of connections to use
        for enabled in connection_enabled:
            connection_list.extend([c for c in connection_params if enabled == c])
        # Open all connections
        for c in connection_list:
            # Split and put address in params[0] and port in params[1]
            params = c.split(':')
            # Connect
            connections[c] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # A connection has 30 seconds before it times out
            connections[c].settimeout(30)
            try:
                connections[c].connect((params[0], int(params[1])))
                # Ok we succeded... Go to non-blocking mode
                connections[c].setblocking(False)
            except socket.timeout:
                # Oops, we timed out... Close and continue
                connections[c].close()
                del connections[c]
                logging.error("The connection to the network server on address %(address)s and port %(port)s timed out." %{'address': params[0], 'port': params[1]}, exc_info=True)
                continue
            except socket.error:
                logging.error("Cannot open a connection to the network server on address %(address)s and port %(port)s." %{'address': params[0], 'port': params[1]}, exc_info=True)

        while True:
            try:
                queueitem = self.queue.get_nowait()
            except: pass
            if queueitem == 'stop':
                try:
                    for con in connections.itervalues():
                        con.close()
                except: pass
                break

            # Now iterate over the connetions
            for (name, con) in connections.iteritems():
                try:
                    # Try to read data from socket
                    data = str(con.recv(2048)).splitlines(True)
                except:
                    # Prevent CPU drain if nothing to do
                    time.sleep(0.05)
                    continue

                # See if we have data left since last read
                # If so, concat it with the first new data
                if name in remainder:
                    data[0] = remainder.pop(name) + data[0]

                # See if the last data has a line break in it
                # If not, pop it for use at next read
                listlength = len(data)
                if listlength > 0 and not data[listlength-1].endswith('\n'):
                    remainder[name] = data.pop(listlength-1)

                for indata in data:
                    # If indata contains raw data, pass it along
                    if indata[0] == '!' or indata[0] == '$':
                        # Put it in CommHubThread's queue
                        comm_hub_thread.put([name,indata])

    def put(self, item):
        self.queue.put(item)

    def start(self):
        try:
            r = threading.Thread(target=self.client)
            r.setDaemon(1)
            r.start()
            return True
        except:
            return False

    def stop(self):
        # Get everything in queue and send stop string
        try:
            while True:
                self.queue.get_nowait()
        except Queue.Empty:
            self.put('stop')


class CommHubThread:
    incoming_queue = Queue.Queue(10000)
    raw_queue = Queue.Queue(500)
    stats = {}

    def runner(self):
        # The routing matrix consists of a dict with key 'input'
        # and value 'output list'
        routing_matrix = self.CreateRoutingMatrix()
        # The message parts dict has 'input' as key and
        # and a list of previous messages as value
        message_parts = {}
        # Empty incoming queue
        incoming_item = ''
        # Set the source to take position data from
        position_source = config['position']['use_position_from']
        if position_source.find('serial') != -1:
            try:
                position_source = 'Serial port ' + position_source[7:] + ' (' + config[position_source]['port'] + ')'
            except KeyError:
                logging.error("The serial port source used for GPS data (%(source)s) has no port associated with it" %{'source': position_source}, exc_info=True)
        while True:
            # Let's try to get some data in the queue
            try:
                incoming_item = self.incoming_queue.get_nowait()
            except:
                # Prevent CPU drain if nothing to do
                time.sleep(0.05)
                continue
            if incoming_item == 'stop':
                break
            # Set some variables
            source = incoming_item[0]
            data = incoming_item[1]

            # See if we got source in stats dict
            if not source in self.stats:
                self.stats[source] = {}
                self.stats[source]['received'] = 0
                self.stats[source]['parsed'] = 0

            # See if we should route the data
            outputs = routing_matrix.get(source,[])
            # Route the raw data
            for output in outputs:
                if output == 'serial':
                    serial_thread.put_send(data)
                elif output == 'network':
                    network_server_thread.put(data)

            # Check if message is split on several lines
            lineinfo = data.split(',')
            if lineinfo[0] == '!AIVDM':
                try:
                    nbr_of_lines = int(lineinfo[1])
                except: continue
                try:
                    line_nbr = int(lineinfo[2])
                    line_seq_id = int(lineinfo[3])
                except: pass
                # If message is split, check that they belong together
                if nbr_of_lines > 1:
                    # Get previous parts if they exist
                    parts = message_parts.get(source)
                    if parts:
                        seq_id = parts[0]
                        total_data = parts[1]
                    else:
                        seq_id = 10
                        total_data = ''
                    # If first message, set seq_id to the sequential message ID
                    if line_nbr == 1:
                        total_data = ''
                        seq_id = line_seq_id
                    # If not first message, check that the seq ID matches seq_id
                    # If not true, reset variables and continue
                    elif line_seq_id != seq_id:
                        message_parts[source] = [10, '']
                        continue
                    # Add data to variable total_data
                    total_data += data
                    # If the final message has been received, join messages and decode
                    if len(total_data.splitlines()) == nbr_of_lines:
                        data = decode.jointelegrams(total_data)
                        message_parts[source] = [10, '']
                    else:
                        message_parts[source] = [seq_id, total_data]
                        continue

            # Set the telegramparser result in dict parser and queue it
            try:
                # Add one to stats dict
                self.stats[source]['received'] += 1
                # Parse data
                #print(data)
                parser = dict(decode.telegramparser(data))
                # Set source in parser
                parser['source'] = source
                # See if we should send it, and if so: do it!
                if 'mmsi' in parser:
                    # Send data to main thread
                    main_thread.put(parser)
                    # Add to stats dict if we have decoded message
                    # (see if 'decoded' is True)
                    if parser.get('decoded',True):
                        self.stats[source]['parsed'] += 1
                # See if we have a position and if we should use it
                elif 'ownlatitude' in parser and 'ownlongitude' in parser:
                    #print('Found Ownship Info: ' + position_source)
                    if position_source.lower() == 'any' or position_source == source:
                        # Send data to main thread
                        main_thread.put(parser)
                        # Add to stats dict
                        self.stats[source]['parsed'] += 1

                # Send raw data to the Raw Window queue
                raw_mmsi = parser.get('mmsi','N/A')
                raw_message = parser.get('message','N/A')
                # Append source, message number, mmsi and data to rawdata
                raw = [source, raw_message, raw_mmsi, data]
                # Add the raw line to the raw queue
                try:
                    self.raw_queue.put_nowait(raw)
                except Queue.Full:
                    self.raw_queue.get_nowait()
                    self.raw_queue.put_nowait(raw)
            except: continue

    def CreateRoutingMatrix(self):
        # Creates a routing matrix dict from the set config options

        # Define the matrix
        matrix = {}

        # Get network config options
        clients_to_serial = config['network']['clients_to_serial'].replace(' ', '').split(',')
        clients_to_server = config['network']['clients_to_server'].replace(' ', '').split(',')

        # Add to matrix
        for network_source in clients_to_serial:
            if network_source:
                send_list = matrix.get(network_source,[])
                send_list.append('serial')
                matrix[network_source] = send_list
        for network_source in clients_to_server:
            if network_source:
                send_list = matrix.get(network_source,[])
                send_list.append('network')
                matrix[network_source] = send_list

        # Get serial config options
        conf_ports = [ port for port in config.iterkeys()
                       if port.find('serial') != -1 ]

        # Iterate over configured ports
        for port in conf_ports:
            if 'port' in config[port]:
                # Try to create port name (the part after 'serial_')
                try:
                    portname = 'Serial port ' + port[7:] + ' (' + config[port]['port'] + ')'
                except: continue
                # Add to serial server send list
                try:
                    if config[port].as_bool('send_to_serial_server'):
                        send_list = matrix.get(portname,[])
                        send_list.append('serial')
                        matrix[portname] = send_list
                except: pass
                # Add to network server send list
                try:
                    if config[port].as_bool('send_to_network_server'):
                        send_list = matrix.get(portname,[])
                        send_list.append('network')
                        matrix[portname] = send_list
                except: pass

        return matrix

    def ReturnStats(self):
        return self.stats

    def ReturnRaw(self):
        # Return all data in the raw queue
        temp = []
        while True:
            try:
                temp.append(self.raw_queue.get_nowait())
            except Queue.Empty:
                break
        return temp
            
    def put(self, item):
        try:
            self.incoming_queue.put_nowait(item)
        except Queue.Full:
            self.incoming_queue.get_nowait()
            self.incoming_queue.put_nowait(item)

    def start(self):
        try:
            r = threading.Thread(target=self.runner)
            r.setDaemon(1)
            r.start()
            return True
        except:
            return False

    def stop(self):
        # Get everything in queue and send stop string
        try:
            while True:
                self.incoming_queue.get_nowait()
        except Queue.Empty:
            self.put('stop')


class MainThread:
    # Create an incoming and an outgoing queue
    # Set a limit on how large the outgoing queue can get
    queue = Queue.Queue(1000)
    outgoing = Queue.Queue(1000)

    def __init__(self):
        # Set an empty incoming dict
        self.incoming_packet = {}

        # Define a dict to store the metadata hashes
        self.hashdict = {}

        # Define a dict to store own position data in
        self.ownposition = {}
        self.ownmmsi = 1

        # Define a dict to store remarks/alerts in
        self.remarkdict = {}

        # See if we should set a fixed manual position
        if config['position'].as_bool('override_on'):
            ownlatitude = decimal.Decimal(config['position']['latitude'])
            ownlongitude = decimal.Decimal(config['position']['longitude'])
            try:
                owngeoref = georef(ownlatitude,ownlongitude)
            except:
                owngeoref = None
            self.ownposition.update({'ownlatitude': ownlatitude, 'ownlongitude': ownlongitude, 'owngeoref': owngeoref, 'owntime': datetime.datetime.now(), 'ownsog': 0, 'owncog': 0})

        # Create main database
        self.db_main = pydblite.Base('dummy')
        self.dbfields = ('mmsi', 'mid', 'imo',
                         'name', 'type', 'typename',
                         'callsign', 'latitude', 'longitude',
                         'georef', 'creationtime', 'time',
                         'sog', 'cog', 'heading',
                         'destination', 'eta', 'length',
                         'width', 'draught', 'rot',
                         'navstatus', 'posacc', 'distance',
                         'bearing', 'source', 'transponder_type'
                         'old', 'soundalerted')
        self.db_main.create(*self.dbfields, mode="override")
        self.db_main.create_index('mmsi')

        # Create ID database
        self.db_iddb = pydblite.Base('dummy2')
        self.db_iddb.create('mmsi', 'imo', 'name', 'callsign', mode="override")
        self.db_iddb.create_index('mmsi')

        # Try to load ID database
        self.loadiddb()

        # Try to load remark file
        self.loadremarkfile()

    def DbUpdate(self, incoming_packet):
        self.incoming_packet = incoming_packet
        incoming_mmsi = self.incoming_packet['mmsi']
        new = False

        # Fetch the current data in DB for MMSI (if exists)
        currentdata = self.db_main._mmsi[incoming_mmsi]

        # Define a dictionary to hold update data
        update_dict = {}

        # Check if report needs special treatment
        if 'message' in self.incoming_packet:
            message = self.incoming_packet['message']
            # If message type 1, 2 or 3 (Mobile Position Report) or
            # message type 5 (Static and Voyage Related Data):
            if message == '1' or message == '2' or message == '3' or message == '5':
                update_dict['transponder_type'] = 'A'
            # If message type S02 (Standard Position), S0E (Identification)
            # or S0F (Vessel Data):
            elif message == 'S02' or message == 'S0E' or message == 'S0F':
                update_dict['transponder_type'] = 'A'
            # If message type 4 (Base Station Report):
            elif message == '4':
                update_dict['transponder_type'] = 'base'
            # If message type 18, 19 or 24 (Class B messages):
            elif message == '18' or message == '19' or message == '24':
                update_dict['transponder_type'] = 'B'
            # Abort insertion if message type 9 (Special Position
            # Report), or type S0D and S11 (aviation reports)
            elif message == '9' or message == 'S0D' or message == 'S11':
                return None
            # FIXME: Should we just throw the rest of these messages?
            else:
                return None

        # If not currently in DB, add the mmsi number, creation time and MID code
        if len(currentdata) == 0:
            # Set variable to indicate a new object
            new = True
            # Map MMSI nbr to nation from MID list
            if 'mmsi' in self.incoming_packet and str(self.incoming_packet['mmsi'])[0:3] in mid:
                mid_code = mid[str(self.incoming_packet['mmsi'])[0:3]]
            else:
                mid_code = None
            self.db_main.insert(mmsi=incoming_mmsi,mid=mid_code,creationtime=self.incoming_packet['time'],
                                time=self.incoming_packet['time'])
            currentdata = self.db_main._mmsi[incoming_mmsi]

        # Get the record so that we can address it
        main_record = currentdata[0]

        # Fetch current data in IDDB
        iddb = self.db_iddb._mmsi[incoming_mmsi]

        # Can we update the IDDB (is IMO in the incoming packet?)
        if 'imo' in self.incoming_packet:
            # See if we have to insert first
            if len(iddb) == 0:
                self.db_iddb.insert(mmsi=incoming_mmsi)
                # Fetch the newly inserted entry
                iddb = self.db_iddb._mmsi[incoming_mmsi]
            # Get the record so that we can address it
            iddb_record = iddb[0]
            # Check if we have callsign or name in incoming_packet
            iddb_update = {}
            if 'callsign' in self.incoming_packet:
                iddb_update['callsign'] = self.incoming_packet['callsign']
            if 'name' in self.incoming_packet:
                iddb_update['name'] = self.incoming_packet['name']
            # Make the update
            # We know that we already have IMO, don't check for it
            self.db_iddb.update(iddb_record,imo=self.incoming_packet['imo'],**iddb_update)
            # We don't update iddb och iddb_record because there is no need, the info
            # will not be used later anyway

        # Iterate over incoming and copy matching fields to update_dict
        for key, value in self.incoming_packet.iteritems():
            if key in self.dbfields:
                # Replace any Nonetypes with string N/A
                if value == None:
                    update_dict[key] = 'N/A'
                else:
                    update_dict[key] = value

        # -- TYPENAME, GEOREF, DISTANCE, BEARING
        # Map type nbr to type name from list
        if 'type' in self.incoming_packet and self.incoming_packet['type'] > 0 and str(self.incoming_packet['type']) in typecode:
            update_dict['typename'] = typecode[str(self.incoming_packet['type'])]

        # Calculate position in GEOREF
        if 'latitude' in self.incoming_packet and 'longitude' in self.incoming_packet:
            try:
                update_dict['georef'] = georef(self.incoming_packet['latitude'],self.incoming_packet['longitude'])
            except: pass

        # Calculate bearing and distance to object
        if 'ownlatitude' in self.ownposition and 'ownlongitude' in self.ownposition and 'latitude' in self.incoming_packet and 'longitude' in self.incoming_packet:
            try:
                dist = VincentyDistance((self.ownposition['ownlatitude'],self.ownposition['ownlongitude']), (self.incoming_packet['latitude'],self.incoming_packet['longitude'])).all
                update_dict['distance'] = decimal.Decimal(str(dist['km'])).quantize(decimal.Decimal('0.1'))
                update_dict['bearing'] = decimal.Decimal(str(dist['bearing'])).quantize(decimal.Decimal('0.1'))
            except: pass

        # Filter destination field for numbers
        if 'destination' in incoming_packet:
            update_dict['destination'] = ''
            for letter in incoming_packet['destination']:
                if not letter.isdigit():
                    update_dict['destination'] += letter

        # Update the DB with new data
        self.db_main.update(main_record,old=False,**update_dict)

        # Return a dictionary of iddb
        if len(iddb) == 0:
            iddb = {}
        elif len(iddb) > 0:
            iddb = iddb[0]

        # Return the updated object and the iddb entry
        return self.db_main[main_record['__id__']].copy(), iddb.copy(), new

    def UpdateMsg(self, object_info, iddb, new=False, query=False):
        # See if we not should send message
        transponder_type = object_info.get('transponder_type',None)
        # See if we know the transponder type
        if transponder_type:
            # See if we display base stations
            if transponder_type == 'base' and not config['common'].as_bool('showbasestations'):
                return
            # See if we display Class B stations
            elif transponder_type == 'B' and not config['common'].as_bool('showclassbstations'):
                return
        else:
            # Unknown transponder type, don't display it
            return

        # See if we have enough updates
        if object_info['__version__'] < config['common'].as_int('showafterupdates'):
            return
        elif object_info['__version__'] == config['common'].as_int('showafterupdates') and query == False:
            new=True

        # Define the dict we're going to send
        message = {}

        # See if we need to use data from iddb
        if object_info['imo'] is None and 'imo' in iddb and not iddb['imo'] is None:
            object_info['imo'] = str(iddb['imo']) + "'"
        if object_info['callsign'] is None and 'callsign' in iddb and not iddb['callsign'] is None:
            object_info['callsign'] = iddb['callsign'] + "'"
        if object_info['name'] is None and 'name' in iddb and not iddb['name'] is None:
            object_info['name'] = iddb['name'] + "'"

        # Match against set alerts
        remarks = self.remarkdict.get(object_info['mmsi'], [])
        # Set initial values to False
        message['alert'] = False
        message['soundalert'] = False
        # Check if we have silent alerts or sound alerts
        if len(remarks) == 2 and remarks[0] == 'A':
            # See if we need to compare the distance to the object
            if config['alert'].as_bool('maxdistance_on'):
                if object_info['distance'] and object_info['distance'] <= config['alert'].as_int('maxdistance'):
                    message['alert'] = True
            else:
                message['alert'] = True
        elif len(remarks) == 2 and remarks[0] == 'AS':
            # See if we need to compare the distance to the object
            if config['alert'].as_bool('maxdistance_on'):
                if object_info['distance'] and object_info['distance'] <= config['alert'].as_int('maxdistance'):
                    message['alert'] = True
                else:
                    # Update the DB with soundalerted flag set to false -
                    # we want it to alert the next time the object is within range
                    main_record = self.db_main._mmsi[object_info['mmsi']][0]
                    self.db_main.update(main_record,soundalerted=False)
                if not object_info['soundalerted']:
                    message['soundalert'] = True
                    # Update the DB with soundalerted flag
                    main_record = self.db_main._mmsi[object_info['mmsi']][0]
                    self.db_main.update(main_record,soundalerted=True)
            else:
                message['alert'] = True
                # If new object, set sound alert,
                if new:
                    message['soundalert'] = True
                    # Update the DB with soundalerted flag
                    main_record = self.db_main._mmsi[object_info['mmsi']][0]
                    self.db_main.update(main_record,soundalerted=True)

        # Match against set remarks
        if len(remarks) == 2 and len(remarks[1]):
            object_info['remark'] = remarks[1]
        else:
            object_info['remark'] = None

        # Make update, insert or query message
        if new:
            message['insert'] = object_info
        elif query:
            message['query'] = object_info
        else:
            message['update'] = object_info

        # Call function to send message
        self.SendMsg(message)

    def CheckDBForOld(self):
        # Go through the DB and see if we can create 'remove' or
        # 'old' messages

        # Calculate datetime objects to compare with
        old_limit = datetime.datetime.now()-datetime.timedelta(seconds=config['common'].as_int('listmakegreytime'))
        remove_limit = datetime.datetime.now()-datetime.timedelta(seconds=config['common'].as_int('deleteitemtime'))

        # Compare objects in db against old_limit and remove_limit
        old_objects = [ r for r in self.db_main
                        if not r['old'] and r['time'] < old_limit ]
        remove_objects = [ r for r in self.db_main
                           if r['time'] < remove_limit ]

        # Mark old as old in the DB and send messages
        for object in old_objects:
            self.db_main[object['__id__']]['old'] = True
            self.SendMsg({'old': {'mmsi': object['mmsi'], 'distance': object['distance']}})
        # Delete removable objects in db
        self.db_main.delete(remove_objects)
        # Send removal messages
        for object in remove_objects:
            self.SendMsg({'remove': object['mmsi']})

    def SendMsg(self, message):
        # Puts message in queue for consumers to get
        try:
            self.outgoing.put_nowait(message)
        except Queue.Full:
            self.outgoing.get_nowait()
            self.outgoing.put_nowait(message)

    def ReturnOutgoing(self):
        # Return all messages in the outgoing queue
        templist = []
        try:
            while True:
                templist.append(self.outgoing.get_nowait())
        except Queue.Empty:
            return templist

    def Main(self):
        # Set some timers
        lastchecktime = time.time()
        lastlogtime = time.time()
        lastiddblogtime = time.time()
        incoming = {}
        # See if we should send a own position before looping
        if self.ownposition:
            self.SendMsg({'own_position': self.ownposition})
        while True:
            # Try to get the next item in queue
            try:
                incoming = self.queue.get_nowait()
            except:
                # Prevent CPU drain if nothing to do
                time.sleep(0.05)
                incoming = {}
            if incoming == 'stop': break

            # Check if incoming contains a MMSI number
            if 'mmsi' in incoming and incoming['mmsi'] > 1:
                update = self.DbUpdate(incoming)
                if update:
                    self.UpdateMsg(*update)
            # If incoming got own position data, use it
            elif 'ownlatitude' in incoming and 'ownlongitude' in incoming: #and not config['position'].as_bool('override_on'):
                ownlatitude = incoming['ownlatitude']
                ownlongitude = incoming['ownlongitude']
                owntime = incoming['time']
                ownsog = incoming['ownsog']
                owncog = incoming['owncog']
                try:
                    owngeoref = georef(ownlatitude,ownlongitude)
                except:
                    owngeoref = None
                self.ownposition.update({'ownlatitude': ownlatitude, 'ownlongitude': ownlongitude, 'owngeoref': owngeoref, 'ownsog': ownsog, 'owncog': owncog, 'owntime': owntime})
                # Send a position update
                self.SendMsg({'own_position': self.ownposition})
            # If incoming has special attributes
            elif 'query' in incoming and incoming['query'] > 0:
                # Fetch the current data in DB for MMSI
                query = self.db_main._mmsi[incoming['query']]
                # Return a dictionary of query
                if len(query) == 0:
                    query = {}
                elif len(query) > 0:
                    query = query[0]
                # Fetch current data in IDDB
                iddb = self.db_iddb._mmsi[incoming['query']]
                # Return a dictionary of iddb
                if len(iddb) == 0:
                    iddb = {}
                elif len(iddb) > 0:
                    iddb = iddb[0]
                # Send the message
                self.UpdateMsg(query, iddb, query=True)
            # If the remark/alert dict is asked for
            elif 'remarkdict_query' in incoming:
                # Send a copy of the remark/alert dict
                self.SendMsg({'remarkdict': self.remarkdict.copy()})
            # If the IDDB is asked for
            elif 'iddb_query' in incoming:
                iddb = [ r for r in self.db_iddb ]
                # Send a copy of the remark/alert dict
                self.SendMsg({'iddb': iddb})
            # If we should update our remark/alert dict
            elif 'update_remarkdict' in incoming:
                self.remarkdict = incoming['update_remarkdict']
            # If we should pass on an error to the GUI
            elif 'error' in incoming:
                self.SendMsg(incoming)

            # Remove or mark objects as old if last update time is above threshold
            if lastchecktime + 10 < time.time():
                self.CheckDBForOld()
                lastchecktime = time.time()

            # Initiate logging to disk of log time is above threshold
            if config['logging'].as_bool('logging_on'):
                if config['logging'].as_int('logtime') == 0: pass
                elif lastlogtime + config['logging'].as_int('logtime') < time.time():
                    self.dblog()
                    lastlogtime = time.time()

            # Initiate iddb logging if current time is > (lastlogtime + logtime)
            if config['iddb_logging'].as_bool('logging_on'):
                if config['iddb_logging'].as_int('logtime') == 0: pass
                elif lastiddblogtime + config['iddb_logging'].as_int('logtime') < time.time():
                    self.iddblog()
                    lastiddblogtime = time.time()

    def dblog(self):
        # Make a query for the metadata, but return only rows where IMO
        # has a value, and make a MD5 hash out of the data
        newhashdict = {}
        for r in self.db_main:
            if r['imo']:
                # If base station, see if we should log it
                if r['transponder_type'] == 'base' and not config['logging'].as_bool('logbasestations'):
                    continue
                # Make of string of these fields
                infostring = str((r['imo'], r['name'], r['type'],
                                  r['callsign'], r['destination'],
                                  r['eta'], r['length'], r['width']))
                # Add info in dict as {mmsi: MD5-hash}
                hash = hashlib.md5()
                hash.update(infostring)
                newhashdict[r['mmsi']] = hash.digest()
        # Check what objects we should update in the metadata table
        update_mmsi = []
        for (key, value) in newhashdict.iteritems():
            # Check if we have logged this MMSI number before
            if key in self.hashdict:
                # Compare the hashes, if different: add to update list
                if cmp(value, self.hashdict[key]):
                    update_mmsi.append(key)
            else:
                # The MMSI was new, add to update list
                update_mmsi.append(key)
        # Set self.hashdict to the new hash dict
        self.hashdict = newhashdict
        # Query the memory DB
        positionquery = []
        # Calculate the oldest time we allow an object to have
        threshold = datetime.datetime.now() - datetime.timedelta(seconds=config['logging'].as_int('logtime'))
        # Iterate over all objects in db_main
        for r in self.db_main:
            # If base station, see if we should log it
            if r['transponder_type'] == 'base' and not config['logging'].as_bool('logbasestations'):
                continue
            # If object is newer than threshold, get data
            if r['time'] > threshold:
                data = [r['time'].replace(microsecond=0).isoformat(), r['mmsi'], r['latitude'],
                        r['longitude'], r['georef'], r['sog'],
                        r['cog']]
                # Set all fields contaning value 'N/A' to Nonetype
                # (it's ugly, I know...)
                # Also convert decimal type to float
                for (i, v) in enumerate(data):
                    if v == 'N/A':
                        data[i] = None
                    elif type(v) == decimal.Decimal:
                        data[i] = float(v)
                positionquery.append(data)
        # Sort in chronological order (by time)
        positionquery.sort()
        metadataquery = []
        # Iterate over the objects we should update in metadata
        for mmsi in update_mmsi:
            # Get only the first list (should be only one anyway)
            r = self.db_main._mmsi[mmsi][0]
            data = [r['time'].replace(microsecond=0).isoformat(), r['mmsi'], r['imo'],
                    r['name'], r['type'], r['callsign'],
                    r['destination'], r['eta'], r['length'],
                    r['width']]
            # Remove any 'N/A' with Nonetype (ugly, I know...)
            for (i, v) in enumerate(data):
                if v == 'N/A':
                    data[i] = None
            metadataquery.append(data)
        # Sort in chronological order (by time)
        metadataquery.sort()
        ownshipdata = [self.ownposition['owntime'].replace(microsecond=0).isoformat(), self.ownmmsi, float(self.ownposition['ownlatitude']), float(self.ownposition['ownlongitude']), self.ownposition['owngeoref'], float(self.ownposition['ownsog']), float(self.ownposition['owncog'])]
        # Open the file and log
        try:
            # Open file with filename in config['logging']['logfile']
            connection = sqlite.connect(os.path.join(package_home(globals()), unicode(config['logging']['logfile'], 'utf-8')))
            cursor = connection.cursor()
            # Create tables if they don't exist
            cursor.execute("CREATE TABLE IF NOT EXISTS position (time, mmsi, latitude, longitude, georef, sog, cog);")
            cursor.execute("CREATE TABLE IF NOT EXISTS metadata (time, mmsi, imo, name, type, callsign, destination, eta, length, width);")
            # Log to the two tables
            cursor.executemany("INSERT INTO position (time, mmsi, latitude, longitude, georef, sog, cog) VALUES (?, ?, ?, ?, ?, ?, ?)", positionquery)
            cursor.executemany("INSERT INTO metadata (time, mmsi, imo, name, type, callsign, destination, eta, length, width) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", metadataquery)
            # Log Ownship data
            cursor.execute("INSERT INTO position (time, mmsi, latitude, longitude, georef, sog, cog) VALUES (?, ?, ?, ?, ?, ?, ?)", ownshipdata)
            # Commit changes and close file
            connection.commit()
            connection.close()
        except:
            logging.warning("Logging to disk failed", exc_info=True)

    def iddblog(self):
        # Query the memory iddb
        iddbquery = []
        for r in self.db_iddb:
            iddbquery.append((r['mmsi'], r['imo'], r['name'], r['callsign']))
        # Open the file and log
        try:
            # Open file with filename in config['iddb_logging']['logfile']
            connection = sqlite.connect(os.path.join(package_home(globals()), unicode(config['iddb_logging']['logfile'], 'utf-8')))
            cursor = connection.cursor()
            # Create table if it doesn't exist
            cursor.execute("CREATE TABLE IF NOT EXISTS iddb (mmsi PRIMARY KEY, imo, name, callsign);")
            # Log
            cursor.executemany("INSERT OR REPLACE INTO iddb (mmsi, imo, name, callsign) VALUES (?, ?, ?, ?)", iddbquery)
            # Commit changes and close file
            connection.commit()
            connection.close()
        except:
            logging.warning("Logging IDDB to disk failed", exc_info=True)

    def loadiddb(self):
        # See if an iddb logfile exists, if not, return
        try:
            dbfile = open(os.path.join(package_home(globals()), unicode(config['iddb_logging']['logfile'], 'utf-8')))
            dbfile.close()
        except: return
        try:
            # Open the db
            connection = sqlite.connect(os.path.join(package_home(globals()), unicode(config['iddb_logging']['logfile'], 'utf-8')))
            cursor = connection.cursor()
            # Select data from table iddb
            cursor.execute("SELECT * FROM iddb;",())
            iddb_data = cursor.fetchall()
            # Close connection
            connection.close()
            # Put iddb_data in the memory db
            for ship in iddb_data:
                self.db_iddb.insert(mmsi=int(ship[0]), imo=ship[1], name=ship[2], callsign=ship[3])
        except:
            logging.warning("Reading from IDDB file failed", exc_info=True)

    def loadremarkfile(self):
        # This function will try to read a remark/alert file, if defined in config
        path = unicode(config['alert']['remarkfile'], 'utf-8')
        if config['alert'].as_bool('remarkfile_on') and len(path) > 0:
            try:
                temp = {}
                file = open(os.path.join(package_home(globals()), path), 'rb')
                csv_reader = csv.reader(file)
                for row in csv_reader:
                    # Try to read line as ASCII/UTF-8, if error, try cp1252
                    try:
                        temp[int(row[0])] = (unicode(row[1]), unicode(row[2], 'utf-8'))
                    except:
                        temp[int(row[0])] = (unicode(row[1]), unicode(row[2], 'cp1252'))
                file.close()
                self.remarkdict = temp.copy()
            except:
                logging.warning("Reading from remark file failed", exc_info=True)

    def put(self, item):
        try:
            self.queue.put_nowait(item)
        except Queue.Full:
            self.queue.get_nowait()
            self.queue.put_nowait(item)

    def start(self):
        try:
            r = threading.Thread(target=self.Main)
            r.setDaemon(1)
            r.start()
            return True
        except:
            return False

    def stop(self):
        # Get everything in queue and send stop string
        try:
            while True:
                self.queue.get_nowait()
        except Queue.Empty:
            self.put('stop')


# Initialize thread classes
main_thread = MainThread()
comm_hub_thread = CommHubThread()
serial_thread = SerialThread()
network_server_thread = NetworkServerThread()
network_client_thread = NetworkClientThread()

# Set up loggers and logging handling
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

class GUIErrorHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)

    def emit(self, record):
        # Send to main thread
        main_thread.put({'error': self.format(record)})

if cmdlineoptions.nogui:
    # Send logging to sys.stderr instead of to the GUI
    handler = logging.StreamHandler()
    formatter = logging.Formatter('\n%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
else:
    # Set a logging handler for errors and send these to the GUI
    gui_handler = GUIErrorHandler()
    gui_formatter = logging.Formatter('%(levelname)s %(message)s')
    gui_handler.setFormatter(gui_formatter)
    gui_handler.setLevel(logging.ERROR)
    logger.addHandler(gui_handler)

# Set a logging handler for everything and save to file
if config['logging'].as_bool('logexceptions'):
    file_handler = logging.FileHandler(filename=os.path.join(package_home(globals()), 'except.log'))
    file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    # Send everything to the exception file
    except_file = open(os.path.join(package_home(globals()), 'except.log'), 'a', 0)
    sys.stderr = except_file
else:
    sys.stderr = open(os.devnull)

# Start threads
main_thread.start()
comm_hub_thread.start()
serial_thread.start()
if config['network'].as_bool('server_on'):
    network_server_thread.start()
network_client_thread.start()

# Start the GUI
# Wait some time before initiating, to let the threads settle
time.sleep(0.2)
# See if we shall start the GUI
if cmdlineoptions.nogui:
    # Say hello
    print "\nAIS Logger running without GUI."
    print "Press any key to terminate program...\n"
    # Wait for key press
    raw_input()
    print "Terminating program..."
else:
    # Start GUI
    app = GUI(0)
    main_window = app.GetFrame()
    app.MainLoop()

# Turn off error logging to prevent spurious messages
sys.stderr = open(os.devnull)
# Stop threads
comm_hub_thread.stop()
serial_thread.stop()
network_server_thread.stop()
network_client_thread.stop()
main_thread.stop()

# Set exit time
exittime = time.time()
# Exit program when only one thread remains or when timeout occur
while True:
    threads = threading.enumerate()
    nrofthreads = len(threads)
    try:
        networkserver_exist = threads.index('Thread(NetworkServer, started daemon)>')
    except ValueError:
        nrofthreads -=1
    # Check for exit conditions, either that only one thread remains
    # or that we have timed out. The timeout prevents the process from
    # not terminating properly.
    if nrofthreads > 1 and (exittime + 30) > time.time():
        pass
    else:
        break
