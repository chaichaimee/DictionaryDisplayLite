# launcher.py

import functools
import os
import threading

import wx
import gui
import tones
import ui
import addonHandler
import logHandler

from . import core, filterSettings, locate, report, reportDialog

addonHandler.initTranslation()
try:
	_ = addonHandler.getTranslation()
except Exception:
	def _(x): return x

_isRunning = False
_isShutDown = False


def resume():
	global _isRunning, _isShutDown
	_isRunning = False
	_isShutDown = False


def shutdown():
	global _isShutDown
	_isShutDown = True
	reportDialog.closeResultDialog()


def _askForDictionaryFile(folder):
	defaultDir = folder if os.path.isdir(folder) else ""
	gui.mainFrame.prePopup()
	try:
		with wx.FileDialog(
			gui.mainFrame,
			message=_("Select the speech dictionary file to check"),
			defaultDir=defaultDir,
			wildcard="Dictionary files (*.dic;*.txt)|*.dic;*.txt|All files (*.*)|*.*",
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as openDialog:
			if openDialog.ShowModal() != wx.ID_OK:
				return ""
			return openDialog.GetPath()
	finally:
		gui.mainFrame.postPopup()


def startValidation(path=""):
	global _isRunning
	if _isRunning:
		ui.message(_("Dictionary check is already running"))
		return
	if not path:
		path, folder = locate.findActiveDictionary()
		if not path:
			path = _askForDictionaryFile(folder)
	if not path:
		return
	_isRunning = True
	ui.message(_("Checking dictionary"))
	threading.Thread(
		target=_validateInBackground, args=(path,), name="DictionaryDisplayLite.dictionaryCheck", daemon=True
	).start()


def _validateInBackground(path):
	try:
		result = core.validate_dictionary(path)
	except Exception:
		logHandler.log.exception("DictionaryDisplayLite: dictionary check failed for {}".format(path))
		wx.CallAfter(_onFailure)
		return
	filterSettings.getExcludedCodes()
	wx.CallAfter(functools.partial(_onResult, result))


def _onFailure():
	global _isRunning
	_isRunning = False
	if _isShutDown:
		return
	tones.beep(300, 200)
	ui.message(_("Dictionary check failed. See the NVDA log for details"))


def _onResult(result):
	global _isRunning
	_isRunning = False
	if _isShutDown:
		return
	reportDialog.closeResultDialog()
	visibleResult = filterSettings.applyExclusions(result, filterSettings.getExcludedCodes())
	report.logResult(visibleResult, logHandler.log)
	summary = visibleResult["summary"]
	announcement = _(
		"Dictionary check finished. {rules} rules checked: {critical} critical, {high} high, {medium} medium, {low} low"
	).format(
		rules=result["parsed_rules"], critical=summary["critical"], high=summary["high"],
		medium=summary["medium"], low=summary["low"],
	)
	if visibleResult["hidden"]:
		announcement += _(". {count} hidden by your issue type filter").format(count=visibleResult["hidden"])
	if not result["summary"]["total"]:
		tones.beep(1000, 100)
		ui.message(announcement)
		return
	if summary["total"]:
		tones.beep(400, 150)
	else:
		tones.beep(1000, 100)
	ui.message(announcement)
	reportDialog.showResultDialog(result)
