"""Built-in commands: help, open, openadb, export, format, levels, app, exit."""

from __future__ import annotations

from ..model.entry import Level
from .base import Command, CommandContext, CommandError, take_flag


def _help(ctx: CommandContext, args: list[str]) -> None:
    if not args:
        width = max(len(c.name) for c in ctx.commands.all())
        lines = ["Commands:"]
        for c in ctx.commands.all():
            lines.append(f"  {c.name.ljust(width)}  {c.summary}")
        lines.append("Type 'help <command>' for details.")
        ctx.write("\n".join(lines))
        return
    command = ctx.commands.get(args[0])
    if command is None:
        raise CommandError(f"No such command '{args[0]}'.")
    text = f"{command.usage}\n\n{command.help}"
    if command.aliases:
        text += f"\n\nAliases: {', '.join(command.aliases)}"
    ctx.write(text)


def _open(ctx: CommandContext, args: list[str]) -> None:
    force, args = take_flag(args, "-f", "--force")
    if len(args) != 1:
        raise CommandError("Usage: open [-f] <filename>")
    ctx.open_file(args[0], force=force)


def _export(ctx: CommandContext, args: list[str]) -> None:
    force, args = take_flag(args, "-f", "--force")
    if len(args) != 1:
        raise CommandError("Usage: export [-f] <filename>")
    try:
        count = ctx.export(args[0], overwrite=force)
    except FileExistsError:
        raise CommandError(
            f"{args[0]} already exists; use 'export -f {args[0]}' to overwrite"
        ) from None
    except OSError as e:
        raise CommandError(f"Cannot write {args[0]}: {e.strerror or e}") from None
    ctx.write(f"Exported {count} entries to {args[0]}")


def _format(ctx: CommandContext, args: list[str]) -> None:
    if not args:
        detection = ctx.current_format()
        ctx.write(f"Format: {detection.describe()}" if detection else "Format: (no log loaded)")
        return
    if len(args) != 1:
        raise CommandError("Usage: format [list | auto | <id>]")
    arg = args[0]
    if arg.lower() == "list":
        parsers = ctx.parsers.all()
        width = max(len(p.id) for p in parsers)
        lines = ["Formats:"]
        for p in parsers:
            lines.append(f"  {p.id.ljust(width)}  {p.description}")
            if p.sample:
                lines.append(f"  {''.ljust(width)}    {p.sample}")
        ctx.write("\n".join(lines))
    elif arg.lower() == "auto":
        ctx.set_format(None)
    else:
        if ctx.parsers.get(arg) is None:
            raise CommandError(f"Unknown format '{arg}'. Type 'format list' for the list.")
        ctx.set_format(arg)


def _levels(ctx: CommandContext, args: list[str]) -> None:
    state = ctx.filters
    if not args:
        ctx.write(f"Levels: {state.levels_text()}")
        return
    # "+W,+E" works like "+W +E" (handy on the alogs command line)
    args = [part for arg in args for part in arg.split(",") if part]
    if len(args) == 1 and args[0].lower() in ("all", "*"):
        state.reset_levels()
    elif len(args) == 1 and args[0].lower() == "none":
        state.levels_touched = True
        state.levels = set()
    else:
        changes = []
        for arg in args:
            sign, name = (arg[0], arg[1:]) if arg[:1] in "+-" else ("+", arg)
            level = Level.from_name(name) if name else None
            if level is None:
                raise CommandError(f"Unknown level '{arg}'. Use V/D/I/W/E/F/A or full names.")
            changes.append((level, sign == "+"))
        # validate everything first so a typo doesn't apply half the arguments
        for level, enable in changes:
            state.change_level(level, enable)
    ctx.filters_changed()
    ctx.write(f"Levels: {state.levels_text()}")


def _openadb(ctx: CommandContext, args: list[str]) -> None:
    no_save, args = take_flag(args, "--no-save", "-n")
    serial = None
    if args[:1] == ["-s"] and len(args) == 2:
        serial = args[1]
    elif args:
        raise CommandError("Usage: openadb [-s <serial>] [--no-save]")
    ctx.open_adb(serial, save=not no_save)


