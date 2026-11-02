"""Shared data model for the Galtea haul tracker."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Delivery targets we care about.
KIND_FLEET = "fleet_carrier"
KIND_SQUADRON = "squadron_carrier"
KIND_CONSTRUCTION = "construction"
# A carrier whose exact type (fleet or squadron) is not known yet.  This
# happens when EDMC is started while already docked and the journal entry that
# told us the station type has been consumed during the startup catch-up.
KIND_CARRIER = "carrier"

CARRIER_KINDS = frozenset({KIND_FLEET, KIND_SQUADRON, KIND_CARRIER})

KIND_LABELS = {
    KIND_FLEET: "Fleet carrier",
    KIND_SQUADRON: "Squadron carrier",
    KIND_CONSTRUCTION: "Construction site",
    KIND_CARRIER: "Carrier",
}

# Fallback station name before we ever saw the site itself; the details view
# replaces it once a Docked/Location event brings the real name.
CONSTRUCTION_PLACEHOLDER_PREFIX = "Construction site "


def construction_placeholder(market_id: Any) -> str:
    """The fallback name stored for an unseen construction site."""
    return f"{CONSTRUCTION_PLACEHOLDER_PREFIX}{market_id}"


def is_construction_placeholder(name: Any) -> bool:
    """True for a fallback name produced by ``construction_placeholder``."""
    return str(name or "").startswith(CONSTRUCTION_PLACEHOLDER_PREFIX)

# Discord handle used in the report command when none is configured.
# A placeholder, so reports are never accidentally credited to a real user.
DEFAULT_DISCORD_USER = "@yourdiscordname"


def normalize_discord_user(value: Any) -> str:
    """Return a Discord handle with a leading ``@``; empty stays empty."""
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("@") else f"@{text}"


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string, matching journal timestamps."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_number(value: int) -> str:
    """Format tons with thousands separators."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


# Construction sites are named "<kind> Construction Site: <future station>"
# in the journal.  Only the future station name is interesting.
_CONSTRUCTION_PREFIX = re.compile(
    r"^\s*(?:(?:orbital|planetary|space|surface)\s+)?construction\s+(?:site|depot)\s*:\s*",
    re.IGNORECASE,
)

# The colonisation ship is the only site whose StationName is a localisation
# token, e.g. "$EXT_PANEL_ColonisationShip; Volk Reach" or
# "$EXT_PANEL_ColonisationShip:#index=2; <name>" (same forms EDMC matches).
_COLONISATION_TOKEN_PREFIX = re.compile(
    r"^\s*\$EXT_PANEL_ColonisationShip(?::#index=\d+)?;\s*", re.IGNORECASE
)


def clean_construction_name(name: str) -> str:
    """Strip the journal's construction-site prefix or colonisation token."""
    text = str(name or "").strip()
    if not text:
        return text
    if _COLONISATION_TOKEN_PREFIX.match(text):
        # What follows the token is the settlement's primary-port name.
        stripped = _COLONISATION_TOKEN_PREFIX.sub("", text, count=1).strip()
        return stripped or "System Colonisation Ship"
    stripped = _CONSTRUCTION_PREFIX.sub("", text, count=1).strip()
    return stripped or text


def clean_carrier_name(name: Any) -> str:
    """Trim a carrier display name.

    Squadron carrier destination drops arrive as ``Name | CALLSIGN``; the
    pipe is punctuation of the journal line, not part of the name.  Older
    plugin versions cached such names verbatim, so this also sanitises
    cached values on read instead of migrating files.
    """
    return str(name or "").strip().strip("|").strip()


# Gaps between two landings longer than 3x their median (but at least this
# many seconds) count as player pauses, not as round trips.  The floor
# matters because some delivery runs are simply long.
ROUNDTRIP_PAUSE_FLOOR_S = 30 * 60


