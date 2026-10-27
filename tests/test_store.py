"""Persistence, per-target reset and the deleted-entry history."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from galtea.model import KIND_CARRIER, KIND_FLEET, KIND_SQUADRON
from galtea.store import (
    CACHE_SCHEMA_VERSION,
    CARRIER_LIMIT,
    HISTORY_LIMIT,
    SCHEMA_VERSION,
    HaulStore,
)

CARRIER = dict(
    market_id=3709409280,
    name="T3S-TIE",
    kind=KIND_FLEET,
    station_type="FleetCarrier",
    system="Bleae Thua ED-D c12-5",
)
DEPOT = dict(
    market_id=3963439106,
    name="Shakespeare Point",
    kind="construction",
    station_type="SpaceConstructionDepot",
    system="Bleae Thua ED-D c12-5",
)


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "haul.json"
        self.cache_path = self.path.with_name("carrier_cache.json")
        self.store = HaulStore(self.path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def add_carrier(self, tons: int = 1320, when: str = "2026-01-01T10:00:00Z") -> None:
        self.store.add("F123", "Test", tons=tons, timestamp=when, **CARRIER)

    def add_depot(self, tons: int = 700) -> None:
        self.store.add("F123", "Test", tons=tons, timestamp="2026-01-01T10:05:00Z", **DEPOT)

    def test_delete_single_target_keeps_it_in_history(self) -> None:
        self.add_carrier(1320)
        self.add_depot(700)

        self.assertTrue(self.store.reset_target("F123", CARRIER["market_id"], "2026-01-02T08:00:00Z"))
        self.assertEqual([t.name for t in self.store.targets("F123")], ["Shakespeare Point"])
        self.assertEqual(self.store.total("F123"), 700)

        history = self.store.history("F123")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["target"]["name"], "T3S-TIE")
        self.assertEqual(history[0]["target"]["tons"], 1320)
        self.assertEqual(history[0]["deleted_at"], "2026-01-02T08:00:00Z")
        self.assertEqual(history[0]["reason"], "deleted")

    def test_reported_target_is_archived_with_reason(self) -> None:
        self.add_carrier(1320)
        batch_id = self.store.targets("F123")[0].id

        self.assertTrue(
            self.store.reset_target(
                "F123", batch_id, "2026-01-02T08:00:00Z", reason="reported"
            )
        )
        self.assertEqual(self.store.targets("F123"), [])
        history = self.store.history("F123")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["reason"], "reported")
        self.assertEqual(history[0]["target"]["tons"], 1320)
        self.assertEqual(history[0]["target"]["id"], batch_id)

    def test_same_carrier_reported_twice_creates_two_history_entries(self) -> None:
        self.add_carrier(300, when="2026-01-01T10:00:00Z")
        self.store.reset_target(
            "F123",
            self.store.targets("F123")[0].id,
            "2026-01-01T11:00:00Z",
            reason="reported",
        )
        self.add_carrier(120, when="2026-01-01T12:00:00Z")
        self.store.reset_target(
            "F123",
            self.store.targets("F123")[0].id,
            "2026-01-01T13:00:00Z",
            reason="reported",
        )

        history = self.store.history("F123")
        self.assertEqual([entry["target"]["tons"] for entry in history], [120, 300])
        self.assertEqual({entry["reason"] for entry in history}, {"reported"})
        self.assertEqual(len({entry["id"] for entry in history}), 2)
        self.assertEqual(len({entry["target"]["id"] for entry in history}), 2)
        self.assertEqual(
            {entry["target"]["market_id"] for entry in history}, {CARRIER["market_id"]}
        )

    def test_history_survives_restart(self) -> None:
        self.add_carrier(1320)
        self.store.reset_target("F123", self.store.targets("F123")[0].id)

        reloaded = HaulStore(self.path)
        self.assertEqual(len(reloaded.history("F123")), 1)
        self.assertEqual(reloaded.total("F123"), 0)

    def test_restore_returns_entry_and_clears_history(self) -> None:
        self.add_carrier(1320)
        self.store.reset_target("F123", self.store.targets("F123")[0].id)
        history_id = self.store.history("F123")[0]["id"]

        self.assertTrue(self.store.restore("F123", history_id))
        self.assertEqual(self.store.total("F123"), 1320)
        self.assertEqual(self.store.history("F123"), [])

    def test_restore_keeps_reported_batches_separate(self) -> None:
        self.add_carrier(1320, when="2026-01-01T10:00:00Z")
        self.store.reset_target(
            "F123", self.store.targets("F123")[0].id, reason="reported"
        )
        history_id = self.store.history("F123")[0]["id"]
        self.add_carrier(500, when="2026-01-03T09:00:00Z")

        self.assertTrue(self.store.restore("F123", history_id))
        targets = self.store.targets("F123")
        self.assertEqual(sorted(target.tons for target in targets), [500, 1320])
        self.assertEqual(len({target.id for target in targets}), 2)
        self.assertEqual(self.store.total("F123"), 1820)

    def test_deliveries_after_restore_go_to_the_newest_batch(self) -> None:
        self.add_carrier(1320, when="2026-01-01T10:00:00Z")
        self.store.reset_target(
            "F123", self.store.targets("F123")[0].id, reason="reported"
        )
        history_id = self.store.history("F123")[0]["id"]
        self.add_carrier(500, when="2026-01-03T09:00:00Z")
        self.store.restore("F123", history_id)

        self.add_carrier(100, when="2026-01-04T09:00:00Z")
        self.assertEqual(sorted(t.tons for t in self.store.targets("F123")), [600, 1320])

    def test_delete_history_entry_is_permanent(self) -> None:
        self.add_carrier(1320)
        self.store.reset_target("F123", self.store.targets("F123")[0].id)
        history_id = self.store.history("F123")[0]["id"]

        self.assertTrue(self.store.delete_history("F123", history_id))
        self.assertEqual(self.store.history("F123"), [])
        self.assertEqual(HaulStore(self.path).history("F123"), [])

    def test_delete_unknown_history_entry_is_ignored(self) -> None:
        self.assertFalse(self.store.delete_history("F123", "missing"))

    def test_clear_history_removes_all_entries(self) -> None:
        self.add_carrier()
        self.add_depot()
        self.store.reset_all("F123")

        self.assertEqual(self.store.clear_history("F123"), 2)
        self.assertEqual(self.store.history("F123"), [])
        self.assertEqual(HaulStore(self.path).history("F123"), [])
        self.assertEqual(self.store.clear_history("F123"), 0)

    def test_reset_all_can_mark_all_reported(self) -> None:
        self.add_carrier()
        self.add_depot()

        self.assertEqual(self.store.reset_all("F123", reason="reported"), 2)
        self.assertTrue(
            all(
                entry["reason"] == "reported"
                for entry in self.store.history("F123")
            )
        )

    def test_reset_all_archives_everything(self) -> None:
        self.add_carrier()
        self.add_depot()

        removed = self.store.reset_all("F123", "2026-01-02T09:00:00Z")
        self.assertEqual(removed, 2)
        self.assertEqual(self.store.targets("F123"), [])
        history = self.store.history("F123")
        self.assertEqual(len(history), 2)
        self.assertTrue(all(entry["reason"] == "reset_all" for entry in history))

    def test_reset_all_is_reversible(self) -> None:
        self.add_carrier()
        self.add_depot()
        self.store.reset_all("F123")

        for entry in self.store.history("F123"):
            self.assertTrue(self.store.restore("F123", entry["id"]))
        self.assertEqual(self.store.total("F123"), 2020)

    def test_history_is_capped(self) -> None:
        for index in range(HISTORY_LIMIT + 5):
            market_id = 1000 + index
            self.store.add(
                "F123",
                "Test",
                market_id=market_id,
                name=f"Site {index}",
                kind=KIND_FLEET,
                tons=10,
            )
            self.store.reset_target("F123", market_id)

        self.assertEqual(len(self.store.history("F123")), HISTORY_LIMIT)

    def test_commanders_do_not_share_totals(self) -> None:
        self.add_carrier()
        self.store.add("F999", "Other", tons=10, **DEPOT)

        self.assertEqual(self.store.total("F123"), 1320)
        self.assertEqual(self.store.total("F999"), 10)

    def test_last_commander_is_remembered(self) -> None:
        self.add_carrier()
        self.store.remember_commander("F123", "Test")

        reloaded = HaulStore(self.path)
        self.assertEqual(reloaded.last_commander(), "F123")
        self.assertEqual(reloaded.cmdr_name("F123"), "Test")

    def test_last_commander_falls_back_to_most_recent_data(self) -> None:
        self.add_carrier(tons=10, when="2026-01-01T10:00:00Z")
        self.store.add("F999", "Other", tons=10, timestamp="2026-01-02T10:00:00Z", **DEPOT)

        # Data files written before the key existed still show something.
        self.assertEqual(self.store.last_commander(), "F999")

    def test_last_commander_of_an_empty_store_is_unknown(self) -> None:
        self.assertEqual(self.store.last_commander(), "")

    def test_carrier_name_cache_survives_restart(self) -> None:
        self.store.remember_carrier("F123", 3709409280, "Test Carrier", "T3S-TIE")
        self.store.remember_carrier("F123", None, "Other Carrier", "X9K-WTW")

        reloaded = HaulStore(self.path)
        self.assertEqual(
            reloaded.carrier_name("F123", 3709409280)["name"], "Test Carrier"
        )
        self.assertEqual(
            reloaded.carrier_name("F123", callsign="t3s-tie")["name"], "Test Carrier"
        )
        self.assertEqual(
            reloaded.carrier_name("F123", callsign="X9K-WTW")["name"], "Other Carrier"
        )

    def test_carrier_name_is_enriched_with_market_id(self) -> None:
        self.store.remember_carrier("F123", None, "Test Carrier", "T3S-TIE")
        self.store.remember_carrier("F123", 3709409280, "Test Carrier", "T3S-TIE")

        self.assertEqual(
            self.store.carrier_name("F123", 3709409280)["name"], "Test Carrier"
        )
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        carriers = raw["cmdrs"]["F123"]["carriers"]
        self.assertEqual(len(carriers), 1)

    def test_carrier_cache_is_stored_separately(self) -> None:
        self.add_carrier()
        self.store.remember_carrier("F123", 3709409280, "Test Carrier", "T3S-TIE")

        hauls = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("carriers", hauls["cmdrs"]["F123"])

        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(cache["version"], CACHE_SCHEMA_VERSION)
        self.assertEqual(
            cache["cmdrs"]["F123"]["carriers"]["3709409280"]["name"],
            "Test Carrier",
        )

    def test_carrier_cache_path_is_configurable(self) -> None:
        cache_path = Path(self.tempdir.name) / "names.json"
        store = HaulStore(self.path, cache_path)
        store.remember_carrier("F123", 3709409280, "Test Carrier", "T3S-TIE")

        self.assertTrue(cache_path.exists())
        self.assertFalse(self.cache_path.exists())

    def test_carrier_cache_does_not_create_a_haul_record(self) -> None:
        self.store.remember_carrier("F999", 1, "Other Carrier", "X9K-WTW")

        self.assertTrue(self.cache_path.exists())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.cmdr_name("F999"), "")

    def test_carrier_cache_evicts_untouched_carriers_oldest_first(self) -> None:
        for index in range(1, CARRIER_LIMIT + 2):
            self.store.remember_carrier("F123", index, f"Carrier {index}", "")

        self.assertEqual(self.store.carrier_name("F123", 1), {})
        self.assertEqual(self.store.carrier_name("F123", 2)["name"], "Carrier 2")

    def test_carrier_cache_forgets_least_recently_named(self) -> None:
        for index in range(1, CARRIER_LIMIT + 1):
            self.store.remember_carrier("F123", index, f"Carrier {index}", "")
        # Naming the oldest carrier again moves it to the back of the queue.
        self.store.remember_carrier("F123", 1, "Home Carrier", "")
        self.store.remember_carrier("F123", CARRIER_LIMIT + 1, "Newcomer", "")

        self.assertEqual(self.store.carrier_name("F123", 1)["name"], "Home Carrier")
        self.assertEqual(self.store.carrier_name("F123", 2), {})

    def test_legacy_carrier_cache_is_migrated(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "cmdrs": {
                        "F123": {
                            "name": "Test",
                            "targets": {},
                            "history": [],
                            "carriers": {
                                "3709409280": {
                                    "market_id": 3709409280,
                                    "name": "Test Carrier",
                                    "callsign": "T3S-TIE",
                                }
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        store = HaulStore(self.path)
        self.assertEqual(
            store.carrier_name("F123", 3709409280)["name"], "Test Carrier"
        )

        hauls = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(hauls["version"], SCHEMA_VERSION)
        self.assertNotIn("carriers", hauls["cmdrs"]["F123"])

        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(
            cache["cmdrs"]["F123"]["carriers"]["3709409280"]["name"],
            "Test Carrier",
        )

        reloaded = HaulStore(self.path)
        self.assertEqual(
            reloaded.carrier_name("F123", callsign="t3s-tie")["name"],
            "Test Carrier",
        )

    def test_corrupt_carrier_cache_is_moved_aside(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text("{not json", encoding="utf-8")

        store = HaulStore(self.path)
        self.assertEqual(store.carrier_name("F123"), {})
        self.assertTrue(self.cache_path.with_suffix(".corrupt").exists())

    def test_carrier_name_without_identifier_is_ignored(self) -> None:
        self.assertEqual(self.store.remember_carrier("F123", None, "Test Carrier"), {})
        self.assertEqual(self.store.carrier_name("F123"), {})

    def test_update_target_upgrades_unknown_carrier(self) -> None:
        self.store.add(
            "F123",
            "Test",
            market_id=CARRIER["market_id"],
            name="T3S-TIE",
            kind=KIND_CARRIER,
            tons=100,
        )
        self.assertTrue(self.store.update_target("F123", CARRIER["market_id"], kind=KIND_FLEET))
        self.assertEqual(self.store.targets("F123")[0].kind, KIND_FLEET)

    def test_update_target_never_downgrades(self) -> None:
        self.add_carrier()
        self.assertFalse(self.store.update_target("F123", CARRIER["market_id"], kind=KIND_CARRIER))
        self.assertEqual(self.store.targets("F123")[0].kind, KIND_FLEET)

    def test_update_target_corrects_fleet_to_squadron(self) -> None:
        self.add_carrier()
        self.assertTrue(self.store.update_target("F123", CARRIER["market_id"], kind=KIND_SQUADRON))
        self.assertEqual(self.store.targets("F123")[0].kind, KIND_SQUADRON)

    def test_load_migrates_old_file_to_batch_ids(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "cmdrs": {
                        "F123": {
                            "name": "Test",
                            "targets": {
                                str(CARRIER["market_id"]): {
                                    "market_id": CARRIER["market_id"],
                                    "name": "T3S-TIE",
                                    "kind": KIND_FLEET,
                                    "tons": 1320,
                                    "first_delivery": "2026-01-01T10:00:00Z",
                                    "last_delivery": "2026-01-01T10:00:00Z",
                                }
                            },
                            "history": [
                                {
                                    "id": "old-entry",
                                    "deleted_at": "2026-01-02T08:00:00Z",
                                    "reason": "deleted",
                                    "target": {
                                        "market_id": 1,
                                        "name": "Old depot",
                                        "kind": "construction",
                                        "tons": 10,
                                    },
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        store = HaulStore(self.path)
        target = store.targets("F123")[0]
        self.assertTrue(target.id)
        self.assertEqual(store.total("F123"), 1320)

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        record = raw["cmdrs"]["F123"]
        self.assertEqual(raw["version"], SCHEMA_VERSION)
        self.assertEqual(list(record["targets"]), [target.id])
        self.assertTrue(record["history"][0]["target"]["id"])

    def test_corrupt_file_is_moved_aside(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json", encoding="utf-8")

        store = HaulStore(self.path)
        self.assertEqual(store.targets("F123"), [])
        self.assertTrue(self.path.with_suffix(".corrupt").exists())

    def test_corrupt_backups_are_not_overwritten(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{first", encoding="utf-8")
        HaulStore._move_corrupt(self.path)

        self.path.write_text("{second", encoding="utf-8")
        HaulStore._move_corrupt(self.path)

        self.assertEqual(
            self.path.with_suffix(".corrupt").read_text(encoding="utf-8"), "{first"
        )
        self.assertEqual(
            self.path.with_suffix(".corrupt.1").read_text(encoding="utf-8"), "{second"
        )

    def test_load_corrects_squadron_carrier_stored_as_fleet(self) -> None:
        self.add_carrier()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        target = next(iter(raw["cmdrs"]["F123"]["targets"].values()))
        target["name"] = "0822"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        store = HaulStore(self.path)
        fixed = store.targets("F123")[0]
        self.assertEqual(fixed.kind, KIND_SQUADRON)
        self.assertEqual(fixed.kind_label, "Squadron carrier")

        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(
            next(iter(persisted["cmdrs"]["F123"]["targets"].values()))["kind"],
            KIND_SQUADRON,
        )

    def test_load_keeps_fleet_carriers_with_three_part_callsign(self) -> None:
        self.add_carrier()
        self.assertEqual(HaulStore(self.path).targets("F123")[0].kind, KIND_FLEET)


if __name__ == "__main__":
    unittest.main()
