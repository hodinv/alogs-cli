# 02 — UI layout

## Zones

The screen is divided into three zones plus a status bar.

```
┌──────────────────────────────── ~70% ─────────────────────────────┬──────── ~30% ────────┐
│ LOG ZONE                                                          │ ACTIVE FILTERS (~40%)│
│ 01-02 03:04:05.678  1234  5678 I ActivityManager: Start proc ...  │ App:                 │
│ 01-02 03:04:05.701  4321  4321 D MyTag: hello                     │   com.example.app    │
│ 01-02 03:04:05.702  4321  4330 W OkHttp: slow response            │   (PIDs 4321, 4502)  │
│ 01-02 03:04:05.703  4321  4321 E AndroidRuntime: FATAL EXCEPTION  │ Levels: W E F        │
│     at com.example.Foo.bar(Foo.kt:12)                             │ Tags:                │
│ ...                                                               │  [x] MyTag           │
│                                                                   │  [x] OkHttp          │
│                                                                   ├──────────────────────┤
│                                                                   │ AVAILABLE TAGS (~60%)│
│                                                                   │  AndroidRuntime  312 │
│                                                                   │  Choreographer   120 │
│                                                                   │  ViewRootImpl     88 │
├───────────────────────────────────────────────────────────────────┤  ...                 │
│ > levels +WARN                                                    │                      │
│ Levels: W                                                         │                      │
├───────────────────────────────────────────────────────────────────┴──────────────────────┤
│ file: crash.log │ format: threadtime+year │ 1 204 311 lines │ shown 3 412 │ LIVE/PAUSED      │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### Log zone (left, top)

- Shows the **filtered** entries only, in source order.
- Virtualized scrolling: only visible rows are rendered (see [06](06-architecture.md)).
- Lines coloured by level (V grey, D blue, I green, W yellow, E red, F/A magenta-bold).
- Continuation lines (stack traces, multi-line messages) are shown indented under their entry and
  always follow the visibility of that entry.
- Horizontal overflow: the log zone scrolls horizontally (`←`/`→`, shift+wheel). A wrap toggle
  is a possible future addition.
- **Follow mode** (live adb): when scrolled to the bottom, the view sticks to new lines. Scrolling
  up pauses following (status `PAUSED`); `End` jumps to the bottom without animation and resumes.

### Command zone (left, bottom)

- One-line input with prompt `>`; history navigation with ↑/↓ (persisted between sessions).
- Tab completion for command names and file paths.
- Below the input: a small output area (≈ 3–6 lines, scrollable) for command results and errors.
- Larger outputs (`help`, `format list`) open in a modal or temporarily replace the output area.

### Filter zone (right, ~30% width)

Split vertically:

1. **Active filters (top ~40%)**
   - *App*: selected packages and/or PIDs (with the PIDs a package resolves to). Shows "all" when
     nothing selected.
   - *Levels*: enabled levels. Shows "all" when all enabled.
   - *Tags*: selected tags, each clickable.
   - Clicking an **app** or **level** item does **nothing** — these are controlled by commands
     (`app`, `levels`).
   - Clicking a **selected tag** removes it from the selection (it moves to the list below).
2. **Available tags (bottom ~60%)**
   - Tags present in entries that pass the **other** active filters (app/PID + levels), minus the
     already-selected tags. Example: if filtered to `com.example.app`, only that app's tags are
     listed.
   - Sorted by number of matching entries (desc, then name), count shown after the tag; a
     "search tags" box at the top narrows the list (case-insensitive substring).
   - Clicking a tag selects it (moves it to the top list).
   - When no tags are available (format has none, e.g. `raw`, or nothing matches) a hint says so.
   - Tag counts refresh at most every 0.5 s while a file is loading.

### Status bar

Source (file name or `adb <serial>`), detected format id, total entries, shown entries,
live/paused indicator, current errors (e.g. "adb disconnected").

## Keyboard & mouse

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Cycle focus: command → log → active filters → available tags |
| `:` or `/` | Focus the command input from anywhere |
| `PgUp` / `PgDn` / `Home` / `End` | Scroll the log (End also resumes follow) |
| `↑` / `↓` | Scroll log by line (when log has focus); history (when command has focus) |
| `Enter` / `Space` | Toggle the highlighted tag in a tag list |
| `Ctrl+Q` | Exit (same as `exit`). `Ctrl+C` copies selected text, as in all Textual apps. |
| Mouse wheel | Scroll the zone under the cursor |
| Mouse click | Tag toggle; focus zone |

## Resizing

Proportions are relative (70/30 horizontal, 40/60 inside the filter zone) and recomputed on
terminal resize. Below 100 columns the filter zone may be hidden and toggled with `F2`.
