"""rem 注释变体 / goto 无空格 / call:label 解析回归测试。

语料依据（v1.4.1 批量分析）：
- ``REM.--`` 风格注释（BatchDelayOnExit.bat，5 处）
- ``goto:eof`` 无空格（17 个脚本 24 处）
- ``call:label`` 无空格（call-1.bat、汉字横排变竖排---转置.bat）
"""

from __future__ import annotations


def test_rem_with_punctuation_is_comment(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nREM.-- Prepare\nrem.(c) 2024\nrem normal\necho ok\n")
    bash_check(out)
    assert "# .-- Prepare" in out
    assert "# .(c) 2024" in out
    assert "# normal" in out
    assert "REM.--" not in out


def test_rem_word_prefix_stays_command(convert_bat):
    out, _ = convert_bat("@echo off\nremsomething\necho ok\n")
    assert "remsomething" in out.splitlines()
    assert "# remsomething" not in out


def test_goto_eof_without_space_exits(convert_bat, bash_check, bash_run):
    out, _ = convert_bat("@echo off\necho before\ngoto:eof\necho after\n")
    bash_check(out)
    assert "exit 0" in out
    proc = bash_run(out)
    assert proc.returncode == 0
    assert proc.stdout == "before\n"


def test_goto_eof_in_sequential_chain(convert_bat, bash_check, bash_run):
    out, _ = convert_bat("@echo off\necho.&goto:eof\necho after\n")
    bash_check(out)
    assert "exit 0" in out
    proc = bash_run(out)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_call_label_without_space_calls_function(convert_bat, bash_check, bash_run):
    out, report = convert_bat(
        "@echo off\ncall:say hi\ngoto:eof\n:say\necho called-%1\n"
    )
    bash_check(out)
    assert "label_say hi" in out
    assert "label_say() {" in out
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0
    assert proc.stdout == "called-hi\n"


def test_unparsable_call_is_todo_not_dropped(convert_bat):
    out, report = convert_bat("@echo off\ncall\necho after\n")
    assert "# TODO: 手动检查: call" in out
    assert report.todo_count == 1
    assert "after" in out
