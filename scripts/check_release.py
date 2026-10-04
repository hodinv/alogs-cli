"""Pre-publish checks run by .github/workflows/release.yml.

    python scripts/check_release.py v0.2.0

Fails (exit 1) unless:
  - the tag is `v` + the version in alogs/__init__.py (e.g. v0.2.0 <-> "0.2.0"),
  - the version is a plain release / pre-release number (0.2.0, 1.0.0rc1, ...),
  - pyproject.toml no longer contains the OWNER placeholder of the GitHub URLs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?$")


def code_version(root: Path = ROOT) -> str:
    text = (root / "alogs" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("alogs/__init__.py has no __version__")
    return match.group(1)


def problems(tag: str, root: Path = ROOT) -> list[str]:
    found = []
    version = code_version(root)
    if tag != f"v{version}":
        found.append(f"tag {tag!r} does not match __version__ {version!r} (expected tag 'v{version}')")
    if not VERSION_RE.match(version):
        found.append(f"version {version!r} is not like 1.2.3 or 1.2.3rc1")
    if "OWNER/" in (root / "pyproject.toml").read_text(encoding="utf-8"):
        found.append("pyproject.toml still contains the OWNER placeholder in the GitHub URLs")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    found = problems(argv[0])
    for problem in found:
        print(f"::error::{problem}")  # GitHub Actions annotation; plain text elsewhere
    if not found:
        print(f"release {argv[0]} OK")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
