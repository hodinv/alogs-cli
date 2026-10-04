"""Header layouts of all built-in formats (docs/09, sections 1 and 3.1).

Each layout is a regex template using the shared fragments below. Named
groups map to LogEntry fields: ts, lvl, tag, pid, tid, uid, pkg, msg.
"""

from __future__ import annotations

from dataclasses import dataclass

from .timestamps import TS

LVL = r"(?P<lvl>[VDIWEFASvdiwefas])"
# `-v uid` inserts the uid before the pid: `u0_a123`, `root`, or numeric.
# Regex backtracking drops it again when the line has no uid.
UID_SP = r"(?:(?P<uid>[A-Za-z_][\w.]*|\d+):?\s+)?"
UID_IN_PARENS = r"(?:(?P<uid>[A-Za-z_][\w.]*|\d+):\s*)?"
PKG = r"(?P<pkg>[A-Za-z_][\w.]*(?::[\w.]+)?|\?|pid-\d+)"


@dataclass(frozen=True)
class Layout:
    id: str
    pattern: str
    description: str
    sample: str
    multiline: bool = False


LAYOUTS: list[Layout] = [
    Layout(
        "threadtime",
        rf"^\s*{TS}\s+{UID_SP}(?P<pid>\d+)\s+(?P<tid>\d+)\s+{LVL}\s+(?P<tag>.*?)\s*:(?:\s(?P<msg>.*))?$",
        "logcat -v threadtime (Android default)",
        "01-02 03:04:05.678  1234  5678 D MyTag   : message",
    ),
    Layout(
        "time",
        rf"^\s*{TS}\s+{LVL}/(?P<tag>.*?)\(\s*{UID_IN_PARENS}(?P<pid>\d+)\):(?:\s(?P<msg>.*))?$",
        "logcat -v time",
        "01-02 03:04:05.678 D/MyTag( 1234): message",
    ),
    Layout(
        "studio",
        rf"^\s*{TS}\s+(?P<pid>\d+)-(?P<tid>\d+)\s+(?P<tag>\S.*?)\s+{PKG}\s+{LVL}\s+(?P<msg>.*)$",
        "Android Studio Logcat copy/export",
        "2024-01-02 03:04:05.678  1234-5678  MyTag  com.example.app  D  message",
    ),
    Layout(
        "studio-legacy",
        rf"^\s*{TS}\s+(?P<pid>\d+)-(?P<tid>\d+)/{PKG}\s+{LVL}/(?P<tag>.*?):(?:\s(?P<msg>.*))?$",
        "Android Studio (before Dolphin) copy/export",
        "2024-01-02 03:04:05.678 1234-5678/com.example.app D/MyTag: message",
    ),
    Layout(
        "long",
        rf"^\[\s+{TS}\s+{UID_SP}(?P<pid>\d+):\s*(?P<tid>\d+)\s+{LVL}/(?P<tag>.*?)\s*\]$",
        "logcat -v long (header line, message lines, blank line)",
        "[ 01-02 03:04:05.678  1234: 5678 D/MyTag ]",
        multiline=True,
    ),
    Layout(
        "brief",
        rf"^{LVL}/(?P<tag>.*?)\(\s*{UID_IN_PARENS}(?P<pid>\d+)\):(?:\s(?P<msg>.*))?$",
        "logcat -v brief",
        "D/MyTag( 1234): message",
    ),
    Layout(
        "thread",
        rf"^{LVL}\(\s*{UID_IN_PARENS}(?P<pid>\d+):\s*(?P<tid>\d+)\)(?:\s(?P<msg>.*))?$",
        "logcat -v thread",
        "D( 1234: 5678) message",
    ),
    Layout(
        "process",
        rf"^{LVL}\(\s*{UID_IN_PARENS}(?P<pid>\d+)\)\s(?P<msg>.*?)\s+\((?P<tag>[^()]*)\)\s*$",
        "logcat -v process",
        "D( 1234) message  (MyTag)",
    ),
    Layout(
        "tag",
        rf"^{LVL}/(?P<tag>[^:]*?)\s*:(?:\s(?P<msg>.*))?$",
        "logcat -v tag",
        "D/MyTag: message",
    ),
]
