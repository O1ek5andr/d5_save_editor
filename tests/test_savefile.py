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
    INNOCENCE_WAREHOUSE_COUNT,
    MAX_EQUIPMENT_LEVEL,
    MAX_HL,
    RESERVE_COUNT_OFFSET,
    ROSTER_OFFSET,
    SAVE_MAGIC,
    STATE_SIZE,
    UNIT_LEVEL_OFFSET,
    UNIT_MANA_OFFSET,
    UNIT_NAME_OFFSET,
    UNIT_SIZE,
    UNIT_USED_OFFSET,
    UNIT_SLOTS,
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

    def test_subdue_all_equipped_residents_only_changes_nonempty(
        self,
    ) -> None:
        document = SaveDocument.from_bytes(make_save())
        army_slot = document.unit_slots()[0]
        reserve_slot = UNIT_SLOTS - 1
        struct.pack_into("<h", document.state, RESERVE_COUNT_OFFSET, 1)
        struct.pack_into(
            "<I",
            document.state,
            ROSTER_OFFSET + reserve_slot * UNIT_SIZE + UNIT_USED_OFFSET,
            1,
        )

        document.set_equipment(
            army_slot, [(100, 0, 0, 0)] + [(0, 0, 0, 0)] * 4
        )
        document.set_residents(
            army_slot,
            0,
            [(3, 28, 56, False), (64, 2, 4, True)]
            + [(0, 0, 0, False)] * (ITEM_RESIDENT_COUNT - 2),
        )
        document.set_residents(
            army_slot,
            1,
            [(99, 7, 9, False)]
            + [(0, 0, 0, False)] * (ITEM_RESIDENT_COUNT - 1),
        )
        document.set_equipment(
            reserve_slot, [(200, 0, 0, 0)] + [(0, 0, 0, 0)] * 4
        )
        document.set_residents(
            reserve_slot,
            0,
            [(7, 11, 22, False)] + [(0, 0, 0, False)] * (ITEM_RESIDENT_COUNT - 1),
        )
        unmapped_byte = (
            ROSTER_OFFSET
            + reserve_slot * UNIT_SIZE
            + EQUIPMENT_OFFSET
            + ITEM_RESIDENT_OFFSET
            + 0x10
        )
        document.state[unmapped_byte] = 0x5A

        self.assertEqual(document.subdue_all_equipped_residents(), 2)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(
            saved.resident_values(army_slot, 0)[:2],
            [(3, 28, 56, True), (64, 2, 4, True)],
        )
        self.assertEqual(
            saved.resident_values(army_slot, 0)[2], (0, 0, 0, False)
        )
        self.assertEqual(
            saved.resident_values(army_slot, 1)[0], (99, 7, 9, False)
        )
        self.assertEqual(
            saved.resident_values(reserve_slot, 0)[0], (7, 11, 22, True)
        )
        self.assertEqual(saved.state[unmapped_byte], 0x5A)
        self.assertEqual(document.subdue_all_equipped_residents(), 0)

    def test_set_all_equipment_levels_for_army_and_reserve(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        army_slot = document.unit_slots()[0]
        reserve_slot = UNIT_SLOTS - 1
        struct.pack_into("<h", document.state, RESERVE_COUNT_OFFSET, 1)
        struct.pack_into(
            "<I",
            document.state,
            ROSTER_OFFSET + reserve_slot * UNIT_SIZE + UNIT_USED_OFFSET,
            1,
        )

        document.set_equipment(
            army_slot,
            [(100, 10, 1, 2), (200, 20, 3, 4)] + [(0, 0, 0, 0)] * 3,
        )
        document.set_equipment(
            reserve_slot, [(300, 30, 5, 6)] + [(0, 0, 0, 0)] * 4
        )
        empty_item = (
            ROSTER_OFFSET
            + army_slot * UNIT_SIZE
            + EQUIPMENT_OFFSET
            + 2 * EQUIPMENT_SIZE
        )
        struct.pack_into(
            "<H", document.state, empty_item + EQUIPMENT_LEVEL_COPY_OFFSET, 77
        )
        struct.pack_into(
            "<H", document.state, empty_item + EQUIPMENT_LEVEL_OFFSET, 88
        )

        target_level = MAX_EQUIPMENT_LEVEL
        self.assertEqual(document.set_all_equipment_levels(target_level), 3)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(
            saved.equipment_values(army_slot),
            [(100, target_level, 1, 2), (200, target_level, 3, 4)]
            + [(0, 88, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)],
        )
        self.assertEqual(
            saved.equipment_values(reserve_slot)[0], (300, target_level, 5, 6)
        )
        self.assertEqual(
            struct.unpack_from(
                "<H", saved.state, empty_item + EQUIPMENT_LEVEL_COPY_OFFSET
            )[0],
            77,
        )
        self.assertEqual(
            struct.unpack_from("<H", saved.state, empty_item + EQUIPMENT_LEVEL_OFFSET)[0],
            88,
        )
        self.assertEqual(document.set_all_equipment_levels(target_level), 0)

    def test_innocence_warehouse_edit_preserves_unmapped_bytes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        first_entry = 0x87A3E8
        last_entry = first_entry + (INNOCENCE_WAREHOUSE_COUNT - 1) * 0x14
        for entry, record_id, subdued in (
            (first_entry, 1, False),
            (last_entry, 428, True),
        ):
            struct.pack_into("<H", document.state, entry, record_id)
            document.state[entry + 2] = 0x12
            document.state[entry + 3] = int(subdued)
            struct.pack_into("<II", document.state, entry + 4, 61, 4)
            struct.pack_into("<II", document.state, entry + 0x0C, 8, 2210)

        document.set_innocence_warehouse_values(0, 42, 256)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(saved.innocence_warehouse_slots(), [0, 255])
        self.assertEqual(saved.innocence_warehouse_values(0), (1, 42, 256, False))
        self.assertEqual(
            saved.innocence_warehouse_values(255), (428, 61, 4, True)
        )
        self.assertEqual(saved.state[first_entry + 2], 0x12)
        self.assertEqual(saved.state[first_entry + 3], 0)
        self.assertEqual(
            struct.unpack_from("<II", saved.state, first_entry + 0x0C), (8, 2210)
        )
        with self.assertRaises(ValueError):
            saved.set_innocence_warehouse_values(1, 42, 256)
        with self.assertRaises(ValueError):
            saved.set_innocence_warehouse_values(0, 0x100000000, 256)
        with self.assertRaises(ValueError):
            saved.innocence_warehouse_values(INNOCENCE_WAREHOUSE_COUNT)

    def test_subdue_all_innocence_warehouse_preserves_other_record_bytes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        first_entry = 0x87A3E8
        second_entry = first_entry + 0x14
        empty_entry = first_entry + 2 * 0x14
        struct.pack_into("<H", document.state, first_entry, 356)
        document.state[first_entry + 2] = 0x12
        document.state[first_entry + 3] = 0
        struct.pack_into("<II", document.state, first_entry + 4, 62, 6)
        document.state[first_entry + 0x0C:first_entry + 0x14] = b"\x0A\x00\x00\x00\x04\x08\x00\x00"
        struct.pack_into("<H", document.state, second_entry, 227)
        document.state[second_entry + 3] = 1
        document.state[empty_entry + 3] = 0x7F

        self.assertEqual(document.subdue_all_innocence_warehouse(), 1)
        self.assertEqual(document.subdue_all_innocence_warehouse(), 0)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(saved.innocence_warehouse_values(0), (356, 62, 6, True))
        self.assertEqual(saved.innocence_warehouse_values(1), (227, 0, 0, True))
        self.assertEqual(saved.state[first_entry + 2], 0x12)
        self.assertEqual(
            saved.state[first_entry + 0x0C:first_entry + 0x14],
            b"\x0A\x00\x00\x00\x04\x08\x00\x00",
        )
        self.assertEqual(saved.state[empty_entry + 3], 0x7F)

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
            document.set_all_equipment_levels(-1)
        with self.assertRaises(ValueError):
            document.set_all_equipment_levels(MAX_EQUIPMENT_LEVEL + 1)
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
