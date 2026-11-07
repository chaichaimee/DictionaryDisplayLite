# dictionaryDisplayLiteCore.py

import os
import re
import json
import threading
import time

import wx
import speech
from comtypes import COMError

import addonHandler
import core
import globalPluginHandler
import globalVars
import controlTypes
import logHandler
import gui
import gui.guiHelper
import ui
import speechDictHandler
from scriptHandler import script

from .validator import editorLink
from .validator import launcher as dictionaryCheckLauncher

addonHandler.initTranslation()

# Multi-tap gap (milliseconds) for the ctrl+shift+D dictionary-open gesture.
DICTIONARY_TAP_WINDOW_MS = 350

# Safety limits for the user-typed regular expression in the editor search box.
SEARCH_REGEX_MAX_LENGTH = 200
SEARCH_REGEX_TIME_BUDGET_SECONDS = 0.25
_NESTED_QUANTIFIER_RE = re.compile(r"\((?:[^()\\]|\\.)*(?:[+*]|\{\d*,\d*\})(?:[^()\\]|\\.)*\)\s*(?:[+*]|\{\d*,\d*\})")


def _isRiskySearchPattern(pattern):
	if len(pattern) > SEARCH_REGEX_MAX_LENGTH:
		return True
	return _NESTED_QUANTIFIER_RE.search(pattern) is not None

CONFIG_SUBFOLDER = os.path.join("ChaiChaimee", "DictionaryDisplayLite")
CONFIG_FILE_NAME = "settings.json"
DEFAULT_SETTINGS = {"condenseEntries": True}


def _getConfigPaths():
	configDir = os.path.join(globalVars.appArgs.configPath, CONFIG_SUBFOLDER)
	return configDir, os.path.join(configDir, CONFIG_FILE_NAME)


def loadSettings():
	"""
	Loads DictionaryDisplayLite's own JSON settings, falling back to defaults
	on any missing, corrupt, or unreadable file rather than raising.
	"""
	_configDir, configFilePath = _getConfigPaths()
	try:
		with open(configFilePath, "r", encoding="utf-8") as settingsFile:
			loadedSettings = json.load(settingsFile)
		if not isinstance(loadedSettings, dict):
			raise ValueError("Settings file did not contain a JSON object")
	except (OSError, ValueError) as loadError:
		logHandler.log.debug(f"DictionaryDisplayLite: Using default settings - {loadError}")
		return dict(DEFAULT_SETTINGS)
	mergedSettings = dict(DEFAULT_SETTINGS)
	mergedSettings.update(loadedSettings)
	return mergedSettings


def saveSettings(settingsToSave):
	configDir, configFilePath = _getConfigPaths()
	try:
		os.makedirs(configDir, exist_ok=True)
		with open(configFilePath, "w", encoding="utf-8") as settingsFile:
			json.dump(settingsToSave, settingsFile, indent="\t")
	except OSError as saveError:
		logHandler.log.debug(f"DictionaryDisplayLite: Failed to save settings - {saveError}")
		ui.message(_("Could not save DictionaryDisplayLite settings."))


def _getEntryTypeChoices():
	"""
	Returns [(intValue, displayLabel), ...] for every speech dictionary entry
	type this NVDA installation currently supports. Tries the modernized
	speechDictHandler.types.EntryType enum first - available from the
	2026-era speech dictionary modernization onward (NVDA PR #19430), which
	also added several new entry types beyond the original three (PR
	#19517: part of word, start of word, end of word, wildcard) - and falls
	back to the three original ENTRY_TYPE_* module constants for older NVDA
	installations where that enum does not exist. Deliberately dynamic
	rather than a hardcoded list: the supported type set has already
	changed once in this NVDA release cycle and may change again.
	"""
	try:
		from speechDictHandler.types import EntryType
		return [(member.value, member.name.replace("_", " ").capitalize()) for member in EntryType]
	except ImportError:
		return [
			(speechDictHandler.ENTRY_TYPE_ANYWHERE, _("Anywhere")),
			(speechDictHandler.ENTRY_TYPE_WORD, _("Whole word")),
			(speechDictHandler.ENTRY_TYPE_REGEXP, _("Regular expression")),
		]


def _getValidEntryTypeValuesAsStrings():
	"""Used by _scanDictionaryFile to validate the on-disk type flag."""
	return {str(typeValue) for typeValue, _label in _getEntryTypeChoices()}


class _DictionaryRow:
	"""
	One data row of a dictionary file, together with the comment and blank
	lines written directly above it (leadingLines, kept verbatim so saving
	never rearranges the file). rawLine is set for a row whose fields could not
	be parsed; it is written back unchanged until the row is edited.
	isEnabled is False for a row stored as a '#'-prefixed data line, which
	NVDA reads as a comment and therefore never applies to speech.
	"""

	def __init__(
		self,
		pattern,
		replacement,
		comment="",
		caseSensitive=False,
		type=0,
		leadingLines=None,
		rawLine=None,
		isEnabled=True,
	):
		self.pattern = pattern
		self.replacement = replacement
		self.comment = comment
		self.caseSensitive = caseSensitive
		self.type = type
		self.leadingLines = leadingLines
		self.rawLine = rawLine
		self.isEnabled = isEnabled


_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")


def _rowFromLine(line, leadingLines):
	comment = " ".join(text[1:] for text in leadingLines if text.startswith("#"))
	fields = line.split("\t")
	try:
		if len(fields) != 4 or not fields[0]:
			raise ValueError("unexpected field layout")
		caseSensitive = bool(int(fields[2]))
		entryType = int(fields[3])
	except ValueError:
		return _DictionaryRow(
			fields[0], fields[1] if len(fields) > 1 else "", comment, False, 0, list(leadingLines), rawLine=line
		)
	return _DictionaryRow(fields[0], fields[1], comment, caseSensitive, entryType, list(leadingLines))


def _disabledRowFromLine(line, leadingLines):
	"""
	Returns a disabled _DictionaryRow when a '#'-prefixed line holds a complete
	entry (four tab-separated fields, a non-empty pattern that does not start
	with whitespace, a 0/1 case flag and a known type), otherwise None so the
	line stays an ordinary comment.
	"""
	fields = line[1:].split("\t")
	if len(fields) != 4 or not fields[0] or fields[0][0].isspace():
		return None
	if fields[2] not in ("0", "1") or fields[3] not in _getValidEntryTypeValuesAsStrings():
		return None
	comment = " ".join(text[1:] for text in leadingLines if text.startswith("#"))
	return _DictionaryRow(
		fields[0], fields[1], comment, fields[2] == "1", int(fields[3]), list(leadingLines), isEnabled=False
	)


def _readDictionaryRows(filePath):
	"""
	Reads every row of the file, including rows that NVDA's own loader would
	silently drop (for example an invalid regular expression), so that
	re-saving the file from the editor never deletes them. Returns
	(rows, trailingLines). Raises OSError or UnicodeDecodeError.
	"""
	with open(filePath, "r", encoding="utf-8-sig", newline="") as dictFile:
		content = dictFile.read()
	lines = _LINE_BREAK_RE.split(content)
	if lines and lines[-1] == "":
		lines.pop()
	rows = []
	pendingLines = []
	for line in lines:
		if line.startswith("#"):
			disabledRow = _disabledRowFromLine(line, pendingLines)
			if disabledRow is None:
				pendingLines.append(line)
				continue
			rows.append(disabledRow)
			pendingLines = []
			continue
		if not line.strip():
			pendingLines.append(line)
			continue
		rows.append(_rowFromLine(line, pendingLines))
		pendingLines = []
	return rows, pendingLines


