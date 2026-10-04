from __future__ import annotations

import pytest

from alogs.commands import CommandError, default_commands
from alogs.commands.base import split_args
from alogs.model.entry import Level
from alogs.model.filters import ALL_LEVELS, FilterState
from alogs.parsing.detect import Detection


class FakeContext:
    def __init__(self, registry):
        self.commands = default_commands()
        self.parsers = registry
        self.output: list[str] = []
        self.opened: list[tuple[str, bool]] = []
        self.exported: list[tuple[str, bool]] = []
        self.format: str | None = "unset"
        self.exited = False
        self.export_error: Exception | None = None
        self.filters = FilterState()
        self.filter_changes = 0
        self.adb_opened: list[str | None] = []
        self.dialogs = 0
        self.searches: list[tuple[str, bool, bool]] = []

    def filters_changed(self):
        self.filter_changes += 1

    def open_adb(self, serial=None, save=True):
        self.adb_opened.append((serial, save))

    def search(self, text, in_messages=False, by_app=False):
        self.searches.append((text, in_messages, by_app))

    def apps(self):
        from alogs.sources.resolver import AppInfo

        return [AppInfo("com.a", (10, 11), 3), AppInfo(None, (30,), 1)]

    def select_apps(self, packages, pids):
        self.filters.packages, self.filters.pids = set(packages), set(pids)

    def show_app_dialog(self):
        self.dialogs += 1

    def app_filter_text(self):
        return "TEXT"

    def write(self, text):
        self.output.append(text)

    def open_file(self, path, force=False):
        self.opened.append((path, force))

    def export(self, path, overwrite=False):
        if self.export_error:
            raise self.export_error
        self.exported.append((path, overwrite))
        return 42

    def current_format(self):
        return Detection("threadtime", 0.98, ["year"])

    def set_format(self, parser_id):
        self.format = parser_id

    def exit(self):
        self.exited = True


@pytest.fixture
def ctx(registry):
    return FakeContext(registry)


def run(ctx, line):
    ctx.commands.dispatch(ctx, line)
    return "\n".join(ctx.output)


def test_split_args_keeps_windows_paths():
    assert split_args(r'open "C:\Users\me\my log.txt"') == ["open", r"C:\Users\me\my log.txt"]
    assert split_args(r"open C:\logs\a.txt") == ["open", r"C:\logs\a.txt"]


def test_help_lists_all_commands(ctx):
    out = run(ctx, "help")
    for name in ("help", "open", "export", "format", "levels", "exit"):
        assert name in out


def test_help_for_command_and_alias(ctx):
    assert "open [-f] <filename>" in run(ctx, "help open")
    assert "Aliases: quit, q" in run(ctx, "HELP exit")
    with pytest.raises(CommandError, match="No such command"):
        run(ctx, "help nope")


def test_unknown_command(ctx):
    with pytest.raises(CommandError, match="Unknown command 'xyz'"):
        run(ctx, "xyz")


def test_empty_line_is_ignored(ctx):
    run(ctx, "   ")
    assert ctx.output == []


def test_open(ctx):
    run(ctx, 'open "my file.log"')
    run(ctx, "open -f bin.dat")
    assert ctx.opened == [("my file.log", False), ("bin.dat", True)]
    with pytest.raises(CommandError, match="Usage"):
        run(ctx, "open")


def test_export(ctx):
    assert "Exported 42 entries" in run(ctx, "export out.log")
    run(ctx, "export -f out.log")
    assert ctx.exported == [("out.log", False), ("out.log", True)]
    ctx.export_error = FileExistsError()
    with pytest.raises(CommandError, match="export -f"):
        run(ctx, "export out.log")


def test_format(ctx):
    assert "threadtime (year) · 98%" in run(ctx, "format")
    assert "studio-legacy" in run(ctx, "format list")
    run(ctx, "format brief")
    assert ctx.format == "brief"
    run(ctx, "format auto")
    assert ctx.format is None
    with pytest.raises(CommandError, match="Unknown format"):
        run(ctx, "format nope")


def test_exit_aliases(ctx):
    run(ctx, "q")
    assert ctx.exited


def test_levels_show(ctx):
    assert run(ctx, "levels") == "Levels: all"
    assert ctx.filter_changes == 0


