"""``attrib ±r`` → ``chmod ∓w`` 的回归测试（v1.11.0）。"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess

import pytest


def _run(text: str, cwd=None) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    return subprocess.run([bash], input=text, capture_output=True, text=True, cwd=cwd)


def test_attrib_plus_r_maps_to_chmod_minus_w(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nattrib +r \"f.txt\"\n")
    assert report.todo_count == 0
    assert 'if [ -e "f.txt" ]; then chmod -w "f.txt"; fi' in out
    bash_check(out)


def test_attrib_minus_r_maps_to_chmod_plus_w(convert_bat):
    out, report = convert_bat("@echo off\nattrib -r \"f.txt\"\n")
    assert report.todo_count == 0
    assert 'chmod +w "f.txt"' in out


def test_attrib_multiple_targets(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nattrib -r \"a.ini\" \"b.ini\"\n")
    assert report.todo_count == 0
    assert 'chmod +w "a.ini"' in out and 'chmod +w "b.ini"' in out
    bash_check(out)


def test_attrib_readonly_semantics_roundtrip(convert_bat, tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")
    out_plus, _ = convert_bat("@echo off\nattrib +r \"f.txt\"\n")
    proc = _run(out_plus, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert not os.access(target, os.W_OK)
    out_minus, _ = convert_bat("@echo off\nattrib -r \"f.txt\"\n")
    proc = _run(out_minus, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert os.access(target, os.W_OK)
    assert stat.S_IMODE(target.stat().st_mode) & stat.S_IWUSR


def test_attrib_missing_path_is_noop(convert_bat):
    out, _ = convert_bat("@echo off\nattrib +r \"missing.txt\"\n")
    proc = _run(out)
    assert proc.returncode == 0, proc.stderr


def test_attrib_system_hidden_archive_stay_todo(convert_bat):
    for line in ('attrib +h "f.txt"', 'attrib +s "d"', 'attrib +a "f"', 'attrib -s -h -r -a "d.ini"'):
        out, report = convert_bat(f"@echo off\n{line}\n")
        assert report.todo_count == 1, line
        assert "chmod" not in out, line


def test_attrib_without_target_stays_todo(convert_bat):
    out, report = convert_bat("@echo off\nattrib\n")
    assert report.todo_count == 1
    assert "chmod" not in out


def test_attrib_todo_hint_is_actionable(convert_bat):
    _, report = convert_bat('@echo off\nattrib +h "f.txt"\n')
    message = report.todos[0].message
    assert "chmod" in message
    assert ". 前缀" in message
