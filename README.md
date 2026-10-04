# alogs — Android Log Analyzer (console)

`alogs` is a cross-platform terminal UI for reading, filtering and exporting Android logs.
It opens saved logcat files (any common logcat / Android Studio format, auto-detected) or streams
live from `adb logcat`, and lets you narrow the view by app/PID, log level and tag using a command
line plus a clickable filter panel.

> Status: **milestones M1–M4 done** — parsing core (all logcat / Android Studio formats with
> auto-detection), file viewing, level/tag/app filtering with a clickable filter panel, live
> `adb logcat` with follow mode, local packaging (wheel + single-file binaries).
> Commands: `help` / `open` / `openadb` / `export` / `format` / `levels` / `app` / `exit`.

## Installation (local, no package index)

The package is called **`alog-cli`**, the command is **`alogs`**. It is not published anywhere;
install it from a checkout of this repository.

**With Python tooling** — [uv](https://docs.astral.sh/uv/) downloads a suitable Python itself:

```sh
uv tool install .              # from the repository root; `alogs` lands on PATH
uv tool install --reinstall .  # after pulling changes
uv tool uninstall alog-cli
```

`pipx install .` works the same way. To hand the tool to someone else, build a wheel with
`uv build` and give them `dist/alog_cli-<version>-py3-none-any.whl`
(`uv tool install alog_cli-<version>-py3-none-any.whl`).

**Without Python** — build a single-file executable on each OS you need (PyInstaller cannot
cross-compile):

```sh
uv run --group build python scripts/build_binary.py
# -> dist/alogs-<version>-<windows|macos|linux>-<arch>[.exe], self-tested after the build
```

Copy that one file anywhere (e.g. onto PATH) and run it. It unpacks to the temp directory
on start (about 1 s).

**Check an installation:** `alogs --self-test some.log` opens the log headless and prints e.g.
`alogs 0.1.0 self-test: OK 10 entries, format threadtime - 100%` (exit code 0).

## Usage

```sh
alogs                     # empty screen, then type commands (`help`)
alogs path/to/log.txt     # open a file
alogs --adb               # live from the connected device
alogs --format brief x.log
```

`adb` is found on PATH, else via `sdk.dir` in `local.properties` (current folder or a parent,
as in an Android Studio project), else `ANDROID_HOME` / `ANDROID_SDK_ROOT`, else the default SDK
folder.

## Development

```sh
uv sync --all-groups         # .venv with runtime, test and build dependencies
uv run alogs path/to/log.txt # run from source
uv run pytest                # tests
```

## Documentation

| Doc | Content |
|---|---|
| [01 – Overview](docs/01-overview.md) | Goals, non-goals, platforms, glossary |
| [02 – UI layout](docs/02-ui-layout.md) | Screen zones, mockup, mouse/keyboard interaction |
| [03 – Commands](docs/03-commands.md) | Command reference |
| [04 – Filtering model](docs/04-filtering-model.md) | Filter state and rules (levels, tags, apps) |
| [05 – Log sources](docs/05-log-sources-and-parsing.md) | File / adb sources, package↔PID resolution, encoding |
| [06 – Architecture](docs/06-architecture.md) | Python + Textual module layout, data flow, performance, testing, packaging |
| [07 – Tech stack decision](docs/07-tech-stack-decision.md) | Node.js vs Python vs Kotlin comparison (ADR) |
| [08 – Roadmap](docs/08-roadmap.md) | Milestones, future ideas, open questions |
| [09 – Log formats & parsers](docs/09-log-formats-and-parsers.md) | Format catalog, pluggable parsers, auto-detection |

Requirements at runtime: a modern terminal (Windows Terminal, iTerm2, any xterm-compatible),
and Android platform-tools (`adb`) for live mode.

License: MIT (see [LICENSE](LICENSE)).
