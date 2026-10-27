"""Event routing: turn live journal entries into accumulated tonnage."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .journal import (
    StationContext,
    carrier_name_from_drop,
    carrier_name_from_stats,
    delivery_tons,
    is_callsign,
    is_squadron_callsign,
    station_from_entry,
)
from .model import (
    CARRIER_KINDS,
    KIND_CARRIER,
    KIND_CONSTRUCTION,
    KIND_SQUADRON,
    construction_placeholder,
)
from .store import HaulStore

# Entries that tell us where the commander is docked.
_DOCK_EVENTS = ("Docked", "Location", "CarrierJump")
# Entries that carry station identity but do not mean "now docked here".
_STATION_HINTS = ("Market", "DockingGranted", "DockingRequested")


class Tracker:
    """Keep track of the current station and record deliveries."""

    def __init__(self, store: HaulStore):
        self.store = store
        self.current: Optional[StationContext] = None
        self.stations: Dict[int, StationContext] = {}
        # Names learned from a drop before we know whether the destination is a
        # carrier.  They are persisted once docking confirms the station kind.
        self.carrier_names: Dict[str, Dict[str, str]] = {}
        # Show the last active commander right away: EDMC only sends a
        # synthetic StartUp event when the game is already running.
        self.cmdr_key: str = store.last_commander()
        self.cmdr_name: str = store.cmdr_name(self.cmdr_key) if self.cmdr_key else ""

    # -- commander -------------------------------------------------------

    def _select_commander(self, cmdr: Optional[str], fid: Optional[str]) -> bool:
        key = str(fid) if fid else (str(cmdr) if cmdr else "unknown")
        if key == self.cmdr_key:
            if cmdr and cmdr != self.cmdr_name:
                self.cmdr_name = str(cmdr)
                self.store.remember_commander(key, self.cmdr_name)
            return False
        self.cmdr_key = key
        self.cmdr_name = str(cmdr or "")
        self.store.remember_commander(key, self.cmdr_name)
        self.current = None
        self.stations.clear()
        return True

    # -- entry point -----------------------------------------------------

    def process(
        self,
        entry: Dict[str, Any],
        system: Optional[str],
        station: Optional[str],
        fid: Optional[str] = None,
        cmdr: Optional[str] = None,
    ) -> bool:
        """Handle one journal entry.  Returns True when the display should refresh."""
        if not isinstance(entry, dict):
            return False

        changed = self._select_commander(cmdr, fid)
        event = entry.get("event")
        if not event:
            return changed

        if event in _DOCK_EVENTS:
            if event == "Location" and not entry.get("StationName"):
                # In space: no station context any more.
                self.current = None
            else:
                changed |= self._remember_station(entry, system)
        elif event == "Undocked":
            self.current = None
        elif event in _STATION_HINTS:
            changed |= self._remember_station(entry, system, set_current=False)
        elif event == "SupercruiseDestinationDrop":
            changed |= self._note_carrier_name(carrier_name_from_drop(entry))
        elif event in ("CarrierStats", "CarrierNameChanged"):
            changed |= self._note_carrier_name(carrier_name_from_stats(entry))
        elif event == "MarketSell":
            changed |= self._on_market_sell(entry, system, station)
        elif event == "ColonisationContribution":
            changed |= self._on_contribution(entry, system, station)

        return changed

    # -- station bookkeeping --------------------------------------------

    def _remember_station(
        self, entry: Dict[str, Any], system: Optional[str], set_current: bool = True
    ) -> bool:
        context = station_from_entry(entry)
        if context is None:
            return False
        if not context.system and system:
            context.system = str(system)
        if context.kind in CARRIER_KINDS:
            known = self.store.carrier_name(
                self.cmdr_key, context.market_id, context.name
            )
            if not known:
                known = self.carrier_names.get(str(context.market_id)) or {}
                if not known:
                    known = self.carrier_names.get(context.name.upper()) or {}
            name = str(known.get("name") or "")
            if name:
                context.display_name = name
                self.store.remember_carrier(
                    self.cmdr_key,
                    context.market_id,
                    name,
                    str(known.get("callsign") or "") or context.name,
                )

        self.stations[context.market_id] = context
        if set_current:
            self.current = context

        return self.store.update_target(
            self.cmdr_key,
            context.market_id,
            name=context.name,
            kind=context.kind,
            station_type=context.station_type,
            system=context.system,
            display_name=context.display_name,
        )

    def _station_context(
        self, market_id: Optional[int], callsign: str
    ) -> Optional[StationContext]:
        """Find a known station by market id or callsign."""
        if market_id:
            context = self.stations.get(int(market_id))
            if context is not None:
                return context
        if callsign:
            wanted = callsign.upper()
            for context in self.stations.values():
                if context.name.upper() == wanted:
                    return context
        return None

    def _carrier_target_ids(
        self, market_id: Optional[int], callsign: str
    ) -> set[int]:
        """Active carrier targets for a market id or callsign."""
        ids: set[int] = set()
        if market_id:
            wanted_id = int(market_id)
            if self.store.target_kind(self.cmdr_key, wanted_id) in CARRIER_KINDS:
                ids.add(wanted_id)
        if callsign:
            wanted = callsign.upper()
            for target in self.store.targets(self.cmdr_key):
                if target.kind in CARRIER_KINDS and target.name.upper() == wanted:
                    ids.add(target.market_id)
        return ids

    def _note_carrier_name(self, info: Optional[Dict[str, Any]]) -> bool:
        if not info:
            return False
        market_id = info.get("market_id")
        name = str(info.get("name") or "").strip()
        callsign = str(info.get("callsign") or "").strip()
        if not name:
            return False

        context = self._station_context(market_id, callsign)
        target_ids = self._carrier_target_ids(market_id, callsign)

        if context is not None:
            market_id = market_id or context.market_id
            callsign = callsign or context.name
        elif not market_id and target_ids:
            market_id = next(iter(target_ids))

        # A drop at a regular station can look like a carrier name ("Fuji
        # City"), so never rename a known non-carrier.
        if context is not None and context.kind not in CARRIER_KINDS and not target_ids:
            return False

        has_carrier = (
            bool(callsign)
            or (context is not None and context.kind in CARRIER_KINDS)
            or bool(target_ids)
        )
        if not has_carrier:
            # Name-only drop at an unknown destination: remember it in memory
            # until docking tells us whether it is a carrier.
            if market_id:
                self.carrier_names[str(int(market_id))] = {
                    "name": name,
                    "callsign": "",
                }
            return False

        record = self.store.remember_carrier(self.cmdr_key, market_id, name, callsign)
        if not record:
            return False

        resolved_id = int(record.get("market_id") or 0)
        resolved_callsign = str(record.get("callsign") or "")
        kind = info.get("kind")
        if kind is None and is_squadron_callsign(resolved_callsign):
            kind = KIND_SQUADRON

        if context is not None and context.kind in CARRIER_KINDS:
            context.display_name = name
            if kind:
                context.kind = kind

        changed = False
        ids = set(target_ids)
        if resolved_id:
            ids.add(resolved_id)
        for target_market_id in ids:
            if self.store.target_kind(self.cmdr_key, target_market_id) not in CARRIER_KINDS:
                continue
            changed |= self.store.update_target(
                self.cmdr_key,
                target_market_id,
                display_name=name,
                name=resolved_callsign or None,
                kind=kind,
            )
        return changed

    # -- deliveries ------------------------------------------------------

    def _context_for(self, market_id: int) -> Optional[StationContext]:
        context = self.stations.get(market_id)
        if context is None and self.current is not None and self.current.market_id == market_id:
            context = self.current
        return context

    def _on_market_sell(
        self, entry: Dict[str, Any], system: Optional[str], station: Optional[str]
    ) -> bool:
        market_id = entry.get("MarketID")
        if market_id is None:
            return False
        try:
            market_id = int(market_id)
        except (TypeError, ValueError):
            return False

        context = self._context_for(market_id)
        if context is None and is_callsign(station):
            # EDMC was started while docked, so we missed the Docked event.
            # A callsign-shaped station name is a reliable carrier hint.
            context = StationContext(
                market_id=market_id,
                name=str(station),
                station_type="",
                kind=KIND_CARRIER,
                system=str(system or ""),
            )
            self.stations[market_id] = context

        if context is None or context.kind not in CARRIER_KINDS:
            # Regular starports and construction sites must not be counted
            # here; construction sites are handled via ColonisationContribution.
            return False

        tons = delivery_tons(entry)
        if tons <= 0:
            return False

        return self.store.add(
            self.cmdr_key,
            self.cmdr_name,
            market_id=market_id,
            name=context.name,
            kind=context.kind,
            tons=tons,
            timestamp=str(entry.get("timestamp") or ""),
            station_type=context.station_type,
            system=context.system or str(system or ""),
            display_name=context.display_name,
        )

    def _on_contribution(
        self, entry: Dict[str, Any], system: Optional[str], station: Optional[str]
    ) -> bool:
        market_id = entry.get("MarketID")
        if market_id is None:
            return False
        try:
            market_id = int(market_id)
        except (TypeError, ValueError):
            return False

        tons = delivery_tons(entry)
        if tons <= 0:
            return False

        context = self._context_for(market_id)
        if context is not None and context.kind == KIND_CONSTRUCTION:
            name = context.name
            system_name = context.system
            station_type = context.station_type
            display_name = context.display_name
        else:
            name = (context.name if context else "") or (station or "") or construction_placeholder(market_id)
            system_name = (context.system if context else "") or str(system or "")
            station_type = context.station_type if context else ""
            display_name = context.display_name if context else ""
            # The event itself proves this is a construction site.
            self.stations[market_id] = StationContext(
                market_id=market_id,
                name=name,
                station_type=station_type,
                kind=KIND_CONSTRUCTION,
                system=system_name,
                display_name=display_name,
            )

        return self.store.add(
            self.cmdr_key,
            self.cmdr_name,
            market_id=market_id,
            name=name,
            kind=KIND_CONSTRUCTION,
            tons=tons,
            timestamp=str(entry.get("timestamp") or ""),
            station_type=station_type,
            system=system_name,
            display_name=display_name,
        )
