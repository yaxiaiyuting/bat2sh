"""前向 goto 的不可达区间：v2.4.0 注释子集（opt-out）与 v2.5.0 状态机（默认）。

cmd 语义：无条件 ``goto :X`` 跳过的区间在 cmd 中**不执行**。

- **v2.5.0 默认**：CFG 标签分派状态机接管（``pc`` 分派），前向跳转真正跳过区间。
- **opt-out**（``cfg_state_machine=False``）：v2.4.0 的可达性证明 + 区间显式注释。

任一模式下运行语义都必须与 cmd 一致；边界（可达标签 / call 目标 / 重复标签）在 opt-out
模式下保留诚实 TODO。
"""

from __future__ import annotations

OPT_OUT = {"cfg_state_machine": False}


def test_forward_skip_region_not_executed(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    bash_check(out)
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["live"]


def test_forward_skip_multiline_region_not_executed(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho a\necho b\n:X\necho live\n")
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_reachable_label_inside_region_blocks_conversion(convert_bat, bash_check):
    text = "@echo off\ngoto :X\n:L\necho inner\n:X\necho live\ncall :L\n:L0\ngoto :eof\n"
    out, report = convert_bat(text)
    bash_check(out)
    assert "# TODO: 手动检查: goto :X" in out
    assert "# [不可达] echo inner" not in out


def test_call_target_inside_region_blocks_conversion(convert_bat, bash_check):
    text = "@echo off\ngoto :X\ncall :SUB\ngoto :eof\n:SUB\necho sub\ngoto :eof\n:X\necho live\n"
    out, _ = convert_bat(text)
    bash_check(out)
    assert "# TODO: 手动检查: goto :X" in out
    assert "# [不可达]" not in out


def test_conditional_goto_state_machine(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\nif 1==1 goto :X\necho maybe\n:X\necho live\n")
    bash_check(out)
    assert report.todo_count == 0
    assert "__bat2sh_pc" in out
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_in_block_goto_state_machine(convert_bat, bash_check, bash_run):
    out, report = convert_bat(
        "@echo off\nif 1==1 (\ngoto :X\necho dead\n)\n:X\necho live\n"
    )
    bash_check(out)
    assert report.todo_count == 0
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_duplicate_target_label_blocks_conversion(convert_bat, bash_check):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho one\n:X\necho two\n")
    bash_check(out)
    assert report.todo_count == 1
    assert "# [不可达]" not in out


def test_forward_skip_has_no_loss_warning(convert_bat):
    _, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    assert [w for w in report.warnings if w.category == "loss"] == []


def test_forward_skip_region_is_comment_only(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    assert not any(
        line.strip() and not line.lstrip().startswith("#")
        for line in out.splitlines()
        if "dead" in line and "__bat2sh_pc" not in line and "echo" not in line
    )
    assert "dead" not in bash_run(out).stdout


# --- opt-out：v2.4.0 可达性注释子集 --------------------------------------


def test_optout_forward_skip_region_commented(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n", **OPT_OUT)
    bash_check(out)
    assert report.todo_count == 0
    assert "# [不可达] echo dead" in out
    assert bash_run(out).stdout.splitlines() == ["live"]


def test_optout_conditional_goto_kept_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nif 1==1 goto :X\necho maybe\n:X\necho live\n", **OPT_OUT)
    bash_check(out)
    assert report.todo_count == 1
    assert "# [不可达]" not in out


def test_optout_in_block_goto_kept_todo(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nif 1==1 (\ngoto :X\necho dead\n)\n:X\necho live\n", **OPT_OUT
    )
    bash_check(out)
    assert report.todo_count == 1
    assert "# [不可达]" not in out


def test_optout_multiline_region_all_commented(convert_bat, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho a\necho b\n:X\necho live\n", **OPT_OUT)
    assert report.todo_count == 0
    assert out.count("# [不可达]") == 2
    assert bash_run(out).stdout.splitlines() == ["live"]
