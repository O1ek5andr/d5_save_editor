from __future__ import annotations

import os
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


HEADER_SIZE = 0x1C0
SAVE_MAGIC = b"NIS_DISGAEA5_COMPLETE_SAVEDATA_"
BODY_MAGIC = 0xE5B2688ACB279CA6
BODY_KEY = 0xE76FCBE3F6D46A37
STATE_SIZE = 0x89B8C8

HL_OFFSET = 0xA18
ITEM_POINTS_OFFSET = 0xA30

ROSTER_OFFSET = 0x23B2B8
UNIT_SIZE = 0x4750
UNIT_SLOTS = 128
ARMY_COUNT_OFFSET = 0x5A7F9C
RESERVE_COUNT_OFFSET = 0x5A7F9E
UNIT_USED_OFFSET = 0x0
UNIT_NAME_OFFSET = 0xBC8
UNIT_LEVEL_OFFSET = 0x2DFC
UNIT_MANA_OFFSET = 0x2DF8
# Base growth stats: HP, SP, ATK, DEF, INT, RES, HIT, SPD.
UNIT_BASE_STAT_OFFSETS = tuple(range(0x2D18, 0x2D58, 8))
MAX_BASE_STAT_VALUE = 10_000_000
UNIT_WEAPON_OFFSET = 0x2DA8
WEAPON_COUNT = 10
WEAPON_SIZE = 8
EQUIPMENT_OFFSET = 0x10
EQUIPMENT_SIZE = 0x258
EQUIPMENT_COUNT = 5
ITEM_STORAGE_OFFSET = 0x4865C0
ITEM_STORAGE_MAX_COUNT = (ARMY_COUNT_OFFSET - ITEM_STORAGE_OFFSET) // EQUIPMENT_SIZE
EQUIPMENT_ID_OFFSET = 0x128
EQUIPMENT_LEVEL_COPY_OFFSET = 0x12C
EQUIPMENT_LEVEL_OFFSET = 0x13E
EQUIPMENT_TYPE_OFFSET = 0x147
EQUIPMENT_RANK_OFFSET = 0x14C
ITEM_RESIDENT_OFFSET = 0x04
ITEM_RESIDENT_SIZE = 0x14
ITEM_RESIDENT_COUNT = 9
ITEM_RESIDENT_ID_OFFSET = 0x00
ITEM_RESIDENT_LEVEL_OFFSET = 0x04
ITEM_RESIDENT_GROWTH_OFFSET = 0x08
ITEM_RESIDENT_SUBDUED_OFFSET = 0x13
INNOCENCE_WAREHOUSE_OFFSET = 0x87A3EC
INNOCENCE_WAREHOUSE_COUNT = 256
INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY = INNOCENCE_WAREHOUSE_COUNT - 1
INNOCENCE_WAREHOUSE_ENTRY_SIZE = 0x14
INNOCENCE_WAREHOUSE_SUBDUED_OFFSET = ITEM_RESIDENT_SUBDUED_OFFSET
INNOCENCE_WAREHOUSE_VALUE_OFFSET = 0x04
INNOCENCE_WAREHOUSE_GROWTH_OFFSET = 0x08
UNIQUE_RESIDENT_ID_MIN = 0xCA
UNIQUE_RESIDENT_ID_MAX = 0xFC

MAX_HL = 0x7FFFFFFFFFFFFFFF
MAX_ITEM_POINTS = 0xFFFFFFFF
MAX_LEVEL = 9999
MAX_WEAPON_LEVEL = 101
MAX_EQUIPMENT_RANK = 39
MAX_EQUIPMENT_LEVEL = 9999


def _decode_header(data: bytes) -> bytes:
    return bytes(
        (((value ^ 0xF0) >> 4) | (((value ^ 0xF0) & 0x0F) << 4))
        for value in data
    )


def _encode_header(data: bytes) -> bytes:
    return bytes(
        (((value >> 4) | ((value & 0x0F) << 4)) ^ 0xF0)
        for value in data
    )


def _xor_body(data: bytes) -> bytes:
    key = struct.pack("<Q", BODY_KEY)
    whole_words = len(data) // len(key)
    masked = bytearray(data)
    for offset in range(whole_words * len(key)):
        masked[offset] ^= key[offset % len(key)]
    return bytes(masked)


