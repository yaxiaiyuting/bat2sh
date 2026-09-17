"""``for /f`` 字符串形式（``in ("...")``）转换的回归测试（v1.11.0）。

断言 cmd 的 **tokens/delims 切分语义**与 ``""`` 转义语义，而非编码转换器现况。
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    return subprocess.run([bash], input=text, capture_output=True, text=True)


def test_string_tokens_rest_splits_on_delims(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nfor /f "tokens=1,2* delims==" %%i in ("a=b=c") do echo [%%i][%%j][%%k]\n'
    )
    assert report.todo_count == 0
    assert 'done <<< "a=b=c"' in out
    bash_check(out)
    assert _run(out).stdout.strip() == "[a][b][c]"


def test_string_literal_with_spaces_is_single_line(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "delims=" %%i in ("hello world") do echo [%%i]\n'
    )
    assert report.todo_count == 0
    assert _run(out).stdout.strip() == "[hello world]"


def test_string_with_delayed_var_expands(convert_bat):
    out, report = convert_bat(
        "@echo off\nsetlocal enabledelayedexpansion\nset vtd=x=y\n"
        'for /f "tokens=1,2 delims==" %%i in ("!vtd!") do echo [%%i][%%j]\n'
    )
    assert report.todo_count == 0
    assert 'done <<< "${vtd}"' in out
    assert _run(out).stdout.strip() == "[x][y]"


def test_string_with_percent_var_expands(convert_bat):
    out, report = convert_bat(
        "@echo off\nset vtd=x=y\n"
        'for /f "tokens=1,2 delims==" %%i in ("%vtd%") do echo [%%i][%%j]\n'
    )
    assert report.todo_count == 0
    assert 'done <<< "${vtd}"' in out
    assert _run(out).stdout.strip() == "[x][y]"


def test_string_doubled_quote_is_literal_quote(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "delims=" %%i in ("he said ""hi""") do echo [%%i]\n'
    )
    assert report.todo_count == 0
    assert _run(out).stdout.strip() == '[he said "hi"]'


def test_string_skip_drops_lines(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "skip=1 delims=" %%i in ("only") do echo [%%i]\n'
    )
    assert report.todo_count == 0
    assert _run(out).stdout.strip() == ""


def test_string_with_dollar_stays_todo(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "delims=" %%i in ("price $5") do echo %%i\n'
    )
    assert report.todo_count == 1
    assert "find" not in out


def test_string_with_backtick_stays_todo(convert_bat):
    out, report = convert_bat(
        '@echo off\nfor /f "delims=" %%i in ("a `cmd` b") do echo %%i\n'
    )
    assert report.todo_count == 1


def test_command_and_file_forms_unaffected(convert_bat, bash_check):
    out_cmd, rep_cmd = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('echo hi') do echo %%a\n"
    )
    assert rep_cmd.todo_count == 0
    assert 'done < <(echo "hi")' in out_cmd
    bash_check(out_cmd)

    out_file, rep_file = convert_bat(
        '@echo off\nfor /f "delims=" %%i in (data.txt) do echo %%i\n'
    )
    assert rep_file.todo_count == 0
    assert 'done < "data.txt"' in out_file
    bash_check(out_file)
