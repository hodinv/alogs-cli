"""`export` implementation: write entries' original text to a file."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .model.entry import LogEntry


def export_entries(entries: Iterable[LogEntry], path: str | Path, overwrite: bool = False) -> int:
    """Write entries (including continuation lines) as UTF-8 with `\\n`.

    Returns the number of entries written. Raises FileExistsError when the
    file exists and `overwrite` is False.
    """
    target = Path(path).expanduser()
    mode = "w" if overwrite else "x"
    count = 0
    with target.open(mode, encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(entry.raw)
            f.write("\n")
            if entry.cont:
                for line in entry.cont:
                    f.write(line)
                    f.write("\n")
            count += 1
    return count
