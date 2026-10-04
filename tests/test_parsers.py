from __future__ import annotations

import pytest

from alogs.model.entry import Level, TimeKind

# (parser id, line, expected fields)
CASES = [
    ("threadtime", "01-02 03:04:05.678  1234  5678 D MyTag   : hello world",
     dict(time_text="01-02 03:04:05.678", time_kind=TimeKind.WALL_NO_YEAR, pid=1234, tid=5678,
          level=Level.DEBUG, tag="MyTag", message="hello world")),
    ("threadtime", "2024-01-02 03:04:05.678901  1234  5678 W OkHttp  : slow: 3 ms",
     dict(time_text="2024-01-02 03:04:05.678901", time_kind=TimeKind.WALL, level=Level.WARN,
          tag="OkHttp", message="slow: 3 ms")),
    ("threadtime", "1704164645.678  1234  5678 E Tag: m",
     dict(time_kind=TimeKind.EPOCH, pid=1234, tid=5678, level=Level.ERROR)),
    ("threadtime", "   123.456  1234  5678 I Tag: m",
     dict(time_text="123.456", time_kind=TimeKind.MONOTONIC, pid=1234)),
    ("threadtime", "01-02 03:04:05.678 +0100  1234  5678 D MyTag: m",
     dict(time_text="01-02 03:04:05.678 +0100", pid=1234, tid=5678)),
    ("threadtime", "01-02 03:04:05.678 u0_a123  1234  5678 D MyTag: m",
     dict(uid="u0_a123", pid=1234, tid=5678)),
    ("threadtime", "01-02 03:04:05.678 10123  1234  5678 D MyTag: m",
     dict(uid="10123", pid=1234, tid=5678)),
    ("threadtime", "01-02 03:04:05.678  1234  5678 D MyTag: m",
     dict(uid=None, pid=1234, tid=5678)),
    ("threadtime", "01-02 03:04:05.800  1000  1010 I My Tag With Spaces: spaced",
     dict(tag="My Tag With Spaces", message="spaced")),
    ("threadtime", "01-02 03:04:05.702   567   890 V chromium: [INFO:foo.cc(12)] value: 3",
     dict(tag="chromium", message="[INFO:foo.cc(12)] value: 3")),
    ("threadtime", "01-02 03:04:05.801  1000  1010 D EmptyMsg:",
     dict(tag="EmptyMsg", message="")),
    ("threadtime", "01-02 03:04:05.801  1000  1010 d lower: case level",
     dict(level=Level.DEBUG)),
    ("time", "01-02 03:04:05.678 D/MyTag   ( 1234): hello world",
     dict(pid=1234, tid=None, level=Level.DEBUG, tag="MyTag", message="hello world")),
    ("time", "2024-01-02 03:04:05.678 W/OkHttp( 4321): slow",
     dict(time_kind=TimeKind.WALL, pid=4321, tag="OkHttp")),
    ("brief", "D/MyTag   ( 1234): hello world",
     dict(pid=1234, level=Level.DEBUG, tag="MyTag", message="hello world", time_text=None)),
    ("brief", "W/OkHttp  ( 4321): slow response (retrying)",
     dict(tag="OkHttp", message="slow response (retrying)")),
    ("brief", "I/Tag(u0_a12:  1234): with uid",
     dict(uid="u0_a12", pid=1234, message="with uid")),
    ("process", "W( 4321) slow response (retrying)  (OkHttp)",
     dict(pid=4321, level=Level.WARN, tag="OkHttp", message="slow response (retrying)")),
    ("tag", "D/MyTag   : hello world",
     dict(level=Level.DEBUG, tag="MyTag", message="hello world", pid=None)),
    ("thread", "D( 1234: 5678) hello world",
     dict(pid=1234, tid=5678, level=Level.DEBUG, message="hello world", tag=None)),
    ("long", "[ 01-02 03:04:05.678  1234: 5678 D/MyTag ]",
     dict(pid=1234, tid=5678, level=Level.DEBUG, tag="MyTag", message="")),
    ("studio", "2024-01-02 03:04:05.678  1234-5678  MyTag                   com.example.app                      D  hello world",
     dict(pid=1234, tid=5678, tag="MyTag", package="com.example.app", level=Level.DEBUG,
          message="hello world")),
    ("studio", "2024-01-02 03:04:05.702   567-890   My Tag                  pid-567                              V  spaced",
     dict(tag="My Tag", package=None, level=Level.VERBOSE, message="spaced")),
    ("studio", "2024-01-02 03:04:05.679  1234-1234  ActivityManager         system_process                       I  Start proc",
     dict(tag="ActivityManager", package="system_process")),
    ("studio-legacy", "2024-01-02 03:04:05.678 1234-5678/com.example.app D/MyTag: hello world",
     dict(pid=1234, tid=5678, package="com.example.app", tag="MyTag", message="hello world")),
    ("studio-legacy", "2024-01-02 03:04:05.701 4321-4321/? E/AndroidRuntime: FATAL",
     dict(package=None, level=Level.ERROR, tag="AndroidRuntime")),
]


@pytest.mark.parametrize("parser_id,line,expected", CASES)
def test_parse_line(registry, parser_id, line, expected):
    entry = registry.get(parser_id).parse(line)
    assert entry is not None, f"{parser_id} did not match {line!r}"
    assert entry.raw == line
    assert entry.format_id == parser_id
    for name, value in expected.items():
        assert getattr(entry, name) == value, name


@pytest.mark.parametrize("parser_id,line", [
    ("threadtime", "D/MyTag( 1234): hello"),
    ("threadtime", "\tat com.example.Foo.bar(Foo.kt:12)"),
    ("time", "01-02 03:04:05.678  1234  5678 D MyTag: m"),
    ("brief", "hello world"),
    ("studio", "01-02 03:04:05.678  1234  5678 D MyTag: m"),
    ("thread", "D/MyTag( 1234): hello"),
    ("process", "D( 1234: 5678) hello"),
])
def test_parser_rejects_other_formats(registry, parser_id, line):
    assert registry.get(parser_id).parse(line) is None


def test_raw_parser_accepts_anything(registry):
    entry = registry.raw.parse("anything at all")
    assert entry.message == "anything at all"
    assert entry.level is None and entry.tag is None and entry.pid is None
