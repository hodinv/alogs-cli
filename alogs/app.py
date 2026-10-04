"""The Textual application: layout, wiring and the CommandContext."""

from __future__ import annotations

import time
from collections import deque
from bisect import bisect_right
from functools import partial
from pathlib import Path
from typing import Union

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static
from textual.worker import get_current_worker

from . import config
from .commands import CommandError, CommandRegistry, default_commands
from .export import export_entries
from .model.entry import LogEntry
from .model.filters import ALL_LEVELS, FilterEngine, FilterSnapshot, FilterState, compute
from .model.store import LogStore
from .parsing.detect import Detection
from .parsing.pipeline import ParserPipeline
from .parsing.registry import FormatConfigError, ParserRegistry, default_registry
from .model.search import MAX_HITS
from .model.search import search as search_entries
from .sources.adb_source import (
    AdbError,
    AdbSource,
    choose_device,
    default_save_path,
    find_adb,
    list_devices,
    process_list,
)
from .sources.file_source import FileSource, SourceError
from .sources.resolver import AppInfo, AppResolver
from .widgets.pick_list import PickListScreen, app_rows, search_rows
from .widgets.command_input import CommandInput
from .widgets.filter_panel import FilterPanel
from .widgets.log_view import LogView

Source = Union[FileSource, AdbSource]

BATCH_LINES = 50_000
BATCH_SECONDS = 0.1
SYNC_FILTER_LIMIT = 100_000  # above this, refilter in a worker thread
PANEL_REFRESH_SECONDS = 0.5  # tag counts refresh rate while loading / live
LIVE_MAX_ENTRIES = 2_000_000  # ring buffer size for live sources
PS_REFRESH_SECONDS = 5.0
OUTPUT_MAX_LINES = 2000


class AlogsApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "alogs"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("colon,slash", "focus_command", "Command", show=False),
    ]

    def __init__(
        self,
        initial_file: str | None = None,
        forced_format: str | None = None,
        parsers: ParserRegistry | None = None,
        commands: CommandRegistry | None = None,
        history_path: Path | None = None,
        live_max_entries: int = LIVE_MAX_ENTRIES,
        initial_adb: bool = False,
        initial_serial: str | None = None,
        save_adb: bool = True,
        startup_commands: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._config_error: str | None = None
        if parsers is None:
            try:
                parsers = default_registry(config.formats_file())
            except FormatConfigError as e:
                self._config_error = f"Ignoring user formats: {e}"
                parsers = default_registry()
        self.parsers = parsers
        self.commands = commands or default_commands()
        self.store = LogStore()
        self.filters = FilterState()
        self.engine = FilterEngine()
        self.resolver = AppResolver()
        self.live_max_entries = live_max_entries
        self._history_path = history_path
        self._initial_file = initial_file
        self._initial_adb = initial_adb
        self._initial_serial = initial_serial
        self._save_adb = save_adb
        self._startup_commands = list(startup_commands or [])
        self._forced_format = forced_format
        self._source: Source | None = None
        self._connecting = False
        self._connect_generation = 0
        self._detection: Detection | None = None
        self._loading = False
        self._progress = 0.0
        self._generation = 0
        self._filter_generation = 0
        self._filtering = False
        self._panel_refresh_pending = False
        self._resolver_version_seen = -1
        self.messages: deque[str] = deque(maxlen=OUTPUT_MAX_LINES)  # what the output panel shows

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # Keep references: queries search the *active* screen, which is the
        # `app` dialog while it is open, but live batches keep arriving.
        self.log_view = LogView(self.engine.visible, id="log")
        self.log_view.border_title = "Log"
        self.command_input = CommandInput(self.commands.names(), self._history_path, id="command")
        self.output = RichLog(id="output", wrap=True, markup=False, max_lines=OUTPUT_MAX_LINES)
        self.filter_panel = FilterPanel(id="filters")
        self.status_bar = Static(id="status")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield self.log_view
                with Vertical(id="command-panel"):
                    yield self.command_input
                    yield self.output
            yield self.filter_panel
        yield self.status_bar

    def on_mount(self) -> None:
        self.command_input.focus()
        if self._config_error:
            self.write_error(self._config_error)
        if self._forced_format and self.parsers.get(self._forced_format) is None:
            self.write_error(f"Unknown format '{self._forced_format}', using auto-detection.")
            self._forced_format = None
        self._update_status()
        self._refresh_panel()
        for line in self._startup_commands:  # filters from the alogs command line
            self._run_line(line, echo=False)
        if self._initial_file:
            self._run_line(f'open "{self._initial_file}"', echo=False)
        elif self._initial_adb:
            serial = f' -s "{self._initial_serial}"' if self._initial_serial else ""
            self._run_line(f"openadb{serial}{'' if self._save_adb else ' --no-save'}", echo=False)

    def on_unmount(self) -> None:
        self._stop_source()

    def action_focus_command(self) -> None:
        self.command_input.focus()

    # -- command handling -------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command":
            return
        line = event.value.strip()
        event.input.value = ""
        if line:
            self.command_input.remember(line)
            self._run_line(line)

    def _run_line(self, line: str, echo: bool = True) -> None:
        if echo:
            self._emit(Text(f"> {line}", style="dim"))
        try:
            self.commands.dispatch(self, line)
        except CommandError as e:
            self.write_error(str(e))
        except Exception as e:  # a buggy command must not kill the app
            self.write_error(f"Error: {e!r}")

    # -- CommandContext ---------------------------------------------------------

    def write(self, text: str) -> None:
        self._emit(Text(text))

    def write_error(self, text: str) -> None:
        self._emit(Text(text, style="bold red"))

    def _emit(self, text: Text) -> None:
        # `messages` keeps the unwrapped text (the panel wraps long lines to its width)
        self.messages.append(text.plain)
        self.output.write(text)

    def open_file(self, path: str, force: bool = False) -> None:
        source = FileSource(path)
        try:
            source.check(force)
        except SourceError as e:
            raise CommandError(str(e)) from None
        self.write(f"Opening {source.path} …")
        self._start_load(source)

    def open_adb(self, serial: str | None = None, save: bool = True) -> None:
        self._save_adb = save
        adb = find_adb()
        if adb is None:
            raise CommandError(
                "adb not found — install Android platform-tools and put adb on PATH, or set ANDROID_HOME"
            )
        self.write("Connecting to adb …")
        self._connect_generation += 1
        self._connecting = True
        self._update_status()
        self.run_worker(
            partial(self._adb_connect_worker, adb, serial, self._connect_generation),
            thread=True,
            group="connect",
            exclusive=True,
            exit_on_error=False,
        )

    def export(self, path: str, overwrite: bool = False) -> int:
        return export_entries(self.shown_entries(), path, overwrite)

    def shown_entries(self) -> list[LogEntry]:
        return self.engine.visible

    def current_format(self) -> Detection | None:
        if self._detection is None and self._forced_format:
            return Detection(self._forced_format, forced=True)
        return self._detection

    def set_format(self, parser_id: str | None) -> None:
        self._forced_format = parser_id
        label = parser_id or "auto-detection"
        source = self._source
        if source is None:
            self.write(f"Format set to {label}; it applies to the next opened log.")
            return
        if isinstance(source, AdbSource):
            self.write(f"Format set to {label}; restarting adb logcat …")
            self._start_load(self._new_adb_source(source.adb, source.serial))
            return
        self.write(f"Format set to {label}; re-reading {source.name} …")
        fresh = FileSource(source.path)
        try:
            fresh.check(force=True)
        except SourceError as e:
            raise CommandError(str(e)) from None
        self._start_load(fresh)

    def apps(self) -> list[AppInfo]:
        return self.resolver.apps(self.store.entries)

    def select_apps(self, packages: set[str], pids: set[int]) -> None:
        self.filters.packages = set(packages)
        self.filters.pids = set(pids)
        self.filters_changed()

    def show_app_dialog(self) -> None:
        def done(result: set[str] | None) -> None:
            if result is not None:
                packages = {k[4:] for k in result if k.startswith("pkg:")}
                pids = {int(k[4:]) for k in result if k.startswith("pid:")}
                self.select_apps(packages, pids)
                self.write(f"App: {self.app_filter_text()}")

        selected = {f"pkg:{p}" for p in self.filters.packages} | {f"pid:{p}" for p in self.filters.pids}
        rows = app_rows(self.apps(), self.filters.packages)
        hint = "Space/Enter/click toggles · Ctrl+S applies · Esc cancels · nothing selected = all apps"
        self.push_screen(PickListScreen("Apps / processes", rows, selected, hint), done)

    def search(self, text: str, in_messages: bool = False, by_app: bool = False) -> None:
        if not self.store.entries:
            raise CommandError("No log loaded — open a file or 'openadb' first.")
        entries = list(self.store.entries)  # snapshot: live batches keep arriving
        generation = self._generation

        def work() -> None:
            hits = search_entries(entries, text, in_messages=in_messages, by_app=by_app)
            try:
                self.call_from_thread(self._show_search, generation, text, in_messages, by_app, hits)
            except RuntimeError:
                pass

        self.run_worker(work, thread=True, exclusive=True, group="search", exit_on_error=False)

    def _show_search(self, generation, text, in_messages, by_app, hits) -> None:
        if generation != self._generation:
            return  # another log was opened meanwhile
        what = "PIDs" if by_app else "tags"
        where = "messages" if in_messages else "tag names"
        if not hits:
            self.write(f"No {what} with '{text}' in {where}.")
            return
        more = f" (first {MAX_HITS})" if len(hits) >= MAX_HITS else ""
        self.write(f"Found {len(hits):,} {what}{more} with '{text}' in {where} — tick to add to the filter.")
        names = {h.pid: self.resolver.name_of(h.pid) or "" for h in hits if h.pid is not None}
        rows = search_rows(hits, names)
        shown = {key for _, key in rows}
        selected = {f"tag:{t}" for t in self.filters.tags} | {f"pid:{p}" for p in self.filters.pids}

        def done(result: set[str] | None) -> None:
            if result is None:
                return
            for key in shown:
                kind, value = key.split(":", 1)
                target = self.filters.tags if kind == "tag" else self.filters.pids
                item = value if kind == "tag" else int(value)
                if key in result:
                    target.add(item)  # type: ignore[arg-type]
                else:
                    target.discard(item)  # type: ignore[arg-type]
            self.filters_changed()
            if by_app:
                self.write(f"App: {self.app_filter_text()}")
            else:
                self.write(f"Tags: {', '.join(sorted(self.filters.tags, key=str.lower)) or 'all'}")

        title = f"search{' -app' if by_app else ''}{' -m' if in_messages else ''}: {text}"
        self.push_screen(PickListScreen(title, rows, selected & shown), done)

    def restart_args(self) -> list[str]:
        """`alogs` arguments that reopen the current source with the current filters."""
        args: list[str] = []
        source = self._source
        if isinstance(source, FileSource):
            args.append(str(source.path.resolve()))
        elif isinstance(source, AdbSource):
            args += ["--adb", "--serial", source.serial]
            if source.save_path is None:
                args.append("--no-save")
        if self._forced_format:
            args += ["--format", self._forced_format]
        state = self.filters
        if state.levels_touched:
            letters = ",".join(level.letter for level in ALL_LEVELS if level in state.levels)
            args.append(f"--levels={letters or 'none'}")
        for tag in sorted(state.tags, key=str.lower):
            args += ["--tag", tag]
        for package in sorted(state.packages):
            args += ["--app", package]
        for pid in sorted(state.pids):
            args += ["--pid", str(pid)]
        return args

    def app_filter_text(self) -> str:
        if not self.filters.has_app_filter:
            return "all"
        parts = []
        for name in sorted(self.filters.packages):
            pids = sorted(self.resolver.pids_of([name]))
            parts.append(f"{name} ({', '.join(map(str, pids)) or 'no PIDs yet'})")
        parts.extend(f"pid {pid}" for pid in sorted(self.filters.pids))
        return "; ".join(parts)

    # -- loading ------------------------------------------------------------------

    def _stop_source(self) -> None:
        if isinstance(self._source, AdbSource):
            self._source.stop()

    def _adb_connect_worker(self, adb: list[str], serial: str | None, generation: int) -> None:
        try:
            device = choose_device(list_devices(adb), serial)
        except AdbError as e:
            self.call_from_thread(self._on_adb_error, generation, str(e))
            return
        self.call_from_thread(self._on_adb_connected, generation, adb, device.serial)

    def _on_adb_error(self, generation: int, message: str) -> None:
        if generation != self._connect_generation:
            return
        self._connecting = False  # the current source (if any) stays as it is
        self.write_error(message)
        self._update_status()

    def _new_adb_source(self, adb: list[str], serial: str) -> AdbSource:
        save_path = default_save_path().resolve() if self._save_adb else None
        if save_path is not None:
            self.write(f"Saving everything received to {save_path}")
        return AdbSource(adb, serial, save_path)

    def _on_adb_connected(self, generation: int, adb: list[str], serial: str) -> None:
        if generation != self._connect_generation:
            return
        self.write(f"Reading live log from {serial} (End resumes following)")
        self._start_load(self._new_adb_source(adb, serial))

    def _start_load(self, source: Source) -> None:
        self._stop_source()
        self._source = source
        self._generation += 1
        self._connect_generation += 1  # a pending openadb no longer applies
        self._connecting = False
        live = isinstance(source, AdbSource)
        self.store.clear()
        self.resolver.clear()
        self._resolver_version_seen = -1
        self._filter_generation += 1  # drop any refilter of the old log
        self._filtering = False
        self.engine.reset(self._snapshot())
        view = self.log_view
        view.follow = live
        view.reset(self.engine.visible)
        view.scroll_to(0, 0, animate=False)
        self._detection = None
        self._loading = True
        self._progress = 0.0
        self._update_status()
        self._refresh_panel()
        self.run_worker(
            partial(self._load_worker, source, self._generation, self._forced_format),
            thread=True,
            exclusive=True,
            group="load",
            exit_on_error=False,
        )
        if live:
            self.run_worker(
                partial(self._ps_worker, source, self._generation),
                thread=True,
                exclusive=True,
                group="ps",
                exit_on_error=False,
            )

    def _load_worker(self, source: Source, generation: int, forced: str | None) -> None:
        worker = get_current_worker()
        pipeline = ParserPipeline(self.parsers, forced)
        batch: list[LogEntry] = []
        last = time.monotonic()
        live = isinstance(source, AdbSource)

        def send(done: bool) -> bool:
            progress = 1.0 if live or done else source.progress  # type: ignore[union-attr]
            try:
                self.call_from_thread(self._on_batch, generation, batch, pipeline.detection, progress, done)
            except RuntimeError:  # app is shutting down
                return False
            return True

        try:
            for count, line in enumerate(source.iter_lines(), 1):
                if worker.is_cancelled:
                    if live:
                        source.stop()  # type: ignore[union-attr]
                    return
                if line is None:  # live source went quiet
                    pipeline.flush_idle(batch)
                    if batch:
                        if not send(False):
                            return
                        batch = []
                        last = time.monotonic()
                    continue
                pipeline.feed(line, batch)
                if live:
                    # show lines promptly even if the stream never goes quiet
                    if time.monotonic() - last > BATCH_SECONDS:
                        pipeline.flush_idle(batch)
                        if batch and not send(False):
                            return
                        batch = []
                        last = time.monotonic()
                elif count & 0x3FF == 0 and (
                    len(batch) >= BATCH_LINES or time.monotonic() - last > BATCH_SECONDS
                ):
                    if not send(False):
                        return
                    batch = []
                    last = time.monotonic()
            pipeline.flush(batch)
        except OSError as e:
            try:
                self.call_from_thread(self._on_load_error, generation, f"Read error: {e}")
            except RuntimeError:
                pass
            return
        if not worker.is_cancelled:
            send(True)

    def _ps_worker(self, source: AdbSource, generation: int) -> None:
        """Refresh the PID -> package map from the device while live."""
        worker = get_current_worker()
        while not worker.is_cancelled and generation == self._generation:
            try:
                output = process_list(source.adb, source.serial)
            except AdbError:
                output = ""
            if output and generation == self._generation:
                try:
                    self.call_from_thread(self._on_ps, generation, output)
                except RuntimeError:
                    return
            for _ in range(int(PS_REFRESH_SECONDS / 0.1)):
                if worker.is_cancelled or generation != self._generation or not self._loading:
                    return
                time.sleep(0.1)

    def _on_ps(self, generation: int, output: str) -> None:
        if generation == self._generation:
            self.resolver.update_from_ps(output)
            self._check_app_pids()

    def _on_batch(
        self,
        generation: int,
        batch: list[LogEntry],
        detection: Detection | None,
        progress: float,
        done: bool,
    ) -> None:
        if generation != self._generation:
            return  # a newer load replaced this one
        self.resolver.learn_from_entries(batch)
        self.store.add(batch)
        self.engine.add(batch)
        self._detection = detection
        self._progress = progress
        live = isinstance(self._source, AdbSource)
        if live:
            source = self._source
            assert isinstance(source, AdbSource)
            if source.save_error and source.save_path is not None:
                self.write_error(f"{source.save_error} — continuing without saving")
                source.save_path = None
            dropped = self.store.trim(self.live_max_entries)
            if dropped:
                self.engine.remove_oldest(dropped)
                view = self.log_view
                view.reset(self.engine.visible, anchor_seq=view.top_seq(), follow=view.following)
        self.log_view.sync()
        self._check_app_pids()
        if done:
            self._loading = False
            if live:
                source = self._source
                assert isinstance(source, AdbSource)
                reason = f" — {source.error}" if source.error else ""
                self.write_error(f"adb logcat stopped (exit code {source.returncode}){reason}")
                if source.save_path is not None and not source.save_error:
                    self.write(f"Saved {source.saved_lines:,} lines to {source.save_path}")
            else:
                fmt = detection.describe() if detection else "?"
                self.write(f"Loaded {len(self.store):,} entries · format: {fmt}")
            self._refresh_panel()
        else:
            self._schedule_panel_refresh()
        self._update_status()

    def _on_load_error(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._loading = False
        self.write_error(message)
        self._update_status()

    def on_log_view_follow_changed(self, event: LogView.FollowChanged) -> None:
        self._update_status()

    def _update_status(self) -> None:
        parts = []
        source = self._source
        if self._connecting:
            parts.append("connecting to adb …")
        elif source is None:
            parts.append("no log open — try 'open <file>', 'openadb' or 'help'")
        if source is not None:
            live = isinstance(source, AdbSource)
            parts.append(source.name if live else f"file: {source.name}")
            fmt = self.current_format()
            parts.append(f"format: {fmt.describe() if fmt else 'detecting…'}")
            shown = len(self.engine.visible)
            parts.append(f"shown {shown:,} of {len(self.store):,} entries")
            parts.append(f"{self.log_view.row_count:,} lines")
            if self.store.dropped:
                parts.append(f"dropped {self.store.dropped:,}")
            if live:
                if self._loading:
                    parts.append("LIVE" if self.log_view.following else "PAUSED (End to follow)")
                else:
                    parts.append("STOPPED")
            elif self._loading:
                parts.append(f"loading {self._progress:.0%}")
            if self._filtering:
                parts.append("filtering…")
        self.status_bar.update(Text(" │ ".join(parts)))

    # -- filtering ----------------------------------------------------------------

    def on_filter_panel_tag_toggled(self, event: FilterPanel.TagToggled) -> None:
        self.filters.toggle_tag(event.tag)
        self.filters_changed()

    def _snapshot(self) -> FilterSnapshot:
        return self.filters.snapshot(self.resolver.pids_of(self.filters.packages))

    def _check_app_pids(self) -> None:
        """Selected packages gained PIDs (process start seen, ps refresh): refilter."""
        if self.resolver.version == self._resolver_version_seen:
            return
        self._resolver_version_seen = self.resolver.version
        if self.filters.packages and self._snapshot().pids != self.engine.snapshot.pids:
            self.filters_changed()
        elif self.filters.has_app_filter:
            self._schedule_panel_refresh()

    def filters_changed(self) -> None:
        """Recompute the visible entries for the current FilterState."""
        self._filter_generation += 1
        generation = self._filter_generation
        snapshot = self._snapshot()
        entries = self.store.entries
        view = self.log_view
        anchor = view.top_seq()
        follow = view.following or (view.at_bottom and view.max_scroll_y > 0)
        self._refresh_panel()  # show the new selection immediately
        if len(entries) <= SYNC_FILTER_LIMIT:
            visible, counts = compute(entries, snapshot)
            self._apply_filter(generation, entries, None, snapshot, visible, counts, anchor, follow)
            return
        self._filtering = True
        self._update_status()
        chunk = list(entries)  # the store may be trimmed meanwhile (live)
        last_seq = chunk[-1].seq

        def work() -> None:
            visible, counts = compute(chunk, snapshot)
            try:
                self.call_from_thread(
                    self._apply_filter, generation, entries, last_seq, snapshot, visible, counts, anchor, follow
                )
            except RuntimeError:
                pass

        self.run_worker(work, thread=True, exclusive=True, group="filter", exit_on_error=False)

    def _apply_filter(
        self,
        generation: int,
        entries: list[LogEntry],
        last_seq: int | None,
        snapshot: FilterSnapshot,
        visible: list[LogEntry],
        counts: dict[str, int],
        anchor: int | None,
        follow: bool,
    ) -> None:
        if generation != self._filter_generation or entries is not self.store.entries:
            return  # superseded by a newer filter change or another log
        self._filtering = False
        self.engine.replace(snapshot, visible, counts)
        if last_seq is not None:
            # computed on a copy: drop entries trimmed since, add entries loaded since
            if entries:
                cut = bisect_right(visible, entries[0].seq - 1, key=lambda e: e.seq)
                del visible[:cut]
            self.engine.add(entries[bisect_right(entries, last_seq, key=lambda e: e.seq):])
        self.log_view.reset(self.engine.visible, anchor_seq=anchor, follow=follow)
        self._refresh_panel()
        self._update_status()

    def _schedule_panel_refresh(self) -> None:
        if not self._panel_refresh_pending and self.is_running:
            self._panel_refresh_pending = True
            self.set_timer(PANEL_REFRESH_SECONDS, self._refresh_panel)

    def _refresh_panel(self) -> None:
        self._panel_refresh_pending = False
        if not self.filter_panel.is_attached:
            return  # timer fired while the app is shutting down
        has_log = self._source is not None
        self.filter_panel.update_view(self.filters, self.engine.tag_counts, self.app_filter_text(), has_log)
        hint = ""
        if self.filters.levels_touched and not self.filters.levels:
            hint = "no levels enabled — try 'levels all'"
        self.log_view.border_subtitle = hint
