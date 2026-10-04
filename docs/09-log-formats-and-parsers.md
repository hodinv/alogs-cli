# 09 — Log formats & parsers

The hardest part of the tool: the same logcat data is printed in many layouts. Depending on the
phone, Android version, `logcat -v` options and the tool that saved the file, the **position and
shape** of date/time, level, PID/TID and tag differ. The design is therefore a **set of pluggable
parsers with auto-detection**, all producing one normalized entry.

Prior art used as reference: lnav (auto-detected formats defined by regexes with named groups),
Plaso's `android_logcat` parser, rogcat, pidcat, Android Studio's Logcat.

## 1. Format catalog

Each sample below becomes a fixture in `tests/fixtures/formats/`.

### 1.1 `logcat -v <format>` base formats

| id | Sample |
|---|---|
| `brief` | `D/MyTag( 1234): message` |
| `process` | `D( 1234) message  (MyTag)` |
| `tag` | `D/MyTag: message` |
| `thread` | `D( 1234: 5678) message` |
| `raw` | `message` |
| `time` | `01-02 03:04:05.678 D/MyTag( 1234): message` |
| `threadtime` | `01-02 03:04:05.678  1234  5678 D MyTag   : message` (default on modern Android) |
| `long` | multi-line, see below |

`long`:

```
[ 01-02 03:04:05.678  1234: 5678 D/MyTag ]
first line of message
second line of message

```

### 1.2 Modifiers (combinable: `-v threadtime -v year -v usec` or `-v threadtime,year,usec`)

| Modifier | Effect on the line |
|---|---|
| `year` | `2024-01-02 03:04:05.678 …` |
| `usec` / `nsec` | fraction has 6 / 9 digits: `03:04:05.678901` |
| `epoch` | time replaced by seconds since 1970: `1704164645.678 …` |
| `monotonic` | seconds since boot, space-padded: `   123.456 …` |
| `UTC` | time printed in UTC (shape unchanged) |
| `zone` | time zone appended: `03:04:05.678 +0000` |
| `uid` | uid inserted before PID: `01-02 03:04:05.678 u0_a123  1234  5678 D …` (or numeric `10123`, or `root`/`system`) |
| `color` | ANSI colour codes around the line |
| `printable` | non-printable bytes escaped |
| `descriptive` | event-log values described (affects `events` buffer messages only) |

### 1.3 Tool & vendor variants

| id | Sample |
|---|---|
| `studio` (Android Studio ≥ Dolphin, copy/export) | `2024-01-02 03:04:05.678  1234-5678  MyTag                   com.example.app                      D  message` |
| `studio-legacy` (old Android Studio) | `2024-01-02 03:04:05.678 1234-5678/com.example.app D/MyTag: message` (package may be `?`) |
| bugreport | logcat sections inside `bugreport-*.txt`, framed by `------ SYSTEM LOG (logcat -v threadtime …) ------`; mixed with non-log content |
| OEM quirks | extra spaces / tabs, very wide PIDs (> 5 digits), tags with spaces or `:` (`My Tag: msg`), empty tags, level letter in lowercase, CRLF line endings |
| separators | `--------- beginning of main`, `--------- beginning of crash`, `--------- switch to system` |

Separators are recognized everywhere and stored as special entries (shown dimmed, never filtered
out) — they also indicate the buffer of following entries.

## 2. Normalized entry

```python
@dataclass(slots=True)
class LogEntry:
    raw: str                     # original first line
    cont: list[str] | None       # continuation lines (stack traces, long-format bodies)
    message: str
    level: Level | None
    tag: str | None
    pid: int | None
    tid: int | None
    uid: str | None
    package: str | None          # only when the format carries it (studio)
    time_kind: TimeKind          # WALL_NO_YEAR | WALL | EPOCH | MONOTONIC | NONE
    time_text: str | None        # original text, used for display
    buffer: str | None           # main/system/crash/... from separators
    format_id: str
```

Every field except `raw`/`message` is optional; filters and UI degrade gracefully when a field is
missing (see [04](04-filtering-model.md)). Numeric time is computed on demand with
`timestamps.to_seconds(time_text, time_kind, default_year)` (not stored, to keep entries small);
dates without year use the given year (file mtime or current year) for sorting only — display
always uses `time_text`.

## 3. Parser architecture

### 3.1 Building blocks instead of one regex per combination

Combinations of formats × modifiers explode, so parsers are **composed**:

- **Timestamp patterns** (`parsing/timestamps.py`), each a named regex fragment:
  - `MMDD`: `\d\d-\d\d \d\d:\d\d:\d\d\.\d{3,9}`
  - `YMD`: `\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3,9}`
  - `EPOCH`: `\d{9,}\.\d{3,9}`
  - `MONO`: `\s*\d+\.\d{3,9}`
  - optional zone suffix: `(?:\s[+-]\d{4})?`
  - combined `TS = (?P<ts>MMDD|YMD|EPOCH|MONO)(?P<zone>...)?`
