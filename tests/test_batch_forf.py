"""for /f 选项分派转换的回归测试。"""

from __future__ import annotations

import pytest


def test_for_f_tokens_star_uses_process_substitution(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "while IFS= read -r a; do" in out
    assert '[ -z "$a" ] && continue' in out
    assert "done < <(ls -1)" in out
    assert "| while" not in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_f_tokens_list_with_delims(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1,2 delims=,\" %%a in ('echo 1,2,3,4') do echo %%a %%b\n"
    )
    assert "while IFS=, read -r a b _; do" in out
    assert 'echo "${a} ${b}"' in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_f_single_token_skips_leading_fields(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=2\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "while read -r _ a _; do" in out
    assert report.todo_count == 0


def test_for_f_tokens_star_suffix_takes_rest(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1*\" %%a in ('dir /b') do echo %%a %%b\n"
    )
    assert "while read -r a b; do" in out
    assert "read -r a b _;" not in out
    assert report.todo_count == 0


def test_for_f_tokens_range(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1-3\" %%a in ('dir /b') do echo %%a %%b %%c\n"
    )
    assert "read -r a b c _;" in out
    assert report.todo_count == 0


def test_for_f_usebackq_file_uses_redirection(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nfor /f "usebackq tokens=*" %%l in ("test1.txt") do echo %%l\n'
    )
    assert 'done < "test1.txt"' in out
    assert "< <(" not in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_f_unquoted_file_uses_redirection(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in (test1.txt) do echo %%a\n"
    )
    assert 'done < "test1.txt"' in out
    assert report.todo_count == 0


def test_for_f_empty_line_skip_guard(convert_bat):
    out, _ = convert_bat(
        "@echo off\nfor /f \"tokens=1,2 delims=,\" %%a in ('echo 1,2') do echo %%a\n"
    )
    assert '[ -z "$a" ] && continue' in out


def test_for_f_default_tokens_reads_first_field(convert_bat):
    out, report = convert_bat("@echo off\nfor /f %%a in ('dir /b') do echo %%a\n")
    assert "while read -r a _; do" in out
    assert report.todo_count == 0
    assert report.warning_count == 0


def test_for_f_runs_without_unbound_variable(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\nfor /f \"tokens=1,2 delims=,\" %%a in ('echo 1,2') do echo [%%a][%%b]\n"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "[1][2]\n"


def test_for_f_duplicate_tokens_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1,1\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_for_f_bad_tokens_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=x\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_for_f_goto_body_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('dir /b') do goto :end\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1
