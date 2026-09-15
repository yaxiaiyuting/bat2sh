"""v1.8.1：bat 行级防线（未知命令元字符、二进制载荷、说明文本）。"""

from __future__ import annotations


def test_unknown_command_with_parens_degrades(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nsomeunknowncmd (a) b\n", bash_check=False)
    assert report.error_count == 0
    bash_check(out)
    assert "# TODO: 手动检查: someunknowncmd (a) b" in out


def test_keep_command_with_parens_degrades(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ncode by author (note)\n", bash_check=False)
    bash_check(out)
    assert "# TODO" in out


def test_quoted_parens_still_pass_through(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\necho "(a) b"\n', bash_check=False)
    bash_check(out)
    assert 'echo "(a) b"' in out


def test_binary_line_is_commented(convert_bat, bash_check):
    out, report = convert_bat("@echo off\n\x01\x02 binary\x03 payload\n", bash_check=False)
    assert report.error_count == 0
    bash_check(out)
    assert "# " in out


def test_latin1_garbage_is_commented(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\n\xc3\x9d3\xc3\x80\xc3\x80t3\xc3\x92\xc3\x90\n", bash_check=False)
    bash_check(out)
    assert "# " in out


def test_cjk_free_text_is_commented(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\n另外一种更简洁高效的方案：\n", bash_check=False)
    bash_check(out)
    assert out.strip().endswith("方案：") or "另外一种" in out
    assert "# 另外一种" in out


def test_normal_cjk_echo_not_commented(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\necho 你好世界\n', bash_check=False)
    bash_check(out)
    assert 'echo "你好世界"' in out or "echo 你好世界" in out
