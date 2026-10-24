"""Persistent accumulation of hauled tonnage.

One JSON document keeps every commander on this machine separate.  Each
commander owns a set of targets (carrier or construction site) and a history
of entries that were deleted or reset, so an accidental delete can be
inspected and undone.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model import (
    KIND_CARRIER,
    KIND_FLEET,
    KIND_SQUADRON,
    Target,
    now_iso,
)

SCHEMA_VERSION = 1
HISTORY_LIMIT = 200


class HaulStore:
    """Load, mutate and persist the haul totals."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {"version": SCHEMA_VERSION, "cmdrs": {}}
        self.load()

    # -- persistence -----------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Keep the broken file around for inspection but start clean.
            try:
                self.path.replace(self.path.with_suffix(".corrupt"))
            except OSError:
                pass
            return
        if isinstance(raw, dict) and isinstance(raw.get("cmdrs"), dict):
            raw.setdefault("version", SCHEMA_VERSION)
            self.data = raw

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            # Never let a failing disk stop the tracker from working in memory.
            pass

    # -- commander records ----------------------------------------------

    def _cmdr(self, cmdr_key: str, cmdr_name: str = "") -> Dict[str, Any]:
        key = str(cmdr_key or "unknown")
        commanders = self.data.setdefault("cmdrs", {})
        record = commanders.get(key)
        if record is None:
            record = {"name": cmdr_name or "", "targets": {}, "history": []}
            commanders[key] = record
        elif cmdr_name and record.get("name") != cmdr_name:
            record["name"] = cmdr_name
        record.setdefault("targets", {})
        record.setdefault("history", [])
        return record

    def cmdr_name(self, cmdr_key: str) -> str:
        record = (self.data.get("cmdrs") or {}).get(str(cmdr_key)) or {}
        return str(record.get("name") or "")

    def last_commander(self) -> str:
        """Commander to display before the journal tells us who is playing.

        EDMC only notifies plugins at startup when the game is running, so the
        plugin has to remember the last commander itself.  Files written before
        that key existed fall back to the most recently active commander.
        """
        remembered = str(self.data.get("last_commander") or "")
        if remembered:
            return remembered

        latest_key = ""
        latest_moment = ""
        for cmdr_key, record in (self.data.get("cmdrs") or {}).items():
            record = record or {}
            moments = [
                str((target or {}).get("last_delivery") or "")
                for target in (record.get("targets") or {}).values()
            ]
            moments += [
                str((entry or {}).get("deleted_at") or "")
                for entry in record.get("history") or []
            ]
            moment = max(moments, default="")
            if moment > latest_moment:
                latest_key = str(cmdr_key)
                latest_moment = moment
        return latest_key

    def remember_commander(self, cmdr_key: str, cmdr_name: str = "") -> None:
        """Persist the active commander for the next start."""
        key = str(cmdr_key or "")
        if not key:
            return
        changed = self.data.get("last_commander") != key
        self.data["last_commander"] = key
        record = (self.data.get("cmdrs") or {}).get(key)
        if record is not None and cmdr_name and record.get("name") != cmdr_name:
            changed = True
        self._cmdr(key, cmdr_name)
        if changed:
            self.save()

    # -- mutations -------------------------------------------------------

    def add(
        self,
        cmdr_key: str,
        cmdr_name: str,
        market_id: int,
        name: str,
        kind: str,
        tons: int,
        timestamp: str = "",
        station_type: str = "",
        system: str = "",
        display_name: str = "",
    ) -> bool:
        """Add a delivery.  Returns True when the stored totals changed."""
        tons = int(tons or 0)
        if tons <= 0 or not market_id:
            return False

        record = self._cmdr(cmdr_key, cmdr_name)
        key = str(int(market_id))
        target = record["targets"].get(key)
        moment = timestamp or now_iso()

        if target is None:
            target = {
                "market_id": int(market_id),
                "name": name or f"Market {market_id}",
                "kind": kind or KIND_CARRIER,
                "station_type": station_type or "",
                "system": system or "",
                "display_name": display_name or "",
                "tons": 0,
                "first_delivery": moment,
                "last_delivery": moment,
            }
            record["targets"][key] = target

        target["tons"] = int(target.get("tons") or 0) + tons
        target["last_delivery"] = moment
        if not target.get("first_delivery"):
            target["first_delivery"] = moment
        if display_name:
            target["display_name"] = display_name
        if station_type:
            target["station_type"] = station_type
        if system:
            target["system"] = system

        self.save()
        return True

    def update_target(
        self,
        cmdr_key: str,
        market_id: int,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        station_type: Optional[str] = None,
        system: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> bool:
        """Enrich an existing target with better metadata.

        Called whenever the commander docks somewhere: journal ``Docked`` and
        ``Location`` give us the station type, and carrier events may give the
        pretty name behind a callsign.
        """
        record = self._cmdr(cmdr_key)
        target = record["targets"].get(str(int(market_id)))
        if target is None:
            return False

        changed = False
        if station_type and target.get("station_type") != station_type:
            target["station_type"] = station_type
            changed = True
        if system and target.get("system") != system:
            target["system"] = system
            changed = True
        if display_name and target.get("display_name") != display_name:
            target["display_name"] = display_name
            changed = True
        if name and target.get("name") != name:
            current = str(target.get("name") or "")
            # Replace empty names and the generic fallback used when a
            # contribution arrives before we ever saw the station.
            if not current or current.startswith("Construction site "):
                target["name"] = name
                changed = True
        if kind and kind != target.get("kind"):
            current = target.get("kind")
            # Only upgrade the vague "carrier" kind, never downgrade a known one.
            if current in (KIND_CARRIER, None) and kind in (KIND_FLEET, KIND_SQUADRON):
                target["kind"] = kind
                changed = True
            elif current == KIND_FLEET and kind == KIND_SQUADRON:
                # The journal reports squadron carriers as "FleetCarrier"; a
                # squadron-bank service, a four-character callsign or
                # CarrierType is the better evidence.
                target["kind"] = kind
                changed = True

        if changed:
            self.save()
        return changed

    def reset_target(
        self, cmdr_key: str, market_id: int, when: str = "", reason: str = "deleted"
    ) -> bool:
        """Delete one target and keep it in the history."""
        record = self._cmdr(cmdr_key)
        target = record["targets"].pop(str(int(market_id)), None)
        if target is None:
            return False
        self._archive(record, target, when or now_iso(), reason)
        self.save()
        return True

    def reset_all(self, cmdr_key: str, when: str = "") -> int:
        """Delete every target of a commander, archiving each one."""
        record = self._cmdr(cmdr_key)
        moment = when or now_iso()
        removed = 0
        for key in list(record["targets"].keys()):
            target = record["targets"].pop(key)
            self._archive(record, target, moment, "reset_all")
            removed += 1
        if removed:
            self.save()
        return removed

    def restore(self, cmdr_key: str, history_id: str) -> bool:
        """Put a deleted entry back and drop it from the history."""
        record = self._cmdr(cmdr_key)
        history = record["history"]
        for index, entry in enumerate(history):
            if entry.get("id") != history_id:
                continue
            history.pop(index)
            snapshot = copy.deepcopy(entry.get("target") or {})
            key = str(snapshot.get("market_id"))
            existing = record["targets"].get(key)
            if existing is None:
                record["targets"][key] = snapshot
            else:
                existing["tons"] = int(existing.get("tons") or 0) + int(snapshot.get("tons") or 0)
                first = [x for x in (existing.get("first_delivery"), snapshot.get("first_delivery")) if x]
                last = [x for x in (existing.get("last_delivery"), snapshot.get("last_delivery")) if x]
                if first:
                    existing["first_delivery"] = min(first)
                if last:
                    existing["last_delivery"] = max(last)
            self.save()
            return True
        return False

    def _archive(self, record: Dict[str, Any], target: Dict[str, Any], when: str, reason: str) -> None:
        record["history"].insert(
            0,
            {
                "id": uuid.uuid4().hex,
                "deleted_at": when,
                "reason": reason,
                "target": copy.deepcopy(target),
            },
        )
        del record["history"][HISTORY_LIMIT:]

    # -- read access -----------------------------------------------------

    def target_kind(self, cmdr_key: str, market_id: int) -> Optional[str]:
        """Stored kind of one target, without building the whole list."""
        target = self._cmdr(cmdr_key)["targets"].get(str(int(market_id)))
        if target is None:
            return None
        return str(target.get("kind") or "") or None

    def targets(self, cmdr_key: str) -> List[Target]:
        record = self._cmdr(cmdr_key)
        items = [Target.from_dict(value) for value in record["targets"].values()]
        items.sort(key=lambda target: (-target.tons, target.label.lower()))
        return items

    def history(self, cmdr_key: str) -> List[Dict[str, Any]]:
        record = self._cmdr(cmdr_key)
        return copy.deepcopy(record["history"])

    def total(self, cmdr_key: str) -> int:
        return sum(target.tons for target in self.targets(cmdr_key))
