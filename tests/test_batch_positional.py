"""位置参数 %~N / %N 生成 ${N:-}：set -u 下缺参不再 unbound。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run_with_args(script: str, *args: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    command = [bash, "-s", "--", *args] if args else [bash]
    return subprocess.run(
        command, input=script, capture_output=True, text=True, timeout=30
    )


def test_modifier_positional_becomes_default_guarded(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "A=%~1"\necho A=%A%\n')
    assert 'A="${1:-}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "unbound" not in proc.stderr


def test_bare_positional_becomes_default_guarded(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "B=%1"\necho B=%B%\n')
    assert 'B="${1:-}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "unbound" not in proc.stderr


def test_two_positionals_both_guarded(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\necho one=%~1 two=%~2\n")
    assert "${1:-}" in out
    assert "${2:-}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr


def test_positional_in_if_condition_guarded(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nif "%~1"=="" echo no-args\n')
    assert '[ "${1:-}" = "" ]' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "no-args" in proc.stdout


def test_script_name_modifiers_unchanged(convert_bat):
    out, _ = convert_bat("@echo off\necho %~nx0\necho %~f0\n")
    assert 'echo "$(basename "$0")"' in out
    assert 'echo "$(readlink -f "$0")"' in out


def test_shift_then_positional_reference(convert_bat):
    out, _ = convert_bat("@echo off\nshift\necho first=%~1\n")
    assert "${1:-}" in out
    proc = _run_with_args(out, "a", "b")
    assert proc.returncode == 0, proc.stderr
    assert "first=b" in proc.stdout


def test_star_with_empty_args_does_not_crash(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "ALL_ARGS=%*"\necho args: %* done\n')
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "unbound" not in proc.stderr


def test_stress_pattern_guard_fallback_runs_without_args(convert_bat, bash_run):
    out, _ = convert_bat(
        '@echo off\nset "ARG1=%~1"\n'
        'if "%~1"=="" (\n    echo default\n    set "ARG1=default1"\n'
        ') else (\n    echo provided\n)\necho A=%ARG1%\n'
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "default" in proc.stdout
    assert "A=default1" in proc.stdout
