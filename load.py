"""EDMarketConnector plugin entry point.

Galtea Haul Tracker accumulates the tonnage sold to fleet carriers and
squadron carriers, plus the commodities delivered to construction sites, and
shows the running totals in the EDMC main window.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import tkinter as tk

VERSION = "0.1.0"

from galtea.core import Tracker
from galtea.store import HaulStore
from galtea.ui import PluginUI

logger = logging.getLogger("GalteaHaulTracker")

_PLUGIN_DIR = Path(__file__).resolve().parent
_STORE_FILE = _PLUGIN_DIR / "data" / "haul_tracker.json"

_store: Optional[HaulStore] = None
_tracker: Optional[Tracker] = None
_ui: Optional[PluginUI] = None


def _ensure() -> HaulStore:
    """Create the store/tracker once, regardless of hook order."""
    global _store, _tracker
    if _store is None:
        _store = HaulStore(_STORE_FILE)
        _tracker = Tracker(_store)
        logger.info("Galtea Haul Tracker %s using %s", VERSION, _STORE_FILE)
    return _store


def _ensure_ui(parent: Optional[tk.Misc] = None) -> PluginUI:
    global _ui
    _ensure()
    if _ui is None:
        _ui = PluginUI(parent, _tracker, _store)
    return _ui


def plugin_start3(plugin_dir: str) -> str:
    """Called by EDMC when the plugin is loaded."""
    global _PLUGIN_DIR, _STORE_FILE
    if plugin_dir:
        _PLUGIN_DIR = Path(plugin_dir).resolve()
        _STORE_FILE = _PLUGIN_DIR / "data" / "haul_tracker.json"
        # Rebuild the store if it was created before we knew the real folder.
        if _store is not None and Path(_store.path) != _STORE_FILE:
            _store.path = _STORE_FILE
            _store.load()
    _ensure()
    return "Galtea Haul Tracker"


def plugin_app(parent: tk.Misc) -> tk.Widget:
    """Add the tracker panel to the EDMC main window."""
    return _ensure_ui(parent).build_panel(parent)


def journal_entry(
    cmdr: str,
    is_beta: bool,
    system: Optional[str],
    station: Optional[str],
    entry: Dict[str, Any],
    state: Dict[str, Any],
) -> Optional[str]:
    """Called for every new journal entry (on EDMC's Tk main thread)."""
    try:
        _ensure()
        changed = _tracker.process(  # type: ignore[union-attr]
            entry,
            system,
            station,
            fid=(state or {}).get("FID"),
            cmdr=cmdr,
        )
        if changed and _ui is not None:
            _ui.refresh()
    except Exception:  # noqa: BLE001 - never break EDMC's journal handling
        logger.exception("Failed to process journal entry: %s", (entry or {}).get("event"))
    return None


def plugin_prefs(parent: tk.Misc, cmdr: str, is_beta: bool) -> tk.Widget:
    return _ensure_ui(parent).build_prefs(parent)


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    _ensure().save()


def plugin_stop() -> None:
    if _store is not None:
        _store.save()
    if _ui is not None:
        _ui.close()
