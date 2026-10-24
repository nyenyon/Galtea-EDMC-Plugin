"""Tk user interface: main-window panel, details window and preferences.

Widgets use classic ``tk`` (not ``ttk``) so EDMC's theme module can colour
them: in dark mode EDMC recolours registered ``tk`` widgets, while ``ttk``
styling is not applied to plugin widgets.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

import myNotebook as nb
from theme import theme

from .model import (
    DEFAULT_DISCORD_USER,
    Target,
    format_number,
    format_timestamp,
    normalize_discord_user,
    now_iso,
)
from .store import HaulStore

PANEL_ROWS = 3
SETTING_DISCORD_USER = "galtea_discord_user"

try:  # EDMC 6 exposes the config singleton from the config package
    from config import config as _edmc_config
except ImportError:  # older EDMC provides the getters on the module itself
    try:
        import config as _edmc_config
    except ImportError:  # pragma: no cover - only happens outside EDMC
        _edmc_config = None  # type: ignore[assignment]


def _get_setting(key: str, default: str) -> str:
    if _edmc_config is None:
        return default
    try:
        value = _edmc_config.get_str(key, default)
    except Exception:  # noqa: BLE001 - a broken config must not break the UI
        return default
    return str(value or default)


def _set_setting(key: str, value: str) -> None:
    if _edmc_config is None:
        return
    try:
        _edmc_config.set(key, value)
        # Newer EDMC versions save on ``set`` already; older ones only write on
        # shutdown.  Saving here keeps the Discord handle across crashes too.
        save = getattr(_edmc_config, "save", None)
        if callable(save):
            save()
    except Exception:  # noqa: BLE001 - saving prefs must never fail loudly
        pass


def _short(text: str, limit: int = 34) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _apply_theme(widget: tk.Misc) -> None:
    """Register a widget tree with EDMC's theme and apply current colours.

    ``theme.update`` registers the widget (and, for frames, its children) and
    colours the widget plus its direct children.  Walking the tree ourselves
    also covers nested rows and history entries created after startup.
    """
    try:
        theme.update(widget)
    except Exception:  # noqa: BLE001 - theming must never break the plugin
        pass
    for child in widget.winfo_children():
        _apply_theme(child)


def _scroll_area(parent: tk.Misc, height: int) -> tuple[tk.Frame, tk.Frame, Any]:
    """A vertically scrollable container.

    Returns (container, inner frame, wheel callback).
    """
    container = tk.Frame(parent)
    # Keep the canvas background at the frame default: EDMC treats an
    # explicitly coloured canvas as intentional and would not re-theme it.
    canvas = tk.Canvas(
        container,
        height=height,
        highlightthickness=0,
        bd=0,
        background=container["background"],
    )
    scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
    # theme.py recolours the slider but not the trough; match the current
    # background so the scrollbar does not stand out in the dark theme.
    try:
        if theme.current:
            scrollbar.configure(troughcolor=theme.current["background"])
    except Exception:  # noqa: BLE001 - cosmetic only
        pass
    inner = tk.Frame(canvas)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

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

        self.panel: Optional[tk.Frame] = None
        self.panel_rows: Optional[tk.Frame] = None
        self.panel_more: Optional[tk.Label] = None
        self.panel_total: Optional[tk.Label] = None

        self.details: Optional[tk.Toplevel] = None
        self.details_total: Optional[tk.Label] = None
        self.target_rows: Optional[tk.Frame] = None
        self.history_rows: Optional[tk.Frame] = None
        self.target_wheel: Any = None
        self.history_wheel: Any = None
        self._history_sig: Optional[tuple] = None

        self.report_window: Optional[tk.Toplevel] = None
        self.discord_user_var: Optional[tk.StringVar] = None

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

    def discord_user(self) -> str:
        """Discord handle used in report commands (configurable in the prefs)."""
        return (
            normalize_discord_user(_get_setting(SETTING_DISCORD_USER, DEFAULT_DISCORD_USER))
            or DEFAULT_DISCORD_USER
        )

    # -- main window panel ----------------------------------------------

    def build_panel(self, parent: tk.Misc) -> tk.Frame:
        self.parent = parent
        frame = tk.Frame(parent)
        frame.columnconfigure(0, weight=1)

        tk.Label(frame, text="Galtea Haul Tracker").grid(row=0, column=0, sticky="w")

        self.panel_rows = tk.Frame(frame)
        self.panel_rows.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.panel_more = tk.Label(frame, text="")
        self.panel_more.grid(row=2, column=0, sticky="w")

        self.panel_total = tk.Label(frame, text="Total: 0 t")
        self.panel_total.grid(row=3, column=0, sticky="w", pady=(4, 0))

        tk.Button(frame, text="Details", command=self.open_details).grid(
            row=4, column=0, sticky="ew", pady=(4, 0)
        )

        self.panel = frame
        self.refresh()
        _apply_theme(frame)
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
            tk.Label(self.panel_rows, text="No deliveries yet").pack(anchor="w")
            self.panel_more.configure(text="")
            self.panel_total.configure(text="Total: 0 t")
            _apply_theme(self.panel_rows)
            return

        for target in targets[:PANEL_ROWS]:
            row = tk.Frame(self.panel_rows)
            row.pack(fill="x")
            tk.Label(row, text=_short(target.label, 20), anchor="w").pack(
                side="left", fill="x", expand=True
            )
            tk.Label(row, text=f"{format_number(target.tons)} t", anchor="e").pack(side="right")

        hidden = len(targets) - PANEL_ROWS
        self.panel_more.configure(text=f"+{hidden} more" if hidden > 0 else "")
        self.panel_total.configure(
            text=f"Total: {format_number(sum(target.tons for target in targets))} t"
        )
        _apply_theme(self.panel_rows)

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

        outer = tk.Frame(window, padx=12, pady=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        outer.rowconfigure(5, weight=1)

        header = tk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.details_total = tk.Label(header, text="Total: 0 t", font="TkHeadingFont")
        self.details_total.grid(row=0, column=0, sticky="w")
        tk.Button(header, text="Reset all", command=self._reset_all).grid(
            row=0, column=1, sticky="e"
        )

        tk.Label(outer, text="Targets").grid(row=1, column=0, sticky="w", pady=(12, 2))
        targets_box, self.target_rows, self.target_wheel = _scroll_area(outer, 220)
        targets_box.grid(row=2, column=0, sticky="nsew")

        tk.Label(outer, text="History (deleted entries)").grid(
            row=3, column=0, sticky="w", pady=(14, 2)
        )
        tk.Label(
            outer,
            text="Deleted entries stay here so an accidental reset can be undone.",
        ).grid(row=4, column=0, sticky="w")
        history_box, self.history_rows, self.history_wheel = _scroll_area(outer, 160)
        history_box.grid(row=5, column=0, sticky="nsew")

        self._refresh_details()
        _apply_theme(window)

    def close_details(self) -> None:
        self._close_report()
        if self.details is not None:
            try:
                self.details.destroy()
            except tk.TclError:
                pass
        self.details = None
        self._history_sig = None

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
            tk.Label(self.target_rows, text="No deliveries tracked yet.").pack(anchor="w", pady=6)
            _bind_wheel(self.target_rows, self.target_wheel)
            _apply_theme(self.target_rows)
            return

        for target in targets:
            row = tk.Frame(self.target_rows)
            row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=1)

            tk.Label(row, text=_short(target.label, 32), anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            tk.Label(row, text=target.kind_label, width=15, anchor="w").grid(
                row=0, column=1, sticky="w", padx=(8, 0)
            )
            tk.Label(row, text=f"{format_number(target.tons)} t", width=10, anchor="e").grid(
                row=0, column=2, sticky="e", padx=(8, 8)
            )
            tk.Button(
                row,
                text="Report",
                width=8,
                command=lambda item=target: self._show_report(item),
            ).grid(row=0, column=3, sticky="e", padx=(0, 4))
            tk.Button(
                row,
                text="Reset",
                width=6,
                command=lambda mid=target.market_id: self._reset_target(mid),
            ).grid(row=0, column=4, sticky="e")

        _bind_wheel(self.target_rows, self.target_wheel)
        _apply_theme(self.target_rows)

    def _refresh_history_rows(self) -> None:
        if self.history_rows is None:
            return

        history = self._history()
        signature = tuple(str(entry.get("id", "")) for entry in history)
        if signature == self._history_sig:
            return
        self._history_sig = signature

        _clear(self.history_rows)
        if not history:
            tk.Label(self.history_rows, text="Nothing deleted yet.").pack(anchor="w", pady=6)
            _bind_wheel(self.history_rows, self.history_wheel)
            _apply_theme(self.history_rows)
            return

        for entry in history:
            snapshot = entry.get("target") or {}
            target = Target.from_dict(snapshot)
            row = tk.Frame(self.history_rows)
            row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=1)

            tk.Label(row, text=_short(target.label, 26), anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            tk.Label(row, text=target.kind_label, width=15, anchor="w").grid(
                row=0, column=1, sticky="w", padx=(8, 0)
            )
            tk.Label(row, text=f"{format_number(target.tons)} t", width=10, anchor="e").grid(
                row=0, column=2, sticky="e", padx=(8, 8)
            )
            tk.Label(row, text=format_timestamp(entry.get("deleted_at", "")), width=16, anchor="w").grid(
                row=0, column=3, sticky="w"
            )
            tk.Button(
                row,
                text="Restore",
                width=8,
                command=lambda hid=entry.get("id"): self._restore(hid),
            ).grid(row=0, column=4, sticky="e")

        _bind_wheel(self.history_rows, self.history_wheel)
        _apply_theme(self.history_rows)

    # -- report ----------------------------------------------------------

    def _show_report(self, target: Target) -> None:
        """Show the Discord/Sicord macro for one target in a copyable field."""
        command = target.report_command(self.discord_user())
        parent = self.details if self.details is not None else self.panel
        self._close_report()

        window = tk.Toplevel(parent)
        window.title("Report delivery")
        window.transient(parent)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self._close_report)
        window.bind("<Escape>", lambda _event: self._close_report())
        self.report_window = window

        frame = tk.Frame(window, padx=12, pady=12)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=f"Report {target.label}", font="TkHeadingFont").pack(anchor="w")
        tk.Label(frame, text=f"{format_number(target.tons)} t delivered").pack(
            anchor="w", pady=(2, 10)
        )
        tk.Label(frame, text="Paste this command into Discord or Sicord:").pack(anchor="w")

        entry = tk.Entry(frame, width=64)
        entry.insert(0, command)
        entry.configure(state="readonly")
        entry.pack(fill="x", pady=(2, 10))

        buttons = tk.Frame(frame)
        buttons.pack(fill="x")
        copy_button = tk.Button(buttons, text="Copy", width=8)
        copy_button.configure(command=lambda: self._copy_report(command, copy_button))
        copy_button.pack(side="left")
        tk.Button(buttons, text="Close", width=8, command=self._close_report).pack(side="right")

        _apply_theme(window)
        try:
            # Read-only entries use their own background colour, which EDMC's
            # theme does not update.
            entry.configure(
                readonlybackground=str(entry.cget("background")),
                readonlyforeground=str(entry.cget("foreground")),
            )
        except tk.TclError:
            pass

        entry.focus_set()
        entry.select_range(0, "end")

    def _copy_report(self, command: str, button: tk.Button) -> None:
        owner = self.details if self.details is not None else self.parent
        try:
            owner.clipboard_clear()
            owner.clipboard_append(command)
        except tk.TclError:
            return
        try:
            button.configure(text="Copied")
            button.after(1800, lambda: self._reset_copy_label(button))
        except tk.TclError:
            pass

    @staticmethod
    def _reset_copy_label(button: tk.Button) -> None:
        try:
            if button.winfo_exists():
                button.configure(text="Copy")
        except tk.TclError:
            pass

    def _close_report(self) -> None:
        if self.report_window is not None:
            try:
                self.report_window.destroy()
            except tk.TclError:
                pass
        self.report_window = None

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

        nb.Label(frame, text="Discord user for the Report command").grid(
            row=2, column=0, sticky="w"
        )
        self.discord_user_var = tk.StringVar(master=frame, value=self.discord_user())
        ttk.Entry(frame, textvariable=self.discord_user_var, width=32).grid(
            row=3, column=0, sticky="w", pady=(2, 2)
        )
        nb.Label(
            frame,
            text=(
                f"Used as user:@name in the /addscore command "
                f"(default: {DEFAULT_DISCORD_USER})."
            ),
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 8))

        nb.Button(frame, text="Reset all tracked entries\u2026", command=self._reset_all).grid(
            row=5, column=0, sticky="w"
        )
        return frame

    def save_prefs(self) -> None:
        """Persist the preferences page; called by EDMC after the dialog."""
        if self.discord_user_var is None:
            return
        _set_setting(
            SETTING_DISCORD_USER, normalize_discord_user(self.discord_user_var.get())
        )

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self.close_details()
