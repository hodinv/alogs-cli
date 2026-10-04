"""Build a single-file `alogs` executable for the current OS with PyInstaller.

    uv run --group build python scripts/build_binary.py

PyInstaller cannot cross-compile: run this on Windows, macOS and Linux to get
one binary per OS. The result is dist/alogs-<version>-<os>-<arch>[.exe]; it is
smoke-tested with `--self-test` on a sample log before the script reports success.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "tests" / "fixtures" / "formats" / "threadtime.log"


def version() -> str:
    namespace: dict[str, str] = {}
    exec((ROOT / "alogs" / "__init__.py").read_text(encoding="utf-8"), namespace)
    return namespace["__version__"]


def target_name() -> str:
    system = {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    suffix = ".exe" if os.name == "nt" else ""
    return f"alogs-{version()}-{system}-{machine}{suffix}"


def main() -> int:
    build_dir = ROOT / "build"
    dist_dir = ROOT / "dist"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--clean", "--noconfirm",
        "--name", "alogs",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        # Textual imports widgets lazily and Rich loads Unicode tables by
        # name, so PyInstaller's import scan misses them.
        "--collect-submodules", "textual",
        "--collect-data", "textual",
        "--collect-submodules", "rich",
        "--add-data", f"{ROOT / 'alogs' / 'app.tcss'}{os.pathsep}alogs",
        str(ROOT / "scripts" / "alogs_entry.py"),
    ]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)

    built = dist_dir / ("alogs.exe" if os.name == "nt" else "alogs")
    target = dist_dir / target_name()
    shutil.move(built, target)

    print(f"+ {target.name} --self-test {SAMPLE.name}", flush=True)
    result = subprocess.run([str(target), "--self-test", str(SAMPLE)], capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())
    if result.returncode != 0:
        print("self-test FAILED", file=sys.stderr)
        return 1
    size = target.stat().st_size / 1e6
    print(f"built {target} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
