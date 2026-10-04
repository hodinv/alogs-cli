"""Filter state and engine (docs/04-filtering-model.md)."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field

from .entry import Level, LogEntry

ALL_LEVELS: tuple[Level, ...] = tuple(Level)


@dataclass
class FilterState:
    """What the user selected. Mutated by commands and tag clicks."""

    levels: set[Level] = field(default_factory=lambda: set(ALL_LEVELS))
    levels_touched: bool = False  # False = untouched state, all levels on
    tags: set[str] = field(default_factory=set)
    # App filter: selected packages (resolved to PIDs by AppResolver) and bare PIDs.
    # Both empty = all apps.
    packages: set[str] = field(default_factory=set)
    pids: set[int] = field(default_factory=set)

    @property
    def has_app_filter(self) -> bool:
        return bool(self.packages or self.pids)

    def change_level(self, level: Level, enable: bool) -> None:
        """Level state machine (docs/04, "Levels")."""
        if not self.levels_touched:
            self.levels_touched = True
            if enable:
                self.levels = {level}
                return
        if enable:
            self.levels.add(level)
        else:
            self.levels.discard(level)

    def reset_levels(self) -> None:
        self.levels = set(ALL_LEVELS)
        self.levels_touched = False

    def toggle_tag(self, tag: str) -> bool:
        """Select or unselect a tag; returns True if it is now selected."""
        if tag in self.tags:
            self.tags.discard(tag)
            return False
        self.tags.add(tag)
        return True

    def levels_text(self) -> str:
        if not self.levels_touched:
            return "all"
        if not self.levels:
            return "none"
        return " ".join(level.letter for level in ALL_LEVELS if level in self.levels)

    def snapshot(self, package_pids: Iterable[int] = ()) -> FilterSnapshot:
        """`package_pids`: PIDs currently known for the selected packages."""
        pids = None
        if self.has_app_filter:
            pids = frozenset(self.pids).union(package_pids)
        return FilterSnapshot(
            levels=None if not self.levels_touched else frozenset(self.levels),
            tags=frozenset(self.tags),
            pids=pids,
        )


@dataclass(frozen=True)
class FilterSnapshot:
    """Immutable copy of FilterState, safe to hand to a worker thread."""

    levels: frozenset[Level] | None = None  # None = all levels
    tags: frozenset[str] = frozenset()
    pids: frozenset[int] | None = None  # None = all apps; empty = app filter matching nothing yet


def compute(entries: Iterable[LogEntry], snap: FilterSnapshot) -> tuple[list[LogEntry], dict[str, int]]:
    """Visible entries + tag counts of entries passing the app and level filters."""
    levels, tags, pids = snap.levels, snap.tags, snap.pids
    visible: list[LogEntry] = []
    counts: dict[str, int] = {}
    append = visible.append
    get = counts.get
    for e in entries:
        if e.is_separator:
            append(e)
            continue
        if pids is not None and e.pid not in pids:
            continue
        if levels is not None and e.level is not None and e.level not in levels:
            continue
        tag = e.tag
        if tag is not None:
            counts[tag] = get(tag, 0) + 1
        if tags and tag not in tags:
            continue
        append(e)
    return visible, counts


class FilterEngine:
    """Holds the visible list and tag counts for the current snapshot.

    Filter changes recompute everything (`replace`); new entries are added
    incrementally (`add`).
    """

    def __init__(self) -> None:
        self.snapshot = FilterSnapshot()
        self.visible: list[LogEntry] = []
        self.tag_counts: dict[str, int] = {}

    def reset(self, snapshot: FilterSnapshot) -> None:
        self.snapshot = snapshot
        self.visible = []
        self.tag_counts = {}

    def replace(self, snapshot: FilterSnapshot, visible: list[LogEntry], counts: dict[str, int]) -> None:
        self.snapshot = snapshot
        self.visible = visible
        self.tag_counts = counts

    def add(self, batch: Iterable[LogEntry]) -> None:
        visible, counts = compute(batch, self.snapshot)
        self.visible.extend(visible)
        own = self.tag_counts
        for tag, n in counts.items():
            own[tag] = own.get(tag, 0) + n

    def remove_oldest(self, dropped: list[LogEntry]) -> None:
        """Forget entries the store dropped from its front (ring buffer)."""
        if not dropped:
            return
        last_seq = dropped[-1].seq
        cut = bisect_right(self.visible, last_seq, key=lambda e: e.seq)
        del self.visible[:cut]
        _, counts = compute(dropped, self.snapshot)
        own = self.tag_counts
        for tag, n in counts.items():
            left = own.get(tag, 0) - n
            if left > 0:
                own[tag] = left
            else:
                own.pop(tag, None)
