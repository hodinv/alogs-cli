"""Virtualized log list (docs/02, "Log zone").

Only the rows on screen are rendered. Every entry occupies 1 + len(cont)
rows; two flat arrays map a row number to (entry index, line within entry).
"""

from __future__ import annotations

from array import array
from bisect import bisect_left

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from ..model.entry import Level, LogEntry

LEVEL_STYLES: dict[Level | None, Style] = {
    Level.VERBOSE: Style(color="grey58"),
    Level.DEBUG: Style(color="#5fafff"),
    Level.INFO: Style(color="#87d787"),
    Level.WARN: Style(color="#ffd75f"),
    Level.ERROR: Style(color="#ff5f5f"),
    Level.FATAL: Style(color="#ff5fff", bold=True),
    Level.ASSERT: Style(color="#ff5fff", bold=True),
    None: Style(),
}
SEPARATOR_STYLE = Style(color="grey50", italic=True)
TAB_SIZE = 4


class LogView(ScrollView, can_focus=True):
    DEFAULT_CSS = """
    LogView {
        background: $surface;
    }
    """

    class FollowChanged(Message):
        """Live mode: the view started or stopped sticking to new lines."""

        def __init__(self, following: bool) -> None:
            super().__init__()
            self.following = following

    def __init__(self, entries: list[LogEntry] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.follow = False  # live sources: stick to the bottom while scrolled there
        # True until the user scrolls up. Tracked explicitly: comparing positions
        # breaks when a horizontal scrollbar appears and the bottom moves by a row.
        self._sticky = True
        self._entries: list[LogEntry] = entries if entries is not None else []
        self._synced = 0  # number of entries already mapped to rows
        self._row_entry = array("I")
        self._row_sub = array("I")
        self._max_width = 0

    @property
    def row_count(self) -> int:
        return len(self._row_entry)

    @property
    def entries(self) -> list[LogEntry]:
        return self._entries

    @property
    def at_bottom(self) -> bool:
        return self.scroll_offset.y >= self.max_scroll_y

    @property
    def following(self) -> bool:
        return self.follow and self._sticky

    def action_scroll_end(self) -> None:
        # Jump without animation: an animation would stop short of the
        # bottom while live lines keep arriving, and never resume following.
        self.scroll_to(None, self.max_scroll_y, animate=False, immediate=True, force=True)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if new_value >= self.max_scroll_y:
            self._set_sticky(True)
        elif new_value < old_value:
            self._set_sticky(False)  # user scrolled up

    def _set_sticky(self, sticky: bool) -> None:
        if sticky != self._sticky:
            self._sticky = sticky
            if self.follow:
                self.post_message(self.FollowChanged(sticky))

    def _scroll_bottom(self) -> None:
        if self._sticky:
            self.scroll_to(None, self.max_scroll_y, animate=False, immediate=True, force=True)

    def top_seq(self) -> int | None:
        """Source position of the entry at the top of the view."""
        row = self.scroll_offset.y
        if row >= len(self._row_entry):
            return None
        return self._entries[self._row_entry[row]].seq

    def reset(self, entries: list[LogEntry], anchor_seq: int | None = None, follow: bool = False) -> None:
        """Show a new entry list (open, filter change).

        With `anchor_seq` the first entry at or after that source position is
        scrolled to the top; with `follow` the view sticks to the bottom.
        """
        self._entries = entries
        self._synced = 0
        self._row_entry = array("I")
        self._row_sub = array("I")
        self._max_width = 0
        self.sync()
        if follow:
            self._set_sticky(True)
            self._scroll_bottom()
            self.call_after_refresh(self._scroll_bottom)
            return
        row = 0
        if anchor_seq is not None and entries:
            index = bisect_left(entries, anchor_seq, key=lambda e: e.seq)
            row = bisect_left(self._row_entry, index)
        self.scroll_to(None, row, animate=False, immediate=True, force=True)
        self._set_sticky(row >= self.max_scroll_y)

    def sync(self) -> None:
        """Map entries appended to the list since the last call."""
        stick = self.follow and self._sticky
        entries = self._entries
        row_entry, row_sub = self._row_entry, self._row_sub
        max_width = self._max_width
        for index in range(self._synced, len(entries)):
            entry = entries[index]
            row_entry.append(index)
            row_sub.append(0)
            max_width = max(max_width, len(entry.raw))
            if entry.cont:
                for sub, line in enumerate(entry.cont, 1):
                    row_entry.append(index)
                    row_sub.append(sub)
                    max_width = max(max_width, len(line))
        self._synced = len(entries)
        self._max_width = max_width
        self.virtual_size = Size(max_width + TAB_SIZE, len(row_entry))
        if stick:
            self._scroll_bottom()
            # again after layout, in case a scrollbar appeared and moved the bottom
            self.call_after_refresh(self._scroll_bottom)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        row = scroll_y + y
        width = self.size.width
        base = self.rich_style
        if row >= len(self._row_entry):
            return Strip.blank(width, base)
        entry = self._entries[self._row_entry[row]]
        sub = self._row_sub[row]
        text = entry.raw if sub == 0 else entry.cont[sub - 1]  # type: ignore[index]
        if "\t" in text:
            text = text.expandtabs(TAB_SIZE)
        style = SEPARATOR_STYLE if entry.is_separator else LEVEL_STYLES.get(entry.level, Style())
        if sub:
            style = style + Style(dim=True)
        strip = Strip([Segment(text, base + style)])
        return strip.crop_extend(scroll_x, scroll_x + width, base)
