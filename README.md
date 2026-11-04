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

The EDMC main window shows the top three targets and the total, plus a **Details** button. The details window lists **Active hauls** and **Finished hauls**: every target has its own **Report** (the prefilled `/addscore` command) and **Finish haul** action, each haul row expands into a per-landing delivery log that can be corrected, and finished hauls can be restored or permanently deleted. A found update is linked at the bottom of the window.

The full guide — details window, delivery log with edit/delete and the round-trip average, the report command, all settings, the data files, journal quirks and development notes — lives in [DETAILS.md](DETAILS.md).

## Install

1. Copy this folder into your EDMC plugins directory:
   - Windows: `%LOCALAPPDATA%\EDMarketConnector\plugins\Galtea-Haul-Tracker`
   - macOS: `~/Library/Application Support/EDMarketConnector/plugins/Galtea-Haul-Tracker`
   - Linux: `~/.local/share/EDMarketConnector/plugins/Galtea-Haul-Tracker` (or `$XDG_DATA_HOME/EDMarketConnector/plugins/…`)
2. Restart EDMC.

The plugin needs no third-party packages. It makes no network requests unless you enable the optional update check or press **Check now**.

## Settings

The plugin adds a **Galtea Haul Tracker** tab to EDMC's settings with four entries: the **Enable Galtea Haul Tracker** master switch, the **Discord user** for the report command (set your own handle before reporting — the default is a placeholder), the optional **Check GitHub for new versions** check with **Check now**, and the **Game data** directory with an **Open** button. The footer shows the plugin version and links to this repository.

What every setting does in detail: [DETAILS.md](DETAILS.md).

## Data

Everything is stored in the plugin folder's `data/` directory (git-ignored): haul totals, finished-haul history and the carrier name cache. It survives plugin updates — but if you come from an old plugin version, check [DETAILS.md](DETAILS.md) before updating: the data format is not converted.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Licence

GPL-3.0 — see [LICENSE](LICENSE).
