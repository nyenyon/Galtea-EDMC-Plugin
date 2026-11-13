"""In-game overlay forwarding to EDMCModernOverlay."""

from __future__ import annotations

import unittest

from galtea import LOGGER_NAME
from galtea.model import KIND_FLEET, Target
from galtea.overlay import (
    AMOUNT_X,
    BASE_X,
    LABEL_LIMIT,
    GameOverlay,
    format_rows,
)


class FakeClient:
    def __init__(self):
        self.messages = []
        self.raw = []
        self.fail = False

    def connect(self):
        pass

    def send_message(self, msgid, text, color, x, y, ttl=4, size="normal"):
        if self.fail:
            raise RuntimeError("overlay busy")
        self.messages.append((msgid, text, color, x, y, ttl, size))

    def send_raw(self, msg):
        if self.fail:
            raise RuntimeError("overlay busy")
        self.raw.append(msg)


def make(fail=False, registrar=None):
    fake = None if fail else FakeClient()
    groups = []

    def fake_registrar():
        groups.append(True)
        return True

    overlay = GameOverlay(
        client_factory=lambda: fake,
        group_registrar=registrar or fake_registrar,
    )
    return overlay, fake, groups


def haul(name: str, tons: int) -> Target:
    return Target(market_id=1, name=name, kind=KIND_FLEET, tons=tons)


class FormatRowsTest(unittest.TestCase):
    def test_empty_state(self) -> None:
        self.assertEqual(
            format_rows([]), [("No deliveries tracked", ""), ("Total:", "0 t")]
        )

    def test_three_rows_plus_total(self) -> None:
        rows = format_rows(
            [
                haul("T3S-TIE", 2640),
                haul("Shakespeare Point", 1300),
                haul("Kruger Depot", 700),
                haul("Fourth Site", 500),
            ]
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0], ("T3S-TIE", "2,640 t"))
        self.assertEqual(rows[2], ("Kruger Depot", "700 t"))
        # the total counts every target, not only the visible rows
        self.assertEqual(rows[3], ("Total:", "5,140 t"))

    def test_long_label_is_truncated(self) -> None:
        rows = format_rows([haul("X" * 80, 10)])
        self.assertEqual(rows[0][0], "X" * (LABEL_LIMIT - 1) + "\u2026")


