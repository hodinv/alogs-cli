"""Modal checkbox list for the `app` command (docs/03, `app`)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..sources.resolver import AppInfo

AppSelection = tuple[set[str], set[int]]  # (packages, pids)


def _row_text(app: AppInfo) -> Text:
    text = Text(app.name if app.name is not None else f"pid {app.pids[0]}")
    if app.name is not None:
        pids = ", ".join(map(str, app.pids)) if app.pids else "no PIDs seen"
        text.append(f"  ({pids})", style="dim")
    text.append(f"  {app.entries:,} entries", style="dim")
    return text


class AppSelectScreen(ModalScreen[AppSelection | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "apply", "Apply"),
    ]

    DEFAULT_CSS = """
    AppSelectScreen {
        align: center middle;
    }
    #app-dialog {
        width: 80%;
        height: 80%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    #app-hint {
        height: auto;
        color: $text-muted;
    }
    #app-search {
        margin: 1 0;
    }
    #app-list {
        height: 1fr;
    }
    #app-buttons {
        height: auto;
        align-horizontal: right;
    }
    #app-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, apps: list[AppInfo], packages: set[str], pids: set[int]) -> None:
        super().__init__()
        known = {a.name for a in apps if a.name is not None}
        # selected apps without entries stay listed so they can be unselected
        extra = [AppInfo(name, (), 0) for name in sorted(packages - known)]
        self._apps = apps + extra
        self._selected: set[str] = {f"pkg:{p}" for p in packages} | {f"pid:{p}" for p in pids}

    def compose(self) -> ComposeResult:
        with Vertical(id="app-dialog") as dialog:
            dialog.border_title = "Apps / processes"
            yield Static(
                "Space/Enter/click toggles · Ctrl+S applies · Esc cancels · nothing selected = all apps",
                id="app-hint",
            )
            yield Input(placeholder="search", id="app-search")
            yield SelectionList[str](id="app-list")
            with Horizontal(id="app-buttons"):
                yield Button("Apply", id="apply", variant="primary")
                yield Button("Clear", id="clear")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._render_list()
        self.query_one("#app-list", SelectionList).focus()

    def _render_list(self) -> None:
        needle = self.query_one("#app-search", Input).value.strip().lower()
        rows = [
            a for a in self._apps
            if not needle or needle in (a.name or "").lower() or any(needle in str(p) for p in a.pids)
        ]
        selection_list = self.query_one("#app-list", SelectionList)
        selection_list.clear_options()
        selection_list.add_options(Selection(_row_text(a), a.key, a.key in self._selected) for a in rows)
        if rows:
            selection_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._render_list()

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        event.stop()
        selection_list = event.selection_list
        shown = {selection_list.get_option_at_index(i).value for i in range(selection_list.option_count)}
        self._selected = (self._selected - shown) | set(selection_list.selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "apply":
            self.action_apply()
        elif event.button.id == "clear":
            self._selected.clear()
            self.query_one("#app-list", SelectionList).deselect_all()
        else:
            self.action_cancel()

    def action_apply(self) -> None:
        packages = {k[4:] for k in self._selected if k.startswith("pkg:")}
        pids = {int(k[4:]) for k in self._selected if k.startswith("pid:")}
        self.dismiss((packages, pids))

    def action_cancel(self) -> None:
        self.dismiss(None)
