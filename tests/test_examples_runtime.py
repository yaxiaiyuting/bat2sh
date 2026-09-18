"""examples 转换后的运行时与结构回归：防 unbound / 主流程吞噬类缺陷漏网。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bat2sh.core.engine import convert_file
from bat2sh.core.settings import ConvertSettings

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BAT_FILES = sorted(p.name for p in EXAMPLES.glob("*.bat"))


def _convert(name: str) -> str:
    result = convert_file(EXAMPLES / name, ConvertSettings(), write=False)
    assert result.error == ""
    return result.text


def _run_converted(tmp_path: Path, text: str, *args: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "converted.sh"
    script.write_text(text, encoding="utf-8")
    env = {**os.environ, "LC_ALL": "C"}
    return subprocess.run(
        [bash, str(script), *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        timeout=120,
        env=env,
    )


def _assert_no_conversion_crash(proc: subprocess.CompletedProcess) -> None:
    for marker in ("unbound variable", "未绑定的变量", "syntax error"):
        assert marker not in proc.stderr, proc.stderr


@pytest.mark.parametrize("name", BAT_FILES)
def test_bat_example_runs_without_unbound(name, tmp_path):
    proc = _run_converted(tmp_path, _convert(name))
    _assert_no_conversion_crash(proc)


def test_stress_without_args_runs_past_positional_setup(tmp_path):
    proc = _run_converted(tmp_path, _convert("stress_test.bat"))
    _assert_no_conversion_crash(proc)
    assert "未提供参数，使用默认值。" in proc.stdout


def test_stress_with_args_runs_past_positional_setup(tmp_path):
    proc = _run_converted(tmp_path, _convert("stress_test.bat"), "arg1", "arg2")
    _assert_no_conversion_crash(proc)
    assert "参数1: arg1" in proc.stdout
    assert "参数2: arg2" in proc.stdout


def test_stress_structure_main_flow_is_linear():
    text = _convert("stress_test.bat")
    assert "label_SKIP" not in text
    goto = text.index("# goto SKIP（前向跳转")
    dead = text.index("# [不可达] echo 这行不会执行")
    label = text.index("# :SKIP（goto 目标，不函数化，主流程继续）")
    skipped = text.index('echo "跳过了。"')
    assert goto < dead < label < skipped


def test_deepseek_static_goto_targets_not_functionized():
    text = _convert("deepseek_bat_20260913_faa286.bat")
    assert "label_FORWARD" not in text
    assert "label_LOOP_START" not in text
    assert "label_IF_GOTO" not in text
    assert "# :FORWARD（goto 目标，不函数化，主流程继续）" in text
