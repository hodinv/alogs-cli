from __future__ import annotations

import pytest

from alogs.export import export_entries
from alogs.parsing.registry import FormatConfigError, default_registry, load_user_formats
from alogs.parsing.timestamps import to_seconds
from alogs.model.entry import TimeKind
from alogs.sources.file_source import FileSource, SourceError

from .conftest import FORMATS, parse_text


def read_all(path, force=False):
    src = FileSource(path)
    src.check(force)
    return list(src.iter_lines())


def test_crlf_and_missing_final_newline(tmp_path):
    p = tmp_path / "a.log"
    p.write_bytes(b"one\r\ntwo\r\nthree")
    assert read_all(p) == ["one", "two", "three"]


def test_utf8_bom_and_invalid_bytes(tmp_path):
    p = tmp_path / "a.log"
    p.write_bytes(b"\xef\xbb\xbfhello\n\xff\xfebad\n")
    assert read_all(p) == ["hello", "\ufffd\ufffdbad"]


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
def test_utf16(tmp_path, encoding):
    p = tmp_path / "a.log"
    text = "D/Tag( 1): привет\n" * 10
    p.write_bytes(text.encode(encoding))
    assert read_all(p) == ["D/Tag( 1): привет"] * 10


def test_large_file_chunk_boundaries(tmp_path, monkeypatch):
    from alogs.sources import file_source

    monkeypatch.setattr(file_source, "CHUNK_SIZE", 7)
    p = tmp_path / "a.log"
    lines = [f"line {i} ✓" for i in range(100)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert read_all(p) == lines


def test_missing_and_binary_files(tmp_path):
    with pytest.raises(SourceError, match="not found"):
        FileSource(tmp_path / "nope.log").check()
    p = tmp_path / "bin.dat"
    p.write_bytes(b"\x00\x01\x02garbage\x00" * 10)
    with pytest.raises(SourceError, match="binary"):
        FileSource(p).check()
    FileSource(p).check(force=True)


def test_export_roundtrip(tmp_path, registry):
    text = (FORMATS / "threadtime.log").read_text(encoding="utf-8")
    entries, _ = parse_text(registry, text)
    out = tmp_path / "out.log"
    assert export_entries(entries, out) == len(entries)
    assert out.read_text(encoding="utf-8") == text
    with pytest.raises(FileExistsError):
        export_entries(entries, out)
    assert export_entries(entries[:2], out, overwrite=True) == 2


def test_user_formats(tmp_path):
    cfg = tmp_path / "formats.toml"
    cfg.write_text(
        """
[[format]]
id = "my-oem"
regex = '^(?P<ts>\\d\\d:\\d\\d:\\d\\d\\.\\d{3}) \\[(?P<lvl>\\w+)\\] (?P<tag>[^:]+): (?P<msg>.*)$'
level_map = { "WARNING" = "W", "ERR" = "E" }
""",
        encoding="utf-8",
    )
    registry = default_registry(cfg)
    lines = [f"03:04:05.{i:03d} [WARNING] Net: slow {i}" for i in range(20)]
    entries, detection = parse_text(registry, "\n".join(lines))
    assert detection.parser_id == "my-oem"
    assert entries[0].tag == "Net" and entries[0].level.letter == "W"


def test_user_formats_errors(tmp_path):
    cfg = tmp_path / "formats.toml"
    cfg.write_text('[[format]]\nid = "x"\nregex = "("\n', encoding="utf-8")
    with pytest.raises(FormatConfigError, match="bad regex"):
        load_user_formats(cfg)
    cfg.write_text('[[format]]\nid = "x"\nregex = "(?P<tag>.*)"\n', encoding="utf-8")
    with pytest.raises(FormatConfigError, match="msg"):
        load_user_formats(cfg)


def test_to_seconds():
    assert to_seconds("1704164645.678", TimeKind.EPOCH) == pytest.approx(1704164645.678)
    assert to_seconds("123.5", TimeKind.MONOTONIC) == 123.5
    utc = to_seconds("2024-01-02 03:04:05.500", TimeKind.WALL)
    assert utc == pytest.approx(1704164645.5)
    assert to_seconds("2024-01-02 04:04:05.500 +0100", TimeKind.WALL) == pytest.approx(utc)
    assert to_seconds("01-02 03:04:05.500", TimeKind.WALL_NO_YEAR, 2024) == pytest.approx(utc)
