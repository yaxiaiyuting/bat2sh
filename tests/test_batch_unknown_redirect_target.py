"""v1.8.3 044：重定向目标依赖未赋值变量 → 诚实 TODO（保守，不产出 ``>""``）。

语料依据（docs/v1.8.3-attribution.md [044]）：
- ``备份文件/备份服务.bat:12`` ``echo … >"%FILENAME%"``，而 ``FILENAME`` 的
  ``:3-4`` ``for /f`` 已被降级为 TODO → 产物 ``>"${FILENAME:-}"`` → 运行期 ``>""`` 报错。
"""

from __future__ import annotations


def test_redirect_to_unset_variable_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat('@echo off\necho hi >"%FILENAME%"\n')
    bash_check(out)
    assert '# TODO: 手动检查: echo hi >"%FILENAME%"' in out
    assert report.todo_count == 1


def test_redirect_to_assigned_variable_kept(convert_bat, bash_check, tmp_path):
    out, report = convert_bat('@echo off\nset FILENAME=out.txt\necho hi >"%FILENAME%"\n')
    bash_check(out)
    assert report.todo_count == 0
    assert '>"${FILENAME}"' in out


def test_redirect_to_env_mapped_variable_not_todo(convert_bat):
    out, report = convert_bat('@echo off\necho hi >"%temp%\\x"\n')
    assert report.todo_count == 0
    assert "${TMPDIR:-/tmp}/x" in out


def test_redirect_to_userprofile_not_todo(convert_bat):
    out, report = convert_bat('@echo off\necho x >"%USERPROFILE%\\a.url"\n')
    assert report.todo_count == 0
    assert "${HOME:-}/a.url" in out
