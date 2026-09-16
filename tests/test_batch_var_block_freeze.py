"""A1（v1.9.2）：块内 %VAR% 解析时冻结语义回归（%VAR% 冻结；!VAR! 执行时取值）。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "freeze.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_for_block_freezes_percent_var(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\nset v=1\nfor %%i in (a b) do (set v=2 & echo i=%v%)\n")
    assert "__bat2sh_snap_v=" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "i=1\ni=1\n"


def test_multiline_for_block_freezes(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\nset v=1\nfor %%i in (a b) do (\nset v=2\necho i=%v%\n)\n")
    assert "__bat2sh_snap_v=" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "i=1\ni=1\n"


def test_nested_block_freezes_at_outermost(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\nset v=1\nfor %%i in (a b) do (\nif 1==1 (\nset v=2\necho n=%v%\n)\n)\n"
    )
    assert "__bat2sh_snap_v=" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "n=1\nn=1\n"


def test_if_block_freezes(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\nset x=1\nif 1==1 (set x=2 & echo x=%x%)\n")
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "x=1\n"


def test_else_block_freezes(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\nset x=1\nif 1==2 (echo t) else (set x=2 & echo e=%x%)\n")
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "e=1\n"


def test_block_unassigned_var_has_no_snapshot(convert_bat, tmp_path):
    out, _ = convert_bat("@echo off\nset v=9\nfor %%i in (a b) do echo s=%v%\n")
    assert "__bat2sh_snap_v=" not in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "s=9\ns=9\n"


def test_outside_block_is_live_reference(convert_bat):
    out, _ = convert_bat("@echo off\nset v=1\nset v=2\necho t=%v%\n")
    assert "__bat2sh_snap_v=" not in out
    assert 'echo "t=${v}"' in out


def test_delayed_var_inside_block_stays_live(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\nsetlocal enabledelayedexpansion\nset v=1\n"
        "for %%i in (a b) do (set v=2 & echo d=!v!)\n"
    )
    assert "__bat2sh_snap_v=" not in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "d=2\nd=2\n"


def test_function_body_block_freezes(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\ncall :work\ngoto :eof\n:work\nset v=1\n"
        "for %%i in (a b) do (set v=2 & echo f=%v%)\ngoto :eof\n"
    )
    assert "__bat2sh_snap_v=" in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "f=1\nf=1\n"
