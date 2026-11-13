"""Optional in-game status display via the EDMCModernOverlay plugin.

EDMCModernOverlay (installed separately) renders simple text inside the
game window; position, colours and background are configured in its own
Overlay Controller.  This module only formats and forwards our haul
summary and fails silently whenever the plugin is not installed or not
accepting messages.  No Tk here, like the other non-UI modules.

Payload scheme (documented "plugin-group-payload" naming): the ``galtea-``
prefix marks payloads as ours.  Names and tonnages share **one** plugin
group, so the controller shows a single overlay; the group is declared
with no background/border, the controller draws any styling.
"""

import logging
from typing import List, Tuple

from . import LOGGER_NAME
from .model import Target, format_number, short_text

logger = logging.getLogger(LOGGER_NAME)

PLUGIN_NAME = "Galtea Haul Tracker"
PLUGIN_PREFIX = "galtea-"
# One plugin group holds every payload, so the controller shows a single
# "Galtea Haul Tracker" overlay.
GROUP_PREFIX = "galtea-haul-"
ROW_COUNT = 3
LABEL_LIMIT = 28
TEXT_COLOR = "#ff8c00"
BASE_X = 20
# Fixed column for the tonnage inside the same overlay.  Names are cut to
# LABEL_LIMIT characters and the column starts a little further right, so a
# full-length name still leaves a visible gap before its tonnage.  A name
# made of very wide letters can still get close, because character count is
# not width.  EDMCModernOverlay justifies whole groups, not columns, so this
# fixed left edge is as close to an aligned number column as one group allows.
AMOUNT_X = 245
BASE_Y = 100
LINE_HEIGHT = 26
# Modern overlay entries expire after this many seconds; the UI heartbeats
# at half this interval, so the display stays while EDMC runs.
TTL_S = 120

NAME_IDS: Tuple[str, ...] = tuple(
    f"{GROUP_PREFIX}name-{index}" for index in range(ROW_COUNT)
) + (f"{GROUP_PREFIX}name-total",)
TONS_IDS: Tuple[str, ...] = tuple(
    f"{GROUP_PREFIX}tons-{index}" for index in range(ROW_COUNT)
) + (f"{GROUP_PREFIX}tons-total",)


def _import_client():
    import edmcoverlay

    return edmcoverlay.Overlay()


def _register_group() -> bool:
    """Announce our single plugin group to EDMCModernOverlay.

    ``define_plugin_group`` is the documented way to make our payloads a
    positionable group in the Overlay Controller.  One group only, so the
    controller lists a single "Galtea Haul Tracker" overlay; the number
    column inside it is positioned by the payload coordinates.  Not
    available on legacy overlays, hence the caller's try/except.
    """
    from overlay_plugin import overlay_api

    return bool(
        overlay_api.define_plugin_group(
            plugin_name=PLUGIN_NAME,
            plugin_matching_prefixes=[PLUGIN_PREFIX],
            plugin_group_name=PLUGIN_NAME,
            plugin_group_prefixes=[GROUP_PREFIX],
            payload_justification="left",
            plugin_group_background_color="none",
            plugin_group_border_color="none",
        )
    )


def format_rows(targets: List[Target]) -> List[Tuple[str, str]]:
    """Overlay text as (name, amount) pairs: up to ROW_COUNT rows plus total."""
    if not targets:
        return [("No deliveries tracked", ""), ("Total:", "0 t")]
    rows = [
        (short_text(target.label, LABEL_LIMIT), f"{format_number(target.tons)} t")
        for target in targets[:ROW_COUNT]
    ]
    rows.append(
        ("Total:", f"{format_number(sum(target.tons for target in targets))} t")
    )
    return rows


