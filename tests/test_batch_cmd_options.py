"""v1.8.3 062①：`cmd /q /c "…"` 因正则漏匹配而丢失参数（产出裸 `bash`）。

语料依据（docs/v1.8.3-attribution.md [062]）：
- ``批处理生成的CMD命令帮助清单.bat:24`` ``cmd /q /c "%%i/?"``
  → 旧产物裸 `bash`（`/q` 使 `^/c\\s+` 不匹配）。
仅修 ①（参数保留）；② 未闭合引号留 backlog（响亮失败，非静默）。
"""

from __future__ import annotations


def test_cmd_with_flags_before_c_keeps_command(convert_bat, bash_check):
    out, report = convert_bat('@echo off\ncmd /q /c "dir /?"\n')
    bash_check(out)
    assert 'bash -c "dir /?"' in out
    assert report.todo_count == 0


def test_cmd_c_plain_unchanged(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\ncmd /c "echo hi"\n')
    bash_check(out)
    assert 'bash -c "echo hi"' in out


def test_cmd_k_still_flags_interactive(convert_bat):
    out, report = convert_bat("@echo off\ncmd /k\n")
    assert "bash" in out
    assert report.warning_count >= 1
