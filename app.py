from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .savefile import (
    EQUIPMENT_COUNT,
    ITEM_RESIDENT_COUNT,
    INNOCENCE_WAREHOUSE_COUNT,
    MAX_EQUIPMENT_LEVEL,
    MAX_LEVEL,
    WEAPON_COUNT,
    SaveDocument,
)


class SaveEditor:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Disgaea 5 Complete Save Editor")
        self.root.minsize(860, 620)

        self.document: SaveDocument | None = None
        self.unit_slots: list[int] = []
        self.selected_slot: int | None = None

        self.path_text = tk.StringVar(value="Open a Save_###.sav or AutoSave.sav file")
        self.header_text = tk.StringVar(value="")
        self.hl_value = tk.StringVar()
        self.item_points_value = tk.StringVar()
        self.unit_level_value = tk.StringVar()
        self.unit_mana_value = tk.StringVar()
        self.class_value = tk.StringVar()
        self.status_text = tk.StringVar(value="No save loaded")

        self.weapon_vars: list[tuple[tk.StringVar, tk.StringVar]] = []
        self.equipment_vars: list[
            tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar]
        ] = []

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Button(top, text="Open save...", command=self.open_save).pack(side="left")
        ttk.Button(top, text="Save as new slot...", command=self.save_copy).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(
            top,
            text="Subdue equipped residents...",
            command=self.subdue_all_equipped_residents,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            top,
            text="Set all equipped levels...",
            command=self.set_all_equipment_levels,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            top,
            text="Set all character levels...",
            command=self.set_all_character_levels,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            top,
            text="Innocence Warehouse...",
            command=self.open_innocence_warehouse,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(top, textvariable=self.status_text).pack(side="right")

        ttk.Label(self.root, textvariable=self.path_text, padding=(12, 0)).pack(
            anchor="w"
        )
        ttk.Label(
            self.root,
            textvariable=self.header_text,
            padding=(12, 4, 12, 8),
        ).pack(anchor="w")

        resources = ttk.LabelFrame(self.root, text="Resources", padding=8)
        resources.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(resources, text="HL").grid(row=0, column=0, sticky="w")
        ttk.Entry(resources, textvariable=self.hl_value, width=22).grid(
            row=0, column=1, padx=(6, 14)
        )
        ttk.Label(resources, text="Item Points").grid(row=0, column=2, sticky="w")
        ttk.Entry(resources, textvariable=self.item_points_value, width=14).grid(
            row=0, column=3, padx=6
        )
        ttk.Button(resources, text="Apply", command=self.apply_resources).grid(
            row=0, column=4, padx=(8, 0)
        )

        body = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        roster = ttk.LabelFrame(body, text="Army and reserve", padding=6)
        roster.grid(row=0, column=0, sticky="nsw")
        roster.rowconfigure(0, weight=1)
        self.unit_list = tk.Listbox(roster, width=30, height=22, exportselection=False)
        self.unit_list.grid(row=0, column=0, sticky="ns")
        scrollbar = ttk.Scrollbar(roster, orient="vertical", command=self.unit_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.unit_list.configure(yscrollcommand=scrollbar.set)
        self.unit_list.bind("<<ListboxSelect>>", self.on_unit_selected)

        editor = ttk.Frame(body)
        editor.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        editor.columnconfigure(0, weight=1)

        character = ttk.LabelFrame(editor, text="Character", padding=8)
        character.grid(row=0, column=0, sticky="ew")
        ttk.Label(character, text="Level").grid(row=0, column=0, sticky="w")
        ttk.Entry(character, textvariable=self.unit_level_value, width=10).grid(
            row=0, column=1, padx=(6, 14)
        )
        ttk.Label(character, text="Mana").grid(row=0, column=2, sticky="w")
        ttk.Entry(character, textvariable=self.unit_mana_value, width=16).grid(
            row=0, column=3, padx=(6, 14)
        )
        ttk.Label(character, text="Class ID").grid(row=0, column=4, sticky="w")
        ttk.Label(character, textvariable=self.class_value).grid(
            row=0, column=5, padx=6, sticky="w"
        )

        weapons = ttk.LabelFrame(editor, text="Weapon mastery", padding=8)
        weapons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(weapons, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Label(weapons, text="Level (0–101)").grid(row=0, column=1, sticky="w")
        ttk.Label(weapons, text="Aptitude (0–255)").grid(row=0, column=2, sticky="w")
        for index in range(WEAPON_COUNT):
            level = tk.StringVar()
            aptitude = tk.StringVar()
            self.weapon_vars.append((level, aptitude))
            ttk.Label(weapons, text=f"Weapon {index + 1}").grid(
                row=index + 1, column=0, sticky="w", pady=1
            )
            ttk.Entry(weapons, textvariable=level, width=12).grid(
                row=index + 1, column=1, sticky="w", pady=1
            )
            ttk.Entry(weapons, textvariable=aptitude, width=12).grid(
                row=index + 1, column=2, sticky="w", pady=1
            )

        equipment = ttk.LabelFrame(editor, text="Equipped items", padding=8)
        equipment.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(equipment, text="Slot").grid(row=0, column=0, sticky="w")
        ttk.Label(equipment, text="Internal item ID").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(equipment, text="Level (0–9999)").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(equipment, text="Type").grid(row=0, column=3, sticky="w")
        ttk.Label(equipment, text="Rank (0–39)").grid(row=0, column=4, sticky="w")
        for index in range(EQUIPMENT_COUNT):
            item_id = tk.StringVar()
            item_level = tk.StringVar()
            item_type = tk.StringVar()
            rank = tk.StringVar()
            self.equipment_vars.append((item_id, item_level, item_type, rank))
            ttk.Label(equipment, text=f"Item {index + 1}").grid(
                row=index + 1, column=0, sticky="w", pady=1
            )
            ttk.Entry(equipment, textvariable=item_id, width=12).grid(
                row=index + 1, column=1, sticky="w", pady=1
            )
            ttk.Entry(equipment, textvariable=item_level, width=12).grid(
                row=index + 1, column=2, sticky="w", pady=1
            )
            ttk.Entry(
                equipment, textvariable=item_type, width=10, state="readonly"
            ).grid(row=index + 1, column=3, sticky="w", pady=1)
            ttk.Entry(equipment, textvariable=rank, width=12).grid(
                row=index + 1, column=4, sticky="w", pady=1
            )
            ttk.Button(
                equipment,
                text="Residents...",
                command=lambda item_index=index: self.edit_residents(item_index),
            ).grid(row=index + 1, column=5, padx=(8, 0), pady=1)

        ttk.Label(
            editor,
            text=(
                "Equipment IDs are raw game IDs; changing an ID does not copy item "
                "properties. Innocence Warehouse... edits the separate stored residents."
            ),
            wraplength=560,
            foreground="#8a4b08",
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        ttk.Label(
            self.root,
            text="The editor only writes a new file. Close the game before loading the edited slot.",
            padding=(12, 0, 12, 10),
        ).pack(anchor="w")

    def open_save(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open Disgaea 5 Complete save",
            filetypes=[("Disgaea 5 saves", "*.sav"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            document = SaveDocument.load(filename)
            slots = document.unit_slots()
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not open save", str(error))
            return

        self.document = document
        self.unit_slots = slots
        self.selected_slot = None
        self.path_text.set(str(document.path))
        self.header_text.set(f"{document.title}  |  {document.chapter}")
        self.hl_value.set(str(document.hl))
        self.item_points_value.set(str(document.item_points))
        self.status_text.set("Loaded")

        self.unit_list.delete(0, tk.END)
        for slot in slots:
            info = document.unit_info(slot)
            label = f"{slot + 1:03}  {info['name']}  Lv {info['level']}"
            self.unit_list.insert(tk.END, label)
        if slots:
            self.unit_list.selection_set(0)
            self.unit_list.activate(0)
            self._show_unit(slots[0])

    def on_unit_selected(self, _event: tk.Event) -> None:
        if self.document is None:
            return
        selection = self.unit_list.curselection()
        if not selection:
            return
        new_slot = self.unit_slots[selection[0]]
        if self.selected_slot is not None and new_slot != self.selected_slot:
            try:
                self._apply_current_unit()
            except ValueError as error:
                messagebox.showerror("Invalid character values", str(error))
                old_index = self.unit_slots.index(self.selected_slot)
                self.unit_list.selection_clear(0, tk.END)
                self.unit_list.selection_set(old_index)
                self.unit_list.activate(old_index)
                return
        self._show_unit(new_slot)

    def _show_unit(self, slot: int) -> None:
        assert self.document is not None
        info = self.document.unit_info(slot)
        self.selected_slot = slot
        self.unit_level_value.set(str(info["level"]))
        self.unit_mana_value.set(str(info["mana"]))
        self.class_value.set(str(info["class_id"]))
        for variables, values in zip(
            self.weapon_vars, self.document.weapon_values(slot)
        ):
            variables[0].set(str(values[0]))
            variables[1].set(str(values[1]))
        for variables, values in zip(
            self.equipment_vars, self.document.equipment_values(slot)
        ):
            variables[0].set(str(values[0]))
            variables[1].set(str(values[1]))
            variables[2].set(str(values[2]))
            variables[3].set(str(values[3]))

    def _refresh_unit_list(self) -> None:
        if self.document is None:
            return
        selected_indices = self.unit_list.curselection()
        self.unit_list.delete(0, tk.END)
        for slot in self.unit_slots:
            info = self.document.unit_info(slot)
            self.unit_list.insert(
                tk.END,
                f"{slot + 1:03}  {info['name']}  Lv {info['level']}",
            )
        for selected_index in selected_indices:
            self.unit_list.selection_set(selected_index)

    def apply_resources(self) -> None:
        if self.document is None:
            return
        try:
            hl = self._integer(self.hl_value.get(), "HL")
            item_points = self._integer(
                self.item_points_value.get(), "Item Points"
            )
            self.document.set_hl(hl)
            self.document.set_item_points(item_points)
        except ValueError as error:
            messagebox.showerror("Invalid resource values", str(error))
            return
        self.status_text.set("Changes applied")

    def edit_residents(self, item_index: int) -> None:
        if self.document is None or self.selected_slot is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return

        document = self.document
        selected_slot = self.selected_slot
        item_id = document.equipment_values(selected_slot)[item_index][0]
        unit_name = document.unit_info(selected_slot)["name"]
        self._edit_resident_values(
            self.root,
            f"Residents - {unit_name} - Item {item_index + 1}",
            f"Item ID {item_id} - edit the nine resident slots",
            document.resident_values(selected_slot, item_index),
            lambda values: document.set_residents(
                selected_slot, item_index, values
            ),
        )

    def _edit_resident_values(
        self,
        parent: tk.Misc,
        title: str,
        item_description: str,
        values: list[tuple[int, int, int, bool]],
        apply_values: Callable[[list[tuple[int, int, int, bool]]], None],
    ) -> None:
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text=item_description,
            padding=(10, 10, 10, 6),
        ).grid(row=0, column=0, columnspan=5, sticky="w")
        headers = (
            "Slot",
            "Resident ID",
            "Unsubdued level",
            "Max growth",
            "Subdued",
        )
        for column, header in enumerate(headers):
            ttk.Label(dialog, text=header).grid(
                row=1, column=column, padx=6, pady=(0, 4), sticky="w"
            )

        resident_vars: list[
            tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.BooleanVar]
        ] = []
        for index, resident_values in enumerate(values):
            resident_id = tk.StringVar(value=str(resident_values[0]))
            level = tk.StringVar(value=str(resident_values[1]))
            growth = tk.StringVar(value=str(resident_values[2]))
            subdued = tk.BooleanVar(value=resident_values[3])
            resident_vars.append((resident_id, level, growth, subdued))
            ttk.Label(dialog, text=str(index + 1)).grid(
                row=index + 2, column=0, padx=6, pady=2, sticky="w"
            )
            ttk.Entry(dialog, textvariable=resident_id, width=12).grid(
                row=index + 2, column=1, padx=6, pady=2
            )
            ttk.Entry(dialog, textvariable=level, width=14).grid(
                row=index + 2, column=2, padx=6, pady=2
            )
            ttk.Entry(dialog, textvariable=growth, width=14).grid(
                row=index + 2, column=3, padx=6, pady=2
            )
            ttk.Checkbutton(dialog, variable=subdued).grid(
                row=index + 2, column=4, padx=6, pady=2
            )

        ttk.Label(
            dialog,
            text="IDs are raw game values; 0 means empty. Other resident data is preserved.",
            padding=(10, 6, 10, 4),
        ).grid(row=ITEM_RESIDENT_COUNT + 2, column=0, columnspan=5, sticky="w")

        buttons = ttk.Frame(dialog, padding=(10, 4, 10, 10))
        buttons.grid(
            row=ITEM_RESIDENT_COUNT + 3, column=0, columnspan=5, sticky="e"
        )

        def apply_residents() -> None:
            try:
                values = [
                    (
                        self._integer(resident_id.get(), "Resident ID"),
                        self._integer(level.get(), "Unsubdued level"),
                        self._integer(growth.get(), "Maximum growth"),
                        subdued.get(),
                    )
                    for resident_id, level, growth, subdued in resident_vars
                ]
                apply_values(values)
            except ValueError as error:
                messagebox.showerror("Invalid resident values", str(error), parent=dialog)
                return
            self.status_text.set("Resident changes applied")
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="right"
        )
        ttk.Button(buttons, text="Apply", command=apply_residents).pack(
            side="right", padx=(0, 8)
        )
        dialog.wait_window()

    def open_innocence_warehouse(self) -> None:
        if self.document is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return

        try:
            self._apply_current_unit()
        except ValueError as error:
            messagebox.showerror("Invalid character values", str(error))
            return

        document = self.document
        innocence_slots = document.innocence_warehouse_slots()
        window = tk.Toplevel(self.root)
        window.title(
            f"Innocence Warehouse - {len(innocence_slots)} / "
            f"{INNOCENCE_WAREHOUSE_COUNT} entries"
        )
        window.transient(self.root)
        window.minsize(820, 460)
        window.grab_set()

        search_value = tk.StringVar()
        entry_summary = tk.StringVar(value="Select an innocence")
        value_value = tk.StringVar()
        growth_value = tk.StringVar()
        visible_slots: list[int] = []
        selected_slot: int | None = None

        ttk.Label(window, text="Search by slot or record ID").pack(
            anchor="w", padx=10, pady=(10, 2)
        )
        ttk.Entry(window, textvariable=search_value).pack(fill="x", padx=10)

        content = ttk.Frame(window, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        entry_list = tk.Listbox(content, width=58, height=22, exportselection=False)
        entry_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            content, orient="vertical", command=entry_list.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        entry_list.configure(yscrollcommand=scrollbar.set)

        details = ttk.LabelFrame(content, text="Stored innocence", padding=10)
        details.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        ttk.Label(details, textvariable=entry_summary, wraplength=250).pack(
            anchor="w", pady=(0, 12)
        )
        ttk.Label(details, text="Value").pack(anchor="w")
        ttk.Entry(details, textvariable=value_value, width=16).pack(
            anchor="w", pady=(2, 8)
        )
        ttk.Label(details, text="Growth").pack(anchor="w")
        ttk.Entry(details, textvariable=growth_value, width=16).pack(
            anchor="w", pady=(2, 10)
        )

        def refresh_list(*_args: str) -> None:
            nonlocal innocence_slots, selected_slot
            innocence_slots = document.innocence_warehouse_slots()
            window.title(
                f"Innocence Warehouse - {len(innocence_slots)} / "
                f"{INNOCENCE_WAREHOUSE_COUNT} entries"
            )
            previous_slot = selected_slot
            query = search_value.get().strip().casefold()
            entry_list.delete(0, tk.END)
            visible_slots.clear()

            for slot in innocence_slots:
                record_id, value, growth, subdued = (
                    document.innocence_warehouse_values(slot)
                )
                row = (
                    f"{slot + 1:03d} | Record {record_id:5d} | "
                    f"Value {value:10d} | Growth {growth:10d} | "
                    f"{'Subdued' if subdued else 'Unsubdued'}"
                )
                if query and query not in row.casefold():
                    continue
                visible_slots.append(slot)
                entry_list.insert(tk.END, row)

            if previous_slot is not None and previous_slot in visible_slots:
                row_index = visible_slots.index(previous_slot)
                entry_list.selection_set(row_index)
                entry_list.activate(row_index)
                show_selected()
            else:
                selected_slot = None
                entry_summary.set("Select an innocence")
                value_value.set("")
                growth_value.set("")

        def show_selected(_event: tk.Event | None = None) -> None:
            nonlocal selected_slot
            selection = entry_list.curselection()
            if not selection:
                return
            selected_slot = visible_slots[selection[0]]
            record_id, value, growth, _subdued = document.innocence_warehouse_values(
                selected_slot
            )
            entry_summary.set(
                f"Warehouse slot {selected_slot + 1}\nRecord ID {record_id}"
            )
            value_value.set(str(value))
            growth_value.set(str(growth))

        def apply_entry() -> None:
            if selected_slot is None:
                messagebox.showinfo(
                    "No innocence selected",
                    "Select an innocence warehouse entry first.",
                    parent=window,
                )
                return
            try:
                document.set_innocence_warehouse_values(
                    selected_slot,
                    self._integer(value_value.get(), "Innocence value"),
                    self._integer(growth_value.get(), "Resident growth"),
                )
            except ValueError as error:
                messagebox.showerror(
                    "Invalid innocence warehouse entry", str(error), parent=window
                )
                return
            self.status_text.set("Innocence warehouse entry applied")
            refresh_list()

        def subdue_all() -> None:
            if not innocence_slots:
                messagebox.showinfo(
                    "No innocences found",
                    "There are no active Innocence Warehouse entries.",
                    parent=window,
                )
                return
            if not messagebox.askyesno(
                "Subdue all Innocence Warehouse entries",
                f"Mark eligible entries as subdued? Unique Innocents "
                "(IDs 202-252 with value 1) are left unchanged.",
                parent=window,
            ):
                return
            subdued_count = document.subdue_all_innocence_warehouse()
            self.status_text.set(
                f"Eligible Innocence Warehouse entries subdued: {subdued_count}"
            )
            refresh_list()

        def move_all_residents() -> None:
            if not messagebox.askyesno(
                "Move all item residents",
                "Move every non-empty resident from equipped items and "
                "unequipped items in the saved item list into free Innocence "
                "Warehouse slots? Equipped residents are moved first. Hostage "
                "Negotiators and other Unique Innocents (IDs 202-252 with "
                "value 1) "
                "remain on their items, and any "
                "eligible residents that do not fit also remain there. One "
                "warehouse slot stays empty until full-capacity behavior is "
                "confirmed safe in-game. The "
                "save file will not be overwritten.",
                parent=window,
            ):
                return
            try:
                self._apply_current_unit()
                moved_count, remaining_count, protected_count = (
                    document.move_all_residents_to_innocence_warehouse()
                )
            except ValueError as error:
                messagebox.showerror(
                    "Could not move residents", str(error), parent=window
                )
                return
            if moved_count == 0 and remaining_count == 0 and protected_count == 0:
                messagebox.showinfo(
                    "No residents to move",
                    "No non-empty residents were found on saved items.",
                    parent=window,
                )
                return
            self.status_text.set(
                f"Residents moved: {moved_count}; remaining on items: "
                f"{remaining_count}; protected special residents left on items: "
                f"{protected_count}"
            )
            if remaining_count:
                messagebox.showwarning(
                    "Innocence Warehouse transfer limit reached",
                    f"Moved {moved_count} residents. "
                    f"{remaining_count} remain on their items because there "
                    "were not enough transfer slots; one warehouse slot is "
                    f"reserved. {protected_count} Unique Innocents were left "
                    "on their items.",
                    parent=window,
                )
            elif protected_count:
                messagebox.showinfo(
                    "Special residents left on items",
                    f"{protected_count} Unique Innocents were not moved.",
                    parent=window,
                )
            refresh_list()

        entry_list.bind("<<ListboxSelect>>", show_selected)
        search_value.trace_add("write", refresh_list)
        ttk.Button(details, text="Apply values", command=apply_entry).pack(
            fill="x", pady=(0, 6)
        )
        ttk.Button(
            details, text="Move all residents...", command=move_all_residents
        ).pack(fill="x", pady=(0, 6))
        ttk.Button(details, text="Subdue all...", command=subdue_all).pack(fill="x")
        ttk.Label(
            window,
            text=(
                "Only value/growth fields are editable; other bytes are preserved. "
                "Subdued status uses the item-resident flag; maximize power is "
                "unavailable until "
                "type-specific caps are mapped."
            ),
            padding=(10, 0, 10, 10),
        ).pack(anchor="w")
        refresh_list()

    def subdue_all_equipped_residents(self) -> None:
        if self.document is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return
        if not messagebox.askyesno(
            "Subdue all residents",
            "Mark every non-empty resident on equipped items as subdued? "
            "This includes all army and reserve characters.",
            parent=self.root,
        ):
            return

        try:
            self._apply_current_unit()
            subdued_count = self.document.subdue_all_equipped_residents()
        except ValueError as error:
            messagebox.showerror(
                "Could not subdue residents", str(error), parent=self.root
            )
            return

        self.status_text.set(
            f"Equipped-item residents subdued: {subdued_count}"
        )

    def set_all_equipment_levels(self) -> None:
        if self.document is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return

        level = simpledialog.askinteger(
            "Set all equipped item levels",
            f"New level (0-{MAX_EQUIPMENT_LEVEL}):",
            minvalue=0,
            maxvalue=MAX_EQUIPMENT_LEVEL,
            parent=self.root,
        )
        if level is None:
            return
        if not messagebox.askyesno(
            "Confirm item level change",
            f"Set every equipped item to level {level}? This includes all "
            "army and reserve characters.",
            parent=self.root,
        ):
            return

        try:
            self._apply_current_unit()
            updated_count = self.document.set_all_equipment_levels(level)
        except ValueError as error:
            messagebox.showerror(
                "Could not set item levels", str(error), parent=self.root
            )
            return

        self.status_text.set(f"Equipped item levels updated: {updated_count}")
        if self.selected_slot is not None:
            self._show_unit(self.selected_slot)

    def set_all_character_levels(self) -> None:
        if self.document is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return

        level = simpledialog.askinteger(
            "Set all character levels",
            f"New level (1-{MAX_LEVEL}):",
            minvalue=1,
            maxvalue=MAX_LEVEL,
            parent=self.root,
        )
        if level is None:
            return
        if not messagebox.askyesno(
            "Confirm character level change",
            f"Set every army and reserve character to level {level}?",
            parent=self.root,
        ):
            return

        try:
            self._apply_current_unit()
            updated_count = self.document.set_all_unit_levels(level)
        except ValueError as error:
            messagebox.showerror(
                "Could not set character levels", str(error), parent=self.root
            )
            return

        self._refresh_unit_list()
        if self.selected_slot is not None:
            self._show_unit(self.selected_slot)
        self.status_text.set(f"Character levels updated: {updated_count}")

    def _apply_current_unit(self) -> None:
        if self.document is None or self.selected_slot is None:
            return
        level = self._integer(self.unit_level_value.get(), "Level")
        mana = self._integer(self.unit_mana_value.get(), "Mana")
        weapons = [
            (
                self._integer(level_var.get(), "Weapon level"),
                self._integer(aptitude_var.get(), "Weapon aptitude"),
            )
            for level_var, aptitude_var in self.weapon_vars
        ]
        equipment = [
            (
                self._integer(item_id.get(), "Item ID"),
                self._integer(item_level.get(), "Item level"),
                self._integer(item_type.get(), "Item type"),
                self._integer(rank.get(), "Item rank"),
            )
            for item_id, item_level, item_type, rank in self.equipment_vars
        ]
        self.document.set_unit(self.selected_slot, level, mana, weapons)
        self.document.set_equipment(self.selected_slot, equipment)
        info = self.document.unit_info(self.selected_slot)
        selected_indices = self.unit_list.curselection()
        list_index = self.unit_slots.index(self.selected_slot)
        if list_index < self.unit_list.size():
            self.unit_list.delete(list_index)
            self.unit_list.insert(
                list_index,
                f"{self.selected_slot + 1:03}  {info['name']}  Lv {info['level']}",
            )
            for selected_index in selected_indices:
                self.unit_list.selection_set(selected_index)
        self.status_text.set("Changes applied")

    def save_copy(self) -> None:
        if self.document is None:
            messagebox.showinfo("No save loaded", "Open a save file first.")
            return
        try:
            hl = self._integer(self.hl_value.get(), "HL")
            item_points = self._integer(
                self.item_points_value.get(), "Item Points"
            )
            self.document.set_hl(hl)
            self.document.set_item_points(item_points)
            self._apply_current_unit()
        except ValueError as error:
            messagebox.showerror("Invalid values", str(error))
            return

        output = filedialog.asksaveasfilename(
            title="Save edited copy as a new slot",
            initialdir=str(self.document.path.parent),
            initialfile=self.document.suggested_output_name(),
            defaultextension=".sav",
            filetypes=[("Disgaea 5 saves", "*.sav"), ("All files", "*.*")],
        )
        if not output:
            return
        try:
            saved_path = self.document.write_new_file(output)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not save edited copy", str(error))
            return
        self.status_text.set(f"Saved new file: {saved_path.name}")
        messagebox.showinfo(
            "Save copy created",
            f"Edited save written to:\n{saved_path}\n\n"
            "The original save was not changed.",
        )

    @staticmethod
    def _integer(value: str, label: str) -> int:
        try:
            return int(value.strip())
        except ValueError as error:
            raise ValueError(f"{label} must be a whole number") from error


def main() -> None:
    root = tk.Tk()
    SaveEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
