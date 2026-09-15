"""v1.8.0 D3：本文件函数调用（赋值 RHS 与条件）必须转换为 bash 调用。

旧行为：`$v = Foo` 被当作字符串赋成 `v="Foo"`；`if (Foo $x)` 退化为占位。
新行为：赋值走命令替换 `v=$(Foo)`；条件直接用命令退出码 `if Foo "$x"; then`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_function_call_as_assignment_rhs(convert_ps, bash_run):
    out, report = convert_ps(
        'function Foo { return "x" }\n$v = Foo\nWrite-Host "$v"\n', bash_check=False
    )
    assert report.error_count == 0
    assert "v=$(Foo)" in out
    assert 'v="Foo"' not in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "x" in proc.stdout


def test_unknown_identifier_stays_string(convert_ps):
    out, _ = convert_ps("$v = SomeUnknownWord\n", bash_check=False)
    assert 'v="SomeUnknownWord"' in out
    assert "$(" not in out


def test_function_call_in_condition_uses_exit_status(convert_ps, bash_check):
    out, report = convert_ps(
        "function IsOk { param([string]$s)\n"
        '    if ($s -eq "yes") { return $true } else { return $false }\n'
        "}\n"
        "if (IsOk $value) { Write-Host 'ok' } else { Write-Host 'no' }\n",
        bash_check=False,
    )
    assert report.error_count == 0
    bash_check(out)
    assert "if IsOk " in out
    assert "本文件函数" not in "".join(d.message for d in report.todos)


def test_function_call_in_negated_condition(convert_ps, bash_check):
    out, _ = convert_ps(
        "function IsOk { return $true }\nif (-not (IsOk)) { Write-Host 'no' }\n",
        bash_check=False,
    )
    bash_check(out)
    assert "if ! IsOk" in out


@pytest.mark.parametrize(
    ("name", "needle"),
    [
        ("cd-temp.ps1", "path=$(GetTempDir)"),
        ("check-ipv4-address.ps1", "if IsIPv4AddressValid"),
        ("cd-logs.ps1", "$(GetLogsDir)"),
    ],
)
def test_real_corpus_function_call_converted(name, needle):
    from bat2sh.core.encoding import decode_bytes
    from bat2sh.core.engine import convert_text
    from bat2sh.core.settings import ConvertSettings
    from bat2sh.core.types import SourceKind

    decoded = decode_bytes((CORPUS / name).read_bytes(), None)
    out, report = convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(bash_check=False), name
    )
    assert report.error_count == 0, name
    assert needle in out, name
