# Galtea Haul Tracker (EDMC plugin)

**Runs on EDMC for Windows, macOS and Linux.**

> **Note:** This plugin was created entirely with AI agents. Code, tests and
> documentation were generated and reviewed by them.

An [EDMarketConnector](https://github.com/EDCD/EDMarketConnector) plugin built for [Project Galtea](https://projectgaltea.org), the community-driven colonisation effort in Elite Dangerous. It counts the tonnage you sell at **fleet carriers** and **squadron carriers**, and the commodities you deliver to **construction sites** (space and planetary), with running totals per target.

## Project Galtea

[Project Galtea](https://projectgaltea.org) is a community-driven Elite Dangerous colonisation initiative building a resupply bridge into the Arcadian Stream to establish a thriving frontier. This plugin keeps each commander's hauling totals for the project and turns every target into the `/addscore` command used to report contributions on the Galtea Discord/Sicord.

## What it tracks

| You sell at | Journal event | Counted |
|---|---|---|
| Fleet carrier | `MarketSell` | yes, all commodities |
| Squadron carrier | `MarketSell` | yes, all commodities |
| Construction site (space / planet / colonisation ship) | `ColonisationContribution` | yes, all delivered commodities |
| Any other station | `MarketSell` | no |

Only the **summed tonnage** is stored — there is no per-commodity breakdown. Totals accumulate per target and survive EDMC restarts. Commanders on the same machine are tracked separately.

Construction sites never emit `MarketSell` for deliveries, so exactly one event type is used per target — no double counting.

## Display

The EDMC main window shows the top three targets and the total, plus a **Details** button:

```
Galtea Haul Tracker
  Test Carrier (T3S-TIE)     2,640 t
  Shakespeare Point          1,300 t
Total: 3,940 t
[ Details ]
```

The details window has **Targets** and **History** tabs. **Targets** is shown first and lists every target with its own **Report** and **Archive** buttons; **Archive all** sits in the header. The **History** tab shows the number of archived entries in its label and lists name, type, tonnage, whether the entry was reported, and the archival time, with a **Restore** button for each entry.

**Report** shows the Project Galtea Discord/Sicord macro for that target in a copyable field:

```
/addscore user:@yourdiscordname points:2372 comment:[PJGT]PANDA BEAR (B6W-34K)
```

`comment:` is the target as shown in the list: the carrier name with its callsign, or the construction site being built. The Discord handle is configurable in the plugin preferences; the default is the placeholder `@yourdiscordname`, so no real user is credited by accident. The configured handle is stored in EDMC's configuration and persists across restarts. While the placeholder is still in use, the report window shows a reminder to change it in the plugin preferences.

Once the tonnage has been reported, the **Reported** button in the same window archives the target: it disappears from the running totals and moves to the history, just like **Archive**. It can be restored from there if needed.

Every report is stored as its own batch with a unique ID. Reporting the same carrier again later creates a separate history entry. If you restore an older batch while the same carrier already has a newer one, both stay separate and new deliveries go to the newest batch. In that case the details window and the report window show the short batch IDs so you can tell the entries apart.

Archiving an entry always moves it to the history instead of discarding it, so an accidental removal can be undone. The history keeps the last 200 entries.

## Install

1. Copy this folder into your EDMC plugins directory:
   - Windows: `%LOCALAPPDATA%\EDMarketConnector\plugins\Galtea-Haul-Tracker`
   - macOS: `~/Library/Application Support/EDMarketConnector/plugins/Galtea-Haul-Tracker`
   - Linux: `~/.local/share/EDMarketConnector/plugins/Galtea-Haul-Tracker` (or `$XDG_DATA_HOME/EDMarketConnector/plugins/…`)
2. Restart EDMC.

The plugin needs no third-party packages and makes no network requests.

## Settings

The plugin adds a **Galtea Haul Tracker** tab to EDMC's settings:

- **Discord user for the Report command** – the Project Galtea Discord handle used as `user:@name` in the `/addscore` command. The default is the placeholder `@yourdiscordname`; set your own handle before reporting. It is stored in EDMC's configuration and survives restarts.
- **Archive all tracked entries…** – archives every active target in the history.
- The footer shows the plugin version and links to the GitHub repository.

## Data file

Totals are stored in `data/haul_tracker.json` inside the plugin folder. The file has a schema version; older data files are migrated automatically, with each target receiving a unique batch id. The file also caches carrier display names per commander, so learned names survive restarts. A corrupt file is moved to `haul_tracker.corrupt` and tracking starts fresh.

> Note: `data/` is local and git-ignored, so it is not part of the repository or a release archive. Replacing the plugin folder (deleting the old one and copying the new one) removes it; updating with `git pull` or copying files over the existing folder keeps it. Back it up if that matters.

## Good to know

- Carrier names: the journal only knows a carrier's **callsign** (e.g. `T3S-TIE` for fleet carriers, `0822` for squadron carriers) when you dock. The pretty name is read from `SupercruiseDestinationDrop` (also when it contains only the name, a localized variant, or no `MarketID`) and from `CarrierStats`/`CarrierNameChanged` for your own carrier; then the display becomes `Name (CALLSIGN)`. Names are cached per commander in the data file, so a carrier you have visited before is shown by name immediately. If the game reports only the callsign on a first visit, the name appears as soon as the journal provides it.
- Squadron carriers are sometimes written as `StationType: "FleetCarrier"` in journals. The plugin recognises them by the `squadronBank` station service or by the four-character callsign, so they are labelled **Squadron carrier**.
- Construction sites are named `Orbital Construction Site: <name>` / `Planetary Construction Site: <name>` in the journal; the display shows only `<name>`, the station that is being built.
- Startup: EDMC only forwards journal events while the game is running. The plugin remembers the last active commander, so the stored totals are visible immediately after restarting EDMC; the display switches as soon as the journal reports a different commander.
- Theme: the plugin's own windows use classic Tk widgets and register them with EDMC's `theme` module, so the **default** and **dark** themes (including theme changes while EDMC is running) are respected. The settings tab keeps EDMC's default colours because EDMC does not theme plugin settings tabs.
- If EDMC is started while you are already docked, the docking event has already been consumed. A sale at a fleet-carrier callsign-shaped station name is still recognised as a carrier (type shown as “Carrier” until a docking event refines it).
- CQC sessions are ignored.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q load.py galtea tests
```

No dependencies; the tests use the standard library only.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Licence

GPL-3.0 — see [LICENSE](LICENSE).