def _writeVoiceDictionaryEntries(filePath, entries, trailingLines=()):
	"""
	Writes entries back in the tab-separated pattern/replacement/caseSensitive/
	type format NVDA's speech dictionary loader reads, keeping each row's own
	comment and blank lines. A disabled entry is written with a leading '#'.
	The file is replaced atomically from a temporary
	file so a failed write cannot leave a half-written dictionary behind.
	"""
	lines = []
	for entry in entries:
		leadingLines = entry.leadingLines
		if leadingLines is None:
			leadingLines = [f"#{entry.comment}"] if entry.comment else []
		lines.extend(leadingLines)
		if entry.rawLine is not None:
			lines.append(entry.rawLine)
			continue
		dataLine = "\t".join([
			entry.pattern,
			entry.replacement,
			"1" if entry.caseSensitive else "0",
			str(entry.type),
		])
		lines.append(dataLine if entry.isEnabled else "#" + dataLine)
	lines.extend(trailingLines)
	temporaryPath = filePath + ".tmp"
	try:
		with open(temporaryPath, "w", encoding="utf-8") as dictFile:
			if lines:
				dictFile.write("\n".join(lines) + "\n")
		os.replace(temporaryPath, filePath)
	except OSError:
		try:
			os.remove(temporaryPath)
		except OSError:
			pass
		raise


class QuickMenu(wx.Dialog):
	"""
	Floating drill-down list menu. An earlier wx.TreeCtrl-based version never
	activated a leaf item on Enter (navigating between sibling items worked,
	but pressing Enter did nothing on every item including Settings), so the
	menu is built on a plain list box instead:
	- Keys are intercepted via wx.EVT_CHAR_HOOK on the dialog itself, not
	  wx.EVT_KEY_DOWN on a child control. EVT_CHAR_HOOK is delivered to the
	  top-level window before a native child control gets a chance to
	  swallow the key itself.
	- A submenu is a genuine navigational drill-down: the same listbox's
	  contents are replaced wholesale, with menu_stack tracking how to go
	  back, rather than a tree expanding in place.

	This dialog is always entered via wx.CallAfter, never core.callLater -
	see _showQuickMenu. That distinction is what makes ShowModal() safe to
	call directly here, unlike DictionaryDisplayLiteSettingsDialog's history
	(see its docstring): wx.CallAfter posts to wx's own idle/pending-event
	queue, so a nested ShowModal() does not stall NVDA's core queue the way
	one reached through a core.callLater (wx.Timer) callback did.

	menuData is a list of dicts, each shaped as either:
	  {"label": str, "action": callable}               - a leaf item, or
	  {"label": str, "submenu": [the same shape, ...]}  - a category item
	"""

	def __init__(self, menuData):
		super().__init__(
			gui.mainFrame, title="",
			style=wx.BORDER_SIMPLE | wx.STAY_ON_TOP | wx.FRAME_FLOAT_ON_PARENT,
		)
		self.menu_stack = []
		self.current_menu = menuData
		self._first_item_label = ""

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.listbox = wx.ListBox(panel, choices=[], style=wx.LB_SINGLE)
		sizer.Add(self.listbox, 1, wx.EXPAND | wx.ALL, 5)
		panel.SetSizer(sizer)
		self._populateList()
		self.Fit()
		self.CentreOnScreen()

		self.Bind(wx.EVT_CHAR_HOOK, self._onCharHook)
		self.Bind(wx.EVT_SHOW, self._onShow)
		self.listbox.SetFocus()

	def _populateList(self):
		self.listbox.Clear()
		for item in self.current_menu:
			self.listbox.Append(item["label"])
		if self.listbox.GetCount() > 0:
			self.listbox.SetSelection(0)
			self._first_item_label = self.current_menu[0]["label"]

	def _onShow(self, evt):
		# Silences the dialog's own default open announcement (which would
		# otherwise speak the window/list boilerplate) and replaces it with
		# just the first item's label, matching the original "declares the
		# first item immediately" request.
		if evt.IsShown():
			previousMode = speech.getState()
			speech.setSpeechMode(speech.SpeechMode.off)
			core.callLater(150, self._restoreSpeechAndAnnounceFirst, previousMode)
		evt.Skip()

	def _restoreSpeechAndAnnounceFirst(self, previousMode):
		speech.setSpeechMode(previousMode)
		if self._first_item_label:
			ui.message(self._first_item_label)

	def _onCharHook(self, evt):
		keyCode = evt.GetKeyCode()
		if keyCode == wx.WXK_RETURN:
			self._onActivate()
		elif keyCode == wx.WXK_ESCAPE:
			if self.menu_stack:
				self._goBack()
			else:
				self.EndModal(wx.ID_CANCEL)
		elif keyCode == wx.WXK_RIGHT:
			self._openSubmenu()
		elif keyCode == wx.WXK_LEFT:
			if self.menu_stack:
				self._goBack()
		else:
			evt.Skip()

	def _openSubmenu(self):
		selectedIndex = self.listbox.GetSelection()
		if selectedIndex == wx.NOT_FOUND:
			return
		item = self.current_menu[selectedIndex]
		if item.get("submenu"):
			self.menu_stack.append((self.current_menu, selectedIndex))
			self.current_menu = item["submenu"]
			self._populateList()

	def _goBack(self):
		if not self.menu_stack:
			return
		previousMenu, previousIndex = self.menu_stack.pop()
		self.current_menu = previousMenu
		self._populateList()
		self.listbox.SetSelection(previousIndex)

	def _onActivate(self):
		selectedIndex = self.listbox.GetSelection()
		if selectedIndex == wx.NOT_FOUND:
			return
		item = self.current_menu[selectedIndex]
		if item.get("submenu"):
			self._openSubmenu()
		elif item.get("action"):
			# Close first, then run the action, both deferred via
			# wx.CallAfter so this dialog is fully torn down before the
			# action potentially opens another dialog (Settings) on top.
			wx.CallAfter(self.EndModal, wx.ID_OK)
			wx.CallAfter(item["action"])


