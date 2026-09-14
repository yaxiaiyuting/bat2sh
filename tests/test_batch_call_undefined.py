"""未定义 call 目标不终止脚本（bat 语义）。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "call.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_undefined_call_does_not_terminate(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\ncall :UNDEFINED\necho 后续行\n")
    assert (
        "if declare -F label_UNDEFINED >/dev/null 2>&1; then label_UNDEFINED; fi" in out
    )
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "后续行\n"


def test_undefined_call_with_args(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\ncall :MISSING a b\necho 继续\n")
    assert (
        "if declare -F label_MISSING >/dev/null 2>&1; then label_MISSING a b; fi" in out
    )
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "继续\n"


def test_defined_call_unchanged(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\ncall :DEFINED\necho after\ngoto :eof\n:DEFINED\necho defined\ngoto :eof\n"
    )
    assert "if declare -F" not in out
    assert "\nlabel_DEFINED\n" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "defined\nafter\n"


def test_defined_call_passes_args(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\ncall :SUB arg1 arg2\ngoto :eof\n:SUB\necho p1=%1 p2=%2\ngoto :eof\n"
    )
    assert "label_SUB arg1 arg2" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "p1=arg1 p2=arg2\n"
