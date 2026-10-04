from __future__ import annotations

import pytest

from alogs import __version__
from alogs.__main__ import main

from .conftest import FORMATS


def test_self_test_ok(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--self-test", str(FORMATS / "threadtime.log")])
    assert exit_info.value.code == 0
    assert f"alogs {__version__} self-test: OK 10 entries, format threadtime - 100%" in capsys.readouterr().out


def test_self_test_missing_file(capsys, tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        main(["--self-test", str(tmp_path / "missing.log")])
    assert exit_info.value.code == 1
    assert "FAILED could not open" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"alogs {__version__}"
