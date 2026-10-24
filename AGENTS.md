# AGENTS.md

## Repository state

- EDMC plugin written in Python 3 (standard library only, no third-party packages).
- Entry point `load.py`; implementation in the `galtea` package; tests in `tests/`.
- The plugin tracks tonnage sold to fleet/squadron carriers (`MarketSell`) and commodities delivered to construction sites (`ColonisationContribution`). Totals persist in `data/haul_tracker.json` (git-ignored).
- `README.md` documents behaviour, install steps and the data file.

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
- UI uses classic `tk` widgets (not `ttk`) and registers every widget tree with EDMC's `theme.update()`; `ttk` widgets are not recoloured by EDMC in dark mode. New widgets must go through `_apply_theme()`.
- `journal_entry` runs on EDMC's Tk main thread, so UI updates are safe there; keep journal handling non-blocking and wrap it in `try/except`.
- Journal field names are verified against real journal samples; check EDDI/EDDiscovery before adding new events.
- Remote is `git@github.com:nyenyon/Galtea-EDMC-Plugin.git`; the default branch is `main`.
