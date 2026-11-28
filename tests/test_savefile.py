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
    ITEM_STORAGE_OFFSET,
    INNOCENCE_WAREHOUSE_COUNT,
    INNOCENCE_WAREHOUSE_ENTRY_SIZE,
    INNOCENCE_WAREHOUSE_OFFSET,
    INNOCENCE_WAREHOUSE_SUBDUED_OFFSET,
    INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY,
    MAX_EQUIPMENT_LEVEL,
    MAX_BASE_STAT_VALUE,
    MAX_LEVEL,
    MAX_HL,
    RESERVE_COUNT_OFFSET,
    ROSTER_OFFSET,
    SAVE_MAGIC,
    STATE_SIZE,
    UNIT_LEVEL_OFFSET,
    UNIT_BASE_STAT_OFFSETS,
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

    def test_set_unit_scales_parameters_with_level(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        slot = document.unit_slots()[0]
        base = ROSTER_OFFSET + slot * UNIT_SIZE
        first_parameter = base + UNIT_BASE_STAT_OFFSETS[0]
        current_hp = base + 0x2CC8
        struct.pack_into("<Q", document.state, first_parameter, 120)
        struct.pack_into("<Q", document.state, current_hp, 456)
        document.state[base + 0x2D60] = 0xA5

        document.set_unit(
            slot,
            20,
            document.unit_info(slot)["mana"],
            document.weapon_values(slot),
        )

        self.assertEqual(document.unit_info(slot)["level"], 20)
        self.assertEqual(
            struct.unpack_from("<Q", document.state, first_parameter)[0],
            240,
        )
        self.assertEqual(struct.unpack_from("<Q", document.state, current_hp)[0], 456)
        self.assertEqual(document.state[base + 0x2D60], 0xA5)

    def test_set_unit_base_stats_changes_only_base_growth_fields(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        slot = document.unit_slots()[0]
        base = ROSTER_OFFSET + slot * UNIT_SIZE
        current_values = (0x2CC8, 0x2CD0, 0x2CD8, 0x2CE0, 0x2CE8)
        for index, relative_offset in enumerate(current_values):
            struct.pack_into("<Q", document.state, base + relative_offset, 100 + index)
        struct.pack_into(
            "<Q", document.state, base + UNIT_BASE_STAT_OFFSETS[0], 12_000_000
        )
        document.state[base + 0x2D60] = 0xA5

        self.assertTrue(document.set_unit_base_stats(slot))
        self.assertFalse(document.set_unit_base_stats(slot))

        for index, relative_offset in enumerate(UNIT_BASE_STAT_OFFSETS):
            self.assertEqual(
                struct.unpack_from("<Q", document.state, base + relative_offset)[0],
                12_000_000 if index == 0 else MAX_BASE_STAT_VALUE,
            )
        for index, relative_offset in enumerate(current_values):
            self.assertEqual(
                struct.unpack_from("<Q", document.state, base + relative_offset)[0],
                100 + index,
            )
        self.assertEqual(document.state[base + 0x2D60], 0xA5)

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

    def test_set_all_unit_levels_scales_parameters_for_army_and_reserve(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        army_second = 1
        reserve_slot = UNIT_SLOTS - 1
        struct.pack_into("<h", document.state, ARMY_COUNT_OFFSET, 2)
        struct.pack_into("<h", document.state, RESERVE_COUNT_OFFSET, 1)
        for slot, level in ((army_second, 20), (reserve_slot, 30)):
            base = ROSTER_OFFSET + slot * UNIT_SIZE
            struct.pack_into("<I", document.state, base + UNIT_USED_OFFSET, 1)
            struct.pack_into("<H", document.state, base + UNIT_LEVEL_OFFSET, level)

        for slot, base_level, value_step in (
            (0, 10, 10),
            (army_second, 20, 10),
            (reserve_slot, 30, 30),
        ):
            base = ROSTER_OFFSET + slot * UNIT_SIZE
            for index, relative_offset in enumerate(UNIT_BASE_STAT_OFFSETS):
                struct.pack_into(
                    "<Q",
                    document.state,
                    base + relative_offset,
                    base_level * 10 + index * value_step,
                )
            document.state[base + 0x2D60] = 0xA5

        before = bytes(document.state)
        self.assertEqual(
            document.set_all_unit_levels_and_approximate_stats(20), 2
        )
        actual_offsets = [
            index
            for index, (old, new) in enumerate(zip(before, document.state))
            if old != new
        ]
        expected_offsets = set()
        for slot in (0, reserve_slot):
            base = ROSTER_OFFSET + slot * UNIT_SIZE
            expected_offsets.update(
                range(base + UNIT_LEVEL_OFFSET, base + UNIT_LEVEL_OFFSET + 2)
            )
            for relative_offset in UNIT_BASE_STAT_OFFSETS:
                expected_offsets.update(
                    range(base + relative_offset, base + relative_offset + 8)
                )
        self.assertTrue(expected_offsets.issuperset(actual_offsets))

        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(
            [saved.unit_info(slot)["level"] for slot in (0, army_second, reserve_slot)],
            [20, 20, 20],
        )
        for index, relative_offset in enumerate(UNIT_BASE_STAT_OFFSETS):
            self.assertEqual(
                struct.unpack_from(
                    "<Q", saved.state, ROSTER_OFFSET + relative_offset
                )[0],
                200 + index * 20,
            )
            self.assertEqual(
                struct.unpack_from(
                    "<Q",
                    saved.state,
                    ROSTER_OFFSET + army_second * UNIT_SIZE + relative_offset,
                )[0],
                200 + index * 10,
            )
            self.assertEqual(
                struct.unpack_from(
                    "<Q",
                    saved.state,
                    ROSTER_OFFSET + reserve_slot * UNIT_SIZE + relative_offset,
                )[0],
                200 + index * 20,
            )
        self.assertEqual(saved.state[ROSTER_OFFSET + 0x2D60], 0xA5)
        self.assertEqual(
            document.set_all_unit_levels_and_approximate_stats(20), 0
        )

    def test_set_all_unit_base_stats_covers_army_and_reserve(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        second_army_slot = 1
        reserve_slot = UNIT_SLOTS - 1
        struct.pack_into("<h", document.state, ARMY_COUNT_OFFSET, 2)
        struct.pack_into("<h", document.state, RESERVE_COUNT_OFFSET, 1)

        for slot in (second_army_slot, reserve_slot):
            base = ROSTER_OFFSET + slot * UNIT_SIZE
            struct.pack_into("<I", document.state, base + UNIT_USED_OFFSET, 1)
            for index, relative_offset in enumerate(UNIT_BASE_STAT_OFFSETS):
                struct.pack_into("<Q", document.state, base + relative_offset, index + 1)
            struct.pack_into("<Q", document.state, base + 0x2CC8, 777)

        self.assertEqual(document.set_all_unit_base_stats(), 3)
        self.assertEqual(document.set_all_unit_base_stats(), 0)
        for slot in (0, second_army_slot, reserve_slot):
            base = ROSTER_OFFSET + slot * UNIT_SIZE
            for relative_offset in UNIT_BASE_STAT_OFFSETS:
                self.assertEqual(
                    struct.unpack_from("<Q", document.state, base + relative_offset)[0],
                    MAX_BASE_STAT_VALUE,
                )
            self.assertEqual(
                struct.unpack_from("<Q", document.state, base + 0x2CC8)[0],
                0 if slot == 0 else 777,
            )

    def test_set_all_unit_levels_rejects_zero_level_without_partial_changes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        second_slot = 1
        struct.pack_into("<h", document.state, ARMY_COUNT_OFFSET, 2)
        struct.pack_into(
            "<I",
            document.state,
            ROSTER_OFFSET + second_slot * UNIT_SIZE + UNIT_USED_OFFSET,
            1,
        )
        struct.pack_into(
            "<H",
            document.state,
            ROSTER_OFFSET + second_slot * UNIT_SIZE + UNIT_LEVEL_OFFSET,
            0,
        )
        before = bytes(document.state)

        with self.assertRaisesRegex(ValueError, "current level is 0"):
            document.set_all_unit_levels_and_approximate_stats(20)

        self.assertEqual(bytes(document.state), before)

    def test_innocence_warehouse_edit_preserves_unmapped_bytes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        first_entry = INNOCENCE_WAREHOUSE_OFFSET
        last_entry = (
            first_entry
            + (INNOCENCE_WAREHOUSE_COUNT - 1) * INNOCENCE_WAREHOUSE_ENTRY_SIZE
        )
        for entry, record_id, subdued in (
            (first_entry, 1, False),
            (last_entry, 428, True),
        ):
            struct.pack_into("<H", document.state, entry, record_id)
            document.state[entry + 2] = 0x12
            document.state[entry + 3] = 0x34
            struct.pack_into("<II", document.state, entry + 4, 61, 4)
            struct.pack_into("<II", document.state, entry + 0x0C, 8, 2210)
            document.state[entry + INNOCENCE_WAREHOUSE_SUBDUED_OFFSET] = int(
                subdued
            )

        document.set_innocence_warehouse_values(0, 42, 256)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(saved.innocence_warehouse_slots(), [0, 255])
        self.assertEqual(saved.innocence_warehouse_values(0), (1, 42, 256, False))
        self.assertEqual(
            saved.innocence_warehouse_values(255), (428, 61, 4, True)
        )
        self.assertEqual(saved.state[first_entry + 2], 0x12)
        self.assertEqual(saved.state[first_entry + 3], 0x34)
        self.assertEqual(
            struct.unpack_from("<II", saved.state, first_entry + 0x0C), (8, 2210)
        )
        with self.assertRaises(ValueError):
            saved.set_innocence_warehouse_values(1, 42, 256)
        with self.assertRaises(ValueError):
            saved.set_innocence_warehouse_values(0, 0x100000000, 256)
        with self.assertRaises(ValueError):
            saved.innocence_warehouse_values(INNOCENCE_WAREHOUSE_COUNT)

    def test_subdue_all_skips_unique_innocents_and_preserves_other_bytes(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        first_entry = INNOCENCE_WAREHOUSE_OFFSET
        second_entry = first_entry + INNOCENCE_WAREHOUSE_ENTRY_SIZE
        unique_entry_min = first_entry + 2 * INNOCENCE_WAREHOUSE_ENTRY_SIZE
        unique_entry_max = first_entry + 3 * INNOCENCE_WAREHOUSE_ENTRY_SIZE
        struct.pack_into("<H", document.state, first_entry, 356)
        document.state[first_entry + 2] = 0x12
        document.state[first_entry + 3] = 0x34
        struct.pack_into("<II", document.state, first_entry + 4, 62, 6)
        document.state[
            first_entry + 0x0C : first_entry + 0x14
        ] = b"\x0A\x00\x00\x00\x04\x08\x00\x00"
        struct.pack_into("<H", document.state, second_entry, 227)
        document.state[
            second_entry + INNOCENCE_WAREHOUSE_SUBDUED_OFFSET
        ] = 1
        struct.pack_into("<H", document.state, unique_entry_min, 202)
        struct.pack_into("<I", document.state, unique_entry_min + 4, 1)
        document.state[unique_entry_min + 3] = 0x7F
        struct.pack_into("<H", document.state, unique_entry_max, 252)
        struct.pack_into("<I", document.state, unique_entry_max + 4, 1)
        document.state[unique_entry_max + 3] = 0x6F

        self.assertEqual(document.subdue_all_innocence_warehouse(), 1)
        self.assertEqual(document.subdue_all_innocence_warehouse(), 0)
        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(saved.innocence_warehouse_slots(), [0, 1, 2, 3])
        self.assertEqual(saved.innocence_warehouse_values(0), (356, 62, 6, True))
        self.assertEqual(saved.innocence_warehouse_values(1), (227, 0, 0, True))
        self.assertEqual(saved.innocence_warehouse_values(2), (202, 1, 0, False))
        self.assertEqual(saved.innocence_warehouse_values(3), (252, 1, 0, False))
        self.assertEqual(saved.state[first_entry + 2], 0x12)
        self.assertEqual(saved.state[first_entry + 3], 0x34)
        self.assertEqual(
            saved.state[first_entry + 0x0C : first_entry + 0x14],
            b"\x0A\x00\x00\x00\x04\x08\x00\x01",
        )
        self.assertEqual(saved.state[unique_entry_min + 3], 0x7F)
        self.assertEqual(saved.state[unique_entry_max + 3], 0x6F)

    def test_move_all_residents_from_stored_and_equipped_items(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        slot = document.unit_slots()[0]
        document.set_equipment(slot, [(1807, 0, 1, 1)] + [(0, 0, 0, 0)] * 4)
        equipment_base = ROSTER_OFFSET + slot * UNIT_SIZE + EQUIPMENT_OFFSET
        equipped_resident = equipment_base + ITEM_RESIDENT_OFFSET
        equipped_record = bytes.fromhex(
            "07 00 00 00 23 00 00 00 46 00 00 00 "
            "89 08 00 00 eb 00 02 00"
        )
        document.state[
            equipped_resident : equipped_resident + ITEM_RESIDENT_SIZE
        ] = equipped_record

        stored_item = ITEM_STORAGE_OFFSET
        struct.pack_into("<H", document.state, stored_item + EQUIPMENT_ID_OFFSET, 219)
        stored_resident = stored_item + ITEM_RESIDENT_OFFSET
        stored_record = bytes.fromhex(
            "01 00 00 00 10 00 00 00 20 00 00 00 "
            "f0 07 00 00 1d 01 02 00"
        )
        document.state[
            stored_resident : stored_resident + ITEM_RESIDENT_SIZE
        ] = stored_record

        existing_entry = INNOCENCE_WAREHOUSE_OFFSET
        existing_record = bytes.fromhex(
            "63 00 12 00 3e 00 00 00 06 00 00 00 "
            "0a 00 00 00 04 08 00 00"
        )
        document.state[
            existing_entry : existing_entry + INNOCENCE_WAREHOUSE_ENTRY_SIZE
        ] = existing_record
        before = bytes(document.state)

        self.assertEqual(
            document.move_all_residents_to_innocence_warehouse(), (2, 0, 0)
        )

        first_free = INNOCENCE_WAREHOUSE_OFFSET + INNOCENCE_WAREHOUSE_ENTRY_SIZE
        second_free = first_free + INNOCENCE_WAREHOUSE_ENTRY_SIZE
        self.assertEqual(
            document.state[first_free : first_free + ITEM_RESIDENT_SIZE],
            equipped_record,
        )
        self.assertEqual(
            document.state[second_free : second_free + ITEM_RESIDENT_SIZE],
            stored_record,
        )
        self.assertEqual(
            document.state[
                stored_resident : stored_resident + ITEM_RESIDENT_SIZE
            ],
            bytes(ITEM_RESIDENT_SIZE),
        )
        self.assertEqual(
            document.state[
                equipped_resident : equipped_resident + ITEM_RESIDENT_SIZE
            ],
            bytes(ITEM_RESIDENT_SIZE),
        )
        self.assertEqual(
            document.state[
                existing_entry : existing_entry + INNOCENCE_WAREHOUSE_ENTRY_SIZE
            ],
            existing_record,
        )
        self.assertEqual(document.innocence_warehouse_slots(), [0, 1, 2])

        expected_changed = set(
            range(stored_resident, stored_resident + ITEM_RESIDENT_SIZE)
        ) | set(
            range(equipped_resident, equipped_resident + ITEM_RESIDENT_SIZE)
        ) | set(range(first_free, first_free + ITEM_RESIDENT_SIZE)) | set(
            range(second_free, second_free + ITEM_RESIDENT_SIZE)
        )
        actual_changed = {
            index
            for index, (old, new) in enumerate(zip(before, document.state))
            if old != new
        }
        self.assertLessEqual(actual_changed, expected_changed)

        saved = SaveDocument.from_bytes(document.to_bytes())
        self.assertEqual(saved.innocence_warehouse_slots(), [0, 1, 2])
        self.assertEqual(
            saved.state[first_free : first_free + ITEM_RESIDENT_SIZE],
            equipped_record,
        )
        self.assertEqual(
            saved.state[second_free : second_free + ITEM_RESIDENT_SIZE],
            stored_record,
        )

    def test_move_all_residents_leaves_overflow_residents_on_items(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        total_residents = INNOCENCE_WAREHOUSE_COUNT + 1
        items_needed = (total_residents + ITEM_RESIDENT_COUNT - 1) // ITEM_RESIDENT_COUNT
        for item_index in range(items_needed):
            item_base = ITEM_STORAGE_OFFSET + item_index * EQUIPMENT_SIZE
            struct.pack_into(
                "<H", document.state, item_base + EQUIPMENT_ID_OFFSET, 219
            )
            resident_count = min(
                ITEM_RESIDENT_COUNT,
                total_residents - item_index * ITEM_RESIDENT_COUNT,
            )
            for resident_index in range(resident_count):
                resident = (
                    item_base
                    + ITEM_RESIDENT_OFFSET
                    + resident_index * ITEM_RESIDENT_SIZE
                )
                struct.pack_into(
                    "<H",
                    document.state,
                    resident + ITEM_RESIDENT_ID_OFFSET,
                    resident_index + 1,
                )

        last_resident = (
            ITEM_STORAGE_OFFSET
            + (items_needed - 1) * EQUIPMENT_SIZE
            + ITEM_RESIDENT_OFFSET
            + (total_residents - (items_needed - 1) * ITEM_RESIDENT_COUNT - 1)
            * ITEM_RESIDENT_SIZE
        )
        last_record = bytes(
            document.state[last_resident : last_resident + ITEM_RESIDENT_SIZE]
        )

        self.assertEqual(
            document.move_all_residents_to_innocence_warehouse(),
            (INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY, 2, 0),
        )
        self.assertEqual(
            document.innocence_warehouse_slots(),
            list(range(INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY)),
        )
        self.assertEqual(
            document.state[last_resident : last_resident + ITEM_RESIDENT_SIZE],
            last_record,
        )

    def test_move_all_residents_reserves_capacity_with_existing_entries(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        existing_count = INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY - 1
        for slot in range(existing_count):
            struct.pack_into(
                "<H",
                document.state,
                INNOCENCE_WAREHOUSE_OFFSET
                + slot * INNOCENCE_WAREHOUSE_ENTRY_SIZE,
                slot + 1,
            )

        item_base = ITEM_STORAGE_OFFSET
        struct.pack_into("<H", document.state, item_base + EQUIPMENT_ID_OFFSET, 219)
        first_resident = item_base + ITEM_RESIDENT_OFFSET
        second_resident = first_resident + ITEM_RESIDENT_SIZE
        struct.pack_into("<H", document.state, first_resident, 1)
        struct.pack_into("<H", document.state, second_resident, 2)
        second_record = bytes(
            document.state[second_resident : second_resident + ITEM_RESIDENT_SIZE]
        )

        self.assertEqual(
            document.move_all_residents_to_innocence_warehouse(), (1, 1, 0)
        )
        self.assertEqual(
            document.innocence_warehouse_slots(),
            list(range(INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY)),
        )
        self.assertEqual(
            document.state[second_resident : second_resident + ITEM_RESIDENT_SIZE],
            second_record,
        )
        final_slot = (
            INNOCENCE_WAREHOUSE_OFFSET
            + (INNOCENCE_WAREHOUSE_COUNT - 1) * INNOCENCE_WAREHOUSE_ENTRY_SIZE
        )
        self.assertEqual(
            document.state[final_slot : final_slot + INNOCENCE_WAREHOUSE_ENTRY_SIZE],
            bytes(INNOCENCE_WAREHOUSE_ENTRY_SIZE),
        )

    def test_move_all_residents_leaves_unique_innocents_on_items(self) -> None:
        document = SaveDocument.from_bytes(make_save())
        item_base = ITEM_STORAGE_OFFSET
        struct.pack_into("<H", document.state, item_base + EQUIPMENT_ID_OFFSET, 219)
        special_resident = item_base + ITEM_RESIDENT_OFFSET
        regular_resident = special_resident + 3 * ITEM_RESIDENT_SIZE
        special_records = [
            struct.pack("<II", resident_id, 1) + bytes(ITEM_RESIDENT_SIZE - 8)
            for resident_id in (202, 229, 252)
        ]
        regular_record = struct.pack("<II", 3, 1) + bytes(ITEM_RESIDENT_SIZE - 8)
        for index, record in enumerate(special_records):
            start = special_resident + index * ITEM_RESIDENT_SIZE
            document.state[start : start + ITEM_RESIDENT_SIZE] = record
        document.state[
            regular_resident : regular_resident + ITEM_RESIDENT_SIZE
        ] = regular_record

        self.assertEqual(
            document.move_all_residents_to_innocence_warehouse(), (1, 0, 3)
        )
        self.assertEqual(
            document.state[
                INNOCENCE_WAREHOUSE_OFFSET : INNOCENCE_WAREHOUSE_OFFSET
                + ITEM_RESIDENT_SIZE
            ],
            regular_record,
        )
        for index, record in enumerate(special_records):
            start = special_resident + index * ITEM_RESIDENT_SIZE
            self.assertEqual(
                document.state[start : start + ITEM_RESIDENT_SIZE], record
            )
        self.assertEqual(
            document.state[
                regular_resident : regular_resident + ITEM_RESIDENT_SIZE
            ],
            bytes(ITEM_RESIDENT_SIZE),
        )

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
            document.set_all_unit_levels_and_approximate_stats(0)
        with self.assertRaises(ValueError):
            document.set_all_unit_levels_and_approximate_stats(MAX_LEVEL + 1)
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
