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

from .journal import is_squadron_callsign
from .model import (
    KIND_CARRIER,
    KIND_FLEET,
    KIND_SQUADRON,
    Target,
    now_iso,
)

SCHEMA_VERSION = 2
HISTORY_LIMIT = 200
CARRIER_LIMIT = 500


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
            changed = self._migrate()
            if self._correct_squadron_kinds():
                changed = True
            if changed:
                self.save()

    def _migrate(self) -> bool:
        """Give every target and history snapshot a unique batch id.

        Older files key the targets by market id and have no batch ids.  The
        same market id can now appear several times (after restoring a reported
        batch), so targets are keyed by their own id instead.
        """
        changed = False
        for record in (self.data.get("cmdrs") or {}).values():
            if not isinstance(record, dict):
                continue

            targets = record.get("targets")
            if isinstance(targets, dict):
                for key, target in list(targets.items()):
                    if not isinstance(target, dict):
                        continue
                    batch_id = str(target.get("id") or "")
                    if not batch_id:
                        batch_id = uuid.uuid4().hex
                        target["id"] = batch_id
                        changed = True
                    if str(key) != batch_id:
                        targets.pop(key, None)
                        targets[batch_id] = target
                        changed = True

            for entry in record.get("history") or []:
                if not isinstance(entry, dict):
                    continue
                if not entry.get("id"):
                    entry["id"] = uuid.uuid4().hex
                    changed = True
                snapshot = entry.get("target")
                if isinstance(snapshot, dict) and not snapshot.get("id"):
                    snapshot["id"] = uuid.uuid4().hex
                    changed = True

        try:
            version = int(self.data.get("version") or 1)
        except (TypeError, ValueError):
            version = 1
        if version < SCHEMA_VERSION:
            self.data["version"] = SCHEMA_VERSION
            changed = True
        return changed

    def _correct_squadron_kinds(self) -> bool:
        """Fix carriers stored as fleet carriers by older plugin versions.

        Journals report squadron carriers as ``FleetCarrier`` and only the
        four-character callsign (stored as the name) gives them away.
        """
        changed = False
        for record in (self.data.get("cmdrs") or {}).values():
            record = record or {}
            for target in (record.get("targets") or {}).values():
                target = target or {}
                if target.get("kind") == KIND_FLEET and is_squadron_callsign(target.get("name")):
                    target["kind"] = KIND_SQUADRON
                    changed = True
            for entry in record.get("history") or []:
                snapshot = (entry or {}).get("target") or {}
                if snapshot.get("kind") == KIND_FLEET and is_squadron_callsign(snapshot.get("name")):
                    snapshot["kind"] = KIND_SQUADRON
                    changed = True
        return changed

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
        if not isinstance(record.get("carriers"), dict):
            record["carriers"] = {}
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

    # -- carrier names ---------------------------------------------------

    def carrier_name(
        self, cmdr_key: str, market_id: Optional[int] = None, callsign: str = ""
    ) -> Dict[str, str]:
        """Best known display name for a carrier, by market id or callsign."""
        record = self._cmdr(cmdr_key)
        wanted_id = _as_int(market_id)
        wanted_callsign = str(callsign or "").strip().upper()

        for entry in (record.get("carriers") or {}).values():
            if not isinstance(entry, dict):
                continue
            entry_id = _as_int(entry.get("market_id"))
            entry_callsign = str(entry.get("callsign") or "").strip().upper()
            if (wanted_id and entry_id == wanted_id) or (
                wanted_callsign and entry_callsign == wanted_callsign
            ):
                return {
                    "name": str(entry.get("name") or ""),
                    "callsign": str(entry.get("callsign") or ""),
                }
        return {}

    def remember_carrier(
        self,
        cmdr_key: str,
        market_id: Optional[int],
        name: str,
        callsign: str = "",
    ) -> Dict[str, Any]:
        """Persist a carrier display name and return the stored record."""
        name = str(name or "").strip()
        if not name:
            return {}
        wanted_id = _as_int(market_id)
        wanted_callsign = str(callsign or "").strip()
        if not wanted_id and not wanted_callsign:
            return {}

        record = self._cmdr(cmdr_key)
        carriers = record["carriers"]

        entry: Optional[Dict[str, Any]] = None
        for existing in carriers.values():
            if not isinstance(existing, dict):
                continue
            existing_id = _as_int(existing.get("market_id"))
            existing_callsign = str(existing.get("callsign") or "").strip().upper()
            if (wanted_id and existing_id == wanted_id) or (
                wanted_callsign and existing_callsign == wanted_callsign.upper()
            ):
                entry = existing
                break

        changed = False
        if entry is None:
            key = str(wanted_id) if wanted_id else wanted_callsign.upper()
            entry = {}
            carriers[key] = entry
            changed = True

        if wanted_id and _as_int(entry.get("market_id")) != wanted_id:
            entry["market_id"] = wanted_id
            changed = True
        if wanted_callsign and str(entry.get("callsign") or "") != wanted_callsign:
            entry["callsign"] = wanted_callsign
            changed = True
        if entry.get("name") != name:
            entry["name"] = name
            changed = True

        while len(carriers) > CARRIER_LIMIT:
            carriers.pop(next(iter(carriers)))
            changed = True

        if changed:
            self.save()
        return {
            "market_id": _as_int(entry.get("market_id")),
            "callsign": str(entry.get("callsign") or ""),
            "name": name,
        }

    @staticmethod
    def _targets_for_market(
        record: Dict[str, Any], market_id: Any
    ) -> List[Dict[str, Any]]:
        """All active batches for one market, newest delivery first."""
        try:
            wanted = int(market_id)
        except (TypeError, ValueError):
            return []

        def belongs(target: Dict[str, Any]) -> bool:
            try:
                return int(target.get("market_id") or 0) == wanted
            except (TypeError, ValueError):
                return False

        matches = [
            target
            for target in (record.get("targets") or {}).values()
            if isinstance(target, dict) and belongs(target)
        ]
        matches.sort(key=lambda target: str(target.get("last_delivery") or ""), reverse=True)
        return matches

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
        moment = timestamp or now_iso()
        # Deliveries accumulate in the newest active batch for this market.
        matches = self._targets_for_market(record, market_id)
        target = matches[0] if matches else None

        if target is None:
            target = {
                "id": uuid.uuid4().hex,
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
            record["targets"][target["id"]] = target

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
        targets = self._targets_for_market(record, market_id)
        if not targets:
            return False

        changed = False
        for target in targets:
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
        self, cmdr_key: str, target_id: Any, when: str = "", reason: str = "deleted"
    ) -> bool:
        """Delete one batch and keep it in the history.

        ``target_id`` is the batch id.  A market id is accepted too and then
        resolves to the most recently delivered active batch.
        """
        record = self._cmdr(cmdr_key)
        target = record["targets"].pop(str(target_id), None)
        if target is None:
            matches = self._targets_for_market(record, target_id)
            if matches:
                target = matches[0]
                record["targets"].pop(str(target.get("id")), None)
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
        """Put a deleted entry back as its own batch and drop it from history.

        A restored batch keeps its own id, so it does not merge with another
        active batch for the same market.
        """
        record = self._cmdr(cmdr_key)
        history = record["history"]
        for index, entry in enumerate(history):
            if entry.get("id") != history_id:
                continue
            history.pop(index)
            snapshot = copy.deepcopy(entry.get("target") or {})
            batch_id = str(snapshot.get("id") or "") or uuid.uuid4().hex
            snapshot["id"] = batch_id
            existing = record["targets"].get(batch_id)
            if existing is None:
                record["targets"][batch_id] = snapshot
            else:
                # The same batch is somehow still active; merge instead of
                # dropping the restored tonnage.
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
        """Stored kind of the newest active batch, without building the list."""
        targets = self._targets_for_market(self._cmdr(cmdr_key), market_id)
        if not targets:
            return None
        return str(targets[0].get("kind") or "") or None

    def targets(self, cmdr_key: str) -> List[Target]:
        record = self._cmdr(cmdr_key)
        items = [Target.from_dict(value) for value in record["targets"].values()]
        items.sort(key=lambda target: (-target.tons, target.label.lower(), target.id))
        return items

    def history(self, cmdr_key: str) -> List[Dict[str, Any]]:
        record = self._cmdr(cmdr_key)
        return copy.deepcopy(record["history"])

    def total(self, cmdr_key: str) -> int:
        return sum(target.tons for target in self.targets(cmdr_key))
