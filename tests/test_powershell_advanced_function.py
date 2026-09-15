"""高级函数 begin/process/end 生命周期块的回归测试（v1.6.0 阶段 A / Fix 111）。"""

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


def test_advanced_function_begin_process_end(convert_ps, bash_check):
    out, report = convert_ps(
        "function Get-Report {\n"
        "    param([string[]]$ComputerName)\n"
        "    begin {\n"
        "        $all = @()\n"
        "    }\n"
        "    process {\n"
        "        foreach ($computer in $ComputerName) {\n"
        '            Write-Host "Processing: $computer"\n'
        "        }\n"
        "    }\n"
        "    end {\n"
        '        Write-Host "Report complete"\n'
        "    }\n"
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    for keyword in ("begin", "process", "end"):
        assert not _leaked(out, keyword)
    assert "# begin 块" in out
    assert "# process 块" in out
    assert "# end 块" in out
    assert "for computer in ${ComputerName}; do" in out
    assert 'echo "Report complete"' in out
    bash_check(out)


def test_advanced_function_braces_balanced(convert_ps):
    out, _ = convert_ps(
        "function f {\n"
        "    begin {\n"
        "        $x = 1\n"
        "    }\n"
        "    process {\n"
        '        Write-Host "p"\n'
        "    }\n"
        "    end {\n"
        '        Write-Host "e"\n'
        "    }\n"
        "}\n"
    )
    assert out.count("{") == out.count("}")
    assert "多余的 }" not in out


def test_phase_emits_warning(convert_ps):
    _, report = convert_ps('process {\n    Write-Host "x"\n}\n')
    assert any(
        "管道生命周期块" in d.message and d.category == "control_flow"
        for d in report.warnings
    )


def test_inline_phase_block(convert_ps, bash_check):
    out, report = convert_ps('process { Write-Host "x" }\n')
    assert report.error_count == 0
    assert "# process 块" in out
    assert 'echo "x"' in out
    assert not _leaked(out, "process")
    bash_check(out)


def test_end_without_brace_not_treated_as_phase(convert_ps):
    out, _ = convert_ps("end\n")
    assert "管道阶段" not in out
    assert "管道生命周期块" not in out
