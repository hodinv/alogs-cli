from __future__ import annotations

from pathlib import Path

import pytest

from alogs.parsing.registry import ParserRegistry, default_registry

FIXTURES = Path(__file__).parent / "fixtures"
FORMATS = FIXTURES / "formats"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never touch the real user config dir from tests."""
    monkeypatch.setenv("ALOGS_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture
def registry() -> ParserRegistry:
    return default_registry()


def parse_text(registry: ParserRegistry, text: str, forced: str | None = None):
    from alogs.parsing.pipeline import ParserPipeline

    pipeline = ParserPipeline(registry, forced)
    out = []
    for line in text.splitlines():
        pipeline.feed(line, out)
    pipeline.flush(out)
    return out, pipeline.detection
