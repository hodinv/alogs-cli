# alogs — Android Log Analyzer (console)

`alogs` is a cross-platform terminal UI for reading, filtering and exporting Android logs.
It opens saved logcat files (any common logcat / Android Studio format, auto-detected) or streams
live from `adb logcat`, and lets you narrow the view by app/PID, log level and tag using a command
line plus a clickable filter panel.

Features: all common logcat / Android Studio formats auto-detected · level / tag / app filters
with a clickable filter panel · live `adb logcat` with follow mode (saved to a file as it
streams) · `search` in tags, messages and PIDs · export of the filtered view.

## Installation

The package is **`alogs-cli`**, the command it installs is **`alogs`**.

**With [uv](https://docs.astral.sh/uv/)** (recommended — it downloads a suitable Python itself):

```sh
uv tool install alogs-cli
uv tool upgrade alogs-cli      # later updates
```

or with pipx: `pipx install alogs-cli`. Works the same on Windows, macOS and Linux.

**Without Python:** download the single-file binary for your OS from the
[latest release](../../releases/latest) and put it on your PATH:

| OS | File | Notes |
|---|---|---|
| Windows | `alogs-<version>-windows-x86_64.exe` | rename to `alogs.exe`; SmartScreen may ask once (More info → Run anyway) |
| macOS (Apple silicon) | `alogs-<version>-macos-arm64` | `chmod +x`, then `xattr -d com.apple.quarantine <file>` (unsigned) |
| Linux | `alogs-<version>-linux-x86_64` | `chmod +x` |

The binaries unpack themselves to the temp folder on start (about 1 s).

**Check an installation:** `alogs --self-test some.log` opens the log headless and prints e.g.
`alogs 0.1.0 self-test: OK 10 entries, format threadtime - 100%`.

For live mode you need Android platform-tools (`adb`) — already there if Android Studio is
installed.

## Usage

```sh
alogs                     # empty screen, then type commands (`help`)
alogs path/to/log.txt     # open a file
alogs --adb               # live from the device, saved to adblog-YYYY-MM-DD-HHMMSS.log
alogs --adb --serial R58M --no-save
alogs --format brief x.log

# start with filters (same as the levels / tag / app commands; options repeatable)
alogs crash.log --levels W,E --tag AndroidRuntime --tag "My Tag" --app com.example.app --pid 1234
alogs --adb --levels=-D,-V      # values starting with '-' need '='
```

When you quit, alogs prints the command line that reopens the same file/device with the
current filters.

Inside the app, `search` finds tags (`search net`), messages (`search -m timeout`) or the PIDs
logging them (`search -app -m FATAL`) and lets you tick results into the filter. `help` lists
all commands.

`adb` is found on PATH, else via `sdk.dir` in `local.properties` (current folder or a parent,
as in an Android Studio project), else `ANDROID_HOME` / `ANDROID_SDK_ROOT`, else the default SDK
folder.

## Development

```sh
uv sync --all-groups         # .venv with runtime, test and build dependencies
uv run alogs path/to/log.txt # run from source
uv run pytest                # tests
uv tool install .            # install your working copy as the `alogs` command
uv run --group build python scripts/build_binary.py   # single-file binary for this OS
```

Releases are built and published by GitHub Actions when a version tag is pushed — see
[RELEASING.md](RELEASING.md).

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

Note: `openadb` saves the received log to `adblog-*.log` in the current folder; device logs can
contain personal data — use `--no-save` if you don't want that file.

License: MIT (see [LICENSE](LICENSE)) · Author: Vasil Khodzin
