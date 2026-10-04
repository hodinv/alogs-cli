"""In-memory storage of parsed entries."""

from __future__ import annotations

from .entry import LogEntry


class LogStore:
    """All entries of the current source, in source order.

    Entries are appended from the UI thread only (workers hand batches over
    via `call_from_thread`), so no locking is needed. `seq` numbers keep
    growing even when old entries are dropped by `trim` (live ring buffer).
    """

    def __init__(self) -> None:
        self.entries: list[LogEntry] = []
        self.dropped = 0
        self._next_seq = 0

    def __len__(self) -> int:
        return len(self.entries)

    def add(self, batch: list[LogEntry]) -> None:
        seq = self._next_seq
        for entry in batch:
            entry.seq = seq
            seq += 1
        self._next_seq = seq
        self.entries.extend(batch)

    def trim(self, max_entries: int) -> list[LogEntry]:
        """Drop the oldest entries beyond `max_entries`; return them.

        Drops only once 10% over the limit so the O(n) list shift is rare.
        """
        if len(self.entries) <= max_entries + max_entries // 10:
            return []
        drop = len(self.entries) - max_entries
        dropped = self.entries[:drop]
        del self.entries[:drop]
        self.dropped += drop
        return dropped

    def clear(self) -> None:
        # Replace rather than clear() so views holding the old list keep a
        # consistent snapshot until they are reset.
        self.entries = []
        self.dropped = 0
        self._next_seq = 0
