from __future__ import annotations

import asyncio

from textual.widgets import RichLog, Static

from alogs.app import AlogsApp
from alogs.widgets.log_view import LogView

from .conftest import FORMATS


async def submit(pilot, line: str) -> None:
    app = pilot.app
    app.command_input.value = line
    app.command_input.focus()
    await pilot.press("enter")
    await pilot.pause()


async def wait_loaded(pilot, timeout: float = 10.0) -> None:
    app = pilot.app
    for _ in range(int(timeout / 0.02)):
        await pilot.pause()
        if not app._loading:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("load did not finish")


def output_text(app) -> str:
    """Messages written to the output panel, one per line, unwrapped — the panel
    itself wraps long lines (e.g. temp paths) at a width that differs per OS."""
    return "\n".join(app.messages)


def status_text(app) -> str:
    return str(app.query_one("#status", Static).render())


async def test_layout_proportions():
    app = AlogsApp()
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        left = app.query_one("#left")
        filters = app.query_one("#filters")
        assert left.size.width == 140
        assert filters.size.width == 60
        active = app.query_one("#active-filters").outer_size.height
        available = app.query_one("#available-tags").outer_size.height
        total = filters.size.height
        assert abs(active - total * 0.4) <= 1
        assert abs(available - total * 0.6) <= 1
        assert "no log open" in status_text(app)


async def test_open_threadtime_file_and_export(tmp_path):
    app = AlogsApp()
    async with app.run_test(size=(160, 40)) as pilot:
        await submit(pilot, f'open "{FORMATS / "threadtime.log"}"')
        await wait_loaded(pilot)
        log = app.query_one("#log", LogView)
        assert len(app.store) == 10
        assert log.row_count == 12  # 2 stack-trace continuation lines
        assert "format: threadtime · 100%" in status_text(app)  # stack traces are neutral
        assert "Loaded 10 entries" in output_text(app)

        out = tmp_path / "exported.log"
        await submit(pilot, f'export "{out}"')
        assert out.read_text(encoding="utf-8") == (FORMATS / "threadtime.log").read_text(encoding="utf-8")
        await submit(pilot, f'export "{out}"')
        assert "already exists" in output_text(app)


async def test_format_force_and_auto():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 40)) as pilot:
        await wait_loaded(pilot)
        await submit(pilot, "format raw")
        await wait_loaded(pilot)
        assert "raw · forced" in status_text(app)
        assert len(app.store) == 12  # every line is its own entry
        await submit(pilot, "format auto")
        await wait_loaded(pilot)
        assert len(app.store) == 10


async def test_open_errors_and_unknown_command(tmp_path):
    app = AlogsApp()
    async with app.run_test() as pilot:
        await submit(pilot, f'open "{tmp_path / "missing.log"}"')
        await submit(pilot, "frobnicate")
        out = output_text(app)
        assert "File not found" in out
        assert "Unknown command 'frobnicate'" in out


async def test_help_and_history(tmp_path):
    history = tmp_path / "history"
    app = AlogsApp(history_path=history)
    async with app.run_test() as pilot:
        await submit(pilot, "help")
        await submit(pilot, "help open")
        assert "open [-f] <filename>" in output_text(app)
        await pilot.press("up")
        assert app.command_input.value == "help open"
        await pilot.press("up")
        assert app.command_input.value == "help"
        await pilot.press("down", "down")
        assert app.command_input.value == ""
    assert history.read_text(encoding="utf-8").split() == ["help", "help", "open"]


async def test_log_view_scrolls_large_file(tmp_path):
    p = tmp_path / "big.log"
    p.write_text(
        "".join(f"01-02 03:04:05.{i % 1000:03d}  1234  5678 I Tag: line {i}\n" for i in range(20000)),
        encoding="utf-8",
    )
    app = AlogsApp(initial_file=str(p))
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_loaded(pilot)
        log = app.query_one("#log", LogView)
        assert log.row_count == 20000
        log.focus()
        await pilot.press("end")
        await pilot.wait_for_scheduled_animations()
        await pilot.pause()
        assert log.scroll_offset.y > 19000
        last = log.render_line(log.size.height - 1).text
        assert "line 19999" in last


async def test_exit_command():
    app = AlogsApp()
    async with app.run_test() as pilot:
        await submit(pilot, "exit")
        assert app._exit_renderables is not None or not app.is_running


async def test_output_messages_match_the_panel():
    long = "x" * 300  # far wider than the panel: wraps on screen
    app = AlogsApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.write(long)
        app.write_error("boom")
        await pilot.pause()
        panel = app.query_one("#output", RichLog)
        assert len(panel.lines) > 2  # wrapped on screen ...
        assert list(app.messages)[-2:] == [long, "boom"]  # ... but kept whole here