class DictionaryDisplayLiteSettingsDialog(wx.Dialog):
	"""
	Shown via ShowModal(), always entered through wx.CallAfter (see
	GlobalPlugin._openSettingsDialog and QuickMenu._onActivate) rather than
	core.callLater. That distinction matters: an earlier version of this
	dialog froze NVDA's core because it was opened via core.callLater(0, ...)
	- a wx.Timer callback nested inside NVDA's own queueHandler.flushQueue
	cycle - and ShowModal() blocking from inside that cycle stalled
	flushQueue itself, which the watchdog then reported as a frozen core.
	wx.CallAfter instead posts to wx's own idle/pending-event queue and does
	not nest inside that cycle, so ShowModal() is safe to call directly here.
	"""

	def __init__(self, parent, currentSettings, onApply):
		# Translators: Title of the DictionaryDisplayLite settings dialog.
		super().__init__(parent, title=_("DictionaryDisplayLite Settings"))
		self._onApply = onApply

		dialogSizer = wx.BoxSizer(wx.VERTICAL)
		self._condenseCheckbox = wx.CheckBox(
			self,
			# Translators: Checkbox label in the DictionaryDisplayLite settings dialog.
			label=_("Condense dictionary entries in the list (shorten spoken labels)"),
		)
		self._condenseCheckbox.SetValue(bool(currentSettings.get("condenseEntries", True)))
		dialogSizer.Add(self._condenseCheckbox, border=15, flag=wx.ALL)
		dialogSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), border=15, flag=wx.ALL | wx.ALIGN_RIGHT)
		self.SetSizerAndFit(dialogSizer)

		self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)

		# wx gives the OK button (as the dialog's default item) initial focus
		# on Show() by default. Deferring via wx.CallAfter lets our focus call
		# run after that default assignment, landing focus on the checkbox
		# (the dialog's first and only real setting) instead, as requested.
		wx.CallAfter(self._condenseCheckbox.SetFocus)

	def _onOk(self, evt):
		self._onApply({"condenseEntries": self._condenseCheckbox.GetValue()})
		# Skip lets the stock OK button's default handling run too, which is
		# what actually calls EndModal(wx.ID_OK) for a CreateButtonSizer button.
		evt.Skip()


def _computeLineNumbers(entries):
	"""
	Returns the real 1-indexed physical line number each entry's data line
	would occupy in the file, counting every physical line including an
	comment or blank line stored above an entry - this
	matches _writeVoiceDictionaryEntries's own output exactly, so it stays
	accurate for a freshly-loaded file and after any in-memory edit alike.
	Pure function (Section 15 testability): no NVDA/wx calls.
	"""
	lineNumbers = []
	currentLine = 1
	for entry in entries:
		currentLine += _leadingLineCount(entry)
		lineNumbers.append(currentLine)
		currentLine += 1
	return lineNumbers


def _leadingLineCount(entry):
	if entry.leadingLines is not None:
		return len(entry.leadingLines)
	return 1 if entry.comment else 0


