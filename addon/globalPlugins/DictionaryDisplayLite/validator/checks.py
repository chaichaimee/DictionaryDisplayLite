# checks.py

import bisect
import re
from collections import namedtuple

from .wordlist import KNOWN_WORDS, MIXED_CASE_ALLOWED, SAFE_LATIN_ABBREVIATIONS

Rule = namedtuple("Rule", "line raw pattern replacement caseSensitive enabled")

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_THAI_CHAR_RE = re.compile(r"[\u0e00-\u0e7f]")
_THAI_ONLY_RE = re.compile(r"[\u0e00-\u0e7f]{2,}")
_SINGLE_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
_LATIN_RUN_RE = re.compile(r"[A-Za-z]+")
_LATIN_ONLY_CORE_RE = re.compile(r"[A-Za-z]{3,}")
_LATIN_THAI_ADJACENT_RE = re.compile(r"[A-Za-z][\u0e00-\u0e7f]|[\u0e00-\u0e7f][A-Za-z]")
_BARE_THAI_CLASS_DOT_RE = re.compile(r"\(?\[[\u0e00-\u0e7f\-]+\]\)?\\\.")
_CLASS_RE = re.compile(r"\[(?:\\.|[^\]\\])*\]")
_CONTEXT_RE = re.compile(r"\\[bB]|\(\?<[=!]|\(\?[=!]|\^|\$")
_ESCAPE_RE = re.compile(r"\\g<[^>]*>|\\.", re.DOTALL)
_BOUNDARY_RE = re.compile(r"\\[bB]")
_BRACE_GROUP_RE = re.compile(r"\{[^{}]*\}")
_QUANTIFIER_RE = re.compile(r"\{(?:\d+(?:,\d*)?|,\d*)\}")
_BACKREF_RE = re.compile(r"\\(?:(\\)|g<([^>]*)>|([0-9]{1,3}))")
_LOOKBEHIND_AFTER_LITERAL_RE = re.compile(
	r"(\\[^\w\s]|[^\\()\[\]{}|*+?^$.\s])\(\?<=\[((?:\\.|[^\]\\])+)\]\)"
)
_REGEX_META = frozenset("\\.^$*+?{}[]|()")
_OCTAL_DIGITS = "01234567"
_MAX_SHADOW_SCAN = 200

INVISIBLE_CHARS = {
	"\u200b": "U+200B ZERO WIDTH SPACE",
	"\u200c": "U+200C ZERO WIDTH NON-JOINER",
	"\u200d": "U+200D ZERO WIDTH JOINER",
	"\ufeff": "U+FEFF ZERO WIDTH NO-BREAK SPACE",
	"\u00ad": "U+00AD SOFT HYPHEN",
}

_LOWERED_SEVERITY = {"critical": "high", "high": "medium", "medium": "low", "low": "low"}


def makeIssue(rule, column, code, severity, message, suggestion=None):
	return {
		"line": rule.line,
		"column": column,
		"rule": rule.raw,
		"code": code,
		"severity": severity,
		"message": message,
		"suggestion": suggestion,
	}


def lowerSeverity(issue):
	lowered = dict(issue)
	lowered["severity"] = _LOWERED_SEVERITY[issue["severity"]]
	lowered["message"] = issue["message"] + " (the rule is disabled)"
	return lowered


def _stripEscapes(text):
	return _ESCAPE_RE.sub(" ", text)


def _isLiteral(pattern):
	return not any(char in _REGEX_META for char in pattern)


def _hasContext(pattern):
	return _CONTEXT_RE.search(_CLASS_RE.sub("", pattern)) is not None


_COMPILE_HINTS = (
	("unterminated character set", "Add the missing closing ] or escape a literal [ as \\[."),
	("missing ), unterminated subpattern", "Add the missing closing parenthesis, or escape a literal ( as \\(."),
	("unbalanced parenthesis", "Remove the extra ) or add the matching (; escape a literal ) as \\)."),
	("nothing to repeat", "A quantifier (* + ? or {}) has nothing before it; put it after a character or group, or escape it."),
	("multiple repeat", "Two quantifiers are stacked; keep only one, or group the first with parentheses."),
	("bad escape", "Remove the backslash or double it. Valid escapes include \\d \\w \\s \\b and an escaped symbol."),
	("look-behind requires fixed-width", "Make every lookbehind alternative the same length, or use a lookahead."),
	("bad character range", "Write the range from the lower to the higher character, for example a-z."),
	("unknown extension", "A group starting with (? must be followed by a valid type such as ?: ?= ?! ?<= ?<!."),
	("unterminated", "A closing symbol is missing; check that every ( [ and { has a matching closer."),
)


