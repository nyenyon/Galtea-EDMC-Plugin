# AGENTS.md

## Repository state

- EDMC plugin written in Python 3 (standard library only, no third-party packages).
- Entry point `load.py`; implementation in the `galtea` package; tests in `tests/`.
- The plugin is built for [Project Galtea](https://projectgaltea.org), an Elite Dangerous colonisation initiative; the Report command feeds the project's Discord/Sicord score bot.
- The plugin tracks tonnage sold to fleet/squadron carriers (`MarketSell`) and commodities delivered to construction sites (`ColonisationContribution`). Totals persist in `data/haul_tracker.json` (git-ignored).
- `README.md` documents behaviour, install steps and the data file.

## Platforms

- The plugin targets EDMC on Linux, Windows and macOS. It uses only the Python standard library and Tk; there are no platform-specific modules, shell commands or path separators.
- File access goes through `pathlib.Path`. The data file lives inside the plugin folder and is written via `os.replace`; write failures are caught so tracking continues in memory.
- Mouse-wheel scrolling handles `<MouseWheel>` (Windows/macOS) and `<Button-4/5>` (Linux). macOS reports small deltas, so the handler falls back to one scroll unit when `int(delta / 120)` is zero.
- Use Tk named fonts (`TkDefaultFont`, `TkHeadingFont`, `TkSmallCaptionFont`) instead of hardcoded families or sizes; EDMC handles UI scaling.
- Clipboard and external links use tkinter's clipboard and `webbrowser`, never platform commands.
- The unit tests are platform-independent, but UI changes still need a visual check on all three platforms when possible.

## Commands

```sh
# Run the test suite (stdlib unittest, no install step needed)
python3 -m unittest discover -s tests -v

# Compile check
python3 -m compileall -q load.py galtea tests
```

There is no linter or CI configuration; do not invent one without asking.

## Working here

- `galtea/` must stay importable without EDMC: only `load.py` and `galtea/ui.py` may import EDMC modules (`myNotebook`, `theme`) or tkinter.
- UI uses classic `tk` widgets (not `ttk`) and registers every widget tree with EDMC's `theme.update()`; `ttk` widgets are not recoloured by EDMC in dark mode. New widgets must go through `_apply_theme()`. Exception: EDMC does not theme plugin settings tabs, so `build_prefs()` uses `nb` widgets and keeps the default colours there.
- `journal_entry` runs on EDMC's Tk main thread, so UI updates are safe there; keep journal handling non-blocking and wrap it in `try/except`.
- Journal field names are verified against real journal samples; check EDDI/EDDiscovery before adding new events.
- Journals sometimes report squadron carriers as `StationType: "FleetCarrier"`; `squadronBank` in `StationServices` and four-character callsigns (e.g. `0822`) identify them. Squadron carrier names also end in such a callsign in `SupercruiseDestinationDrop`.
- EDMC only sends journal events while the game is running (plus a synthetic `StartUp` event when it starts with the game already running). `Tracker` therefore preloads the last commander via `HaulStore.last_commander()`; keep `remember_commander()` in sync when commander handling changes.
- Since `SCHEMA_VERSION` 2, `data/haul_tracker.json` keys targets by a unique batch id, not by market id: the same carrier can have several active batches after an old report is restored. Deliveries go to the newest active batch; `reset_target()` takes a batch id (a market id still resolves to the newest batch); `restore()` reinserts a batch separately instead of merging. `_migrate()` upgrades old files on load and must be extended for schema changes.
- Carrier display names are cached per commander under `cmdrs.<key>.carriers`, keyed by market id and callsign. `SupercruiseDestinationDrop.Type` may be `Name CALLSIGN`, just the name, a localized token, or only the callsign, so `carrier_name_from_drop()` accepts all variants. Names are only applied to carrier contexts and targets; debug logs record drops that cannot be parsed.
- **Report** shows `/addscore user:<handle> points:<tons> comment:<target>`; **Reported** finishes the batch via `reset_target(..., reason="reported")`. If **Copy** was not pressed first, the UI asks for confirmation. **Finish haul** offers **Yes** (reason `reported`), **No, do it anyway** (reason `unreported`) and **Cancel**. The handle is the EDMC config key `galtea_discord_user`, default placeholder `@yourdiscordname`.
- Finished hauls (the history) can be restored with `restore()`, permanently deleted with `delete_history()`, or cleared with `clear_history()`. The delete paths are irreversible and always ask for confirmation in the UI. The details header action follows the active tab: **Finish all hauls** on Active hauls, **Delete all** on Finished hauls.
- User-visible changes are recorded in `CHANGELOG.md` (Keep a Changelog style, versions match `VERSION` in `load.py`).
- Remote is `git@github.com:nyenyon/Galtea-EDMC-Plugin.git`; the default branch is `main`.
