"""Modal checkbox list used by `app` and `search` (docs/03)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..model.search import SearchHit
from ..sources.resolver import AppInfo

HINT = "Space/Enter/click toggles · Ctrl+S applies · Esc cancels"
SAMPLE_WIDTH = 100


class PickListScreen(ModalScreen[set[str] | None]):
    """Rows of (prompt, key). Dismisses with the set of selected keys
    (over all rows, also those hidden by the search box), or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "apply", "Apply"),
    ]

    DEFAULT_CSS = """
    PickListScreen {
        align: center middle;
    }
    #pick-dialog {
        width: 80%;
        height: 80%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    #pick-hint {
        height: auto;
        color: $text-muted;
    }
    #pick-search {
        margin: 1 0;
    }
    #pick-list {
        height: 1fr;
    }
    #pick-buttons {
        height: auto;
        align-horizontal: right;
    }
    #pick-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, title: str, rows: list[tuple[Text, str]], selected: set[str], hint: str = HINT) -> None:
        super().__init__()
        self._title = title
        self._hint = hint
        self._rows = rows
        self._selected = set(selected) & {key for _, key in rows}

    def compose(self) -> ComposeResult:
        with Vertical(id="pick-dialog") as dialog:
            dialog.border_title = self._title
            yield Static(self._hint, id="pick-hint")
            yield Input(placeholder="search", id="pick-search")
            yield SelectionList[str](id="pick-list")
            with Horizontal(id="pick-buttons"):
                yield Button("Apply", id="apply", variant="primary")
                yield Button("Clear", id="clear")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._render_list()
        self.query_one("#pick-list", SelectionList).focus()

    def _render_list(self) -> None:
        needle = self.query_one("#pick-search", Input).value.strip().casefold()
        rows = [(prompt, key) for prompt, key in self._rows if not needle or needle in prompt.plain.casefold()]
        selection_list = self.query_one("#pick-list", SelectionList)
        selection_list.clear_options()
        selection_list.add_options(Selection(prompt, key, key in self._selected) for prompt, key in rows)
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
            self.query_one("#pick-list", SelectionList).deselect_all()
        else:
            self.action_cancel()

    def action_apply(self) -> None:
        self.dismiss(set(self._selected))

    def action_cancel(self) -> None:
        self.dismiss(None)


# -- row builders ------------------------------------------------------------------


def _short(text: str, width: int = SAMPLE_WIDTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def app_rows(apps: list[AppInfo], selected_packages: set[str]) -> list[tuple[Text, str]]:
    known = {a.name for a in apps if a.name is not None}
    # selected apps without entries stay listed so they can be unselected
    apps = apps + [AppInfo(name, (), 0) for name in sorted(selected_packages - known)]
    rows = []
    for app in apps:
        text = Text(app.name if app.name is not None else f"pid {app.pids[0]}")
        if app.name is not None:
            pids = ", ".join(map(str, app.pids)) if app.pids else "no PIDs seen"
            text.append(f"  ({pids})", style="dim")
        text.append(f"  {app.entries:,} entries", style="dim")
        rows.append((text, app.key))
    return rows


def search_rows(hits: list[SearchHit], names: dict[int, str]) -> list[tuple[Text, str]]:
    rows = []
    for hit in hits:
        if hit.pid is not None:
            text = Text(f"pid {hit.pid}")
            name = names.get(hit.pid)
            if name:
                text.append(f"  {name}", style="bold")
            if hit.sample is not None:
                text.append(f"  {hit.tag or ''}: {_short(hit.sample)}")
            elif hit.tags:
                text.append(f"  tags: {', '.join(hit.tags)}")
        else:
            text = Text(hit.tag or "", style="bold")
            if hit.sample is not None:
                text.append(f": {_short(hit.sample)}")
        text.append(f"  ({hit.count:,})", style="dim")
        rows.append((text, hit.key))
    return rows
