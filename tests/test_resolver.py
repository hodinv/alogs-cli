from __future__ import annotations

from alogs.model.entry import LogEntry
from alogs.sources.resolver import AppResolver, app_name

from .conftest import FORMATS, parse_text


def e(tag=None, msg="", pid=None, package=None) -> LogEntry:
    return LogEntry(raw=msg, message=msg, format_id="t", tag=tag, pid=pid, package=package)


def test_start_proc_variants():
    r = AppResolver()
    r.learn_from_entries([
        e("ActivityManager", "Start proc 4321:com.example.app/u0a123 for activity {com.example.app/.Main}"),
        e("ActivityManager", "Start proc com.old.app for activity com.old.app/.Main: pid=555 uid=10001 gids={}"),
        e("ActivityManager", "Process com.died.app (pid 777) has died: fg  TOP"),
        e("am_proc_start", "[0,888,10123,com.events.app,pre-top-activity,{com.events.app/.Main}]"),
        e("ActivityManager", "Start proc 999:com.example.app:remote/u0a123 for service"),
        e("SomethingElse", "Start proc 1:com.fake/u0a1 for activity"),
    ])
    assert r.pid_names == {
        4321: "com.example.app",
        555: "com.old.app",
        777: "com.died.app",
        888: "com.events.app",
        999: "com.example.app:remote",
    }
    assert r.pids_of(["com.example.app"]) == {4321, 999}
    assert r.name_of(999) == "com.example.app"


def test_package_field_from_studio_export(registry):
    entries, _ = parse_text(registry, (FORMATS / "studio.log").read_text(encoding="utf-8"))
    r = AppResolver()
    r.learn_from_entries(entries)
    assert r.name_of(1234) == "com.example.app"
    assert r.name_of(4321) == "com.example.app"
    assert r.name_of(567) is None  # "pid-567" means unknown


def test_ps_formats():
    r = AppResolver()
    r.update_from_ps("PID NAME\n    1 init\n    2 [kthreadd]\n 4321 com.example.app\n 4400 com.example.app:remote\n")
    r.update_from_ps(
        "USER     PID   PPID  VSIZE  RSS     WCHAN    PC         NAME\n"
        "u0_a12   555   100   1000   200   ffffffff 00000000 S com.old.app\n"
        "garbage\n"
    )
    assert r.pid_names == {1: "init", 4321: "com.example.app", 4400: "com.example.app:remote", 555: "com.old.app"}
    v = r.version
    r.update_from_ps("PID NAME\n 4321 com.example.app\n")
    assert r.version == v  # unchanged mapping does not bump the version
    r.update_from_ps("no header here\n")


def test_apps_groups_processes_and_sorts_by_entries():
    r = AppResolver()
    r.update_from_ps("PID NAME\n 10 com.a\n 11 com.a:remote\n 20 com.b\n")
    entries = [e(pid=10), e(pid=11), e(pid=11), e(pid=20), e(pid=30), e(pid=30), e(pid=30), e(pid=30), e()]
    apps = r.apps(entries)
    assert [(a.name, a.pids, a.entries) for a in apps] == [
        (None, (30,), 4),
        ("com.a", (10, 11), 3),
        ("com.b", (20,), 1),
    ]
    assert apps[0].key == "pid:30" and apps[1].key == "pkg:com.a"


def test_app_name():
    assert app_name("com.x:remote") == "com.x"
    assert app_name("system_server") == "system_server"
