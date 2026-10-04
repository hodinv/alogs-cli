from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from textual.widgets import SelectionList

from alogs.app import AlogsApp
from alogs.sources import adb_source
from alogs.widgets.app_select import AppSelectScreen
from alogs.widgets.log_view import LogView

from .conftest import FORMATS
from .test_ui import output_text, status_text, submit

FAKE_ADB = Path(__file__).parent / "fake_adb.py"


def tt(i: int, pid: int = 4321, tag: str = "MyTag", level: str = "I") -> str:
    return f"2024-01-02 03:04:05.{i % 1000:03d}000  {pid:5d}  {pid:5d} {level} {tag:<8}: line {i}"


@pytest.fixture
def device(tmp_path, monkeypatch):
    """Configure the fake adb; returns a function writing the device log."""
    log = tmp_path / "device.log"
    ps = tmp_path / "ps.txt"
    ps.write_text("PID NAME\n 1234 system_server\n 4321 com.example.app\n", encoding="utf-8")
    monkeypatch.setenv("ALOGS_ADB", f'"{sys.executable}" "{FAKE_ADB}"')
    monkeypatch.setenv("FAKE_ADB_LOG", str(log))
    monkeypatch.setenv("FAKE_ADB_PS", str(ps))
    for var in ("FAKE_ADB_HANG", "FAKE_ADB_NO_MODIFIERS", "FAKE_ADB_DELAY", "FAKE_ADB_EXIT", "FAKE_ADB_DEVICES"):
        monkeypatch.delenv(var, raising=False)

    def write(lines: list[str], delay: float = 0.0, hang: bool = False) -> None:
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if delay:
            monkeypatch.setenv("FAKE_ADB_DELAY", str(delay))
        if hang:
            monkeypatch.setenv("FAKE_ADB_HANG", "1")

    return write


async def wait_until(pilot, predicate, timeout: float = 15.0, what: str = "condition") -> None:
    for _ in range(int(timeout / 0.05)):
        await pilot.pause()
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}; status: {status_text(pilot.app)}")


async def test_openadb_streams_until_device_goes_away(device):
    device([tt(i) for i in range(30)])
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: "STOPPED" in status_text(app), what="stop")
        assert len(app.store) == 30
        status = status_text(app)
        assert "adb emulator-5554" in status
        assert "format: threadtime (year, usec)" in status
        out = output_text(app)
        assert "Reading live log from emulator-5554" in out
        assert "adb logcat stopped (exit code 0) — logcat: device went away" in out


async def test_live_follow_pause_and_resume(device):
    device([tt(i) for i in range(400)], delay=0.005, hang=True)
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "openadb")
        log = app.query_one("#log", LogView)
        await wait_until(pilot, lambda: len(app.store) > 100, what="first lines")
        assert "LIVE" in status_text(app)
        assert log.at_bottom and log.scroll_offset.y > 0  # following

        log.scroll_to(None, 10, animate=False, immediate=True)
        await pilot.pause()
        assert "PAUSED" in status_text(app)
        count = len(app.store)
        await wait_until(pilot, lambda: len(app.store) > count + 50, what="more lines")
        assert log.scroll_offset.y == 10  # paused: view does not move

        log.focus()
        await pilot.press("end")
        await pilot.wait_for_scheduled_animations()
        await wait_until(pilot, lambda: "LIVE" in status_text(app), what="resume")
        await wait_until(pilot, lambda: len(app.store) == 400, what="all lines")
        await pilot.pause()
        assert log.at_bottom


async def test_live_ring_buffer(device):
    device([tt(i) for i in range(300)])
    app = AlogsApp(live_max_entries=50)
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: "STOPPED" in status_text(app), what="stop")
        assert 50 <= len(app.store) <= 55
        assert app.store.dropped == 300 - len(app.store)
        assert app.store.entries[-1].message == "line 299"
        assert f"dropped {app.store.dropped}" in status_text(app)
        log = app.query_one("#log", LogView)
        assert log.entries == app.store.entries


async def test_app_filter_uses_device_process_list(device):
    lines = []
    for i in range(40):
        lines.append(tt(i, pid=4321 if i % 2 else 1234, tag="App" if i % 2 else "Sys"))
    device(lines, delay=0.01, hang=True)
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "app com.example.app")
        assert "com.example.app (no PIDs yet)" in output_text(app)
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: len(app.store) == 40, what="all lines")
        await wait_until(pilot, lambda: app.resolver.name_of(4321) == "com.example.app", what="ps")
        await pilot.pause()
        log = app.query_one("#log", LogView)
        assert log.entries and {e.pid for e in log.entries} == {4321}
        assert set(app.engine.tag_counts) == {"App"}  # tags scoped to the selected app


