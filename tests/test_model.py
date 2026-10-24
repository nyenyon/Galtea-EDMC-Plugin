"""The Discord/Sicord report command generated for a target."""

from __future__ import annotations

import unittest

from galtea.model import (
    DEFAULT_DISCORD_USER,
    KIND_CONSTRUCTION,
    KIND_FLEET,
    KIND_SQUADRON,
    Target,
    normalize_discord_user,
)


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


if __name__ == "__main__":
    unittest.main()
