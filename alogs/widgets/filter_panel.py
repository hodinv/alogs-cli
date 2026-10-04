"""Filter zone (docs/02-ui-layout.md, "Filter zone").

Top: active filters (app, levels — display only — and selected tags).
Bottom: tags available under the other filters. Clicking a tag in either
list toggles it; the app owns the state and calls `update_view`.
"""

from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from ..model.filters import ALL_LEVELS, FilterState
from .log_view import LEVEL_STYLES

EMPTY_TAG_LABEL = "(empty tag)"


def _tag_label(tag: str, count: int) -> Text:
    text = Text(tag if tag else EMPTY_TAG_LABEL, style="" if tag else "italic")
    text.append(f"  {count:,}", style="dim")
    return text


def _option_id(tag: str) -> str:
    return "t:" + tag


def _tag_of(option_id: str | None) -> str | None:
    return option_id[2:] if option_id and option_id.startswith("t:") else None


class TagList(OptionList):
    """OptionList that keeps highlight and scroll position across updates."""

    _last_highlight: int | None = None

    def replace_tags(self, items: list[tuple[str, int]]) -> None:
        current = self.highlighted_option
        current_id = current.id if current else None
        scroll_y = self.scroll_y
        self.set_options(Option(_tag_label(tag, n), id=_option_id(tag)) for tag, n in items)
        if not items:
            return
        index = None
        if current_id is not None:
            try:
                index = self.get_option_index(current_id)
            except Exception:  # option disappeared (e.g. moved to the other list)
                index = None
        if index is None and self.has_focus and self._last_highlight is not None:
            index = min(self._last_highlight, len(items) - 1)
        if index is not None:
            self.highlighted = index
        self.scroll_to(None, scroll_y, animate=False, immediate=True)

    def watch_highlighted(self, highlighted: int | None) -> None:
        super().watch_highlighted(highlighted)
        if highlighted is not None:
            self._last_highlight = highlighted


class FilterPanel(Vertical):
    class TagToggled(Message):
        def __init__(self, tag: str) -> None:
            super().__init__()
            self.tag = tag

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._available: list[tuple[str, int]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="active-filters") as active:
            active.border_title = "Active filters"
            yield Static(id="active-summary")
            yield TagList(id="selected-tags")
        with Vertical(id="available-tags") as available:
            available.border_title = "Available tags"
            yield Input(placeholder="search tags", id="tag-search")
            yield TagList(id="tag-list")
            yield Static(id="tags-hint")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        tag = _tag_of(event.option.id)
        if tag is not None:
            self.post_message(self.TagToggled(tag))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tag-search":
            event.stop()
            self._render_available()

    def update_view(self, state: FilterState, counts: dict[str, int], app_text: str, has_log: bool) -> None:
        summary = Text()
        summary.append("App: ", style="bold")
        summary.append(app_text + "\n")
        summary.append("Levels: ", style="bold")
        if not state.levels_touched:
            summary.append("all")
        else:
            for level in ALL_LEVELS:
                on = level in state.levels
                style = LEVEL_STYLES[level] + Style.parse("bold" if on else "dim strike")
                summary.append(level.letter, style=style)
                summary.append(" ")
            if not state.levels:
                summary.append(" (none — nothing shown)", style="italic")
        summary.append("\nTags: ", style="bold")
        summary.append("all" if not state.tags else f"{len(state.tags)} selected (click to remove)")
        self.query_one("#active-summary", Static).update(summary)

        selected = sorted(state.tags, key=str.lower)
        self.query_one("#selected-tags", TagList).replace_tags([(t, counts.get(t, 0)) for t in selected])

        self._available = sorted(
            ((t, n) for t, n in counts.items() if t not in state.tags),
            key=lambda item: (-item[1], item[0].lower()),
        )
        hint = ""
        if not has_log:
            hint = "no log loaded"
        elif not counts and not state.tags:
            hint = "no tags — the log format has none, or nothing matches the filters"
        self.query_one("#tags-hint", Static).update(Text(hint, style="dim italic"))
        self._render_available()

    def _render_available(self) -> None:
        needle = self.query_one("#tag-search", Input).value.strip().lower()
        items = self._available
        if needle:
            items = [(t, n) for t, n in items if needle in t.lower()]
        self.query_one("#tag-list", TagList).replace_tags(items)

