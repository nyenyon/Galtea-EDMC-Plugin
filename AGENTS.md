# AGENTS.md

## Repository state

- EDMC plugin written in Python 3 (standard library only, no third-party packages).
- Entry point `load.py`; implementation in the `galtea` package; tests in `tests/`.
- The plugin is built for [Project Galtea](https://projectgaltea.org), an Elite Dangerous colonisation initiative; the Report command feeds the project's Discord score bot.
- The plugin tracks tonnage sold to fleet/squadron carriers (`MarketSell`) and commodities delivered to construction sites (`ColonisationContribution`). Active totals persist in `data/haul_tracker.json`, the finished-haul history in `data/haul_history.json`, carrier display names in `data/carrier_cache.json` (all git-ignored).
- `README.md` is the short overview (what the plugin does, counting rules, install, settings summary, data folder); `DETAILS.md` is the full guide (details window, delivery log, report command, settings, data files, journal quirks, development) and is linked from the README — update both when behaviour changes.
- The logo is `assets/logo.svg`, embedded at the top of `README.md`.

## Platforms

- The plugin targets EDMC on Linux, Windows and macOS. It uses only the Python standard library and Tk; there are no platform-specific modules, shell commands or path separators.
- File access goes through `pathlib.Path`. The data files live inside the plugin folder and are written via `os.replace`; write failures are caught so tracking continues in memory.
- Mouse-wheel scrolling handles `<MouseWheel>` (Windows/macOS) and `<Button-4/5>` (Linux). macOS reports small deltas, so the handler falls back to one scroll unit when `int(delta / 120)` is zero.
- Use Tk named fonts (`TkDefaultFont`, `TkHeadingFont`, `TkSmallCaptionFont`) instead of hardcoded families or sizes; EDMC handles UI scaling.
- Clipboard and external links use tkinter's clipboard and `webbrowser`, never platform commands. The single exception is the settings **Open** button: revealing the data folder has no cross-platform API, so `_open_folder` uses `os.startfile` (Windows), `open` (macOS) or `xdg-open` (Linux) and swallows all errors.
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

- `galtea/` must stay importable without EDMC: only `load.py` and `galtea/ui.py` may import EDMC modules (`myNotebook`, `theme`, `config`) or tkinter. Network access and the update-check state machine (`UpdateChecker`) live in `galtea/update.py`; the optional in-game display lives in `galtea/overlay.py`, which lazily imports the `edmcoverlay` shim provided by the separate EDMCModernOverlay plugin and fails silently without it (`is_available()` lets the settings page grey out the switch and link to the plugin); both modules are Tk-free and `overlay.py` is tested with a fake client.
- The optional automatic update check is opt-in (`galtea_update_check`, default off), lives in `galtea/update.py` (standard-library `urllib.request` only), runs off the Tk thread with a timeout, and fails silently. The settings tab also has a **Check now** button for an explicit manual check; it uses the same background worker, works even when automatic checks are off, and reports its result in the settings tab. It only fetches release metadata and opens a validated GitHub release URL; it never downloads or installs updates. Tests mock the network.
- UI uses classic `tk` widgets (not `ttk`) and registers every widget tree with EDMC's `theme.update()`; `ttk` widgets are not recoloured by EDMC in dark mode. New widgets must go through `_apply_theme()`. Do not set a non-default `cursor` on themed `tk` widgets: EDMC's theme renders such widgets as hyperlinks (selection-highlight text) and `tk.Frame` breaks theming entirely with one. Exception: EDMC does not theme plugin settings tabs, so `build_prefs()` uses `nb` widgets and keeps the default colours there — note that `myNotebook` has no `Entry`, so text fields on that page use `ttk.Entry`.
- `journal_entry` runs on EDMC's Tk main thread, so UI updates are safe there; keep journal handling non-blocking and wrap it in `try/except`.
- Journal field names are verified against real journal samples; check EDDI/EDDiscovery before adding new events.
- Journals sometimes report squadron carriers as `StationType: "FleetCarrier"`; `squadronBank` in `StationServices` and four-character callsigns (e.g. `0822`) identify them. Squadron carrier names also end in such a callsign in `SupercruiseDestinationDrop`.
- EDMC only sends journal events while the game is running (plus a synthetic `StartUp` event when it starts with the game already running). `Tracker` therefore preloads the last commander via `HaulStore.last_commander()`; keep `remember_commander()` in sync when commander handling changes.
- `data/haul_tracker.json` keys targets by a unique batch id assigned in `add()`; deliveries go to the newest active batch; `reset_target()` takes a batch id (a market id still resolves to the newest batch); `restore()` reinserts a batch separately instead of merging. Every batch carries a `deliveries` log (one `{"tons","timestamp","session"}` entry per landing: `Tracker` passes the `Docked` timestamp as session, `store.add()` merges same-session sales into the last entry, newest `DELIVERY_LIMIT` kept; without a session a merge-window fallback of `DELIVERY_MERGE_WINDOW_S` (2 min) since the entry's last sale combines the landing, while two different known sessions are always separate landings). `store.edit_delivery()` corrects one entry's tonnage and `store.delete_delivery()` removes one (both find the entry by its unique timestamp, adjust the batch total by the delta, and touch active targets only; archived history stays immutable because it may already have been reported). History lives only in `data/haul_history.json`: `load()` merges it into the commander records and `save()` splits it out again, so `ui.py`/`core.py` never learn about the file count. Releases up to 0.9.0 shipped **no data migrations**: any data file whose version is not the current one is moved to `<name>.corrupt` with a warning log so no save can destroy it. **Mandated again since 2026-11-02: future releases must migrate the `data/` files.** Every release that changes the format has to ship a converter that upgrades existing files step by step to the current `SCHEMA_VERSION` during `load()`, so users can update **without** clearing `data/`; only unreadable JSON keeps moving aside to `<name>.corrupt`, and every migration logs what it did. The rule is **prospective only**: files older than schema 5 (before 0.8.0) intentionally stay reject-and-park — no retroactive converter.
- Carrier display names are cached per commander in `data/carrier_cache.json`, keyed by market id and callsign. `SupercruiseDestinationDrop.Type` may be `Name CALLSIGN`, `Name | CALLSIGN` (squadron carriers), just the name, a localized token, or only the callsign, so `carrier_name_from_drop()` accepts all variants and `model.clean_carrier_name()` strips the stray `|` — also for names cached by older versions, which self-heal on read without any migration. Names are only applied to carrier contexts and targets; debug logs record drops that cannot be parsed.
- **Report** shows `/addscore user:<handle> points:<tons> comment:<target>`; **Reported** finishes the batch via `reset_target(..., reason="reported")`. If **Copy** was not pressed first, the UI asks for confirmation. **Finish haul** offers **Yes** (reason `reported`), **No, do it anyway** (reason `unreported`) and **Cancel**; **Finish all hauls** uses the same choice and `reset_all(reason=...)` applies it to every active haul. The handle is the EDMC config key `galtea_discord_user`, default placeholder `@yourdiscordname`.
- Finished hauls (the history) can be restored with `restore()`, permanently deleted with `delete_history()`, or cleared with `clear_history()`. The delete paths are irreversible and always ask for confirmation in the UI. Entries archived with reason `reported` show the Reported flag; all other reasons do not. The details header action follows the active tab: **Finish all hauls** on Active hauls, **Delete all** on Finished hauls.
- Confirmation dialogs use the shared `_make_modal` / `_show_modal` helpers (`_confirm` for simple confirmations, `_ask_finish_choice` for the three-way reported choice) so every modal has the same themed layout; do not add native `messagebox` dialogs. Hover help uses the module-level `_Tooltip` (delayed borderless popup, theme-registered, no `hand2` cursor).
- The whole plugin has a master switch, `galtea_enabled` (default on). When off, `journal_entry` does nothing, `build_panel`/`_rebuild_panel` show a disabled hint instead of the rows, the details window closes, and background update checks stop; data files are left untouched. Haul actions live only in the details window, never in the settings page. The settings **Check now** manual check deliberately still works while off. Read it via `ui.plugin_enabled()` at the few entry points, never per widget.
- User-visible changes are recorded in `CHANGELOG.md` (Keep a Changelog style, versions match `VERSION` in `load.py`).
- Never run `git commit` or `git push` without the user's explicit instruction for that commit; leave changes in the working tree and tell the user they are uncommitted.
- Remote is `git@github.com:nyenyon/Galtea-EDMC-Plugin.git`; the default branch is `main`.
