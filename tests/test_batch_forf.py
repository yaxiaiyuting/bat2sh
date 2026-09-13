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
    assert report.warning_count == 1
    assert "goto" in report.warnings[0].message


# ----------------------------------------------------------------------
# CRLF / tokens 越界
# ----------------------------------------------------------------------
def test_for_f_crlf_trim_line(convert_bat):
    out, _ = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "a=\"${a%$'\\r'}\"" in out


def test_for_f_crlf_multi_var_trims_last_variable(convert_bat):
    out, _ = convert_bat(
        "@echo off\nfor /f \"tokens=1,2 delims=,\" %%a in ('echo 1,2') do echo %%a %%b\n"
    )
    assert "b=\"${b%$'\\r'}\"" in out


def test_for_f_crlf_file_runs_clean(convert_bat, bash_run, tmp_path):
    (tmp_path / "crlf.txt").write_bytes("alpha\r\n\r\nbeta\r\n".encode("utf-8"))
    out, _ = convert_bat(
        '@echo off\nfor /f "usebackq tokens=*" %%a in ("crlf.txt") do echo [%%a]\n'
    )
    proc = bash_run(f"cd {tmp_path}\n" + out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "[alpha]\n[beta]\n"


def test_for_f_undeclared_token_warns(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1\" %%a in ('dir /b') do echo %%a %%b\n"
    )
    assert any("循环体引用 %%b 但 tokens 未声明" == d.message for d in report.warnings)
    assert report.todo_count == 0


# ----------------------------------------------------------------------
# skip / eol
# ----------------------------------------------------------------------
def test_for_f_skip_wraps_tail(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"skip=1 tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "done < <(ls -1 | tail -n +2)" in out
    assert report.todo_count == 0


def test_for_f_skip_two_wraps_tail(convert_bat):
    out, _ = convert_bat(
        "@echo off\nfor /f \"skip=2 tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "tail -n +3" in out


def test_for_f_skip_runs_in_bash(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\nfor /f \"skip=1 tokens=*\" %%a in ('seq 2') do echo %%a\n"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "2\n"


def test_for_f_skip_multiline_body(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"skip=1 tokens=*\" %%a in ('dir /b') do (\n    echo %%a\n)\n"
    )
    assert "done < <(ls -1 | tail -n +2)" in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_f_eol_guard_and_warning(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"eol=; tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert '[[ -z "$a" || "$a" == \\;* ]] && continue' in out
    assert report.warning_count == 1
    assert (
        "eol=; 仅近似为跳过以 ; 开头的行；Windows 在行中间遇到 ; 会截断，请核对"
        == report.warnings[0].message
    )


def test_for_f_eol_runs_in_bash(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\nfor /f \"eol=1 tokens=*\" %%a in ('seq 3') do echo %%a\n"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "2\n3\n"


def test_for_f_skip_and_eol_together(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"skip=1 eol=; tokens=*\" %%a in ('dir /b') do echo %%a\n"
    )
    assert "tail -n +2" in out
    assert '[[ -z "$a" || "$a" == \\;* ]] && continue' in out
    assert report.warning_count == 1


def test_for_f_skip_usebackq_file(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "usebackq skip=1 tokens=*" %%a in ("test1.txt") do echo %%a\n'
    )
    assert 'done < <(tail -n +2 < "test1.txt")' in out
    assert report.todo_count == 0

