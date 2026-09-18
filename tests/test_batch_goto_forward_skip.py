"""v2.4.0 Stage B：前向 goto 的不可达区间处理。

cmd 语义：无条件 ``goto :X`` 跳过的区间在 cmd 中**不执行**。旧行为把该区间原样发射
（bash 里会执行），仅以 TODO + 告警暴露；本版在**可达性证明**成立时把区间显式注释。

可达性证明（保守前置）：区间内每个标签的 goto 入边为 0 且非 ``call`` 目标 → 除
「goto 行 fall-through」（被 goto 阻断）外无路径进入区间 → 区间不可达。
任一前置不成立（可达标签 / 条件 goto / 块内 goto / 重复标签）则**不转换**，保留诚实 TODO。
"""

from __future__ import annotations


def test_forward_skip_region_not_executed(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho dead\n:X\necho live\n")
    bash_check(out)
    assert report.todo_count == 0
    assert "# [不可达] echo dead" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["live"]


def test_forward_skip_multiline_region_all_commented(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\ngoto :X\necho a\necho b\n:X\necho live\n")
    bash_check(out)
    assert report.todo_count == 0
    assert out.count("# [不可达]") == 2
    proc = bash_run(out)
    assert proc.stdout.splitlines() == ["live"]


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


def test_conditional_goto_not_converted(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nif 1==1 goto :X\necho maybe\n:X\necho live\n")
    bash_check(out)
    assert report.todo_count == 1
    assert "# [不可达]" not in out


def test_in_block_goto_not_converted(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nif 1==1 (\ngoto :X\necho dead\n)\n:X\necho live\n"
    )
    bash_check(out)
    assert report.todo_count == 1
    assert "# [不可达]" not in out


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
        if "dead" in line
    )
    proc = bash_run(out)
    assert "dead" not in proc.stdout
