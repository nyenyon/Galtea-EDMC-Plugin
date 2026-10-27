"""Version comparison and the optional GitHub release check."""

from __future__ import annotations

import json
import unittest
import urllib.error

from galtea.update import (
    MAX_RESPONSE_BYTES,
    RELEASE_URL_PREFIX,
    RELEASES_API_URL,
    ReleaseInfo,
    UpdateChecker,
    fetch_latest_release,
    is_newer,
    normalize_version,
    parse_version,
)


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self.data
        return self.data[:size]


class VersionTest(unittest.TestCase):
    def test_normalize_version(self) -> None:
        self.assertEqual(normalize_version("0.6.0"), "0.6.0")
        self.assertEqual(normalize_version("v0.6.0"), "0.6.0")
        self.assertEqual(normalize_version("V1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("v0.6.0-beta"), "0.6.0")
        self.assertEqual(normalize_version("v0.6.0+build"), "0.6.0")
        self.assertIsNone(normalize_version("0.6"))
        self.assertIsNone(normalize_version("latest"))
        self.assertIsNone(normalize_version(None))

    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("v0.6.0"), (0, 6, 0))
        self.assertEqual(parse_version("1.20.3"), (1, 20, 3))
        self.assertIsNone(parse_version("0.6"))

    def test_is_newer(self) -> None:
        self.assertTrue(is_newer("v0.6.0", "0.5.1"))
        self.assertTrue(is_newer("0.5.10", "0.5.9"))
        self.assertFalse(is_newer("0.5.1", "0.5.1"))
        self.assertFalse(is_newer("0.5.0", "0.5.1"))
        self.assertFalse(is_newer("latest", "0.5.1"))
        self.assertFalse(is_newer("0.6.0", ""))


class ReleaseFetchTest(unittest.TestCase):
    def payload(self, **overrides: object) -> dict:
        data = {
            "tag_name": "v0.6.1",
            "html_url": RELEASE_URL_PREFIX + "tag/v0.6.1",
            "draft": False,
            "prerelease": False,
        }
        data.update(overrides)
        return data

    def opener_for(self, payload: object):
        def opener(request, timeout):
            self.assertEqual(request.full_url, RELEASES_API_URL)
            self.assertIn("GalteaHaulTracker/0.6.0", request.get_header("User-agent"))
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        return opener

    def test_fetch_latest_release(self) -> None:
        release = fetch_latest_release(
            "0.6.0", opener=self.opener_for(self.payload())
        )

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.version, "0.6.1")
        self.assertEqual(release.url, RELEASE_URL_PREFIX + "tag/v0.6.1")

    def test_fetch_uses_repository_url_when_github_url_is_unexpected(self) -> None:
        release = fetch_latest_release(
            "0.6.0",
            opener=self.opener_for(
                self.payload(html_url="https://example.invalid/not-a-release")
            ),
        )

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.url, RELEASE_URL_PREFIX + "tag/v0.6.1")

    def test_fetch_ignores_prerelease(self) -> None:
        self.assertIsNone(
            fetch_latest_release(
                "0.6.0", opener=self.opener_for(self.payload(prerelease=True))
            )
        )

    def test_fetch_ignores_draft(self) -> None:
        self.assertIsNone(
            fetch_latest_release(
                "0.6.0", opener=self.opener_for(self.payload(draft=True))
            )
        )

    def test_fetch_ignores_invalid_tag(self) -> None:
        self.assertIsNone(
            fetch_latest_release(
                "0.6.0", opener=self.opener_for(self.payload(tag_name="latest"))
            )
        )

    def test_fetch_rejects_oversized_response(self) -> None:
        data = b"x" * (MAX_RESPONSE_BYTES + 1)

        def opener(request, timeout):
            return FakeResponse(data)

        self.assertIsNone(fetch_latest_release("0.6.0", opener=opener))

    def test_fetch_returns_none_on_network_error(self) -> None:
        def opener(request, timeout):
            raise urllib.error.URLError("offline")

        self.assertIsNone(fetch_latest_release("0.6.0", opener=opener))

    def test_fetch_returns_none_on_invalid_json(self) -> None:
        def opener(request, timeout):
            return FakeResponse(b"{not json")

        self.assertIsNone(fetch_latest_release("0.6.0", opener=opener))


class FakeThread:
    """Thread stand-in that runs its target only when the test says so."""

    def __init__(self, target):
        self.target = target
        self.alive = False

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive


class BoomThread(FakeThread):
    def start(self):
        raise RuntimeError("cannot start")


