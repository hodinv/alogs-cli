from __future__ import annotations

from alogs.model.entry import Level
from alogs.parsing import pipeline as pipeline_mod
from alogs.parsing.pipeline import ParserPipeline

from .conftest import FORMATS, parse_text


def load(registry, name, forced=None):
    return parse_text(registry, (FORMATS / f"{name}.log").read_text(encoding="utf-8"), forced)


def test_threadtime_continuations_and_separators(registry):
    entries, detection = load(registry, "threadtime")
    assert detection.parser_id == "threadtime"
    seps = [e for e in entries if e.is_separator]
    assert [s.buffer for s in seps] == ["main", "system"]
    crash = next(e for e in entries if "IllegalStateException" in e.message)
    assert crash.cont == ["\tat com.example.Foo.bar(Foo.kt:12)", "\tat com.example.Foo.main(Foo.kt:3)"]
    assert crash.buffer == "main"
    spaced = next(e for e in entries if e.tag == "My Tag With Spaces")
    assert spaced.buffer == "system"
    # every source line is kept exactly once
    text = (FORMATS / "threadtime.log").read_text(encoding="utf-8").splitlines()
    assert [line for e in entries for line in e.text_lines()] == text


def test_long_format_bodies(registry):
    entries, detection = load(registry, "long")
    assert detection.parser_id == "long"
    assert [e.tag for e in entries] == ["MyTag", "ActivityManager", "AndroidRuntime"]
    assert entries[0].message == "hello world"
    assert entries[2].message == "FATAL EXCEPTION: main"
    assert entries[2].cont == [
        "FATAL EXCEPTION: main",
        "java.lang.IllegalStateException: boom",
        "\tat com.example.Foo.bar(Foo.kt:12)",
    ]


def test_mixed_file_uses_fallback_parsers(registry):
    entries, detection = load(registry, "mixed")
    assert detection.parser_id == "threadtime"
    assert [e.format_id for e in entries] == [
        "threadtime", "threadtime", "threadtime", "threadtime", "brief", "brief", "threadtime",
    ]
    assert entries[4].pid == 2222 and entries[4].tag == "Other"


def test_bugreport_preamble_and_log_section(registry):
    entries, detection = load(registry, "bugreport")
    assert detection.parser_id == "threadtime"
    logs = [e for e in entries if e.format_id == "threadtime"]
    assert len(logs) == 14
    assert logs[0].uid == "1000" and logs[0].pid == 1234
    # preamble before the first log entry becomes raw entries
    assert entries[0].format_id == "raw"


def test_studio_continuation(registry):
    entries, _ = load(registry, "studio")
    crash = next(e for e in entries if e.message == "FATAL EXCEPTION: main")
    assert crash.cont and "IllegalStateException" in crash.cont[0]


def test_forced_raw_makes_every_line_an_entry(registry):
    entries, detection = load(registry, "threadtime", forced="raw")
    assert detection.forced
    assert all(e.format_id in ("raw", "separator") for e in entries)
    assert all(e.cont is None for e in entries)


def test_forced_parser_does_not_fall_back(registry):
    entries, _ = load(registry, "mixed", forced="threadtime")
    brief_lines = [e for e in entries if e.raw.startswith("D/Other")]
    assert brief_lines == []  # became continuation lines instead
    assert entries[3].cont == ["D/Other   ( 2222): from a brief log", "I/Other   ( 2222): second brief line"]


def test_ansi_codes_are_stripped(registry):
    entries, _ = parse_text(registry, "\x1b[38;5;196m01-02 03:04:05.678  1234  5678 E Tag: boom\x1b[0m")
    assert entries[0].level is Level.ERROR
    assert entries[0].message == "boom"


def test_redetection_switches_parser(registry, monkeypatch):
    monkeypatch.setattr(pipeline_mod, "REDETECT_WINDOW", 20)
    monkeypatch.setattr(pipeline_mod, "SAMPLE_SIZE", 10)
    pipeline = ParserPipeline(registry)
    out = []
    for i in range(10):
        pipeline.feed(f"D/Tag( {i + 1}): brief {i}", out)
    for i in range(60):
        pipeline.feed(f"01-02 03:04:05.{i:03d}  1  2 I Tag: tt {i}", out)
    pipeline.flush(out)
    assert pipeline.detection.parser_id == "threadtime"
    assert len(out) == 70


def test_small_input_detected_on_flush(registry):
    entries, detection = parse_text(registry, "D/Tag( 1): a\nD/Tag( 1): b")
    assert detection.parser_id == "brief"
    assert len(entries) == 2
