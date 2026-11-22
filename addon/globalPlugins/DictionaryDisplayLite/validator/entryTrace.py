# entryTrace.py

import itertools
import os
import re

import globalVars
import logHandler
import addonHandler

addonHandler.initTranslation()
try:
	_ = addonHandler.getTranslation()
except Exception:
	def _(x): return x

MAX_MATCHES_PER_STEP = 20
REGEXP_ENTRY_TYPE = 1

_FALLBACK_TYPE_LABELS = {0: "Anywhere", 1: "Regular expression", 2: "Whole word"}

try:
	import regex as _regexModule
	_MATCH_ERRORS = (re.error, _regexModule.error, RecursionError, ValueError, IndexError)
except ImportError:
	_MATCH_ERRORS = (re.error, RecursionError, ValueError, IndexError)

# Raised while building one entry. NVDA's own loader skips an entry on any exception, so this mirrors it.
ENTRY_ERRORS = (Exception,)


class DictionarySource:
	def __init__(self, key, label, filePath, isEnabled, liveDictionary):
		self.key = key
		self.label = label
		self.filePath = filePath
		self.isEnabled = isEnabled
		self.liveDictionary = liveDictionary

	@property
	def isEditable(self):
		return bool(self.filePath) and self.key in ("voice", "default")


class TraceEntry:
	def __init__(self, source, lineNumber, entryObject, rawLine):
		self.source = source
		self.lineNumber = lineNumber
		self.entryObject = entryObject
		self.rawLine = rawLine

	@property
	def pattern(self):
		return self.entryObject.pattern

	@property
	def replacement(self):
		return self.entryObject.replacement

	@property
	def caseSensitive(self):
		return bool(self.entryObject.caseSensitive)

	@property
	def typeValue(self):
		return int(self.entryObject.type)

	@property
	def typeLabel(self):
		return getEntryTypeLabel(self.typeValue)


class TraceStep:
	def __init__(self, entry, matchedTexts, resultTexts, textBefore, textAfter):
		self.entry = entry
		self.matchedTexts = matchedTexts
		self.resultTexts = resultTexts
		self.textBefore = textBefore
		self.textAfter = textAfter

	@property
	def changedText(self):
		return self.textBefore != self.textAfter


class TraceResult:
	def __init__(self, inputText, finalText, steps, notes, skippedEntries, isProcessingEnabled):
		self.inputText = inputText
		self.finalText = finalText
		self.steps = steps
		self.notes = notes
		self.skippedEntries = skippedEntries
		self.isProcessingEnabled = isProcessingEnabled


def getEntryTypeLabel(typeValue):
	try:
		from speechDictHandler.types import EntryType
		return EntryType(typeValue).name.replace("_", " ").capitalize()
	except (ImportError, ValueError):
		return _FALLBACK_TYPE_LABELS.get(typeValue, str(typeValue))


def createSpeechDictEntry(pattern, replacement, comment, caseSensitive, typeValue):
	"""Builds an entry with NVDA's own class so matching behaves exactly like speech does."""
	try:
		from speechDictHandler.types import SpeechDictEntry, EntryType
	except ImportError:
		import speechDictHandler
		return speechDictHandler.SpeechDictEntry(
			pattern, replacement, comment, caseSensitive=caseSensitive, type=typeValue
		)
	return SpeechDictEntry(pattern, replacement, comment, caseSensitive=caseSensitive, type=EntryType(typeValue))


def _knownLabel(key):
	labels = {
		"temp": _("Temporary dictionary"),
		"voice": _("Voice dictionary"),
		"default": _("Default dictionary"),
		"builtin": _("Built-in dictionary"),
	}
	return labels.get(key, key)


def listDictionarySources():
	"""Returns every speech dictionary in the order NVDA applies them to spoken text."""
	import speechDictHandler
	listDefinitions = getattr(speechDictHandler, "listAvailableSpeechDictDefinitions", None)
	if listDefinitions is not None:
		sources = []
		for definition in listDefinitions():
			label = definition.displayName if definition.userVisible else _knownLabel(definition.name)
			sources.append(DictionarySource(
				str(definition.name), label, definition.path, bool(definition.enabled), definition.dictionary
			))
		return sources
	sources = []
	for key in speechDictHandler.dictTypes:
		liveDictionary = speechDictHandler.dictionaries.get(key)
		if liveDictionary is None:
			continue
		sources.append(DictionarySource(key, _knownLabel(key), getattr(liveDictionary, "fileName", None), True, liveDictionary))
	return sources


def getDictionarySource(key):
	for source in listDictionarySources():
		if source.key == key:
			return source
	return None


def getDictionaryFilePath(key):
	source = getDictionarySource(key)
	return source.filePath if source is not None else None


def getLiveDictionary(key):
	source = getDictionarySource(key)
	return source.liveDictionary if source is not None else None


