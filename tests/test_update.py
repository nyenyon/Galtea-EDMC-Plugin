"""Version comparison and the optional GitHub release check."""

from __future__ import annotations

import json
import unittest
import urllib.error

from galtea.update import (
    MAX_RESPONSE_BYTES,
    RELEASE_URL_PREFIX,
    RELEASES_API_URL,
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


if __name__ == "__main__":
    unittest.main()
