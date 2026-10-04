# 06 — Architecture (Python + Textual)

Why this stack: see [07](07-tech-stack-decision.md).

## Package layout

```
alogs/
  __main__.py            # entry point: `alogs [file]` / `alogs --adb`
  app.py                 # Textual App: layout, key bindings, wiring
  app.tcss               # Textual CSS: 70/30 and 40/60 proportions, colours
  widgets/
    log_view.py          # virtualized log list (Textual ScrollView + line API)
    command_input.py     # Input with history + completion, output area
    filter_panel.py      # ActiveFilters + AvailableTags (clickable lists)
    pick_list.py         # modal checkbox list for `app` and `search` results
    status_bar.py
  model/
    entry.py             # LogEntry dataclass (slots), Level enum
    store.py             # LogStore: entries list, interned tags, ring-buffer cap
    filters.py           # FilterState + FilterEngine (visible index, tag counts)
    search.py            # `search`: tags / messages / PIDs containing a text
  sources/
    base.py              # LogSource protocol
    file_source.py
    adb_source.py        # adb discovery, devices, logcat subprocess (format fallback), `ps`
    resolver.py          # AppResolver: pid -> process name from ps / log lines; app list
  parsing/
    timestamps.py        # timestamp sub-patterns
    layouts.py           # header layouts (threadtime, brief, studio, ...)
    parsers.py           # LineParser implementations, multi-line (long)
    registry.py          # built-in + user formats (formats.toml)
    detect.py            # auto-detection & re-detection
    pipeline.py          # ParserPipeline: lines -> entries (continuations, fallback)
  commands/
    base.py              # Command dataclass, registry, argument parsing helpers
    builtin.py           # help, open, export, format, exit (M1); later commands get own modules
  export.py              # export_entries()
  config.py              # user config dir (platformdirs), history file
tests/
  fixtures/formats/      # one sample file per format/variant (+ bugreport, mixed)
  test_parsers.py test_detect.py test_pipeline.py test_roundtrip.py
  test_sources_and_export.py test_commands.py test_ui.py
```

## Data flow

```
LogSource.lines()  ──►  ParserPipeline  ──►  LogStore.append(batch)
                                                   │
                                     FilterEngine.on_new(batch) ──► visible idx, tag counts
                                                   │
                         Textual messages (EntriesAdded / FilterChanged) ──► widgets refresh
Command input ──► CommandRegistry.dispatch ──► mutate FilterState / sources ──► FilterEngine.rescan
```

- Sources and parsing run in Textual **workers** (asyncio task for adb, thread for file parsing).
- Widgets never touch raw data directly; they query the store/engine by index (log view asks
  for rows `[top, top+height)` only).
- The app holds direct references to its main widgets instead of querying: queries search the
  active screen, which is the `app` dialog while it is open, and live batches keep arriving.
- Commands receive a `CommandContext` (app, store, filter state, source manager, output writer),
  which keeps them testable without the UI.

## Performance

- `LogEntry` uses `__slots__`; tags interned to ints; level stored as small int.
- Visible list = `array('I')` of indexes; rescan in a thread.
- Log view renders only visible rows; colouring done per rendered line.
- Target: open a 1M-line / ~150 MB file in < 10 s, filter change < 1 s, live stream of 5 000
  lines/s without UI lag.
- If pure Python becomes a bottleneck: optional fast path using compiled regexes per layout and
  `re` precheck on first characters; later possibly a Rust/`pyo3` parser module (not planned now).

## Configuration

`platformdirs` user config dir, e.g. `~/.config/alogs/` / `%APPDATA%\alogs\`:

- `config.toml` — ring buffer size, colours, default adb args.
- `formats.toml` — user-defined parsers ([09](09-log-formats-and-parsers.md#33-registry)).
- `history` — command history.

## Testing

- `pytest` for parsing (every fixture), detection, filter semantics (level state machine!),
  commands via `CommandContext` fakes.
- Textual `App.run_test()` / `Pilot` for UI: zone proportions, tag click moves tag between lists,
  click on level/app does nothing, command input history.
- Fake adb (`tests/fake_adb.py`): prints a log file (optionally slowly / forever), answers
  `devices` and `ps`, can reject `-v year`; injected with the `ALOGS_ADB` environment variable.
- `alogs --self-test FILE` runs the real app headless on a file — used to verify wheel installs
  and frozen binaries.

## Packaging & distribution

Decision: local distribution only — no PyPI upload, no CI release pipeline.

- Distribution name `alog-cli` (`alogs` is taken on PyPI by an unrelated project); import package
  and command stay `alogs`. MIT license.
- `pyproject.toml` (hatchling), version read from `alogs/__init__.py`, console script
  `alogs = alogs.__main__:main`, Python ≥ 3.10. The wheel contains `alogs/app.tcss`.
- Dependencies: `textual`, `platformdirs`, `tomli` (py < 3.11). Dependency groups: `dev`
  (pytest), `build` (PyInstaller).
- Install from the checkout: `uv tool install .` / `pipx install .`; `uv build` makes a wheel to
  share.
- `scripts/build_binary.py` builds a one-file PyInstaller executable for the current OS
  (`--collect-submodules textual rich`, since both import modules lazily), names it
  `alogs-<version>-<os>-<arch>` and runs `--self-test` on it. Run it once per OS.
