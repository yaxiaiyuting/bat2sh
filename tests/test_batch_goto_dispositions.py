"""v2.4.0：C4 台账 7 主形态 + 1 辅形态的**处置由测试锁定**（实现 / 诚实 TODO）。

目标 = 语义完整性（每形态有明确归属），而非翻转数。已实现形态断言「真实转换」；
未实现形态断言「保留响亮诚实 TODO / error」，防止回归为静默行为。
"""

from __future__ import annotations

# --- 已实现 ---------------------------------------------------------------


def test_eof_exit_implemented(convert_bat):
    out, report = convert_bat("@echo off\ngoto :eof\n")
    assert "exit 0" in out
    assert report.todo_count == 0


def test_redundant_goto_implemented_as_noop(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\n:X\necho live\n")
    assert "（冗余跳转" in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_forward_skip_unreachable_region_implemented(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    assert "# [不可达] echo dead" in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


# --- 诚实 TODO（未实现，显式归属） ----------------------------------------


def test_backward_loop_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\n:Top\necho loop\ngoto Top\n")
    bash_check(out)
    assert "# TODO: 手动检查: goto Top" in out
    assert report.todo_count == 1


def test_in_block_goto_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nfor %%i in (a) do (\ngoto :OUT\n)\n:OUT\necho x\n")
    bash_check(out)
    assert "# TODO: 手动检查: goto :OUT" in out
    assert report.todo_count == 1


def test_missing_label_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\ngoto :NOWHERE\necho x\n")
    bash_check(out)
    assert "# TODO: 手动检查: goto :NOWHERE" in out
    assert report.todo_count == 1


def test_dynamic_target_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nset L=x\ngoto :%L%\n:x\necho x\n")
    bash_check(out)
    assert "# TODO: 手动检查: goto :%L%" in out
    assert report.todo_count == 1


def test_label_in_block_is_error_layer(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nif 1==1 (\n:DEEP\necho d\n)\n")
    bash_check(out)
    assert report.error_count == 1
    assert "位于控制块内" in out
