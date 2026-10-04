from __future__ import annotations

import pytest

from alogs.parsing.detect import detect

from .conftest import FORMATS

# fixture file -> (expected parser id, expected variant)
EXPECTED = {
    "threadtime": ("threadtime", []),
    "threadtime-year-usec": ("threadtime", ["year", "usec"]),
    "threadtime-epoch": ("threadtime", ["epoch"]),
    "threadtime-monotonic": ("threadtime", ["monotonic"]),
    "threadtime-uid": ("threadtime", ["uid"]),
    "threadtime-zone": ("threadtime", ["zone"]),
    "time": ("time", []),
    "time-year": ("time", ["year"]),
    "brief": ("brief", []),
    "process": ("process", []),
    "tag": ("tag", []),
    "thread": ("thread", []),
    "raw": ("raw", []),
    "long": ("long", []),
    "studio": ("studio", ["year"]),
    "studio-legacy": ("studio-legacy", ["year"]),
    "bugreport": ("threadtime", ["uid"]),
    "mixed": ("threadtime", []),
}


def test_every_fixture_has_an_expectation():
    names = {p.stem for p in FORMATS.glob("*.log")}
    assert names == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_detects_fixture(registry, name):
    lines = (FORMATS / f"{name}.log").read_text(encoding="utf-8").splitlines()
    result = detect(lines, registry)
    parser_id, variant = EXPECTED[name]
    assert result.parser_id == parser_id
    assert result.variant == variant


def test_empty_input_is_raw(registry):
    assert detect([], registry).parser_id == "raw"
    assert detect(["", "   "], registry).parser_id == "raw"


def test_describe(registry):
    lines = (FORMATS / "threadtime-year-usec.log").read_text(encoding="utf-8").splitlines()
    assert detect(lines, registry).describe() == "threadtime (year, usec) · 100%"
