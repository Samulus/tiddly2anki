# tiddler2anki by Samuel Vargas # this is a plugin for anki that uses a ghetto regex based parsing system 
# to import exported tiddler.json file from tiddlywiki into Anki.
# It checks for the prescence of a <qa time=blah></qa> and matching <an></an>
# tag to determine the question and answer. This is so I can combine my questions and
# flashcards directly in my notes. Feel free to adapt it to your needs.
# TODO: nested lists, nested bullets, text fmt replacing
# __update, __create, __remove need to operate on the specific deck only
# __remove needs to be created (will suspend cards not found anymore and the user can delete them manually)

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *
from PyQt4 import QtGui
from os import getenv
from itertools import izip
from pprint import pformat as Pretty
from BeautifulSoup import BeautifulSoup as Soup
import json, re

def tiddler2html(text):
  struct = {
    'header'  : re.compile("^\!+", re.M),
    'bullets' : re.compile("^\*+", re.M),
    'numlist' : re.compile("^\#+", re.M),
    "table"   : re.compile("((?<=\|)[^\s]*?)(?=\|)", re.M),
    "strings" : re.compile("(?![\!\*\#\|])^.+", re.M),
  }

  fmt = {
    "link_a"  : re.compile("\[\[.+?\|.+?\]\]"), # [[ABC|Alphabet]]
    "link_b"  : re.compile("\[\[[^\|]+?\]\]"),  # [[ABC]]
    "latex"   : re.compile("\$\$(.|\n)*?\$\$"),
    "bold"    : re.compile("''.+?''"),
    "italics" : re.compile("//.+?//"),
    "under"   : re.compile("__.+?__"),
    "strike"  : re.compile("~~.+?~~"),
  }

  html = ''
  prev = newrow = None
  for line in text.splitlines():
    for rule in struct:
      newrow = True if prev == "table" and rule == "table" else False
      for m in struct[rule].finditer(line):
        s,e = m.span();
        # Lists
        if (prev != 'bullets' and rule  == "bullets"): html += "<ul><li>{}</li>".format(line[e:])
        if (prev == 'bullets' and rule  == "bullets"): html += "<li>{}</li>".format(line[e:])
        if (prev == 'bullets' and rule  != "bullets"): html += "</ul></br>"
        if (prev != 'numlist' and rule  == "numlist"): html += "<ol><li>{}</li>".format(line[e:])
        if (prev == 'numlist' and rule  == "numlist"): html += "<li>{}</li>".format(line[e:])
        if (prev == 'numlist' and rule  != "numlist"): html += "</ol></br>"
        # Tables
        if (prev != 'table'   and rule == 'table'): html += "<table><tbody><tr><td>{}</td>".format(line[s:e])
        if (prev == 'table'   and rule == "table" and newrow): 
          newrow= False; 
          html += ("</tr><td>{}</td>".format(line[s:e]))
        elif (prev == "table" and rule == "table" and not newrow): html += "<td>{}</td>".format(line[s:e])
        elif (prev == "table"   and rule != "table"): html += "</tr></tbody></br>";
        # One Liners
        if (rule == "strings"): html += (line[s:e])
        if (rule == "header"): html += "<h{l}>{val}</h{l}>".format(l=len(line[s:e]), val=line[e:])
        prev = rule;

  # Doublecheck Table Ended
  if (prev == "table" and rule != "table"): html += "</tr>\n</tbody></br>\n";

  # Text Formatting
  #for f in fmt:
    #for m in fmt[f].finditer(html):
      #s,e = f.span() TODO
      #pass

  return Soup(html + "</html>").prettify();


