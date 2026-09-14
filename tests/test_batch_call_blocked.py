"""call 目标转换失败（控制块内标签）走容错形态并告警。"""

from __future__ import annotations

import shutil
import subprocess

import pytest

BLOCKED_CASE = (
    "@echo off\n"
    "call :INNER\n"
    "echo after\n"
    "if 1==1 (\n"
    ":INNER\n"
    "echo inner\n"
    ")\n"
)


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "call.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_blocked_target_guarded_with_warning(convert_bat, tmp_path):
    out, report = convert_bat(BLOCKED_CASE)
    assert "if declare -F label_INNER >/dev/null 2>&1; then label_INNER; fi" in out
    assert any("未生成函数" in d.message for d in report.warnings)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "after\ninner\n"


def test_blocked_target_with_args(convert_bat, tmp_path):
    text = (
        "@echo off\n"
        "call :INNER a b\n"
        "echo after\n"
        "if 1==1 (\n"
        ":INNER\n"
        "echo inner\n"
        ")\n"
    )
    out, report = convert_bat(text)
    assert "if declare -F label_INNER >/dev/null 2>&1; then label_INNER a b; fi" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "after\ninner\n"


def test_normal_target_still_plain(convert_bat, tmp_path):
    text = (
        "@echo off\n"
        "call :DEFINED\n"
        "echo after\n"
        "goto :eof\n"
        ":DEFINED\n"
        "echo defined\n"
        "goto :eof\n"
    )
    out, report = convert_bat(text)
    assert "\nlabel_DEFINED\n" in out
    assert not any("未生成函数" in d.message for d in report.warnings)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "defined\nafter\n"


def test_undefined_target_unchanged_no_warning(convert_bat, tmp_path):
    out, report = convert_bat("@echo off\ncall :MISSING\necho after\n")
    assert "if declare -F label_MISSING >/dev/null 2>&1; then label_MISSING; fi" in out
    assert not any("未生成函数" in d.message for d in report.warnings)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "after\n"
