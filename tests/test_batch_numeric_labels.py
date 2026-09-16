"""v1.8.2 A-1：纯数字标签 `:1` 未识别修复回归。

语料依据（v1.8.2 artifact 分类 §2.A）：
- ``判断分区格式.bat:2`` ``:1``（配 ``goto 1``）
- ``结束进程.bat:2`` ``:1``
- ``文件夹伪装.bat:73`` ``:1``（``:1``…``:8``）

根因：``core/batch.py`` 标签匹配要求首字符 ``[A-Za-z_]``，数字标签落入未知命令透传，
产物出现 ``:1: command not found``。
"""

from __future__ import annotations


def test_numeric_label_is_comment_not_command(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\n:1\ncls\necho ok\n")
    bash_check(out)
    assert "# :1" in out
    assert not any(line.strip() == ":1" for line in out.splitlines())


def test_numeric_label_reachable_via_goto(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\ngoto 1\n:1\necho reached\npause>nul\n")
    bash_check(out)
    assert report.error_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "reached" in proc.stdout


def test_multi_digit_label_and_call_target(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ngoto 12\n:12\necho twelve\n")
    bash_check(out)
    assert "# :12" in out


def test_double_colon_comment_still_comment(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\n:: note here\necho ok\n")
    bash_check(out)
    assert "# note here" in out
    assert not any(line.strip().startswith(":note") for line in out.splitlines())
