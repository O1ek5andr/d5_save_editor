from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from d5_save_editor.savefile import (
    ARMY_COUNT_OFFSET,
    BODY_MAGIC,
    EQUIPMENT_ID_OFFSET,
    EQUIPMENT_LEVEL_COPY_OFFSET,
    EQUIPMENT_LEVEL_OFFSET,
    EQUIPMENT_OFFSET,
    EQUIPMENT_RANK_OFFSET,
    EQUIPMENT_SIZE,
    EQUIPMENT_TYPE_OFFSET,
    HEADER_SIZE,
    ITEM_POINTS_OFFSET,
    ITEM_RESIDENT_COUNT,
    ITEM_RESIDENT_GROWTH_OFFSET,
    ITEM_RESIDENT_ID_OFFSET,
    ITEM_RESIDENT_LEVEL_OFFSET,
    ITEM_RESIDENT_OFFSET,
    ITEM_RESIDENT_SIZE,
    ITEM_RESIDENT_SUBDUED_OFFSET,
    MAX_EQUIPMENT_LEVEL,
    MAX_HL,
    ROSTER_OFFSET,
    SAVE_MAGIC,
    STATE_SIZE,
    UNIT_LEVEL_OFFSET,
    UNIT_MANA_OFFSET,
    UNIT_NAME_OFFSET,
    UNIT_SIZE,
    UNIT_USED_OFFSET,
    UNIT_WEAPON_OFFSET,
    WEAPON_SIZE,
    SaveDocument,
    _decode_header,
    _decompress_yukes_lz,
    _encode_header,
)


def make_save() -> bytes:
    header = bytearray(HEADER_SIZE)
    header[:len(SAVE_MAGIC)] = SAVE_MAGIC
    header[0x40:0x40 + len(b"Test save")] = b"Test save"
    header[0xC0:0xC0 + len(b"Test chapter")] = b"Test chapter"

    state = bytearray(STATE_SIZE)
    struct.pack_into("<h", state, ARMY_COUNT_OFFSET, 1)
    unit = ROSTER_OFFSET
    struct.pack_into("<I", state, unit + UNIT_USED_OFFSET, 1)
    state[unit + UNIT_NAME_OFFSET:unit + UNIT_NAME_OFFSET + 5] = b"Test\0"
    struct.pack_into("<H", state, unit + UNIT_LEVEL_OFFSET, 10)
    struct.pack_into("<I", state, unit + UNIT_MANA_OFFSET, 123)

    document = SaveDocument(Path("source.sav"), header, state)
    return document.to_bytes()


class SaveFileTests(unittest.TestCase):
    def test_header_cipher_round_trip(self) -> None:
        original = bytes(range(256))
        self.assertEqual(_encode_header(_decode_header(original)), original)

    def test_yukes_lz_literal_and_overlapping_reference(self) -> None:
        self.assertEqual(
            _decompress_yukes_lz(b"\x03abc\xA2", 6),
            b"abcabc",
        )

    def test_rejects_bad_back_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "back-reference"):
            _decompress_yukes_lz(b"\xA0", 1)

    def test_edits_round_trip_to_a_new_file(self) -> None:
        source = make_save()
        document = SaveDocument.from_bytes(source, "source.sav")
        slot = document.unit_slots()[0]

        document.set_hl(999_999_999)
        document.set_item_points(500)
        current_weapons = document.weapon_values(slot)
        current_weapons[0] = (10, 120)
        document.set_unit(slot, 9999, 999_999_999, current_weapons)
        document.set_equipment(slot, [(123, 250, 4, 20)] * 5)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "Save_002.sav"
            document.write_new_file(destination)
            saved = SaveDocument.load(destination)

        self.assertEqual(saved.hl, 999_999_999)
        self.assertEqual(saved.item_points, 500)
        info = saved.unit_info(slot)
        self.assertEqual(info["level"], 9999)
        self.assertEqual(info["mana"], 999_999_999)
        self.assertEqual(saved.weapon_values(slot)[0], (10, 120))
        self.assertEqual(saved.equipment_values(slot)[0], (123, 250, 4, 20))
        item = ROSTER_OFFSET + slot * UNIT_SIZE + EQUIPMENT_OFFSET
        self.assertEqual(
            struct.unpack_from("<H", saved.state, item + EQUIPMENT_LEVEL_COPY_OFFSET)[0],
            250,
        )
        self.assertEqual(
            struct.unpack_from("<H", saved.state, item + EQUIPMENT_LEVEL_OFFSET)[0],
            250,
        )

    def test_source_file_is_never_overwritten(self) -> None:
        document = SaveDocument.from_bytes(make_save(), "source.sav")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "already-exists.sav"
            destination.write_bytes(b"untouched")
            with self.assertRaises(FileExistsError):
                document.write_new_file(destination)
            self.assertEqual(destination.read_bytes(), b"untouched")

    def test_residents_round_trip_and_preserve_unmapped_bytes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        slot = document.unit_slots()[0]
        item_index = 2
        item = ROSTER_OFFSET + slot * UNIT_SIZE + EQUIPMENT_OFFSET
        resident = item + item_index * EQUIPMENT_SIZE + ITEM_RESIDENT_OFFSET
        document.state[resident + 2] = 0xA5
        document.state[resident + 0x10] = 0x5A
        values = [(3, 28, 56, False), (64, 2, 4, True)] + [
            (0, 0, 0, False)
        ] * (ITEM_RESIDENT_COUNT - 2)

        document.set_residents(slot, item_index, values)
        saved = SaveDocument.from_bytes(document.to_bytes())

        self.assertEqual(saved.resident_values(slot, item_index), values)
        self.assertEqual(saved.state[resident + 2], 0xA5)
        self.assertEqual(saved.state[resident + 0x10], 0x5A)

    def test_setters_reject_out_of_range_values(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        with self.assertRaises(ValueError):
            document.set_hl(MAX_HL + 1)
        with self.assertRaises(ValueError):
            document.set_item_points(-1)
        slot = document.unit_slots()[0]
        with self.assertRaises(ValueError):
            document.set_equipment(slot, [(0, MAX_EQUIPMENT_LEVEL + 1, 0, 0)] * 5)
        with self.assertRaises(ValueError):
            document.set_residents(slot, 0, [(0, 0, 0, False)] * 8)
        with self.assertRaises(ValueError):
            document.set_residents(
                slot,
                0,
                [(0, 0, 0, False)] * 8 + [(0x10000, 0, 0, False)],
            )
        with self.assertRaises(ValueError):
            document.set_residents(
                slot,
                0,
                [(0, 0x100000000, 0, False)]
                + [(0, 0, 0, False)] * (ITEM_RESIDENT_COUNT - 1),
            )


if __name__ == "__main__":
    unittest.main()
