# editorLink.py

_opener = None


def setOpener(opener):
	global _opener
	_opener = opener


def clearOpener():
	global _opener
	_opener = None


def openAtLine(filePath, lineNumber):
	"""Return None when no editor is registered, otherwise True if the file was changed in the editor."""
	if _opener is None:
		return None
	return bool(_opener(filePath, lineNumber))