def describeCompileError(error):
	message = getattr(error, "msg", None) or str(error)
	position = getattr(error, "pos", None)
	pattern = getattr(error, "pattern", None)
	text = "Pattern does not compile: {}".format(message)
	if isinstance(position, int) and isinstance(pattern, str):
		snippet = pattern[max(0, position - 6):position + 6]
		text += " at position {} near {!r}".format(position + 1, snippet)
	suggestion = "Fix the regular expression syntax, or escape special characters with a backslash."
	lowered = message.lower()
	for fragment, hint in _COMPILE_HINTS:
		if fragment in lowered:
			suggestion = hint
			break
	return text + ".", suggestion


def _compileFailure(compiled):
	if isinstance(compiled, re.Pattern):
		return []
	message, suggestion = describeCompileError(compiled)
	return [(1, message, suggestion)]


def _backrefFailures(rule, compiled):
	if not isinstance(compiled, re.Pattern):
		return []
	groupCount = compiled.groups
	findings = []
	reported = set()
	for match in _BACKREF_RE.finditer(rule.replacement):
		if match.group(1):
			continue
		if match.group(2) is not None:
			name = match.group(2)
			if name.isdigit():
				groupNumber = int(name)
			elif name in compiled.groupindex:
				continue
			else:
				groupNumber = None
			reference = "\\g<{}>".format(name)
		else:
			digits = match.group(3)
			if digits[0] == "0":
				continue
			if len(digits) == 3 and all(digit in _OCTAL_DIGITS for digit in digits):
				continue
			groupNumber = int(digits[:2])
			reference = "\\" + digits[:2]
		if reference in reported:
			continue
		if groupNumber is not None and groupNumber <= groupCount:
			continue
		reported.add(reference)
		if groupNumber is None:
			message = "Replacement uses the named group {} but the pattern defines no group with that name.".format(reference)
		elif groupCount == 0:
			message = "Replacement uses {} but the pattern has no capture groups.".format(reference)
		else:
			message = "Replacement uses {} but the pattern has only {} capture group(s).".format(reference, groupCount)
		findings.append((
			2,
			message,
			"Add the missing capture group to the pattern, or remove the back-reference from the replacement.",
		))
	return findings


def _invisibleFindings(rule):
	found = [INVISIBLE_CHARS[char] for char in INVISIBLE_CHARS if char in rule.replacement]
	if not found:
		return []
	return [(
		2,
		"Replacement contains invisible character(s): {}.".format(", ".join(found)),
		"Remove the invisible character if it was pasted by accident. If it is an intentional TTS pause "
		"marker, add the pattern to validator/whitelist.txt.",
	)]


def checkRegexCompile(rule, compiled):
	return [
		makeIssue(rule, column, "REGEX_COMPILE_ERROR", "critical", message, suggestion)
		for column, message, suggestion in _compileFailure(compiled)
	]


def checkInvalidBackref(rule, compiled):
	return [
		makeIssue(rule, column, "INVALID_BACKREF", "high", message, suggestion)
		for column, message, suggestion in _backrefFailures(rule, compiled)
	]


def checkInvisibleChar(rule):
	return [
		makeIssue(rule, column, "INVISIBLE_CHAR", "high", message, suggestion)
		for column, message, suggestion in _invisibleFindings(rule)
	]


def checkDisabledButBroken(rule, compiled):
	findings = _compileFailure(compiled) + _backrefFailures(rule, compiled) + _invisibleFindings(rule)
	return [
		makeIssue(
			rule, column, "DISABLED_BUT_BROKEN", "medium",
			"Rule is disabled but would fail if enabled: " + message, suggestion,
		)
		for column, message, suggestion in findings
	]


