from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_release.py"
spec = importlib.util.spec_from_file_location("check_release", SCRIPT)
check_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_release)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "alogs").mkdir()

    def make(version: str, owner: str = "someone") -> Path:
        (tmp_path / "alogs" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            f'[project.urls]\nHomepage = "https://github.com/{owner}/alogs-cli"\n', encoding="utf-8"
        )
        return tmp_path

    return make


def test_matching_tag_passes(repo):
    assert check_release.problems("v0.2.0", repo("0.2.0")) == []
    assert check_release.problems("v1.0.0rc1", repo("1.0.0rc1")) == []


def test_mismatched_tag(repo):
    [problem] = check_release.problems("v0.2.1", repo("0.2.0"))
    assert "expected tag 'v0.2.0'" in problem
    assert check_release.problems("0.2.0", repo("0.2.0"))  # missing "v"


def test_bad_version_and_placeholder(repo):
    found = check_release.problems("v0.2", repo("0.2", owner="OWNER"))
    assert len(found) == 2
    assert any("not like 1.2.3" in p for p in found)
    assert any("OWNER placeholder" in p for p in found)


def test_current_repo_tag_for_its_own_version():
    version = check_release.code_version()
    found = check_release.problems(f"v{version}")
    if "OWNER/" in (check_release.ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        assert found == ["pyproject.toml still contains the OWNER placeholder in the GitHub URLs"]
    else:
        assert found == []
