from __future__ import annotations

import asyncio
import shlex
import subprocess
import sys

import pytest

from alogs import __version__
from alogs.__main__ import build_parser, main, startup_commands
from alogs.app import AlogsApp
from alogs.model.entry import Level

from .conftest import FORMATS


def test_self_test_ok(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--self-test", str(FORMATS / "threadtime.log")])
    assert exit_info.value.code == 0
    assert f"alogs {__version__} self-test: OK 10 entries, format threadtime - 100%" in capsys.readouterr().out


def test_self_test_missing_file(capsys, tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        main(["--self-test", str(tmp_path / "missing.log")])
    assert exit_info.value.code == 1
    assert "FAILED could not open" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"alogs {__version__}"


def test_filter_options_become_commands():
    args = build_parser().parse_args(
        ["x.log", "--levels", "W,E", "--tag", "MyTag", "--tag", "My Tag", "--app", "com.x", "--pid", "42"]
    )
    assert startup_commands(args) == ["levels W,E", 'tag +MyTag "+My Tag"', "app +com.x +42"]
    args = build_parser().parse_args(["--levels=-D,-V", "--levels", "+F"])
    assert startup_commands(args) == ["levels -D,-V +F"]
    assert startup_commands(build_parser().parse_args([])) == []


def split_printed(line: str) -> list[str]:
    """Parse the printed restart command the way the user's shell would."""
    if sys.platform == "win32":
        # cmd-style quoting from list2cmdline: CommandLineToArgvW rules
        import ctypes
        from ctypes import wintypes

        argc = ctypes.c_int()
        fn = ctypes.windll.shell32.CommandLineToArgvW
        fn.restype = ctypes.POINTER(wintypes.LPWSTR)
        argv = fn(line, ctypes.byref(argc))
        return [argv[i] for i in range(argc.value)]
    return shlex.split(line)


def test_restart_line_round_trip(monkeypatch, capsys):
    """Start with filters from the command line, quit, and check that the
    printed command line parses back to the same source and filters."""
    original_run = AlogsApp.run
    seen = {}

    async def quit_when_loaded(pilot):
        app = pilot.app
        for _ in range(200):
            await pilot.pause()
            if app._source is not None and not app._loading:
                break
            await asyncio.sleep(0.05)
        seen["levels"] = set(app.filters.levels)
        seen["tags"] = set(app.filters.tags)
        seen["pids"] = set(app.filters.pids)
        seen["packages"] = set(app.filters.packages)
        seen["shown"] = len(app.engine.visible)
        app.exit()

    monkeypatch.setattr(
        AlogsApp, "run", lambda self, **kw: original_run(self, headless=True, auto_pilot=quit_when_loaded)
    )
    log = FORMATS / "threadtime.log"
    main([str(log), "--levels", "W,E", "--tag", "AndroidRuntime", "--tag", "My Tag With Spaces",
          "--app", "com.example.app", "--pid", "1000"])

    assert seen["levels"] == {Level.WARN, Level.ERROR}
    assert seen["tags"] == {"AndroidRuntime", "My Tag With Spaces"}
    assert seen["pids"] == {1000} and seen["packages"] == {"com.example.app"}
    assert seen["shown"] == 4  # 2 AndroidRuntime errors of pid 4321 + 2 separators

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "To start again with the same source and filters:"
    printed = out[1].strip()
    assert printed.startswith("alogs ")
    argv = split_printed(printed)[1:]
    again = build_parser().parse_args(argv)
    assert again.file == str(log.resolve())
    assert again.levels == ["W,E"]
    assert again.tag == ["AndroidRuntime", "My Tag With Spaces"]
    assert again.app == ["com.example.app"] and again.pid == [1000]


def test_no_restart_line_without_source_or_filters(monkeypatch, capsys):
    original_run = AlogsApp.run

    async def quit_now(pilot):
        await pilot.pause()
        pilot.app.exit()

    monkeypatch.setattr(AlogsApp, "run", lambda self, **kw: original_run(self, headless=True, auto_pilot=quit_now))
    main([])
    assert capsys.readouterr().out == ""


def test_windows_quoting_is_list2cmdline():
    from alogs.__main__ import quote

    if sys.platform == "win32":
        assert quote("My Tag") == subprocess.list2cmdline(["My Tag"]) == '"My Tag"'
    else:
        assert quote("My Tag") == "'My Tag'"
