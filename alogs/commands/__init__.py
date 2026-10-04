from .base import Command, CommandContext, CommandError, CommandRegistry
from .builtin import COMMANDS


def default_commands() -> CommandRegistry:
    return CommandRegistry(COMMANDS)


__all__ = ["Command", "CommandContext", "CommandError", "CommandRegistry", "default_commands"]
