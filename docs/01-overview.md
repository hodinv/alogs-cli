# 01 — Overview

## Problem

Android logs are huge, noisy and come in several slightly different text formats depending on the
device, Android version, `logcat -v` options and the tool that saved them (Android Studio,
bugreport, …). Android Studio's Logcat window is good but requires the IDE; `adb logcat | grep`
is too primitive. We want a fast, keyboard-and-mouse friendly **console** tool that works the same
on every desktop OS.

## Goals

- Open a saved log file **or** stream live from `adb logcat`.
- Understand many log formats automatically (see [09](09-log-formats-and-parsers.md)).
- Filter by **app / package / PID**, **log level** and **tag**; see the active filters at a glance.
- Click tags on/off in a side panel; everything else is driven by short commands.
- Export the currently filtered lines to a file.
- Handle large logs (≥ 1 000 000 lines) smoothly.
- Install with one command on Windows, macOS and Linux.
- Extensible command system — new commands are added without touching the UI code.

## Non-goals (for the first versions)

- GUI / web UI.
- Editing logs.
- Device management beyond running `adb logcat` / `adb shell ps`.
- Merging several files by time (possible future feature).

## Target users

Android developers and QA engineers analysing logs from their own or customers' devices.

## Platforms

Windows 10+ (Windows Terminal recommended), macOS, Linux. Any terminal with 256 colours and
mouse reporting. Minimum useful size: 100×30.

## Glossary

| Term | Meaning |
|---|---|
| **Entry** | One parsed log record (may span several text lines, e.g. stack traces, `-v long`). |
| **PID** | Process ID that emitted the entry. |
| **TID** | Thread ID within the process. |
| **UID** | Linux user id of the app (`u0_a123` or numeric), present with `-v uid`. |
| **Package** | Android application id, e.g. `com.example.app`; mapped to one or more PIDs. |
| **Level / priority** | `V` Verbose, `D` Debug, `I` Info, `W` Warn, `E` Error, `F` Fatal, `A`/`S` Assert/Silent. |
| **Tag** | Short component name given by the caller of `Log.x(tag, msg)`. |
| **Source** | Where entries come from: a file or a live adb stream. |
| **Parser / format** | Code that converts raw text lines into entries for one log layout. |
| **Filter state** | Current selection of apps/PIDs, levels and tags. |