class GameOverlayTest(unittest.TestCase):
    ROWS = [("Row A", "1,320 t"), ("Row B", "660 t"), ("Row C", "70 t"), ("Total:", "1,750 t")]

    def test_update_sends_names_and_amounts(self) -> None:
        overlay, fake, groups = make()
        overlay.update(self.ROWS)
        self.assertEqual(len(fake.messages), 8)
        self.assertEqual(
            [msg[0] for msg in fake.messages[::2]],
            [
                "galtea-haul-name-0",
                "galtea-haul-name-1",
                "galtea-haul-name-2",
                "galtea-haul-name-total",
            ],
        )
        self.assertEqual(
            [msg[0] for msg in fake.messages[1::2]],
            [
                "galtea-haul-tons-0",
                "galtea-haul-tons-1",
                "galtea-haul-tons-2",
                "galtea-haul-tons-total",
            ],
        )
        self.assertEqual(fake.messages[0][1], "Row A")
        self.assertEqual(fake.messages[1][1], "1,320 t")
        # amounts sit in their own column, names at the left edge, same line
        self.assertEqual(fake.messages[0][3], BASE_X)
        self.assertEqual(fake.messages[1][3], AMOUNT_X)
        self.assertEqual(fake.messages[0][4], fake.messages[1][4])
        for msg in fake.messages:
            self.assertEqual(msg[2], "#ff8c00")
            self.assertEqual(msg[5], 120)
        # the group is announced exactly once, not on every update
        overlay.update(self.ROWS)
        self.assertEqual(len(groups), 1)

    def test_missing_amount_only_sends_the_name(self) -> None:
        overlay, fake, _ = make()
        overlay.update(format_rows([]))
        self.assertEqual([msg[0] for msg in fake.messages], [
            "galtea-haul-name-0",
            "galtea-haul-name-total",
            "galtea-haul-tons-total",
        ])

    def test_reset_allows_retry_after_failure(self) -> None:
        attempts = []

        def factory():
            attempts.append(True)
            if len(attempts) == 1:
                raise ImportError("EDMCModernOverlay not installed yet")
            return FakeClient()

        overlay = GameOverlay(client_factory=factory, group_registrar=lambda: True)
        overlay.update(self.ROWS)
        self.assertTrue(overlay._client_failed)

        overlay.reset()
        overlay.update(self.ROWS)
        self.assertFalse(overlay._client_failed)
        self.assertEqual(len(attempts), 2)

    def test_group_registration_is_retried_until_it_succeeds(self) -> None:
        calls = []

        def registrar():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("overlay plugin not ready yet")
            return True

        overlay, fake, _ = make(registrar=registrar)
        overlay.update(self.ROWS)
        # the failure is only logged, the rows are sent anyway
        self.assertEqual(len(fake.messages), 8)

        overlay.update(self.ROWS)
        overlay.update(self.ROWS)
        # second attempt succeeded, no further calls after that
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(fake.messages), 24)

    def test_a_failed_group_announcement_is_logged_once(self) -> None:
        def broken_registrar():
            raise ImportError("no overlay_plugin module")

        overlay, fake, _ = make(registrar=broken_registrar)
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            overlay.update(self.ROWS)
            overlay.update(self.ROWS)
        self.assertEqual(len(logs.records), 1)
        # the rows are still sent, only the group stays unlisted
        self.assertEqual(len(fake.messages), 16)

    def test_reset_forgets_the_registration(self) -> None:
        overlay, _, groups = make()
        overlay.update(self.ROWS)
        self.assertEqual(len(groups), 1)
        overlay.reset()
        overlay.update(self.ROWS)
        self.assertEqual(len(groups), 2)

    def test_update_sends_at_most_three_rows_plus_total(self) -> None:
        overlay, fake, _ = make()
        overlay.update([(f"Row {i}", f"{i} t") for i in range(6)] + [("Total:", "1 t")])
        self.assertEqual(len(fake.messages), 8)

    def test_unavailable_plugin_is_skipped_silently(self) -> None:
        overlay, _, _ = make(fail=True)
        overlay.update(self.ROWS)
        overlay.hide()
        self.assertTrue(overlay._client_failed)

    def test_is_available_reports_a_missing_plugin(self) -> None:
        overlay, _, _ = make(fail=True)
        self.assertFalse(overlay.is_available())
        # not remembered: installing the plugin later must still work
        self.assertFalse(overlay._client_failed)

    def test_is_available_survives_a_broken_import(self) -> None:
        def broken():
            raise ImportError("no overlay module")

        overlay = GameOverlay(client_factory=broken, group_registrar=lambda: True)
        self.assertFalse(overlay.is_available())

    def test_is_available_with_the_plugin(self) -> None:
        overlay, _, _ = make()
        self.assertTrue(overlay.is_available())

    def test_a_failed_probe_is_logged_once(self) -> None:
        def broken():
            raise ImportError("no overlay module")

        overlay = GameOverlay(client_factory=broken, group_registrar=lambda: True)
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            self.assertFalse(overlay.is_available())
            self.assertFalse(overlay.is_available())
        self.assertEqual(len(logs.records), 1)

    def test_hide_without_a_client_does_not_connect(self) -> None:
        calls = []

        def broken():
            calls.append(True)
            raise ImportError("no overlay module")

        overlay = GameOverlay(client_factory=broken, group_registrar=lambda: True)
        overlay.hide()
        self.assertEqual(calls, [])

    def test_send_failure_is_swallowed(self) -> None:
        overlay, fake, _ = make()
        fake.fail = True
        overlay.update(self.ROWS)
        overlay.hide()
        fake.fail = False
        overlay.update(self.ROWS)
        self.assertEqual(len(fake.messages), 8)

    def test_shorter_summary_clears_the_leftover_rows(self) -> None:
        overlay, fake, _ = make()
        overlay.update(self.ROWS)
        overlay.update(format_rows([]))
        # every slot the second update did not use is removed, so the old
        # haul rows do not linger until their TTL runs out
        self.assertEqual(
            [msg["id"] for msg in fake.raw],
            [
                "galtea-haul-name-1",
                "galtea-haul-name-2",
                "galtea-haul-tons-0",
                "galtea-haul-tons-1",
                "galtea-haul-tons-2",
            ],
        )

    def test_hide_clears_every_payload_id(self) -> None:
        overlay, fake, _ = make()
        overlay.update(self.ROWS)  # connect first; nothing to clear before that
        overlay.hide()
        self.assertEqual(
            [msg["id"] for msg in fake.raw],
            [
                "galtea-haul-name-0",
                "galtea-haul-name-1",
                "galtea-haul-name-2",
                "galtea-haul-name-total",
                "galtea-haul-tons-0",
                "galtea-haul-tons-1",
                "galtea-haul-tons-2",
                "galtea-haul-tons-total",
            ],
        )

    def test_empty_update_is_ignored(self) -> None:
        overlay, fake, _ = make()
        overlay.update([])
        self.assertEqual(fake.messages, [])


if __name__ == "__main__":
    unittest.main()
