"""wine 黄金对照 harness 的 pytest 包装（B3，无 wine 时 skip）。"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[1] / "tools" / "oracle" / "golden_harness.py"


def _load():
    spec = importlib.util.spec_from_file_location("golden_harness", _HARNESS)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


gh = _load()

pytestmark = pytest.mark.skipif(
    not gh.wine_available() or shutil.which("bash") is None,
    reason="需要 wine + bash（黄金对照 harness）",
)


@pytest.mark.parametrize("name", ("g01", "g02", "g03", "g04", "g05", "g06"))
def test_golden_case_matches_wine(name):
    result = gh.compare_case(name)
    assert result["match"], (
        f"{name} 与 wine 不一致：wine={result['wine']!r} bat2sh={result['bash']!r}"
    )


@pytest.mark.parametrize("name", ("g07", "g08", "g09", "g10", "g11", "g12"))
def test_state_machine_case_matches_wine(name):
    """v2.5.0：CFG 状态机产物须与 wine cmd 语义一致（goto 形态证伪）。"""
    result = gh.compare_case(name)
    assert result["state_machine"] is True
    assert result["match"], (
        f"{name}（状态机）与 wine 不一致：wine={result['wine']!r} bat2sh={result['bash']!r}"
    )


def test_state_machine_case_not_a_fallback_todo():
    """状态机用例产物不得含 TODO（否则说明门控回退，Wine 对照失去意义）。"""
    bat = (gh.CASES_DIR / "g07.bat").read_text(encoding="utf-8")
    assert "__bat2sh_pc" in gh.to_bash(bat, state_machine=True)


def test_g05_records_a1_freeze():
    result = gh.compare_case("g05")
    assert result["bash"] == "i=1\ni=1"


def test_unreliable_probes_documented():
    assert set(gh.UNRELIABLE_PROBES) == {"x5_fd_digit", "a8_findstr_multiword"}
