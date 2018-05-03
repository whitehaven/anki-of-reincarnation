#-------------------------------------------------------------------------------
#
# Name:        Quizlet plugin for Anki 2.0
# Purpose:     Import decks from Quizlet into Anki 2.0
# Author:
#  - Original: (c) Rolph Recto 2012, last updated 12/06/2012
#              https://github.com/rolph-recto/Anki-Quizlet
#  - Also:     Contributions from https://ankiweb.net/shared/info/1236400902
#  - Current:  JDMaybeMD
# Created:     04/07/2017
#
# Changlog:    Inital release
#               - Rolph's plugin functionality was broken, so...
#               - removed search tables and associated functions to KISS
#               - reused the original API key, dunno if that's OK
#               - replaced with just one box, for a quizlet URL
#               - added basic error handling for dummies
#
#               Update 04/09/2017
#               - modified to now take a full Quizlet url for ease of use
#               - provide feedback if trying to download a private deck
#               - return RFC 2616 response codes when error handling
#               - don't make a new card type every time a new deck imported
#               - better code documentation so people can modify it
#   
#               Update 01/31/2018
#               - get original quality images instead of mobile version
#-------------------------------------------------------------------------------
#!/usr/bin/env python

__window = None

import sys, math, time, urllib, urlparse, json, re
from urllib2 import Request, urlopen, URLError

# Anki
from aqt import mw
from aqt.qt import *

# PyQt4.Qt import Qt
from PyQt4.QtGui import *

# add custom model if needed
def addCustomModel(name, col):

    # create custom model for imported deck
    mm = col.models
    existing = mm.byName("Basic Quizlet")
    if existing:
        return existing
    m = mm.new("Basic Quizlet")

    # add fields
    mm.addField(m, mm.newField("Front"))
    mm.addField(m, mm.newField("Back"))
    mm.addField(m, mm.newField("Add Reverse"))

    # add cards
    t = mm.newTemplate("Normal")

    # front
    t['qfmt'] = "{{Front}}"
    t['afmt'] = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"
    mm.addTemplate(m, t)

    # back
    t = mm.newTemplate("Reverse")
    t['qfmt'] = "{{#Add Reverse}}{{Back}}{{/Add Reverse}}"
    t['afmt'] = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Front}}"
    mm.addTemplate(m, t)

    mm.add(m)
    return m

# throw up a window with some info (used for testing)
def debug(message):
    QMessageBox.information(QWidget(), "Message", message)

