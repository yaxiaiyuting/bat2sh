"""findstr 开关映射：/r 为正则（grep -E），/c: 为字面（grep -F）。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_r_switch_uses_extended_regex(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /r "^[0-9]" data.txt\n')
    assert 'grep -E "^[0-9]" "data.txt"' in out


def test_c_switch_without_r_is_fixed(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /c:"a.b" data.txt\n')
    assert 'grep -F "a.b" "data.txt"' in out


def test_r_with_c_switch_prefers_regex(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /r /c:"^[0-9][0-9]*$" numbers.txt\n')
    assert 'grep -E "^[0-9][0-9]*$" "numbers.txt"' in out
    assert "-F" not in out


def test_i_switch(convert_bat):
    out, _ = convert_bat("@echo off\nfindstr /i hello data.txt\n")
    assert "grep -i hello" in out


def test_v_switch(convert_bat):
    out, _ = convert_bat("@echo off\nfindstr /v hello data.txt\n")
    assert "grep -v hello" in out


def test_regex_mode_runtime_matches_number_lines(convert_bat, tmp_path):
    (tmp_path / "numbers.txt").write_text("123\nabc\n45\n", encoding="utf-8")
    out, _ = convert_bat('@echo off\nfindstr /r /c:"^[0-9][0-9]*$" numbers.txt\n')
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    proc = subprocess.run(
        [bash], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "123\n45\n"