def checkOverbroadPattern(rule):
	pattern = rule.pattern
	if _BARE_THAI_CLASS_DOT_RE.fullmatch(pattern):
		return [makeIssue(
			rule, 1, "OVERBROAD_PATTERN", "high",
			"Pattern matches any Thai letter followed by a dot with no context, so it fires inside ordinary text "
			"and not only in abbreviations.",
			"Anchor the pattern with a lookbehind or boundary so that it only matches real abbreviations.",
		)]
	if _SINGLE_THAI_RE.fullmatch(pattern):
		return [makeIssue(
			rule, 1, "OVERBROAD_PATTERN", "high",
			"Pattern is a single Thai character with no context, so it matches inside every word that contains it.",
			"Use a longer pattern or add a lookbehind or lookahead for context.",
		)]
	return []


def checkLangMixReplacement(rule):
	text = _stripEscapes(rule.replacement)
	if not _LATIN_THAI_ADJACENT_RE.search(text):
		return []
	offenders = []
	for match in _LATIN_RUN_RE.finditer(text):
		before = text[match.start() - 1] if match.start() > 0 else ""
		after = text[match.end()] if match.end() < len(text) else ""
		touchesThai = bool(_THAI_CHAR_RE.fullmatch(before)) or bool(_THAI_CHAR_RE.fullmatch(after))
		if touchesThai and match.group().upper() not in SAFE_LATIN_ABBREVIATIONS:
			offenders.append(match.group())
	if not offenders:
		return []
	return [makeIssue(
		rule, 2, "LANG_MIX_REPLACEMENT", "high",
		"Replacement joins Latin text ({}) directly to Thai text without a hyphen or space, which makes the "
		"TTS engine mispronounce the word.".format(", ".join(offenders)),
		"Separate the Latin and Thai parts with a hyphen or a space.",
	)]


def checkMixedCaseToken(rule):
	offenders = []
	for token in _LATIN_RUN_RE.findall(_stripEscapes(rule.replacement)):
		if token.isupper() or token.lower() in MIXED_CASE_ALLOWED:
			continue
		if any(char.isupper() for char in token[1:]):
			offenders.append(token)
	if not offenders:
		return []
	return [makeIssue(
		rule, 2, "MIXED_CASE_TOKEN", "medium",
		"Replacement contains mixed-case Latin token(s): {}. TTS engines may spell them out or "
		"mispronounce them.".format(", ".join(offenders)),
		"Use one leading capital for a word, or all capitals for an acronym.",
	)]


def _latinLiteralCore(pattern):
	core = _BOUNDARY_RE.sub("", pattern)
	return core if _LATIN_ONLY_CORE_RE.fullmatch(core) else None


def checkSuspiciousSpelling(rule):
	core = _latinLiteralCore(rule.pattern)
	if core is None:
		return []
	patternText = core.lower()
	offenders = []
	for token in _LATIN_RUN_RE.findall(_stripEscapes(rule.replacement)):
		lowered = token.lower()
		if len(token) < 4 or lowered in KNOWN_WORDS or lowered in patternText:
			continue
		offenders.append(token)
	if not offenders:
		return []
	return [makeIssue(
		rule, 2, "SUSPICIOUS_SPELLING", "medium",
		"Replacement spelling {} is not a known English word, while the pattern is a plain English "
		"word.".format(", ".join(offenders)),
		"Check the spelling, or write the intended pronunciation in Thai script.",
	)]


def checkHyphenBoundary(rule):
	text = rule.replacement
	if len(text) < 2:
		return []
	edges = []
	if text[0] == "-":
		edges.append(("starts", text[1]))
	if text[-1] == "-":
		edges.append(("ends", text[-2]))
	severity = None
	description = ""
	for side, neighbor in edges:
		if _THAI_CHAR_RE.fullmatch(neighbor):
			edgeSeverity, script = "low", "Thai"
		elif neighbor.isascii() and neighbor.isalpha():
			edgeSeverity, script = "medium", "Latin"
		else:
			continue
		if severity is None or edgeSeverity == "medium":
			severity = edgeSeverity
			description = "Replacement {} with a hyphen next to {} text".format(side, script)
	if severity is None:
		return []
	return [makeIssue(
		rule, 2, "HYPHEN_BOUNDARY", severity,
		description + "; the hyphen joins the result to the neighbouring word and can change how the TTS "
		"engine splits it.",
		"Keep the hyphen only if a join or pause is intended; otherwise remove it.",
	)]


