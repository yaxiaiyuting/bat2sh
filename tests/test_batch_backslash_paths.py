"""v1.8.2 A-3：未知命令 / POSIX 透传路径反斜杠未转换修复回归。

语料依据（v1.8.2 artifact 分类 §2.A A2/A7）：
- ``宽带连接.bat:1`` ``c:\\windows\\system32\\rasdial …`` → 产物保留反斜杠
- ``注册表/设注册表某个键的键值为变量1.bat:2`` ``%temp%\\d~.vbs``
- ``史上最牛X批处理工具包…bat`` 大量 ``c:\\windows\\…``
"""

from __future__ import annotations


def test_unknown_command_path_backslashes_converted(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nc:\\windows\\system32\\mytool foo bar\n", bash_check=False)
    bash_check(out)
    assert "c:/windows/system32/mytool foo bar" in out
    assert "\\" not in out.split("源文件:")[1]


def test_mapped_path_prefix_command_resolves_to_todo(convert_bat):
    # v1.9.0 B-1：盘符全路径先取 basename 再查映射表（rasdial 为 C 档 → 建议 + TODO）
    out, report = convert_bat("@echo off\nc:\\windows\\system32\\rasdial foo bar\n")
    assert "# TODO: 手动检查:" in out
    assert not any(line.strip().startswith("c:/windows") for line in out.splitlines())
    assert report.todo_count >= 1


def test_start_inner_windows_only_command_becomes_todo(convert_bat):
    # v1.9.0 B-2：`start` 的目标若不是路径，应识别 Windows 专有命令并诚实 TODO
    out, report = convert_bat('@echo off\nSTART /WAIT REGEDIT /S "x.reg"\n')
    assert "# TODO: 手动检查: START /WAIT REGEDIT" in out
    assert report.todo_count >= 1


def test_start_inner_normal_command_unchanged(convert_bat):
    out, report = convert_bat("@echo off\nstart /wait notepad\n")
    assert "notepad" in out
    assert report.todo_count == 0


def test_unknown_command_relative_path_converted(convert_bat):
    out, _ = convert_bat("@echo off\nfoo\\bar baz\n")
    assert "foo/bar baz" in out


def test_posix_keep_path_backslashes_converted(convert_bat):
    out, _ = convert_bat("@echo off\ngit\\bin\\git status\n")
    assert "git/bin/git status" in out


def test_redirect_target_backslashes_converted(convert_bat):
    out, _ = convert_bat('@echo off\n>"%temp%\\d~.vbs" echo hi\n')
    assert '"${TMPDIR:-/tmp}/d~.vbs"' in out
