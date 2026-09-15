"""RHS 类型转换剥离与赋值内 switch 的回归测试（v1.6.0 阶段 A / Fix 114）。"""

from __future__ import annotations

import re


def _uncommented(out: str) -> list[str]:
    return [
        line for line in out.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_version_typecast_rhs_stripped(convert_ps, bash_check):
    out, report = convert_ps('$minVersion = [version]"2.0.0"\n')
    assert report.error_count == 0
    assert 'minVersion="2.0.0"' in out
    assert not _uncommented(out) or all("[version]" not in line for line in _uncommented(out))
    bash_check(out)


def test_version_var_cast_stripped(convert_ps, bash_check):
    out, _ = convert_ps('$currentVersion = [version]$Version\n')
    assert "[version]" not in out
    bash_check(out)


def test_int_typecast_rhs_stripped(convert_ps, bash_check):
    out, _ = convert_ps('$x = [int]"5"\n')
    assert "[int]" not in out
    assert 'x="5"' in out
    bash_check(out)


def test_dotnet_static_not_stripped(convert_ps):
    out, report = convert_ps("$y = [math]::Round(1.5)\n")
    assert "# TODO: 手动检查: $y = [math]::Round(1.5)" in out
    assert any(".NET 类型静态调用" in d.message for d in report.todos)


def test_switch_in_assignment_arms_not_raw(convert_ps, bash_check):
    out, report = convert_ps(
        "$action = switch ($Environment.ToLower()) {\n"
        '    "dev"     { "Deploy to DEV" }\n'
        '    "staging" { "Deploy to STAGING" }\n'
        '    default   { "Unknown" }\n'
        "}\n"
        'Write-Host "after"\n'
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    raw_arms = [
        line for line in _uncommented(out)
        if re.match(r'^\s*"(dev|staging)"', line)
    ]
    assert raw_arms == []
    assert 'echo "after"' in out
    bash_check(out)


def test_typecast_strip_warns(convert_ps):
    _, report = convert_ps('$minVersion = [version]"2.0.0"\n')
    assert any("右值类型转换" in d.message for d in report.warnings)
