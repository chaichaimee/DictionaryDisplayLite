<div align="center">

<img src="https://www.nvaccess.org/files/nvda/documentation/userGuide/images/nvda.ico" alt="NVDA Logo" width="120" style="display: block; margin: 0 auto 20px;">

# DictionaryDisplayLite

Speak less, understand more &mdash; a lighter, searchable way to browse and manage NVDA's speech dictionaries.

**author:** chai chaimee  
**url:** https://github.com/chaichaimee/DictionaryDisplayLite

</div>

---

## Introduction

NVDA's built-in speech dictionaries (Voice, Default, and Temporary) let you tell NVDA how to pronounce or replace certain text, but the standard dialogs can be verbose to listen to and awkward to search through when a dictionary grows large.

DictionaryDisplayLite makes working with these dictionaries faster and quieter. While a dictionary dialog is open, it automatically condenses each spoken list entry down to just its essential words. It also adds a dedicated quick-access menu, a custom search-and-edit tool for the Voice dictionary with a filterable list and a built-in reordering system, and a background checker that finds broken or invalid entries that NVDA itself would otherwise silently ignore.

All of this add-on's behavior is local: it only reads and writes dictionary and settings files already on your computer. It does not make any network requests.

### Hot Keys

> **Control+Shift+D**  
> Single Tap : Open the Voice dictionary dialog  
> Double Tap : Open the Default dictionary dialog  
> Triple Tap (or more) : Open the Temporary dictionary dialog

Taps must follow each other within 350 milliseconds to be counted together. Once that window elapses, NVDA opens the dialog matching however many taps were pressed within it.

<br>

> **Shift+Windows+D**  
> Single Tap : Open the DictionaryDisplayLite quick menu  
> Double Tap : Open "Search and Edit Voice Dictionary" directly

As with the dictionary-opening gesture above, taps must land within 350 milliseconds of each other. A single tap opens the quick menu; two taps in quick succession skip the menu and jump straight into the voice dictionary search-and-edit tool.

## Features

### Condensed Dictionary Entries

NVDA's dictionary list items are normally announced with full field labels, for example something like "Pattern: hello; Replace: hi; Case sensitive: no". This can be slow to listen to while browsing a long list.

