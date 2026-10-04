# 07 — Tech stack decision (ADR)

**Status:** accepted · **Decision:** Python + [Textual](https://textual.textualize.io/)

## Requirements that drive the choice

1. Runs on Windows, macOS and Linux.
2. Easy to install for developers and QA.
3. Mouse-clickable items (tag toggling) and scrollable panes.
4. Percentage-based multi-zone layout.
5. Smooth scrolling through 1M+ lines (virtualization).
6. Subprocess streaming (`adb logcat`).

## Options compared

| | Node.js | Python | Kotlin / JVM |
|---|---|---|---|
| TUI libraries | Ink (React-style, active); blessed / neo-blessed (full widgets, largely unmaintained) | **Textual** (modern, very active, richest widget set) | Lanterna (basic widgets); Mosaic (Compose-style, young) |
| Mouse clicks | Ink: no native mouse support; blessed: yes | Built-in on every widget | Lanterna: limited; Mosaic: no |
| Large log scrolling | Ink re-renders the tree — needs custom virtualization; blessed OK | Built-in virtual line API / `Log`, `DataTable` | Must be hand-built |
| Layout (70/30, 40/60) | Ink flexbox good; blessed percentages | CSS-like layout, trivial | Manual |
| Checkbox list (`app`) | Community packages | Built-in `SelectionList` | Manual |
| Subprocess streaming | Excellent | Good (asyncio) | Good |
| Install | `npm i -g` / `npx` (needs Node); single binary via Bun `--compile` or Node SEA | `uv tool install` / `pipx` (uv fetches Python itself); single binary via PyInstaller per OS | Needs JRE, or GraalVM native-image per OS (complex) |
| Windows terminal | Fine in Windows Terminal | Fine in Windows Terminal | Lanterna may fall back to a Swing window |
| Cross-platform effort | Low | Low | Medium–high |

## Decision

Python + Textual: it provides out of the box the exact widgets this UI needs (clickable lists,
modal selection lists, scroll views with virtualization, CSS layout), it has a first-class testing
harness (`Pilot`), and distribution is a one-liner on all platforms with an optional no-Python
binary.

## Consequences

- Raw parsing speed of pure Python is lower than Node/Go/Rust; mitigated by compiled regexes,
  batching, worker threads and an optional native parser later ([06](06-architecture.md#performance)).
- Requires Python ≥ 3.10 when installed as a package (uv handles this automatically); the
  PyInstaller binary (~15 MB on Windows) needs no Python at all.
