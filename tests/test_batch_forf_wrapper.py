"""for /f 命令串整体被双引号包装（cmd /c 包装引号）的处理回归测试。

语料依据（v1.4.1 沙箱体检 §10，016-bat-master-wmic查找文件.bat）：
``for /f %%a in ('"wmic ... |find ...|sort /r"')`` 之前整串被当单个命令名执行
（`No such file or directory`）。cmd 语义外层引号是 cmd /c 包装，管道仍按管道执行。
"""

from __future__ import annotations

WRAPPED_THREE_SEGMENTS = (
    '@echo off\n'
    'for /f %%a in (\'"wmic logicaldisk get caption|find /i /v "caption"|sort /r"\') '
    "do echo %%a\n"
)
WRAPPED_TWO_SEGMENTS = (
    '@echo off\nfor /f "delims=" %%a in (\'"echo hello|findstr h"\') do echo got-%%a\n'
)
WRAPPED_NO_PIPE = (
    '@echo off\nfor /f "delims=" %%a in (\'"C:\\path with space\\tool.exe" "arg"\') '
    "do echo %%a\n"
)
WRAPPED_UNKNOWN_SEGMENTS = (
    '@echo off\nfor /f "delims=" %%a in (\'"C:\\tool dir\\my tool.exe" "a|b"\') '
    "do echo %%a\n"
)
NOT_FULLY_WRAPPED = (
    '@echo off\nfor /f "delims=" %%a in (\'"C:\\tool.exe" x|findstr y\') do echo %%a\n'
)


def test_wrapped_three_segments_becomes_todo(convert_bat, bash_check):
    out, report = convert_bat(WRAPPED_THREE_SEGMENTS)
    bash_check(out)
    assert "# TODO: 手动检查" in out
    assert '<("wmic' not in out
    assert report.todo_count >= 1


def test_wrapped_two_segments_converts_and_runs(convert_bat, bash_check, bash_run):
    out, _ = convert_bat(WRAPPED_TWO_SEGMENTS)
    bash_check(out)
    assert 'done < <(echo "hello" | grep h)' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "got-hello\n"


def test_wrapped_without_pipe_not_stripped(convert_bat, bash_check):
    out, _ = convert_bat(WRAPPED_NO_PIPE)
    bash_check(out)
    assert "# TODO: 手动检查" in out
    assert "done < <(" not in out


def test_wrapped_unknown_segments_not_stripped(convert_bat, bash_check):
    out, _ = convert_bat(WRAPPED_UNKNOWN_SEGMENTS)
    bash_check(out)
    assert "# TODO: 手动检查" in out
    assert "done < <(" not in out


def test_not_fully_wrapped_not_stripped(convert_bat, bash_check):
    out, _ = convert_bat(NOT_FULLY_WRAPPED)
    bash_check(out)
    assert "# TODO: 手动检查" in out
    assert "done < <(" not in out
