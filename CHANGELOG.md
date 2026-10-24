# Changelog

All notable changes to the Galtea Haul Tracker plugin are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match `VERSION` in `load.py`.

## [0.2.1] - 2026-10-24

### Changed

- The default Discord handle used by the **Report** command is now the
  placeholder `@yourdiscordname` instead of `@nyenyon`, so tonnage is not
  accidentally credited to the wrong user. A handle entered in the plugin
  preferences is stored in EDMC's configuration and persists across restarts.

## [0.2.0] - 2026-10-24

### Added

- **Report** button next to every target in the details window: it shows the
  Discord/Sicord macro `/addscore user:@name points:<tons> comment:<target>`
  in a copyable field. The Discord handle is configurable in the plugin
  preferences (default `@nyenyon`).

## [0.1.0] - 2026-10-24

### Added

- Tracks the tonnage sold at fleet carriers and squadron carriers
  (`MarketSell`) and the commodities delivered to construction sites
  (`ColonisationContribution`), including space depots, planetary depots,
  colonisation ships and colonisation ports.
- Running totals per target plus a grand total in the EDMC main window.
- Details window with a reset button per target, a "Reset all" button and a
  history of deleted entries (last 200) with a restore button.
- Per-commander persistence in `data/haul_tracker.json` with atomic writes;
  corrupt files are moved aside instead of stopping the tracker.
- Carrier display names resolved from `SupercruiseDestinationDrop`,
  `CarrierStats` and `CarrierNameChanged`, shown as `Name (CALLSIGN)`.
- Respects EDMC's default and dark themes, including theme changes while
  EDMC is running.

### Fixed

- Squadron carriers, which journals sometimes report as
  `StationType: "FleetCarrier"`, are detected by the `squadronBank` service or
  their four-character callsign (`0822`) and labelled "Squadron carrier".
  Entries stored with the old, wrong kind are corrected when the data file is
  loaded.
- Construction sites show only the station being built
  (`Orbital Construction Site: X` is displayed as `X`).
- Stored totals are visible immediately after restarting EDMC while the game
  is not running: the last active commander is remembered and preloaded,
  because EDMC only sends journal events while the game is running.
