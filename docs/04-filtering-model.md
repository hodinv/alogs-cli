# 04 — Filtering model

## Filter state

```python
@dataclass
class FilterState:
    apps: set[AppKey]          # packages and/or PIDs; empty = all
    levels: set[Level]         # enabled levels
    levels_touched: bool       # False = untouched (all on)
    tags: set[str]             # selected tags; empty = all
```

An entry is **visible** iff:

```
app_match(entry)   AND   level_match(entry)   AND   tag_match(entry)
```

- `app_match`: `apps` empty, or entry PID belongs to a selected PID, or to a PID mapped to a selected
  package. Entries without PID (format has none) match only when `apps` is empty.
- `level_match`: entry level in `levels`. Entries without level (e.g. `raw`) always match.
- `tag_match`: `tags` empty, or entry tag in `tags`. Entries without tag match only when `tags` is
  empty.

Continuation lines belong to their entry and never match/filter on their own.
Buffer separators (`--------- beginning of main`) are always visible.

## Levels

Order: `V < D < I < W < E < F < A`.

State machine:

| State | Command | Result |
|---|---|---|
| untouched (all on) | `+X` | only `{X}`, touched |
| untouched (all on) | `-X` | all except `X`, touched |
| touched | `+X` | add `X` |
| touched | `-X` | remove `X` |
| any | `levels all` | untouched (all on) |
| touched, set becomes empty | — | allowed; log zone shows "no levels enabled" hint |

Multiple arguments are applied left to right using the same table.

## Tags

- Selected tags are toggled only by clicking (or `Enter`/`Space`) in the filter zone (a `tag`
  command is a future addition).
- **Available tags** = distinct tags of entries passing `app_match AND level_match`, minus
  `tags`. Counts are entries passing those two filters.
- Selected tags remain shown in "Active filters" even if they currently have zero matching entries
  (shown dimmed with count 0), so users can always unselect them.

## Apps / PIDs

- `AppKey` is either `Package(name)` or `Pid(n)`.
- Package → PIDs map comes from the source (see [05](05-log-sources-and-parsing.md)); a package may
  have several PIDs over time (restarts) — all of them match.
- Live mode: new PIDs for a selected package (app restarted) are added automatically when the map
  refreshes.

## Recomputation strategy

Implemented in `alogs/model/filters.py`:

- Filters change rarely; entries arrive often (live). `FilterEngine` keeps:
  - `visible: list[LogEntry]` — references to visible entries (what the log view shows/exports).
  - `tag_counts: dict[str, int]` — counts for the available-tags panel.
- `FilterState.snapshot()` gives an immutable `FilterSnapshot` that is safe to use from a thread.
- On **filter change**: full rescan with `compute(entries, snapshot)`. Up to 100 000 entries it
  runs synchronously; above that in a worker thread (status bar shows "filtering…"). Entries
  that arrive while the worker runs are added on completion; a newer filter change or a newly
  opened file discards the stale result.
- On **new entries**: `FilterEngine.add(batch)` evaluates predicates once and appends.
- The log view keeps its position: the first visible entry at or after the old top entry
  (by source position `LogEntry.seq`) becomes the new top; if the view was at the bottom it stays
  there.
- Filters (levels, tags) are kept when another file is opened.
