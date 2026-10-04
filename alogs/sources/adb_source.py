"""Live `adb logcat` source (docs/05, "ADB source")."""

from __future__ import annotations

import os
import platform
import queue
import shlex
import shutil
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Preferred format first; the plain one is the fallback for devices whose
# logcat rejects modifiers (docs/05).
LOGCAT_FORMATS = (
    ["-v", "threadtime", "-v", "year", "-v", "usec"],
    ["-v", "threadtime"],
)
IDLE_SECONDS = 0.2  # quiet time after which iter_lines yields None (flush hint)
_CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class AdbError(Exception):
    pass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str  # device / unauthorized / offline / ...


def _split_command(value: str) -> list[str]:
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""  # keep backslashes of Windows paths
    return list(lexer)


def _unescape_property(value: str) -> str:
    """Java .properties escapes: `C\\:\\\\Users` -> `C:\\Users`, `\\uXXXX`, `\\t`..."""
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt == "u" and i + 6 <= len(value):
                try:
                    out.append(chr(int(value[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            out.append({"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def sdk_dir_from_local_properties(start: Path | None = None) -> Path | None:
    """`sdk.dir` from `local.properties` in `start` (default: the current
    directory) or one of its parents — where Android Studio / Gradle keep the
    SDK path of a project."""
    folder = (start or Path.cwd()).resolve()
    for directory in (folder, *folder.parents):
        props = directory / "local.properties"
        if not props.is_file():
            continue
        try:
            text = props.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for line in text.splitlines():
            line = line.strip()
            if not line or line[0] in "#!":
                continue
            key, sep, value = line.partition("=")
            if not sep:
                key, sep, value = line.partition(":")
            if key.strip() == "sdk.dir" and value.strip():
                return Path(_unescape_property(value.strip()))
        return None  # the nearest local.properties decides, even without sdk.dir
    return None


def _sdk_dirs() -> list[Path]:
    dirs = []
    from_props = sdk_dir_from_local_properties()
    if from_props is not None:
        dirs.append(from_props)
    dirs += [Path(os.environ[v]) for v in ("ANDROID_HOME", "ANDROID_SDK_ROOT") if os.environ.get(v)]
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Android" / "Sdk")
    elif system == "Darwin":
        dirs.append(home / "Library" / "Android" / "sdk")
    else:
        dirs.append(home / "Android" / "Sdk")
    return dirs


def find_adb() -> list[str] | None:
    """Command to run adb: `ALOGS_ADB` env (may include arguments, used by
    tests), then PATH, then `sdk.dir` of `local.properties`, then
    ANDROID_HOME / ANDROID_SDK_ROOT, then the default SDK folder per OS."""
    override = os.environ.get("ALOGS_ADB")
    if override:
        return _split_command(override)
    found = shutil.which("adb")
    if found:
        return [found]
    exe = "adb.exe" if os.name == "nt" else "adb"
    for sdk in _sdk_dirs():
        candidate = sdk / "platform-tools" / exe
        if candidate.is_file():
            return [str(candidate)]
    return None


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, creationflags=_CREATE_FLAGS
        )
    except FileNotFoundError as e:
        raise AdbError(f"cannot run adb: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise AdbError(f"'{' '.join(cmd[-2:])}' timed out") from e


def list_devices(adb: list[str]) -> list[Device]:
    result = _run([*adb, "devices"], timeout=30)
    if result.returncode != 0:
        raise AdbError(result.stderr.decode(errors="replace").strip() or "adb devices failed")
    devices = []
    for line in result.stdout.decode(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and not line.startswith(("List of devices", "*")):
            devices.append(Device(parts[0], parts[1]))
    return devices


def choose_device(devices: list[Device], serial: str | None) -> Device:
    if serial is not None:
        for d in devices:
            if d.serial == serial:
                break
        else:
            raise AdbError(f"device '{serial}' not found")
    elif not devices:
        raise AdbError("no devices/emulators found")
    elif len(devices) > 1:
        serials = ", ".join(d.serial for d in devices)
        raise AdbError(f"more than one device: {serials} — use 'openadb -s <serial>'")
    else:
        d = devices[0]
    if d.state == "unauthorized":
        raise AdbError(f"device {d.serial} is unauthorized — accept the USB debugging prompt on the device")
    if d.state != "device":
        raise AdbError(f"device {d.serial} is {d.state}")
    return d


def process_list(adb: list[str], serial: str) -> str:
    """Output of `ps` on the device (`-A -o PID,NAME`, or classic `ps`)."""
    for args in (["ps", "-A", "-o", "PID,NAME"], ["ps"]):
        result = _run([*adb, "-s", serial, "shell", *args], timeout=15)
        out = result.stdout.decode(errors="replace")
        if result.returncode == 0 and "PID" in out.split("\n", 1)[0]:
            return out
    return ""


class AdbSource:
    """Streams `adb logcat` lines. `iter_lines()` yields None after IDLE_SECONDS
    without output, so the consumer can flush the held-back entry."""

    is_live = True

    def __init__(self, adb: list[str], serial: str) -> None:
        self.adb = adb
        self.serial = serial
        self.returncode: int | None = None
        self.error = ""
        self._process: subprocess.Popen[bytes] | None = None
        self._stopped = threading.Event()

    @property
    def name(self) -> str:
        return f"adb {self.serial}"

    def stop(self) -> None:
        self._stopped.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def iter_lines(self) -> Iterator[str | None]:
        for i, fmt in enumerate(LOGCAT_FORMATS):
            last_attempt = i == len(LOGCAT_FORMATS) - 1
            produced = False
            for line in self._stream([*self.adb, "-s", self.serial, "logcat", *fmt]):
                produced = produced or line is not None
                yield line
            if produced or last_attempt or self._stopped.is_set() or self.returncode == 0:
                return
            # exited with an error before printing anything: try a simpler format

    def _stream(self, cmd: list[str]) -> Iterator[str | None]:
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                creationflags=_CREATE_FLAGS,
            )
        except OSError as e:
            self.returncode = -1
            self.error = f"cannot run adb: {e}"
            return
        self._process = process
        lines: queue.Queue[bytes | None] = queue.Queue(maxsize=100_000)
        stderr: list[bytes] = []

        def pump_stdout() -> None:
            assert process.stdout is not None
            for raw in process.stdout:
                lines.put(raw)
            lines.put(None)

        def pump_stderr() -> None:
            assert process.stderr is not None
            stderr.append(process.stderr.read())

        threading.Thread(target=pump_stdout, daemon=True).start()
        stderr_thread = threading.Thread(target=pump_stderr, daemon=True)
        stderr_thread.start()
        while True:
            try:
                raw = lines.get(timeout=IDLE_SECONDS)
            except queue.Empty:
                if self._stopped.is_set():
                    break
                yield None
                continue
            if raw is None:
                break
            text = raw.decode("utf-8", errors="replace")
            yield text.rstrip("\r\n")
        self.returncode = process.wait()
        stderr_thread.join(timeout=2)
        self.error = b"".join(stderr).decode(errors="replace").strip()
