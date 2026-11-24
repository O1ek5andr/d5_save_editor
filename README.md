# Disgaea 5 Complete Save Editor

A small, offline Tkinter utility for Windows and Python 3.10+ that reads
Disgaea 5 Complete PC save files and writes edited copies. It uses only Python's
standard library.

## Run

From the repository root:

```powershell
python -m d5_save_editor.app
```

Open `Save_###.sav` or `AutoSave.sav` from:

```text
%APPDATA%\Nippon Ichi Software, Inc\Disgaea 5 Complete\<Steam account ID>\SaveData
```

The first version edits:

- HL (64-bit) and Item Points
- Character level and Mana
- Ten weapon mastery levels and aptitudes
- The five equipped-item IDs, levels, types, and ranks for a selected character
- Nine resident slots on each equipped item, including resident ID, unsubdued
  level, maximum growth, and subdued state

The warehouse item list and `SystemSave.sav` are not edited. Equipment IDs are
raw game IDs; the editor does not validate them against the game's item
database, and changing an ID does not copy the other item's properties.
Item levels can be set from 0 to 9999 for equipped items.
Click **Residents...** beside an equipped item to edit its nine resident slots.
Resident IDs are raw game values (0 means empty); the editor preserves unmapped
bytes in each resident record.

## Safety

The editor never overwrites the selected input save. “Save as new slot…” uses an
exclusive create and refuses to replace an existing file. The suggested output
is the next unused `Save_###.sav` in the same folder, so the game can load it as
a separate slot. Close the game before loading the edited slot.

Keep a separate backup of your saves before using any editor.

## Verify

Run the focused tests from the repository root:

```powershell
python -m unittest discover -s .\d5_save_editor\tests
```

## Format references

- [D5 Mod Kit save parser and format notes](https://github.com/eraser4521/D5ModKit/blob/main/d5lib/savegame.py)
- [D5 Mod Kit executable/save analysis](https://github.com/eraser4521/D5ModKit/blob/main/docs/EXE_ANALYSIS.md)
- [Disgaea 5 save dumper](https://github.com/qeedquan/game_format_dumpers/blob/master/disgaea5/save-dumper.go)
- [Disgaea 5 Complete Cheat Engine table discussion](https://fearlessrevolution.com/viewtopic.php?f=4&t=6692)

The linked `disgaea-pc-tools` project targets the original Disgaea PC release,
not Disgaea 5 Complete.
