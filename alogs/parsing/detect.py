"""Format auto-detection (docs/09, section 4)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..model.entry import LogEntry, TimeKind
from .registry import ParserRegistry
from .timestamps import fraction_digits, has_zone

MIN_SCORE = 0.3
SAMPLE_SIZE = 500

SEPARATOR_RE = re.compile(r"^-{9} (?:beginning of|switch to) (\S+)")


@dataclass
class Detection:
    parser_id: str
    score: float = 0.0
    variant: list[str] = field(default_factory=list)
    forced: bool = False

    def describe(self) -> str:
        name = self.parser_id
        if self.variant:
            name += f" ({', '.join(self.variant)})"
        if self.forced:
            return f"{name} · forced"
        return f"{name} · {self.score:.0%}"


def detect(lines: Iterable[str], registry: ParserRegistry) -> Detection:
    """Pick the parser matching most sample lines; ties go to the parser
    that extracts more fields. Falls back to `raw` below MIN_SCORE."""
    # Blank lines are kept (they end `-v long` records) but not scored.
    sample: list[str] = []
    scored = 0
    for line in lines:
        if SEPARATOR_RE.match(line):
            continue
        sample.append(line)
        if line.strip():
            scored += 1
            if scored >= SAMPLE_SIZE:
                break
    if not scored:
        return Detection("raw")

    best_key: tuple[float, int] | None = None
    best: Detection | None = None
    for parser in registry.candidates():
        first: LogEntry | None = None
        matched = 0
        total = 0
        in_record = False  # multi-line formats: body lines count as matched
        for line in sample:
            if not line.strip():
                in_record = False
                continue
            entry = parser.parse(line)
            if entry is not None:
                matched += 1
                in_record = parser.multiline
                if first is None:
                    first = entry
            elif in_record:
                matched += 1
            elif line[0] in " \t" and first is not None:
                continue  # indented continuation (stack trace): neutral
            total += 1
        score = matched / total if total else 0.0
        key = (round(score, 2), parser.specificity)
        if score >= MIN_SCORE and (best_key is None or key > best_key):
            best_key = key
            best = Detection(parser.id, score, variant_of(first) if first else [])
    return best or Detection("raw")


def variant_of(entry: LogEntry) -> list[str]:
    """Logcat `-v` modifiers visible in an entry (year, usec, epoch, ...)."""
    out = []
    ts = entry.time_text or ""
    if entry.time_kind is TimeKind.WALL:
        out.append("year")
    elif entry.time_kind is TimeKind.EPOCH:
        out.append("epoch")
    elif entry.time_kind is TimeKind.MONOTONIC:
        out.append("monotonic")
    digits = fraction_digits(ts)
    if digits == 6:
        out.append("usec")
    elif digits == 9:
        out.append("nsec")
    if ts and has_zone(ts):
        out.append("zone")
    if entry.uid is not None:
        out.append("uid")
    return out
