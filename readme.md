![NVDA Logo](https://www.nvaccess.org/files/nvda/documentation/userGuide/images/nvda.ico)

# DictionaryDisplayLite

Faster, quieter speech dictionary management for NVDA: condensed list announcements, a quick menu, a searchable dictionary editor and a built-in dictionary checker.

**author:** chai chaimee

**url:** https://github.com/chaichaimee/DictionaryDisplayLite

## Introduction

NVDA speech dictionaries let you fix how your synthesizer pronounces words, but working with them can be slow and noisy. Each entry in the standard dictionary list is read out with long labels, large dictionaries are hard to browse, and a single mistake in a pattern can silently break an entry.

DictionaryDisplayLite solves these problems. It shortens what NVDA says for each dictionary entry, gives you quick keyboard shortcuts to open the Voice, Default and Temporary dictionaries, adds a quick menu with the most useful dictionary actions, and provides its own voice dictionary editor with search, reordering, and the ability to turn individual entries off without deleting them. It can also check a dictionary file for errors and show you a clear report that lists exactly which line is wrong and how to fix it.

## Hot Keys

**Control+Shift+D**

- Single Tap : Open the Voice dictionary dialog
- Double Tap : Open the Default dictionary dialog
- Triple Tap (or more) : Open the Temporary dictionary dialog

**Shift+Windows+D**

- Single Tap : Open the DictionaryDisplayLite quick menu
- Double Tap : Open Search and Edit Voice Dictionary directly
- Triple Tap (or more) : Validate the speech dictionary of the current synthesizer

These two shortcuts are listed in the NVDA Input Gestures dialog under the category **DictionaryDisplayLite**.

## Features

### 1. Condensed Dictionary Entry Announcements

When one of NVDA's dictionary dialogs is in front (any dialog whose title contains the words dictionary, default, voice or temporary), moving through the entry list is announced in a shorter form. NVDA normally reads every field name together with its value. DictionaryDisplayLite removes the field names and speaks only the values, so you hear what matters and nothing else.

Example: an entry that NVDA would normally announce as a series of labelled fields, separated by semicolons, is spoken as just the values joined together, with extra spaces removed.

The original text of the entry is never changed. Only the spoken announcement is shortened. This feature is on by default and can be turned off in the add-on settings (see Settings below).

### 2. Quick Open of the Dictionary Dialogs

Instead of going through the NVDA menu, press **Control+Shift+D** once for the Voice dictionary, twice for the Default dictionary, or three times for the Temporary dictionary. These open NVDA's own standard dictionary dialogs.

### 3. Quick Menu

Press **Shift+Windows+D** once to open a small floating menu. The first item is announced as soon as the menu appears. The menu works like a list that you can drill into:

- **Up and Down Arrow** : Move between items
- **Enter** : Run the selected item, or open it if it contains a submenu
- **Right Arrow** : Open a submenu
- **Left Arrow** : Go back to the previous level
- **Escape** : Go back one level, or close the menu when you are already at the top

The menu contains these items, in this order:

- **Open dictionary file** : A submenu with Voice dictionary, Default dictionary and Temporary dictionary. The chosen dictionary file is opened in the program Windows uses for that file type.
- **Open dictionary folder** : A submenu with the same three choices. The folder that contains the chosen dictionary is opened in File Explorer.
- **Check dictionary error** : Scans the Voice and Default dictionary files for errors (see Feature 4).
- **Validate synthesizer dictionary** : Runs the full dictionary check (see Feature 5).
- **Search and Edit Voice Dictionary** : Opens the add-on's own editor (see Feature 7).
- **DictionaryDisplayLite Settings** : Opens the settings dialog.

The Temporary dictionary exists only during the current session and is never saved to disk. If you choose it under Open dictionary file or Open dictionary folder, NVDA tells you that it has no file or folder on disk yet. The same message is spoken for any dictionary that has not been created yet.

### 4. Check Dictionary Error

This quick scan reads the Voice and Default dictionary files directly from disk. This matters because NVDA silently discards entries with an invalid regular expression and shows no message to the user, so a broken entry can simply stop working without any warning.

The scan reports these problems: a row that does not have exactly four tab-separated fields, an empty pattern, an unrecognized entry type, an unrecognized case-sensitivity flag, and an invalid regular expression (checked only for entries whose type is Regular expression).

How it behaves:

1. NVDA says that the dictionaries are being checked and asks you to wait.
2. If no dictionary file exists, NVDA tells you that no dictionary file was found to check.
3. If no problem is found, NVDA announces that the check is complete and that no problems were found. No file is created.
4. If problems are found, a text report named **dictionary_error_report.txt** is saved in the add-on's folder inside your NVDA configuration folder (ChaiChaimee\DictionaryDisplayLite) and is opened automatically. Each problem is listed under the name and path of the dictionary it belongs to, together with its line number.

### 5. Validate Synthesizer Dictionary

This is a deeper dictionary checker. Press **Shift+Windows+D** three times, or choose **Validate synthesizer dictionary** in the quick menu.

Step by step:

1. Press **Shift+Windows+D** three times. NVDA says that it is checking the dictionary.
2. The add-on looks in your NVDA speechDicts folder for the dictionary that belongs to the synthesizer and voice you are currently using. If it cannot identify one single matching file, a standard Open File dialog appears so that you can pick a dictionary file (.dic or .txt) yourself. If you cancel that dialog, nothing happens.
3. The check runs in the background, so NVDA stays responsive. If a check is already running, NVDA tells you so.
4. When the check finishes, you hear a short beep and a summary: how many rules were checked and how many issues were found at each severity level (critical, high, medium and low). A higher beep means no issues were found, and a lower beep means issues were found.
5. If any issues exist, a result window opens (see Feature 6). Critical and high severity issues are also written to the NVDA log.

**What the checker looks for**

Issues are sorted by severity, then by line number. Each issue has a code, a message that explains the problem, and a suggestion that explains how to fix it.

- **Critical** : A malformed row (wrong number of fields, an empty pattern, or a flag that is not 0 or 1), a file that is not valid UTF-8, and a pattern that is not a valid regular expression.
- **High** : A back-reference in the replacement that points to a group the pattern does not have, invisible or special-space characters, a damaged character caused by a wrong file encoding, an invalid substitution string, an overly broad Thai pattern that would fire inside ordinary words, Latin text joined directly to Thai text without a hyphen or space, look-alike letters from different scripts mixed in one word, and an empty alternative next to a | symbol.
- **Medium** : Mixed-case Latin words in a replacement, a replacement spelling that is not a known English word when the pattern is a plain English word, a hyphen at the edge of a replacement next to Latin text, a Thai pattern with no boundary that is only given a hyphen or replaced by identical text, braces that are not a repetition count, a lookbehind that can never match, a ^ or $ anchor in the wrong place, an empty group, a character range that matches unintended characters, full-width symbols that look like regex symbols, text that is not in Unicode NFC form, and rules that are disabled but would fail if they were enabled.
- **Low** : Duplicate patterns, a rule that can prevent a later, longer rule from matching, curly quotes in a pattern with no plain quote alternative, a dot after a letter that is not escaped, a word boundary next to a script written without spaces (Thai, Lao, Khmer, Myanmar, Japanese or Chinese), a hyphen at the edge of a replacement next to Thai text, and unbalanced or markup-like symbols in a replacement.

Disabled rules are checked too, but their findings are reported one severity level lower and are marked as belonging to a disabled rule.

### 6. The Result Window

The window title shows the number of issues. It contains:

- **Issue types to show** : A list of check boxes, one for each issue type, with the number of issues found. Types that have issues come first. Uncheck a type to hide it. NVDA announces whether the item is now checked or not checked. Your choice is remembered for later checks, and the number of hidden issues is mentioned in the summary.
- **Issues** : A table with the columns Line, Pattern, Severity, Code, Message and Suggestion.
- **Show all types** : Turns every issue type back on.
- **Copy Report** : Copies the full report as text to the clipboard.
- **Export CSV** : Saves the issues as a CSV file. The save dialog starts in the folder you used last, or in the dictionary's folder.
- **Close** : Closes the window. Escape does the same.
- **Show description of each issue** : When it is turned off, the table shows only a short version of each message and hides the Suggestion column. Your choice is remembered.

In the Issues table, press **Enter** on an issue to open the dictionary file. Press the **Applications key** (or Shift+F10) to open a menu with:

- **Edit in dictionary editor** : Opens the add-on's editor and selects the entry on the line of the issue.
- **Open dictionary file** : Opens the file in its default program and tells you which line to go to.
- **Copy this issue** : Copies only the selected issue to the clipboard.

If you changed the dictionary in the editor, the check is run again automatically so that the report is up to date.

### 7. Search and Edit Voice Dictionary

NVDA's own dictionary dialog has no search, which makes a large voice dictionary difficult to use. This editor is built to fix that. Open it by pressing **Shift+Windows+D** twice, or by choosing it in the quick menu. If no voice dictionary is available, or the file cannot be found, NVDA tells you. If the file cannot be read, NVDA asks you to make sure it is saved as UTF-8.

**The dialog**

- **Use regular expression for search** : A check box that is off by default.
- **Search** : Type here to filter the list. The list filters immediately with every key press, and the search matches both the pattern and the replacement text. Without the check box, it is a normal text search that ignores upper and lower case.
- **Dictionary entries** : The list of entries. Each one reads like "pattern → replacement (line 12)", where the number is the real line number in the dictionary file. A disabled entry has ", disabled" added at the end. Focus starts on this list.
- **Add**, **Edit**, **Remove**, **OK** and **Cancel** buttons.

After you stop typing in the search box, NVDA announces how many results were found. If the regular expression is too long or too complex, is not valid, or takes too long to run, NVDA announces that the search was not run or was stopped, instead of freezing.

**Add or edit an entry**

1. Press **Add** to create a new entry, or select an entry and press **Edit** to change it. A small dialog opens.
2. Fill in **Pattern** and **Replace**.
3. Check or uncheck **Case sensitive**.
4. Choose the entry **Type**. The available types are taken from the NVDA version you are running, so the list always matches what your NVDA supports.
5. Set the **Line number**. For a new entry it starts at the line after the last entry. If you type another line number, the entry is inserted at that position and the entry that was there, and everything below it, moves down. It does not overwrite anything. When you edit an entry and change its line number, the entry is moved to that position.
6. Press OK. The pattern cannot be empty, the line number must be a whole number of 1 or greater, and a regular expression type with an invalid pattern is rejected with an explanation. NVDA announces **Entry added** or **Entry updated**.

Because Add always opens a blank dialog, you can never create a duplicate of the selected entry by accident.

**Disable, enable, move and remove entries**

Select an entry and press the **Applications key** (or Shift+F10) to open a context menu with these items:

- **Disable entry** / **Enable entry** : A disabled entry stays in the dictionary file with a # at the start of its line, so NVDA ignores it and does not use it for speech, but you can turn it back on at any time. NVDA announces **Entry disabled** or **Entry enabled**. A row whose format is not valid cannot be turned on or off, and NVDA tells you so.
- **Move up** and **Move down** : Changes the order of entries, which matters because NVDA applies dictionary rules in order. Reordering is only possible when the search box is empty. Otherwise NVDA asks you to clear the search box first.
- **Remove** : Deletes the selected entry. NVDA announces **Entry removed**. The Remove button does the same.

**Saving**

Every Add, Edit, Remove, Enable, Disable and Move is written to the dictionary file immediately. The file is written safely through a temporary file, so a failed save cannot leave a half-written dictionary. Comment lines and blank lines above each entry are kept exactly as they were, and rows that NVDA cannot parse are written back unchanged. When you close the dialog after making changes, NVDA's live voice dictionary is reloaded, so the changes take effect without restarting NVDA.

Important: Cancel and Escape only close the dialog. They do not undo changes that were already saved.

### 8. Settings

Choose **DictionaryDisplayLite Settings** in the quick menu. The dialog contains one check box:

- **Condense dictionary entries in the list (shorten spoken labels)** : On by default. Turn it off if you prefer NVDA's normal, full announcements.

Press OK to save. The setting is stored in a file called settings.json in the add-on's folder inside your NVDA configuration folder. If the file is missing or damaged, the default setting is used.

## Support Me

If this tool has made your life easier, consider fueling the next update with a small donation.

[![Support me](https://img.shields.io/badge/Donate-Support%20Me-blue?style=for-the-badge&logo=stripe)](https://buy.stripe.com/dRm9AU1xQ3Ds22N6VK1VK01)

Your support means the world. Let's build something great together

© 2026 Chai Chaimee NVDA Add-on Released under GNU GPL
