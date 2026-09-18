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


def test_forward_skip_region_does_not_execute(convert_bat, bash_run):
    # cmd 语义：goto :SKIP 跳过 echo dead；产物必须同样不执行（原先会执行）。
    out, _ = convert_bat(MINIMAL_REPRO)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["before", "skipped", "after"]


def test_structure_positions_are_linear(convert_bat):
    out, _ = convert_bat(MINIMAL_REPRO)
    assert (
        out.index('echo "before"')
        < out.index("echo dead")
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


def test_forward_skip_region_is_explicitly_commented(convert_bat):
    out, _ = convert_bat("@echo off\ngoto :SKIP\necho dead\n:SKIP\necho done\n")
    assert "# TODO: 手动检查: goto :SKIP" not in out
    assert "# goto SKIP（前向跳转" in out
    assert "# [不可达] echo dead" in out
    assert out.index("# goto SKIP（前向跳转") < out.index("# [不可达] echo dead")


def test_no_warning_when_target_immediately_follows(convert_bat):
    out, _ = convert_bat("@echo off\ngoto :SKIP\n:SKIP\necho done\n")
    assert "# 注意：" not in out


def test_multiple_forward_skip_regions_commented_independently(convert_bat):
    text = "@echo off\ngoto :A\necho deadA\n:A\ngoto :B\necho deadB\n:B\necho done\n"
    out, _ = convert_bat(text)
    assert "# [不可达] echo deadA" in out
    assert "# [不可达] echo deadB" in out
    assert out.count("# [不可达]") == 2
    assert "# TODO: 手动检查" not in out


def test_no_dead_region_when_target_immediately_follows(convert_bat):
    text = "@echo off\ngoto :A\n:A\necho done\ngoto :B\n:B\necho end\n"
    out, _ = convert_bat(text)
    assert "# 注意：" not in out
    assert "# [不可达]" not in out


def test_forward_skip_region_is_comment_only(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\ngoto :SKIP\necho dead\n:SKIP\necho done\n")
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["done"]
