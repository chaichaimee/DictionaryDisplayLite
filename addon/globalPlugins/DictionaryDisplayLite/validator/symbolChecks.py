# symbolChecks.py

import re
import unicodedata
from bisect import bisect_right

from .checks import INVISIBLE_CHARS, _backrefFailures, makeIssue

_SCRIPT_TABLE = tuple(sorted((
	(0x0041, 0x005A, "Latin"), (0x0061, 0x007A, "Latin"), (0x00C0, 0x00D6, "Latin"),
	(0x00D8, 0x00F6, "Latin"), (0x00F8, 0x024F, "Latin"), (0x1E00, 0x1EFF, "Latin"),
	(0x0370, 0x03FF, "Greek"), (0x1F00, 0x1FFF, "Greek"),
	(0x0400, 0x052F, "Cyrillic"),
	(0x0590, 0x05FF, "Hebrew"),
	(0x0600, 0x06FF, "Arabic"), (0x0750, 0x077F, "Arabic"), (0xFB50, 0xFDFF, "Arabic"), (0xFE70, 0xFEFF, "Arabic"),
	(0x0900, 0x097F, "Devanagari"),
	(0x0E00, 0x0E7F, "Thai"), (0x0E80, 0x0EFF, "Lao"), (0x1000, 0x109F, "Myanmar"), (0x1780, 0x17FF, "Khmer"),
	(0x1100, 0x11FF, "Hangul"), (0x3130, 0x318F, "Hangul"), (0xAC00, 0xD7AF, "Hangul"),
	(0x3040, 0x309F, "Hiragana"), (0x30A0, 0x30FF, "Katakana"),
	(0x3400, 0x4DBF, "Han"), (0x4E00, 0x9FFF, "Han"),
)))
_SCRIPT_STARTS = tuple(entry[0] for entry in _SCRIPT_TABLE)
_HOMOGLYPH_SCRIPTS = frozenset(("Latin", "Cyrillic", "Greek"))

_CYRILLIC_OR_GREEK_RE = re.compile("[\u0370-\u03ff\u0400-\u052f]")
_WORD_RUN_RE = re.compile(r"[^\W\d_]+")
_ESCAPE_RE = re.compile(r"\\g<[^>]*>|\\.", re.DOTALL)
_CLASS_RE = re.compile(r"\[\^?\]?(?:\\.|[^\]\\])*\]")
_MULTILINE_FLAG_RE = re.compile(r"\(\?[aiLsux]*m")
_GROUP_PREFIX_RE = re.compile(r"\?(?:P<[^>]*>|P=[^)]*\)|<[=!]|[:=!]|#[^)]*\)|[aiLmsux]*(?:-[imsx]+)?(?:\)|:))")
_UNSPACED_SCRIPT_CHARS = "\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u9fff"
_UNSPACED_BOUNDARY_RE = re.compile(
	r"\\[bB][{0}]|[{0}]\\[bB]".format(_UNSPACED_SCRIPT_CHARS)
)

_FULLWIDTH_REGEX_SYMBOLS = frozenset(
	"\uff08\uff09\uff3b\uff3d\uff5b\uff5d\uff5c\uff0a\uff0b\uff1f\uff3c\uff3e\uff04\uff0e"
)
_TYPOGRAPHIC_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
_HIDDEN_CHARS_RE = re.compile(
	"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u00a0\u061c\u180e\u1680\u2000-\u200f"
	"\u2028-\u202f\u205f-\u2064\u2066-\u2069\u3000\ufeff\u00ad]"
)
_REPLACEMENT_MARKUP_CHARS = "<>&"
_BRACKET_PAIRS = (("(", ")"), ("[", "]"), ("{", "}"))


def scriptOf(char):
	code = ord(char)
	index = bisect_right(_SCRIPT_STARTS, code) - 1
	if index < 0:
		return None
	_start, end, name = _SCRIPT_TABLE[index]
	return name if code <= end else None


def _charName(char):
	return unicodedata.name(char, "U+{:04X}".format(ord(char)))


def _literalText(pattern):
	text = _ESCAPE_RE.sub(" ", pattern)
	text = _CLASS_RE.sub(" ", text)
	return re.sub(r"[()|*+?{}^$.]", " ", text)


