"""Log file source (docs/05, "File source")."""

from __future__ import annotations

import codecs
from collections.abc import Iterator
from pathlib import Path

CHUNK_SIZE = 1 << 20
_PROBE_SIZE = 8192


class SourceError(Exception):
    pass


def _sniff_encoding(head: bytes) -> str:
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    # UTF-16 without BOM: logs are mostly ASCII, so many high bytes are NUL
    # while low bytes (almost) never are.
    if len(head) >= 64:
        odd_nuls = head[1::2].count(0)
        even_nuls = head[0::2].count(0)
        half = len(head) // 2
        if odd_nuls > half * 0.3 and even_nuls < half * 0.02:
            return "utf-16-le"
        if even_nuls > half * 0.3 and odd_nuls < half * 0.02:
            return "utf-16-be"
    return "utf-8"


class FileSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.bytes_read = 0
        self.size = 0
        self._encoding = "utf-8"

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def progress(self) -> float:
        return self.bytes_read / self.size if self.size else 1.0

    def check(self, force: bool = False) -> None:
        """Validate the file before loading; raises SourceError."""
        if not self.path.exists():
            raise SourceError(f"File not found: {self.path}")
        if not self.path.is_file():
            raise SourceError(f"Not a file: {self.path}")
        try:
            self.size = self.path.stat().st_size
            with self.path.open("rb") as f:
                head = f.read(_PROBE_SIZE)
        except OSError as e:
            raise SourceError(f"Cannot read {self.path}: {e.strerror or e}") from e
        self._encoding = _sniff_encoding(head)
        if not force and self._encoding == "utf-8" and b"\x00" in head:
            raise SourceError(
                f"{self.path.name} looks like a binary file; use 'open -f' to open it anyway"
            )

    def iter_lines(self) -> Iterator[str]:
        """Decoded lines without line terminators (handles LF and CRLF)."""
        decoder = codecs.getincrementaldecoder(self._encoding)(errors="replace")
        rest = ""
        with self.path.open("rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                self.bytes_read += len(chunk)
                text = rest + decoder.decode(chunk, final=not chunk)
                if not chunk:
                    break
                lines = text.split("\n")
                rest = lines.pop()
                for line in lines:
                    yield line[:-1] if line.endswith("\r") else line
        if text:
            yield text[:-1] if text.endswith("\r") else text
