from __future__ import annotations

import asyncio

from textual.widgets import SelectionList

from alogs.app import AlogsApp
from alogs.widgets.log_view import LogView
from alogs.widgets.pick_list import PickListScreen

from .conftest import FORMATS
from .test_ui import output_text, submit


async def wait_for(pilot, predicate, timeout: float = 10.0) -> None:
    for _ in range(int(timeout / 0.05)):
        await pilot.pause()
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


def rows(app) -> list[tuple[str, str]]:
    sl = app.screen.query_one("#pick-list", SelectionList)
    return [(str(sl.get_option_at_index(i).prompt), sl.get_option_at_index(i).value) for i in range(sl.option_count)]


async def open_search(pilot, line: str) -> None:
    await submit(pilot, line)
    await wait_for(pilot, lambda: isinstance(pilot.app.screen, PickListScreen) or "No " in output_text(pilot.app))


async def loaded_app(pilot) -> AlogsApp:
    app = pilot.app
    await wait_for(pilot, lambda: app._source is not None and not app._loading)
    return app


async def test_search_tags_and_add_to_filter():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 45)) as pilot:
        await loaded_app(pilot)
        await open_search(pilot, "search activity")
        assert [key for _, key in rows(app)] == ["tag:ActivityManager"]
        assert "Found 1 tags with 'activity' in tag names" in output_text(app)
        await pilot.press("space", "ctrl+s")
        await pilot.pause()
        assert app.filters.tags == {"ActivityManager"}
        assert {e.tag for e in app.query_one("#log", LogView).entries if not e.is_separator} == {"ActivityManager"}
        assert "Tags: ActivityManager" in output_text(app)

        # searching again shows the tag ticked; unticking + apply removes it
        await open_search(pilot, "search activity")
        sl = app.screen.query_one("#pick-list", SelectionList)
        assert sl.selected == ["tag:ActivityManager"]
        await pilot.press("space", "ctrl+s")
        await pilot.pause()
        assert app.filters.tags == set()


async def test_search_messages_lists_tag_and_message():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 45)) as pilot:
        await loaded_app(pilot)
        await open_search(pilot, "search -m exception")
        found = rows(app)
        assert [key for _, key in found] == ["tag:AndroidRuntime"]  # distinct tags
        prompt = found[0][0]
        assert prompt.startswith("AndroidRuntime: FATAL EXCEPTION: main")
        assert prompt.endswith("(2)")
        await pilot.press("escape")
        await pilot.pause()
        assert app.filters.tags == set()  # cancel changes nothing


async def test_search_app_adds_pid():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 45)) as pilot:
        await loaded_app(pilot)
        await open_search(pilot, "search -app -m slow")
        found = rows(app)
        assert [key for _, key in found] == ["pid:4321"]
        assert "com.example.app" in found[0][0]  # name from the Start proc line
        assert "OkHttp: slow response: 2034 ms" in found[0][0]
        await pilot.press("space", "ctrl+s")
        await pilot.pause()
        assert app.filters.pids == {4321}
        assert {e.pid for e in app.query_one("#log", LogView).entries if not e.is_separator} == {4321}
        assert "App: pid 4321" in output_text(app)


async def test_search_without_hits_or_log():
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "search x")
        assert "No log loaded" in output_text(app)
        await submit(pilot, f'open "{FORMATS / "threadtime.log"}"')
        await loaded_app(pilot)
        await open_search(pilot, "search -m zzzz-not-there")
        assert "No tags with 'zzzz-not-there' in messages." in output_text(app)
        assert not isinstance(app.screen, PickListScreen)


async def test_tag_command_and_startup_filters():
    app = AlogsApp(
        initial_file=str(FORMATS / "threadtime.log"),
        startup_commands=["levels +E", 'tag +AndroidRuntime "+My Tag With Spaces"'],
    )
    async with app.run_test(size=(160, 45)) as pilot:
        await loaded_app(pilot)
        shown = [e for e in app.query_one("#log", LogView).entries if not e.is_separator]
        assert {e.tag for e in shown} == {"AndroidRuntime"}  # the spaced tag has level I
        assert app.restart_args()[1:] == [
            "--levels=E", "--tag", "AndroidRuntime", "--tag", "My Tag With Spaces",
        ]
