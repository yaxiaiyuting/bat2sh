"""Fixer 层测试：M1/M3/M4 扫描、M2/M5/M6 排除、对齐、payload 边界、替换与 diff。

部分用例直接使用转换器真实输出（回归 §1.3 六形态 / §1.4 四类定位障碍）。
"""

from __future__ import annotations

import pytest

from bat2sh.core.api import fixer
from bat2sh.core.types import ConvertReport, Diagnostic

M1_BAT = '@echo off\nfor /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
M4_BAT = '@echo off\nif /i "a*b"=="c" echo yes\n'
M2_BAT = '@echo off\ndir /b | findstr /i "foo" | sort /r > out.txt\n'
M3_PS = 'if ($LASTEXITCODE -ne 0) { Write-Host "x" }\n[System.IO.File]::ReadAllText("a")\n'
DEGRADE_PS = "function f { [CmdletBinding()] param([string]$p) Write-Output $p }\nf\n"

M6_LINE = "# TODO: 生成脚本未通过 bash -n 语法检查，已降级为注释"
M5_LINE = "# 带有 # TODO 标记的行无法自动转换，请人工检查"


def test_scan_m1_line_marker_with_alignment(convert_bat):
    text, report = convert_bat(M1_BAT)
    markers = fixer.scan_todo_markers(text, report)
    assert len(markers) == 1
    marker = markers[0]
    assert marker.kind == "line"
    assert marker.original.startswith("for /f")
    assert marker.source_line == 2
    assert marker.category == "control_flow"
    assert not marker.ambiguous


def test_scan_m4_indented_condition_marker(convert_bat):
    text, report = convert_bat(M4_BAT)
    markers = fixer.scan_todo_markers(text, report)
    assert len(markers) == 1
    assert markers[0].kind == "line"
    assert markers[0].original == '"a*b"=="c" echo yes'
    assert markers[0].source_line == 2
    assert markers[0].category == "control_flow"


def test_scan_m3_inline_marker(convert_ps):
    text, report = convert_ps(M3_PS, last_exit_code="warn")
    markers = fixer.scan_todo_markers(text, report)
    inline = [m for m in markers if m.kind == "inline"]
    assert len(inline) == 1
    assert inline[0].line_text.startswith("if [[ false ]]; then")
    assert inline[0].original == ""


def test_scan_m2_excluded(convert_bat):
    text, report = convert_bat(M2_BAT)
    assert "# TODO: 复杂管道需手动重写" in text
    assert fixer.scan_todo_markers(text, report) == []


def test_scan_m5_excluded(convert_bat):
    text, report = convert_bat(M1_BAT)
    assert M5_LINE in text
    assert all("带有 # TODO" not in m.line_text for m in fixer.scan_todo_markers(text, report))


def test_scan_degraded_returns_empty(convert_ps):
    text, report = convert_ps(DEGRADE_PS)
    assert fixer.is_degraded(report)
    assert M6_LINE in text
    assert fixer.scan_todo_markers(text, report) == []


def test_scan_m6_line_only_returns_empty():
    text = M6_LINE + "\n# # TODO: 手动检查: leftover\n"
    assert fixer.scan_todo_markers(text, None) == []


def test_scan_alignment_ambiguous_flag():
    text = "# TODO: 手动检查: same cmd\n"
    report = ConvertReport(
        todos=[
            Diagnostic(3, "手动检查: same cmd", "same cmd", "command"),
            Diagnostic(7, "手动检查: same cmd", "same cmd", "pipeline"),
        ]
    )
    marker = fixer.scan_todo_markers(text, report)[0]
    assert marker.ambiguous
    assert marker.source_line == 3
    assert marker.category == "command"


def test_scan_alignment_missing_diagnostic():
    text = "# TODO: 手动检查: orphan\n"
    report = ConvertReport(todos=[Diagnostic(3, "x", "other", "command")])
    marker = fixer.scan_todo_markers(text, report)[0]
    assert marker.source_line == 0
    assert marker.original == "orphan"


def test_scan_error_layer_aligned():
    text = "# TODO: 手动检查: risky\n"
    report = ConvertReport(errors=[Diagnostic(9, "必须人工处理: risky", "risky", "command")])
    marker = fixer.scan_todo_markers(text, report)[0]
    assert marker.source_line == 9
    assert marker.category == "command"
    assert marker.diagnostic_message.startswith("必须人工处理")


def _synthetic_marker(line_no: int, text: str, report=None):
    markers = fixer.scan_todo_markers(text, report)
    return next(m for m in markers if m.out_line == line_no)


