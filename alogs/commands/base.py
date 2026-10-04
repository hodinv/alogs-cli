"""Command registry (docs/03, "Adding a command")."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..model.filters import FilterState
    from ..parsing.detect import Detection
    from ..parsing.registry import ParserRegistry
    from ..sources.resolver import AppInfo


class CommandError(Exception):
    """User-facing error; shown in the command output in red."""


class CommandContext(Protocol):
    """What commands may use. Implemented by the app (and by fakes in tests)."""

    commands: CommandRegistry
    parsers: ParserRegistry
    filters: FilterState

    def write(self, text: str) -> None: ...
    def filters_changed(self) -> None: ...
    def open_file(self, path: str, force: bool = False) -> None: ...
    def open_adb(self, serial: str | None = None, save: bool = True) -> None: ...
    def search(self, text: str, in_messages: bool = False, by_app: bool = False) -> None: ...
    def apps(self) -> list[AppInfo]: ...
    def select_apps(self, packages: set[str], pids: set[int]) -> None: ...
    def show_app_dialog(self) -> None: ...
    def app_filter_text(self) -> str: ...
    def export(self, path: str, overwrite: bool = False) -> int: ...
    def current_format(self) -> Detection | None: ...
    def set_format(self, parser_id: str | None) -> None: ...
    def exit(self) -> None: ...


Handler = Callable[[CommandContext, list[str]], None]


@dataclass(frozen=True)
class Command:
    name: str
    summary: str
    usage: str
    help: str
    handler: Handler
    aliases: tuple[str, ...] = field(default=())


def split_args(line: str) -> list[str]:
    """Split like a shell, but keep backslashes (Windows paths)."""
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    try:
        return list(lexer)
    except ValueError as e:
        raise CommandError(f"Cannot parse command: {e}") from e


def take_flag(args: list[str], *flags: str) -> tuple[bool, list[str]]:
    """Remove flags like `-f` from args; return (present, remaining)."""
    rest = [a for a in args if a not in flags]
    return len(rest) != len(args), rest


class CommandRegistry:
    def __init__(self, commands: Sequence[Command] = ()) -> None:
        self._commands: dict[str, Command] = {}
        self._lookup: dict[str, Command] = {}
        for command in commands:
            self.register(command)

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        for key in (command.name, *command.aliases):
            self._lookup[key.lower()] = command

    def get(self, name: str) -> Command | None:
        return self._lookup.get(name.lower())

    def all(self) -> list[Command]:
        return sorted(self._commands.values(), key=lambda c: c.name)

    def names(self) -> list[str]:
        return sorted(self._lookup)

    def dispatch(self, ctx: CommandContext, line: str) -> None:
        args = split_args(line)
        if not args:
            return
        command = self.get(args[0])
        if command is None:
            raise CommandError(f"Unknown command '{args[0]}'. Type 'help' for the list.")
        command.handler(ctx, args[1:])
