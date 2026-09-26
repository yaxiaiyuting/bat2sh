"""%%~nx / %%~n / %%~x 循环变量修饰符回归 + set /a %% 取模守护。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "loop.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_loop_var_nx_basename(convert_bat, tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    out, _ = convert_bat("@echo off\nfor %%F in (*.txt) do echo %%~nxF\n")
    assert 'echo "$(basename "${f}")"' in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "a.txt\n"


def test_loop_var_n_without_extension(convert_bat, tmp_path):
    """语义：``%%~nF`` 取去扩展名的文件名（不再钉死实现串）。"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    out, _ = convert_bat("@echo off\nfor %%F in (*.txt) do echo %%~nF\n")
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "a\n"


def test_loop_var_x_extension(convert_bat):
    out, _ = convert_bat("@echo off\nfor %%F in (*.txt) do echo %%~xF\n")
    assert 'echo "$(echo ".${f##*.}")"' in out


def test_set_a_modulo_still_converts(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\nset /a X=10 %% 3\necho X=%X%\n")
    assert "X=$(( 10 % 3 ))" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "X=1\n"


def test_combined_no_interference(convert_bat, tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    out, _ = convert_bat(
        "@echo off\n"
        "for %%F in (*.txt) do (echo %%~nxF & set /a Y=7 %% 2 & echo Y=%Y% & echo %%~nF & echo %%~xF)\n"
    )
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    # cmd 在块解析时冻结 %Y%（此时尚未赋值 ⇒ 空串）；块内 set /a 的赋值对该 %Y% 不可见（wine 实测 Y=）
    assert proc.stdout == "a.txt\nY=\na\n.txt\n"