def _selection_args(args: list[str], current: set[str]) -> set[str]:
    """`+X -Y` modify `current`; bare values replace it."""
    result = set(current) if any(a[:1] in "+-" for a in args) else set()
    for arg in args:
        sign, value = (arg[0], arg[1:]) if arg[:1] in "+-" else ("+", arg)
        if not value:
            raise CommandError("missing name after + / -")
        if sign == "+":
            result.add(value)
        else:
            result.discard(value)
    return result


def _tag(ctx: CommandContext, args: list[str]) -> None:
    state = ctx.filters
    if args:
        if len(args) == 1 and args[0].lower() in ("all", "*"):
            state.tags = set()
        else:
            state.tags = _selection_args(args, state.tags)
        ctx.filters_changed()
    shown = ", ".join(sorted(state.tags, key=str.lower)) or "all"
    ctx.write(f"Tags: {shown}")


def _search(ctx: CommandContext, args: list[str]) -> None:
    by_app = in_messages = False
    words = []
    for arg in args:
        if arg.lower() in ("-app", "--app", "-a"):
            by_app = True
        elif arg.lower() in ("-m", "--message", "--messages"):
            in_messages = True
        else:
            words.append(arg)
    text = " ".join(words)
    if not text:
        raise CommandError("Usage: search [-app] [-m] <text>")
    ctx.search(text, in_messages=in_messages, by_app=by_app)


def _app(ctx: CommandContext, args: list[str]) -> None:
    if not args:
        ctx.show_app_dialog()
        return
    if len(args) == 1 and args[0].lower() == "list":
        apps = ctx.apps()
        if not apps:
            ctx.write("No apps/processes in the current log.")
            return
        lines = []
        for a in apps:
            name = a.name if a.name is not None else f"pid {a.pids[0]}"
            pids = f"  ({', '.join(map(str, a.pids))})" if a.name is not None else ""
            lines.append(f"  {name}{pids}  {a.entries:,} entries")
        ctx.write("\n".join(["Apps:", *lines]))
        return
    packages: set[str] = set()
    pids: set[int] = set()
    if not (len(args) == 1 and args[0].lower() in ("all", "*")):
        state = ctx.filters
        current = state.packages | {str(p) for p in state.pids}
        try:
            chosen = _selection_args(args, current)
        except CommandError:
            raise CommandError("Usage: app [list | all | [+|-]<package|pid> ...]") from None
        pids = {int(v) for v in chosen if v.isdigit()}
        packages = {v for v in chosen if not v.isdigit()}
    ctx.select_apps(packages, pids)
    ctx.write(f"App: {ctx.app_filter_text()}")


def _exit(ctx: CommandContext, args: list[str]) -> None:
    ctx.exit()


