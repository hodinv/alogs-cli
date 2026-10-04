"""`search` command: find tags / messages / PIDs containing a text."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .entry import LogEntry

MAX_HITS = 1000
MAX_TAGS_PER_PID = 5


@dataclass
class SearchHit:
    """One result row: a distinct tag, or a PID with `by_app`."""

    tag: str | None = None
    pid: int | None = None
    count: int = 0
    sample: str | None = None  # first matching message (message search)
    tags: list[str] = field(default_factory=list)  # tags seen for a PID (by_app)

    @property
    def key(self) -> str:
        return f"pid:{self.pid}" if self.pid is not None else f"tag:{self.tag}"


def search(
    entries: Iterable[LogEntry],
    text: str,
    in_messages: bool = False,
    by_app: bool = False,
    limit: int = MAX_HITS,
) -> list[SearchHit]:
    """Case-insensitive substring search.

    Default: tags containing `text`, one hit per distinct tag.
    `in_messages`: messages containing `text`, one hit per distinct tag with
    the first matching message as sample.
    `by_app`: same matching, but one hit per PID.
    Hits are sorted by number of matching entries, most first.
    """
    needle = text.casefold()
    hits: dict[object, SearchHit] = {}
    tag_matches: dict[str, bool] = {}  # tag search: decide once per distinct tag
    for e in entries:
        if e.is_separator:
            continue
        tag = e.tag
        if in_messages:
            if needle not in e.message.casefold():
                continue
        else:
            if tag is None:
                continue
            matched = tag_matches.get(tag)
            if matched is None:
                matched = tag_matches[tag] = needle in tag.casefold()
            if not matched:
                continue
        if by_app:
            if e.pid is None:
                continue
            hit = hits.get(e.pid)
            if hit is None:
                hit = hits[e.pid] = SearchHit(pid=e.pid, sample=e.message if in_messages else None)
                hit.tag = tag
            if tag is not None and tag not in hit.tags and len(hit.tags) < MAX_TAGS_PER_PID:
                hit.tags.append(tag)
        else:
            if tag is None:
                continue
            hit = hits.get(tag)
            if hit is None:
                hit = hits[tag] = SearchHit(tag=tag, sample=e.message if in_messages else None)
        hit.count += 1
    if by_app:
        ordered = sorted(hits.values(), key=lambda h: (-h.count, h.pid or 0))
    else:
        ordered = sorted(hits.values(), key=lambda h: (-h.count, (h.tag or "").casefold()))
    return ordered[:limit]