def _decompress_yukes_lz(data: bytes, expected_size: int) -> bytes:
    output = bytearray()
    position = 0

    def require(count: int) -> None:
        if position + count > len(data):
            raise ValueError("truncated Yukes LZ stream")

    while len(output) < expected_size:
        require(1)
        command = data[position]
        position += 1

        if command < 0x80:
            length = command
            require(length)
            if len(output) + length > expected_size:
                raise ValueError("Yukes LZ stream exceeds its declared size")
            output.extend(data[position:position + length])
            position += length
            continue

        if command < 0xC0:
            length = ((command >> 4) & 0x03) + 1
            distance = (command & 0x0F) + 1
        elif command < 0xE0:
            length = (command & 0x3F) + 2
            require(1)
            distance = data[position] + 1
            position += 1
        else:
            require(2)
            next_one, next_two = data[position:position + 2]
            position += 2
            length = (((command & 0x1F) << 4) | (next_one >> 4)) + 3
            distance = (((next_one & 0x0F) << 8) | next_two) + 1

        if distance > len(output):
            raise ValueError("invalid Yukes LZ back-reference")
        if len(output) + length > expected_size:
            raise ValueError("Yukes LZ stream exceeds its declared size")
        for _ in range(length):
            output.append(output[-distance])

    return bytes(output)


def _decompress_ykcmp(data: bytes) -> bytes:
    if len(data) < 20 or data[:8] != b"YKCMP_V1":
        raise ValueError("missing YKCMP_V1 container")

    compression_type, total_size, raw_size = struct.unpack_from("<III", data, 8)
    if total_size < 20 or total_size > len(data):
        raise ValueError("invalid YKCMP container size")
    if raw_size != STATE_SIZE:
        raise ValueError(
            f"unexpected game-state size {raw_size:#x}; expected {STATE_SIZE:#x}"
        )

    if compression_type == 4:
        output = _decompress_yukes_lz(data[20:total_size], raw_size)
    elif compression_type == 7:
        try:
            output = zlib.decompress(data[20:total_size])
        except zlib.error as error:
            raise ValueError(f"invalid YKCMP zlib stream: {error}") from error
    else:
        raise ValueError(f"unsupported YKCMP compression type {compression_type}")

    if len(output) != raw_size:
        raise ValueError(
            f"YKCMP size mismatch: decoded {len(output)} bytes, expected {raw_size}"
        )
    return output


def _compress_ykcmp(data: bytes) -> bytes:
    compressed = zlib.compress(data, level=9)
    return (
        b"YKCMP_V1"
        + struct.pack("<III", 7, len(compressed) + 20, len(data))
        + compressed
    )


