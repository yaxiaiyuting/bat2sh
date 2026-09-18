"""C4 台账 7 主形态 + 1 辅形态的**处置由测试锁定**（实现 / 诚实 TODO）。

目标 = 语义完整性（每形态有明确归属），而非翻转数。

- **v2.5.0 默认**：`redundant_goto` / `forward_skip` / `backward_loop` / `in_block_goto` /
  `eof_exit` 由 CFG 标签分派状态机（`core/cfg_state.py`）真实转换。
- **opt-out**（`cfg_state_machine=False`）：`redundant_goto` / `forward_skip` 退回 v2.4.0 子集，
  其余退回诚实 TODO。
- `missing_label` / `dynamic_target` / `label_in_block`：无静态安全映射 / error 层，维持响亮处置。
"""

from __future__ import annotations

OPT_OUT = {"cfg_state_machine": False}


# --- 已实现（v2.5.0 状态机，默认） ----------------------------------------


def test_eof_exit_implemented(convert_bat):
    out, report = convert_bat("@echo off\ngoto :eof\n")
    assert "exit 0" in out
    assert report.todo_count == 0


def test_redundant_goto_state_machine(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\n:X\necho live\n")
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_forward_skip_unreachable_region_state_machine(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    assert report.todo_count == 0
    assert "__bat2sh_pc" in out
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_backward_loop_state_machine(convert_bat, bash_check, bash_run):
    text = "@echo off\nset n=\n:Top\nset n=%n%x\necho %n%\nif not \"%n%\"==\"xxx\" goto Top\n"
    out, report = convert_bat(text)
    bash_check(out)
    assert report.todo_count == 0
    assert "__bat2sh_pc" in out
    assert bash_run(out).stdout.splitlines() == ["x", "xx", "xxx"]


def test_in_block_goto_state_machine(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\nfor %%i in (a) do (\ngoto :OUT\n)\n:OUT\necho x\n")
    bash_check(out)
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["x"]


# --- opt-out：v2.4.0 子集 / 诚实 TODO -------------------------------------


def test_optout_redundant_goto_noop(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\n:X\necho live\n", **OPT_OUT)
    assert "（冗余跳转" in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_optout_forward_skip_region_commented(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n", **OPT_OUT)
    assert "# [不可达] echo dead" in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_optout_backward_loop_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\n:Top\necho loop\ngoto Top\n", **OPT_OUT)
    bash_check(out)
    assert "# TODO: 手动检查: goto Top" in out
    assert report.todo_count == 1


def test_optout_in_block_goto_is_honest_todo(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor %%i in (a) do (\ngoto :OUT\n)\n:OUT\necho x\n", **OPT_OUT
    )
    bash_check(out)
    assert "# TODO: 手动检查: goto :OUT" in out
    assert report.todo_count == 1


# --- 无静态安全映射（维持） -----------------------------------------------


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
