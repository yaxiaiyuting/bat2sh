"""控制块内 goto 标签的回归测试：不得生成函数定义/破坏块结构。"""

from __future__ import annotations

FUNCTION_MODE_REPRO = (
    "@echo off\n"
    "call :MAIN\n"
    "goto :eof\n"
    ":MAIN\n"
    "if 1==1 (\n"
    "goto :SKIP\n"
    ":SKIP\n"
    "echo done\n"
    ")\n"
    "goto :eof\n"
)


def test_label_in_if_block_does_not_break_structure(convert_bat, bash_check):
    out, report = convert_bat(FUNCTION_MODE_REPRO)
    bash_check(out)
    assert "label_SKIP" not in out
    assert "位于控制块内" in out
    assert report.error_count == 1
    # 同脚本内 goto :SKIP 跨函数跳转仍单独记为 TODO
    assert report.todo_count == 1
    assert not any("多余" in d.message for d in report.warnings)
    assert not any("未正常闭合" in d.message for d in report.warnings)


def test_plain_label_in_if_block_without_function_mode(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nif 1==1 (\ngoto :SKIP\n:SKIP\necho done\n)\n")
    bash_check(out)
    assert "label_SKIP" not in out
    assert "位于控制块内" in out


def test_label_in_for_block(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nfor %%i in (a b) do (\n:INNER\necho %%i\n)\n")
    bash_check(out)
    assert "label_INNER" not in out
    assert "位于控制块内" in out


def test_label_in_nested_blocks(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nif 1==1 (\nif 2==2 (\n:DEEP\necho deep\n)\n)\n")
    bash_check(out)
    assert "label_DEEP" not in out
    assert out.count("fi") >= 2


def test_top_level_label_still_becomes_function(convert_bat):
    text = "@echo off\ncall :SUB\ngoto :eof\n:SUB\necho sub\ngoto :eof\n"
    out, _ = convert_bat(text)
    assert "label_SUB() {" in out
    assert "标签位于控制块内" not in out


def test_mixed_top_level_and_block_labels(convert_bat, bash_check):
    text = (
        "@echo off\ncall :SUB\ngoto :eof\n"
        ":SUB\nif 1==1 (\n:INNER\necho inner\n)\ngoto :eof\n"
    )
    out, _ = convert_bat(text)
    bash_check(out)
    assert "label_SUB() {" in out
    assert "label_INNER" not in out


def test_comment_only_if_body_is_not_empty(convert_bat, bash_check):
    text = "@echo off\nset /a COUNT=0\nif %COUNT% lss 3 goto :LOOP_START\n"
    out, _ = convert_bat(text)
    bash_check(out)
    assert 'if [ "${COUNT}" -lt 3 ]; then' in out


def test_comment_only_for_body_is_not_empty(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nfor %%i in (a) do (\ngoto :DONE\n)\n")
    bash_check(out)


def test_comment_only_else_body_is_not_empty(convert_bat, bash_check):
    text = "@echo off\nif 1==1 (\necho a\n) else (\ngoto :X\n)\n"
    out, _ = convert_bat(text)
    bash_check(out)


def test_empty_function_body_is_not_empty(convert_bat, bash_check):
    text = "@echo off\ncall :A\ngoto :eof\n:A\n:B\necho done\ngoto :eof\n"
    out, _ = convert_bat(text)
    bash_check(out)


def test_unclosed_paren_autocloses_inside_function(convert_bat, bash_check):
    text = "@echo off\ncall :MAIN\ngoto :eof\n:MAIN\nif 1==1 (\necho no-close\n"
    out, report = convert_bat(text)
    bash_check(out)
    assert any("未正常闭合" in d.message for d in report.warnings)


def test_backtick_inside_double_quotes_escaped(convert_bat, bash_check, bash_run):
    out, _ = convert_bat("@echo off\necho \"混合'引号`测试\"\n")
    bash_check(out)
    proc = bash_run(out)
    assert "混合'引号`测试" in proc.stdout
