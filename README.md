# Disgaea 5 Complete Save Editor

A small, offline Tkinter utility for Windows and Python 3.10+ that reads
Disgaea 5 Complete PC save files and writes edited copies. It uses only Python's
standard library.

## Run

From the directory containing the checkout folder (for this workspace,
`D:\Projects`):

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
- A batch action to set levels for all army and reserve characters
- Ten weapon mastery levels and aptitudes
- The five equipped-item IDs, levels, types, and ranks for a selected character
- A batch action to set equipped-item levels across army and reserve characters
- Nine resident slots on each equipped item, including resident ID, unsubdued
  level, maximum growth, and subdued state
- A batch action to move all non-empty residents from equipped and unequipped
  saved items into free Innocence Warehouse slots, leaving one slot empty
- A bulk action to subdue all non-empty residents on equipped items for every
  army and reserve character
- A separate Innocence Warehouse browser for editing existing value/growth
  fields, plus a bulk subdued action

The editor exposes direct resident editing for equipped items and can move
residents from equipped and unequipped saved items, but it does not expose a
separate item warehouse editor. The Innocence Warehouse browser covers its
256-record table, edits value/growth fields, and preserves unmapped bytes; the
batch transfer currently reserves one slot pending in-game validation of full
capacity.
If there are more residents than transfer slots, it moves equipped residents
first, then moves what fits from unequipped items and leaves the rest on their
items. Warehouse subduing uses the item-resident flag at byte `+0x13`; the
earlier `+0x03` mapping caused a crash when applied to all entries. The
corrected mapping still needs in-game validation. Unique Innocents (IDs 202
through 252 with value 1) are protected from transfer and bulk subduing; the
green Hostage Negotiator in the supplied screenshot maps to ID 229. Ordinary
Innocents can also have value 1, so the ID range is checked too. Power
maximization is not available because the record IDs have not been mapped
reliably to the game's type-specific caps.
`SystemSave.sav` is not edited. Equipment IDs are raw game IDs; the editor does
not validate them against the game's item database, and changing an ID does not
copy the other item's properties. Item levels can be set from 0 to 9999. The

Click **Residents...** beside an equipped item to edit its nine resident slots.
Resident IDs are raw game values (0 means empty); the editor preserves unmapped
bytes in each resident record. Use **Innocence Warehouse...** for the separate
stored innocence entries; these are not residents attached to equipped items.
Its **Subdue all...** action sets the subdued flag on eligible active entries,
leaving Unique Innocents unchanged.

## Safety

The editor never overwrites the selected input save. “Save as new slot…” uses an
exclusive create and refuses to replace an existing file. The suggested output
is the next unused `Save_###.sav` in the same folder, so the game can load it as
a separate slot. Close the game before loading the edited slot.

Keep a separate backup of your saves before using any editor.

## Verify

Run the focused tests from the directory containing the checkout folder:

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