class QuizletWindow(QWidget):

    # used to access Quizlet API
    __APIKEY = "ke9tZw8YM6"

    # main window of Quizlet plugin
    def __init__(self):
        super(QuizletWindow, self).__init__()

        self.results = None
        self.thread = None

        self.initGUI()

    # create GUI skeleton
    def initGUI(self):
        
        self.box_top = QVBoxLayout()
        self.box_upper = QHBoxLayout()

        # left side
        self.box_left = QVBoxLayout()

        # quizlet url field
        self.box_name = QHBoxLayout()
        self.label_url = QLabel("Quizlet URL:")
        self.text_url = QLineEdit("",self)
        self.text_url.setMinimumWidth(300)

        self.box_name.addWidget(self.label_url)
        self.box_name.addWidget(self.text_url)

        # add layouts to left
        self.box_left.addLayout(self.box_name)

        # right side
        self.box_right = QVBoxLayout()

        # code (import set) button
        self.box_code = QHBoxLayout()
        self.button_code = QPushButton("Import Deck", self)
        self.box_code.addStretch(1)
        self.box_code.addWidget(self.button_code)
        self.button_code.clicked.connect(self.onCode)

        # add layouts to right
        self.box_right.addLayout(self.box_code)

        # add left and right layouts to upper
        self.box_upper.addLayout(self.box_left)
        self.box_upper.addSpacing(20)
        self.box_upper.addLayout(self.box_right)

        # results label
        self.label_results = QLabel("\r\n<i>Example: https://quizlet.com/150875612/usmle-flash-cards/</i>")

        # add all widgets to top layout
        self.box_top.addLayout(self.box_upper)
        self.box_top.addWidget(self.label_results)
        self.box_top.addStretch(1)
        self.setLayout(self.box_top)

        # go, baby go!
        self.setMinimumWidth(500)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setWindowTitle("Improved Quizlet to Anki Importer")
        self.show()

    def onCode(self):

        # grab url input
        url = self.text_url.text()
        
        # voodoo needed for some error handling
        if urlparse.urlparse(url).scheme:
            urlDomain = urlparse.urlparse(url).netloc
            urlPath = urlparse.urlparse(url).path
        else:
            urlDomain = urlparse.urlparse("https://"+url).netloc
            urlPath = urlparse.urlparse("https://"+url).path

        # validate quizlet URL
        if url == "":
            self.label_results.setText("Oops! You forgot the deck URL :(")
            return
        elif not "quizlet.com" in urlDomain:
            self.label_results.setText("Oops! That's not a Quizlet URL :(")
            return

        # validate and set Quizlet deck ID
        quizletDeckID = urlPath.strip("/")
        if quizletDeckID == "":
            self.label_results.setText("Oops! Please use the full deck URL :(")
            return
        elif not bool(re.search(r'\d', quizletDeckID)):
            self.label_results.setText(u"Oops! No deck ID found in path <i>{0}</i> :(".format(quizletDeckID))
            return
        else: # get first set of digits from url path
            quizletDeckID = re.search(r"\d+", quizletDeckID).group(0)

        # and aaawaaaay we go...
        self.label_results.setText("Connecting to Quizlet...")

        # build URL
        deck_url = (u"https://api.quizlet.com/2.0/sets/{0}".format(quizletDeckID))
        deck_url += (u"?client_id={0}".format(QuizletWindow.__APIKEY))

        # stop previous thread first
        if not self.thread == None:
            self.thread.terminate()

        # download the data!
        self.thread = QuizletDownloader(self, deck_url)
        self.thread.start()

        while not self.thread.isFinished():
            mw.app.processEvents()
            self.thread.wait(50)

        # error fetching data
        if self.thread.error:
            if self.thread.errorCode == 403:
                self.label_results.setText("Sorry, this is a private deck :(")
            elif self.thread.errorCode == 404:
                self.label_results.setText(u"Can't find a deck with the ID <i>{0}</i>".format(quizletDeckID))
            else:
                self.label_results.setText(self.thread.errorMessage)
        else: # everything went through, let's roll!
            deck = self.thread.results
            self.label_results.setText((u"Importing deck {0} by {1}...".format(deck["title"], deck["created_by"])))
            self.createDeck(deck)
            self.label_results.setText((u"Success! Imported <b>{0}</b> ({1} cards by <i>{2}</i>)".format(deck["title"], deck["term_count"], deck["created_by"])))

        self.thread.terminate()
        self.thread = None

    def createDeck(self, result):

        # create new deck and custom model
        name = result['title']
        terms = result['terms']
        deck = mw.col.decks.get(mw.col.decks.id(name))
        model = addCustomModel(name, mw.col)

        # assign custom model to new deck
        mw.col.decks.select(deck["id"])
        mw.col.decks.get(deck)["mid"] = model["id"]
        mw.col.decks.save(deck)

        # assign new deck to custom model
        mw.col.models.setCurrent(model)
        mw.col.models.current()["did"] = deck["id"]
        mw.col.models.save(model)
        txt=u"""
        <div><img src="{0}" /></div>
        """
        for term in terms:
            note = mw.col.newNote()
            note["Front"] = term["term"]
            note["Back"] = term["definition"].replace('\n','<br>')
            if not term["image"] is None:
                #stop the previous thread first
                file_name = self.fileDownloader(term["image"]["url"])
                note["Back"]+=txt.format(file_name)
                mw.app.processEvents()
            mw.col.addNote(note)
        mw.col.reset()
        mw.reset()

    # download the images
    def fileDownloader(self, url):
        file_name = "quizlet-" + url.split('/')[-1]
		# get original, non-mobile version of images
        url = url.replace('_m', '')
        urllib.urlretrieve(url, file_name)
        return file_name

class QuizletDownloader(QThread):

    # thread that downloads results from the Quizlet API
    def __init__(self, window, url):
        super(QuizletDownloader, self).__init__()
        self.window = window

        self.url = url
        self.results = None

        self.error = False
        self.errorCode = None 
        self.errorReason = None
        self.errorMessage = None

    def run(self):
        try: # can we parse this url and get valid json?
            self.results = json.load(urlopen(self.url))
        except URLError as e:
            self.error = True
            if hasattr(e, 'code'):
                self.errorCode = e.code
                self.errorMessage = (u"Error {0}".format(self.errorCode))
                if hasattr(e, 'reason'):
                    self.errorReason = e.reason
                    self.errorMessage += (u": {0}".format(self.errorReason))
        except ValueError as e:
                self.error = True
                self.errorReason = (u"Invalid json: {0}".format(e))
        # yep, we got it

# plugin was called from Anki
def runQuizletPlugin():
    global __window
    __window = QuizletWindow()

# create menu item in Anki
action = QAction("Import from Quizlet", mw)
mw.connect(action, SIGNAL("triggered()"), runQuizletPlugin)
mw.form.menuTools.addAction(action)