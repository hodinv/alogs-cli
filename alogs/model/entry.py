"""Normalized log entry produced by every parser (see docs/09, section 2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Level(IntEnum):
    """Android log priorities, ordered like android.util.Log."""

    VERBOSE = 2
    DEBUG = 3
    INFO = 4
    WARN = 5
    ERROR = 6
    FATAL = 7
    ASSERT = 8

    @property
    def letter(self) -> str:
        return _LEVEL_TO_LETTER[self]

    @classmethod
    def from_letter(cls, letter: str | None) -> Level | None:
        if not letter:
            return None
        return _LETTER_TO_LEVEL.get(letter.upper())

    @classmethod
    def from_name(cls, name: str) -> Level | None:
        """Accept a letter (`W`) or a full name (`WARN`, `warning`)."""
        key = name.strip().upper()
        return _LETTER_TO_LEVEL.get(key) or _NAME_TO_LEVEL.get(key)


_LEVEL_TO_LETTER = {
    Level.VERBOSE: "V",
    Level.DEBUG: "D",
    Level.INFO: "I",
    Level.WARN: "W",
    Level.ERROR: "E",
    Level.FATAL: "F",
    Level.ASSERT: "A",
}
_LETTER_TO_LEVEL = {letter: level for level, letter in _LEVEL_TO_LETTER.items()}
_LETTER_TO_LEVEL["S"] = Level.ASSERT  # "silent" priority only appears in odd dumps
_NAME_TO_LEVEL = {level.name: level for level in Level}
_NAME_TO_LEVEL["WARNING"] = Level.WARN


class TimeKind(Enum):
    NONE = "none"
    WALL_NO_YEAR = "wall-no-year"  # 01-02 03:04:05.678
    WALL = "wall"  # 2024-01-02 03:04:05.678
    EPOCH = "epoch"  # 1704164645.678
    MONOTONIC = "monotonic"  # 123.456 (seconds since boot)


@dataclass(slots=True, eq=False)
class LogEntry:
    """One parsed log record; may span several text lines (`cont`)."""

    raw: str
    message: str
    format_id: str
    level: Level | None = None
    tag: str | None = None
    pid: int | None = None
    tid: int | None = None
    uid: str | None = None
    package: str | None = None
    time_text: str | None = None
    time_kind: TimeKind = TimeKind.NONE
    buffer: str | None = None
    cont: list[str] | None = None
    is_separator: bool = False
    seq: int = 0  # position in the source, assigned by LogStore

    def add_continuation(self, line: str) -> None:
        if self.cont is None:
            self.cont = [line]
        else:
            self.cont.append(line)

    @property
    def line_count(self) -> int:
        return 1 + (len(self.cont) if self.cont else 0)

    def text_lines(self) -> list[str]:
        """Original text of the entry, as it appeared in the source."""
        return [self.raw, *self.cont] if self.cont else [self.raw]