class GameOverlay:
    """Formats the haul summary and forwards it to EDMCModernOverlay."""

    def __init__(self, client_factory=None, group_registrar=None):
        self._client_factory = client_factory or _import_client
        self._group_registrar = group_registrar or _register_group
        self._client = None
        self._client_failed = False
        self._probe_failed = False
        self._group_registered = False
        self._group_warned = False

    def _get_client(self):
        """Return a connected client, or None while the plugin is missing.

        The import is retried on every call, so one failed connection does
        not disable the overlay for the rest of the session.
        """
        if self._client is not None:
            return self._client
        try:
            client = self._client_factory()
            client.connect()
        except Exception:
            if not self._client_failed:
                logger.info(
                    "EDMCModernOverlay not available; the in-game display "
                    "stays off"
                )
                self._client_failed = True
            return None
        self._client = client
        self._client_failed = False
        return self._client

    def _ensure_group(self) -> None:
        """Announce our plugin group, retrying until the overlay is ready.

        EDMCModernOverlay only accepts groups once its own plugin has
        started, which can be after our first payload, so a single attempt
        is not enough.
        """
        if self._group_registered:
            return
        try:
            self._group_registrar()
            self._group_registered = True
        except Exception:
            # Retried on every update (the overlay may still be starting),
            # but the traceback is worth reading only once.
            if not self._group_warned:
                logger.info(
                    "could not announce the overlay group yet; the entries "
                    "are shown but stay unlisted in the Overlay Controller "
                    "until it succeeds",
                    exc_info=True,
                )
                self._group_warned = True

    def is_available(self) -> bool:
        """True when the EDMCModernOverlay client module is importable.

        Used by the settings page to grey out the switch.  EDMC adds a
        plugin's folder to ``sys.path`` when it loads the plugin at
        start-up, so a plugin installed or enabled later needs a restart.
        """
        if self._client is not None:
            return True
        try:
            return self._client_factory() is not None
        except Exception:
            if not self._probe_failed:
                logger.info(
                    "EDMCModernOverlay cannot be imported in this EDMC "
                    "session; install or enable it, then restart EDMC",
                    exc_info=True,
                )
                self._probe_failed = True
            return False

    def reset(self) -> None:
        """Drop the cached client and the logged warning.

        Called when the user switches the setting on: the overlay may have
        been installed or enabled after EDMC started.
        """
        self._client = None
        self._client_failed = False
        self._probe_failed = False
        self._group_registered = False
        self._group_warned = False

    def update(self, rows: List[Tuple[str, str]]) -> None:
        """Send the summary rows (name plus amount) to the overlay."""
        client = self._get_client()
        if client is None:
            return
        self._ensure_group()
        if not rows:
            return
        try:
            limited = rows[: ROW_COUNT + 1]
            used = set()
            for index, (name, amount) in enumerate(limited):
                # The summary line always uses the "-total" slots, no matter
                # how many rows precede it (the empty state has just one).
                total_row = index == len(limited) - 1
                name_id = NAME_IDS[-1] if total_row else NAME_IDS[index]
                tons_id = TONS_IDS[-1] if total_row else TONS_IDS[index]
                y = BASE_Y + index * LINE_HEIGHT
                client.send_message(
                    name_id,
                    name,
                    TEXT_COLOR,
                    BASE_X,
                    y,
                    ttl=TTL_S,
                    size="normal",
                )
                used.add(name_id)
                if amount:
                    client.send_message(
                        tons_id,
                        amount,
                        TEXT_COLOR,
                        AMOUNT_X,
                        y,
                        ttl=TTL_S,
                        size="normal",
                    )
                    used.add(tons_id)
            # Rows from a longer summary would stay visible until their TTL
            # runs out, so remove the slots this update did not use.
            for msgid in NAME_IDS + TONS_IDS:
                if msgid not in used:
                    client.send_raw({"id": msgid})
        except Exception:
            logger.warning("could not update the in-game overlay", exc_info=True)

    def hide(self) -> None:
        """Clear our entries in the game window.

        Only a client we already hold can have sent something; asking for
        one here would import the overlay (and log) at every EDMC exit.
        """
        client = self._client
        if client is None:
            return
        try:
            for msgid in NAME_IDS + TONS_IDS:
                # Documented way to remove one payload by its id.
                client.send_raw({"id": msgid})
        except Exception:
            logger.warning("could not clear the in-game overlay", exc_info=True)
