"""Entry point: `alogs [file] [--adb] [filters...]`."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import subprocess
import sys

from . import __version__, config


def self_test(path: str) -> int:
    """Run the full app headless, open `path`, print a summary.

    Used to verify an installed package or a frozen binary (all modules,
    CSS and widgets load). Exit code 0 on success.
    """
    from .app import AlogsApp

    async def pilot_script(pilot) -> None:
        app = pilot.app
        for _ in range(600):  # up to ~60 s
            await pilot.pause()
            # `open` runs at mount: no source afterwards means it failed
            if app._source is None or not app._loading:
                break
            await asyncio.sleep(0.1)
        if app._source is None:
            app.exit(f"FAILED could not open {path} (missing or unreadable)")
            return
        fmt = app.current_format()
        ok = not app._loading and len(app.store) > 0
        # plain ASCII: legacy Windows consoles cannot print "·"
        described = fmt.describe().replace("·", "-") if fmt else "?"
        app.exit(f"{'OK' if ok else 'FAILED'} {len(app.store)} entries, format {described}")

    app = AlogsApp(initial_file=path)
    result = app.run(headless=True, auto_pilot=pilot_script)
    print(f"alogs {__version__} self-test: {result}")
    return 0 if isinstance(result, str) and result.startswith("OK") else 1


def quote(token: str) -> str:
    """Quote one argument for the user's shell (cmd/PowerShell or POSIX)."""
    if os.name == "nt":
        return subprocess.list2cmdline([token])
    return shlex.quote(token)


def command_quote(token: str) -> str:
    """Quote one argument for alogs' own command line (double quotes)."""
    return f'"{token}"' if any(c.isspace() for c in token) or not token else token


def startup_commands(args: argparse.Namespace) -> list[str]:
    """Filter options -> the equivalent alogs commands, run before opening."""
    lines = []
    if args.levels:
        lines.append(f"levels {' '.join(args.levels)}")
    if args.tag:
        lines.append("tag " + " ".join(command_quote("+" + t) for t in args.tag))
    apps = [*(args.app or []), *(str(p) for p in args.pid or [])]
    if apps:
        lines.append("app " + " ".join(command_quote("+" + a) for a in apps))
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alogs",
        description="Console analyzer for Android logs",
        epilog="Values starting with '-' need '=': --levels=-D,-V",
    )
    parser.add_argument("file", nargs="?", help="log file to open")
    parser.add_argument("--adb", action="store_true", help="start reading live from adb logcat")
    parser.add_argument("--serial", "-s", metavar="SERIAL", help="device serial for --adb")
    parser.add_argument("--no-save", action="store_true", help="with --adb: don't save adblog-*.log")
    parser.add_argument("--format", metavar="ID", help="force a log format (see 'format list')")
    filters = parser.add_argument_group("filters (same as the commands levels / tag / app)")
    filters.add_argument("--levels", action="append", metavar="LEVELS", help="e.g. W,E  or  =-D,-V  or none")
    filters.add_argument("--tag", action="append", metavar="TAG", help="show this tag (repeatable)")
    filters.add_argument("--app", action="append", metavar="PACKAGE", help="show this app (repeatable)")
    filters.add_argument("--pid", action="append", type=int, metavar="PID", help="show this PID (repeatable)")
    parser.add_argument("--self-test", metavar="FILE", help="open FILE headless, print a summary and exit")
    parser.add_argument("--version", action="version", version=f"alogs {__version__}")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.self_test:
        sys.exit(self_test(args.self_test))

    from .app import AlogsApp

    app = AlogsApp(
        initial_file=args.file,
        forced_format=args.format,
        initial_adb=args.adb,
        initial_serial=args.serial,
        save_adb=not args.no_save,
        startup_commands=startup_commands(args),
        history_path=config.history_file(),
    )
    app.run()
    restart = app.restart_args()
    if restart:
        print("To start again with the same source and filters:")
        print("  alogs " + " ".join(quote(a) for a in restart))


if __name__ == "__main__":
    main()
