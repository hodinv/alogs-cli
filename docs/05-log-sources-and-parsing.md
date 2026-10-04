# 05 — Log sources & package resolution

Text → entry parsing (formats, parsers, detection) is described in
[09 – Log formats & parsers](09-log-formats-and-parsers.md). This document covers where the text
comes from and how apps are mapped to PIDs.

## Source interface

```python
class LogSource(Protocol):
    name: str                       # shown in status bar
    is_live: bool
    async def lines(self) -> AsyncIterator[str]   # raw text lines, newline stripped
    async def stop(self) -> None
    def app_resolver(self) -> AppResolver          # package <-> pid mapping
```

Both sources feed the same pipeline: `lines → ParserPipeline → LogStore → FilterEngine → UI`.

## File source (`open`)

- Read in binary chunks (e.g. 1 MiB), split on `\n`, strip trailing `\r` (Windows files).
- Decode as UTF-8 with `errors="replace"`; if a BOM is present (UTF-8/UTF-16) honour it — Windows
  tools sometimes save UTF-16 LE.
- Strip ANSI escape sequences (files saved from `logcat -v color` or from terminals).
- Parsing runs in a worker; entries are appended in batches (e.g. every 10 000 lines or 50 ms) so
  the UI stays responsive and shows progress.
- Compressed files (`.gz`, `.zip` bugreports) — future (see [08](08-roadmap.md)).

## ADB source (`openadb`)

- Locate `adb`, first match wins:
  1. `PATH`;
  2. `sdk.dir` from `local.properties` in the current folder or the nearest parent that has
     one (the file Android Studio / Gradle write into every project; Java properties escaping
     such as `C\:\\Users\\me\\Sdk` and `\uXXXX` is decoded);
  3. `$ANDROID_HOME`, `$ANDROID_SDK_ROOT`;
  4. default SDK locations per OS (`%LOCALAPPDATA%\Android\Sdk`, `~/Library/Android/sdk`,
     `~/Android/Sdk`).

  In each SDK folder the binary is `platform-tools/adb[.exe]`.
- `ALOGS_ADB` environment variable overrides discovery (a full command, used by the tests'
  fake adb).
- `adb devices` first: 0 devices → error; >1 → error listing serials unless `-s` was given;
  `unauthorized` / `offline` devices → error.
- Because we start the process, we choose a predictable format:

  ```
  adb [-s SERIAL] logcat -v threadtime -v year -v usec
  ```

  If the device's logcat rejects a modifier (very old Android), retry with `-v threadtime` only.
  Format detection still runs on the stream as a safety net for OEM quirks.
- Run with `subprocess.Popen` in a worker thread; helper threads pump stdout/stderr into a
  queue. When nothing arrives for 0.2 s (and at least every 0.1 s on a busy stream) the parser
  pipeline is flushed so new lines show up immediately.
- Memory cap: ring buffer of N entries (default 2 000 000); the oldest 10% are dropped at once,
  the status bar shows "dropped X", filters/tag counts are adjusted incrementally.
- On process exit: "adb logcat stopped (exit code N) — <stderr>"; entries are kept; `openadb`
  again restarts. Opening a file or another `openadb` stops the running adb process.

## Package ↔ PID resolution (`AppResolver`)

| Source | Strategy |
|---|---|
| adb | `adb shell ps -A -o PID,NAME` (fallback `adb shell ps` on old devices; NAME = last column, kernel threads skipped); process name of app processes is the package (`com.pkg` or `com.pkg:service`). Refreshed every 5 s. Old mappings are kept (PIDs of dead processes still map to their package). Lines from the log itself are used too. |
| file | Scan entries of `ActivityManager` / `ActivityTaskManager` / `am_proc_start` for `Start proc 1234:com.pkg/u0a12 …` (Android 7+), `Start proc com.pkg for … pid=1234` (≤ 6), `Process com.pkg (pid 1234) has died`, `[0,1234,10123,com.pkg,…]` events. |
| Android Studio export | Package is a field in the line itself — used directly. |
| fallback | Bare PIDs with entry counts. |

Processes like `com.pkg:remote` are grouped under `com.pkg` in the `app` list. When a mapping
changes for a selected app (app restarted, `ps` refresh), the filter is recomputed.
