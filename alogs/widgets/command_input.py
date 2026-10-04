"""Command input with persistent history (docs/02, "Command zone")."""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.suggester import SuggestFromList
from textual.widgets import Input

HISTORY_LIMIT = 500


class CommandInput(Input):
    BINDINGS = [
        Binding("up", "history(-1)", "Previous command", show=False),
        Binding("down", "history(1)", "Next command", show=False),
    ]

    def __init__(self, command_names: list[str], history_path: Path | None = None, **kwargs) -> None:
        super().__init__(
            placeholder="type a command — 'help' for the list",
            suggester=SuggestFromList(command_names, case_sensitive=False),
            **kwargs,
        )
        self._history_path = history_path
        self.history: list[str] = self._load_history()
        self._history_pos = len(self.history)  # == len(history): editing a new line
        self._draft = ""

    def _load_history(self) -> list[str]:
        if self._history_path is None:
            return []
        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        return [line for line in lines if line.strip()][-HISTORY_LIMIT:]

    def remember(self, line: str) -> None:
        if line and (not self.history or self.history[-1] != line):
            self.history.append(line)
            del self.history[:-HISTORY_LIMIT]
            self._save_history()
        self._history_pos = len(self.history)
        self._draft = ""

    def _save_history(self) -> None:
        if self._history_path is None:
            return
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text("\n".join(self.history) + "\n", encoding="utf-8")
        except OSError:
            pass  # history is a convenience; never fail a command because of it

    def action_history(self, step: int) -> None:
        if not self.history:
            return
        if self._history_pos == len(self.history):
            self._draft = self.value
        self._history_pos = max(0, min(len(self.history), self._history_pos + step))
        at_draft = self._history_pos == len(self.history)
        self.value = self._draft if at_draft else self.history[self._history_pos]
        self.cursor_position = len(self.value)
