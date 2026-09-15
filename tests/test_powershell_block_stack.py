"""统一块栈加固的回归测试（v1.6.0 阶段 A）。

覆盖：未登记大括号开启符的 comment 降级、同行平衡不误触发、
try 体内嵌 comment 容器的边界自洽。
"""

from __future__ import annotations

import re


def _uncommented(out: str) -> list[str]:
    return [
        line for line in out.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _leaked(out: str, keyword: str) -> list[str]:
    pattern = re.compile(rf"(?i)^\s*{keyword}\b")
    return [line for line in _uncommented(out) if pattern.match(line)]


def test_net_open_assignment_degrades_to_comment(convert_ps, bash_check):
    out, report = convert_ps(
        '$serverConfig = [ordered]@{\n'
        '    "web01" = @{ IP = "10.0.1.10" }\n'
        '    "db01" = @{ IP = "10.0.1.20" }\n'
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not [line for line in _uncommented(out) if "@{" in line]
    assert "# TODO: 手动检查: $serverConfig = [ordered]@{" in out
    assert '"web01" = @{ IP = "10.0.1.10" }' in out
    bash_check(out)


def test_unregistered_brace_opener_degrades_to_comment(convert_ps, bash_check):
    out, report = convert_ps('customBlock {\n    Write-Host "body"\n}\nWrite-Host "marker"\n')
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert "# customBlock {" not in out
    assert "# TODO: 手动检查: customBlock {" in out
    assert 'echo "marker"' in out
    assert "# echo" not in out
    bash_check(out)


def test_inline_balanced_where_object_not_swallowed(convert_ps, bash_check):
    out, _ = convert_ps(
        'Get-Process | Where-Object { $_.CPU -gt 10 }\nWrite-Host "marker"\n'
    )
    assert 'echo "marker"' in out
    bash_check(out)


def test_inline_balanced_switch_arm_not_swallowed(convert_ps, bash_check):
    out, report = convert_ps('$x = 1\n"dev" { Write-Host "x" }\nWrite-Host "marker"\n')
    assert 'echo "marker"' in out
    assert not any("无法识别的块结构" in d.message for d in report.todos)
    bash_check(out)


def test_inline_balanced_script_block_not_swallowed(convert_ps, bash_check):
    out, report = convert_ps(
        'Register-ObjectEvent -Action { Write-Host "hi" }\nWrite-Host "marker"\n'
    )
    assert 'echo "marker"' in out
    assert not any("无法识别的块结构" in d.message for d in report.todos)
    bash_check(out)


def test_brace_inside_string_not_triggered(convert_ps, bash_check):
    out, report = convert_ps('Write-Host "use { placeholder"\nWrite-Host "marker"\n')
    assert 'echo "use { placeholder"' in out
    assert 'echo "marker"' in out
    assert not any("无法识别的块结构" in d.message for d in report.todos)
    bash_check(out)


def test_bare_open_brace_keeps_existing_behavior(convert_ps):
    _, report = convert_ps('{\n  Write-Host "x"\n}\n')
    assert not any("无法识别的块结构" in d.message for d in report.todos)


def test_try_body_with_net_open_container_keeps_structure(convert_ps, bash_check):
    out, report = convert_ps(
        "try {\n"
        "    $h = @{\n"
        "        a = 1\n"
        "    }\n"
        '    Get-Item "/tmp/a"\n'
        "}\n"
        "catch {\n"
        '    Write-Host "err"\n'
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not _leaked(out, "catch")
    assert 'ls -la "/tmp/a"' in out
    assert 'echo "err"' in out
    bash_check(out)
