# locate.py

import os
import re

import globalVars
import logHandler

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def _asciiKey(text):
	return _NON_ALNUM_RE.sub("", text).lower()


def _getSynthAndVoiceNames():
	import synthDriverHandler
	synth = synthDriverHandler.getSynth()
	if synth is None:
		return "", ""
	try:
		voiceName = synth.availableVoices[synth.voice].displayName
	except (AttributeError, KeyError, TypeError):
		logHandler.log.debug("DictionaryDisplayLite: voice name of the current synthesizer is unavailable")
		voiceName = ""
	return synth.name, voiceName


def getDictionaryRoot():
	return os.path.join(globalVars.appArgs.configPath, "speechDicts")


def _listDictionaryFiles(root):
	found = []
	for folder, _dirNames, fileNames in os.walk(root):
		for fileName in fileNames:
			if fileName.lower().endswith(".dic"):
				found.append(os.path.join(folder, fileName))
	return found


def findActiveDictionary():
	"""Return (path, folder). path is empty when the active dictionary cannot be identified."""
	root = getDictionaryRoot()
	folder = root if os.path.isdir(root) else globalVars.appArgs.configPath
	if not os.path.isdir(root):
		return "", folder
	try:
		synthName, voiceName = _getSynthAndVoiceNames()
		files = _listDictionaryFiles(root)
	except OSError:
		logHandler.log.exception("DictionaryDisplayLite: speech dictionary folder could not be read")
		return "", folder
	if not synthName:
		return "", folder
	prefix = synthName.lower() + "-"
	synthFiles = [path for path in files if os.path.basename(path).lower().startswith(prefix)]
	voiceKey = _asciiKey(synthName + "-" + voiceName)
	voiceMatches = [
		path for path in synthFiles
		if _asciiKey(os.path.splitext(os.path.basename(path))[0]) == voiceKey
	]
	if len(voiceMatches) == 1:
		return voiceMatches[0], folder
	if not voiceMatches and len(synthFiles) == 1:
		return synthFiles[0], folder
	return "", folder
