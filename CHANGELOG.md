# Changelog

All notable changes to the Galtea Haul Tracker plugin are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match `VERSION` in `load.py`.

## [0.6.1] - 2026-10-26

### Added

- **Check now** button in the plugin settings for an immediate GitHub release
  check. It works even when automatic checks are disabled and shows the result
  below the button.
- A manually found update is also shown as a link at the bottom of the details
  window, even if automatic checks are disabled.

### Changed

- Manual checks use the same background request and timeout as automatic
  checks. Automatic failures stay silent; manual checks report a failure in
  the settings tab.
- The automatic check remains opt-in and off by default.

## [0.6.0] - 2026-10-26

### Added

- Optional update check for new GitHub releases. It is off by default and can
  be enabled in the plugin settings. The check runs in the background, only
  fetches release metadata, and fails silently.
- When a newer release exists, the details window shows a small link to the
  GitHub release at the bottom. The plugin never downloads or installs an
  update automatically.

### Changed

- The update check runs immediately only when the option is enabled; saving
  the plugin settings later does not reset the 24-hour interval.

## [0.5.1] - 2026-10-26

### Changed

- Carrier display names are cached in `data/carrier_cache.json` instead of
  inside `data/haul_tracker.json`, so updating a name no longer rewrites the
  haul totals. The haul data schema is now 3, and existing embedded caches are
  migrated automatically.
- The report window and documentation now refer only to Discord; the Sicord
  wording was removed.

## [0.5.0] - 2026-10-25

### Added

- **Reported** button in the "Report delivery" window: once the tonnage has
  been reported, it removes the target from the running totals and moves it to
  **Finished hauls**, where it can be restored.
- The **Finished hauls** tab shows whether an entry was finished with
  **Reported**.
- If restoring a report leaves several active batches for the same carrier,
  the details window and the report window show each batch's short ID so they
  can be told apart.
- The report window shows a reminder to set your own Discord handle while the
  placeholder `@yourdiscordname` is still in use.
- The plugin settings tab shows the version and links to the GitHub repository.
- Added a project logo, shown at the top of the README.
- The **Active hauls** tab shows the number of active entries in its label.
- Entries in **Finished hauls** have a **Delete** button that permanently
  removes the entry after a confirmation. **Delete all** on that tab clears the
  whole list, also after a confirmation.
- Pressing **Reported** without pressing **Copy** first asks for confirmation,
  preventing accidental finishing.
- **Finish haul** offers **Yes** (mark as reported), **No, do it anyway**
  (finish without the reported flag) and **Cancel**. **Finish all hauls** uses
  the same choice for every active haul.

### Changed

- The details window now has **Active hauls** and **Finished hauls** tabs. The
  finished list is only shown when its tab is selected, and the tab label shows
  the number of entries.
- The plugin panel is separated from EDMC's **Update** button by a themed
  divider, and the settings tab was rebuilt to stay usable when resized while
  keeping EDMC's default colours.
- The target button is now labelled **Finish haul** (and **Finish all hauls…**
  in the settings) instead of **Reset**; entries still move to **Finished
  hauls** and can be restored.
- The details header action follows the active tab: **Finish all hauls** on
  **Active hauls** (moves every active target to **Finished hauls**) and
  **Delete all** on **Finished hauls** (permanently clears the list).
- All confirmation dialogs now use the plugin's own themed modal layout
  instead of native message boxes.
- The main-window target list keeps its tonnage column at a fixed width and
  right-aligns it, while the name column grows and shows more of the name as
  the window widens. The same name fitting is used in the Active hauls and
  Finished hauls tabs, and their type column fits "Construction site".
- Every target now has a unique batch ID. Reporting the same carrier again
  creates a separate entry in **Finished hauls**, and restoring a reported
  batch keeps it separate from a newer batch instead of merging the tonnage.
  Existing data files are migrated automatically.
- The default Discord handle used by the **Report** command is now the
  placeholder `@yourdiscordname` instead of `@nyenyon`, so tonnage is not
  accidentally credited to the wrong user. A handle entered in the plugin
  preferences is stored in EDMC's configuration and persists across restarts.

### Fixed

- Carrier display names are resolved from the first
  `SupercruiseDestinationDrop` where possible, including name-only, localized
  and missing-`MarketID` variants, and are cached per commander. The callsign
  is no longer shown until the second visit.
- Mouse-wheel scrolling handles the small trackpad deltas reported by macOS.

## [0.2.0] - 2026-10-24

### Added

- **Report** button next to every target in the details window: it shows the
  Discord macro `/addscore user:@name points:<tons> comment:<target>`
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
