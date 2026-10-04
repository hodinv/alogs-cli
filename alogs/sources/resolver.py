"""Package <-> PID resolution (docs/05, "Package ↔ PID resolution")."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ..model.entry import LogEntry

# Process-start / death lines that reveal "pid -> process name".
# Android 7+:  Start proc 4321:com.example.app/u0a123 for activity {...}
_START_NEW = re.compile(r"Start proc (\d+):([^/\s]+)/")
# Android <= 6: Start proc com.example.app for activity com.example.app/.Main: pid=4321 uid=...
_START_OLD = re.compile(r"Start proc ([^\s]+) for .*?pid=(\d+)")
# Process com.example.app (pid 4321) has died
_DIED = re.compile(r"Process ([^\s]+) \(pid (\d+)\)")
# events buffer: am_proc_start: [0,4321,10123,com.example.app,activity,...]
_AM_PROC_START = re.compile(r"\[\d+,(\d+),\d+,([^,\]]+)")

_START_TAGS = frozenset({"ActivityManager", "ActivityTaskManager", "am_proc_start", "am_proc_died"})


def app_name(process_name: str) -> str:
    """`com.example.app:remote` -> `com.example.app` (processes grouped by app)."""
    return process_name.split(":", 1)[0]


@dataclass(frozen=True)
class AppInfo:
    """One row of the `app` list."""

    name: str | None  # app/process name; None = unknown (bare PID row)
    pids: tuple[int, ...]
    entries: int

    @property
    def key(self) -> str:
        return f"pkg:{self.name}" if self.name is not None else f"pid:{self.pids[0]}"


class AppResolver:
    """Learns which process name each PID has. Old mappings are kept, so
    PIDs of dead processes still map to their app."""

    def __init__(self) -> None:
        self.pid_names: dict[int, str] = {}
        self.version = 0  # bumped whenever a mapping changes

    def clear(self) -> None:
        self.pid_names.clear()
        self.version += 1

    def _set(self, pid: int, name: str) -> None:
        if self.pid_names.get(pid) != name:
            self.pid_names[pid] = name
            self.version += 1

    def learn_from_entries(self, entries: Iterable[LogEntry]) -> None:
        for e in entries:
            if e.package is not None and e.pid is not None:
                if e.pid not in self.pid_names:
                    self._set(e.pid, e.package)
                continue
            tag = e.tag
            if tag is None or tag not in _START_TAGS:
                continue
            msg = e.message
            if tag.startswith("am_proc"):
                m = _AM_PROC_START.match(msg)
                if m:
                    self._set(int(m.group(1)), m.group(2))
                continue
            m = _START_NEW.search(msg)
            if m:
                self._set(int(m.group(1)), m.group(2))
                continue
            m = _START_OLD.search(msg)
            if m:
                self._set(int(m.group(2)), m.group(1))
                continue
            m = _DIED.search(msg)
            if m:
                self._set(int(m.group(2)), m.group(1))

    def update_from_ps(self, output: str) -> None:
        """Parse `ps -A -o PID,NAME` or classic `ps` output (NAME = last column)."""
        lines = output.splitlines()
        if not lines:
            return
        header = lines[0].split()
        if "PID" not in header:
            return
        pid_col = header.index("PID")
        for line in lines[1:]:
            cols = line.split()
            if len(cols) <= pid_col or not cols[pid_col].isdigit():
                continue
            name = cols[-1]
            if name.startswith("[") and name.endswith("]"):
                continue  # kernel threads
            self._set(int(cols[pid_col]), name)

    def name_of(self, pid: int) -> str | None:
        name = self.pid_names.get(pid)
        return app_name(name) if name is not None else None

    def pids_of(self, apps: Iterable[str]) -> set[int]:
        wanted = set(apps)
        return {pid for pid, name in self.pid_names.items() if app_name(name) in wanted}

    def apps(self, entries: Iterable[LogEntry]) -> list[AppInfo]:
        """Apps/PIDs seen in `entries`, most entries first."""
        per_pid: dict[int, int] = {}
        get = per_pid.get
        for e in entries:
            pid = e.pid
            if pid is not None:
                per_pid[pid] = get(pid, 0) + 1
        named: dict[str, tuple[list[int], int]] = {}
        rows: list[AppInfo] = []
        for pid, count in per_pid.items():
            name = self.name_of(pid)
            if name is None:
                rows.append(AppInfo(None, (pid,), count))
            else:
                pids, total = named.get(name, ([], 0))
                pids.append(pid)
                named[name] = (pids, total + count)
        rows.extend(AppInfo(name, tuple(sorted(pids)), total) for name, (pids, total) in named.items())
        rows.sort(key=lambda a: (-a.entries, a.name or "", a.pids))
        return rows
