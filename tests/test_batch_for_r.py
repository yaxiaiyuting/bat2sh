"""``for /r`` → ``find`` 转换的回归测试（v1.11.0）。

断言转换的**语义**（递归枚举目录），而非编码转换器当前行为。
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_for_r_dot_converts_to_find_dir_loop(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do echo %%i\n")
    assert report.todo_count == 0
    assert "while IFS= read -r i; do" in out
    assert 'done < <(find . -type d)' in out
    assert "for i in" not in out
    bash_check(out)


def test_for_r_enumerates_directories_recursively(convert_bat, tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "c").mkdir()
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do echo %%i\n")
    assert report.todo_count == 0
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    proc = subprocess.run(
        [bash], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    enumerated = set(proc.stdout.split())
    assert {".", "./a", "./a/b", "./c"} <= enumerated


def test_for_r_block_body_converts(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /r %%i in (.) do (\n  echo %%i\n)\n"
    )
    assert report.todo_count == 0
    assert "while IFS= read -r i; do" in out
    assert 'done < <(find . -type d)' in out
    bash_check(out)


def test_for_r_variable_root_defaults_to_current_dir(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nfor /r %back% %%a in (.) do echo %%a\n")
    assert "find \"${back:-.}\" -type d" in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_r_file_set_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (*.jpg) do echo %%i\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_r_body_with_goto_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do goto done\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_r_glob_root_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (*.txt) do echo %%i\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_l_and_plain_for_unaffected(convert_bat, bash_check):
    out_l, report_l = convert_bat("@echo off\nfor /l %%i in (1,1,3) do echo %%i\n")
    assert "for i in $(seq 1 1 3); do" in out_l
    assert "find" not in out_l
    assert report_l.todo_count == 0
    bash_check(out_l)

    out_p, report_p = convert_bat("@echo off\nfor %%i in (a b) do echo %%i\n")
    assert "for i in a b; do" in out_p
    assert "find" not in out_p
    assert report_p.todo_count == 0
    bash_check(out_p)


def test_for_f_file_form_unaffected(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"delims=\" %%i in (data.txt) do echo %%i\n"
    )
    assert report.todo_count == 0
    assert 'done < "data.txt"' in out
    assert "find" not in out
    bash_check(out)
