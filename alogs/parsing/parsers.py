"""Line parsers (docs/09, section 3.2)."""

from __future__ import annotations

import re

from ..model.entry import Level, LogEntry, TimeKind
from .layouts import Layout
from .timestamps import classify

# Group name -> LogEntry field it fills (used for specificity scoring).
_FIELD_GROUPS = {
    "ts": "time",
    "lvl": "level",
    "tag": "tag",
    "pid": "pid",
    "tid": "tid",
    "uid": "uid",
    "pkg": "package",
}


class LineParser:
    """Turns one header line into a LogEntry (or None if it doesn't match)."""

    id: str = ""
    description: str = ""
    sample: str = ""
    multiline: bool = False
    fields: frozenset[str] = frozenset()

    @property
    def specificity(self) -> int:
        return len(self.fields)

    def parse(self, line: str) -> LogEntry | None:
        raise NotImplementedError

    def absorb(self, entry: LogEntry, line: str) -> bool:
        """Multi-line formats: consume a non-header line into `entry`."""
        return False


class RegexParser(LineParser):
    def __init__(
        self,
        id: str,
        pattern: str,
        description: str = "",
        sample: str = "",
        multiline: bool = False,
        level_map: dict[str, str] | None = None,
    ) -> None:
        self.id = id
        self.description = description
        self.sample = sample
        self.multiline = multiline
        self._re = re.compile(pattern)
        self._level_map = {k.upper(): v for k, v in (level_map or {}).items()}
        groups = self._re.groupindex
        self.fields = frozenset(f for g, f in _FIELD_GROUPS.items() if g in groups)
        # uid is optional in every built-in layout, so it never adds specificity.
        if "uid" in self.fields:
            self.fields = self.fields - {"uid"}

    @classmethod
    def from_layout(cls, layout: Layout) -> RegexParser:
        return cls(layout.id, layout.pattern, layout.description, layout.sample, layout.multiline)

    def parse(self, line: str) -> LogEntry | None:
        # Hot path (runs once per line): positional construction, dict lookups.
        m = self._re.match(line)
        if m is None:
            return None
        g = m.groupdict()
        lvl = g.get("lvl")
        if lvl and self._level_map:
            lvl = self._level_map.get(lvl.upper(), lvl)
        ts = g.get("ts")
        pid = g.get("pid")
        tid = g.get("tid")
        tag = g.get("tag")
        pkg = g.get("pkg")
        return LogEntry(
            line,
            g.get("msg") or "",
            self.id,
            _LEVELS.get(lvl) if lvl else None,
            tag.strip() if tag is not None else None,
            int(pid) if pid and pid.isdigit() else None,
            int(tid) if tid and tid.isdigit() else None,
            g.get("uid"),
            _clean_pkg(pkg) if pkg else None,
            ts,
            classify(ts) if ts else TimeKind.NONE,
        )

    def absorb(self, entry: LogEntry, line: str) -> bool:
        if not self.multiline:
            return False
        if not line.strip():
            return True  # blank line terminates a `-v long` record
        if entry.cont is None:
            entry.message = line
        entry.add_continuation(line)
        return True


class RawParser(LineParser):
    """Last resort: the whole line is the message."""

    id = "raw"
    description = "logcat -v raw / unknown text (message only)"
    sample = "message"

    def parse(self, line: str) -> LogEntry:
        return LogEntry(raw=line, message=line, format_id=self.id)


_LEVELS: dict[str, Level] = {}
for _letter in "VDIWEFAS":
    _level = Level.from_letter(_letter)
    assert _level is not None
    _LEVELS[_letter] = _LEVELS[_letter.lower()] = _level


def _clean_pkg(pkg: str | None) -> str | None:
    if not pkg or pkg == "?" or pkg.startswith("pid-"):
        return None
    return pkg
