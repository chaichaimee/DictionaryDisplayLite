# filterSettings.py

import json
import os
import threading

CONFIG_SUBFOLDER = os.path.join("ChaiChaimee", "DictionaryDisplayLite")
FILTER_FILE_NAME = "validatorFilter.json"

ALL_CODES = (
	"MALFORMED_ROW", "REGEX_COMPILE_ERROR", "INVALID_BACKREF", "INVISIBLE_CHAR", "OVERBROAD_PATTERN",
	"LANG_MIX_REPLACEMENT", "MIXED_CASE_TOKEN", "SUSPICIOUS_SPELLING", "HYPHEN_BOUNDARY", "THAI_LATIN_NO_SEP",
	"LITERAL_BRACES", "UNREACHABLE_LOOKBEHIND", "DUPLICATE_PATTERN", "SHADOWED_RULE", "DISABLED_BUT_BROKEN",
	"SYMBOL_POSITION", "FULLWIDTH_SYMBOL", "TYPOGRAPHIC_SYMBOL", "NON_NFC_TEXT", "MIXED_SCRIPT_TOKEN",
	"BAD_CLASS_RANGE", "UNESCAPED_DOT", "BOUNDARY_IN_UNSPACED_SCRIPT", "REPLACEMENT_TEMPLATE_ERROR",
	"SYMBOL_IN_REPLACEMENT", "ENCODING_ERROR",
)

_SEVERITIES = ("critical", "high", "medium", "low")

_cacheLock = threading.Lock()
_writeLock = threading.Lock()
_loaded = None


def getFilterPath():
	import globalVars
	return os.path.join(globalVars.appArgs.configPath, CONFIG_SUBFOLDER, FILTER_FILE_NAME)


def readFilterSettings(path):
	"""Return {"excludedCodes": set, "showDescription": bool}; defaults apply to anything missing or invalid."""
	settings = {"excludedCodes": set(), "showDescription": True}
	try:
		with open(path, "r", encoding="utf-8") as handle:
			data = json.load(handle)
	except (OSError, ValueError):
		return settings
	if not isinstance(data, dict):
		return settings
	codes = data.get("excludedCodes")
	if isinstance(codes, list):
		settings["excludedCodes"] = {code for code in codes if isinstance(code, str)}
	if isinstance(data.get("showDescription"), bool):
		settings["showDescription"] = data["showDescription"]
	return settings


def writeFilterSettings(path, excludedCodes, showDescription):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	temporaryPath = path + ".tmp"
	try:
		with open(temporaryPath, "w", encoding="utf-8") as handle:
			json.dump(
				{"version": 1, "excludedCodes": sorted(excludedCodes), "showDescription": showDescription},
				handle, indent=2,
			)
		os.replace(temporaryPath, path)
	except OSError:
		try:
			os.remove(temporaryPath)
		except OSError:
			pass
		raise


def _loadedSettings():
	global _loaded
	if _loaded is None:
		_loaded = readFilterSettings(getFilterPath())
	return _loaded


def getExcludedCodes():
	with _cacheLock:
		return frozenset(_loadedSettings()["excludedCodes"])


def setExcludedCodes(codes):
	with _cacheLock:
		_loadedSettings()["excludedCodes"] = set(codes)


def getShowDescription():
	with _cacheLock:
		return _loadedSettings()["showDescription"]


def setShowDescription(value):
	with _cacheLock:
		_loadedSettings()["showDescription"] = bool(value)


def _saveLatest():
	import logHandler
	with _writeLock:
		excludedCodes = getExcludedCodes()
		showDescription = getShowDescription()
		try:
			writeFilterSettings(getFilterPath(), excludedCodes, showDescription)
		except OSError:
			logHandler.log.exception("DictionaryDisplayLite: validator filter could not be saved")


def saveInBackground():
	threading.Thread(target=_saveLatest, name="DictionaryDisplayLite.filterSave", daemon=True).start()


def countByCode(result):
	counts = {}
	for issue in result["issues"]:
		counts[issue["code"]] = counts.get(issue["code"], 0) + 1
	return counts


def applyExclusions(result, excluded):
	"""Return a copy of result without the excluded issue codes, with the summary recomputed."""
	view = dict(result)
	issues = [issue for issue in result["issues"] if issue["code"] not in excluded]
	summary = {severity: 0 for severity in _SEVERITIES}
	summary["total"] = len(issues)
	for issue in issues:
		summary[issue["severity"]] += 1
	view["issues"] = issues
	view["summary"] = summary
	view["hidden"] = len(result["issues"]) - len(issues)
	return view
