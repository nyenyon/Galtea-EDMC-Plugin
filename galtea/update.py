"""Optional check for newer GitHub releases.

The module has no Tk or EDMC imports so it can be tested without a running
client.  It only fetches the latest public release metadata; it never
downloads or installs anything.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

RELEASES_API_URL = (
    "https://api.github.com/repos/nyenyon/Galtea-EDMC-Plugin/releases/latest"
)
RELEASE_URL_PREFIX = "https://github.com/nyenyon/Galtea-EDMC-Plugin/releases/"
MAX_RESPONSE_BYTES = 256 * 1024

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseInfo:
    """The latest stable release found on GitHub."""

    version: str
    url: str


def normalize_version(value: Any) -> Optional[str]:
    """Return ``major.minor.patch`` for a release tag, or ``None``."""
    match = _VERSION_RE.match(str(value or "").strip())
    if match is None:
        return None
    return ".".join(str(int(part)) for part in match.groups())


def parse_version(value: Any) -> Optional[Tuple[int, int, int]]:
    """Parse a version tag into a comparable tuple."""
    normalized = normalize_version(value)
    if normalized is None:
        return None
    major, minor, patch = normalized.split(".")
    return int(major), int(minor), int(patch)


def is_newer(latest: Any, current: Any) -> bool:
    """True when *latest* is a valid version newer than *current*."""
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    if latest_parts is None or current_parts is None:
        return False
    return latest_parts > current_parts


def _release_url(payload: dict, tag: Any) -> str:
    """Use GitHub's URL when it stays inside this repository, else build one."""
    url = payload.get("html_url")
    if isinstance(url, str) and url.startswith(RELEASE_URL_PREFIX):
        return url
    return RELEASE_URL_PREFIX + "tag/" + urllib.parse.quote(str(tag), safe="")


def fetch_latest_release(
    current_version: str,
    *,
    url: str = RELEASES_API_URL,
    timeout: float = 5.0,
    opener: Optional[Callable[..., Any]] = None,
) -> Optional[ReleaseInfo]:
    """Fetch the latest stable GitHub release, or return ``None`` on failure.

    ``opener`` is injectable for tests.  Any network, TLS, HTTP, size or JSON
    problem is treated as "no update information" and never reaches the UI.
    """
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"GalteaHaulTracker/{current_version or 'unknown'}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    open_url = opener or urllib.request.urlopen

    try:
        with open_url(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            logger.debug("GitHub release response exceeded %s bytes", MAX_RESPONSE_BYTES)
            return None

        payload = json.loads(data.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if payload.get("draft") or payload.get("prerelease"):
            return None

        tag = payload.get("tag_name")
        version = normalize_version(tag)
        if version is None:
            logger.debug("Ignoring release with invalid tag: %r", tag)
            return None
        return ReleaseInfo(version=version, url=_release_url(payload, tag))
    except Exception as exc:  # noqa: BLE001 - update checks must never break EDMC
        logger.debug("GitHub release check failed: %s", exc)
        return None


class UpdateChecker:
    """State machine for the optional GitHub release check.  No Tk.

    ``start`` runs one fetch in a worker thread; ``apply_result`` folds a
    finished check into ``info`` and returns the action the UI should show.
    ``thread_factory`` exists so tests can fake the thread.
    """

    def __init__(
        self,
        current_version: str,
        is_enabled: Callable[[], bool],
        *,
        fetch: Optional[Callable[[str], Optional[ReleaseInfo]]] = None,
        thread_factory: Optional[Callable[[Callable[[], None]], Any]] = None,
    ):
        self.current_version = str(current_version or "")
        self.is_enabled = is_enabled
        self._fetch = fetch or fetch_latest_release
        self._thread_factory = thread_factory
        self.info: Optional[ReleaseInfo] = None
        self.info_from_manual = False
        self.manual = False
        self.thread: Any = None
        self.closed = False
        self.queue: queue.Queue = queue.Queue()

    @property
    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, manual: bool = False) -> str:
        """Kick off one check; returns skipped, running, failed or started."""
        if self.closed:
            return "skipped"
        if not manual and not self.is_enabled():
            return "skipped"
        if self.busy:
            return "running"
        self.manual = manual
        if self._thread_factory is not None:
            thread = self._thread_factory(self._worker)
        else:
            thread = threading.Thread(
                target=self._worker, name="GalteaUpdateCheck", daemon=True
            )
        self.thread = thread
        try:
            thread.start()
        except RuntimeError:
            self.thread = None
            self.manual = False
            return "failed"
        return "started"

    def _worker(self) -> None:
        try:
            self.queue.put(self._fetch(self.current_version))
        except Exception:  # noqa: BLE001 - a check must never break the plugin
            self.queue.put(None)

    def abandon(self) -> bool:
        """Reset a finished worker that left no result; return manual mode."""
        manual = self.manual
        self.thread = None
        self.manual = False
        return manual

    def apply_result(self, result: Optional[ReleaseInfo]) -> Tuple[str, bool]:
        """Fold one finished check into ``info``.

        Returns the action (``disabled``, ``update``, ``uptodate``, ``failed``
        or ``idle``) and whether the check had been started manually.
        ``failed`` keeps a previously found update; ``idle`` changes nothing.
        """
        manual = self.abandon()
        if not manual and not self.is_enabled():
            if not self.info_from_manual:
                self.info = None
            return "disabled", manual
        if result is not None and is_newer(result.version, self.current_version):
            self.info = result
            self.info_from_manual = manual
            return "update", manual
        if manual:
            if result is not None:
                self.info = None
                self.info_from_manual = False
                return "uptodate", manual
            return "failed", manual
        return "idle", manual