class DictionaryEditorDialog(wx.Dialog):
	"""
	Custom search-and-edit GUI for the current voice dictionary. Built as a
	separate dialog rather than extending NVDA's own DictionaryDialog,
	because that dialog has no search/filter - the whole pain point this
	feature addresses is that a large voice dictionary is hard to browse
	there.

	This dialog only ever shows the entry list itself (plus the search box
	and Add/Edit/Remove buttons) - it does NOT show pattern/replace/case/
	type fields directly. Add and Edit each open a separate
	DictionaryEntryEditDialog instead, mirroring NVDA's own real speech
	dictionary dialogs. This was a deliberate restructuring in response to
	a flagged risk: showing pattern/replace fields inline and re-using
	whatever they currently held meant an accidental Add click could
	duplicate the currently selected word. Routing Add through its own
	always-blank sub-dialog removes that risk structurally rather than
	just reducing it (e.g. by moving the button).

	Works on a private SpeechDict loaded fresh from disk (_loadEntries), not
	the live speechDictHandler.dictionaries["voice"] object NVDA is actively
	using for speech, so a half-edited entry never briefly affects real
	output. Add/Edit/Remove/Move each rewrite the file immediately, per
	spec. On close, if anything changed, the live dictionary NVDA actually
	speaks from is reloaded (_reloadLiveVoiceDictionaryIfDirty) so the
	change takes effect without an NVDA restart.

	Known, deliberate limitation: Cancel/Escape only closes the dialog - it
	does NOT undo Add/Edit/Remove/Move actions already applied, since those
	already wrote to disk immediately as they happened. A true undo would
	require snapshotting and restoring the original file content, which is
	a larger feature than what was specified.

	Search-result announcement is debounced (the pending timer is cancelled
	and rescheduled on every keystroke) so typing doesn't trigger a spoken
	count on every character - only once typing pauses. The list itself
	still filters immediately on every keystroke; only the spoken
	announcement is delayed, since a live-updating list with a delayed
	announcement was the most sensible reading of the request.
	"""

	SEARCH_ANNOUNCE_DELAY_MS = 700

	def __init__(self, parent, filePath, initialLine=0):
		# Translators: Title of the voice dictionary search-and-edit dialog.
		super().__init__(parent, title=_("Search and Edit Voice Dictionary"))
		self._filePath = filePath
		self._entries = []
		self._visibleIndices = []
		self._isDirty = False
		self._typeChoices = _getEntryTypeChoices()
		self._searchAnnounceTimer = None
		self._searchProblem = None
		self._trailingLines = []

		self._loadEntries()

		sizerHelper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

		self._useRegexSearchCheckbox = sizerHelper.addItem(
			# Translators: Checkbox controlling whether the search box is treated as a regular expression.
			wx.CheckBox(self, label=_("Use regular &expression for search"))
		)
		self._useRegexSearchCheckbox.SetValue(False)
		self._useRegexSearchCheckbox.Bind(wx.EVT_CHECKBOX, self._onSearchChanged)

		# Translators: Label of the search box in the voice dictionary editor.
		self._searchEdit = sizerHelper.addLabeledControl(_("&Search:"), wx.TextCtrl)
		self._searchEdit.Bind(wx.EVT_TEXT, self._onSearchChanged)

		# Translators: Label of the entry list in the voice dictionary editor.
		self._entryListBox = sizerHelper.addLabeledControl(
			_("Dictionary &entries"), wx.ListBox, style=wx.LB_SINGLE
		)
		self._entryListBox.Bind(wx.EVT_CONTEXT_MENU, self._onListContextMenu)

		buttonRowSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button to add a new entry in the voice dictionary editor.
		self._addButton = wx.Button(self, label=_("&Add"))
		# Translators: Button to edit the selected entry in the voice dictionary editor.
		self._editButton = wx.Button(self, label=_("E&dit"))
		# Translators: Button to remove the selected entry.
		self._removeButton = wx.Button(self, label=_("&Remove"))
		for button in (self._addButton, self._editButton, self._removeButton):
			buttonRowSizer.Add(button, border=5, flag=wx.RIGHT)
		sizerHelper.addItem(buttonRowSizer)

		sizerHelper.addItem(self.CreateButtonSizer(wx.OK | wx.CANCEL))

		self.SetSizerAndFit(sizerHelper.sizer)

		self._addButton.Bind(wx.EVT_BUTTON, self._onAdd)
		self._editButton.Bind(wx.EVT_BUTTON, self._onEdit)
		self._removeButton.Bind(wx.EVT_BUTTON, self._onRemove)
		self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._onCancelButton, id=wx.ID_CANCEL)
		self.Bind(wx.EVT_CLOSE, self._onCloseEvent)

		self._refreshList(announce=False)
		if initialLine:
			self._selectEntryByLine(initialLine)
		# Focus lands on the entry list itself, not the search box, per spec.
		wx.CallAfter(self._entryListBox.SetFocus)

	def _loadEntries(self):
		self._entries, self._trailingLines = _readDictionaryRows(self._filePath)

	@property
	def isDirty(self):
		return self._isDirty

	def _selectEntryByLine(self, lineNumber):
		lineNumbers = _computeLineNumbers(self._entries)
		targetIndex = None
		for index, entryLine in enumerate(lineNumbers):
			if entryLine > lineNumber:
				break
			targetIndex = index
		if targetIndex is None:
			return
		self._selectEntryByIndex(targetIndex)

	def _refreshList(self, announce=True):
		searchText = self._searchEdit.GetValue()
		useRegex = self._useRegexSearchCheckbox.GetValue()
		compiledSearch = None
		self._searchProblem = None
		if useRegex and searchText:
			if _isRiskySearchPattern(searchText):
				self._searchProblem = "unsafe"
			else:
				try:
					compiledSearch = re.compile(searchText, re.IGNORECASE)
				except re.error:
					self._searchProblem = "invalid"

		lineNumbers = _computeLineNumbers(self._entries)
		self._visibleIndices = []
		displayLabels = []
		searchStartTime = time.perf_counter()
		for index, entry in enumerate(self._entries):
			haystack = f"{entry.pattern} {entry.replacement}"
			if searchText:
				if useRegex:
					if compiledSearch is None:
						break
					if time.perf_counter() - searchStartTime > SEARCH_REGEX_TIME_BUDGET_SECONDS:
						self._searchProblem = "timeout"
						break
					if not compiledSearch.search(haystack):
						continue
				elif searchText.lower() not in haystack.lower():
					continue
			self._visibleIndices.append(index)
			entryLabel = (
				# Translators: {pattern}/{replacement} are the entry's own text; {line} is its line number in the .dic file.
				_("{pattern} \u2192 {replacement} (line {line})").format(
					pattern=entry.pattern, replacement=entry.replacement, line=lineNumbers[index]
				)
			)
			if not entry.isEnabled:
				# Translators: {label} is a dictionary entry's list text; appended for an entry that is turned off.
				entryLabel = _("{label}, disabled").format(label=entryLabel)
			displayLabels.append(entryLabel)

		self._entryListBox.Set(displayLabels)
		if displayLabels:
			self._entryListBox.SetSelection(0)

		if announce:
			self._scheduleSearchResultAnnouncement()

	def _onSearchChanged(self, evt):
		self._refreshList()

	def _scheduleSearchResultAnnouncement(self):
		if self._searchAnnounceTimer is not None:
			self._searchAnnounceTimer.Stop()
		self._searchAnnounceTimer = core.callLater(
			self.SEARCH_ANNOUNCE_DELAY_MS, self._announceSearchResultCount
		)

	def _announceSearchResultCount(self):
		self._searchAnnounceTimer = None
		resultCount = len(self._visibleIndices)
		speech.cancelSpeech()
		searchProblem = self._searchProblem
		if searchProblem == "unsafe":
			# Translators: Reported when the regular expression typed in the search box is too complex or too long to run safely.
			ui.message(_("Search not run: the regular expression is too complex or too long"))
			return
		if searchProblem == "invalid":
			# Translators: Reported when the regular expression typed in the search box is not valid.
			ui.message(_("Search not run: the regular expression is not valid"))
			return
		if searchProblem == "timeout":
			# Translators: Reported when a regular expression search was stopped because it took too long.
			ui.message(_("Search stopped because it took too long. Results are incomplete"))
			return
		# Translators: {count} is the number of dictionary entries matching the current search.
		ui.message(_("{count} results found").format(count=resultCount))

	def _getSelectedEntryIndex(self):
		visiblePosition = self._entryListBox.GetSelection()
		if visiblePosition == wx.NOT_FOUND or visiblePosition >= len(self._visibleIndices):
			return None
		return self._visibleIndices[visiblePosition]

	def _selectEntryByIndex(self, entryIndex):
		if entryIndex in self._visibleIndices:
			self._entryListBox.SetSelection(self._visibleIndices.index(entryIndex))

	def _insertEntryAtLineNumber(self, entry, targetLineNumber, excludeIndex=None):
		"""
		Inserts entry at the position matching targetLineNumber - the
		developer's spec: editing the line-number field and confirming
		"will move the word to a new line ... It doesn't overwrite the
		original line, but inserts the new word in its place. The original
		line position will be shifted down." excludeIndex removes the
		entry being edited from its old slot first, so moving an entry to
		a line number does not count itself when locating the target
		position. Returns the entry's new index in self._entries.
		"""
		workingEntries = list(self._entries)
		if excludeIndex is not None:
			del workingEntries[excludeIndex]
		lineNumbers = _computeLineNumbers(workingEntries)
		insertPosition = len(workingEntries)
		for position, lineNumber in enumerate(lineNumbers):
			if lineNumber >= targetLineNumber:
				insertPosition = position
				break
		workingEntries.insert(insertPosition, entry)
		self._entries = workingEntries
		return insertPosition

	def _onAdd(self, evt):
		existingLineNumbers = _computeLineNumbers(self._entries)
		defaultLineNumber = (existingLineNumbers[-1] + 1) if existingLineNumbers else 1
		subDialog = DictionaryEntryEditDialog(
			self, self._typeChoices, defaultLineNumber=defaultLineNumber, isNew=True
		)
		try:
			result = subDialog.ShowModal()
		finally:
			subDialog.Destroy()
		if result != wx.ID_OK or subDialog.resultEntry is None:
			return
		newIndex = self._insertEntryAtLineNumber(subDialog.resultEntry, subDialog.resultLineNumber)
		self._isDirty = True
		self._writeEntriesToDisk()
		self._refreshList(announce=False)
		self._selectEntryByIndex(newIndex)
		# Translators: Reported after a new entry is added.
		ui.message(_("Entry added"))

	def _onEdit(self, evt):
		entryIndex = self._getSelectedEntryIndex()
		if entryIndex is None:
			# Translators: Reported when Edit is pressed with nothing selected.
			ui.message(_("No dictionary entry is selected"))
			return
		lineNumbers = _computeLineNumbers(self._entries)
		subDialog = DictionaryEntryEditDialog(
			self,
			self._typeChoices,
			defaultLineNumber=lineNumbers[entryIndex],
			isNew=False,
			existingEntry=self._entries[entryIndex],
			existingLineNumber=lineNumbers[entryIndex],
		)
		try:
			result = subDialog.ShowModal()
		finally:
			subDialog.Destroy()
		if result != wx.ID_OK or subDialog.resultEntry is None:
			return
		newIndex = self._insertEntryAtLineNumber(
			subDialog.resultEntry, subDialog.resultLineNumber, excludeIndex=entryIndex
		)
		self._isDirty = True
		self._writeEntriesToDisk()
		self._refreshList(announce=False)
		self._selectEntryByIndex(newIndex)
		# Translators: Reported after an entry is successfully updated.
		ui.message(_("Entry updated"))

	def _onRemove(self, evt):
		entryIndex = self._getSelectedEntryIndex()
		if entryIndex is None:
			# Translators: Reported when Remove is pressed with nothing selected.
			ui.message(_("No dictionary entry is selected"))
			return
		del self._entries[entryIndex]
		self._isDirty = True
		self._writeEntriesToDisk()
		self._refreshList(announce=False)
		# Translators: Reported after an entry is removed.
		ui.message(_("Entry removed"))

	def _onToggleEnabled(self, evt):
		entryIndex = self._getSelectedEntryIndex()
		if entryIndex is None:
			# Translators: Reported when Enable or Disable is chosen with nothing selected.
			ui.message(_("No dictionary entry is selected"))
			return
		entry = self._entries[entryIndex]
		if entry.rawLine is not None:
			# Translators: Reported when an entry cannot be turned on or off because its line is malformed.
			ui.message(_("This entry cannot be enabled or disabled because its line is not in a valid format"))
			return
		entry.isEnabled = not entry.isEnabled
		self._isDirty = True
		self._writeEntriesToDisk()
		self._refreshList(announce=False)
		self._selectEntryByIndex(entryIndex)
		if entry.isEnabled:
			# Translators: Reported after an entry is turned on.
			ui.message(_("Entry enabled"))
			return
		# Translators: Reported after an entry is turned off.
		ui.message(_("Entry disabled"))

	def _onMove(self, delta):
		if self._searchEdit.GetValue():
			# Translators: Reported when trying to reorder entries while a search filter is active.
			ui.message(_("Clear the search box to reorder entries"))
			return
		entryIndex = self._getSelectedEntryIndex()
		if entryIndex is None:
			return
		targetIndex = entryIndex + delta
		if targetIndex < 0 or targetIndex >= len(self._entries):
			return
		self._entries[entryIndex], self._entries[targetIndex] = self._entries[targetIndex], self._entries[entryIndex]
		self._isDirty = True
		self._writeEntriesToDisk()
		self._refreshList(announce=False)
		self._selectEntryByIndex(targetIndex)

	def _writeEntriesToDisk(self):
		try:
			_writeVoiceDictionaryEntries(self._filePath, self._entries, self._trailingLines)
		except OSError as writeError:
			logHandler.log.debug(f"DictionaryDisplayLite: Failed to write voice dictionary - {writeError}")
			# Translators: Reported when the voice dictionary file could not be saved.
			ui.message(_("Could not save the voice dictionary file"))

	def _onListContextMenu(self, evt):
		menu = wx.Menu()
		selectedIndex = self._getSelectedEntryIndex()
		if selectedIndex is not None and not self._entries[selectedIndex].isEnabled:
			# Translators: Context menu item to turn a disabled entry back on.
			toggleItem = menu.Append(wx.ID_ANY, _("&Enable entry"))
		else:
			# Translators: Context menu item to stop an entry from being applied without deleting it.
			toggleItem = menu.Append(wx.ID_ANY, _("Disa&ble entry"))
		self.Bind(wx.EVT_MENU, self._onToggleEnabled, toggleItem)
		# Translators: Context menu item to move the selected entry earlier in the dictionary.
		moveUpItem = menu.Append(wx.ID_ANY, _("Move &up"))
		# Translators: Context menu item to move the selected entry later in the dictionary.
		moveDownItem = menu.Append(wx.ID_ANY, _("Move &down"))
		# Translators: Context menu item to remove the selected entry.
		removeItem = menu.Append(wx.ID_ANY, _("&Remove"))
		self.Bind(wx.EVT_MENU, lambda e: self._onMove(-1), moveUpItem)
		self.Bind(wx.EVT_MENU, lambda e: self._onMove(1), moveDownItem)
		self.Bind(wx.EVT_MENU, self._onRemove, removeItem)
		self.PopupMenu(menu)
		menu.Destroy()

	def _reloadLiveVoiceDictionaryIfDirty(self):
		if not self._isDirty:
			return
		liveDict = speechDictHandler.dictionaries.get("voice")
		if liveDict is None:
			return
		liveFileName = getattr(liveDict, "fileName", None)
		if not liveFileName or (
			os.path.normcase(os.path.abspath(liveFileName)) != os.path.normcase(os.path.abspath(self._filePath))
		):
			return
		try:
			liveDict.load(self._filePath)
		except OSError as reloadError:
			logHandler.log.debug(
				f"DictionaryDisplayLite: Failed to reload live voice dictionary - {reloadError}"
			)

	def _cleanupTimers(self):
		if self._searchAnnounceTimer is not None:
			self._searchAnnounceTimer.Stop()
			self._searchAnnounceTimer = None

	def _onOk(self, evt):
		self._cleanupTimers()
		self._reloadLiveVoiceDictionaryIfDirty()
		evt.Skip()

	def _onCancelButton(self, evt):
		self._cleanupTimers()
		self._reloadLiveVoiceDictionaryIfDirty()
		evt.Skip()

	def _onCloseEvent(self, evt):
		self._cleanupTimers()
		self._reloadLiveVoiceDictionaryIfDirty()
		self.EndModal(wx.ID_CANCEL)