def test_levels_first_plus_selects_only(ctx):
    assert run(ctx, "levels +ERROR").endswith("Levels: E")
    assert ctx.filters.levels == {Level.ERROR}
    run(ctx, "levels +w")
    assert ctx.filters.levels == {Level.WARN, Level.ERROR}
    assert ctx.filter_changes == 2


def test_levels_first_minus_removes_only(ctx):
    run(ctx, "levels -DEBUG -verbose")
    assert ctx.filters.levels == set(ALL_LEVELS) - {Level.DEBUG, Level.VERBOSE}


def test_levels_multiple_args_left_to_right(ctx):
    run(ctx, "levels +W +E")
    assert ctx.filters.levels == {Level.WARN, Level.ERROR}


def test_levels_bare_name_means_plus(ctx):
    run(ctx, "levels warning")
    assert ctx.filters.levels == {Level.WARN}


def test_levels_all_resets(ctx):
    run(ctx, "levels +E")
    assert run(ctx, "levels all").endswith("Levels: all")
    assert not ctx.filters.levels_touched
    run(ctx, "levels +E")
    run(ctx, "levels *")
    assert not ctx.filters.levels_touched


def test_levels_typo_changes_nothing(ctx):
    with pytest.raises(CommandError, match="Unknown level 'XYZ'"):
        run(ctx, "levels +E XYZ")
    assert not ctx.filters.levels_touched
    with pytest.raises(CommandError):
        run(ctx, "levels +")


def test_openadb(ctx):
    run(ctx, "openadb")
    run(ctx, "openadb -s emulator-5554")
    run(ctx, "openadb --no-save -s emulator-5554")
    assert ctx.adb_opened == [(None, True), ("emulator-5554", True), ("emulator-5554", False)]
    with pytest.raises(CommandError, match="Usage"):
        run(ctx, "openadb emulator-5554")


def test_app_dialog_and_list(ctx):
    run(ctx, "app")
    assert ctx.dialogs == 1
    out = run(ctx, "app list")
    assert "com.a  (10, 11)  3 entries" in out
    assert "pid 30  1 entries" in out


def test_app_selection_forms(ctx):
    run(ctx, "app com.a")
    assert (ctx.filters.packages, ctx.filters.pids) == ({"com.a"}, set())
    run(ctx, "app +30 +com.b")
    assert (ctx.filters.packages, ctx.filters.pids) == ({"com.a", "com.b"}, {30})
    run(ctx, "app -com.a -30")
    assert (ctx.filters.packages, ctx.filters.pids) == ({"com.b"}, set())
    run(ctx, "app 42")  # bare value replaces the selection
    assert (ctx.filters.packages, ctx.filters.pids) == (set(), {42})
    assert run(ctx, "app all").endswith("App: TEXT")
    assert (ctx.filters.packages, ctx.filters.pids) == (set(), set())
    with pytest.raises(CommandError, match="Usage"):
        run(ctx, "app +")


def test_levels_none_and_commas(ctx):
    run(ctx, "levels none")
    assert ctx.filters.levels_touched and ctx.filters.levels == set()
    run(ctx, "levels all")
    run(ctx, "levels W,E")
    assert ctx.filters.levels == {Level.WARN, Level.ERROR}
    run(ctx, "levels all")
    run(ctx, "levels -D,-V")
    assert ctx.filters.levels == set(ALL_LEVELS) - {Level.DEBUG, Level.VERBOSE}


def test_tag_command(ctx):
    assert run(ctx, "tag") == "Tags: all"
    run(ctx, 'tag MyTag "My Tag"')
    assert ctx.filters.tags == {"MyTag", "My Tag"}
    run(ctx, "tag +OkHttp -MyTag")
    assert ctx.filters.tags == {"My Tag", "OkHttp"}
    assert run(ctx, "tag all").endswith("Tags: all")
    assert ctx.filters.tags == set()
    assert ctx.filter_changes == 3
    with pytest.raises(CommandError):
        run(ctx, "tag +")


def test_search_command_flags(ctx):
    run(ctx, "search net")
    run(ctx, "search -m connection timed out")
    run(ctx, "search -app -m FATAL")
    run(ctx, "search -APP Activity")
    assert ctx.searches == [
        ("net", False, False),
        ("connection timed out", True, False),
        ("FATAL", True, True),
        ("Activity", False, True),
    ]
    with pytest.raises(CommandError, match="Usage: search"):
        run(ctx, "search -m")