def structuralFindings(pattern):
	"""Return (kind, index) for empty alternatives, empty groups and anchors in the wrong place."""
	findings = []
	allowAnchorAnywhere = bool(_MULTILINE_FLAG_RE.search(pattern))
	length = len(pattern)
	index = 0
	inClass = False
	atAlternativeStart = True
	lastWasPipe = False
	while index < length:
		char = pattern[index]
		if inClass:
			if char == "\\":
				index += 2
				continue
			if char == "]":
				inClass = False
			index += 1
			continue
		if char == "\\":
			following = pattern[index + 1:index + 2]
			if following not in ("b", "B", "A", "Z"):
				atAlternativeStart = False
				lastWasPipe = False
			index += 2
			continue
		if char == "[":
			inClass = True
			index += 1
			if pattern[index:index + 1] == "^":
				index += 1
			if pattern[index:index + 1] == "]":
				index += 1
			atAlternativeStart = False
			lastWasPipe = False
			continue
		if char == "(":
			index += 1
			prefix = _GROUP_PREFIX_RE.match(pattern, index) if pattern[index:index + 1] == "?" else None
			if prefix is not None:
				index = prefix.end()
				text = prefix.group()
				if text.endswith(")"):
					if text.startswith("?P="):
						atAlternativeStart = False
					continue
			atAlternativeStart = True
			lastWasPipe = False
			continue
		if char == "|":
			if atAlternativeStart:
				findings.append(("EMPTY_ALTERNATIVE", index))
			atAlternativeStart = True
			lastWasPipe = True
			index += 1
			continue
		if char == ")":
			if atAlternativeStart and lastWasPipe:
				findings.append(("EMPTY_ALTERNATIVE", index))
			elif atAlternativeStart and pattern[index - 1:index] == "(":
				findings.append(("EMPTY_GROUP", index))
			atAlternativeStart = False
			lastWasPipe = False
			index += 1
			continue
		if char == "^":
			if not atAlternativeStart and not allowAnchorAnywhere:
				findings.append(("CARET_NOT_AT_START", index))
			index += 1
			continue
		if char == "$":
			if pattern[index + 1:index + 2] not in ("", "|", ")", "$") and not allowAnchorAnywhere:
				findings.append(("DOLLAR_NOT_AT_END", index))
			index += 1
			continue
		if char not in "*+?{":
			atAlternativeStart = False
			lastWasPipe = False
		index += 1
	if atAlternativeStart and lastWasPipe:
		findings.append(("EMPTY_ALTERNATIVE", length))
	return findings


_STRUCTURE_MESSAGES = {
	"EMPTY_ALTERNATIVE": (
		"high", "SYMBOL_POSITION",
		"Pattern has an empty alternative next to a | symbol, so it matches an empty string everywhere and the "
		"replacement is inserted between every character.",
		"Remove the stray | or add the missing text beside it.",
	),
	"EMPTY_GROUP": (
		"medium", "SYMBOL_POSITION",
		"Pattern contains an empty group (), which matches nothing useful.",
		"Remove the empty parentheses or put the intended text inside them.",
	),
	"CARET_NOT_AT_START": (
		"medium", "SYMBOL_POSITION",
		"The ^ anchor is in the middle of the pattern, so the pattern can never match.",
		"Move ^ to the start of the pattern or alternative, or escape it as \\^ if it is a literal symbol.",
	),
	"DOLLAR_NOT_AT_END": (
		"medium", "SYMBOL_POSITION",
		"The $ anchor is followed by more text, so the pattern can never match.",
		"Move $ to the end of the pattern or alternative, or escape it as \\$ if it is a literal symbol.",
	),
}


def checkStructure(rule, compiled):
	if not isinstance(compiled, re.Pattern) or not any(char in rule.pattern for char in "|()^$"):
		return []
	issues = []
	seen = set()
	for kind, position in structuralFindings(rule.pattern):
		if kind in seen:
			continue
		seen.add(kind)
		severity, code, message, suggestion = _STRUCTURE_MESSAGES[kind]
		issues.append(makeIssue(
			rule, 1, code, severity, "{} (position {}).".format(message[:-1], position + 1), suggestion,
		))
	return issues


def checkFullwidthSymbols(rule):
	found = sorted({char for char in rule.pattern if char in _FULLWIDTH_REGEX_SYMBOLS})
	if not found:
		return []
	return [makeIssue(
		rule, 1, "FULLWIDTH_SYMBOL", "medium",
		"Pattern contains full-width symbol(s) that look like regex symbols but are matched as literal text: {}.".format(
			", ".join("{} {}".format(char, _charName(char)) for char in found)
		),
		"Replace them with the normal ASCII symbols if a regex symbol was intended.",
	)]


def checkTypographicSymbols(rule):
	found = sorted({
		char for char in rule.pattern
		if char in _TYPOGRAPHIC_QUOTES and _TYPOGRAPHIC_QUOTES[char] not in rule.pattern
	})
	if not found:
		return []
	return [makeIssue(
		rule, 1, "TYPOGRAPHIC_SYMBOL", "low",
		"Pattern contains curly quote(s) ({}) but not the plain ASCII quote, so it will not match text typed with "
		"a straight quote.".format(", ".join(_charName(char) for char in found)),
		"Match both forms with a character class, for example ['\\u2019], or add the straight quote as an alternative.",
	)]