def _text(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _is_unique_innocent(resident_id: int, value: int) -> bool:
    return (
        UNIQUE_RESIDENT_ID_MIN <= resident_id <= UNIQUE_RESIDENT_ID_MAX
        and value == 1
    )


@dataclass
class SaveDocument:
    path: Path
    header: bytearray
    state: bytearray

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> SaveDocument:
        save_path = Path(path)
        return cls.from_bytes(save_path.read_bytes(), save_path)

    @classmethod
    def from_bytes(
        cls, data: bytes, path: str | os.PathLike[str] = "save.sav"
    ) -> SaveDocument:
        if len(data) < HEADER_SIZE + 8:
            raise ValueError("file is too short to be a Disgaea 5 save")

        header = bytearray(_decode_header(data[:HEADER_SIZE]))
        if not header.startswith(SAVE_MAGIC):
            raise ValueError("not a Disgaea 5 Complete save file")

        body_size = struct.unpack_from("<I", header, 0x38)[0]
        available_body_size = len(data) - HEADER_SIZE
        if body_size < 8 or body_size > available_body_size:
            raise ValueError("invalid save body size in header")

        body = data[HEADER_SIZE:HEADER_SIZE + body_size]
        if struct.unpack_from("<Q", body)[0] != BODY_MAGIC:
            raise ValueError("unknown Disgaea 5 save body")

        state = _decompress_ykcmp(_xor_body(body[8:]))
        if len(state) != STATE_SIZE:
            raise ValueError(
                f"unexpected game-state size {len(state):#x}; expected {STATE_SIZE:#x}"
            )

        return cls(Path(path), header, bytearray(state))

    @property
    def title(self) -> str:
        return _text(self.header[0x40:0xC0])

    @property
    def chapter(self) -> str:
        return _text(self.header[0xC0:0x140])

    @property
    def hl(self) -> int:
        return struct.unpack_from("<Q", self.state, HL_OFFSET)[0]

    @property
    def item_points(self) -> int:
        return struct.unpack_from("<I", self.state, ITEM_POINTS_OFFSET)[0]

    def set_hl(self, value: int) -> None:
        self._validate_range(value, 0, MAX_HL, "HL")
        struct.pack_into("<Q", self.state, HL_OFFSET, value)

    def set_item_points(self, value: int) -> None:
        self._validate_range(value, 0, MAX_ITEM_POINTS, "Item Points")
        struct.pack_into("<I", self.state, ITEM_POINTS_OFFSET, value)

    def unit_slots(self) -> list[int]:
        army_count = struct.unpack_from("<h", self.state, ARMY_COUNT_OFFSET)[0]
        reserve_count = struct.unpack_from("<h", self.state, RESERVE_COUNT_OFFSET)[0]
        if not 0 <= army_count <= UNIT_SLOTS:
            raise ValueError(f"invalid army count in save: {army_count}")
        if not 0 <= reserve_count <= UNIT_SLOTS:
            raise ValueError(f"invalid reserve count in save: {reserve_count}")
        if army_count + reserve_count > UNIT_SLOTS:
            raise ValueError("army and reserve counts exceed the roster capacity")
        return list(range(army_count)) + list(
            range(UNIT_SLOTS - reserve_count, UNIT_SLOTS)
        )

    def unit_info(self, slot: int) -> dict[str, int | str]:
        base = self._unit_base(slot)
        name = _text(self.state[base + UNIT_NAME_OFFSET:base + UNIT_NAME_OFFSET + 52])
        level = struct.unpack_from("<H", self.state, base + UNIT_LEVEL_OFFSET)[0]
        mana = struct.unpack_from("<I", self.state, base + UNIT_MANA_OFFSET)[0]
        class_id = struct.unpack_from("<I", self.state, base + 0x2E04)[0]
        return {
            "name": name or f"Unit slot {slot + 1}",
            "level": level,
            "mana": mana,
            "class_id": class_id,
        }

    def weapon_values(self, slot: int) -> list[tuple[int, int]]:
        base = self._unit_base(slot) + UNIT_WEAPON_OFFSET
        return [
            (
                self.state[base + index * WEAPON_SIZE + 4],
                self.state[base + index * WEAPON_SIZE + 6],
            )
            for index in range(WEAPON_COUNT)
        ]

    def set_unit(
        self,
        slot: int,
        level: int,
        mana: int,
        weapon_values: list[tuple[int, int]],
    ) -> None:
        self._validate_range(level, 1, MAX_LEVEL, "Level")
        self._validate_range(mana, 0, 0xFFFFFFFF, "Mana")
        if len(weapon_values) != WEAPON_COUNT:
            raise ValueError(f"exactly {WEAPON_COUNT} weapon entries are required")
        for weapon_level, aptitude in weapon_values:
            self._validate_range(
                weapon_level, 0, MAX_WEAPON_LEVEL, "Weapon level"
            )
            self._validate_range(aptitude, 0, 0xFF, "Weapon aptitude")

        base = self._unit_base(slot)
        current_level = struct.unpack_from(
            "<H", self.state, base + UNIT_LEVEL_OFFSET
        )[0]
        parameter_updates = self._scaled_base_stat_updates(
            base, current_level, level
        )
        struct.pack_into("<H", self.state, base + UNIT_LEVEL_OFFSET, level)
        struct.pack_into("<I", self.state, base + UNIT_MANA_OFFSET, mana)
        for offset, value in parameter_updates:
            struct.pack_into("<Q", self.state, offset, value)
        for index, (weapon_level, aptitude) in enumerate(weapon_values):
            weapon = base + UNIT_WEAPON_OFFSET + index * WEAPON_SIZE
            struct.pack_into("<I", self.state, weapon, _weapon_experience(weapon_level))
            self.state[weapon + 4] = weapon_level
            self.state[weapon + 6] = aptitude

    def set_all_unit_levels_and_approximate_stats(self, level: int) -> int:
        self._validate_range(level, 1, MAX_LEVEL, "Level")
        level_updates: list[tuple[int, int]] = []
        parameter_updates: list[tuple[int, int]] = []
        changed_count = 0

        for slot in self.unit_slots():
            base = self._unit_base(slot)
            level_offset = base + UNIT_LEVEL_OFFSET
            current_level = struct.unpack_from("<H", self.state, level_offset)[0]
            parameter_updates.extend(
                self._scaled_base_stat_updates(base, current_level, level)
            )

            if current_level != level:
                level_updates.append((level_offset, level))
                changed_count += 1

        for offset, value in level_updates:
            struct.pack_into("<H", self.state, offset, value)
        for offset, value in parameter_updates:
            struct.pack_into("<Q", self.state, offset, value)
        return changed_count

    def set_unit_base_stats(self, slot: int) -> bool:
        base = self._unit_base(slot)
        updates = self._base_stat_max_updates(base)
        for offset, value in updates:
            struct.pack_into("<Q", self.state, offset, value)
        return bool(updates)

    def set_all_unit_base_stats(self) -> int:
        updates: list[tuple[int, int]] = []
        changed_slots = set()
        for slot in self.unit_slots():
            base = self._unit_base(slot)
            unit_updates = self._base_stat_max_updates(base)
            if unit_updates:
                changed_slots.add(slot)
                updates.extend(unit_updates)

        for offset, value in updates:
            struct.pack_into("<Q", self.state, offset, value)
        return len(changed_slots)

    def _base_stat_max_updates(self, base: int) -> list[tuple[int, int]]:
        updates = []
        for relative_offset in UNIT_BASE_STAT_OFFSETS:
            offset = base + relative_offset
            current_value = struct.unpack_from("<Q", self.state, offset)[0]
            if current_value < MAX_BASE_STAT_VALUE:
                updates.append((offset, MAX_BASE_STAT_VALUE))
        return updates

    def _scaled_base_stat_updates(
        self, base: int, current_level: int, new_level: int
    ) -> list[tuple[int, int]]:
        if current_level == 0:
            slot = (base - ROSTER_OFFSET) // UNIT_SIZE
            raise ValueError(
                f"cannot scale parameters for unit slot {slot + 1} "
                "because its current level is 0"
            )

        updates = []
        for relative_offset in UNIT_BASE_STAT_OFFSETS:
            offset = base + relative_offset
            current_value = struct.unpack_from("<Q", self.state, offset)[0]
            scaled_value = (
                current_value * new_level + current_level // 2
            ) // current_level
            if scaled_value > 0xFFFFFFFFFFFFFFFF:
                slot = (base - ROSTER_OFFSET) // UNIT_SIZE
                raise ValueError(
                    f"scaled parameter at unit slot {slot + 1} exceeds "
                    "the save format limit"
                )
            if scaled_value != current_value:
                updates.append((offset, scaled_value))
        return updates

    def equipment_values(self, slot: int) -> list[tuple[int, int, int, int]]:
        base = self._unit_base(slot) + EQUIPMENT_OFFSET
        return [
            self._item_values(base + index * EQUIPMENT_SIZE)
            for index in range(EQUIPMENT_COUNT)
        ]

    def innocence_warehouse_slots(self) -> list[int]:
        return [
            slot
            for slot in range(INNOCENCE_WAREHOUSE_COUNT)
            if self.innocence_warehouse_values(slot)[0] != 0
        ]

    def innocence_warehouse_values(self, slot: int) -> tuple[int, int, int, bool]:
        base = self._innocence_warehouse_base(slot)
        return (
            struct.unpack_from("<H", self.state, base)[0],
            struct.unpack_from(
                "<I", self.state, base + INNOCENCE_WAREHOUSE_VALUE_OFFSET
            )[0],
            struct.unpack_from(
                "<I", self.state, base + INNOCENCE_WAREHOUSE_GROWTH_OFFSET
            )[0],
            bool(self.state[base + INNOCENCE_WAREHOUSE_SUBDUED_OFFSET]),
        )

    def set_innocence_warehouse_values(
        self, slot: int, value: int, growth: int
    ) -> None:
        base = self._innocence_warehouse_base(slot)
        if self.innocence_warehouse_values(slot)[0] == 0:
            raise ValueError(f"innocence warehouse slot {slot + 1} is empty")
        self._validate_range(value, 0, 0xFFFFFFFF, "Innocence value")
        self._validate_range(growth, 0, 0xFFFFFFFF, "Resident growth")
        struct.pack_into(
            "<I", self.state, base + INNOCENCE_WAREHOUSE_VALUE_OFFSET, value
        )
        struct.pack_into(
            "<I", self.state, base + INNOCENCE_WAREHOUSE_GROWTH_OFFSET, growth
        )

    def subdue_all_innocence_warehouse(self) -> int:
        subdued_count = 0
        for slot in self.innocence_warehouse_slots():
            record_id, value, _, _ = self.innocence_warehouse_values(slot)
            if _is_unique_innocent(record_id, value):
                continue
            base = self._innocence_warehouse_base(slot)
            flag = base + INNOCENCE_WAREHOUSE_SUBDUED_OFFSET
            if not self.state[flag]:
                self.state[flag] = 1
                subdued_count += 1
        return subdued_count

    def move_all_residents_to_innocence_warehouse(self) -> tuple[int, int, int]:
        sources: list[tuple[int, bytes]] = []
        protected_count = 0
        item_bases = [
            self._item_base(slot, item_index)
            for slot in self.unit_slots()
            for item_index, item in enumerate(self.equipment_values(slot))
            if item[0] != 0
        ]
        item_bases.extend(self._item_storage_bases())

        for item_base in item_bases:
            for index in range(ITEM_RESIDENT_COUNT):
                resident = (
                    item_base
                    + ITEM_RESIDENT_OFFSET
                    + index * ITEM_RESIDENT_SIZE
                )
                resident_id = struct.unpack_from(
                    "<H", self.state, resident + ITEM_RESIDENT_ID_OFFSET
                )[0]
                if resident_id == 0:
                    continue
                resident_value = struct.unpack_from(
                    "<I", self.state, resident + ITEM_RESIDENT_LEVEL_OFFSET
                )[0]
                if _is_unique_innocent(resident_id, resident_value):
                    protected_count += 1
                    continue
                sources.append(
                    (
                        resident,
                        bytes(self.state[resident : resident + ITEM_RESIDENT_SIZE]),
                    )
                )

        if not sources:
            return 0, 0, protected_count

        active_slots = self.innocence_warehouse_slots()
        remaining_capacity = max(
            0, INNOCENCE_WAREHOUSE_TRANSFER_CAPACITY - len(active_slots)
        )
        free_slots = [
            slot
            for slot in range(INNOCENCE_WAREHOUSE_COUNT - 1)
            if self.innocence_warehouse_values(slot)[0] == 0
        ][:remaining_capacity]
        moved_count = min(len(sources), len(free_slots))
        for (source, record), slot in zip(sources[:moved_count], free_slots):
            destination = self._innocence_warehouse_base(slot)
            self.state[
                destination : destination + INNOCENCE_WAREHOUSE_ENTRY_SIZE
            ] = record
            self.state[source : source + ITEM_RESIDENT_SIZE] = bytes(
                ITEM_RESIDENT_SIZE
            )
        return moved_count, len(sources) - moved_count, protected_count

    def set_equipment(self, slot: int, values: list[tuple[int, int, int, int]]) -> None:
        if len(values) != EQUIPMENT_COUNT:
            raise ValueError(f"exactly {EQUIPMENT_COUNT} equipment entries are required")
        for item_id, item_level, item_type, rank in values:
            self._validate_range(item_id, 0, 0xFFFF, "Item ID")
            self._validate_range(
                item_level, 0, MAX_EQUIPMENT_LEVEL, "Item level"
            )
            self._validate_range(item_type, 0, 0xFF, "Item type")
            self._validate_range(rank, 0, MAX_EQUIPMENT_RANK, "Item rank")

        base = self._unit_base(slot) + EQUIPMENT_OFFSET
        for index, (item_id, item_level, item_type, rank) in enumerate(values):
            item = base + index * EQUIPMENT_SIZE
            struct.pack_into("<H", self.state, item + EQUIPMENT_ID_OFFSET, item_id)
            struct.pack_into(
                "<H", self.state, item + EQUIPMENT_LEVEL_COPY_OFFSET, item_level
            )
            struct.pack_into("<H", self.state, item + EQUIPMENT_LEVEL_OFFSET, item_level)
            self.state[item + EQUIPMENT_TYPE_OFFSET] = item_type
            self.state[item + EQUIPMENT_RANK_OFFSET] = rank

    def set_all_equipment_levels(self, level: int) -> int:
        self._validate_range(level, 0, MAX_EQUIPMENT_LEVEL, "Item level")
        item_bases: list[int] = []
        for slot in self.unit_slots():
            for item_index, item in enumerate(self.equipment_values(slot)):
                if item[0] != 0:
                    item_bases.append(self._item_base(slot, item_index))

        updates: list[int] = []
        for item_base in item_bases:
            visible_level = struct.unpack_from(
                "<H", self.state, item_base + EQUIPMENT_LEVEL_OFFSET
            )[0]
            copied_level = struct.unpack_from(
                "<H", self.state, item_base + EQUIPMENT_LEVEL_COPY_OFFSET
            )[0]
            if visible_level != level or copied_level != level:
                updates.append(item_base)

        for item_base in updates:
            self._set_item_level(item_base, level)
        return len(updates)

    def resident_values(
        self, slot: int, item_index: int
    ) -> list[tuple[int, int, int, bool]]:
        return self._resident_values_at(self._item_base(slot, item_index))

    def _resident_values_at(self, item_base: int) -> list[tuple[int, int, int, bool]]:
        values = []
        for index in range(ITEM_RESIDENT_COUNT):
            resident = item_base + ITEM_RESIDENT_OFFSET + index * ITEM_RESIDENT_SIZE
            values.append(
                (
                    struct.unpack_from(
                        "<H", self.state, resident + ITEM_RESIDENT_ID_OFFSET
                    )[0],
                    struct.unpack_from(
                        "<I", self.state, resident + ITEM_RESIDENT_LEVEL_OFFSET
                    )[0],
                    struct.unpack_from(
                        "<I", self.state, resident + ITEM_RESIDENT_GROWTH_OFFSET
                    )[0],
                    bool(self.state[resident + ITEM_RESIDENT_SUBDUED_OFFSET]),
                )
            )
        return values

    def set_residents(
        self,
        slot: int,
        item_index: int,
        values: list[tuple[int, int, int, bool]],
    ) -> None:
        self._set_residents_at(self._item_base(slot, item_index), values)

    def _set_residents_at(
        self, item_base: int, values: list[tuple[int, int, int, bool]]
    ) -> None:
        if len(values) != ITEM_RESIDENT_COUNT:
            raise ValueError(
                f"exactly {ITEM_RESIDENT_COUNT} resident entries are required"
            )
        for resident_id, level, growth, subdued in values:
            self._validate_range(resident_id, 0, 0xFFFF, "Resident ID")
            self._validate_range(level, 0, 0xFFFFFFFF, "Resident level")
            self._validate_range(growth, 0, 0xFFFFFFFF, "Resident growth")
            if not isinstance(subdued, bool):
                raise ValueError("Resident subdued state must be true or false")

        for index, (resident_id, level, growth, subdued) in enumerate(values):
            resident = item_base + ITEM_RESIDENT_OFFSET + index * ITEM_RESIDENT_SIZE
            struct.pack_into(
                "<H", self.state, resident + ITEM_RESIDENT_ID_OFFSET, resident_id
            )
            struct.pack_into(
                "<I", self.state, resident + ITEM_RESIDENT_LEVEL_OFFSET, level
            )
            struct.pack_into(
                "<I", self.state, resident + ITEM_RESIDENT_GROWTH_OFFSET, growth
            )
            self.state[resident + ITEM_RESIDENT_SUBDUED_OFFSET] = int(subdued)

    def subdue_all_equipped_residents(self) -> int:
        item_bases: list[int] = []
        for slot in self.unit_slots():
            for item_index, item in enumerate(self.equipment_values(slot)):
                if item[0] != 0:
                    item_bases.append(self._item_base(slot, item_index))
        subdued_count = 0
        for item_base in item_bases:
            residents = self._resident_values_at(item_base)
            pending = sum(
                1
                for resident_id, _, _, subdued in residents
                if resident_id != 0 and not subdued
            )
            if pending == 0:
                continue
            self._set_residents_at(
                item_base,
                [
                    (resident_id, level, growth, subdued or resident_id != 0)
                    for resident_id, level, growth, subdued in residents
                ],
            )
            subdued_count += pending
        return subdued_count

    def _item_values(self, item_base: int) -> tuple[int, int, int, int]:
        return (
            struct.unpack_from("<H", self.state, item_base + EQUIPMENT_ID_OFFSET)[0],
            struct.unpack_from("<H", self.state, item_base + EQUIPMENT_LEVEL_OFFSET)[0],
            self.state[item_base + EQUIPMENT_TYPE_OFFSET],
            self.state[item_base + EQUIPMENT_RANK_OFFSET],
        )

    def _set_item_level(self, item_base: int, level: int) -> None:
        struct.pack_into(
            "<H", self.state, item_base + EQUIPMENT_LEVEL_COPY_OFFSET, level
        )
        struct.pack_into(
            "<H", self.state, item_base + EQUIPMENT_LEVEL_OFFSET, level
        )

    def _innocence_warehouse_base(self, slot: int) -> int:
        self._validate_range(
            slot, 0, INNOCENCE_WAREHOUSE_COUNT - 1, "Innocence warehouse slot"
        )
        return INNOCENCE_WAREHOUSE_OFFSET + slot * INNOCENCE_WAREHOUSE_ENTRY_SIZE

    def _item_storage_bases(self) -> list[int]:
        bases: list[int] = []
        for index in range(ITEM_STORAGE_MAX_COUNT):
            item_base = ITEM_STORAGE_OFFSET + index * EQUIPMENT_SIZE
            if self._item_values(item_base)[0] == 0:
                return bases
            bases.append(item_base)
        raise ValueError("could not find the end of the saved item list")

    def _item_base(self, slot: int, item_index: int) -> int:
        self._validate_range(item_index, 0, EQUIPMENT_COUNT - 1, "Equipment slot")
        return (
            self._unit_base(slot)
            + EQUIPMENT_OFFSET
            + item_index * EQUIPMENT_SIZE
        )

    def to_bytes(self) -> bytes:
        body = struct.pack("<Q", BODY_MAGIC) + _xor_body(_compress_ykcmp(bytes(self.state)))
        header = bytearray(self.header)
        struct.pack_into("<I", header, 0x38, len(body))
        return _encode_header(bytes(header)) + body

    def write_new_file(self, path: str | os.PathLike[str]) -> Path:
        output_path = Path(path)
        if os.path.normcase(os.path.abspath(output_path)) == os.path.normcase(
            os.path.abspath(self.path)
        ):
            raise ValueError("choose a new output file; the source save is never overwritten")

        data = self.to_bytes()
        descriptor = os.open(
            output_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            try:
                output_path.unlink()
            except OSError:
                pass
            raise
        return output_path

    def suggested_output_name(self) -> str:
        match = re.fullmatch(r"Save_(\d{3})", self.path.stem, flags=re.IGNORECASE)
        next_slot = int(match.group(1)) + 1 if match else 1
        for slot in range(next_slot, 1000):
            candidate = f"Save_{slot:03}.sav"
            candidate_path = self.path.with_name(candidate)
            if (
                candidate_path.exists()
                or os.path.normcase(os.path.abspath(candidate_path))
                == os.path.normcase(os.path.abspath(self.path))
            ):
                continue
            return candidate
        return f"{self.path.stem}_edited.sav"

    def _unit_base(self, slot: int) -> int:
        if slot not in self.unit_slots():
            raise ValueError(f"unit slot {slot} is not in the army or reserve")
        base = ROSTER_OFFSET + slot * UNIT_SIZE
        if struct.unpack_from("<I", self.state, base + UNIT_USED_OFFSET)[0] == 0:
            raise ValueError(f"unit slot {slot} is empty")
        return base

    @staticmethod
    def _validate_range(value: int, minimum: int, maximum: int, label: str) -> None:
        if not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")


def _weapon_experience(level: int) -> int:
    return 300 * (level * (level + 1) // 2 + 4 * level)
