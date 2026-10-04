from __future__ import annotations

from alogs.model.entry import LogEntry
from alogs.model.search import search


def e(tag, msg, pid=1, sep=False) -> LogEntry:
    return LogEntry(raw=msg, message=msg, format_id="t", tag=tag, pid=pid, is_separator=sep)


ENTRIES = [
    e("NetworkMonitor", "probe ok", 100),
    e("OkHttp", "--> GET https://example.com", 200),
    e("NetworkMonitor", "probe FAILED: timeout", 100),
    e("netd", "setting DNS", 50),
    e("OkHttp", "<-- HTTP FAILED: java.net.SocketTimeoutException: timeout", 200),
    e("OkHttp", "<-- HTTP FAILED again: timeout", 300),
    e(None, "a raw line mentioning timeout", None),
    e(None, "--------- beginning of main timeout", None, sep=True),
]


def test_tag_search_is_case_insensitive_and_distinct():
    hits = search(ENTRIES, "NET")
    assert [(h.tag, h.count, h.key) for h in hits] == [
        ("NetworkMonitor", 2, "tag:NetworkMonitor"),
        ("netd", 1, "tag:netd"),
    ]
    assert all(h.sample is None for h in hits)


def test_message_search_one_row_per_tag_with_first_sample():
    hits = search(ENTRIES, "TimeOut", in_messages=True)
    assert [(h.tag, h.count, h.sample) for h in hits] == [
        ("OkHttp", 2, "<-- HTTP FAILED: java.net.SocketTimeoutException: timeout"),
        ("NetworkMonitor", 1, "probe FAILED: timeout"),
    ]  # tagless lines and separators are skipped


def test_app_search_by_tag():
    hits = search(ENTRIES, "okhttp", by_app=True)
    assert [(h.pid, h.count, h.tags, h.key) for h in hits] == [
        (200, 2, ["OkHttp"], "pid:200"),
        (300, 1, ["OkHttp"], "pid:300"),
    ]


def test_app_search_by_message():
    hits = search(ENTRIES, "failed", in_messages=True, by_app=True)
    assert [(h.pid, h.count, h.tag, h.sample) for h in hits] == [
        (100, 1, "NetworkMonitor", "probe FAILED: timeout"),
        (200, 1, "OkHttp", "<-- HTTP FAILED: java.net.SocketTimeoutException: timeout"),
        (300, 1, "OkHttp", "<-- HTTP FAILED again: timeout"),
    ]  # ties: lower PID first


def test_limit_and_no_hits():
    many = [e(f"Tag{i}", "x", i) for i in range(50)]
    assert len(search(many, "tag", limit=10)) == 10
    assert search(ENTRIES, "nothing-like-this") == []