- **Optional uid fragment**: `(?:(?P<uid>u\d+_\w+|\d+|[a-z_]+)\s+)?`
- **Header layouts** (`parsing/layouts.py`), written with those fragments, e.g.

  ```
  threadtime:    ^{TS}\s+{UID}(?P<pid>\d+)\s+(?P<tid>\d+)\s+(?P<lvl>[VDIWEFAS])\s+(?P<tag>.*?)\s*:\s(?P<msg>.*)$
  time:          ^{TS}\s+(?P<lvl>[VDIWEFAS])/(?P<tag>.*?)\(\s*{UID}(?P<pid>\d+)\):\s(?P<msg>.*)$
  brief:         ^(?P<lvl>[VDIWEFAS])/(?P<tag>.*?)\(\s*(?P<pid>\d+)\):\s(?P<msg>.*)$
  process:       ^(?P<lvl>[VDIWEFAS])\(\s*(?P<pid>\d+)\)\s(?P<msg>.*?)\s+\((?P<tag>.*)\)$
  tag:           ^(?P<lvl>[VDIWEFAS])/(?P<tag>.*?):\s(?P<msg>.*)$
  thread:        ^(?P<lvl>[VDIWEFAS])\(\s*(?P<pid>\d+):\s*(?P<tid>\d+)\)\s(?P<msg>.*)$
  studio:        ^{TS}\s+(?P<pid>\d+)-(?P<tid>\d+)\s+(?P<tag>\S.*?)\s{2,}(?P<pkg>\S+)\s+(?P<lvl>[VDIWEFA])\s{2}(?P<msg>.*)$
  studio-legacy: ^{TS}\s+(?P<pid>\d+)-(?P<tid>\d+)/(?P<pkg>\S+)\s+(?P<lvl>[VDIWEFA])/(?P<tag>.*?):\s(?P<msg>.*)$
  long-header:   ^\[\s{TS}\s+{UID}(?P<pid>\d+):\s*(?P<tid>\d+)\s+(?P<lvl>[VDIWEFAS])/(?P<tag>.*?)\s+\]$
  ```

  (Exact regexes are finalized and tuned against fixtures during implementation; tag matching is
  non-greedy up to the *first* `: ` after the level for threadtime, which handles tags with
  spaces.)

### 3.2 Interfaces

```python
class LineParser(Protocol):
    id: str
    fields: frozenset[str]                 # which LogEntry fields it can fill (for scoring)
    def parse(self, line: str) -> LogEntry | None
    def is_continuation(self, line: str, prev: LogEntry) -> bool   # default: not a header
    multiline: bool = False                # long: header + body until blank line

class RegexParser(LineParser): ...         # built from a layout + timestamp fragments
class LongParser(LineParser): ...          # stateful, for -v long
class RawParser(LineParser): ...           # always matches; message only (last resort)
```

### 3.3 Registry

- Built-in parsers registered at import time.
- **User-defined formats** loaded from `formats.toml`:

  ```toml
  [[format]]
  id = "my-oem"
  regex = '^(?P<ts>\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) \[(?P<lvl>\w)\] (?P<tag>[^:]+): (?P<msg>.*)$'
  level_map = { "V"="V", "D"="D", "I"="I", "W"="W", "E"="E" }  # optional
  ```

  Named groups `ts`, `lvl`, `tag`, `pid`, `tid`, `uid`, `pkg`, `msg` map to entry fields. Shown in
  `format list`, take part in detection like built-ins.

## 4. Pipeline & auto-detection

```
raw line ─► strip ANSI / \r ─► separator? ─► locked parser ─► ok ─► entry
                                              │ fail
                                              ▼
                                   other parsers (by score order)  ─► ok ─► entry
                                              │ all fail
                                              ▼
                     previous entry exists? ─► continuation line of previous entry
                                              │ no
                                              ▼
                                        raw entry (message only)
```

### Detection

1. Take the first ~200 non-empty, non-separator lines (for files: also sample from the middle to
   skip headers such as bugreport preambles).
2. For each parser compute `score = matched_lines / sampled_lines`. Indented lines that no
   parser header matches (stack traces, Studio continuation lines) are neutral; for multi-line
   formats (`long`) body lines following a header count as matched.
3. Choose the highest score; tie-break by **specificity** = number of fields the parser fills
   (threadtime > time > brief > tag > raw). Parsers below 30% are never chosen.
4. Lock the chosen parser for the source; status bar shows `format: threadtime+year+usec (98%)`.

### Robustness

- Lines that fail the locked parser are tried against the others → mixed files (bugreports, logs
  concatenated from several sessions) work.
- Lines matched by nobody become **continuation lines** of the previous entry (Java stack traces,
  multi-line messages) — they inherit visibility.
- **Re-detection**: if over a sliding window of 500 lines fewer than 50% parse with the locked
  parser, detection runs again on that window.
- **Override**: `format <id>` forces a parser (no detection); `format auto` restores detection
  ([03](03-commands.md#format-list--auto--id)).

### Level normalization

Accept `V D I W E F A S` and lowercase; Studio may print `A` for assert; unknown letters → `None`
level (shown uncoloured).

## 5. Tests

- `tests/fixtures/formats/<name>.log` for every catalog entry, including modifiers combined with
  `threadtime` and `time`, both Studio variants, a bugreport excerpt and a mixed-format file.
- Detection test: each fixture is detected as the expected parser id **and** variant
  (e.g. `threadtime (year, usec)`).
- Per-line tests with explicit expected fields for tricky lines (tags with spaces/colons, uid
  forms, zones, empty messages, lowercase levels).
- Property test: generate random entries, render them in every logcat layout like `logprint.c`,
  parse back (forced and auto-detected), compare fields.
- Performance test: 1M threadtime lines parsed within the budget from
  [06](06-architecture.md#performance).
