# __init__.py
# Copyright (C) 2026 Chai Chaimee
# Licensed under GNU General Public License. See COPYING.txt for details.

import os
import sys
import threading
import re
from comtypes import COMError

import addonHandler
import core
import globalPluginHandler
import controlTypes
import logHandler

addonHandler.initTranslation()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self._isDictionaryDialogActive = False
		logHandler.log.info(_("DictionaryDisplayLite loaded in Watchdog mode"))

	def terminate(self):
		"""
		Safely release resources and reset state to prevent zombie states.
		"""
		self._isDictionaryDialogActive = False
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
		Intercepts focus events. Uses O(1) early exit if the dictionary is not active.
		"""
		# Early Exit: Watchdog is asleep
		if not self._isDictionaryDialogActive:
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
				_, parsedValue = segment.split(':', 1)
				extractedValues.append(parsedValue.strip())
			else:
				extractedValues.append(segment)

		condensedResult = ' '.join(extractedValues)
		condensedResult = re.sub(r'\s+', ' ', condensedResult).strip()

		if not condensedResult or condensedResult == originalText:
			return None
			
		return condensedResult