def _parseDictionaryFile(source, skippedEntries):
	"""Mirrors the line handling of NVDA's SpeechDict.load, keeping each entry's file line number."""
	entries = []
	try:
		with open(source.filePath, encoding="utf_8_sig", errors="replace") as dictFile:
			for lineNumber, line in enumerate(dictFile, 1):
				if line.isspace() or line.startswith("#"):
					continue
				line = line.rstrip("\r\n")
				fields = line.split("\t")
				if len(fields) != 4:
					skippedEntries.append((source.label, lineNumber, _("Line does not have 4 tab-separated fields")))
					continue
				pattern = fields[0].replace(r"\#", "#")
				replacement = fields[1].replace(r"\#", "#")
				try:
					entryObject = createSpeechDictEntry(
						pattern, replacement, "", bool(int(fields[2])), int(fields[3])
					)
				except ENTRY_ERRORS as entryError:
					skippedEntries.append((source.label, lineNumber, str(entryError)))
					continue
				entries.append(TraceEntry(source, lineNumber, entryObject, line))
	except OSError as readError:
		logHandler.log.debug(f"DictionaryDisplayLite: dictionary file could not be read for the trace - {readError}")
		skippedEntries.append((source.label, 0, _("The dictionary file could not be read")))
	return entries


def _collectLiveEntries(source):
	entries = []
	for index, entryObject in enumerate(source.liveDictionary, 1):
		rawLine = "\t".join((
			entryObject.pattern, entryObject.replacement,
			"1" if entryObject.caseSensitive else "0", str(int(entryObject.type)),
		))
		entries.append(TraceEntry(source, 0, entryObject, rawLine))
	return entries


def collectEntries():
	"""Returns (entries, notes, skippedEntries) for every enabled dictionary, in NVDA's processing order."""
	entries = []
	notes = []
	skippedEntries = []
	for source in listDictionarySources():
		if not source.isEnabled:
			notes.append(_("{name} is turned off in NVDA and was not checked").format(name=source.label))
			continue
		if source.filePath and os.path.isfile(source.filePath):
			entries.extend(_parseDictionaryFile(source, skippedEntries))
		elif source.liveDictionary:
			entries.extend(_collectLiveEntries(source))
	return entries, notes, skippedEntries


def traceText(text, entries):
	"""Applies the entries one after another, as NVDA does, and records every entry that matches."""
	steps = []
	currentText = text
	for entry in entries:
		entryObject = entry.entryObject
		try:
			matches = list(itertools.islice(entryObject.compiled.finditer(currentText), MAX_MATCHES_PER_STEP))
			if not matches:
				continue
			newText = entryObject.sub(currentText)
		except _MATCH_ERRORS as matchError:
			logHandler.log.debug(f"DictionaryDisplayLite: entry skipped during the trace - {matchError}")
			continue
		isRegexp = entry.typeValue == REGEXP_ENTRY_TYPE
		template = entry.replacement if isRegexp else entry.replacement.replace("\\", "\\\\")
		resultTexts = []
		for match in matches:
			try:
				resultTexts.append(match.expand(template))
			except _MATCH_ERRORS:
				resultTexts.append("")
		steps.append(TraceStep(entry, [match.group(0) for match in matches], resultTexts, currentText, newText))
		currentText = newText
	return currentText, steps


def runTrace(text):
	entries, notes, skippedEntries = collectEntries()
	isProcessingEnabled = bool(getattr(globalVars, "speechDictionaryProcessing", True))
	if not isProcessingEnabled:
		return TraceResult(text, text, [], notes, skippedEntries, False)
	finalText, steps = traceText(text, entries)
	return TraceResult(text, finalText, steps, notes, skippedEntries, True)


def filterSteps(steps, word):
	"""Keeps the steps whose matched text, result or pattern contains the word (case-insensitive)."""
	needle = word.strip().lower()
	if not needle:
		return list(steps)
	kept = []
	for step in steps:
		haystack = [step.entry.pattern] + step.matchedTexts + step.resultTexts
		if any(needle in piece.lower() for piece in haystack):
			kept.append(step)
	return kept


def _visible(text):
	return text if text != "" else _("(empty)")


def formatStepDetails(step):
	entry = step.entry
	lines = [_("Dictionary: {name}").format(name=entry.source.label)]
	if entry.lineNumber:
		lines.append(_("Line: {line}").format(line=entry.lineNumber))
	lines += [
		_("Pattern: {pattern}").format(pattern=_visible(entry.pattern)),
		_("Replacement: {replacement}").format(replacement=_visible(entry.replacement)),
		_("Type: {type}").format(type=entry.typeLabel),
		_("Case sensitive: {value}").format(value=_("yes") if entry.caseSensitive else _("no")),
		_("Matched: {matched}").format(matched=" | ".join(_visible(text) for text in step.matchedTexts)),
		_("Becomes: {result}").format(result=" | ".join(_visible(text) for text in step.resultTexts)),
		_("Text before this entry: {text}").format(text=step.textBefore),
		_("Text after this entry: {text}").format(text=step.textAfter),
	]
	if not step.changedText:
		lines.append(_("This entry matched but did not change the text"))
	return "\n".join(lines)


def formatReport(result):
	lines = [_("Text checked: {text}").format(text=result.inputText), _("Text after all dictionaries: {text}").format(text=result.finalText), ""]
	if not result.isProcessingEnabled:
		lines.append(_("Speech dictionary processing is turned off in NVDA"))
	for note in result.notes:
		lines.append(note)
	for index, step in enumerate(result.steps, 1):
		lines += [_("Entry {number}").format(number=index), formatStepDetails(step), ""]
	for label, lineNumber, reason in result.skippedEntries:
		lines.append(_("Not loaded by NVDA: {name}, line {line}: {reason}").format(name=label, line=lineNumber, reason=reason))
	return "\n".join(lines).rstrip() + "\n"