def checkThaiLatinNoSep(rule):
	pattern = rule.pattern
	if not _THAI_ONLY_RE.fullmatch(pattern) or _hasContext(pattern):
		return []
	if rule.replacement == pattern:
		return [makeIssue(
			rule, 2, "THAI_LATIN_NO_SEP", "medium",
			"Thai pattern with no boundary is replaced by identical text, so the rule changes nothing.",
			"Remove the rule or change the replacement.",
		)]
	if rule.replacement in ("-" + pattern, pattern + "-"):
		return [makeIssue(
			rule, 2, "THAI_LATIN_NO_SEP", "medium",
			"Thai pattern with no boundary is only given a hyphen, so it also hyphenates longer Thai words "
			"that contain it.",
			"Add a lookbehind or lookahead for context, or remove the rule.",
		)]
	return []


def checkLiteralBraces(rule, compiled):
	if not isinstance(compiled, re.Pattern):
		return []
	stripped = _CLASS_RE.sub("", _ESCAPE_RE.sub("", rule.pattern))
	for match in _BRACE_GROUP_RE.finditer(stripped):
		if _QUANTIFIER_RE.fullmatch(match.group()):
			continue
		return [makeIssue(
			rule, 1, "LITERAL_BRACES", "medium",
			"Pattern contains {} which is not a repetition count, so it is matched as literal text and the rule "
			"only fires on text that contains those exact braces.".format(match.group()),
			"Use a character class in square brackets instead of braces, or escape the braces if they are meant "
			"literally.",
		)]
	return []


def checkUnreachableLookbehind(rule, compiled):
	if not isinstance(compiled, re.Pattern):
		return []
	flags = re.UNICODE if rule.caseSensitive else re.UNICODE | re.IGNORECASE
	for match in _LOOKBEHIND_AFTER_LITERAL_RE.finditer(rule.pattern):
		literal = match.group(1)[-1]
		try:
			allowed = re.fullmatch("[" + match.group(2) + "]", literal, flags)
		except re.error:
			continue
		if allowed:
			continue
		return [makeIssue(
			rule, 1, "UNREACHABLE_LOOKBEHIND", "medium",
			"A lookbehind right after the literal character {!r} requires one of [{}] before the cursor, but the "
			"character just consumed is {!r}, so the pattern can never match.".format(
				literal, match.group(2), literal
			),
			"Move the lookbehind before the literal character, or remove it.",
		)]
	return []


def checkDuplicatePatterns(rules):
	firstLineByPattern = {}
	issues = []
	for rule in rules:
		if not rule.enabled:
			continue
		firstLine = firstLineByPattern.get(rule.pattern)
		if firstLine is None:
			firstLineByPattern[rule.pattern] = rule.line
			continue
		issues.append(makeIssue(
			rule, 1, "DUPLICATE_PATTERN", "low",
			"Pattern is identical to the enabled rule on line {}, so only one of the two can take effect.".format(
				firstLine
			),
			"Remove or merge one of the duplicate rules.",
		))
	return issues


def checkShadowedRules(rules):
	literalRules = [
		rule for rule in rules
		if rule.enabled and len(rule.pattern) >= 3 and _isLiteral(rule.pattern)
	]
	if len(literalRules) < 2:
		return []
	starts = []
	offset = 0
	for rule in literalRules:
		starts.append(offset)
		offset += len(rule.pattern) + 1
	joined = "\0".join(rule.pattern for rule in literalRules)
	issues = []
	for index, rule in enumerate(literalRules):
		position = joined.find(rule.pattern)
		scanned = 0
		while position != -1 and scanned < _MAX_SHADOW_SCAN:
			ownerIndex = bisect.bisect_right(starts, position) - 1
			owner = literalRules[ownerIndex]
			if ownerIndex > index and owner.pattern != rule.pattern:
				issues.append(makeIssue(
					rule, 1, "SHADOWED_RULE", "low",
					"Pattern is contained in the pattern of the later rule on line {}, so this rule runs first and "
					"can stop that rule from matching.".format(owner.line),
					"Make this pattern more specific, or move the longer rule above it.",
				))
				break
			position = joined.find(rule.pattern, position + 1)
			scanned += 1
	return issues
