"""Parser registry: built-in layouts plus user formats (docs/09, section 3.3)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .layouts import LAYOUTS
from .parsers import LineParser, RawParser, RegexParser

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


class FormatConfigError(Exception):
    pass


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, LineParser] = {}

    def register(self, parser: LineParser) -> None:
        self._parsers[parser.id] = parser

    def get(self, parser_id: str) -> LineParser | None:
        return self._parsers.get(parser_id)

    def all(self) -> list[LineParser]:
        return list(self._parsers.values())

    def candidates(self) -> list[LineParser]:
        """Parsers taking part in detection/fallback, most specific first."""
        found = [p for p in self._parsers.values() if p.id != RawParser.id]
        return sorted(found, key=lambda p: -p.specificity)

    @property
    def raw(self) -> LineParser:
        return self._parsers[RawParser.id]


def load_user_formats(path: Path) -> list[RegexParser]:
    """Read `[[format]]` tables with `id`, `regex` and optional `level_map`."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise FormatConfigError(f"{path}: {e}") from e
    parsers = []
    for i, fmt in enumerate(data.get("format", [])):
        fid, regex = fmt.get("id"), fmt.get("regex")
        if not fid or not regex:
            raise FormatConfigError(f"{path}: format #{i + 1} needs 'id' and 'regex'")
        try:
            parser = RegexParser(
                fid,
                regex,
                description=fmt.get("description", "user-defined format"),
                sample=fmt.get("sample", ""),
                level_map=fmt.get("level_map"),
            )
        except re.error as e:
            raise FormatConfigError(f"{path}: format '{fid}': bad regex: {e}") from e
        if "msg" not in parser._re.groupindex:
            raise FormatConfigError(f"{path}: format '{fid}': regex needs a (?P<msg>...) group")
        parsers.append(parser)
    return parsers


def default_registry(user_formats: Path | None = None) -> ParserRegistry:
    registry = ParserRegistry()
    for layout in LAYOUTS:
        registry.register(RegexParser.from_layout(layout))
    registry.register(RawParser())
    if user_formats is not None and user_formats.exists():
        for parser in load_user_formats(user_formats):
            registry.register(parser)
    return registry
