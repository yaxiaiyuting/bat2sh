"""v1.8.2 A-2a：命令词与开关粘连（`dir/b`、`cd/d`、`date/t`）拆分回归。

语料依据（v1.8.2 artifact 分类 §2.A A3）：
- ``右键菜单/新建“当前日期文件夹”/md.bat:2`` ``cd/d %~dp1`` → 产物 ``cd/d ${1:-}``
- ``将所在目录的BAT文件合并…bat:12`` ``for /f %%i in ('dir/b *.bat')``
- ``查找最新的文件.bat:9`` ``date/t`` → ``date/t: command not found``

注意：本文件的被测实现（``_convert_simple_no_pipe`` 的粘连拆分）因分批提交时
``git add`` 范围过宽，实际落在提交 ``14c88b6`` 中（该提交标题为 A-4b 补）。
本提交补齐 A-2a 的专属回归测试，并在文档中披露该提交归属问题。
"""

from __future__ import annotations


def test_cd_stuck_switch_split(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ncd/d %~dp1\n", bash_check=False)
    bash_check(out)
    assert "cd/d" not in out
    assert 'cd "${1:-}"' in out


def test_dir_stuck_switch_split_inside_for_f(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\nfor /f %%i in ('dir/b *.bat') do echo %%i\n", bash_check=False
    )
    bash_check(out)
    assert "dir/b" not in out
    assert 'compgen -G "*.bat" || true' in out


def test_date_stuck_switch_is_not_invalid_command(convert_bat):
    out, report = convert_bat("@echo off\ndate/t >>out.txt\n")
    assert "date/t" not in out
    assert report.todo_count == 1


def test_path_with_slash_not_split_as_command(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nxcopy a/b.txt c\n", bash_check=False)
    bash_check(out)
    assert '"a/b.txt"' in out
