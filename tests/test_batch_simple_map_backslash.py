"""v1.8.3 047：简单映射命令（md 等）未做反斜杠转换，致 `\\"` 转义收尾引号。

语料依据（docs/v1.8.3-attribution.md [047]）：
- ``多功能系统优化设置.cmd:151`` ``md "%select%:\\Personal\\Temp\\">nul``
  → 产物 ``mkdir -p "${select}:\\Personal\\Temp\\"``，结尾 `\\"` 转义引号 → 多行合并。
"""

from __future__ import annotations


def test_md_backslash_absolute_converted(convert_bat, bash_check):
    out, _ = convert_bat(
        '@echo off\nset select=D\nmd "%select%:\\Personal\\Temp\\">nul 2>nul\n'
    )
    bash_check(out)
    assert 'mkdir -p "${select}:/Personal/Temp/"' in out
    assert "\\Personal" not in out


def test_md_relative_backslash_converted(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nmd out\\sub\n")
    bash_check(out)
    assert "mkdir -p out/sub" in out


def test_ren_plain_args_unaffected(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nren a.txt b.txt\n")
    bash_check(out)
    assert "mv a.txt b.txt" in out


def test_echo_content_still_backslash_converted(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\necho C:\\Windows\\x\n")
    bash_check(out)
    assert 'echo "C:/Windows/x"' in out
