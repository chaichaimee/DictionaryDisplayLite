# entryTraceDialog.py

import wx
import api
import core
import gui
import tones
import ui
import addonHandler
import logHandler

from . import editorLink, entryTrace, filterSettings

addonHandler.initTranslation()
try:
	_ = addonHandler.getTranslation()
except Exception:
	def _(x): return x

FILTER_DELAY_MS = 350
ANNOUNCE_DELAY_MS = 450

_instance = None


class EntryTraceDialog(wx.Dialog):
	def __init__(self, parent, text):
		super().__init__(
			parent,
			title=_("Find dictionary entries for the selected text"),
			size=(1000, 720),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
		)
		self._result = None
		self._visibleSteps = []
		self._filterTimer = None
		self._announceTimer = None
		self._showLineNumber = filterSettings.getShowLineNumber()

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		textLabel = wx.StaticText(self, label=_("&Text to check"))
		mainSizer.Add(textLabel, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
		self.textBox = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE, size=(-1, 90))
		mainSizer.Add(self.textBox, 0, wx.EXPAND | wx.ALL, 10)

		self.checkButton = wx.Button(self, label=_("&Check"))
		mainSizer.Add(self.checkButton, 0, wx.LEFT | wx.RIGHT, 10)

		filterLabel = wx.StaticText(self, label=_("&Show only entries containing this word (optional)"))
		mainSizer.Add(filterLabel, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
		self.filterBox = wx.TextCtrl(self)
		mainSizer.Add(self.filterBox, 0, wx.EXPAND | wx.ALL, 10)

		self.lineNumberCheckBox = wx.CheckBox(self, label=_("Show &line number"))
		self.lineNumberCheckBox.SetValue(self._showLineNumber)
		mainSizer.Add(self.lineNumberCheckBox, 0, wx.LEFT | wx.RIGHT, 10)

		listLabel = wx.StaticText(self, label=_("&Entries that change this text, in the order NVDA applies them"))
		mainSizer.Add(listLabel, 0, wx.LEFT | wx.RIGHT, 10)
		self.entryList = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
		columnLabels = (_("No."), _("Dictionary"), _("Line"), _("Pattern"), _("Matched"), _("Becomes"))
		columnWidths = (50, 200, 60, 220, 200, 220)
		for index, (label, width) in enumerate(zip(columnLabels, columnWidths)):
			self.entryList.InsertColumn(index, label, width=width)
		self._applyLineColumn()
		mainSizer.Add(self.entryList, 1, wx.EXPAND | wx.ALL, 10)

		detailLabel = wx.StaticText(self, label=_("&Details of the selected entry"))
		mainSizer.Add(detailLabel, 0, wx.LEFT | wx.RIGHT, 10)
		self.detailBox = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
		mainSizer.Add(self.detailBox, 0, wx.EXPAND | wx.ALL, 10)

		finalLabel = wx.StaticText(self, label=_("Text after all &dictionaries"))
		mainSizer.Add(finalLabel, 0, wx.LEFT | wx.RIGHT, 10)
		self.finalBox = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 70))
		mainSizer.Add(self.finalBox, 0, wx.EXPAND | wx.ALL, 10)

		buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.editButton = wx.Button(self, label=_("&Edit entry"))
		copyButton = wx.Button(self, label=_("Copy &report"))
		closeButton = wx.Button(self, id=wx.ID_CLOSE, label=_("Close"))
		for button in (self.editButton, copyButton, closeButton):
			buttonSizer.Add(button, 0, wx.RIGHT, 10)
		mainSizer.Add(buttonSizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		self.SetSizer(mainSizer)
		self.SetEscapeId(wx.ID_CLOSE)

		self.checkButton.Bind(wx.EVT_BUTTON, self.onCheck)
		self.filterBox.Bind(wx.EVT_TEXT, self.onFilterChanged)
		self.lineNumberCheckBox.Bind(wx.EVT_CHECKBOX, self.onLineNumberToggled)
		self.entryList.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onSelectionChanged)
		self.entryList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onEdit)
		self.entryList.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.onRightClick)
		self.editButton.Bind(wx.EVT_BUTTON, self.onEdit)
		copyButton.Bind(wx.EVT_BUTTON, self.onCopyReport)
		closeButton.Bind(wx.EVT_BUTTON, lambda event: self.Close())
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.CenterOnScreen()

	def runCheck(self):
		text = self.textBox.GetValue()
		try:
			self._result = entryTrace.runTrace(text)
		except (OSError, RuntimeError, AttributeError, KeyError, TypeError):
			logHandler.log.exception("DictionaryDisplayLite: dictionary entry check failed")
			self._result = None
			self._fillList()
			ui.message(_("The dictionary entry check failed. See the NVDA log for details"))
			return
		self.finalBox.SetValue(self._result.finalText)
		self._fillList()
		self._announceSummary(delay=ANNOUNCE_DELAY_MS)

	def _fillList(self):
		self.entryList.DeleteAllItems()
		self.detailBox.SetValue("")
		if self._result is None:
			self._visibleSteps = []
			return
		self._visibleSteps = entryTrace.filterSteps(self._result.steps, self.filterBox.GetValue())
		for row, step in enumerate(self._visibleSteps):
			entry = step.entry
			number = self._result.steps.index(step) + 1
			self.entryList.InsertItem(row, str(number))
			values = (
				entry.source.label,
				self._lineText(entry),
				entry.pattern,
				" | ".join(step.matchedTexts),
				" | ".join(step.resultTexts),
			)
			for column, value in enumerate(values, 1):
				self.entryList.SetItem(row, column, value)
		self.SetTitle(_("Dictionary entries for the text: {count} found").format(count=len(self._visibleSteps)))
		if self._visibleSteps:
			self.entryList.Select(0)
			self.entryList.Focus(0)
		self.editButton.Enable(bool(self._visibleSteps))

	def _lineText(self, entry):
		if not self._showLineNumber or not entry.lineNumber:
			return ""
		return str(entry.lineNumber)

	def _applyLineColumn(self):
		self.entryList.SetColumnWidth(2, 60 if self._showLineNumber else 0)
		for row, step in enumerate(self._visibleSteps):
			self.entryList.SetItem(row, 2, self._lineText(step.entry))

	def onLineNumberToggled(self, event):
		self._showLineNumber = self.lineNumberCheckBox.GetValue()
		filterSettings.setShowLineNumber(self._showLineNumber)
		filterSettings.saveInBackground()
		self._applyLineColumn()

	def _announceSummary(self, delay):
		if self._announceTimer is not None:
			self._announceTimer.Stop()
		self._announceTimer = core.callLater(delay, self._speakSummary)

	def _speakSummary(self):
		self._announceTimer = None
		if self._result is None:
			return
		if not self._result.isProcessingEnabled:
			ui.message(_("Speech dictionary processing is turned off in NVDA"))
			return
		count = len(self._visibleSteps)
		if count:
			ui.message(_("{count} dictionary entries change this text").format(count=count))
			return
		if self._result.steps:
			ui.message(_("No entry contains that word"))
			return
		ui.message(_(
			"No dictionary entry changes this text. If it is still pronounced wrongly, "
			"the cause is outside the dictionaries"
		))

	def _getSelectedStep(self):
		index = self.entryList.GetFirstSelected()
		if index < 0 or index >= len(self._visibleSteps):
			return None
		return self._visibleSteps[index]

	def onCheck(self, event):
		self.runCheck()
		if self._visibleSteps:
			self.entryList.SetFocus()
		else:
			self.textBox.SetFocus()

	def onFilterChanged(self, event):
		if self._filterTimer is not None:
			self._filterTimer.Stop()
		self._filterTimer = core.callLater(FILTER_DELAY_MS, self._applyFilter)

	def _applyFilter(self):
		self._filterTimer = None
		self._fillList()
		self._announceSummary(delay=0)

	def onSelectionChanged(self, event):
		step = self._getSelectedStep()
		self.detailBox.SetValue(entryTrace.formatStepDetails(step) if step is not None else "")
		event.Skip()

	def onCharHook(self, event):
		keyCode = event.GetKeyCode()
		isMenuKey = keyCode == wx.WXK_WINDOWS_MENU or (keyCode == wx.WXK_F10 and event.ShiftDown())
		if isMenuKey and self.FindFocus() is self.entryList:
			self._showEntryMenu()
			return
		event.Skip()

	def onRightClick(self, event):
		self._showEntryMenu()

	def _showEntryMenu(self):
		step = self._getSelectedStep()
		if step is None:
			return
		menu = wx.Menu()
		# Translators: Context menu item that opens the dictionary editor on the line of the selected entry.
		editItem = menu.Append(wx.ID_ANY, _("&Edit in dictionary editor"))
		editItem.Enable(step.entry.source.isEditable and step.entry.lineNumber >= 1)
		# Translators: Context menu item that copies the dictionary line of the selected entry.
		copyItem = menu.Append(wx.ID_ANY, _("&Copy dictionary line"))
		self.Bind(wx.EVT_MENU, lambda event: wx.CallAfter(self._editStep, step), editItem)
		self.Bind(wx.EVT_MENU, lambda event: self._copyLine(step), copyItem)
		self.PopupMenu(menu)
		menu.Destroy()

	def _copyLine(self, step):
		api.copyToClip(step.entry.rawLine)
		tones.beep(800, 100)
		ui.message(_("Dictionary line copied to clipboard"))

	def onEdit(self, event):
		step = self._getSelectedStep()
		if step is None:
			return
		wx.CallAfter(self._editStep, step)

	def _editStep(self, step):
		entry = step.entry
		if not entry.source.isEditable or entry.lineNumber < 1:
			ui.message(_("This entry cannot be edited here"))
			return
		changed = editorLink.openAtLine(entry.source.filePath, entry.lineNumber)
		if changed is None:
			ui.message(_("The dictionary editor is not available"))
			return
		if changed:
			self.runCheck()
			self.entryList.SetFocus()

	def onCopyReport(self, event):
		if self._result is None:
			return
		api.copyToClip(entryTrace.formatReport(self._result))
		tones.beep(800, 100)
		ui.message(_("Report copied to clipboard"))

	def onClose(self, event):
		global _instance
		_instance = None
		for timer in (self._filterTimer, self._announceTimer):
			if timer is not None:
				timer.Stop()
		self._filterTimer = None
		self._announceTimer = None
		self.Destroy()


def showEntryTraceDialog(text):
	global _instance
	closeEntryTraceDialog()
	_instance = EntryTraceDialog(gui.mainFrame, text)
	_instance.Show()
	_instance.Raise()
	_instance.runCheck()
	if _instance._visibleSteps:
		_instance.entryList.SetFocus()
	else:
		_instance.textBox.SetFocus()


def closeEntryTraceDialog():
	if _instance is None:
		return
	try:
		_instance.Close()
	except RuntimeError:
		logHandler.log.debug("DictionaryDisplayLite: entry check window was already destroyed")
