# __main__.py

import os
import sys

if __package__:
	from .core import validate_dictionary
	from .report import toJson
else:
	sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	from validator.core import validate_dictionary
	from validator.report import toJson


def main(argv):
	if len(argv) != 2:
		sys.stderr.write("Usage: python <path to the validator folder> <dictionary file>\n")
		return 2
	try:
		result = validate_dictionary(argv[1])
	except OSError as error:
		sys.stderr.write("Cannot read dictionary file: {}\n".format(error))
		return 2
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")
	sys.stdout.write(toJson(result) + "\n")
	summary = result["summary"]
	return 1 if summary["critical"] or summary["high"] else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
