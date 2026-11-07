# core.py

import os
import re
import threading
import warnings

from . import checks, symbolChecks
from .checks import Rule, SEVERITY_RANK

WHITELIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whitelist.txt")

_LINE_SPLIT_RE = re.compile(r"\r\n|\n|\r")
_FLAG_VALUES = ("0", "1")
_CACHE_LIMIT = 20000

_compileCache = {}
_cacheLock = threading.Lock()


def _compilePattern(pattern, caseSensitive):
	key = (pattern, caseSensitive)
	with _cacheLock:
		cached = _compileCache.get(key)
		if cached is not None:
			return cached
		flags = re.UNICODE if caseSensitive else re.UNICODE | re.IGNORECASE
		try:
			with warnings.catch_warnings():
				warnings.simplefilter("ignore")
				outcome = re.compile(pattern, flags)
		except (re.error, RecursionError, OverflowError) as error:
			outcome = error
		if len(_compileCache) >= _CACHE_LIMIT:
			_compileCache.clear()
		_compileCache[key] = outcome
		return outcome


def _loadWhitelist(path=None):
	try:
		with open(path or WHITELIST_PATH, "r", encoding="utf-8-sig") as handle:
			lines = handle.read().splitlines()
	except OSError:
		return frozenset()
	return frozenset(line for line in lines if line and not line.startswith("#"))


def _splitLines(content):
	lines = _LINE_SPLIT_RE.split(content)
	if lines and lines[-1] == "":
		lines.pop()
	return lines


def _malformedIssue(lineNumber, line, column, message, suggestion):
	fields = line.split("\t")
	placeholder = Rule(lineNumber, line, fields[0], fields[1] if len(fields) > 1 else "", False, True)
	return checks.makeIssue(placeholder, column, "MALFORMED_ROW", "critical", message, suggestion)


def _lineIssue(lineNumber, line, code, severity, message, suggestion):
	fields = line.split("\t")
	placeholder = Rule(lineNumber, line, fields[0], fields[1] if len(fields) > 1 else "", False, True)
	return checks.makeIssue(placeholder, 0, code, severity, message, suggestion)


def _parseRule(lineNumber, line):
	"""Return (rule, issue); exactly one of the two is None."""
	fields = line.split("\t")
	if len(fields) < 2:
		return None, _malformedIssue(
			lineNumber, line, 1,
			"Row has {} field(s); a pattern and a replacement separated by a tab are required.".format(len(fields)),
			"Separate the columns with tab characters: pattern, replacement, case sensitive (0 or 1), enabled (0 or 1).",
		)
	if len(fields) > 4:
		return None, _malformedIssue(
			lineNumber, line, 1,
			"Row has {} fields but only 4 are expected; a stray tab inside the pattern or replacement shifts "
			"the columns.".format(len(fields)),
			"Remove the extra tab character.",
		)
	if fields[0] == "":
		return None, _malformedIssue(
			lineNumber, line, 1, "Pattern is empty.", "Write a pattern, or delete the row.",
		)
	caseText = fields[2].strip() if len(fields) > 2 else "0"
	enabledText = fields[3].strip() if len(fields) > 3 else "1"
	if caseText not in _FLAG_VALUES:
		return None, _malformedIssue(
			lineNumber, line, 3,
			"Column 3 (case sensitive) is {!r}; it must be 0 or 1.".format(caseText),
			"Use 1 for case-sensitive matching or 0 to ignore case.",
		)
	if enabledText not in _FLAG_VALUES:
		return None, _malformedIssue(
			lineNumber, line, 4,
			"Column 4 (enabled) is {!r}; it must be 0 or 1.".format(enabledText),
			"Use 1 to enable the rule or 0 to disable it.",
		)
	rule = Rule(lineNumber, line, fields[0], fields[1], caseText == "1", enabledText == "1")
	return rule, None


def _checkEnabledRule(rule, compiled):
	issues = []
	issues += checks.checkRegexCompile(rule, compiled)
	issues += checks.checkInvalidBackref(rule, compiled)
	issues += checks.checkInvisibleChar(rule)
	issues += checks.checkLiteralBraces(rule, compiled)
	issues += checks.checkUnreachableLookbehind(rule, compiled)
	issues += checks.checkOverbroadPattern(rule)
	issues += checks.checkLangMixReplacement(rule)
	issues += checks.checkMixedCaseToken(rule)
	issues += checks.checkSuspiciousSpelling(rule)
	issues += checks.checkHyphenBoundary(rule)
	issues += checks.checkThaiLatinNoSep(rule)
	issues += symbolChecks.checkEnabledRule(rule, compiled)
	return issues


def _checkDisabledRule(rule, compiled):
	issues = checks.checkDisabledButBroken(rule, compiled) + symbolChecks.checkDisabledTemplate(rule, compiled)
	lexicalIssues = []
	lexicalIssues += checks.checkLangMixReplacement(rule)
	lexicalIssues += checks.checkMixedCaseToken(rule)
	lexicalIssues += checks.checkSuspiciousSpelling(rule)
	return issues + [checks.lowerSeverity(issue) for issue in lexicalIssues]


def _decodeContent(rawBytes):
	try:
		return rawBytes.decode("utf-8-sig"), False
	except UnicodeDecodeError:
		return rawBytes.decode("utf-8-sig", errors="replace"), True


def _validateText(content, sourceName, hasEncodingProblem=False):
	if content.startswith("\ufeff"):
		content = content[1:]
	lines = _splitLines(content)
	issues = []
	rules = []
	skippedLines = 0
	for lineNumber, line in enumerate(lines, 1):
		if "\ufffd" in line:
			issues.append(_lineIssue(
				lineNumber, line, "ENCODING_ERROR", "high",
				"Line contains the replacement character U+FFFD, which means a byte or symbol was damaged when the "
				"file was saved in a different encoding.",
				"Retype the damaged text and save the file as UTF-8.",
			))
		if not line.strip() or line.startswith("#"):
			skippedLines += 1
			continue
		rule, malformed = _parseRule(lineNumber, line)
		if malformed is not None:
			issues.append(malformed)
			continue
		rules.append(rule)
	if hasEncodingProblem:
		issues.append({
			"line": 0, "column": 0, "rule": "", "code": "MALFORMED_ROW", "severity": "critical",
			"message": "File is not valid UTF-8; the invalid bytes were replaced while reading.",
			"suggestion": "Save the dictionary file as UTF-8.",
		})
	for rule in rules:
		compiled = _compilePattern(rule.pattern, rule.caseSensitive)
		issues += _checkEnabledRule(rule, compiled) if rule.enabled else _checkDisabledRule(rule, compiled)
	issues += checks.checkDuplicatePatterns(rules)
	issues += checks.checkShadowedRules(rules)
	whitelist = _loadWhitelist()
	if whitelist:
		issues = [issue for issue in issues if issue["rule"].split("\t", 1)[0] not in whitelist]
	issues.sort(key=lambda issue: (SEVERITY_RANK[issue["severity"]], issue["line"], issue["column"]))
	summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": len(issues)}
	for issue in issues:
		summary[issue["severity"]] += 1
	return {
		"file": sourceName,
		"total_lines": len(lines),
		"parsed_rules": len(rules),
		"skipped_lines": skippedLines,
		"issues": issues,
		"summary": summary,
	}


def validate_dictionary_string(content, source_name="<string>"):
	return _validateText(content, source_name)


def validate_dictionary(file_path):
	with open(file_path, "rb") as handle:
		rawBytes = handle.read()
	content, hasEncodingProblem = _decodeContent(rawBytes)
	return _validateText(content, file_path, hasEncodingProblem)
