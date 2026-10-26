<p align="center">
  <img src="assets/logo.svg" alt="Galtea Haul Tracker logo" width="160">
</p>

# Galtea Haul Tracker (EDMC plugin)

**Runs on EDMC for Windows, macOS and Linux.**

> **Note:** This plugin was created entirely with AI agents. Code, tests and
> documentation were generated and reviewed by them.

An [EDMarketConnector](https://github.com/EDCD/EDMarketConnector) plugin for [Project Galtea](https://projectgaltea.org). It counts tonnage sold at **fleet carriers** and **squadron carriers** and commodities delivered to **construction sites** (space and planetary), and generates the prefilled `/addscore` command for the project's Discord.

## Project Galtea

[Project Galtea](https://projectgaltea.org) is a community-driven Elite Dangerous colonisation initiative building a resupply bridge into the Arcadian Stream to establish a thriving frontier.

## What it is for

The plugin has two jobs:

- **Count deliveries automatically.** It follows EDMC's journal while you play. Sales at fleet and squadron carriers and contributions to construction sites are added to the matching target with a running total, so there is no manual adding up of cargo.
- **Prepare the Discord report.** When you are ready to report, the target's **Report** window contains the finished `/addscore` command with your handle, the current tonnage and the target label:

  ```
  /addscore user:@nyenyon points:2372 comment:[PJGT]PANDA BEAR (B6W-34K)
  ```

  **Copy** puts it on the clipboard; paste it into the Galtea Discord. This avoids typos in the handle, tonnage or carrier name and keeps the report consistent with the tracker.
- **Nothing is posted automatically.** The plugin only prepares the command; you decide when and where to send it.

### What is counted

| You sell at | Journal event | Counted |
|---|---|---|
| Fleet carrier | `MarketSell` | yes, all commodities |
| Squadron carrier | `MarketSell` | yes, all commodities |
| Construction site (space / planet / colonisation ship) | `ColonisationContribution` | yes, all delivered commodities |
| Any other station | `MarketSell` | no |

Only the **summed tonnage** per target is tracked — there is no per-commodity breakdown. Totals persist across EDMC restarts, and commanders on the same machine are tracked separately.

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

The details window has **Active hauls (N)** and **Finished hauls (N)** tabs, both showing their entry count.

**Active hauls** is shown first and lists every target with its own **Report** and **Finish haul** buttons. **Finish haul** asks whether the haul was already reported: **Yes** archives it as reported, **No, do it anyway** archives it without the flag, and **Cancel** keeps it active. Unreported tonnage is therefore never archived silently. The header action **Finish all hauls** applies the same choice to every active haul.

**Report** opens the prefilled Project Galtea command shown above for that target. `comment:` is the target as shown in the list — the carrier name with its callsign, or the construction site being built — and `user:` comes from the plugin settings. After you post the command, **Reported** archives the haul as reported; if **Copy** was not pressed first, it asks for confirmation. Every report is stored as its own batch with a unique ID, so reporting the same carrier again later creates a separate entry.

**Finished hauls** lists name, type, tonnage, reported flag and finish time, with **Restore** and **Delete** buttons for each entry; **Delete all** clears the whole list. The tab keeps the last 200 entries. Restoring a batch reinserts it as its own entry: if the same carrier already has a newer active batch, both stay separate and new deliveries go to the newest. In that case the details and report windows show the short batch IDs so you can tell the entries apart. All delete actions are permanent and ask for confirmation first.

## Install

1. Copy this folder into your EDMC plugins directory:
   - Windows: `%LOCALAPPDATA%\EDMarketConnector\plugins\Galtea-Haul-Tracker`
   - macOS: `~/Library/Application Support/EDMarketConnector/plugins/Galtea-Haul-Tracker`
   - Linux: `~/.local/share/EDMarketConnector/plugins/Galtea-Haul-Tracker` (or `$XDG_DATA_HOME/EDMarketConnector/plugins/…`)
2. Restart EDMC.

The plugin needs no third-party packages and makes no network requests.

## Settings

The plugin adds a **Galtea Haul Tracker** tab to EDMC's settings:

- **Discord user for the Report command** – the handle used as `user:@name` in the `/addscore` command. The default is the placeholder `@yourdiscordname`, so no real user is credited by accident; set your own handle before reporting. The handle is stored in EDMC's configuration, and the report window reminds you while the placeholder is still in use.
- **Finish all hauls…** – applies the same three-way reported choice as the **Finish all hauls** action in the details window.
- The footer shows the plugin version and links to the GitHub repository.

## Data files

Totals are stored in `data/haul_tracker.json`; carrier display names are cached separately in `data/carrier_cache.json`. Both live inside the plugin folder and have a schema version, so older files are migrated automatically. `haul_tracker.json` keys each target by a unique batch id. A corrupt file is moved to `<name>.corrupt` and the affected data starts fresh.

> Note: `data/` is local and git-ignored, so it is not part of the repository or a release archive. Replacing the plugin folder (deleting the old one and copying the new one) removes it; updating with `git pull` or copying files over the existing folder keeps it. Back it up if that matters.

## Good to know

- Carrier names: the journal only knows a carrier's **callsign** (e.g. `T3S-TIE` for fleet carriers, `0822` for squadron carriers) when you dock. The pretty name is read from `SupercruiseDestinationDrop` (also when it contains only the name, a localized variant, or no `MarketID`) and from `CarrierStats`/`CarrierNameChanged` for your own carrier; then the display becomes `Name (CALLSIGN)`. Names are cached per commander, so a carrier you have visited before is shown by name immediately. If the game reports only the callsign on a first visit, the name appears as soon as the journal provides it.
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

The tests use the standard library only.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Licence

GPL-3.0 — see [LICENSE](LICENSE).
