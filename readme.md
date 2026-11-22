![NVDA Logo](https://www.nvaccess.org/files/nvda/documentation/userGuide/images/nvda.ico)

# DictionaryDisplayLite

Manage your NVDA speech dictionaries faster and quieter: condensed list announcements, a quick menu, a searchable dictionary editor, entry lookup for selected text, and a built-in dictionary checker.

**author:** chai chaimee

**url:** https://github.com/chaichaimee/DictionaryDisplayLite

## Introduction

DictionaryDisplayLite makes working with NVDA speech dictionaries fast, quiet, and safe. Large dictionaries become easy to handle: lists are announced in a short, clean form, any dictionary can be opened with a single shortcut, and a custom editor lets you search, add, edit, reorder, disable, and enable entries without losing your place.

The add-on also tells you why a word is pronounced the way it is. It shows exactly which dictionary entries change the text you selected, in the order NVDA applies them, and it can check your dictionary for mistakes and report each problem with a suggested fix.

## Hot Keys

**Control+Shift+D**

- Single Tap : Open the Voice dictionary dialog
- Double Tap : Open the Default dictionary dialog
- Triple Tap : Open the Temporary dictionary dialog

**Shift+Windows+D**

- Single Tap : Open the DictionaryDisplayLite quick menu
- Double Tap : Open Search and Edit Voice Dictionary directly
- Triple Tap : Validate the speech dictionary of the current synthesizer

## Features

### Condensed Dictionary List Announcements

When one of NVDA's dictionary dialogs (Voice, Default, or Temporary) is in front, each entry in the list is spoken in a shortened form. The field labels are removed and only the values are read, so you hear the content of the entry instead of repeated label words.

This can be turned off at any time in the DictionaryDisplayLite Settings item of the quick menu, using the check box "Condense dictionary entries in the list (shorten spoken labels)". It is on by default.

### Quick Menu

Press Shift+Windows+D once to open a small list menu. The first item is announced as soon as it opens. The menu contains these items in this order:

- Open dictionary file : choose Voice dictionary, Default dictionary, or Temporary dictionary to open its file in your default program.
- Open dictionary folder : choose Voice dictionary, Default dictionary, or Temporary dictionary to open the folder that holds it.
- Check dictionary error
- Find dictionary entries for selected text
- Validate synthesizer dictionary
- Search and Edit Voice Dictionary
- DictionaryDisplayLite Settings

Move through the list with the Up and Down arrow keys. Press Enter or Right Arrow to open a submenu or run an item. Press Left Arrow or Escape to go back from a submenu. Press Escape in the main list to close the menu.

The Temporary dictionary exists only for the current session and has no file on disk, so NVDA reports that it has no file or folder yet.

### Opening the Speech Dictionaries Quickly

Control+Shift+D opens NVDA's own dictionary dialogs directly, with no need to go through the NVDA menu. The number of taps chooses the dictionary: one tap for Voice, two taps for Default, three taps for Temporary.

### Search and Edit Voice Dictionary

A custom editor built for large voice dictionaries, which NVDA's own dialog makes hard to browse. Open it with a double tap on Shift+Windows+D, or from the quick menu. Focus starts on the entry list.

Every entry appears in the list as pattern, an arrow, and the replacement. When Show line number is checked, the line of the entry in the dictionary file is added. Entries that are turned off are announced with the word disabled.

- Use regular expression for search : treat the search text as a regular expression.
- Show line number : show or hide the line number of each entry. It is checked by default and the choice is remembered.
- Search : the list narrows as you type and searches both the pattern and the replacement. After you stop typing, the number of results is announced.
- Add : opens a blank entry dialog, so nothing from the selected entry can be duplicated by accident.
- Edit : opens the selected entry for changes.
- Remove : deletes the selected entry.

The entry dialog has the fields Pattern, Replace, Case sensitive, Type, and Line number. The Type choices are the entry types your NVDA version supports, for example Anywhere, Whole word, and Regular expression. The pattern cannot be empty, and a regular expression that is not valid is rejected with a message.

Every change is written to the dictionary file immediately. Comments and blank lines stored above an entry are kept, and lines that could not be parsed are kept unchanged, so saving never deletes your notes. Cancel only closes the window and does not undo changes that were already saved. When you close the editor after making changes, NVDA's live voice dictionary is reloaded, so the changes work without restarting NVDA.

The search box accepts a regular expression only when it is valid, not too long, and not too complex, and it stops if it takes too long. In each case a spoken message tells you.

### Insert a Word at a Chosen Line

In the Add or Edit dialog, the Line number field decides where the entry is placed in the dictionary. The new or moved entry is inserted at that line and the entry that was there is shifted down. Nothing is overwritten. This makes it easy to place a specific rule before a general one in a big dictionary.

1. Open Search and Edit Voice Dictionary.
2. Press Add, or select an entry and press Edit.
3. Fill in Pattern, Replace, Case sensitive, and Type.
4. Type the line number where the entry should go in Line number. It must be a whole number of 1 or greater.
5. Press OK. The entry is saved at that position and selected in the list.

### Disable and Enable Entries

Open the context menu on an entry in the editor with the Applications key. Disable entry switches the selected entry off without deleting it, and Enable entry switches it back on. A disabled entry stays in the file with a leading # at the start of its line, so NVDA ignores it for speech.

Disable all and Enable all switch the whole dictionary off or on in one step. The menu shows Enable all when every switchable entry is already off. If some entries cannot be switched off because their lines are not in a valid format, the number of entries that were disabled and the number that could not be disabled are announced.

### Reorder Entries

The order of entries matters because NVDA applies them from top to bottom. In the editor's context menu, Move up and Move down shift the selected entry one position. Reordering works only while the search box is empty; otherwise a message asks you to clear it first.

### Find Dictionary Entries for Selected Text

Shows which speech dictionary entries change a piece of text, in the order NVDA applies them. It uses the text you selected, or the current line if nothing is selected. Choose it from the quick menu.

1. Select a word or sentence in any window, or just place the cursor on a line.
2. Press Shift+Windows+D once and choose Find dictionary entries for selected text.
3. The window opens with the text already checked. The number of entries that change the text is announced, and focus moves to the list.
4. Move through the list. For each entry the columns show its number, the dictionary it comes from, its line, its pattern, the text it matched, and what it becomes.
5. Read the Details of the selected entry box for the full information: dictionary, line, pattern, replacement, type, case sensitivity, the text before and after the entry, and a note when an entry matched but did not change the text.
6. Read Text after all dictionaries to hear the final result.

You can change the text in the Text to check box and press Check to test any text. The optional field Show only entries containing this word narrows the list to entries whose pattern, matched text, or result contains that word.

Press Enter on an entry, or use Edit entry, to open it directly in the dictionary editor at its line. The context menu offers Edit in dictionary editor and Copy dictionary line. Editing is available for entries of the Voice and Default dictionaries. After you change something, the check runs again automatically. Copy report copies the whole result to the clipboard.

If no entry changes the text, you are told that if the word is still pronounced wrongly, the cause is outside the dictionaries. If NVDA's speech dictionary processing is turned off, or a dictionary is turned off, the window tells you so.

### Validate Synthesizer Dictionary

Checks the speech dictionary of the synthesizer you are using right now and reports every problem found. Press Shift+Windows+D three times, or choose Validate synthesizer dictionary in the quick menu.

1. Trigger the command. The add-on looks for the dictionary file of the current synthesizer and voice in your NVDA speechDicts folder.
2. If the file cannot be identified, a file chooser opens so you can select a dictionary file (.dic or .txt).
3. The check runs in the background so NVDA stays responsive. A short tone signals the result: a high tone when no problems are found and a lower tone when there are.
4. The summary is announced: the number of rules checked and the number of critical, high, medium, and low issues.
5. A results window opens with the full list of issues.

### Validation Results Window

The results window is designed for working through the problems one by one.

- Issue types to show : a list of check boxes, one per issue type with its count. Uncheck a type to hide it. The choice is remembered for the next check, and the number of hidden issues is mentioned in the summary.
- Issues : a list with the columns Line, Pattern, Severity, Code, Message, and Suggestion.
- Show all types and Hide all types : switch every issue type on or off at once.
- Show description of each issue : when cleared, the long explanation and the suggestion are hidden and only a short message remains.
- Show line number : show or hide the line column.
- Copy Report : copy the whole report to the clipboard.
- Export CSV : save the issues to a CSV file.

Press Enter on an issue to open the dictionary file in your default program. The context menu offers Edit in dictionary editor, which opens the editor on the line of that issue, Open dictionary file, and Copy this issue. After you change the file in the editor, the check runs again automatically.

Problems are rated critical, high, medium, or low. Critical and high issues are also written to the NVDA log.

### What the Dictionary Check Looks For

The check reads every rule and reports these kinds of problems:

- Structure : rows with the wrong number of columns, an empty pattern, invalid case sensitivity or enabled values, and damaged characters caused by saving in the wrong encoding.
- Regular expressions : patterns that do not compile, invalid back references, literal braces that are not repetition counts, lookbehinds that can never match, unusual symbol positions such as an empty alternative next to a | symbol, an empty group, or a ^ or $ anchor in the wrong place, character class ranges that match unintended characters, unescaped dots, and word boundaries next to scripts written without spaces.
- Hidden and look-alike characters : invisible or special-space characters, text that is not in Unicode NFC form, full-width symbols and curly quotes in a pattern, and words that mix look-alike letters from different scripts.
- Replacement text : Latin text joined directly to Thai text, mixed-case Latin words, replacement spellings that are not known English words, hyphens at the edges of a replacement, symbols in a replacement that speech engines may read aloud or treat as markup, unbalanced paired symbols, and invalid substitution strings.
- Thai patterns : a single Thai character or a bare Thai letter followed by a dot matching too much, and Thai patterns with no boundary that change nothing or only add a hyphen.
- Rule relationships : duplicate patterns and rules that are shadowed by a later, longer rule.
- Disabled rules : a disabled rule that would fail if it were enabled.

### Check Dictionary Error

A quick health check of your Voice and Default dictionary files, available in the quick menu. It reads the files directly from disk, so it also finds entries that NVDA silently ignored when it loaded the dictionary.

1. Choose Check dictionary error in the quick menu.
2. Wait for the message that the check is running. It works in the background.
3. If no problem is found, you hear a message that the check is complete and no problems were found.
4. If problems are found, a report named dictionary_error_report.txt is saved in the ChaiChaimee\DictionaryDisplayLite folder inside your NVDA configuration folder and opened for you. Each problem is listed with its line number.

The check reports lines that do not have four tab-separated fields, empty patterns, unrecognized entry types, invalid case sensitivity flags, and invalid regular expressions in entries of the regular expression type.

## Support Me

If this tool has made your life easier, consider fueling the next update with a small donation.

[![Support me](https://img.shields.io/badge/Donate-Support%20Me-blue?style=for-the-badge&logo=stripe)](https://buy.stripe.com/dRm9AU1xQ3Ds22N6VK1VK01)

Your support means the world. Let's build something great together

© 2026 Chai Chaimee NVDA Add-on Released under GNU GPL
