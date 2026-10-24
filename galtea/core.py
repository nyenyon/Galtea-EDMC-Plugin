"""Event routing: turn live journal entries into accumulated tonnage."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .journal import (
    StationContext,
    carrier_name_from_drop,
    carrier_name_from_stats,
    delivery_tons,
    is_callsign,
    station_from_entry,
)
from .model import CARRIER_KINDS, KIND_CARRIER, KIND_CONSTRUCTION
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
        self.carrier_names: Dict[int, Dict[str, str]] = {}
        self.cmdr_key: str = ""
        self.cmdr_name: str = ""

    # -- commander -------------------------------------------------------

    def _select_commander(self, cmdr: Optional[str], fid: Optional[str]) -> bool:
        key = str(fid) if fid else (str(cmdr) if cmdr else "unknown")
        if key == self.cmdr_key:
            if cmdr and cmdr != self.cmdr_name:
                self.cmdr_name = str(cmdr)
            return False
        self.cmdr_key = key
        self.cmdr_name = str(cmdr or "")
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
        known = self.carrier_names.get(context.market_id)
        if known:
            context.display_name = known.get("name", "")

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

    def _note_carrier_name(self, info: Optional[Dict[str, Any]]) -> bool:
        if not info:
            return False
        market_id = int(info["market_id"])
        name = str(info.get("name") or "")
        callsign = str(info.get("callsign") or "")
        if not name:
            return False

        self.carrier_names[market_id] = {"name": name, "callsign": callsign}
        context = self.stations.get(market_id)
        if context is not None:
            context.display_name = name

        return self.store.update_target(
            self.cmdr_key, market_id, display_name=name, name=callsign or None
        )

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
            name = (context.name if context else "") or (station or "") or f"Construction site {market_id}"
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
