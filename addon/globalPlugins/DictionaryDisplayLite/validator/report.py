# report.py

import csv
import io
import json

CSV_COLUMNS = ("Line", "Pattern", "Severity", "Code", "Message", "Suggestion")


def issuePattern(issue):
	return issue["rule"].split("\t", 1)[0]


_SHORT_CUT_MARKERS = (": ", "; ", ", which ", ", so ", ", but ", ". ")


def shortMessage(message):
	"""Return the first part of an issue message, without the long explanation that follows it."""
	cut = len(message)
	for marker in _SHORT_CUT_MARKERS:
		position = message.find(marker)
		if position != -1:
			cut = min(cut, position)
	return message[:cut].rstrip(".")


def formatHeader(result):
	summary = result["summary"]
	header = (
		"File: {file}\n"
		"Lines: {total} ({parsed} rules checked, {skipped} comment or blank lines skipped)\n"
		"Issues: {issues} (critical {critical}, high {high}, medium {medium}, low {low})"
	).format(
		file=result["file"], total=result["total_lines"], parsed=result["parsed_rules"],
		skipped=result["skipped_lines"], issues=summary["total"], critical=summary["critical"],
		high=summary["high"], medium=summary["medium"], low=summary["low"],
	)
	if result.get("hidden"):
		header += "\nHidden by the issue type filter: {}".format(result["hidden"])
	return header


def formatIssueLines(issue):
	lines = ["Line {line} {pattern} {severity} {code}: {message}".format(pattern=issuePattern(issue), **issue)]
	if issue["suggestion"]:
		lines.append("    Suggestion: {}".format(issue["suggestion"]))
	return lines


def formatReportText(result):
	parts = [formatHeader(result), ""]
	for issue in result["issues"]:
		parts.extend(formatIssueLines(issue))
	return "\n".join(parts) + "\n"


def toCsv(result):
	buffer = io.StringIO(newline="")
	writer = csv.writer(buffer, lineterminator="\r\n")
	writer.writerow(CSV_COLUMNS)
	for issue in result["issues"]:
		writer.writerow([
			issue["line"], issuePattern(issue), issue["severity"], issue["code"],
			issue["message"], issue["suggestion"] or "",
		])
	return buffer.getvalue()


def toJson(result):
	return json.dumps(result, ensure_ascii=False, indent=2)


def logResult(result, logger):
	summary = result["summary"]
	logger.info(
		"Dictionary check of {}: {} rules, {} issues (critical {}, high {}, medium {}, low {})".format(
			result["file"], result["parsed_rules"], summary["total"], summary["critical"],
			summary["high"], summary["medium"], summary["low"],
		)
	)
	for issue in result["issues"]:
		if issue["severity"] == "critical":
			logger.error("Dictionary line {} {}: {}".format(issue["line"], issue["code"], issue["message"]))
		elif issue["severity"] == "high":
			logger.warning("Dictionary line {} {}: {}".format(issue["line"], issue["code"], issue["message"]))
