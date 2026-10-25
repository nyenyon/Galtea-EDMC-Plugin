"""Shared data model for the Galtea haul tracker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Delivery targets we care about.
KIND_FLEET = "fleet_carrier"
KIND_SQUADRON = "squadron_carrier"
KIND_CONSTRUCTION = "construction"
# A carrier whose exact type (fleet or squadron) is not known yet.  This
# happens when EDMC is started while already docked and the journal entry that
# told us the station type has been consumed during the startup catch-up.
KIND_CARRIER = "carrier"

CARRIER_KINDS = frozenset({KIND_FLEET, KIND_SQUADRON, KIND_CARRIER})
TRACKED_KINDS = frozenset({KIND_FLEET, KIND_SQUADRON, KIND_CONSTRUCTION, KIND_CARRIER})

KIND_LABELS = {
    KIND_FLEET: "Fleet carrier",
    KIND_SQUADRON: "Squadron carrier",
    KIND_CONSTRUCTION: "Construction site",
    KIND_CARRIER: "Carrier",
}

# Discord/Sicord handle used in the report command when none is configured.
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


def clean_construction_name(name: str) -> str:
    """Strip the generic construction-site prefix from a station name."""
    text = str(name or "").strip()
    if not text:
        return text
    stripped = _CONSTRUCTION_PREFIX.sub("", text, count=1).strip()
    return stripped or text


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
        """The Discord/Sicord macro that reports this target's tonnage."""
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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Target":
        return cls(
            market_id=int(data.get("market_id") or 0),
            name=str(data.get("name") or ""),
            kind=str(data.get("kind") or KIND_CARRIER),
            station_type=str(data.get("station_type") or ""),
            system=str(data.get("system") or ""),
            display_name=str(data.get("display_name") or ""),
            tons=int(data.get("tons") or 0),
            first_delivery=str(data.get("first_delivery") or ""),
            last_delivery=str(data.get("last_delivery") or ""),
            id=str(data.get("id") or ""),
        )
