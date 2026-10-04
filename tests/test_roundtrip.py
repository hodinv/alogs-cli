"""Property-style test: render random entries in every logcat layout the way
logcat's logprint.c does, parse them back, compare fields (docs/09, section 5)."""

from __future__ import annotations

import random

import pytest

from alogs.model.entry import Level

from .conftest import parse_text

LETTERS = "VDIWEFA"
TAG_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
MSG_CHARS = TAG_CHARS + " :/()[]{}=,#@!?\"'"


def rand_ts(rng: random.Random) -> str:
    frac = rng.choice([3, 6, 9])
    f = "".join(rng.choice("0123456789") for _ in range(frac))
    kind = rng.choice(["mmdd", "ymd", "epoch", "mono"])
    if kind == "mmdd":
        ts = f"{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}.{f}"
    elif kind == "ymd":
        ts = f"20{rng.randint(10, 30)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}.{f}"
    elif kind == "epoch":
        ts = f"{rng.randint(1_000_000_000, 1_999_999_999)}.{f}"
    else:
        ts = f"{rng.randint(0, 99999):>6}.{f}"
    if kind in ("mmdd", "ymd") and rng.random() < 0.2:
        ts += f" {rng.choice('+-')}{rng.randint(0, 12):02d}00"
    return ts


def rand_record(rng: random.Random) -> dict:
    msg = "".join(rng.choice(MSG_CHARS) for _ in range(rng.randint(1, 60))).strip() or "x"
    return dict(
        ts=rand_ts(rng),
        lvl=rng.choice(LETTERS),
        tag="".join(rng.choice(TAG_CHARS) for _ in range(rng.randint(1, 23))),
        pid=rng.randint(1, 99999),
        tid=rng.randint(1, 99999),
        msg=msg,
    )


RENDER = {
    "brief": lambda r: f"{r['lvl']}/{r['tag']:<8}({r['pid']:5}): {r['msg']}",
    "process": lambda r: f"{r['lvl']}({r['pid']:5}) {r['msg']}  ({r['tag']})",
    "tag": lambda r: f"{r['lvl']}/{r['tag']:<8}: {r['msg']}",
    "thread": lambda r: f"{r['lvl']}({r['pid']:5}:{r['tid']:5}) {r['msg']}",
    "time": lambda r: f"{r['ts']} {r['lvl']}/{r['tag']:<8}({r['pid']:5}): {r['msg']}",
    "threadtime": lambda r: f"{r['ts']} {r['pid']:5} {r['tid']:5} {r['lvl']} {r['tag']:<8}: {r['msg']}",
    "long": lambda r: f"[ {r['ts']} {r['pid']:5}:{r['tid']:5} {r['lvl']}/{r['tag']:<8} ]\n{r['msg']}\n",
}
FIELDS = {
    "brief": ("lvl", "tag", "pid", "msg"),
    "process": ("lvl", "tag", "pid", "msg"),
    "tag": ("lvl", "tag", "msg"),
    "thread": ("lvl", "pid", "tid", "msg"),
    "time": ("ts", "lvl", "tag", "pid", "msg"),
    "threadtime": ("ts", "lvl", "tag", "pid", "tid", "msg"),
    "long": ("ts", "lvl", "tag", "pid", "tid", "msg"),
}


def actual(entry, field):
    return {
        "ts": entry.time_text,
        "lvl": entry.level,
        "tag": entry.tag,
        "pid": entry.pid,
        "tid": entry.tid,
        "msg": entry.message,
    }[field]


def expected(record, field):
    if field == "lvl":
        return Level.from_letter(record["lvl"])
    if field == "ts":
        return record["ts"].strip()
    return record[field]


@pytest.mark.parametrize("fmt", sorted(RENDER))
@pytest.mark.parametrize("auto", [False, True], ids=["forced", "auto"])
def test_roundtrip(registry, fmt, auto):
    rng = random.Random(f"{fmt}-42")
    records = [rand_record(rng) for _ in range(300)]
    text = "\n".join(RENDER[fmt](r) for r in records)
    entries, detection = parse_text(registry, text, None if auto else fmt)
    assert detection.parser_id == fmt
    assert len(entries) == len(records)
    for record, entry in zip(records, entries):
        for field in FIELDS[fmt]:
            assert actual(entry, field) == expected(record, field), (field, entry.raw)
