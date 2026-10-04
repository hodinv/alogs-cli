# 03 — Commands

Commands are typed in the command zone. Names are case-insensitive; arguments are space-separated,
quotes allowed for paths with spaces (`open "C:\logs\my log.txt"`). Each command is registered in
the command registry with its name, short help, long help and handler (see
[06](06-architecture.md)), so `help` is generated automatically.

Unknown command → `Unknown command 'xyz'. Type 'help' for the list.`

---

## `help`

```
help
help <command>
```

- Without argument: list of all commands with a one-line description.
- With argument: syntax, description and examples for that command.

Errors: `help foo` → `No such command 'foo'.`

---

## `open [-f] <filename>`

Open a log file as the current source. Replaces the current source (live adb is stopped);
filters are kept, except app/PID selections that no longer exist.

- Format is auto-detected ([09](09-log-formats-and-parsers.md)); detected format shown in status bar.
- Loading is incremental — the UI is usable while a big file is still being parsed (progress in
  status bar).
- Relative paths are resolved against the working directory; `~` is expanded.

Examples:

```
open crash.log
open "C:\Users\me\Desktop\logcat 2024-01-02.txt"
```

- Encoding: UTF-8 (with or without BOM), UTF-16 with BOM, and UTF-16 without BOM are detected.

Errors: file not found, not a file, not readable, binary file (refused unless `-f` is given).

---

## `openadb [-s <serial>]`

Start reading live from the device via `adb logcat`. Also available as `alogs --adb`.

- Runs `adb logcat -v threadtime -v year -v usec` (see [05](05-log-sources-and-parsing.md)).
- If several devices are connected, an error lists them; pick one with `openadb -s <serial>`.
- Connecting runs in the background; the current log stays usable until the device answers.
- Starts with the device's existing buffer, then follows new lines. Follow mode is on
  (status bar `LIVE`; scrolling up shows `PAUSED (End to follow)`).
- When adb exits or the device disconnects, the output shows `adb logcat stopped (exit code N)`
  with adb's message, the status bar shows `STOPPED`; entries stay in memory.
- Filters are kept; the device's `ps` process list is read every 5 s for `app`.

`adb` lookup: PATH → `sdk.dir` in `local.properties` (current folder or a parent) →
`ANDROID_HOME` / `ANDROID_SDK_ROOT` → default SDK folder (details in
[05](05-log-sources-and-parsing.md#adb-source-openadb)).

Errors: `adb not found …`, `no devices/emulators found`, `more than one device: … — use
'openadb -s <serial>'`, `device … is unauthorized — accept the USB debugging prompt`,
`device … is offline`.

---

## `exit`

Exit the application (stops adb if running). Aliases: `quit`, `q`.

---

## `export [-f] <filename>`

Write the **currently filtered** entries to a file, as their original raw text (including
continuation lines), UTF-8, `\n` line endings — i.e. what the app/level/tag filters show.

- If the file exists, the command fails with a hint; `export -f <filename>` overwrites.
- Reports number of entries written.

Example: `export only-errors.log`

---

## `levels [+|-]LEVEL ...`

Switch log levels on or off.

Level names (case-insensitive): `V`/`VERBOSE`, `D`/`DEBUG`, `I`/`INFO`, `W`/`WARN`/`WARNING`,
`E`/`ERROR`, `F`/`FATAL`, `A`/`ASSERT`. A bare name means `+`.

Semantics (detailed in [04](04-filtering-model.md#levels)):

- Initially all levels are on ("untouched" state).
- First change from the untouched state:
  - `+X` → **only** X is on, all others off.
  - `-X` → X off, all others stay on.
- Afterwards `+X` / `-X` just add / remove X.
- Several arguments are applied left to right: `levels +W +E` → only W and E.
- `levels` with no arguments prints the current state.
- `levels all` (or `levels *`) → back to the untouched state (all on).

Examples:

```
levels +ERROR          # only errors
levels +WARN           # now warnings and errors
levels -DEBUG          # (from untouched) everything except debug
levels all             # reset
```

Errors: `Unknown level 'XYZ'`.

---

## `app`

```
app                          checkbox dialog
app list                     print apps with PIDs and entry counts
app all                      show all apps again
app com.example.app 1234     show only these apps / PIDs (bare values replace the selection)
app +1234 -com.example.app   add / remove to the current selection
```

Show the list of apps found in the current log and select/unselect them.

- The dialog lists one row per app (most entries first): name, its PIDs, entry count.
  Processes like `com.pkg:remote` are grouped under `com.pkg`.
  - adb source: names resolved from the device process list (`ps`).
  - file source: names derived from the log itself (`ActivityManager: Start proc` / `Process …
    has died` lines, `am_proc_start` events, Android Studio exports); otherwise rows are bare PIDs.
- `Space`/`Enter`/click toggles a row, `Ctrl+S` or **Apply** applies, `Esc` or **Cancel**
  cancels, **Clear** unselects all. A search box filters the rows by name or PID.
- Nothing selected = all apps shown. Selecting an app covers all its PIDs, including PIDs that
  appear later (app restarts); before any PID is known, the app filter shows nothing.

---

## `format [list | auto | <id>]`

Inspect or override the log format parser ([09](09-log-formats-and-parsers.md)).

- `format` → current format id and how it was chosen (auto-detected with N% match, or forced).
- `format list` → all available parsers (built-in and user-defined) with a sample line.
- `format <id>` → force that parser and re-parse the current source.
- `format auto` → back to auto-detection.

---

## Adding a command (for implementers)

Create a module in `alogs/commands/`, define a `Command` with `name`, `aliases`, `summary`,
`help`, `handler(ctx, args)`, and register it. Nothing else needs changing. Future candidates are
listed in [08](08-roadmap.md).