class DictionaryEntryEditDialog(wx.Dialog):
	"""
	Per-entry Add/Edit sub-dialog opened by DictionaryEditorDialog, mirroring
	NVDA's own real speech dictionary dialogs (Add/Edit each open a small
	dedicated entry-editing dialog rather than exposing pattern/replace
	fields directly on the main list dialog). See DictionaryEditorDialog's
	docstring for why this structure was chosen.

	isNew=True (Add) starts with blank Pattern/Replace, Case sensitive
	unchecked, the first available Type selected, and a Line number field
	set to defaultLineNumber (the caller works out the real "insert after
	the last entry" line, accounting for comment lines - see
	DictionaryEditorDialog._onAdd).
	isNew=False (Edit) starts pre-filled from existingEntry/
	existingLineNumber. Changing the line number and confirming moves the
	entry to that position rather than overwriting whatever was already
	there - the caller (DictionaryEditorDialog._insertEntryAtLineNumber)
	does the actual reordering; this dialog only reports back the desired
	pattern/replace/case/type/line-number as resultEntry/resultLineNumber.
	"""

	def __init__(self, parent, typeChoices, defaultLineNumber, isNew, existingEntry=None, existingLineNumber=None):
		# Translators: Titles of the add/edit voice dictionary entry dialog.
		title = _("Add Dictionary Entry") if isNew else _("Edit Dictionary Entry")
		super().__init__(parent, title=title)
		self._typeChoices = typeChoices
		self._originalComment = existingEntry.comment if (existingEntry is not None) else ""
		self._originalEnabled = existingEntry.isEnabled if (existingEntry is not None) else True
		self._originalLeadingLines = (
			list(existingEntry.leadingLines)
			if (existingEntry is not None and existingEntry.leadingLines is not None)
			else None
		)
		self.resultEntry = None
		self.resultLineNumber = None

		sizerHelper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

		# Translators: Label of the pattern edit field in the voice dictionary entry dialog.
		self._patternEdit = sizerHelper.addLabeledControl(_("&Pattern:"), wx.TextCtrl)
		# Translators: Label of the replacement edit field in the voice dictionary entry dialog.
		self._replaceEdit = sizerHelper.addLabeledControl(_("Rep&lace:"), wx.TextCtrl)
		self._caseSensitiveCheckbox = sizerHelper.addItem(
			# Translators: Checkbox for whether the entry's pattern is case sensitive.
			wx.CheckBox(self, label=_("Case &sensitive"))
		)
		self._typeRadioBox = sizerHelper.addItem(
			wx.RadioBox(
				self,
				# Translators: Label of the entry-type radio group in the voice dictionary entry dialog.
				label=_("Type"),
				choices=[choiceLabel for _choiceValue, choiceLabel in typeChoices],
			)
		)
		# Translators: Label of the line-number field in the voice dictionary entry dialog.
		self._lineNumberEdit = sizerHelper.addLabeledControl(_("&Line number:"), wx.TextCtrl)

		if isNew:
			self._caseSensitiveCheckbox.SetValue(False)
			self._typeRadioBox.SetSelection(0)
			self._lineNumberEdit.SetValue(str(defaultLineNumber))
		else:
			self._patternEdit.SetValue(existingEntry.pattern)
			self._replaceEdit.SetValue(existingEntry.replacement)
			self._caseSensitiveCheckbox.SetValue(bool(existingEntry.caseSensitive))
			for choiceIndex, (choiceValue, _choiceLabel) in enumerate(typeChoices):
				if choiceValue == existingEntry.type:
					self._typeRadioBox.SetSelection(choiceIndex)
					break
			self._lineNumberEdit.SetValue(str(existingLineNumber))

		sizerHelper.addItem(self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.SetSizerAndFit(sizerHelper.sizer)

		self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)
		wx.CallAfter(self._patternEdit.SetFocus)

	def _onOk(self, evt):
		pattern = self._patternEdit.GetValue()
		if not pattern:
			# Translators: Reported when OK is pressed with an empty pattern.
			ui.message(_("The pattern cannot be empty"))
			return
		try:
			lineNumber = int(self._lineNumberEdit.GetValue())
		except ValueError:
			# Translators: Reported when the line-number field does not contain a whole number.
			ui.message(_("Line number must be a whole number"))
			return
		if lineNumber < 1:
			# Translators: Reported when the line-number field is less than 1.
			ui.message(_("Line number must be 1 or greater"))
			return

		replacement = self._replaceEdit.GetValue()
		caseSensitive = self._caseSensitiveCheckbox.GetValue()
		typeIndex = self._typeRadioBox.GetSelection()
		entryType = self._typeChoices[typeIndex][0] if typeIndex != wx.NOT_FOUND else self._typeChoices[0][0]
		try:
			speechDictHandler.SpeechDictEntry(
				pattern, replacement, self._originalComment, caseSensitive=caseSensitive, type=entryType
			)
		except re.error as regexError:
			# Translators: {error} is the underlying regular expression error message.
			ui.message(_("Invalid regular expression: {error}").format(error=regexError))
			return

		self.resultEntry = _DictionaryRow(
			pattern,
			replacement,
			self._originalComment,
			caseSensitive,
			entryType,
			self._originalLeadingLines,
			isEnabled=self._originalEnabled,
		)
		self.resultLineNumber = lineNumber
		# Skip lets the stock OK button's default handling run too, which is
		# what actually calls EndModal(wx.ID_OK) for a CreateButtonSizer button.
		evt.Skip()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	# Translators: Category name shown for this add-on's commands in the Input Gestures dialog.
	scriptCategory = _("DictionaryDisplayLite")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self._isDictionaryDialogActive = False
		self._dictionaryTapCount = 0
		self._dictionaryTapTimer = None
		self._quickMenuTapCount = 0
		self._quickMenuTapTimer = None
		self._settings = loadSettings()
		dictionaryCheckLauncher.resume()
		editorLink.setOpener(self._showEditorForFile)
		logHandler.log.info(_("DictionaryDisplayLite loaded in Watchdog mode"))

	def terminate(self):
		"""
		Safely release resources and reset state to prevent zombie states.
		"""
		self._isDictionaryDialogActive = False
		dictionaryCheckLauncher.shutdown()
		editorLink.clearOpener()
		if self._dictionaryTapTimer is not None:
			self._dictionaryTapTimer.Stop()
			self._dictionaryTapTimer = None
		if self._quickMenuTapTimer is not None:
			self._quickMenuTapTimer.Stop()
			self._quickMenuTapTimer = None
		super(GlobalPlugin, self).terminate()

	def event_foreground(self, foregroundObj, nextHandler):
		"""
		Watchdog trigger: Monitors top-level window changes to toggle the active state.
		"""
		try:
			# Default to sleeping state for non-dictionary windows
			self._isDictionaryDialogActive = False

			if foregroundObj and foregroundObj.role == controlTypes.Role.DIALOG:
				dialogTitle = foregroundObj.name or foregroundObj.windowText
				if dialogTitle:
					titleLower = dialogTitle.lower()
					if (_("dictionary") in titleLower or
						_("default") in titleLower or
						_("voice") in titleLower or
						_("temporary") in titleLower or
						"dictionary" in titleLower):
						# Wake state activated
						self._isDictionaryDialogActive = True

		except (RuntimeError, AttributeError, COMError) as foregroundCheckError:
			logHandler.log.debug(f"DictionaryDisplayLite: Foreground check aborted safely - {foregroundCheckError}")

		nextHandler()

	def event_gainFocus(self, focusedObj, nextHandler):
		"""
		Intercepts focus events. Uses O(1) early exit if the dictionary is not active
		or the user has disabled entry condensing in settings.
		"""
		# Early Exit: Watchdog is asleep, or the user turned condensing off.
		if not self._isDictionaryDialogActive or not self._settings.get("condenseEntries", True):
			return nextHandler()

		try:
			if focusedObj and focusedObj.role == controlTypes.Role.LISTITEM:
				originalName = focusedObj.name
				if originalName:
					modifiedName = self._condenseDictionaryEntry(originalName)
					if modifiedName and modifiedName != originalName:
						# Temporarily modify the object's name
						focusedObj.name = modifiedName
						try:
							# Pass to next handlers (including speech output)
							nextHandler()
						finally:
							# Strictly guarantee restoration of the original state
							focusedObj.name = originalName
						return

		except (RuntimeError, AttributeError, COMError) as focusError:
			logHandler.log.debug(f"DictionaryDisplayLite: Object mutation aborted safely - {focusError}")

		# Fallback to normal behavior if no modifications were made
		nextHandler()

	def _condenseDictionaryEntry(self, originalText):
		"""
		Removes excessive labels from a dictionary entry for concise output.
		"""
		entrySegments = originalText.split(';')
		extractedValues = []

		for segment in entrySegments:
			segment = segment.strip()
			if ':' in segment:
				_labelPart, parsedValue = segment.split(':', 1)
				extractedValues.append(parsedValue.strip())
			else:
				extractedValues.append(segment)

		condensedResult = ' '.join(extractedValues)
		condensedResult = re.sub(r'\s+', ' ', condensedResult).strip()

		if not condensedResult or condensedResult == originalText:
			return None

		return condensedResult

	# --- ctrl+shift+D: multi-tap dictionary-editor opener -------------------

	@script(
		description=_(
			# Translators: Input help mode message for the dictionary quick-open gesture.
			"Press once to open the Voice dictionary, twice for the Default dictionary, "
			"or three times for the Temporary dictionary"
		),
		gesture="kb:control+shift+d",
	)
	def script_openSpeechDictionaryByTapCount(self, gesture):
		if self._dictionaryTapTimer is not None:
			self._dictionaryTapTimer.Stop()
		self._dictionaryTapCount += 1
		self._dictionaryTapTimer = core.callLater(
			DICTIONARY_TAP_WINDOW_MS,
			self._openSpeechDictionaryDialog,
		)

	def _openSpeechDictionaryDialog(self):
		tapCount = self._dictionaryTapCount
		self._dictionaryTapCount = 0
		self._dictionaryTapTimer = None

		if tapCount == 1:
			gui.mainFrame.onVoiceDictionaryCommand(None)
		elif tapCount == 2:
			gui.mainFrame.onDefaultDictionaryCommand(None)
		else:
			gui.mainFrame.onTemporaryDictionaryCommand(None)

	# --- shift+windows+D: quick menu (1 tap) / dictionary editor (2 taps) / validation (3 taps) ---

	@script(
		description=_(
			# Translators: Input help mode message for the DictionaryDisplayLite quick menu gesture.
			"Press once to open the DictionaryDisplayLite quick menu, twice to "
			"open Search and Edit Voice Dictionary directly, or three times to "
			"validate the speech dictionary of the current synthesizer"
		),
		gesture="kb:shift+windows+d",
	)
	def script_openQuickMenu(self, gesture):
		if self._quickMenuTapTimer is not None:
			self._quickMenuTapTimer.Stop()
		self._quickMenuTapCount += 1
		self._quickMenuTapTimer = core.callLater(
			DICTIONARY_TAP_WINDOW_MS,
			self._dispatchQuickMenuGesture,
		)

	def _dispatchQuickMenuGesture(self):
		tapCount = self._quickMenuTapCount
		self._quickMenuTapCount = 0
		self._quickMenuTapTimer = None
		if tapCount >= 3:
			wx.CallAfter(dictionaryCheckLauncher.startValidation)
		elif tapCount == 2:
			wx.CallAfter(self._openDictionaryEditor)
		else:
			wx.CallAfter(self._showQuickMenu, self._buildQuickMenuData())

	def _buildQuickMenuData(self):
		dictionaryLabels = (
			("voice", _("Voice dictionary")),
			("default", _("Default dictionary")),
			("temp", _("Temporary dictionary")),
		)
		fileSubmenu = [
			{
				"label": displayLabel,
				"action": (
					lambda dictType=dictType, displayLabel=displayLabel: self._openDictionaryFile(dictType, displayLabel)
				),
			}
			for dictType, displayLabel in dictionaryLabels
		]
		folderSubmenu = [
			{
				"label": displayLabel,
				"action": (
					lambda dictType=dictType, displayLabel=displayLabel: self._openDictionaryFolder(dictType, displayLabel)
				),
			}
			for dictType, displayLabel in dictionaryLabels
		]
		# Order per request: file, folder, check error, validate, editor, settings last.
		return [
			{"label": _("Open dictionary file"), "submenu": fileSubmenu},
			{"label": _("Open dictionary folder"), "submenu": folderSubmenu},
			# Translators: Item in the DictionaryDisplayLite quick menu.
			{"label": _("Check dictionary error"), "action": self._checkDictionaryErrors},
			# Translators: Item in the DictionaryDisplayLite quick menu that validates the speech dictionary of the current synthesizer.
			{"label": _("Validate synthesizer dictionary"), "action": dictionaryCheckLauncher.startValidation},
			# Translators: Item in the DictionaryDisplayLite quick menu.
			{"label": _("Search and Edit Voice Dictionary"), "action": self._openDictionaryEditor},
			{"label": _("DictionaryDisplayLite Settings"), "action": self._openSettingsDialog},
		]

	@staticmethod
	def _showQuickMenu(menuData):
		gui.mainFrame.prePopup()
		quickMenu = QuickMenu(menuData)
		try:
			quickMenu.ShowModal()
		finally:
			quickMenu.Destroy()
			gui.mainFrame.postPopup()

	@staticmethod
	def _resolveDictionaryFilePath(dictType):
		"""
		Reads the real, already-resolved path NVDA itself uses for this
		dictionary, rather than reconstructing it, since the on-disk layout
		varies between portable/installed and 32/64-bit NVDA setups.
		Returns None if this dictionary type has never had a file resolved
		(this is the normal, expected case for the temporary dictionary,
		which is session-only and is never saved to disk).
		"""
		speechDict = speechDictHandler.dictionaries.get(dictType)
		if speechDict is None:
			return None
		return getattr(speechDict, "fileName", None)

	def _openDictionaryFile(self, dictType, displayLabel):
		filePath = self._resolveDictionaryFilePath(dictType)
		if not filePath or not os.path.isfile(filePath):
			ui.message(
				# Translators: Reported when a dictionary has no file on disk yet.
				# {label} is replaced with the dictionary's name, e.g. Temporary dictionary.
				_("{label} has no file on disk yet").format(label=displayLabel)
			)
			return
		try:
			os.startfile(filePath)
		except OSError as openError:
			logHandler.log.debug(f"DictionaryDisplayLite: Failed to open dictionary file - {openError}")
			# Translators: Reported when the dictionary file could not be opened.
			ui.message(_("Could not open the dictionary file"))

	def _openDictionaryFolder(self, dictType, displayLabel):
		filePath = self._resolveDictionaryFilePath(dictType)
		folderPath = os.path.dirname(filePath) if filePath else None
		if not folderPath or not os.path.isdir(folderPath):
			ui.message(
				# Translators: Reported when a dictionary's folder does not exist yet.
				# {label} is replaced with the dictionary's name, e.g. Temporary dictionary.
				_("{label} has no folder on disk yet").format(label=displayLabel)
			)
			return
		try:
			os.startfile(folderPath)
		except OSError as openError:
			logHandler.log.debug(f"DictionaryDisplayLite: Failed to open dictionary folder - {openError}")
			# Translators: Reported when the dictionary folder could not be opened.
			ui.message(_("Could not open the dictionary folder"))

	def _checkDictionaryErrors(self):
		# Translators: Reported when the dictionary error check starts.
		ui.message(_("Checking dictionaries for errors, please wait"))
		threading.Thread(target=self._runDictionaryErrorCheck, daemon=True).start()

	def _runDictionaryErrorCheck(self):
		"""
		Runs off the main thread: reads the voice and default dictionary files
		directly from disk and re-validates them, since NVDA's own loader
		silently drops entries with invalid regular expressions rather than
		surfacing them to the user (only a log warning is written). The
		report file is only written and opened when a problem is actually
		found; a clean result is reported via a UI message alone.
		"""
		reportSections = []
		checkedAnyFile = False
		foundAnyIssue = False

		for dictType, displayLabel in (
			("voice", _("Voice dictionary")),
			("default", _("Default dictionary")),
		):
			filePath = self._resolveDictionaryFilePath(dictType)
			if not filePath or not os.path.isfile(filePath):
				continue
			checkedAnyFile = True
			issues = self._scanDictionaryFile(filePath)
			if issues:
				foundAnyIssue = True
				reportSections.append(f"=== {displayLabel} ({filePath}) ===\n" + "\n".join(issues))

		if not checkedAnyFile:
			# Translators: Reported when no dictionary file exists to check.
			wx.CallAfter(ui.message, _("No dictionary file was found to check"))
			return

		if not foundAnyIssue:
			# Translators: Reported when the dictionary check finds no problems.
			wx.CallAfter(ui.message, _("Dictionary check complete. No problems were found"))
			return

		reportText = "\n\n".join(reportSections)
		reportDir = os.path.join(globalVars.appArgs.configPath, CONFIG_SUBFOLDER)
		reportPath = os.path.join(reportDir, "dictionary_error_report.txt")
		try:
			os.makedirs(reportDir, exist_ok=True)
			with open(reportPath, "w", encoding="utf-8") as reportFile:
				reportFile.write(reportText)
		except OSError as writeError:
			logHandler.log.debug(f"DictionaryDisplayLite: Failed to write error report - {writeError}")
			# Translators: Reported when the dictionary error report could not be written.
			wx.CallAfter(ui.message, _("Could not write the dictionary error report"))
			return

		def _reportReady():
			# Translators: Reported when the dictionary check finds problems.
			ui.message(_("Dictionary check complete. Problems were found, opening the report"))
			try:
				os.startfile(reportPath)
			except OSError as openError:
				logHandler.log.debug(f"DictionaryDisplayLite: Failed to open error report - {openError}")
				# Translators: Reported when the dictionary error report could not be opened.
				ui.message(_("Could not open the dictionary error report"))

		wx.CallAfter(_reportReady)

	@staticmethod
	def _scanDictionaryFile(filePath):
		"""
		Independently re-parses a .dic file line by line, mirroring the
		on-disk format NVDA's own speechDictHandler.SpeechDict.load uses
		(tab-separated pattern/replacement/caseSensitive/type, '#'-prefixed
		comment lines), and validates each entry's pattern. Re-parsing the
		raw file - rather than trusting speechDictHandler.dictionaries[...] -
		is what lets this catch entries NVDA's own loader already silently
		dropped for having invalid regular expressions.
		"""
		issues = []
		try:
			with open(filePath, "r", encoding="utf-8-sig", errors="replace") as dictFile:
				lines = dictFile.readlines()
		except OSError as readError:
			# Translators: {error} is the underlying OS error message.
			return [_("Could not read this dictionary file: {error}").format(error=readError)]

		for lineNumber, rawLine in enumerate(lines, start=1):
			line = rawLine.rstrip("\r\n")
			if not line or line.startswith("#"):
				continue

			fields = line.split("\t")
			if len(fields) != 4:
				issues.append(
					# Translators: {fieldCount} and {lineNumber} are numbers.
					_("Malformed entry (expected 4 tab-separated fields, found {fieldCount}) (line {lineNumber})").format(
						fieldCount=len(fields), lineNumber=lineNumber
					)
				)
				continue

			pattern, _replacementField, caseSensitiveFlag, typeFlag = fields

			if not pattern:
				# Translators: {lineNumber} is a number.
				issues.append(_("Empty pattern (line {lineNumber})").format(lineNumber=lineNumber))
				continue

			if typeFlag not in _getValidEntryTypeValuesAsStrings():
				issues.append(
					# Translators: {typeFlag} and {lineNumber} identify the problem entry.
					_("Unrecognized entry type \"{typeFlag}\" (line {lineNumber})").format(
						typeFlag=typeFlag, lineNumber=lineNumber
					)
				)
			if caseSensitiveFlag not in ("0", "1"):
				issues.append(
					# Translators: {lineNumber} identifies the problem entry.
					_("Unrecognized case-sensitivity flag (line {lineNumber})").format(lineNumber=lineNumber)
				)

			# Only entries of the actual ENTRY_TYPE_REGEXP type are used as
			# raw regular expressions by NVDA. Other entry types are
			# re.escape()-d internally before compiling, so checking their
			# raw literal text as regex here would produce false positives.
			# Read via the legacy module constant rather than the new enum,
			# since that constant is kept working via a compatibility shim
			# on modernized NVDA installations too (confirmed during
			# Zero-Trust verification), so this works across all versions.
			if typeFlag == str(speechDictHandler.ENTRY_TYPE_REGEXP):
				try:
					re.compile(pattern)
				except re.error as regexError:
					issues.append(
						# Translators: {pattern}, {error}, and {lineNumber} identify the problem entry.
						_("Invalid regular expression \"{pattern}\" - {error} (line {lineNumber})").format(
							pattern=pattern, error=regexError, lineNumber=lineNumber
						)
					)

		return issues

	def _openDictionaryEditor(self):
		# Reached only via wx.CallAfter (see QuickMenu._onActivate), so
		# ShowModal() here is safe - same reasoning as _openSettingsDialog.
		filePath = self._resolveDictionaryFilePath("voice")
		if not filePath:
			# Translators: Reported when there is no voice dictionary to edit.
			ui.message(_("No voice dictionary is available to edit"))
			return
		self._showEditorForFile(filePath, 0)

	def _showEditorForFile(self, filePath, initialLine=0):
		"""
		Opens the editor on filePath, selecting the entry at initialLine when
		given. Returns True when the file was changed. Must run on the main
		thread, reached through wx.CallAfter.
		"""
		if not filePath or not os.path.isfile(filePath):
			# Translators: Reported when the dictionary file to edit does not exist.
			ui.message(_("The dictionary file was not found"))
			return False
		gui.mainFrame.prePopup()
		editorDialog = None
		try:
			editorDialog = DictionaryEditorDialog(gui.mainFrame, filePath, initialLine)
			editorDialog.ShowModal()
			return editorDialog.isDirty
		except (OSError, UnicodeDecodeError) as loadError:
			logHandler.log.debug(f"DictionaryDisplayLite: Could not open dictionary in editor - {loadError}")
			# Translators: Reported when the dictionary file could not be read for editing.
			ui.message(_("Could not read the dictionary file. Make sure it is saved as UTF-8"))
			return False
		finally:
			if editorDialog is not None:
				editorDialog.Destroy()
			gui.mainFrame.postPopup()

	def _openSettingsDialog(self):
		# Reached only via wx.CallAfter (see QuickMenu._onActivate), so
		# ShowModal() here is safe - see DictionaryDisplayLiteSettingsDialog's
		# docstring for why that distinction matters.
		gui.mainFrame.prePopup()
		settingsDialog = DictionaryDisplayLiteSettingsDialog(
			gui.mainFrame,
			self._settings,
			self._onSettingsApplied,
		)
		try:
			settingsDialog.ShowModal()
		finally:
			settingsDialog.Destroy()
			gui.mainFrame.postPopup()

	def _onSettingsApplied(self, updatedSettings):
		self._settings.update(updatedSettings)
		saveSettings(self._settings)
