from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from alogs import app as app_module
from alogs.app import AlogsApp
from alogs.model.entry import Level
from alogs.widgets.filter_panel import TagList
from alogs.widgets.log_view import LogView

from .conftest import FORMATS
from .test_ui import output_text, status_text, submit


async def wait_idle(pilot, timeout: float = 10.0) -> None:
    app = pilot.app
    for _ in range(int(timeout / 0.02)):
        await pilot.pause()
        if not app._loading and not app._filtering:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("app did not become idle")


def tag_names(app, list_id: str) -> list[str]:
    tag_list = app.query_one(f"#{list_id}", TagList)
    return [tag_list.get_option_at_index(i).id[2:] for i in range(tag_list.option_count)]


def shown_tags(app) -> set:
    return {e.tag for e in app.query_one("#log", LogView).entries if not e.is_separator}


@pytest.fixture
def threadtime_app():
    return AlogsApp(initial_file=str(FORMATS / "threadtime.log"))


async def test_available_tags_sorted_by_count(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        available = tag_names(app, "tag-list")
        assert available[0] == "AndroidRuntime"  # 2 entries, the rest have 1
        assert set(available) == {
            "MyTag", "ActivityManager", "OkHttp", "AndroidRuntime", "chromium", "My Tag With Spaces", "EmptyMsg",
        }
        assert tag_names(app, "selected-tags") == []
        assert "shown 10 of 10 entries" in status_text(app)


async def test_click_tag_selects_and_click_again_unselects(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        await pilot.click("#tag-list", offset=(2, 0))  # AndroidRuntime
        await wait_idle(pilot)
        assert app.filters.tags == {"AndroidRuntime"}
        assert tag_names(app, "selected-tags") == ["AndroidRuntime"]
        assert "AndroidRuntime" not in tag_names(app, "tag-list")
        assert shown_tags(app) == {"AndroidRuntime"}
        assert "shown 4 of 10 entries" in status_text(app)  # 2 + 2 separators

        await pilot.click("#selected-tags", offset=(2, 0))
        await wait_idle(pilot)
        assert app.filters.tags == set()
        assert tag_names(app, "selected-tags") == []
        assert "AndroidRuntime" in tag_names(app, "tag-list")
        assert "shown 10 of 10 entries" in status_text(app)


async def test_clicking_levels_summary_does_nothing(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        await submit(pilot, "levels +E")
        await wait_idle(pilot)
        before = (set(app.filters.levels), set(app.filters.tags))
        for row in range(3):
            await pilot.click("#active-summary", offset=(2, row))
        await wait_idle(pilot)
        assert (set(app.filters.levels), set(app.filters.tags)) == before


async def test_levels_command_filters_log_and_tags(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        await submit(pilot, "levels +W +E")
        await wait_idle(pilot)
        levels = {e.level for e in app.query_one("#log", LogView).entries if not e.is_separator}
        assert levels == {Level.WARN, Level.ERROR}
        assert set(tag_names(app, "tag-list")) == {"OkHttp", "AndroidRuntime"}
        summary = str(app.query_one("#active-summary", Static).render())
        assert "Levels:" in summary
        assert "Levels: W E" in output_text(app)

        await submit(pilot, "levels -W -E")
        await wait_idle(pilot)
        assert app.query_one("#log", LogView).border_subtitle.startswith("no levels enabled")
        await submit(pilot, "levels all")
        await wait_idle(pilot)
        assert "shown 10 of 10 entries" in status_text(app)
        assert app.query_one("#log", LogView).border_subtitle == ""


async def test_export_writes_only_filtered(threadtime_app, tmp_path):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        await submit(pilot, "levels +E")
        await wait_idle(pilot)
        out = tmp_path / "errors.log"
        await submit(pilot, f'export "{out}"')
        lines = out.read_text(encoding="utf-8").splitlines()
        assert [line for line in lines if not line.startswith("-") and not line.startswith("\t")] == [
            "01-02 03:04:05.701  4321  4321 E AndroidRuntime: FATAL EXCEPTION: main",
            "01-02 03:04:05.701  4321  4321 E AndroidRuntime: java.lang.IllegalStateException: boom",
        ]
        assert "\tat com.example.Foo.bar(Foo.kt:12)" in lines  # continuation lines follow their entry


async def test_tag_search_narrows_available_list(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        app.query_one("#tag-search").value = "act"
        await pilot.pause()
        assert tag_names(app, "tag-list") == ["ActivityManager"]


async def test_filters_survive_open_of_another_file(threadtime_app):
    app = threadtime_app
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        await submit(pilot, "levels +E")
        await submit(pilot, f'open "{FORMATS / "brief.log"}"')
        await wait_idle(pilot)
        entries = app.query_one("#log", LogView).entries
        assert [e.tag for e in entries] == ["AndroidRuntime"]


async def test_large_log_filters_in_worker_and_keeps_position(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "SYNC_FILTER_LIMIT", 0)
    p = tmp_path / "big.log"
    p.write_text(
        "".join(
            f"01-02 03:04:05.{i % 1000:03d}  1234  5678 {'DIWE'[i % 4]} Tag{i % 4}: line {i}\n"
            for i in range(4000)
        ),
        encoding="utf-8",
    )
    app = AlogsApp(initial_file=str(p))
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_idle(pilot)
        log = app.query_one("#log", LogView)
        log.scroll_to(None, 2000, animate=False, immediate=True)
        await pilot.pause()
        top = log.top_seq()
        assert top == 2000
        await submit(pilot, "levels +E")
        await wait_idle(pilot)
        assert len(log.entries) == 1000
        # the first error entry at/after the old top is now at the top
        assert log.top_seq() == 2003
        assert {e.level for e in log.entries} == {Level.ERROR}
