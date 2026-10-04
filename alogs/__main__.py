"""Entry point: `alogs [file] [--adb] [--format ID]`."""

from __future__ import annotations

import argparse
import asyncio
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="alogs", description="Console analyzer for Android logs")
    parser.add_argument("file", nargs="?", help="log file to open")
    parser.add_argument("--adb", action="store_true", help="start reading live from adb logcat")
    parser.add_argument("--format", metavar="ID", help="force a log format (see 'format list')")
    parser.add_argument("--self-test", metavar="FILE", help="open FILE headless, print a summary and exit")
    parser.add_argument("--version", action="version", version=f"alogs {__version__}")
    args = parser.parse_args(argv)

    if args.self_test:
        sys.exit(self_test(args.self_test))

    from .app import AlogsApp

    AlogsApp(
        initial_file=args.file,
        forced_format=args.format,
        initial_adb=args.adb,
        history_path=config.history_file(),
    ).run()


if __name__ == "__main__":
    main()