class Logic:
  def __init__(self):
    self.__json_db = {}
    self.__anki_db = {}

  def run(self, json_path, deck_str, log_fn):
    self.__log = log_fn
    self.__build_json_db(json_path)
    self.__build_anki_db(deck_str)
    self.__log(">>> Database Built")

    self.__selected_deck = deck_str
    self.__set_card_type('Basic')

    self.__log(">>> Card Type set to Basic")

    self.__create();
    self.__log(">>> Created new entries from " + json_path)

    self.__update();
    self.__log(">>> Updated existing entries from " + json_path)
    self.__log(">>> Peachy Keen")
    #self.__remove();

  # 
  # Database Initialisation
  #

  def __json_to_cards(self, text):
    s = Soup(text);
    assert(s != None)
    questions = s.findAll('qa')
    answers = s.findAll('an')
    if (questions == None or answers == None):
      return None
    assert len(questions) == len(answers)
    out = {}
    for q, a in izip(questions, answers):
      assert q['time'] != None # user forgot to put in a TIME attribute
      out[q['time']] = {'Front': q, 'Back': a}
    return out

  # tiddlers.json --> self.__json_db
  def __build_json_db(self, jpath):
    with open(jpath, 'r') as f:
      for node in json.loads(f.read()):
        cards = self.__json_to_cards(node['text'])
        if cards != None:
          for key in cards: 
            self.__json_db[key] = cards[key]

  # anki.sqlite --> self.__anki_db
  def __build_anki_db(self, deck):
    nids = mw.col.findNotes('')
    for i in nids:
      c = mw.col.getNote(i)
      if (c['md'] != '' or c['md'] != None):
        self.__anki_db[c['md']] = {'Front': c['Front'], 'Back': c['Back']}

  #
  # Database Operations 
  #

  def __set_card_type(self, ctype):
    # TODO: add support for cloze and basic and reverse'd 
    did = mw.col.decks.id(self.__selected_deck)
    mw.col.decks.select(did) 
    m = mw.col.models.byName(ctype)
    deck = mw.col.decks.get(did)
    deck['mid'] = m['id']
    mw.col.decks.save(deck)

  def __create(self):
    jkeys = self.__json_db.keys()
    akeys = self.__anki_db.keys()
    for k in jkeys:
      if k not in akeys:
        n = mw.col.newNote()
        did = mw.col.decks.id(self.__selected_deck)
        n['Front'] = tiddler2html((self.__json_db[k]['Front'].string))
        n['Back'] = tiddler2html((self.__json_db[k]['Back'].string))
        n['md'] = k
        n.model()['did'] = did
        mw.col.addNote(n)
    mw.reset()

  def __update(self):
    jkeys = self.__json_db.keys()
    akeys = self.__anki_db.keys()
    for k in jkeys:
      if k in akeys:
        nid = mw.col.findNotes(k)
        assert len(nid) == 1 # C O L L I S I O N
        n = mw.col.getNote(nid[0])
        n['Front'] = tiddler2html((self.__json_db[k]['Front'].string))
        n['Back']  = tiddler2html((self.__json_db[k]['Back'].string))
        self.__anki_db['Front'] = self.__json_db[k]['Front']
        self.__anki_db['Back']  = self.__json_db[k]['Back']
        n.flush();
    mw.reset()

  def __delete(self):
    jkeys = self.__json_db.keys()
    akeys = self.__anki_db.keys()
    for k in jkeys:
      if k not in akeys:
        pass


class UI(QtGui.QWidget):
  def __init__(self, decks):
    super(UI, self).__init__()
    self.__data = {'deck': None, 'path': None}
    self.__decks = decks
    self.__callback = None
    self.__json_btn = QtGui.QPushButton("Open JSON")
    self.__json_path = QtGui.QLineEdit(self)
    self.__deck_label = QtGui.QLabel("Deck")
    self.__deck_process = QtGui.QPushButton("Process")
    self.__deck_cancel = QtGui.QPushButton("Cancel")
    self.__deck_list = QComboBox(self)
    self.__log_stats = QtGui.QTextBrowser(self)
    self.__init_actions()
    self.__init_layout()

  def __init_actions(self):
    def set_path():
      fname = QtGui.QFileDialog.getOpenFileName(self, 'json location', getenv('HOME'))
      if fname: 
        self.__json_path.setText(fname)
    self.__json_btn.clicked.connect(set_path)

    def process():
      if self.__data['path'] != "" and self.__data['path'] != None:
        self.__data['path'] = self.__json_path.text()
        self.__data['deck'] = self.__deck_list.currentText()
        self.__callback(self.__data['path'], self.__data['deck'], self.logger)

    self.__deck_process.clicked.connect(process)

  def __init_layout(self):
    frame = QtGui.QVBoxLayout()
    row_a = QtGui.QHBoxLayout()
    row_a.addWidget(self.__json_btn)
    row_a.addWidget(self.__json_path)
    row_b = QtGui.QHBoxLayout()
    row_b.addWidget(self.__deck_label)
    for d in self.__decks:
      self.__deck_list.addItem(d)
    row_b.addWidget(self.__deck_list)
    row_b.addWidget(self.__deck_process)
    row_b.addWidget(self.__deck_cancel)
    frame.addLayout(row_a)
    frame.addLayout(row_b)
    frame.addWidget(self.__log_stats)
    self.setLayout(frame)
    self.show()

  # Public
  def setCallback(self, fn):
    self.__callback = fn

  def logger(self, msg):
    self.__log_stats.append(msg)

def get_decks():
  out = []
  decks = mw.col.decks.all()
  for d in decks:
    out.append(d['name'])
  return out

def main():
  decks = get_decks()
  logic = Logic()
  mw.ui = UI(decks)
  mw.ui.setCallback(logic.run)

action = QAction("tiddler2anki", mw)
mw.connect(action, SIGNAL("triggered()"), main)
mw.form.menuTools.addAction(action)
