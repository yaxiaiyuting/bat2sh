"""%* 映射为 "$*" 与位置参数保护回归。"""

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


def test_star_maps_to_dollar_star(convert_bat):
    out, _ = convert_bat('@echo off\nset "ALL_ARGS=%*"\n')
    assert 'ALL_ARGS="$*"' in out
    assert '\\"' not in out


def test_star_runtime_empty_and_joined(convert_bat):
    out, _ = convert_bat("@echo off\necho 所有参数: %*\n")
    assert 'echo "所有参数: $*"' in out
    proc = _run_with_args(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "所有参数: \n"
    proc = _run_with_args(out, "a", "b")
    assert proc.stdout == "所有参数: a b\n"


def test_positional_args_stay_guarded(convert_bat):
    out, _ = convert_bat("@echo off\necho 参数: %1 %2\n")
    assert "${1:-}" in out
    assert "${2:-}" in out


def test_no_literal_escaped_quote_in_generated_code(convert_bat):
    out, _ = convert_bat('@echo off\nset "ALL_ARGS=%*"\necho 所有参数: %*\n')
    assert '\\"' not in out


def test_for_star_keeps_each_arg_iteration(convert_bat):
    out, _ = convert_bat("@echo off\nfor %%a in (%*) do echo 参数: %%a\n")
    assert 'for a in "$@"; do' in out
