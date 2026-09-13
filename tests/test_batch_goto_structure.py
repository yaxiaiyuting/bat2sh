"""顶层 goto 目标标签不函数化：主流程保持线性，不再被吞进未调用函数。"""

from __future__ import annotations

MINIMAL_REPRO = (
    "@echo off\n"
    "echo before\n"
    "goto :SKIP\n"
    "echo dead\n"
    ":SKIP\n"
    "echo skipped\n"
    "echo after\n"
)


def test_goto_target_label_not_functionized(convert_bat, bash_check):
    out, _ = convert_bat(MINIMAL_REPRO)
    bash_check(out)
    assert "label_SKIP" not in out
    assert "# :SKIP（goto 目标，不函数化，主流程继续）" in out


def test_main_flow_order_matches_source(convert_bat, bash_run):
    out, _ = convert_bat(MINIMAL_REPRO)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["before", "dead", "skipped", "after"]


def test_structure_positions_are_linear(convert_bat):
    out, _ = convert_bat(MINIMAL_REPRO)
    assert (
        out.index('echo "before"')
        < out.index('echo "dead"')
        < out.index('echo "skipped"')
        < out.index('echo "after"')
    )


def test_pure_call_target_still_functionized(convert_bat):
    out, _ = convert_bat("@echo off\ncall :SUB\ngoto :eof\n:SUB\necho sub\ngoto :eof\n")
    assert "label_SUB() {" in out
    assert "\nlabel_SUB\n" in out


def test_mixed_call_and_goto_targets(convert_bat, bash_check, bash_run):
    text = (
        "@echo off\n"
        "echo start\n"
        "call :SUB\n"
        "goto :END\n"
        ":SUB\n"
        "echo sub\n"
        "exit /b\n"
        ":END\n"
        "echo end\n"
    )
    out, _ = convert_bat(text)
    bash_check(out)
    assert "label_SUB() {" in out
    assert "label_END" not in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["start", "sub", "end"]


def test_label_both_call_and_goto_is_functionized(convert_bat):
    out, _ = convert_bat(
        "@echo off\ncall :BOTH\ngoto :BOTH\n:BOTH\necho both\ngoto :eof\n"
    )
    assert "label_BOTH() {" in out


def test_unreferenced_label_keeps_function_behavior(convert_bat):
    text = "@echo off\ncall :A\ngoto :eof\n:A\necho a\n:B\necho b\ngoto :eof\n"
    out, _ = convert_bat(text)
    assert "label_B() {" in out


def test_goto_target_inside_function_returns_to_main_flow(convert_bat, bash_check):
    text = (
        "@echo off\n"
        "call :SUB\n"
        "goto :END\n"
        ":SUB\n"
        "echo sub\n"
        "goto :MID\n"
        "echo skipped-in-sub\n"
        ":MID\n"
        "echo mid\n"
        "exit /b\n"
        ":END\n"
        "echo end\n"
    )
    out, _ = convert_bat(text)
    bash_check(out)
    assert "label_MID" not in out


def test_stress_shape_keeps_post_skip_code_in_main_flow(convert_bat, bash_check):
    text = (
        "@echo off\n"
        "echo module1\n"
        "goto :SKIP\n"
        "echo unreachable\n"
        ":SKIP\n"
        "echo module5\n"
        "call :SUB\n"
        "goto :eof\n"
        ":SUB\n"
        "echo sub\n"
        "goto :eof\n"
    )
    out, _ = convert_bat(text)
    bash_check(out)
    assert "label_SKIP" not in out
    assert out.index('echo "module1"') < out.index('echo "module5"')
    assert "label_SUB() {" in out


def test_dead_code_warning_after_goto(convert_bat):
    out, _ = convert_bat("@echo off\ngoto :SKIP\necho dead\n:SKIP\necho done\n")
    assert "# 注意：以下代码原被 goto :SKIP 跳过，在 bash 中会执行，请核对" in out
    assert out.index("# TODO: 手动检查: goto :SKIP") < out.index("# 注意：")


def test_no_warning_when_target_immediately_follows(convert_bat):
    out, _ = convert_bat("@echo off\ngoto :SKIP\n:SKIP\necho done\n")
    assert "# 注意：" not in out


def test_multiple_goto_targets_warn_independently(convert_bat):
    text = "@echo off\ngoto :A\necho deadA\n:A\ngoto :B\necho deadB\n:B\necho done\n"
    out, _ = convert_bat(text)
    assert "# 注意：以下代码原被 goto :A 跳过" in out
    assert "# 注意：以下代码原被 goto :B 跳过" in out
    assert out.count("# 注意：") == 2


def test_warning_not_emitted_past_target_label(convert_bat):
    text = "@echo off\ngoto :A\n:A\necho done\ngoto :B\n:B\necho end\n"
    out, _ = convert_bat(text)
    assert "# 注意：" not in out


def test_warning_is_comment_only(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\ngoto :SKIP\necho dead\n:SKIP\necho done\n")
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["dead", "done"]