COMMANDS = [
    Command(
        "help",
        "List commands or show help for one command",
        "help\nhelp <command>",
        "Without argument: list all commands.\nWith argument: syntax, description and examples.",
        _help,
    ),
    Command(
        "open",
        "Open a log file",
        "open [-f] <filename>",
        "Open a log file as the current source (replaces the current one).\n"
        "The log format is detected automatically; see 'format'.\n"
        "Use quotes for paths with spaces. -f opens files that look binary.\n\n"
        "Examples:\n  open crash.log\n  open \"C:\\logs\\my log.txt\"",
        _open,
    ),
    Command(
        "openadb",
        "Read the live log from a device via adb logcat",
        "openadb [-s <serial>] [--no-save]",
        "Start reading live from the connected device (adb logcat). Filters are kept.\n"
        "With several devices connected, pick one with -s (see 'adb devices').\n"
        "The view follows new lines while scrolled to the bottom; scroll up to\n"
        "pause, press End to follow again.\n\n"
        "Everything received is also saved to adblog-YYYY-MM-DD-HHMMSS.log in the\n"
        "current folder (unfiltered, as received); --no-save turns that off.\n\n"
        "adb is looked up on PATH, then via sdk.dir in local.properties (current\n"
        "folder or a parent, as written by Android Studio), then ANDROID_HOME /\n"
        "ANDROID_SDK_ROOT, then the default SDK folder.",
        _openadb,
    ),
    Command(
        "export",
        "Export currently shown entries to a file",
        "export [-f] <filename>",
        "Write the currently shown entries (with their continuation lines) as\n"
        "their original text, UTF-8. -f overwrites an existing file.\n\n"
        "Example:\n  export only-errors.log",
        _export,
    ),
    Command(
        "format",
        "Show, list or force the log format parser",
        "format\nformat list\nformat auto\nformat <id>",
        "format        show the current format and how it was chosen\n"
        "format list   list all available parsers with a sample line\n"
        "format <id>   force a parser and re-read the current file\n"
        "format auto   back to auto-detection",
        _format,
    ),
    Command(
        "levels",
        "Switch log levels on or off",
        "levels\nlevels [+|-]LEVEL ...\nlevels all\nlevels none",
        "Levels: V/VERBOSE D/DEBUG I/INFO W/WARN E/ERROR F/FATAL A/ASSERT\n"
        "(case-insensitive; a bare name means +).\n\n"
        "Initially all levels are on. The first change decides the mode:\n"
        "  +X  -> only X is on\n"
        "  -X  -> everything except X is on\n"
        "After that +X / -X simply add / remove X. Arguments apply left to right.\n"
        "'levels' shows the current state, 'levels all' turns everything back on,\n"
        "'levels none' turns everything off. Commas work as separators too.\n\n"
        "Examples:\n  levels +ERROR\n  levels +W +E\n  levels -DEBUG,-VERBOSE\n  levels all",
        _levels,
    ),
    Command(
        "tag",
        "Select tags to show",
        "tag\ntag all\ntag <tag> ...\ntag [+|-]<tag> ...",
        "tag                 show the selected tags\n"
        "tag all             show all tags again\n"
        "tag MyTag OkHttp    show only these tags (bare names replace the selection)\n"
        "tag +MyTag -OkHttp  add / remove tags\n\n"
        "Tags are case-sensitive; quote tags with spaces: tag +\"My Tag\".\n"
        "Clicking tags in the filter panel does the same.",
        _tag,
    ),
    Command(
        "search",
        "Find tags, messages or PIDs and add them to the filter",
        "search <text>\nsearch -m <text>\nsearch -app <text>\nsearch -app -m <text>",
        "Case-insensitive search in the whole loaded log (not only what is shown).\n\n"
        "search <text>          tags whose name contains <text>\n"
        "search -m <text>       messages containing <text>; one row per distinct tag\n"
        "                       as 'tag: first matching message'\n"
        "search -app <text>     PIDs that log a tag containing <text>\n"
        "search -app -m <text>  PIDs that log a message containing <text>\n\n"
        "Results open in a checkbox list, most matches first; ticked rows are added\n"
        "to the tag / PID filter when you apply (Ctrl+S), unticked rows removed.\n\n"
        "Examples:\n  search net\n  search -m timeout\n  search -app -m FATAL EXCEPTION",
        _search,
    ),
    Command(
        "app",
        "Select apps/processes to show",
        "app\napp list\napp all\napp [+|-]<package|pid> ...",
        "app                 open a checkbox list of apps/processes in the log\n"
        "app list            print apps with their PIDs and entry counts\n"
        "app all             show all apps again\n"
        "app com.example     show only this app (all its processes and PIDs)\n"
        "app +1234 -com.x    add / remove apps or PIDs to the selection\n\n"
        "Packages are matched to PIDs from the device process list (live),\n"
        "from 'Start proc' lines of ActivityManager, or from Android Studio\n"
        "exports. Otherwise processes are listed by PID.",
        _app,
    ),
    Command(
        "exit",
        "Exit the application",
        "exit",
        "Exit the application.",
        _exit,
        aliases=("quit", "q"),
    ),
]