def round_trip_summary(
    deliveries: List[Dict[str, Any]],
) -> Optional[Tuple[int, int, int]]:
    """Average round-trip seconds and the trips used/seen, or ``None``.

    One round trip is the gap between two consecutive delivery timestamps.
    Gaps above ``max(3 * median, ROUNDTRIP_PAUSE_FLOOR_S)`` are treated as
    pauses (the player stepped away) and dropped from the average.
    """
    moments = []
    for entry in deliveries or []:
        stamp = str(entry.get("timestamp") or "")
        if not stamp:
            continue
        text = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
        try:
            moments.append(datetime.fromisoformat(text))
        except ValueError:
            continue
    try:
        moments.sort()
        gaps = sorted(
            (later - earlier).total_seconds()
            for earlier, later in zip(moments, moments[1:])
        )
    except TypeError:  # mixed naive/aware timestamps
        return None
    if len(gaps) < 2:
        return None
    middle = len(gaps) // 2
    median = gaps[middle] if len(gaps) % 2 else (gaps[middle - 1] + gaps[middle]) / 2
    cutoff = max(3 * median, ROUNDTRIP_PAUSE_FLOOR_S)
    used = [gap for gap in gaps if gap <= cutoff]
    if not used:
        return None
    return int(round(sum(used) / len(used))), len(used), len(gaps)


def format_duration(seconds: int) -> str:
    """Human duration: ``6 min 10 s`` or ``1 h 2 min``."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"


def round_trip_text(deliveries: List[Dict[str, Any]]) -> str:
    """One-line average round trip for the delivery log, or ``""``."""
    summary = round_trip_summary(deliveries)
    if summary is None:
        return ""
    avg, used, total = summary
    text = f"Avg round trip: {format_duration(avg)}"
    if used < total:
        skipped = total - used
        word = "pause" if skipped == 1 else "pauses"
        text += f" ({used} of {total} trips, {skipped} {word} ignored)"
    else:
        text += f" ({total} trips)"
    return text


def format_timestamp(value: str) -> str:
    """Turn a journal timestamp into a short local time string for display."""
    if not value:
        return "-"
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if moment.tzinfo is None:
        return moment.strftime("%Y-%m-%d %H:%M")
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


@dataclass
class Target:
    """One place deliveries have been made to, with accumulated tonnage."""

    market_id: int
    name: str
    kind: str
    station_type: str = ""
    system: str = ""
    display_name: str = ""
    tons: int = 0
    first_delivery: str = ""
    last_delivery: str = ""
    # Unique id of this delivery batch.  The same market can have several
    # active batches after a reported one has been restored.
    id: str = ""
    # One entry per individual delivery: {"tons": int, "timestamp": str}.
    # Older files have no log; the first new delivery starts it.
    deliveries: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Human readable name, including the callsign when a name is known."""
        name = self.name or f"Market {self.market_id}"
        if self.kind == KIND_CONSTRUCTION:
            name = clean_construction_name(name)
        if self.display_name and self.display_name != self.name:
            return f"{self.display_name} ({self.name})"
        return name

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, "Unknown")

    def report_command(self, user: Optional[str] = DEFAULT_DISCORD_USER) -> str:
        """The Discord macro that reports this target's tonnage."""
        name = normalize_discord_user(user) or DEFAULT_DISCORD_USER
        return f"/addscore user:{name} points:{int(self.tons)} comment:{self.label}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_id": int(self.market_id),
            "name": self.name,
            "kind": self.kind,
            "station_type": self.station_type,
            "system": self.system,
            "display_name": self.display_name,
            "tons": int(self.tons),
            "first_delivery": self.first_delivery,
            "last_delivery": self.last_delivery,
            "id": self.id,
            "deliveries": [dict(entry) for entry in self.deliveries],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Target":
        return cls(
            market_id=int(data.get("market_id") or 0),
            name=str(data.get("name") or ""),
            kind=str(data.get("kind") or KIND_CARRIER),
            station_type=str(data.get("station_type") or ""),
            system=str(data.get("system") or ""),
            display_name=clean_carrier_name(data.get("display_name")),
            tons=int(data.get("tons") or 0),
            first_delivery=str(data.get("first_delivery") or ""),
            last_delivery=str(data.get("last_delivery") or ""),
            id=str(data.get("id") or ""),
            deliveries=[
                entry
                for entry in (data.get("deliveries") or [])
                if isinstance(entry, dict)
            ],
        )
