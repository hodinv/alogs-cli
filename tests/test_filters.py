from __future__ import annotations

import pytest

from alogs.model.entry import Level, LogEntry
from alogs.model.filters import ALL_LEVELS, FilterEngine, FilterState, compute
from alogs.model.store import LogStore

D, I, W, E = Level.DEBUG, Level.INFO, Level.WARN, Level.ERROR


def entry(level=None, tag=None, pid=None, sep=False) -> LogEntry:
    return LogEntry(raw="x", message="x", format_id="t", level=level, tag=tag, pid=pid, is_separator=sep)


# -- level state machine (docs/04, "Levels") --------------------------------------


def test_untouched_plus_selects_only_that_level():
    s = FilterState()
    s.change_level(E, True)
    assert s.levels == {E} and s.levels_touched


def test_untouched_minus_removes_only_that_level():
    s = FilterState()
    s.change_level(D, False)
    assert s.levels == set(ALL_LEVELS) - {D}


def test_touched_adds_and_removes():
    s = FilterState()
    s.change_level(E, True)
    s.change_level(W, True)
    assert s.levels == {W, E}
    s.change_level(E, False)
    assert s.levels == {W}
    s.change_level(W, False)
    assert s.levels == set() and s.levels_text() == "none"


def test_reset_levels():
    s = FilterState()
    s.change_level(E, True)
    s.reset_levels()
    assert s.levels == set(ALL_LEVELS) and not s.levels_touched
    assert s.levels_text() == "all"


def test_levels_text_order():
    s = FilterState()
    s.change_level(E, True)
    s.change_level(D, True)
    assert s.levels_text() == "D E"


def test_toggle_tag():
    s = FilterState()
    assert s.toggle_tag("A") is True
    assert s.toggle_tag("A") is False
    assert s.tags == set()


# -- compute ----------------------------------------------------------------------

ENTRIES = [
    entry(D, "A", 1),
    entry(I, "B", 1),
    entry(W, "A", 2),
    entry(E, "C", 2),
    entry(None, None, None),  # raw line: no level, no tag
    entry(sep=True),
]


def test_no_filters_shows_everything():
    visible, counts = compute(ENTRIES, FilterState().snapshot())
    assert visible == ENTRIES
    assert counts == {"A": 2, "B": 1, "C": 1}


def test_level_filter_and_tag_counts_follow_levels():
    s = FilterState()
    s.change_level(W, True)
    s.change_level(E, True)
    visible, counts = compute(ENTRIES, s.snapshot())
    assert visible == [ENTRIES[2], ENTRIES[3], ENTRIES[4], ENTRIES[5]]  # levelless + separator stay
    assert counts == {"A": 1, "C": 1}


def test_tag_filter_does_not_change_available_counts():
    s = FilterState()
    s.toggle_tag("A")
    visible, counts = compute(ENTRIES, s.snapshot())
    assert visible == [ENTRIES[0], ENTRIES[2], ENTRIES[5]]  # tagless entries hidden, separator kept
    assert counts == {"A": 2, "B": 1, "C": 1}


def test_pid_filter_restricts_tags():
    s = FilterState(pids={2})
    visible, counts = compute(ENTRIES, s.snapshot())
    assert visible == [ENTRIES[2], ENTRIES[3], ENTRIES[5]]
    assert counts == {"A": 1, "C": 1}


def test_no_levels_enabled_hides_all_leveled_entries():
    s = FilterState()
    s.change_level(E, True)
    s.change_level(E, False)
    visible, counts = compute(ENTRIES, s.snapshot())
    assert visible == [ENTRIES[4], ENTRIES[5]]
    assert counts == {}


# -- engine -----------------------------------------------------------------------


@pytest.mark.parametrize("split", [0, 1, 3, 6])
def test_incremental_add_equals_full_compute(split):
    s = FilterState()
    s.change_level(D, False)
    snap = s.snapshot()
    engine = FilterEngine()
    engine.reset(snap)
    engine.add(ENTRIES[:split])
    engine.add(ENTRIES[split:])
    assert (engine.visible, engine.tag_counts) == compute(ENTRIES, snap)


def test_store_assigns_sequence_numbers():
    store = LogStore()
    a, b, c = entry(), entry(), entry()
    store.add([a, b])
    store.add([c])
    assert [a.seq, b.seq, c.seq] == [0, 1, 2]


def test_app_filter_without_known_pids_shows_nothing():
    s = FilterState(packages={"com.x"})
    visible, counts = compute(ENTRIES, s.snapshot())
    assert visible == [ENTRIES[5]]  # only the separator
    assert counts == {}
    visible, _ = compute(ENTRIES, s.snapshot(package_pids=[1]))
    assert visible == [ENTRIES[0], ENTRIES[1], ENTRIES[5]]


def test_store_trim_and_engine_remove_oldest():
    store = LogStore()
    entries = [entry(D if i % 2 else E, f"T{i % 3}", 1) for i in range(21)]
    store.add(entries)
    s = FilterState()
    s.change_level(E, True)
    engine = FilterEngine()
    engine.reset(s.snapshot())
    engine.add(store.entries)
    assert store.trim(20) == []  # within the 10% slack (22)
    store.add([entry(E, "T0", 1) for _ in range(5)])
    dropped = store.trim(20)
    assert len(dropped) == 6 and store.dropped == 6
    assert [x.seq for x in store.entries] == list(range(6, 26))
    engine.add(store.entries[-5:])
    engine.remove_oldest(dropped)
    expected_visible, expected_counts = compute(store.entries, s.snapshot())
    assert engine.visible == expected_visible
    assert engine.tag_counts == expected_counts
