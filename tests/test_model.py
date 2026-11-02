"""The Discord report command generated for a target."""

from __future__ import annotations

import unittest

from datetime import datetime, timedelta, timezone

from galtea.model import (
    DEFAULT_DISCORD_USER,
    KIND_CONSTRUCTION,
    KIND_FLEET,
    KIND_SQUADRON,
    Target,
    clean_construction_name,
    format_duration,
    normalize_discord_user,
    round_trip_summary,
    round_trip_text,
)


def deliveries_from_gaps(gaps_s, tons=1320):
    """Delivery log whose consecutive timestamps differ by the given gaps."""
    base = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    moments = [base]
    for gap in gaps_s:
        moments.append(moments[-1] + timedelta(seconds=gap))
    return [
        {"tons": tons, "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%SZ")}
        for moment in moments
    ]


class ReportCommandTest(unittest.TestCase):
    def test_fleet_carrier_command_uses_label_and_plain_tonnage(self) -> None:
        target = Target(
            market_id=3709409280,
            name="B6W-34K",
            kind=KIND_FLEET,
            display_name="[PJGT]PANDA BEAR",
            tons=2372,
        )

        self.assertEqual(
            target.report_command(),
            f"/addscore user:{DEFAULT_DISCORD_USER} points:2372 "
            "comment:[PJGT]PANDA BEAR (B6W-34K)",
        )

    def test_squadron_carrier_command(self) -> None:
        target = Target(
            market_id=3709409998,
            name="0822",
            kind=KIND_SQUADRON,
            display_name="[SCC] The Knave",
            tons=105,
        )

        self.assertEqual(
            target.report_command(),
            f"/addscore user:{DEFAULT_DISCORD_USER} points:105 "
            "comment:[SCC] The Knave (0822)",
        )

    def test_construction_site_command_has_no_prefix(self) -> None:
        target = Target(
            market_id=3963439106,
            name="Orbital Construction Site: Hoshino Enterprise",
            kind=KIND_CONSTRUCTION,
            tons=512,
        )

        self.assertEqual(
            target.report_command(),
            f"/addscore user:{DEFAULT_DISCORD_USER} points:512 comment:Hoshino Enterprise",
        )

    def test_user_is_configurable_and_gets_an_at_sign(self) -> None:
        target = Target(market_id=1, name="T3S-TIE", kind=KIND_FLEET, tons=10)

        self.assertIn("user:@someone", target.report_command("someone"))
        self.assertIn("user:@someone", target.report_command("@someone"))
        self.assertIn("user:@someone", target.report_command("  @someone  "))

    def test_empty_user_falls_back_to_default(self) -> None:
        target = Target(market_id=1, name="T3S-TIE", kind=KIND_FLEET, tons=10)

        self.assertIn(f"user:{DEFAULT_DISCORD_USER}", target.report_command(""))
        self.assertIn(f"user:{DEFAULT_DISCORD_USER}", target.report_command(None))

    def test_large_tonnage_has_no_thousands_separator(self) -> None:
        target = Target(market_id=1, name="T3S-TIE", kind=KIND_FLEET, tons=12345)

        self.assertIn("points:12345", target.report_command())

    def test_default_user_is_a_placeholder(self) -> None:
        self.assertEqual(DEFAULT_DISCORD_USER, "@yourdiscordname")

    def test_normalize_discord_user(self) -> None:
        self.assertEqual(normalize_discord_user("exampleuser"), "@exampleuser")
        self.assertEqual(normalize_discord_user("@exampleuser"), "@exampleuser")
        self.assertEqual(normalize_discord_user("   "), "")

    def test_clean_construction_name_variants(self) -> None:
        # Plain depot names keep working.
        self.assertEqual(
            clean_construction_name("Orbital Construction Site: Marshburn Hub"),
            "Marshburn Hub",
        )
        # The colonisation ship token resolves to its primary-port name.
        self.assertEqual(
            clean_construction_name("$EXT_PANEL_ColonisationShip; Volk Reach"),
            "Volk Reach",
        )
        self.assertEqual(
            clean_construction_name(
                "$EXT_PANEL_ColonisationShip:#index=2; Okawara Horizons"
            ),
            "Okawara Horizons",
        )
        self.assertEqual(
            clean_construction_name("$EXT_PANEL_ColonisationShip;"),
            "System Colonisation Ship",
        )

    def test_cached_pipe_display_name_self_heals_on_read(self) -> None:
        # Old plugin versions cached the "|" of "ILMARINEN | SETA" verbatim.
        target = Target.from_dict(
            {
                "market_id": 3709409999,
                "name": "SETA",
                "kind": KIND_SQUADRON,
                "display_name": "ILMARINEN |",
            }
        )
        self.assertEqual(target.label, "ILMARINEN (SETA)")


class RoundTripTest(unittest.TestCase):
    # The 16 gaps from nyenyon's real Volk Reach session (seconds).
    REAL_GAPS = [
        593, 451, 325, 333, 319, 348, 352, 543, 337, 366, 346, 318, 315,
        321, 329, 318,
    ]

    def test_real_session_has_no_pauses(self) -> None:
        summary = round_trip_summary(deliveries_from_gaps(self.REAL_GAPS))
        # median 335 -> cutoff max(1005, 1800) = 1800 -> nothing dropped
        self.assertEqual(summary, (370, 16, 16))
        self.assertEqual(
            round_trip_text(deliveries_from_gaps(self.REAL_GAPS)),
            "Avg round trip: 6 min 10 s (16 trips)",
        )

    def test_long_pause_is_ignored(self) -> None:
        deliveries = deliveries_from_gaps([360, 360, 360, 360, 7200])
        self.assertEqual(round_trip_summary(deliveries), (360, 4, 5))
        self.assertEqual(
            round_trip_text(deliveries),
            "Avg round trip: 6 min 0 s (4 of 5 trips, 1 pause ignored)",
        )

    def test_long_legitimate_flights_are_not_pauses(self) -> None:
        # median 3700 s -> cutoff 11100 s, so the 4000 s run stays counted
        deliveries = deliveries_from_gaps([3700, 4000, 3700, 90000])
        summary = round_trip_summary(deliveries)
        self.assertEqual(summary[1:], (3, 4))
        self.assertEqual(summary[0], round((3700 + 4000 + 3700) / 3))

    def test_needs_at_least_two_gaps(self) -> None:
        self.assertIsNone(round_trip_summary(deliveries_from_gaps([300])))
        self.assertEqual(round_trip_text(deliveries_from_gaps([300])), "")
        self.assertEqual(round_trip_text([]), "")

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(59), "59 s")
        self.assertEqual(format_duration(370), "6 min 10 s")
        self.assertEqual(format_duration(3725), "1 h 2 min")
        self.assertEqual(format_duration(-5), "0 s")


if __name__ == "__main__":
    unittest.main()
