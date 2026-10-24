"""Parsing helpers that turn journal entries into haul-tracker facts.

Only fields documented in the Elite Dangerous player journal are used.  The
two events that matter for a delivery are:

* ``MarketSell``              - sold to a fleet or squadron carrier market.
* ``ColonisationContribution``- commodities delivered to a construction site.

Construction sites never emit ``MarketSell`` for deliveries, so using exactly
one event per target type avoids double counting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .model import KIND_CARRIER, KIND_CONSTRUCTION, KIND_FLEET, KIND_SQUADRON

# StationType values seen in real journals.  Construction sites show up as
# either a depot (space or planetary) or, during the very first build, as a
# colonisation ship/port.
STATION_KINDS = {
    "fleetcarrier": KIND_FLEET,
    "squadroncarrier": KIND_SQUADRON,
    "spaceconstructiondepot": KIND_CONSTRUCTION,
    "planetaryconstructiondepot": KIND_CONSTRUCTION,
    "colonisationship": KIND_CONSTRUCTION,
    "colonisationport": KIND_CONSTRUCTION,
}

# Fleet-carrier callsigns look like "T3S-TIE" / "X9K-WTW".  Squadron carriers
# use a four-character identifier such as "0822" or "SCCX" instead.
FLEET_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{3}-[A-Z0-9]{3}$")
SQUADRON_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{4}$")
# SupercruiseDestinationDrop for a carrier reads like "Test Carrier T3S-TIE"
# or, for a squadron carrier, "[SCC] The Knave 0822".
DROP_NAME_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<callsign>(?:[A-Z0-9]{3}-[A-Z0-9]{3}|[A-Z0-9]{4}))$"
)


@dataclass
class StationContext:
    """What we know about the station the commander is currently docked at."""

    market_id: int
    name: str
    station_type: str = ""
    kind: Optional[str] = None
    system: str = ""
    display_name: str = ""


def is_callsign(value: Optional[str]) -> bool:
    """True for a fleet-carrier callsign such as ``T3S-TIE``.

    Four-character squadron identifiers are deliberately not accepted here:
    this check recognises a carrier from the *station name* alone, and a
    short station name could be a regular starport.
    """
    if not value:
        return False
    return bool(FLEET_CALLSIGN_RE.match(str(value).strip().upper()))


def is_squadron_callsign(value: Optional[str]) -> bool:
    """True for a four-character squadron-carrier identifier (``0822``)."""
    if not value:
        return False
    return bool(SQUADRON_CALLSIGN_RE.match(str(value).strip().upper()))


def kind_for_station_type(station_type: Optional[str]) -> Optional[str]:
    if not station_type:
        return None
    return STATION_KINDS.get(str(station_type).strip().lower())


def station_kind(
    station_type: Optional[str], name: Optional[str] = "", services: Any = ()
) -> Optional[str]:
    """Classify a station, correcting the journal's carrier-type ambiguity.

    The game writes ``StationType: "FleetCarrier"`` for squadron carriers as
    well; the ``squadronBank`` service and the four-character callsign give
    them away.
    """
    kind = kind_for_station_type(station_type)
    if kind == KIND_FLEET:
        known_services = {str(service).lower() for service in services or ()}
        if "squadronbank" in known_services or is_squadron_callsign(name):
            return KIND_SQUADRON
    return kind


def station_from_entry(entry: Dict[str, Any]) -> Optional[StationContext]:
    """Build a station context from any entry that carries station identity."""
    market_id = entry.get("MarketID")
    name = entry.get("StationName")
    if market_id is None or not name:
        return None
    try:
        market_id = int(market_id)
    except (TypeError, ValueError):
        return None
    station_type = str(entry.get("StationType") or "")
    return StationContext(
        market_id=market_id,
        name=str(name),
        station_type=station_type,
        kind=station_kind(station_type, name, entry.get("StationServices")),
        system=str(entry.get("StarSystem") or ""),
    )


def delivery_tons(entry: Dict[str, Any]) -> int:
    """Tonnage delivered by a ``MarketSell`` or ``ColonisationContribution``."""
    event = entry.get("event")
    if event == "MarketSell":
        try:
            return max(0, int(entry.get("Count") or 0))
        except (TypeError, ValueError):
            return 0
    if event == "ColonisationContribution":
        total = 0
        for item in entry.get("Contributions") or []:
            if not isinstance(item, dict):
                continue
            try:
                total += max(0, int(item.get("Amount") or 0))
            except (TypeError, ValueError):
                continue
        return total
    return 0


def carrier_name_from_drop(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``SupercruiseDestinationDrop`` can reveal a carrier's display name.

    The journal writes the carrier's name followed by its callsign, e.g.
    ``"Type": "Test Carrier T3S-TIE"`` or, for a squadron carrier,
    ``"Type": "[SCC] The Knave 0822"``.
    """
    market_id = entry.get("MarketID")
    if market_id is None:
        return None
    match = DROP_NAME_RE.match(str(entry.get("Type") or "").strip())
    if not match:
        return None
    return {
        "market_id": int(market_id),
        "name": match.group("name").strip(),
        "callsign": match.group("callsign").strip(),
    }


def carrier_name_from_stats(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``CarrierStats``/``CarrierNameChanged`` describe the player's carrier."""
    if entry.get("event") not in ("CarrierStats", "CarrierNameChanged"):
        return None
    market_id = entry.get("CarrierID")
    name = entry.get("Name")
    callsign = entry.get("Callsign")
    if market_id is None or not name:
        return None
    kind = None
    if str(entry.get("CarrierType") or "").strip().lower() == "squadroncarrier":
        kind = KIND_SQUADRON
    return {
        "market_id": int(market_id),
        "name": str(name),
        "callsign": str(callsign or ""),
        "kind": kind,
    }