async def test_openadb_errors(device, monkeypatch):
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        monkeypatch.setenv("FAKE_ADB_DEVICES", "a:device,b:device")
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: "more than one device" in output_text(app), what="error")
        assert "no log open" in status_text(app)

        monkeypatch.setenv("FAKE_ADB_DEVICES", "none")
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: "no devices/emulators found" in output_text(app), what="error")

        monkeypatch.delenv("ALOGS_ADB")
        monkeypatch.setattr(adb_source.shutil, "which", lambda name: None)
        monkeypatch.setattr(adb_source, "_sdk_dirs", lambda: [])
        await submit(pilot, "openadb")
        assert "adb not found" in output_text(app)


async def test_openadb_falls_back_on_old_devices(device, monkeypatch):
    device(["01-02 03:04:05.678  1234  5678 D MyTag   : old device"])
    monkeypatch.setenv("FAKE_ADB_NO_MODIFIERS", "1")
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: "STOPPED" in status_text(app), what="stop")
        assert [e.message for e in app.store.entries] == ["old device"]


async def test_app_command_on_file_uses_start_proc_lines():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_until(pilot, lambda: not app._loading, what="load")
        await submit(pilot, "app list")
        assert "com.example.app  (4321)  3 entries" in output_text(app)
        await submit(pilot, "app com.example.app")
        entries = [e for e in app.query_one("#log", LogView).entries if not e.is_separator]
        assert {e.pid for e in entries} == {4321}
        summary = str(app.query_one("#active-summary").render())
        assert "com.example.app (4321)" in summary


async def test_app_dialog_select_apply_and_cancel():
    app = AlogsApp(initial_file=str(FORMATS / "threadtime.log"))
    async with app.run_test(size=(160, 45)) as pilot:
        await wait_until(pilot, lambda: not app._loading, what="load")
        await submit(pilot, "app")
        await pilot.pause()
        assert isinstance(app.screen, AppSelectScreen)
        selection_list = app.screen.query_one("#app-list", SelectionList)
        keys = [selection_list.get_option_at_index(i).value for i in range(selection_list.option_count)]
        assert keys[0] == "pkg:com.example.app"  # most entries first
        assert "pid:1234" in keys and "pid:1000" in keys

        await pilot.press("space")  # toggle the highlighted first row
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, AppSelectScreen)
        assert app.filters.packages == {"com.example.app"}
        assert "App: com.example.app (4321)" in output_text(app)

        await submit(pilot, "app")
        await pilot.pause()
        selection_list = app.screen.query_one("#app-list", SelectionList)
        assert selection_list.selected == ["pkg:com.example.app"]
        app.screen.query_one("#app-search").value = "1234"
        await pilot.pause()
        assert selection_list.option_count == 1
        await pilot.press("escape")
        await pilot.pause()
        assert app.filters.packages == {"com.example.app"}  # cancel keeps the selection


async def test_follow_survives_horizontal_scrollbar(device):
    lines = [tt(i) for i in range(150)]
    lines[120] = tt(120) + " " + "x" * 400  # makes the horizontal scrollbar appear
    device(lines, delay=0.003, hang=True)
    app = AlogsApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: len(app.store) == 150, what="all lines")
        await pilot.pause()
        log = app.query_one("#log", LogView)
        assert "LIVE" in status_text(app)
        assert log.following
        assert log.at_bottom


async def test_live_batches_while_app_dialog_is_open(device):
    device([tt(i, pid=4321 if i % 2 else 1234) for i in range(300)], delay=0.005, hang=True)
    app = AlogsApp()
    async with app.run_test(size=(160, 45)) as pilot:
        await submit(pilot, "openadb")
        await wait_until(pilot, lambda: len(app.store) > 20, what="first lines")
        await submit(pilot, "app")
        await pilot.pause()
        assert isinstance(app.screen, AppSelectScreen)
        count = len(app.store)
        await wait_until(pilot, lambda: len(app.store) > count + 50, what="lines while dialog open")
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AppSelectScreen)
