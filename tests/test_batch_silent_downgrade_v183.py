"""v1.8.3 退回条目降级：085 / 053 由「静默错」改为诚实 TODO。

依据 docs/v1.8.3-design.md §5：
- 085 ``for /f`` 解析 ipconfig **英文标签 “ip address”** —— Linux ip addr 无该关键词、
  列位不同（``tokens=15``），静态不可靠 → 诚实 TODO。
  （**不触碰** 已有 ``_FINDSTR_CJK_MAP`` 覆盖的 ``findstr "IPv4"`` 等情形。）
- 053 ``%%i`` **逸出 for 循环**（块结构失同步）→ 原样发射 `cat %i` 坏命令 → 诚实 TODO。
  （**不触碰** 循环内「tokens 未声明」的 warn-only 情形。）
"""

from __future__ import annotations


def test_ipconfig_forf_english_label_becomes_todo(convert_bat):
    out, report = convert_bat(
        '@echo off\n'
        'for /f "tokens=15" %%i in (\'ipconfig ^| find /i "ip address"\') do set ip=%%i\n'
        "echo %ip%\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count >= 1


def test_ipconfig_forf_cjk_mapping_unchanged(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        'for /f "tokens=2 delims=:" %%a in (\'ipconfig ^| findstr /i "IPv4"\') do echo %%a\n'
    )
    assert report.todo_count == 0
    assert "grep" in out


def test_loop_var_leak_outside_loop_becomes_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        "for /f %%i in ('dir/b *.bat') do if %%i==a (echo x) else (if %%i==b (echo y) else (\n"
        "set/a a+=1\n"
        "type %%i>>t.txt\n"
        "))\n"
    )
    assert "# TODO: 手动检查: type %%i>>t.txt" in out
    assert "cat %i" not in out


def test_undeclared_token_still_warns_not_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=1\" %%a in ('dir /b') do echo %%a %%b\n"
    )
    assert any("tokens 未声明" in d.message for d in report.warnings)
    assert report.todo_count == 0