def test_build_prompt_marks_target_and_redacts_other_todos():
    output = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "# TODO: 手动检查: cmd-a",
            "# TODO: 手动检查: cmd-b",
            "echo hi",
        ]
    )
    marker = _synthetic_marker(3, output)
    prompt = fixer.build_prompt(marker, "", "demo.bat", output, context_lines=2)
    assert ">>> # TODO: 手动检查: cmd-a" in prompt
    assert "cmd-b" not in prompt
    assert "（其它待人工检查项，已省略）" in prompt
    assert "Bash 输出第 3 行" in prompt


def test_build_prompt_source_context_bounded():
    source = "\n".join(f"SRC-{i}" for i in range(1, 41))
    output = "\n".join(["# TODO: 手动检查: cmd-a", "echo hi", "echo ho"])
    marker = _synthetic_marker(1, output)
    marker.source_line = 20
    marker.category = "command"
    prompt = fixer.build_prompt(marker, source, "demo.bat", output, context_lines=3)
    assert "SRC-17" in prompt and "SRC-23" in prompt
    assert "SRC-1\n" not in prompt
    assert "SRC-40" not in prompt
    assert "第 17-23 行" in prompt


def test_build_prompt_context_lines_zero_only_target():
    source = "\n".join(f"SRC-{i}" for i in range(1, 11))
    output = "# TODO: 手动检查: cmd-a\necho hi"
    marker = _synthetic_marker(1, output)
    marker.source_line = 5
    prompt = fixer.build_prompt(marker, source, "demo.bat", output, context_lines=0)
    assert "SRC-5" in prompt
    assert "SRC-4" not in prompt
    assert "SRC-6" not in prompt


def test_build_prompt_reports_aligned_metadata():
    text = "# TODO: 手动检查: risky\n"
    report = ConvertReport(
        errors=[Diagnostic(9, "必须人工处理: risky（说明）", "risky", "command")]
    )
    marker = fixer.scan_todo_markers(text, report)[0]
    prompt = fixer.build_prompt(marker, "", "demo.ps1", text, context_lines=3)
    assert "源文件第 9 行" in prompt
    assert "分类: command" in prompt
    assert "必须人工处理: risky（说明）" in prompt


def test_clean_completion_variants():
    assert fixer.clean_completion("") == ""
    assert fixer.clean_completion("\n\n  \n") == ""
    assert fixer.clean_completion(None) == ""
    assert fixer.clean_completion("echo a") == "echo a"
    assert fixer.clean_completion("```bash\necho a\necho b\n```") == "echo a\necho b"
    assert fixer.clean_completion("```\necho a\n```") == "echo a"
    assert fixer.clean_completion("\n```sh\necho a\n```\n\n") == "echo a"
    assert fixer.clean_completion("echo a\r\necho b\r\n") == "echo a\necho b"
    assert fixer.clean_completion("  echo spaced  ") == "  echo spaced"


def test_apply_replacement_preserves_indent_and_newline():
    text = "#!/usr/bin/env bash\nif true; then\n    # TODO: 手动检查条件: x\nfi\n"
    result = fixer.apply_replacement(text, 3, 'echo "ok"')
    assert result == '#!/usr/bin/env bash\nif true; then\n    echo "ok"\nfi\n'


def test_apply_replacement_multiline_keeps_common_strip():
    text = "a\n    # TODO: 手动检查: x\nb\n"
    replacement = 'if [ -f x ]; then\n    echo "found"\nfi'
    result = fixer.apply_replacement(text, 2, replacement)
    assert result == 'a\n    if [ -f x ]; then\n        echo "found"\n    fi\nb\n'
    assert fixer.replacement_line_count(replacement) == 3


def test_apply_replacement_no_trailing_newline_preserved():
    text = "# TODO: 手动检查: x"
    result = fixer.apply_replacement(text, 1, "echo done")
    assert result == "echo done"


def test_apply_replacement_out_of_range_raises():
    with pytest.raises(ValueError):
        fixer.apply_replacement("a\nb\n", 9, "x")
    with pytest.raises(ValueError):
        fixer.apply_replacement("a\nb\n", 0, "x")


def test_render_diff_shows_change_and_empty_when_same():
    old = "a\n# TODO: 手动检查: x\nc\n"
    new = "a\necho fixed\nc\n"
    diff = fixer.render_diff(old, new)
    assert "-# TODO: 手动检查: x" in diff
    assert "+echo fixed" in diff
    assert fixer.render_diff(old, old) == ""


def test_count_markers(convert_bat, convert_ps):
    text, report = convert_bat(M1_BAT, last_exit_code="warn")
    assert fixer.count_markers(text, report) == 1
    text2, report2 = convert_ps(M3_PS, last_exit_code="warn")
    assert fixer.count_markers(text2, report2) == 2
