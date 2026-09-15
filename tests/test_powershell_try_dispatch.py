"""try/catch/finally 独立行与多臂派发的回归测试（v1.6.0 阶段 A / Fix 109）。"""

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


def test_multi_arm_try_degrades_to_comment(convert_ps, bash_check):
    out, report = convert_ps(
        "try {\n"
        "    Write-Verbose \"attempt\"\n"
        "    $result = & $Action\n"
        "}\n"
        "catch [System.IO.FileNotFoundException] {\n"
        '    Write-Warning "not found"\n'
        "}\n"
        "catch [System.UnauthorizedAccessException] {\n"
        '    Write-Error "denied"\n'
        "}\n"
        "catch {\n"
        '    Write-Error "unexpected"\n'
        "}\n"
        "finally {\n"
        '    Write-Debug "done"\n'
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    for keyword in ("catch", "finally"):
        assert not _leaked(out, keyword)
    assert "# TODO: 手动检查: try {" in out
    assert 'Write-Warning "not found"' in out
    assert 'Write-Debug "done"' in out
    bash_check(out)


def test_typed_try_degrades_to_comment(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    risky\n} catch [System.IO.IOException] {\n    Write-Host "io"\n}\n'
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not _leaked(out, "catch")
    assert "# TODO: 手动检查: try {" in out
    bash_check(out)


def test_standalone_catch_lines_routed(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n}\ncatch {\n    Write-Host "err"\n}\n'
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not _leaked(out, "catch")
    assert 'ls -la "/tmp/a"' in out
    assert 'echo "err"' in out
    bash_check(out)


def test_standalone_finally_routed(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n}\ncatch {\n    Write-Host "err"\n}\n'
        'finally {\n    Write-Host "done"\n}\n'
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not _leaked(out, "finally")
    assert "if true; then  # TODO: finally 块总是执行" in out
    assert 'echo "done"' in out
    bash_check(out)


def test_nested_try_outer_catch_preserved(convert_ps, bash_check):
    out, report = convert_ps(
        "try {\n"
        '    Get-Item "/tmp/a"\n'
        "    try {\n"
        '        Get-Item "/tmp/b"\n'
        "    } catch {\n"
        '        Write-Host "inner catch"\n'
        "    }\n"
        "} catch {\n"
        '    Write-Host "outer catch"\n'
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert 'echo "outer catch"' in out
    assert not _leaked(out, "catch")
    bash_check(out)


def test_standalone_else_degrades_safely(convert_ps, bash_check):
    out, report = convert_ps(
        'if ($a) {\n    Write-Host "a"\n}\nelse {\n    Write-Host "b"\n}\n'
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not _leaked(out, "else")
    bash_check(out)


def test_standalone_elseif_no_dangling_elif(convert_ps, bash_check):
    out, report = convert_ps(
        'if ($a) {\n    Write-Host "a"\n}\nelseif ($b) {\n    Write-Host "b"\n}\n'
    )
    assert report.error_count == 0
    assert not _leaked(out, "elif")
    bash_check(out)
