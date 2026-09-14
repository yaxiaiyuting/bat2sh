"""for /f 内两段管道直译：'CMD ^| FILTER' → done < <(CMD | FILTER)。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "forf.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_basic_two_segment_runtime(convert_bat, bash_check, tmp_path):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=*" %%a in (\'echo x ^| findstr x\') do echo %%a\n'
    )
    assert 'done < <(echo "x" | grep x)' in out
    assert report.todo_count == 0
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "x\n"


def test_filter_no_match_does_not_terminate(convert_bat, bash_check, tmp_path):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=*" %%a in (\'echo x ^| findstr nomatch\') do echo BODY:%%a\n'
        "echo after\n"
    )
    assert report.todo_count == 0
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert "BODY:" not in proc.stdout
    assert "after" in proc.stdout


def test_skip_option_with_two_segment(convert_bat, bash_check, tmp_path):
    (tmp_path / "data.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
    out, report = convert_bat(
        "@echo off\n"
        'for /f "skip=1 tokens=*" %%a in (\'type data.txt ^| findstr l\') do echo [%%a]\n'
    )
    assert report.todo_count == 0
    assert "tail -n +2" in out
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "[l2]\n[l3]\n"


def test_tokens_delims_with_two_segment(convert_bat, bash_check, tmp_path):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=2 delims=:" %%a in (\'echo key:value ^| findstr key\') do echo %%a\n'
    )
    assert report.todo_count == 0
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "value\n"


def test_eol_option_with_two_segment(convert_bat, bash_check, tmp_path):
    (tmp_path / "data.txt").write_text(";skip\nkeep\n", encoding="utf-8")
    out, report = convert_bat(
        "@echo off\n"
        'for /f "eol=; tokens=*" %%a in (\'type data.txt ^| findstr .\') do echo [%%a]\n'
    )
    assert report.todo_count == 0
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "[keep]\n"


def test_findstr_chinese_mapping_inside_two_segment(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        "for /f \"tokens=2 delims=:\" %%a in ('ipconfig ^| findstr /i \"IPv4\"') do echo %%a\n"
    )
    assert report.todo_count == 0
    assert "ip addr" in out
    assert "done < <(ip addr | grep -i \"IPv4\")" in out


def test_redirect_inside_pipeline_still_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=*" %%a in (\'sc query x 2^>nul ^| findstr STATE\') do echo %%a\n'
    )
    assert "while" not in out
    assert report.todo_count == 1
    assert "重定向" in report.todos[0].message


def test_todo_command_segment_rolls_back_and_todos(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=*" %%a in (\'sc query wuauserv ^| findstr STATE\') do echo %%a\n'
    )
    assert "while" not in out
    assert report.todo_count == 1
    assert "两段管道无法自动转换" in report.todos[0].message


def test_three_segment_pipeline_still_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=*" %%a in (\'dir /b ^| findstr .bat ^| findstr /v test\') do echo %%a\n'
    )
    assert "while" not in out
    assert report.todo_count == 1
    assert "三段及以上" in report.todos[0].message


def test_quoted_pipe_is_not_a_separator(convert_bat, bash_check):
    out, report = convert_bat('@echo off\nfor /f "tokens=*" %%a in (\'echo "a|b"\') do echo %%a\n')
    assert report.todo_count == 0
    assert "a|b" in out
    bash_check(out)


def test_usebackq_backtick_pipeline_still_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        "for /f \"usebackq\" %%i in (`dir /b ^| findstr x`) do echo %%i\n"
    )
    assert "while" not in out
    assert report.todo_count == 1
    assert "反引号" in report.todos[0].message


def test_or_operator_inside_command_not_split_as_pipeline(convert_bat, bash_check, tmp_path):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('echo a || echo b') do echo %%a\n"
    )
    assert report.todo_count == 0
    assert 'done < <(echo "a" || echo "b")' in out
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "a\n"
