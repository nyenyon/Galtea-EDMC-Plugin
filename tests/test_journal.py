"""Carrier name resolution from ``SupercruiseDestinationDrop``."""

from __future__ import annotations

import unittest

from galtea.journal import carrier_name_from_drop


class CarrierDropTest(unittest.TestCase):
    def test_name_and_callsign_are_split(self) -> None:
        info = carrier_name_from_drop(
            {"MarketID": 3709409280, "Type": "Test Carrier T3S-TIE"}
        )

        self.assertEqual(info["market_id"], 3709409280)
        self.assertEqual(info["name"], "Test Carrier")
        self.assertEqual(info["callsign"], "T3S-TIE")

    def test_name_without_callsign_is_kept(self) -> None:
        info = carrier_name_from_drop({"MarketID": 1, "Type": "Test Carrier"})

        self.assertEqual(info["name"], "Test Carrier")
        self.assertEqual(info["callsign"], "")

    def test_localized_name_is_used_for_tokens(self) -> None:
        info = carrier_name_from_drop(
            {
                "MarketID": 1,
                "Type": "$FLEET_CARRIER_NAME;",
                "Type_Localised": "[SCC] The Knave 0822",
            }
        )

        self.assertEqual(info["name"], "[SCC] The Knave")
        self.assertEqual(info["callsign"], "0822")

    def test_bare_callsign_is_not_a_name(self) -> None:
        with self.assertLogs("GalteaHaulTracker", level="DEBUG"):
            self.assertIsNone(
                carrier_name_from_drop({"MarketID": 1, "Type": "T3S-TIE"})
            )
        self.assertIsNone(carrier_name_from_drop({"MarketID": 1, "Type": "0822"}))

    def test_missing_market_id_is_allowed(self) -> None:
        info = carrier_name_from_drop({"Type": "Test Carrier T3S-TIE"})

        self.assertIsNone(info["market_id"])
        self.assertEqual(info["name"], "Test Carrier")
        self.assertEqual(info["callsign"], "T3S-TIE")

    def test_generic_type_is_ignored(self) -> None:
        self.assertIsNone(
            carrier_name_from_drop(
                {"MarketID": 1, "Type": "$X;", "Type_Localised": "Fleet Carrier"}
            )
        )


if __name__ == "__main__":
    unittest.main()