NEWER = ReleaseInfo("9.9.9", RELEASE_URL_PREFIX + "tag/v9.9.9")
SAME = ReleaseInfo("0.6.1", RELEASE_URL_PREFIX + "tag/v0.6.1")


class UpdateCheckerTest(unittest.TestCase):
    def make(self, enabled=True, fetch=lambda version: NEWER, thread_cls=FakeThread):
        self.state = {"enabled": enabled}
        self.threads = []

        def factory(target):
            thread = thread_cls(target)
            self.threads.append(thread)
            return thread

        return UpdateChecker(
            "0.6.1",
            lambda: self.state["enabled"],
            fetch=fetch,
            thread_factory=factory,
        )

    def test_start_skips_when_closed_or_disabled(self) -> None:
        checker = self.make()
        checker.closed = True
        self.assertEqual(checker.start(), "skipped")
        checker.closed = False
        self.state["enabled"] = False
        self.assertEqual(checker.start(), "skipped")

    def test_manual_check_works_while_disabled(self) -> None:
        checker = self.make(enabled=False)
        self.assertEqual(checker.start(manual=True), "started")
        self.assertTrue(checker.manual)

    def test_start_while_busy_reports_running(self) -> None:
        checker = self.make()
        self.assertEqual(checker.start(), "started")
        self.assertEqual(checker.start(), "running")
        self.assertEqual(checker.start(manual=True), "running")

    def test_start_reports_thread_failure(self) -> None:
        checker = self.make(thread_cls=BoomThread)
        self.assertEqual(checker.start(manual=True), "failed")
        self.assertIsNone(checker.thread)
        self.assertFalse(checker.manual)

    def test_worker_uses_current_version(self) -> None:
        seen = []

        def fetch(version):
            seen.append(version)
            return NEWER

        checker = self.make(fetch=fetch)
        checker.start()
        self.threads[-1].target()
        self.assertIs(checker.queue.get_nowait(), NEWER)
        self.assertEqual(seen, ["0.6.1"])

    def test_worker_converts_failures_to_none(self) -> None:
        def fetch(version):
            raise RuntimeError("boom")

        checker = self.make(fetch=fetch)
        checker.start()
        self.threads[-1].target()
        self.assertIsNone(checker.queue.get_nowait())

    def test_auto_update_sets_info(self) -> None:
        checker = self.make()
        checker.start()
        self.assertEqual(checker.apply_result(NEWER), ("update", False))
        self.assertEqual(checker.info, NEWER)
        self.assertFalse(checker.info_from_manual)

    def test_manual_update_marks_info_as_manual(self) -> None:
        checker = self.make()
        checker.start(manual=True)
        self.assertEqual(checker.apply_result(NEWER), ("update", True))
        self.assertTrue(checker.info_from_manual)

    def test_manual_up_to_date_clears_previous_info(self) -> None:
        checker = self.make()
        checker.info = NEWER
        checker.start(manual=True)
        self.assertEqual(checker.apply_result(SAME), ("uptodate", True))
        self.assertIsNone(checker.info)
        self.assertFalse(checker.info_from_manual)

    def test_manual_failure_keeps_previous_info(self) -> None:
        checker = self.make()
        checker.info = NEWER
        checker.info_from_manual = True
        checker.start(manual=True)
        self.assertEqual(checker.apply_result(None), ("failed", True))
        self.assertEqual(checker.info, NEWER)

    def test_auto_failure_is_silent_idle(self) -> None:
        checker = self.make()
        checker.start()
        self.assertEqual(checker.apply_result(None), ("idle", False))
        self.assertIsNone(checker.info)

    def test_result_while_auto_disabled_drops_auto_info(self) -> None:
        checker = self.make()
        checker.info = NEWER
        checker.start()
        self.state["enabled"] = False
        self.assertEqual(checker.apply_result(NEWER), ("disabled", False))
        self.assertIsNone(checker.info)

    def test_result_while_auto_disabled_keeps_manual_info(self) -> None:
        checker = self.make()
        checker.info = NEWER
        checker.info_from_manual = True
        checker.start()
        self.state["enabled"] = False
        self.assertEqual(checker.apply_result(NEWER), ("disabled", False))
        self.assertEqual(checker.info, NEWER)

    def test_abandon_resets_worker_state(self) -> None:
        checker = self.make()
        checker.start(manual=True)
        self.assertTrue(checker.busy)
        self.assertTrue(checker.abandon())
        self.assertFalse(checker.busy)
        self.assertFalse(checker.manual)


if __name__ == "__main__":
    unittest.main()