def checkHiddenCharacters(rule):
	if not _HIDDEN_CHARS_RE.search(rule.pattern + rule.replacement):
		return []
	issues = []
	patternHidden = sorted({char for char in _HIDDEN_CHARS_RE.findall(rule.pattern)} | {
		char for char in INVISIBLE_CHARS if char in rule.pattern
	})
	if patternHidden:
		issues.append(makeIssue(
			rule, 1, "INVISIBLE_CHAR", "high",
			"Pattern contains invisible or special-space character(s): {}. The rule will not match ordinary text.".format(
				", ".join(_charName(char) for char in patternHidden)
			),
			"Delete the character and retype the pattern; use \\s in a regex to match any kind of space.",
		))
	replacementHidden = sorted(
		char for char in set(_HIDDEN_CHARS_RE.findall(rule.replacement)) if char not in INVISIBLE_CHARS
	)
	if replacementHidden:
		issues.append(makeIssue(
			rule, 2, "INVISIBLE_CHAR", "high",
			"Replacement contains invisible or special-space character(s): {}.".format(
				", ".join(_charName(char) for char in replacementHidden)
			),
			"Delete the character and retype the replacement.",
		))
	return issues


def checkNormalization(rule):
	issues = []
	for column, label, text in ((1, "Pattern", rule.pattern), (2, "Replacement", rule.replacement)):
		if text.isascii() or unicodedata.is_normalized("NFC", text):
			continue
		issues.append(makeIssue(
			rule, column, "NON_NFC_TEXT", "medium",
			"{} is not in Unicode NFC form (for example accents or marks stored as separate characters or in a "
			"different order), so it can fail to match visually identical text.".format(label),
			"Retype the text or normalize it to NFC before saving.",
		))
	return issues


def checkMixedScriptToken(rule):
	if not _CYRILLIC_OR_GREEK_RE.search(rule.pattern + rule.replacement):
		return []
	issues = []
	for column, label, text in ((1, "Pattern", _literalText(rule.pattern)), (2, "Replacement", _ESCAPE_RE.sub(" ", rule.replacement))):
		if text.isascii() or not _CYRILLIC_OR_GREEK_RE.search(text):
			continue
		offenders = []
		for token in _WORD_RUN_RE.findall(text):
			scripts = {scriptOf(char) for char in token} & _HOMOGLYPH_SCRIPTS
			if len(scripts) >= 2:
				offenders.append("{} ({})".format(token, "+".join(sorted(scripts))))
		if offenders:
			issues.append(makeIssue(
				rule, column, "MIXED_SCRIPT_TOKEN", "high",
				"{} has a word that mixes look-alike letters from different scripts: {}. It will not match, or will be "
				"read in the wrong language.".format(label, ", ".join(offenders[:3])),
				"Retype the word using letters from one script only.",
			))
	return issues


def _classRangeProblems(pattern):
	problems = []
	for match in _CLASS_RE.finditer(pattern):
		body = match.group()[1:-1]
		if body.startswith("^"):
			body = body[1:]
		tokens = []
		position = 0
		while position < len(body):
			if body[position] == "\\":
				tokens.append(None)
				position += 2
				continue
			tokens.append(body[position])
			position += 1
		for index in range(len(tokens) - 2):
			if tokens[index + 1] != "-":
				continue
			low, high = tokens[index], tokens[index + 2]
			if low is None or high is None or low == "-" or high == "-":
				continue
			lowScript, highScript = scriptOf(low), scriptOf(high)
			if lowScript and highScript and lowScript != highScript:
				problems.append("{}-{} spans {} and {}".format(low, high, lowScript, highScript))
			elif lowScript == "Latin" == highScript and low.isupper() and high.islower() and low.isascii():
				problems.append("{}-{} also includes the symbols [ \\ ] ^ _ and the backtick".format(low, high))
			elif low.isdigit() and high.isascii() and high.isalpha():
				problems.append("{}-{} also includes the symbols : ; < = > ? @ and more".format(low, high))
	return problems


def checkClassRange(rule, compiled):
	if not isinstance(compiled, re.Pattern) or "[" not in rule.pattern:
		return []
	problems = _classRangeProblems(rule.pattern)
	if not problems:
		return []
	return [makeIssue(
		rule, 1, "BAD_CLASS_RANGE", "medium",
		"Character class range matches unintended characters: {}.".format("; ".join(problems[:3])),
		"Split the range, for example [A-Za-z] instead of [A-z], and list each script separately.",
	)]


