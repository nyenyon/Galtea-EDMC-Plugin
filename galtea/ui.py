"""Tk user interface: main-window panel, details window and preferences."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

import myNotebook as nb

from .model import Target, format_number, format_timestamp, now_iso
from .store import HaulStore

PANEL_ROWS = 3


def _short(text: str, limit: int = 34) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _scroll_area(parent: tk.Misc, height: int) -> tuple[tk.Frame, ttk.Frame, Any]:
    """A vertically scrollable container.

    Returns (container, inner frame, wheel callback).
    """
    container = ttk.Frame(parent)
    canvas = tk.Canvas(container, height=height, highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    background = ttk.Style().lookup("TFrame", "background")
    if background:
        canvas.configure(background=background)

    inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))

    def wheel(event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")
        elif getattr(event, "delta", 0):
            canvas.yview_scroll(int(-event.delta / 120), "units")

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind(sequence, wheel)
        inner.bind(sequence, wheel)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return container, inner, wheel


def _bind_wheel(widget: tk.Misc, wheel: Any) -> None:
    """Route mouse-wheel events from every row widget to its scroll area."""
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(sequence, wheel)
    for child in widget.winfo_children():
        _bind_wheel(child, wheel)
def _clear(frame: tk.Misc) -> None:
    for child in frame.winfo_children():
        child.destroy()


class PluginUI:
    """Owns every widget the plugin adds to EDMC."""

    def __init__(self, parent: tk.Misc, tracker: Any, store: HaulStore):
        self.parent = parent
        self.tracker = tracker
        self.store = store

        self.panel: Optional[ttk.Frame] = None
        self.panel_rows: Optional[ttk.Frame] = None
        self.panel_more: Optional[ttk.Label] = None
        self.panel_total: Optional[ttk.Label] = None

        self.details: Optional[tk.Toplevel] = None
        self.details_total: Optional[ttk.Label] = None
        self.target_rows: Optional[ttk.Frame] = None
        self.history_rows: Optional[ttk.Frame] = None
        self.target_wheel: Any = None
        self.history_wheel: Any = None

    # -- helpers ---------------------------------------------------------

    @property
    def cmdr_key(self) -> str:
        return str(getattr(self.tracker, "cmdr_key", "") or "")

    def _targets(self) -> List[Target]:
        if not self.cmdr_key:
            return []
        return self.store.targets(self.cmdr_key)

    def _history(self) -> List[Dict[str, Any]]:
        if not self.cmdr_key:
            return []
        return self.store.history(self.cmdr_key)

    # -- main window panel ----------------------------------------------

    def build_panel(self, parent: tk.Misc) -> ttk.Frame:
        self.parent = parent
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Galtea Haul Tracker").grid(row=0, column=0, sticky="w")

        self.panel_rows = ttk.Frame(frame)
        self.panel_rows.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.panel_more = ttk.Label(frame, text="")
        self.panel_more.grid(row=2, column=0, sticky="w")

        self.panel_total = ttk.Label(frame, text="Total: 0 t")
        self.panel_total.grid(row=3, column=0, sticky="w", pady=(4, 0))

        ttk.Button(frame, text="Details", command=self.open_details).grid(
            row=4, column=0, sticky="ew", pady=(4, 0)
        )

        self.panel = frame
        self.refresh()
        return frame

    def refresh(self) -> None:
        self._refresh_panel()
        self._refresh_details()

    def _refresh_panel(self) -> None:
        if self.panel_rows is None or self.panel_total is None or self.panel_more is None:
            return

        _clear(self.panel_rows)
        targets = self._targets()
        if not targets:
            ttk.Label(self.panel_rows, text="No deliveries yet").pack(anchor="w")
            self.panel_more.configure(text="")
            self.panel_total.configure(text="Total: 0 t")
            return

        for target in targets[:PANEL_ROWS]:
            row = ttk.Frame(self.panel_rows)
            row.pack(fill="x")
            ttk.Label(row, text=_short(target.label, 20), anchor="w").pack(
                side="left", fill="x", expand=True
            )
            ttk.Label(row, text=f"{format_number(target.tons)} t", anchor="e").pack(side="right")

        hidden = len(targets) - PANEL_ROWS
        self.panel_more.configure(text=f"+{hidden} more" if hidden > 0 else "")
        self.panel_total.configure(
            text=f"Total: {format_number(sum(target.tons for target in targets))} t"
        )

    # -- details window --------------------------------------------------

    def open_details(self) -> None:
        if self.details is not None and self.details.winfo_exists():
            self.details.deiconify()
            self.details.lift()
            return

        window = tk.Toplevel(self.parent)
        window.title("Galtea Haul Tracker")
        window.geometry("640x600")
        window.minsize(520, 440)
        window.protocol("WM_DELETE_WINDOW", self.close_details)
        self.details = window

        outer = ttk.Frame(window, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        outer.rowconfigure(5, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.details_total = ttk.Label(header, text="Total: 0 t", font="TkHeadingFont")
        self.details_total.grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Reset all", command=self._reset_all).grid(row=0, column=1, sticky="e")

        ttk.Label(outer, text="Targets").grid(row=1, column=0, sticky="w", pady=(12, 2))
        targets_box, self.target_rows, self.target_wheel = _scroll_area(outer, 220)
        targets_box.grid(row=2, column=0, sticky="nsew")

        ttk.Label(outer, text="History (deleted entries)").grid(
            row=3, column=0, sticky="w", pady=(14, 2)
        )
        ttk.Label(
            outer,
            text="Deleted entries stay here so an accidental reset can be undone.",
        ).grid(row=4, column=0, sticky="w")
        history_box, self.history_rows, self.history_wheel = _scroll_area(outer, 160)
        history_box.grid(row=5, column=0, sticky="nsew")

        self._refresh_details()

    def close_details(self) -> None:
        if self.details is not None:
            try:
                self.details.destroy()
            except tk.TclError:
                pass
        self.details = None

    def _refresh_details(self) -> None:
        if self.details is None or not self.details.winfo_exists():
            return
        self._refresh_target_rows()
        self._refresh_history_rows()

    def _refresh_target_rows(self) -> None:
        if self.target_rows is None or self.details_total is None:
            return

        _clear(self.target_rows)
        targets = self._targets()
        self.details_total.configure(
            text=f"Total: {format_number(sum(target.tons for target in targets))} t"
        )
        if not targets:
            ttk.Label(self.target_rows, text="No deliveries tracked yet.").pack(
                anchor="w", pady=6
            )
            _bind_wheel(self.target_rows, self.target_wheel)
            return

        for target in targets:
            row = ttk.Frame(self.target_rows)
            row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=1)

            ttk.Label(row, text=_short(target.label, 32), anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Label(row, text=target.kind_label, width=15, anchor="w").grid(
                row=0, column=1, sticky="w", padx=(8, 0)
            )
            ttk.Label(row, text=f"{format_number(target.tons)} t", width=10, anchor="e").grid(
                row=0, column=2, sticky="e", padx=(8, 8)
            )
            ttk.Button(
                row,
                text="Reset",
                width=6,
                command=lambda mid=target.market_id: self._reset_target(mid),
            ).grid(row=0, column=3, sticky="e")

        _bind_wheel(self.target_rows, self.target_wheel)

    def _refresh_history_rows(self) -> None:
        if self.history_rows is None:
            return

        _clear(self.history_rows)
        history = self._history()
        if not history:
            ttk.Label(self.history_rows, text="Nothing deleted yet.").pack(anchor="w", pady=6)
            _bind_wheel(self.history_rows, self.history_wheel)
            return

        for entry in history:
            snapshot = entry.get("target") or {}
            target = Target.from_dict(snapshot)
            row = ttk.Frame(self.history_rows)
            row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=1)

            ttk.Label(row, text=_short(target.label, 26), anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Label(row, text=target.kind_label, width=15, anchor="w").grid(
                row=0, column=1, sticky="w", padx=(8, 0)
            )
            ttk.Label(row, text=f"{format_number(target.tons)} t", width=10, anchor="e").grid(
                row=0, column=2, sticky="e", padx=(8, 8)
            )
            ttk.Label(row, text=format_timestamp(entry.get("deleted_at", "")), width=16, anchor="w").grid(
                row=0, column=3, sticky="w"
            )
            ttk.Button(
                row,
                text="Restore",
                width=8,
                command=lambda hid=entry.get("id"): self._restore(hid),
            ).grid(row=0, column=4, sticky="e")

        _bind_wheel(self.history_rows, self.history_wheel)

    # -- actions ---------------------------------------------------------

    def _reset_target(self, market_id: int) -> None:
        if not self.cmdr_key:
            return
        if self.store.reset_target(self.cmdr_key, market_id, now_iso()):
            self.refresh()

    def _reset_all(self) -> None:
        if not self.cmdr_key:
            return
        parent = self.details if self.details is not None else self.panel
        if not messagebox.askyesno(
            "Reset all entries",
            "Move every tracked target to the history?\n\nThe tonnage is not lost: "
            "each entry can be restored from the history.",
            parent=parent,
        ):
            return
        if self.store.reset_all(self.cmdr_key, now_iso()):
            self.refresh()

    def _restore(self, history_id: Optional[str]) -> None:
        if not self.cmdr_key or not history_id:
            return
        if self.store.restore(self.cmdr_key, str(history_id)):
            self.refresh()

    # -- preferences -----------------------------------------------------

    def build_prefs(self, parent: tk.Misc) -> "nb.Frame":
        frame = nb.Frame(parent)
        frame.columnconfigure(0, weight=1)

        nb.Label(frame, text="Galtea Haul Tracker").grid(row=0, column=0, sticky="w")
        nb.Label(
            frame,
            text=(
                "Tracks tonnage sold to fleet carriers and squadron carriers, and "
                "commodities delivered to construction sites.\n"
                f"Data file: {self.store.path}"
            ),
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))
        nb.Button(frame, text="Reset all tracked entries\u2026", command=self._reset_all).grid(
            row=2, column=0, sticky="w"
        )
        return frame

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self.close_details()
