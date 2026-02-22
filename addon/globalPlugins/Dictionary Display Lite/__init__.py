# __init__.py
# Copyright (C) 2026 Chai Chaimee
# Licensed under GNU General Public License. See COPYING.txt for details.

"""
DictionaryDisplayLite add-on for NVDA.
Modifies the speech of dictionary entries to remove redundant labels
(e.g., "Pattern:", "Replacement:", "case:", "Type:") and speaks only the values.
"""

import re
import globalPluginHandler
import controlTypes
from logHandler import log
import addonHandler

# Initialize translation
addonHandler.initTranslation()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    """
    Global plugin that intercepts focus events on dictionary list items
    and temporarily alters their names for concise speech.
    """

    def __init__(self):
        super(GlobalPlugin, self).__init__()
        # Translators: Log message when the add-on is loaded
        log.info(_("DictionaryDisplayLite loaded"))

    def event_gainFocus(self, obj, nextHandler):
        """
        Triggered when an object gains focus.
        If the object is a dictionary list item, modify its name temporarily.
        """
        if self._isDictionaryListItem(obj):
            original = obj.name
            if original:
                modified = self._condenseDictionaryEntry(original)
                if modified and modified != original:
                    obj.name = modified
                    # Let the original event handlers run (speech, etc.)
                    nextHandler()
                    # Restore original name to avoid permanent changes
                    obj.name = original
                    return
        # Not a dictionary item or no modification needed
        nextHandler()

    def _isDictionaryListItem(self, obj):
        """
        Determine if the given object is a list item inside a dictionary dialog.
        """
        # Must be a list item
        if obj.role != controlTypes.ROLE_LISTITEM:
            return False

        # Traverse parents to find the dialog
        parent = obj.parent
        while parent and parent.role != controlTypes.ROLE_DIALOG:
            parent = parent.parent

        if not parent:
            return False

        # Check dialog title against translated keywords
        title = parent.windowText
        if not title:
            return False

        title_lower = title.lower()
        # Translators: Part of the dictionary dialog title (e.g., "Default dictionary", "Voice dictionary")
        if _("dictionary") in title_lower:
            return True
        # Fallback for possible localized titles that might not contain the exact word "dictionary"
        # Translators: Additional keywords that might appear in dictionary dialog titles
        if _("default") in title_lower or _("voice") in title_lower or _("temporary") in title_lower:
            return True
        # Final fallback to English (if addon lacks translation)
        if "dictionary" in title_lower:
            return True

        return False

    def _condenseDictionaryEntry(self, rawText):
        """
        Remove labels like 'Pattern:', 'Replacement:', etc. from a dictionary entry.
        Returns the condensed string or None if no change.
        """
        # Split by semicolon to get each field
        parts = rawText.split(';')
        values = []

        for part in parts:
            part = part.strip()
            if ':' in part:
                # Split only at the first colon to separate label from value
                _, value = part.split(':', 1)
                values.append(value.strip())
            else:
                # If no colon (unlikely), keep the whole part
                values.append(part)

        # Join all values with a single space
        condensed = ' '.join(values)
        # Normalize whitespace
        condensed = re.sub(r'\s+', ' ', condensed).strip()

        # Return None if unchanged or empty
        if not condensed or condensed == rawText:
            return None
        return condensed