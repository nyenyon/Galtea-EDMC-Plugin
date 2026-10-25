"""Tk user interface: main-window panel, details window and preferences.

Widgets use classic ``tk`` (not ``ttk``) so EDMC's theme module can colour
them: in dark mode EDMC recolours registered ``tk`` widgets, while ``ttk``
styling is not applied to plugin widgets.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import font as tkfont
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
GITHUB_URL = "https://github.com/nyenyon/Galtea-EDMC-Plugin"

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


def _open_url(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - opening a browser must never break the UI
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
            # Windows reports one wheel notch as 120; macOS trackpads report
            # much smaller values, so fall back to a single unit.
            steps = int(-event.delta / 120)
            if steps == 0:
                steps = -1 if event.delta > 0 else 1
            canvas.yview_scroll(steps, "units")

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

    def __init__(self, parent: tk.Misc, tracker: Any, store: HaulStore, version: str = ""):
        self.parent = parent
        self.tracker = tracker
        self.store = store
        self.version = str(version or "")

        self.panel: Optional[tk.Frame] = None
        self.panel_rows: Optional[tk.Frame] = None
        self.panel_more: Optional[tk.Label] = None
        self.panel_total: Optional[tk.Label] = None

        self.details: Optional[tk.Toplevel] = None
        self.details_total: Optional[tk.Label] = None
        self.details_bulk: Optional[tk.Button] = None
        self.details_view = "targets"
        self.details_content: Optional[tk.Frame] = None
        self.targets_view: Optional[tk.Frame] = None
        self.history_view: Optional[tk.Frame] = None
        self.tab_targets: Optional[tk.Label] = None
        self.tab_history: Optional[tk.Label] = None
        self.tab_targets_bar: Optional[tk.Frame] = None
        self.tab_history_bar: Optional[tk.Frame] = None
        self.target_rows: Optional[tk.Frame] = None
        self.history_rows: Optional[tk.Frame] = None
        self.target_wheel: Any = None
        self.history_wheel: Any = None
        self._history_sig: Optional[tuple] = None

        self.report_window: Optional[tk.Toplevel] = None
        self.report_copied = False
        self.discord_user_var: Optional[tk.StringVar] = None
        self.link_font: Optional[tkfont.Font] = None

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

        # Mirror EDMC's per-plugin separator (a themed highlight frame) so the
        # next EDMC control ("Update") is visually separate from this panel.
        tk.Frame(frame, highlightthickness=1).grid(
            row=5, column=0, sticky="ew", pady=(8, 6)
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

        self.details_view = "targets"
        window = tk.Toplevel(self.parent)
        window.title("Galtea Haul Tracker")
        window.geometry("760x600")
        window.minsize(600, 440)
        window.protocol("WM_DELETE_WINDOW", self.close_details)
        self.details = window

        outer = tk.Frame(window, padx=12, pady=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = tk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.details_total = tk.Label(header, text="Total: 0 t", font="TkHeadingFont")
        self.details_total.grid(row=0, column=0, sticky="w")
        self.details_bulk = tk.Button(
            header, text="Finish all hauls", command=self._reset_all
        )
        self.details_bulk.grid(row=0, column=1, sticky="e")

        tabs = tk.Frame(outer)
        tabs.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.tab_targets, self.tab_targets_bar = self._build_details_tab(
            tabs, "Active hauls", "targets"
        )
        self.tab_history, self.tab_history_bar = self._build_details_tab(
            tabs, "Finished hauls (0)", "history"
        )

        # Dim line under the whole tab strip; the active tab gets an accent
        # bar of its own just above it.
        tk.Frame(outer, highlightthickness=1).grid(row=2, column=0, sticky="ew")

        self.details_content = tk.Frame(outer)
        self.details_content.grid(row=3, column=0, sticky="nsew")
        self.details_content.columnconfigure(0, weight=1)
        self.details_content.rowconfigure(0, weight=1)

        self.targets_view = tk.Frame(self.details_content)
        self.targets_view.grid(row=0, column=0, sticky="nsew")
        self.targets_view.columnconfigure(0, weight=1)
        self.targets_view.rowconfigure(0, weight=1)
        targets_box, self.target_rows, self.target_wheel = _scroll_area(
            self.targets_view, 300
        )
        targets_box.grid(row=0, column=0, sticky="nsew")

        self.history_view = tk.Frame(self.details_content)
        self.history_view.grid(row=0, column=0, sticky="nsew")
        self.history_view.columnconfigure(0, weight=1)
        self.history_view.rowconfigure(0, weight=1)
        history_box, self.history_rows, self.history_wheel = _scroll_area(
            self.history_view, 300
        )
        history_box.grid(row=0, column=0, sticky="nsew")

        self._show_details_view("targets")
        _apply_theme(window)

    def _build_details_tab(
        self, parent: tk.Misc, text: str, view: str
    ) -> tuple[tk.Label, tk.Frame]:
        """Create one flat tab label with a thin accent bar underneath."""
        cell = tk.Frame(parent)
        cell.pack(side="left")
        label = tk.Label(cell, text=text, padx=12, pady=4)
        label.pack(side="top")
        bar = tk.Frame(cell, height=2, bd=0)
        bar.pack(side="bottom", fill="x")

        def switch(_event: tk.Event) -> None:
            self._show_details_view(view)

        for widget in (cell, label, bar):
            widget.bind("<Button-1>", switch)
        return label, bar

    def _show_details_view(self, view: str) -> None:
        """Switch between the active and finished hauls tabs."""
        self.details_view = "history" if view == "history" else "targets"
        if self.targets_view is not None and self.history_view is not None:
            if self.details_view == "targets":
                self.history_view.grid_remove()
                self.targets_view.grid()
            else:
                self.targets_view.grid_remove()
                self.history_view.grid()
        self._refresh_details()

    def _update_details_tabs(self) -> None:
        targets = len(self._targets())
        history = len(self._history())
        if self.tab_targets is not None:
            try:
                self.tab_targets.configure(text=f"Active hauls ({targets})")
            except tk.TclError:
                pass
        if self.tab_history is not None:
            try:
                self.tab_history.configure(text=f"Finished hauls ({history})")
            except tk.TclError:
                pass
        if self.details_bulk is not None:
            try:
                if self.details_view == "history":
                    self.details_bulk.configure(
                        text="Delete all",
                        command=self._delete_all_history,
                        state=tk.NORMAL if history else tk.DISABLED,
                    )
                else:
                    self.details_bulk.configure(
                        text="Finish all hauls",
                        command=self._reset_all,
                        state=tk.NORMAL if targets else tk.DISABLED,
                    )
            except tk.TclError:
                pass

        accent = background = ""
        try:
            current = getattr(theme, "current", None) or {}
            accent = str(current.get("foreground") or "")
            background = str(current.get("background") or "")
        except Exception:  # noqa: BLE001 - theming must never break the window
            pass

        for view, bar in (
            ("targets", self.tab_targets_bar),
            ("history", self.tab_history_bar),
        ):
            if bar is None:
                continue
            color = accent if view == self.details_view else background
            if not color:
                continue
            try:
                bar.configure(background=color)
            except tk.TclError:
                pass

    def close_details(self) -> None:
        self._close_report()
        if self.details is not None:
            try:
                self.details.destroy()
            except tk.TclError:
                pass
        self.details = None
        self.details_bulk = None
        self.details_content = None
        self.targets_view = None
        self.history_view = None
        self.tab_targets = None
        self.tab_history = None
        self.tab_targets_bar = None
        self.tab_history_bar = None
        self._history_sig = None

    def _refresh_details(self) -> None:
        if self.details is None or not self.details.winfo_exists():
            return
        self._refresh_target_rows()
        self._refresh_history_rows()
        self._update_details_tabs()

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

        counts: Dict[int, int] = {}
        for target in targets:
            counts[target.market_id] = counts.get(target.market_id, 0) + 1

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
                text="Finish haul",
                width=11,
                command=lambda tid=target.id, label=target.label: self._reset_target(
                    tid, label
                ),
            ).grid(row=0, column=4, sticky="e")

            # Only ambiguous when a restored batch runs next to a newer one.
            if counts.get(target.market_id, 0) > 1:
                tk.Label(
                    row,
                    text=f"Batch {target.id[:8]}",
                    anchor="w",
                    font="TkSmallCaptionFont",
                ).grid(row=1, column=0, sticky="w")

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
            tk.Label(self.history_rows, text="No finished hauls yet.").pack(anchor="w", pady=6)
            _bind_wheel(self.history_rows, self.history_wheel)
            _apply_theme(self.history_rows)
            return

        for entry in history:
            snapshot = entry.get("target") or {}
            target = Target.from_dict(snapshot)
            row = tk.Frame(self.history_rows)
            row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=1)

            tk.Label(row, text=_short(target.label, 24), anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            tk.Label(row, text=target.kind_label, width=15, anchor="w").grid(
                row=0, column=1, sticky="w", padx=(8, 0)
            )
            tk.Label(row, text=f"{format_number(target.tons)} t", width=10, anchor="e").grid(
                row=0, column=2, sticky="e", padx=(8, 8)
            )
            reported = str(entry.get("reason") or "") == "reported"
            tk.Label(
                row,
                text="Reported" if reported else "\u2014",
                width=9,
                anchor="w",
            ).grid(row=0, column=3, sticky="w", padx=(0, 8))
            tk.Label(row, text=format_timestamp(entry.get("deleted_at", "")), width=16, anchor="w").grid(
                row=0, column=4, sticky="w"
            )
            tk.Button(
                row,
                text="Restore",
                width=8,
                command=lambda hid=entry.get("id"): self._restore(hid),
            ).grid(row=0, column=5, sticky="e")
            tk.Button(
                row,
                text="Delete",
                width=6,
                command=lambda hid=entry.get("id"), label=target.label: self._delete_history(
                    hid, label
                ),
            ).grid(row=0, column=6, sticky="e", padx=(4, 0))

        _bind_wheel(self.history_rows, self.history_wheel)
        _apply_theme(self.history_rows)

    # -- report ----------------------------------------------------------

    def _show_report(self, target: Target) -> None:
        """Show the Discord/Sicord macro for one target in a copyable field."""
        user = self.discord_user()
        command = target.report_command(user)
        parent = self.details if self.details is not None else self.panel
        self._close_report()
        self.report_copied = False

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
            anchor="w", pady=(2, 2)
        )
        siblings = sum(1 for item in self._targets() if item.market_id == target.market_id)
        if siblings > 1:
            tk.Label(frame, text=f"Batch {target.id[:8]}", font="TkSmallCaptionFont").pack(
                anchor="w"
            )
        tk.Label(frame, text="Paste this command into Discord or Sicord:").pack(
            anchor="w", pady=(8, 0)
        )

        entry = tk.Entry(frame, width=64)
        entry.insert(0, command)
        entry.configure(state="readonly")
        entry.pack(fill="x", pady=(2, 10))

        if user == DEFAULT_DISCORD_USER:
            tk.Label(
                frame,
                text=(
                    f"Note: {DEFAULT_DISCORD_USER} is only a placeholder. "
                    "Change the Discord user in EDMC's settings "
                    "(Galtea Haul Tracker) before using this command."
                ),
                justify="left",
                wraplength=440,
            ).pack(anchor="w", pady=(0, 10))

        buttons = tk.Frame(frame)
        buttons.pack(fill="x")
        for column in range(3):
            buttons.columnconfigure(column, weight=1)
        copy_button = tk.Button(buttons, text="Copy", width=8)
        copy_button.configure(command=lambda: self._copy_report(command, copy_button))
        copy_button.grid(row=0, column=0, sticky="w")
        tk.Button(
            buttons,
            text="Reported",
            width=10,
            command=lambda: self._mark_reported(target),
        ).grid(row=0, column=1)
        tk.Button(buttons, text="Close", width=8, command=self._close_report).grid(
            row=0, column=2, sticky="e"
        )

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

    def _mark_reported(self, target: Target) -> None:
        """Finish a target after its tonnage has been reported."""
        if not self.cmdr_key:
            return
        if not self.report_copied:
            parent = self.report_window
            if parent is None:
                parent = self.details if self.details is not None else self.panel
            if not messagebox.askyesno(
                "Confirm reported",
                "The command was not copied. Was this delivery really reported?\n\n"
                "Finishing it removes the haul from the active list.",
                parent=parent,
                default="no",
            ):
                return
        if self.store.reset_target(self.cmdr_key, target.id, now_iso(), reason="reported"):
            self.refresh()
        self._close_report()

    def _copy_report(self, command: str, button: tk.Button) -> None:
        owner = self.details if self.details is not None else self.parent
        try:
            owner.clipboard_clear()
            owner.clipboard_append(command)
        except tk.TclError:
            return
        self.report_copied = True
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
        self.report_copied = False

    # -- actions ---------------------------------------------------------

    def _ask_finish_haul(self, label: str = "") -> Optional[str]:
        """Ask whether a haul was reported; return reported, unreported or None."""
        parent = self.details if self.details is not None else self.panel
        owner = parent.winfo_toplevel()
        window = tk.Toplevel(parent)
        window.title("Finish haul")
        window.transient(owner)
        window.resizable(False, False)

        result: Optional[str] = None

        def close(decision: Optional[str]) -> None:
            nonlocal result
            result = decision
            try:
                window.destroy()
            except tk.TclError:
                pass

        window.protocol("WM_DELETE_WINDOW", lambda: close(None))
        window.bind("<Escape>", lambda _event: close(None))

        frame = tk.Frame(window, padx=12, pady=12)
        frame.pack(fill="both", expand=True)
        question = (
            f'Has the haul "{label}" already been reported?'
            if label
            else "Has this haul already been reported?"
        )
        tk.Label(
            frame, text=question, font="TkHeadingFont", justify="left", wraplength=480
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=(
                "Yes marks it as reported.\n"
                "No, do it anyway finishes it without the reported flag.\n"
                "Cancel keeps it in Active hauls."
            ),
            justify="left",
            wraplength=480,
        ).pack(anchor="w", pady=(6, 12))

        buttons = tk.Frame(frame)
        buttons.pack(fill="x")
        tk.Button(buttons, text="Yes", width=8, command=lambda: close("reported")).pack(
            side="left"
        )
        tk.Button(
            buttons,
            text="No, do it anyway",
            command=lambda: close("unreported"),
        ).pack(side="left", padx=(6, 0))
        cancel = tk.Button(buttons, text="Cancel", width=8, command=lambda: close(None))
        cancel.pack(side="right")

        _apply_theme(window)
        window.update_idletasks()
        x = owner.winfo_rootx() + max(
            (owner.winfo_width() - window.winfo_reqwidth()) // 2, 0
        )
        y = owner.winfo_rooty() + max(
            (owner.winfo_height() - window.winfo_reqheight()) // 2, 0
        )
        window.geometry(f"+{x}+{y}")
        try:
            window.wait_visibility()
        except tk.TclError:
            pass
        cancel.focus_set()
        try:
            window.grab_set()
        except tk.TclError:
            pass
        window.wait_window()
        return result

    def _reset_target(self, target_id: str, label: str = "") -> None:
        if not self.cmdr_key:
            return
        decision = self._ask_finish_haul(label)
        if decision is None:
            return
        reason = "reported" if decision == "reported" else "unreported"
        if self.store.reset_target(self.cmdr_key, target_id, now_iso(), reason=reason):
            self.refresh()

    def _reset_all(self) -> None:
        if not self.cmdr_key:
            return
        parent = self.details if self.details is not None else self.panel
        if not messagebox.askyesno(
            "Finish all hauls",
            "Move every active haul to Finished hauls?\n\nThe tonnage is not lost: "
            "each entry can be restored from Finished hauls.",
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

    def _delete_history(self, history_id: Optional[str], label: str = "") -> None:
        if not self.cmdr_key or not history_id:
            return
        parent = self.details if self.details is not None else self.panel
        name = f'"{label}"' if label else "this entry"
        if not messagebox.askyesno(
            "Delete finished haul",
            f"Permanently delete {name} from Finished hauls?\n\n"
            "This cannot be undone.",
            parent=parent,
            default="no",
        ):
            return
        if self.store.delete_history(self.cmdr_key, str(history_id)):
            self.refresh()

    def _delete_all_history(self) -> None:
        if not self.cmdr_key:
            return
        history = self._history()
        if not history:
            return
        parent = self.details if self.details is not None else self.panel
        if not messagebox.askyesno(
            "Delete all finished hauls",
            f"Permanently delete all {len(history)} finished hauls?\n\n"
            "This cannot be undone.",
            parent=parent,
            default="no",
        ):
            return
        if self.store.clear_history(self.cmdr_key):
            self.refresh()

    # -- preferences -----------------------------------------------------

    def build_prefs(self, parent: tk.Misc) -> "nb.Frame":
        frame = nb.Frame(parent)
        frame.columnconfigure(0, weight=1)

        nb.Label(frame, text="Galtea Haul Tracker").grid(row=0, column=0, sticky="w")
        description = nb.Label(
            frame,
            text=(
                "Tracks tonnage sold to fleet carriers and squadron carriers, and "
                "commodities delivered to construction sites.\n"
                f"Data file: {self.store.path}"
            ),
            justify="left",
            wraplength=420,
        )
        description.grid(row=1, column=0, sticky="w", pady=(4, 8))

        nb.Label(frame, text="Discord user for the Report command").grid(
            row=2, column=0, sticky="w"
        )
        self.discord_user_var = tk.StringVar(master=frame, value=self.discord_user())
        ttk.Entry(frame, textvariable=self.discord_user_var, width=1).grid(
            row=3, column=0, sticky="ew", pady=(2, 2)
        )
        hint = nb.Label(
            frame,
            text=(
                f"Used as user:@name in the /addscore command "
                f"(default: {DEFAULT_DISCORD_USER})."
            ),
            justify="left",
            wraplength=420,
        )
        hint.grid(row=4, column=0, sticky="w", pady=(0, 8))

        nb.Button(frame, text="Finish all hauls\u2026", command=self._reset_all).grid(
            row=5, column=0, sticky="w"
        )

        # Footer: version and repository link, left aligned and kept at the
        # bottom of the page.  EDMC does not theme the plugin prefs tab, so use
        # nb widgets (their default colours) instead of theme.update().
        frame.rowconfigure(6, weight=1)
        footer = tk.Frame(frame)
        footer.grid(row=7, column=0, sticky="w", pady=(12, 0))
        version_label = nb.Label(footer, text=f"Version {self.version or 'unknown'}")
        version_label.pack(side="left")
        background = version_label.cget("background")
        if background:
            footer.configure(background=background)
        if self.link_font is None:
            self.link_font = tkfont.nametofont("TkDefaultFont").copy()
            self.link_font.configure(underline=True)
        link = nb.Label(
            footer, text=GITHUB_URL, cursor="hand2", font=self.link_font, wraplength=420
        )
        link.pack(side="left", padx=(8, 0))
        link.bind("<Button-1>", lambda _event: _open_url(GITHUB_URL))

        def fit_width(event: tk.Event) -> None:
            """Keep the long labels inside the page when the dialog is resized."""
            width = max(int(event.width) - 4, 200)
            for label in (description, hint):
                try:
                    label.configure(wraplength=width)
                except tk.TclError:
                    pass
            try:
                link.configure(
                    wraplength=max(width - version_label.winfo_reqwidth() - 12, 80)
                )
            except tk.TclError:
                pass

        frame.bind("<Configure>", fit_width, add="+")
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