def checkUnescapedDot(rule, compiled):
	if not isinstance(compiled, re.Pattern) or "." not in rule.pattern:
		return []
	core = _ESCAPE_RE.sub("", rule.pattern).replace("^", "").replace("$", "")
	if any(char in core for char in "[](){}|*+?"):
		return []
	for position, char in enumerate(core):
		if char != "." or position == 0 or not core[position - 1].isalpha():
			continue
		following = core[position + 1:position + 2]
		if following == "" or following.isalpha() or following == ".":
			return [makeIssue(
				rule, 1, "UNESCAPED_DOT", "low",
				"Pattern has a dot after a letter that is not escaped, so it matches any character, not only a full stop.",
				"Write \\. for a literal dot (for example Mr\\.), or ignore this if a wildcard is intended.",
			)]
	return []


def checkUnspacedBoundary(rule):
	if "\\" not in rule.pattern or not _UNSPACED_BOUNDARY_RE.search(rule.pattern):
		return []
	return [makeIssue(
		rule, 1, "BOUNDARY_IN_UNSPACED_SCRIPT", "low",
		"A word boundary \\b sits next to a letter of a script written without spaces between words (Thai, Lao, Khmer, "
		"Myanmar, Japanese, Chinese), so the rule only fires when the word is surrounded by spaces or punctuation.",
		"Use a lookbehind or lookahead for context instead of \\b, or keep \\b only if standalone matches are intended.",
	)]


def _templateError(rule, compiled):
	if "\\" not in rule.replacement or not isinstance(compiled, re.Pattern):
		return None
	try:
		compiled.sub(rule.replacement, "")
	except (re.error, IndexError, ValueError) as error:
		return str(error)
	return None


def checkReplacementTemplate(rule, compiled):
	if _backrefFailures(rule, compiled):
		return []
	error = _templateError(rule, compiled)
	if error is None:
		return []
	return [makeIssue(
		rule, 2, "REPLACEMENT_TEMPLATE_ERROR", "high",
		"Replacement is not a valid substitution string: {}.".format(error),
		"Double any backslash that is meant literally (\\\\) and use only \\1 to \\9 or \\g<name> for groups.",
	)]


def checkDisabledTemplate(rule, compiled):
	error = _templateError(rule, compiled)
	if error is None:
		return []
	return [makeIssue(
		rule, 2, "DISABLED_BUT_BROKEN", "medium",
		"Rule is disabled but would fail if enabled: replacement is not a valid substitution string: {}.".format(error),
		"Double any backslash that is meant literally (\\\\).",
	)]


def _bracketProblems(text):
	problems = []
	for opener, closer in _BRACKET_PAIRS:
		depth = 0
		for char in text:
			if char == opener:
				depth += 1
			elif char == closer:
				depth -= 1
				if depth < 0:
					break
		if depth != 0 or text.count(opener) != text.count(closer):
			problems.append("{}{}".format(opener, closer))
	if text.count('"') % 2:
		problems.append('"')
	return problems


def checkReplacementSymbols(rule):
	text = _ESCAPE_RE.sub("", rule.replacement)
	if text.isalnum():
		return []
	markup = [char for char in _REPLACEMENT_MARKUP_CHARS if char in text]
	unbalanced = _bracketProblems(text)
	if not markup and not unbalanced:
		return []
	parts = []
	if markup:
		parts.append("contains {} which some speech engines read as a symbol name or treat as markup".format(
			" ".join(markup)
		))
	if unbalanced:
		parts.append("has unbalanced or misplaced paired symbols ({})".format(" ".join(unbalanced)))
	return [makeIssue(
		rule, 2, "SYMBOL_IN_REPLACEMENT", "low",
		"Replacement " + " and ".join(parts) + ".",
		"Remove the symbol, spell it out as a word, or close the pair.",
	)]


def checkEnabledRule(rule, compiled):
	issues = []
	if not rule.pattern.isascii() or not rule.replacement.isascii():
		issues += checkFullwidthSymbols(rule)
		issues += checkTypographicSymbols(rule)
		issues += checkNormalization(rule)
		issues += checkMixedScriptToken(rule)
		issues += checkUnspacedBoundary(rule)
	issues += checkHiddenCharacters(rule)
	issues += checkStructure(rule, compiled)
	issues += checkClassRange(rule, compiled)
	issues += checkUnescapedDot(rule, compiled)
	issues += checkReplacementTemplate(rule, compiled)
	issues += checkReplacementSymbols(rule)
	return issues
