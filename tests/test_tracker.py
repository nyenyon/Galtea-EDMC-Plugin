"""Behaviour of the journal event router."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from galtea.core import Tracker
from galtea.model import KIND_CARRIER, KIND_CONSTRUCTION, KIND_FLEET, KIND_SQUADRON
from galtea.store import HaulStore

FLEET_CARRIER = {
    "event": "Docked",
    "MarketID": 3709409280,
    "StationName": "T3S-TIE",
    "StationType": "FleetCarrier",
    "StarSystem": "Bleae Thua ED-D c12-5",
    "timestamp": "2026-01-01T10:00:00Z",
}
SQUADRON_CARRIER = {
    "event": "Docked",
    "MarketID": 3709409999,
    "StationName": "SQD-001",
    "StationType": "SquadronCarrier",
    "StarSystem": "Bleae Thua ED-D c12-5",
    "timestamp": "2026-01-01T10:00:00Z",
}
# The game reports squadron carriers as FleetCarrier; the squadron bank
# service and the four-character callsign identify them.
SQUADRON_CARRIER_AS_FLEET = {
    "event": "Docked",
    "MarketID": 3709409998,
    "StationName": "0822",
    "StationType": "FleetCarrier",
    "StationServices": ["dock", "commodities", "squadronBank"],
    "StarSystem": "Bleae Thua ED-D c12-5",
    "timestamp": "2026-01-01T10:00:00Z",
}
SPACE_DEPOT = {
    "event": "Docked",
    "MarketID": 3963439106,
    "StationName": "Shakespeare Point",
    "StationType": "SpaceConstructionDepot",
    "StarSystem": "Bleae Thua ED-D c12-5",
    "timestamp": "2026-01-01T10:00:00Z",
}
PLANETARY_DEPOT = {
    "event": "Docked",
    "MarketID": 3963439107,
    "StationName": "Kruger Depot",
    "StationType": "PlanetaryConstructionDepot",
    "StarSystem": "Bleae Thua ED-D c12-5",
    "timestamp": "2026-01-01T10:00:00Z",
}
REGULAR_STATION = {
    "event": "Docked",
    "MarketID": 128016640,
    "StationName": "Abraham Lincoln",
    "StationType": "Coriolis",
    "StarSystem": "Sol",
    "timestamp": "2026-01-01T10:00:00Z",
}


def sale(count: int, market_id: int = 3709409280, timestamp: str = "2026-01-01T10:01:00Z") -> dict:
    return {
        "event": "MarketSell",
        "MarketID": market_id,
        "Type": "steel",
        "Count": count,
        "SellPrice": 4179,
        "TotalSale": 4179 * count,
        "timestamp": timestamp,
    }


def contribution(amounts: dict, market_id: int = 3963439106, timestamp: str = "2026-01-01T10:02:00Z") -> dict:
    return {
        "event": "ColonisationContribution",
        "MarketID": market_id,
        "Contributions": [
            {"Name": f"${name}_name;", "Name_Localised": name.title(), "Amount": amount}
            for name, amount in amounts.items()
        ],
        "timestamp": timestamp,
    }


class TrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = HaulStore(Path(self.tempdir.name) / "haul.json")
        self.tracker = Tracker(self.store)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def feed(self, entry: dict, system: str = "Bleae Thua ED-D c12-5", station: str = "") -> bool:
        return self.tracker.process(entry, system, station, fid="F123", cmdr="Test")

    # -- carriers --------------------------------------------------------

    def test_fleet_carrier_sales_accumulate(self) -> None:
        self.feed(FLEET_CARRIER)
        self.assertTrue(self.feed(sale(1320)))
        self.assertTrue(self.feed(sale(1320, timestamp="2026-01-01T10:05:00Z")))

        targets = self.store.targets("F123")
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].market_id, 3709409280)
        self.assertEqual(targets[0].kind, KIND_FLEET)
        self.assertEqual(targets[0].tons, 2640)
        self.assertEqual(targets[0].name, "T3S-TIE")
        self.assertEqual(self.store.total("F123"), 2640)

    def test_squadron_carrier_is_tracked_separately(self) -> None:
        self.feed(SQUADRON_CARRIER)
        self.feed(sale(500, market_id=3709409999))

        targets = self.store.targets("F123")
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].kind, KIND_SQUADRON)
        self.assertEqual(targets[0].tons, 500)

    def test_sales_at_regular_stations_are_ignored(self) -> None:
        self.feed(REGULAR_STATION, system="Sol")
        self.assertFalse(self.feed(sale(500, market_id=128016640), system="Sol"))

        self.assertEqual(self.store.targets("F123"), [])
        self.assertEqual(self.store.total("F123"), 0)

    def test_sales_at_construction_sites_do_not_double_count(self) -> None:
        self.feed(SPACE_DEPOT)
        self.feed(contribution({"steel": 700}))
        self.assertFalse(self.feed(sale(700, market_id=3963439106)))

        self.assertEqual(self.store.total("F123"), 700)

    def test_carrier_name_from_supercruise_drop(self) -> None:
        self.feed(
            {
                "event": "SupercruiseDestinationDrop",
                "MarketID": 3709409280,
                "Type": "Test Carrier T3S-TIE",
            }
        )
        self.feed(FLEET_CARRIER)
        self.feed(sale(1320))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.display_name, "Test Carrier")
        self.assertEqual(target.label, "Test Carrier (T3S-TIE)")

    def test_squadron_carrier_is_recognised_despite_fleetcarrier_type(self) -> None:
        self.feed(SQUADRON_CARRIER_AS_FLEET)
        self.feed(sale(105, market_id=3709409998))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_SQUADRON)
        self.assertEqual(target.name, "0822")

    def test_squadron_carrier_is_recognised_by_callsign_shape(self) -> None:
        entry = dict(SQUADRON_CARRIER_AS_FLEET, StationServices=[], MarketID=3709409997)
        self.feed(entry)
        self.feed(sale(50, market_id=3709409997))

        self.assertEqual(self.store.targets("F123")[0].kind, KIND_SQUADRON)

    def test_squadron_carrier_name_from_supercruise_drop(self) -> None:
        self.feed(SQUADRON_CARRIER_AS_FLEET)
        self.feed(sale(105, market_id=3709409998))
        self.feed(
            {
                "event": "SupercruiseDestinationDrop",
                "MarketID": 3709409998,
                "Type": "[SCC] The Knave 0822",
            }
        )

        target = self.store.targets("F123")[0]
        self.assertEqual(target.display_name, "[SCC] The Knave")
        self.assertEqual(target.label, "[SCC] The Knave (0822)")
        self.assertEqual(target.kind, KIND_SQUADRON)

    def test_squadron_carrier_drop_before_docking(self) -> None:
        self.feed(
            {
                "event": "SupercruiseDestinationDrop",
                "MarketID": 3709409998,
                "Type": "[SCC] The Knave 0822",
            }
        )
        self.feed(SQUADRON_CARRIER_AS_FLEET)
        self.feed(sale(105, market_id=3709409998))

        self.assertEqual(self.store.targets("F123")[0].label, "[SCC] The Knave (0822)")

    def test_station_drop_does_not_rename_a_construction_site(self) -> None:
        self.feed(SPACE_DEPOT)
        self.feed(contribution({"steel": 700}))
        # A station name that happens to end in four letters must not be
        # mistaken for a squadron-carrier name.
        self.feed(
            {
                "event": "SupercruiseDestinationDrop",
                "MarketID": 3963439106,
                "Type": "Fuji City",
            }
        )

        target = self.store.targets("F123")[0]
        self.assertEqual(target.display_name, "")
        self.assertEqual(target.label, "Shakespeare Point")

    def test_squadron_carrier_stats_set_name_and_kind(self) -> None:
        self.feed(SQUADRON_CARRIER_AS_FLEET)
        self.feed(sale(105, market_id=3709409998))
        self.feed(
            {
                "event": "CarrierStats",
                "CarrierID": 3709409998,
                "CarrierType": "SquadronCarrier",
                "Callsign": "0822",
                "Name": "The Knave",
            }
        )

        target = self.store.targets("F123")[0]
        self.assertEqual(target.display_name, "The Knave")
        self.assertEqual(target.kind, KIND_SQUADRON)
        self.assertEqual(target.label, "The Knave (0822)")

    def test_carrier_name_from_carrier_stats(self) -> None:
        self.feed(FLEET_CARRIER)
        self.feed(sale(100))
        self.feed(
            {
                "event": "CarrierStats",
                "CarrierID": 3709409280,
                "Callsign": "T3S-TIE",
                "Name": "Spirula",
            }
        )

        target = self.store.targets("F123")[0]
        self.assertEqual(target.display_name, "Spirula")

    def test_callsign_fallback_when_edmc_started_while_docked(self) -> None:
        # No Docked event: EDMC consumed it during the startup catch-up.
        self.assertTrue(self.feed(sale(1320), station="X9K-WTW"))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_CARRIER)
        self.assertEqual(target.name, "X9K-WTW")
        self.assertEqual(target.tons, 1320)

    def test_unknown_station_without_context_is_ignored(self) -> None:
        self.feed({"event": "Undocked"})  # selects the commander, no delivery
        self.assertFalse(self.feed(sale(1320), station="Abraham Lincoln"))
        self.assertEqual(self.store.total("F123"), 0)

    def test_later_docked_event_upgrades_unknown_carrier(self) -> None:
        self.feed(sale(200), station="T3S-TIE")
        self.feed(FLEET_CARRIER)
        self.feed(sale(100))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_FLEET)
        self.assertEqual(target.tons, 300)

    # -- construction sites ---------------------------------------------

    def test_space_construction_site_contributions(self) -> None:
        self.feed(SPACE_DEPOT)
        self.assertTrue(self.feed(contribution({"steel": 700, "titanium": 598})))
        self.feed(contribution({"steel": 2}, timestamp="2026-01-01T10:09:00Z"))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_CONSTRUCTION)
        self.assertEqual(target.name, "Shakespeare Point")
        self.assertEqual(target.tons, 1300)

    def test_planetary_construction_site(self) -> None:
        self.feed(PLANETARY_DEPOT)
        self.feed(contribution({"cmmcomposite": 42999}, market_id=3963439107))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_CONSTRUCTION)
        self.assertEqual(target.name, "Kruger Depot")
        self.assertEqual(target.tons, 42999)

    def test_colonisation_ship_is_detected_by_event(self) -> None:
        self.feed(
            {
                "event": "Docked",
                "MarketID": 3963439199,
                "StationName": "Colonisation Ship",
                "StationType": "ColonisationShip",
                "StarSystem": "Bleae Thua ED-D c12-5",
            }
        )
        self.feed(contribution({"steel": 1000}, market_id=3963439199))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_CONSTRUCTION)
        self.assertEqual(target.tons, 1000)

    def test_construction_site_prefix_is_not_displayed(self) -> None:
        self.feed(
            dict(
                SPACE_DEPOT,
                StationName="Orbital Construction Site: Hoshino Enterprise",
            )
        )
        self.feed(contribution({"steel": 700}))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.name, "Orbital Construction Site: Hoshino Enterprise")
        self.assertEqual(target.label, "Hoshino Enterprise")

    def test_planetary_construction_site_prefix_is_not_displayed(self) -> None:
        self.feed(
            dict(
                PLANETARY_DEPOT,
                StationName="Planetary Construction Site: Kruger Depot",
            )
        )
        self.feed(contribution({"steel": 700}, market_id=3963439107))

        self.assertEqual(self.store.targets("F123")[0].label, "Kruger Depot")

    def test_contribution_without_docked_event_uses_station_name(self) -> None:
        self.assertTrue(self.feed(contribution({"steel": 900}), station="Shakespeare Point"))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_CONSTRUCTION)
        self.assertEqual(target.name, "Shakespeare Point")
        self.assertEqual(target.tons, 900)

    def test_docked_event_replaces_generic_construction_name(self) -> None:
        self.feed(contribution({"steel": 900}))
        self.assertEqual(self.store.targets("F123")[0].name, "Construction site 3963439106")

        self.feed(SPACE_DEPOT)
        self.assertEqual(self.store.targets("F123")[0].name, "Shakespeare Point")

    # -- commanders ------------------------------------------------------

    def test_commanders_are_kept_separate(self) -> None:
        self.feed(FLEET_CARRIER)
        self.feed(sale(1320))

        self.tracker.process(FLEET_CARRIER, "Bleae Thua ED-D c12-5", "", fid="F999", cmdr="Other")
        self.assertTrue(
            self.tracker.process(sale(500), "Bleae Thua ED-D c12-5", "", fid="F999", cmdr="Other")
        )

        self.assertEqual(self.store.total("F123"), 1320)
        self.assertEqual(self.store.total("F999"), 500)
        self.assertEqual(len(self.store.targets("F123")), 1)
        self.assertEqual(len(self.store.targets("F999")), 1)

    # -- persistence -----------------------------------------------------

    def test_totals_survive_restart(self) -> None:
        self.feed(FLEET_CARRIER)
        self.feed(sale(1320))
        self.feed(SPACE_DEPOT)
        self.feed(contribution({"steel": 700}))

        reloaded = HaulStore(Path(self.tempdir.name) / "haul.json")
        self.assertEqual(reloaded.total("F123"), 2020)
        self.assertEqual(len(reloaded.targets("F123")), 2)

    def test_location_event_when_docked(self) -> None:
        self.feed({"event": "Location", "Docked": True, **{k: v for k, v in FLEET_CARRIER.items() if k != "event"}})
        self.feed(sale(300))

        target = self.store.targets("F123")[0]
        self.assertEqual(target.kind, KIND_FLEET)
        self.assertEqual(target.tons, 300)


if __name__ == "__main__":
    unittest.main()
