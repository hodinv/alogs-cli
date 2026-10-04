"""Stand-in for `adb`, driven by environment variables (used via ALOGS_ADB).

FAKE_ADB_DEVICES      "serial:state,serial:state" or "none" (default "emulator-5554:device")
FAKE_ADB_LOG          file whose lines `logcat` prints
FAKE_ADB_DELAY        seconds between logcat lines (default 0)
FAKE_ADB_PAUSE_AT     after this many logcat lines, wait until FAKE_ADB_RESUME_FILE exists
FAKE_ADB_HANG         if set, logcat keeps running after the file (like a real device)
FAKE_ADB_EXIT         logcat exit code after the file (default 0)
FAKE_ADB_NO_MODIFIERS if set, logcat rejects `-v year` like very old devices
FAKE_ADB_PS           file printed by `shell ps ...`
FAKE_ADB_CALLS        file to which every invocation's arguments are appended
"""

from __future__ import annotations

import os
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    calls = os.environ.get("FAKE_ADB_CALLS")
    if calls:
        with open(calls, "a", encoding="utf-8") as f:
            f.write(" ".join(args) + "\n")
    if args[:1] == ["-s"]:
        args = args[2:]

    if args == ["devices"]:
        print("List of devices attached")
        spec = os.environ.get("FAKE_ADB_DEVICES", "emulator-5554:device")
        for item in filter(None, spec.split(",") if spec != "none" else []):
            serial, state = item.split(":")
            print(f"{serial}\t{state}")
        print()
        return 0

    if args[:1] == ["logcat"]:
        if os.environ.get("FAKE_ADB_NO_MODIFIERS") and "year" in args:
            print("logcat: Invalid -v argument 'year'", file=sys.stderr)
            return 1
        delay = float(os.environ.get("FAKE_ADB_DELAY", "0"))
        pause_at = int(os.environ.get("FAKE_ADB_PAUSE_AT", "0"))
        resume_file = os.environ.get("FAKE_ADB_RESUME_FILE", "")
        with open(os.environ["FAKE_ADB_LOG"], encoding="utf-8") as f:
            for count, line in enumerate(f):
                if pause_at and count == pause_at:
                    # deterministic tests: stop until the test creates the resume file
                    while not os.path.exists(resume_file):
                        time.sleep(0.02)
                sys.stdout.write(line)
                sys.stdout.flush()
                if delay:
                    time.sleep(delay)
        if os.environ.get("FAKE_ADB_HANG"):
            time.sleep(120)
        print("logcat: device went away", file=sys.stderr)
        return int(os.environ.get("FAKE_ADB_EXIT", "0"))

    if args[:2] == ["shell", "ps"]:
        path = os.environ.get("FAKE_ADB_PS")
        if path:
            with open(path, encoding="utf-8") as f:
                sys.stdout.write(f.read())
        return 0

    print(f"fake adb: unsupported {args}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
