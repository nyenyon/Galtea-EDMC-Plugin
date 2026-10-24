# Galtea Haul Tracker (EDMC plugin)

An [EDMarketConnector](https://github.com/EDCD/EDMarketConnector) plugin that counts the tonnage you sell at **fleet carriers** and **squadron carriers**, and the commodities you deliver to **construction sites** (space and planetary), with running totals per target.

This is step 1 of the Galtea plugin: a focused haul tracker, nothing else.

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

The details window lists every target with its own **Reset** button, a **Reset all** button, and a **History** section containing every deleted entry (name, type, tonnage, deletion time) with a **Restore** button.

Deletes always move the entry to the history instead of discarding it, so an accidental reset can be undone. The history keeps the last 200 entries.

## Install

1. Copy this folder into your EDMC plugins directory:
   - Windows: `%LOCALAPPDATA%\EDMarketConnector\plugins\Galtea-Haul-Tracker`
   - macOS: `~/Library/Application Support/EDMarketConnector/plugins/Galtea-Haul-Tracker`
   - Linux: `~/.local/share/EDMarketConnector/plugins/Galtea-Haul-Tracker` (or `$XDG_DATA_HOME/EDMarketConnector/plugins/…`)
2. Restart EDMC.

The plugin needs no third-party packages and makes no network requests.

## Data file

Totals are stored in `data/haul_tracker.json` inside the plugin folder. A corrupt file is moved to `haul_tracker.corrupt` and tracking starts fresh.

> Note: reinstalling/updating the plugin by replacing the folder removes the data file. Back it up if that matters.

## Good to know

- Carrier names: the journal only knows a carrier's **callsign** (e.g. `T3S-TIE`) when you dock. The pretty name appears when the journal reveals it (`SupercruiseDestinationDrop`, or `CarrierStats` for your own carrier); then the display becomes `Name (CALLSIGN)`. Until then the callsign is shown.
- Theme: the plugin uses classic Tk widgets and registers them with EDMC's `theme` module, so the **default** and **dark** themes (including theme changes while EDMC is running) are respected.
- If EDMC is started while you are already docked, the docking event has already been consumed. A sale at a callsign-shaped station name is still recognised as a carrier (type shown as “Carrier” until a docking event refines it).
- CQC sessions are ignored.

## Development

```sh
python3 -m unittest discover -s tests -v
```

No dependencies; the tests use the standard library only.

## Licence

GPL-3.0 — see [LICENSE](LICENSE).