DictionaryDisplayLite watches for a dictionary dialog being in the foreground (it checks the dialog's title for words like "dictionary", "default", "voice", or "temporary"). While one of these dialogs is active and focus lands on a list item, the add-on:

1. Splits the item's spoken name on semicolons into segments.
2. For each segment, if it contains a colon (a "Label: value" pair), keeps only the value after the colon; otherwise keeps the whole segment.
3. Joins the kept values back together with single spaces and collapses any repeated whitespace.
4. Temporarily swaps in this shortened text as the item's name only for the moment NVDA speaks it, then immediately restores the original name afterward so nothing else is affected.

This can be switched off at any time from the Settings dialog if you prefer NVDA's normal, fully-labeled announcements.

### Quick Menu

Opened with a single tap of Shift+Windows+D, this is a small floating, keyboard-driven list of shortcuts:

* **Open dictionary file** &mdash; a submenu offering Voice, Default, or Temporary dictionary. Selecting one opens that dictionary's file on disk in its associated application.
* **Open dictionary folder** &mdash; the same three-way submenu, but opens the folder containing that dictionary's file instead.
* **Check dictionary error** &mdash; runs the dictionary error checker described below.
* **Search and Edit Voice Dictionary** &mdash; opens the custom voice dictionary editor described below.
* **DictionaryDisplayLite Settings** &mdash; opens the add-on's settings dialog.

Navigation inside the menu:
* Up/Down arrows move between items as usual.
* Enter or Right Arrow opens a highlighted submenu, or activates a highlighted action item.
* Left Arrow or Escape steps back out of a submenu; pressing Escape with no submenu open closes the menu entirely.

The Temporary dictionary has no file on disk until NVDA actually saves one, so choosing its file or folder option before that point simply reports that none exists yet.

### Check Dictionary Error

NVDA's own dictionary loader quietly drops any entry with an invalid regular expression, only writing a note to its log file. This feature re-reads the Voice and Default dictionary files directly from disk, in a background thread, and checks every entry itself so problems don't go unnoticed.

For each line in a dictionary file, it checks for:
* Lines that don't split into exactly four tab-separated fields (pattern, replacement, case-sensitivity flag, and type).
* An empty pattern.
* A type flag that isn't one of the entry types this NVDA installation currently supports.
* A case-sensitivity flag that isn't "0" or "1".
* For entries specifically marked as the regular-expression type, a pattern that fails to compile as a valid regular expression.

If no dictionary files are found, NVDA reports that nothing could be checked. If files are found but no problems are found, NVDA simply reports that the check completed cleanly. If problems are found, a plain-text report is written to a file and opened automatically for review.

### Search and Edit Voice Dictionary

Opened via the quick menu, or by tapping Shift+Windows+D twice in quick succession. It gives the Voice dictionary a dedicated search-and-edit interface that NVDA's own dictionary dialog does not offer.

Layout and controls:
* A checkbox to treat the search box's text as a regular expression instead of plain text.
* A search box that filters the entry list as you type, matching against each entry's pattern and replacement text together.
* A list of matching entries, each shown as "pattern &rarr; replacement (line N)", where the line number reflects the entry's real position in the dictionary file.
* Add, Edit, and Remove buttons below the list.
* A right-click context menu on the list offering Move up, Move down, and Remove.

Step-by-step behavior:
1. **Searching:** the visible list updates immediately on every keystroke. The spoken result count, however, is debounced: it only announces "N results found" once typing has paused for 700 milliseconds, so rapid typing doesn't trigger a flood of announcements.
2. **Adding an entry:** opens a blank entry dialog defaulting to the line right after the current last entry. Confirming inserts the new entry at whatever line number was specified, shifting existing entries down as needed, then immediately rewrites the dictionary file on disk.
3. **Editing an entry:** opens the same style of dialog pre-filled with the selected entry's current pattern, replacement, case sensitivity, type, and line number. Changing the line number and confirming moves the entry to that new position rather than overwriting whatever entry was already there; the file is rewritten immediately.
4. **Removing an entry:** deletes the selected entry and rewrites the file immediately.
5. **Reordering (Move up / Move down):** swaps the selected entry with its neighbor and rewrites the file immediately. This is only available while the search box is empty; if a search filter is active, NVDA asks you to clear it first, since positions during a filtered view could be ambiguous.

> **Note:** Add, Edit, Remove, and Move all save to disk the moment they happen. Cancelling or closing the dialog afterward does not undo any of these already-applied changes &mdash; only closes the window. If anything changed during the session, NVDA's live Voice dictionary is reloaded automatically when the dialog closes, so your edits take effect immediately without needing to restart NVDA.

### Add / Edit Entry Dialog

This smaller dialog is opened by the Add and Edit buttons above and handles the actual entry fields:
* **Pattern** &mdash; the text or expression to match. Cannot be left empty.
* **Replace** &mdash; the replacement text.
* **Case sensitive** &mdash; a checkbox for whether matching should respect letter case.
* **Type** &mdash; a radio group listing every entry type this NVDA installation supports (this list is read dynamically from NVDA itself, so it may include more than the classic Anywhere / Whole word / Regular expression choices on newer NVDA versions).
* **Line number** &mdash; where in the dictionary file this entry should live.

On confirming, NVDA validates that the pattern isn't empty and that the line number is a whole number of 1 or greater, and reports a clear spoken message if either check fails. If the pattern is marked as a regular expression and doesn't compile, NVDA reports the underlying error instead of accepting it.

### Settings

Reached from the quick menu's "DictionaryDisplayLite Settings" item. Currently offers a single option:
* **Condense dictionary entries in the list (shorten spoken labels)** &mdash; enabled by default. Turning this off restores NVDA's normal, fully-labeled announcements for dictionary list items.

Settings are saved to a small JSON file in your NVDA configuration folder and are restored automatically the next time NVDA starts.

## Support Me

If this tool has made your life easier, consider fueling the next update with a small donation.

<p>
  <a href="https://buy.stripe.com/dRm9AU1xQ3Ds22N6VK1VK01">
    <img src="https://img.shields.io/badge/Donate-Support%20Me-blue?style=for-the-badge&logo=stripe" alt="Support me">
  </a>
</p>

Your support means the world. Let's build something great together

&copy; 2026 Chai Chaimee NVDA Add-on Released under GNU GPL