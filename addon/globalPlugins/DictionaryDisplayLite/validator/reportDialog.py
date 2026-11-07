# reportDialog.py

import os

import wx
import api
import core
import gui
import tones
import ui
import addonHandler
import logHandler

from . import editorLink, filterSettings, report

addonHandler.initTranslation()
try:
	_ = addonHandler.getTranslation()
except Exception:
	def _(x): return x

_instance = None
_lastExportFolder = ""


class ValidationResultDialog(wx.Dialog):
	def __init__(self, parent, result):
		visibleResult = filterSettings.applyExclusions(result, filterSettings.getExcludedCodes())
		super().__init__(
			parent,
			title=_("Dictionary Check: {count} issue(s)").format(count=visibleResult["summary"]["total"]),
			size=(1000, 700),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
		)
		self.fullResult = result
		self.result = visibleResult
		self._filterChanged = False
		self._filterAnnounceTimer = None
		self._showDescription = filterSettings.getShowDescription()
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.headerLabel = wx.StaticText(self, label=report.formatHeader(self.result))
		mainSizer.Add(self.headerLabel, 0, wx.EXPAND | wx.ALL, 10)

		filterLabel = wx.StaticText(self, label=_("Issue &types to show (uncheck a type to hide it)"))
		mainSizer.Add(filterLabel, 0, wx.LEFT | wx.RIGHT, 10)
		self.filterList = wx.CheckListBox(self, choices=[], size=(-1, 140))
		self._fillFilterList()
		mainSizer.Add(self.filterList, 0, wx.EXPAND | wx.ALL, 10)

		listLabel = wx.StaticText(self, label=_("&Issues"))
		mainSizer.Add(listLabel, 0, wx.LEFT | wx.RIGHT, 10)
		self.issueList = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
		columnWidths = (60, 220, 80, 200, 420, 320)
		columnLabels = (_("Line"), _("Pattern"), _("Severity"), _("Code"), _("Message"), _("Suggestion"))
		for index, (label, width) in enumerate(zip(columnLabels, columnWidths)):
			self.issueList.InsertColumn(index, label, width=width)
		self._fillList()
		self._applyDescriptionColumns()
		mainSizer.Add(self.issueList, 1, wx.EXPAND | wx.ALL, 10)

		buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
		showAllButton = wx.Button(self, label=_("Show &all types"))
		copyButton = wx.Button(self, label=_("&Copy Report"))
		exportButton = wx.Button(self, label=_("&Export CSV"))
		closeButton = wx.Button(self, id=wx.ID_CLOSE, label=_("Close"))
		for button in (showAllButton, copyButton, exportButton, closeButton):
			buttonSizer.Add(button, 0, wx.RIGHT, 10)
		mainSizer.Add(buttonSizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		self.descriptionCheckBox = wx.CheckBox(self, label=_("Show &description of each issue"))
		self.descriptionCheckBox.SetValue(self._showDescription)
		mainSizer.Add(self.descriptionCheckBox, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
		self.SetSizer(mainSizer)
		self.SetEscapeId(wx.ID_CLOSE)

		showAllButton.Bind(wx.EVT_BUTTON, self.onShowAll)
		self.descriptionCheckBox.Bind(wx.EVT_CHECKBOX, self.onDescriptionToggled)
		self.filterList.Bind(wx.EVT_CHECKLISTBOX, self.onFilterToggled)
		copyButton.Bind(wx.EVT_BUTTON, self.onCopy)
		exportButton.Bind(wx.EVT_BUTTON, self.onExport)
		closeButton.Bind(wx.EVT_BUTTON, lambda event: self.Close())
		self.issueList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onActivate)
		self.issueList.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.onRightClick)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.CenterOnScreen()

	def _fillFilterList(self):
		self._filterCounts = filterSettings.countByCode(self.fullResult)
		excluded = filterSettings.getExcludedCodes()
		knownCodes = set(filterSettings.ALL_CODES)
		extraCodes = (set(self._filterCounts) | set(excluded)) - knownCodes
		allCodes = sorted(knownCodes | extraCodes)
		self._filterCodes = (
			[code for code in allCodes if self._filterCounts.get(code)]
			+ [code for code in allCodes if not self._filterCounts.get(code)]
		)
		self._rebuildFilterList()

	def _rebuildFilterList(self, selectIndex=0):
		# The checked state is part of each item's text because the list does not
		# expose it to the screen reader on its own.
		excluded = filterSettings.getExcludedCodes()
		labels = []
		for code in self._filterCodes:
			state = _("not checked") if code in excluded else _("checked")
			labels.append("{} ({}), {}".format(code, self._filterCounts.get(code, 0), state))
		self.filterList.Set(labels)
		for index, code in enumerate(self._filterCodes):
			self.filterList.Check(index, code not in excluded)
		if 0 <= selectIndex < self.filterList.GetCount():
			self.filterList.SetSelection(selectIndex)

	def onFilterToggled(self, event):
		index = event.GetInt()
		excluded = set(filterSettings.getExcludedCodes())
		code = self._filterCodes[index]
		isChecked = self.filterList.IsChecked(index)
		if isChecked:
			excluded.discard(code)
		else:
			excluded.add(code)
		self._changeFilter(excluded)
		ui.message(_("checked") if isChecked else _("not checked"))
		wx.CallAfter(self._rebuildFilterList, index)

	def onShowAll(self, event):
		self._changeFilter(set())
		self._rebuildFilterList(0)
		self.filterList.SetFocus()

	def _changeFilter(self, excluded):
		filterSettings.setExcludedCodes(excluded)
		self._filterChanged = True
		self.result = filterSettings.applyExclusions(self.fullResult, excluded)
		self.issueList.DeleteAllItems()
		self._fillList()
		self.SetTitle(_("Dictionary Check: {count} issue(s)").format(count=self.result["summary"]["total"]))
		self.headerLabel.SetLabel(report.formatHeader(self.result))
		self.Layout()
		if self._filterAnnounceTimer is not None:
			self._filterAnnounceTimer.Stop()
		self._filterAnnounceTimer = core.callLater(400, self._announceShownCount)

	def _announceShownCount(self):
		self._filterAnnounceTimer = None
		ui.message(_("{count} issue(s) shown").format(count=self.result["summary"]["total"]))

	def onDescriptionToggled(self, event):
		self._showDescription = self.descriptionCheckBox.GetValue()
		filterSettings.setShowDescription(self._showDescription)
		self._filterChanged = True
		self.issueList.DeleteAllItems()
		self._fillList()
		self._applyDescriptionColumns()

	def _applyDescriptionColumns(self):
		self.issueList.SetColumnWidth(5, 320 if self._showDescription else 0)

	def _fillList(self):
		for row, issue in enumerate(self.result["issues"]):
			self.issueList.InsertItem(row, str(issue["line"]))
			if self._showDescription:
				message, suggestion = issue["message"], issue["suggestion"] or ""
			else:
				message, suggestion = report.shortMessage(issue["message"]), ""
			values = (report.issuePattern(issue), issue["severity"], issue["code"], message, suggestion)
			for column, value in enumerate(values, 1):
				self.issueList.SetItem(row, column, value)
		if self.issueList.GetItemCount():
			self.issueList.Select(0)
			self.issueList.Focus(0)

	def onActivate(self, event):
		self._openFileAtIssue(self.result["issues"][event.GetIndex()])

	def onCharHook(self, event):
		keyCode = event.GetKeyCode()
		isMenuKey = keyCode == wx.WXK_WINDOWS_MENU or (keyCode == wx.WXK_F10 and event.ShiftDown())
		if isMenuKey and self.FindFocus() is self.issueList:
			self._showIssueMenu(self.issueList.GetFirstSelected())
			return
		event.Skip()

	def onRightClick(self, event):
		self._showIssueMenu(event.GetIndex())

	def _showIssueMenu(self, index):
		if index < 0 or index >= len(self.result["issues"]):
			return
		self.issueList.Select(index)
		issue = self.result["issues"][index]
		menu = wx.Menu()
		# Translators: Context menu item that opens the dictionary editor on the line of the selected issue.
		editItem = menu.Append(wx.ID_ANY, _("&Edit in dictionary editor"))
		editItem.Enable(issue["line"] >= 1)
		# Translators: Context menu item that opens the dictionary file in its default program.
		openItem = menu.Append(wx.ID_ANY, _("&Open dictionary file"))
		# Translators: Context menu item that copies the selected issue to the clipboard.
		copyItem = menu.Append(wx.ID_ANY, _("&Copy this issue"))
		self.Bind(wx.EVT_MENU, lambda event: wx.CallAfter(self._openEditorAtIssue, issue), editItem)
		self.Bind(wx.EVT_MENU, lambda event: self._openFileAtIssue(issue), openItem)
		self.Bind(wx.EVT_MENU, lambda event: self._copyIssue(issue), copyItem)
		self.PopupMenu(menu)
		menu.Destroy()

	def _copyIssue(self, issue):
		api.copyToClip("\n".join(report.formatIssueLines(issue)) + "\n")
		tones.beep(800, 100)
		ui.message(_("Issue copied to clipboard"))

	def _openEditorAtIssue(self, issue):
		path = self.result["file"]
		changed = editorLink.openAtLine(path, issue["line"])
		if changed is None:
			ui.message(_("The dictionary editor is not available"))
			return
		if changed:
			from . import launcher
			launcher.startValidation(path)

	def _openFileAtIssue(self, issue):
		path = self.result["file"]
		if issue["line"] < 1 or not os.path.isfile(path):
			return
		try:
			os.startfile(path)
		except OSError:
			logHandler.log.exception("DictionaryDisplayLite: dictionary file could not be opened")
			ui.message(_("Failed to open the dictionary file"))
			return
		ui.message(_("Opened the dictionary file. Go to line {line}").format(line=issue["line"]))

	def onCopy(self, event):
		api.copyToClip(report.formatReportText(self.result))
		tones.beep(800, 100)
		ui.message(_("Report copied to clipboard"))

	def onExport(self, event):
		global _lastExportFolder
		defaultDir = _lastExportFolder or os.path.dirname(self.result["file"])
		gui.mainFrame.prePopup()
		try:
			with wx.FileDialog(
				self,
				message=_("Export CSV"),
				defaultDir=defaultDir,
				defaultFile="dictionary-check.csv",
				wildcard="CSV (*.csv)|*.csv",
				style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
			) as saveDialog:
				if saveDialog.ShowModal() != wx.ID_OK:
					return
				path = saveDialog.GetPath()
		finally:
			gui.mainFrame.postPopup()
		try:
			with open(path, "w", encoding="utf-8-sig", newline="") as handle:
				handle.write(report.toCsv(self.result))
		except OSError:
			logHandler.log.exception("DictionaryDisplayLite: CSV export failed")
			ui.message(_("Failed to export the CSV file"))
			return
		_lastExportFolder = os.path.dirname(path)
		tones.beep(800, 100)
		ui.message(_("Exported {count} issue(s) to {path}").format(count=len(self.result["issues"]), path=path))

	def onClose(self, event):
		global _instance
		_instance = None
		if self._filterAnnounceTimer is not None:
			self._filterAnnounceTimer.Stop()
			self._filterAnnounceTimer = None
		if self._filterChanged:
			filterSettings.saveInBackground()
		self.Destroy()


def showResultDialog(result):
	global _instance
	closeResultDialog()
	_instance = ValidationResultDialog(gui.mainFrame, result)
	_instance.Show()
	_instance.Raise()
	_instance.issueList.SetFocus()


def closeResultDialog():
	if _instance is None:
		return
	try:
		_instance.Close()
	except RuntimeError:
		logHandler.log.debug("DictionaryDisplayLite: dictionary result window was already destroyed")
