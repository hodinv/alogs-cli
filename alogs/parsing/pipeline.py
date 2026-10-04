"""Text lines -> entries: detection, fallback, continuations (docs/09, section 4)."""

from __future__ import annotations

import re
from collections import deque

from ..model.entry import LogEntry
from .detect import SAMPLE_SIZE, SEPARATOR_RE, Detection, detect
from .parsers import LineParser
from .registry import ParserRegistry

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

REDETECT_WINDOW = 500
REDETECT_BELOW = 0.5


class ParserPipeline:
    """Feeds raw lines, emits finished entries.

    The newest entry is held back until the next entry starts (or `flush()`),
    because following lines may still turn out to be its continuation lines
    (stack traces, `-v long` bodies). Emitted entries are never mutated again.
    """

    def __init__(self, registry: ParserRegistry, forced_id: str | None = None) -> None:
        self._registry = registry
        self._forced = forced_id is not None
        self.detection: Detection | None = None
        self._parser: LineParser | None = None
        self._pending: list[str] | None = []
        self._current: LogEntry | None = None
        self._buffer: str | None = None
        self._window: deque[str] = deque(maxlen=REDETECT_WINDOW)
        self._window_ok = 0
        self._window_seen = 0
        if forced_id is not None:
            parser = registry.get(forced_id)
            if parser is None:
                raise KeyError(forced_id)
            self._lock(Detection(forced_id, 1.0, forced=True))

    # -- public API ---------------------------------------------------------

    def feed(self, line: str, out: list[LogEntry]) -> None:
        """Process one line; finished entries are appended to `out`."""
        if "\x1b" in line:
            line = ANSI_RE.sub("", line)
        if self._pending is not None:
            self._pending.append(line)
            if len(self._pending) >= SAMPLE_SIZE:
                self._detect_pending(out)
            return
        self._process(line, out)

    def flush(self, out: list[LogEntry]) -> None:
        """End of input: finish detection and emit the held-back entry."""
        if self._pending is not None:
            self._detect_pending(out)
        if self._current is not None:
            out.append(self._current)
            self._current = None

    def flush_idle(self, out: list[LogEntry]) -> None:
        """Live sources went quiet: emit what is buffered so it gets shown.

        A continuation line arriving later becomes a separate raw entry, which
        is rare for logcat (every line of a multi-line message has a header).
        """
        if self._pending is not None and not self._pending:
            return  # nothing seen yet; don't lock detection on an empty sample
        self.flush(out)

    # -- internals ----------------------------------------------------------

    def _lock(self, detection: Detection) -> None:
        self.detection = detection
        self._parser = self._registry.get(detection.parser_id) or self._registry.raw
        self._pending = None

    def _detect_pending(self, out: list[LogEntry]) -> None:
        pending = self._pending or []
        self._lock(detect(pending, self._registry))
        for line in pending:
            self._process(line, out)

    def _emit(self, entry: LogEntry, out: list[LogEntry]) -> None:
        if self._current is not None:
            out.append(self._current)
        self._current = entry

    def _process(self, line: str, out: list[LogEntry]) -> None:
        parser = self._parser
        assert parser is not None
        current = self._current

        if not line.strip():
            if current is not None and not parser.absorb(current, line):
                current.add_continuation(line)
            return

        sep = SEPARATOR_RE.match(line) if line[0] == "-" else None
        if sep:
            self._buffer = sep.group(1)
            self._emit(LogEntry(raw=line, message=line, format_id="separator",
                                buffer=self._buffer, is_separator=True), out)
            if self._current is not None:
                out.append(self._current)
                self._current = None
            return

        is_raw = parser is self._registry.raw
        entry = None if is_raw and not self._forced else parser.parse(line)
        if entry is None and current is not None and parser.absorb(current, line):
            self._track(line, True)
            return
        self._track(line, entry is not None)

        if entry is None and not self._forced:
            for other in self._registry.candidates():
                if other is not parser:
                    entry = other.parse(line)
                    if entry is not None:
                        break
        if entry is None:
            if current is not None and not is_raw:
                current.add_continuation(line)
                return
            entry = self._registry.raw.parse(line)

        entry.buffer = self._buffer
        self._emit(entry, out)

    def _track(self, line: str, ok: bool) -> None:
        """Re-detect when the locked parser stops matching (docs/09, section 4)."""
        if self._forced:
            return
        self._window.append(line)
        self._window_seen += 1
        self._window_ok += ok
        if self._window_seen < REDETECT_WINDOW:
            return
        rate = self._window_ok / self._window_seen
        self._window_seen = self._window_ok = 0
        if rate >= REDETECT_BELOW:
            return
        found = detect(self._window, self._registry)
        if found.parser_id != "raw" and found.score > rate:
            self._lock(found)
