# 08 — Roadmap

## Milestones

### M1 — Parsing core & static viewing ✅ done
- Parser framework, all built-in formats, auto-detection, fixtures + tests ([09](09-log-formats-and-parsers.md)).
- `LogStore`, file source, log zone with virtual scrolling and level colours.
- Command zone with registry: `help`, `open`, `export`, `format`, `exit`.

### M2 — Filtering ✅ done
- `FilterState` / `FilterEngine`, `levels` command with the state machine.
- Filter zone: active filters + available tags, click to toggle.
- Status bar counts.

### M3 — Live & apps ✅ done
- `openadb` with adb discovery, follow mode, ring buffer.
- `AppResolver` (adb `ps`, ActivityManager lines, Studio exports), `app` modal.

### M4 — Packaging ✅ done
- Package `alog-cli` (MIT), local install with `uv tool install .` / `pipx install .`, wheel via
  `uv build`. No public release (decided).
- `scripts/build_binary.py`: one-file PyInstaller binary for the current OS, self-tested.
- `alogs --self-test FILE` to verify installations.

### After M4 — additions ✅ done
- `openadb` saves everything received to `adblog-YYYY-MM-DD-HHMMSS.log` (`--no-save`).
- Filters from the command line: `--levels`, `--tag`, `--app`, `--pid` (+ `--serial`,
  `--no-save` for `--adb`); on exit the matching restart command line is printed.
- `search` (tags / `-m` messages / `-app` PIDs) with a checkbox dialog to add results to the
  filter; `tag` command; `levels none` and comma-separated levels.

## Future ideas

- `find <text>` / `grep <regex>` — text filter and highlight; `n`/`N` to jump between matches.
- Tag exclusion (hide a noisy tag instead of selecting the wanted ones).
- `clear` (clear buffer, live mode), `pause` / `resume`.
- Device picker dialog, `-b` buffers (main/system/crash/events/radio).
- Time range filter (`since 12:00:00`, `until …`).
- Saved filter presets (`save <name>`, `load <name>`).
- Open `.gz` / bugreport `.zip` directly; merge multiple files by timestamp.
- Bookmarks on lines; jump to next error/crash (`FATAL EXCEPTION`, `ANR in`).
- Export in other forms (CSV/JSON).
- CI (GitHub Actions) running the tests and building binaries on all three OSes, if the
  project ever gets a shared repository.

## Open questions

1. `levels` with no arguments: print state (current spec) or reset to all? Reset is `levels all`.
2. `open` while a source is loaded: replace (current spec) or append/merge?
3. `export`: raw original lines (current spec) or re-formatted in one normalized format?
4. Should selected tags whose app is no longer selected be kept or dropped automatically?
5. Live mode default: dump existing device buffer first (current spec) or only new lines (`-T 1`)?
