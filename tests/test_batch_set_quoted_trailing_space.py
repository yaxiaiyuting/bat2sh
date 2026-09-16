"""v1.8.2 A-5：``set "x=y "`` 引号内尾随空格被吞修复回归。

语料依据（v1.8.2 artifact 分类 §2.A A9）：
- ``窗口设置/1.bat:3`` ``set "r=color "&set "t=title "``
- ``窗口设置/1.bat:4`` ``%t%%q%`` → 误产 ``title广东``（cmd 实为 ``title 广东…``）

根因：``cmd_set`` 对引号形式也执行 ``value.rstrip()``，吞掉 cmd 会保留的尾随空格。
"""

from __future__ import annotations


def test_quoted_set_preserves_trailing_space(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nset "t=title "\nset "q=Hello"\necho [%t%%q%]\n')
    bash_check(out)
    assert 't="title "' in out


def test_quoted_set_trailing_space_visible_at_runtime(convert_bat, bash_check, bash_run):
    out, _ = convert_bat('@echo off\nset "sep=, "\necho one%sep%two\n')
    bash_check(out)
    assert 'sep=", "' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "one, two"


def test_unquoted_set_still_normalised(convert_bat, bash_check, bash_run):
    out, _ = convert_bat("@echo off\nset x=abc\necho %x%\n")
    bash_check(out)
    assert 'x="abc"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "abc"
