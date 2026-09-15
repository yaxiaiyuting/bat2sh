"""v1.8.0 D5：PowerShell 未赋值变量展开为空串，bash `set -u` 下不得中止。

策略：仅顶层直线赋值视为「必定已赋值」（发射 `${x}`）；其余（未赋值、分支/块内赋值）
保守发射 `${x:-}`，与 PowerShell「未定义即空」语义一致，且不触发 unbound。
"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_top_level_assignment_keeps_plain_ref(convert_ps, bash_check):
    out, _ = convert_ps('$path = "/tmp"\nWrite-Host "$path"\n', bash_check=False)
    bash_check(out)
    assert 'echo "${path}"' in out
    assert "${path:-}" not in out


def test_unassigned_variable_uses_default(convert_ps, bash_check):
    out, _ = convert_ps('Write-Host "at $path here"\n', bash_check=False)
    bash_check(out)
    assert "${path:-}" in out


def test_function_param_keeps_plain_ref(convert_ps, bash_check):
    out, _ = convert_ps(
        "function F { param([string]$IP)\n    Write-Host \"$IP\"\n}\n", bash_check=False
    )
    bash_check(out)
    assert 'echo "${IP}"' in out


def test_foreach_variable_keeps_plain_ref(convert_ps, bash_check):
    out, _ = convert_ps(
        'foreach ($f in $files) {\n    Write-Host "$f"\n}\n', bash_check=False
    )
    bash_check(out)
    assert 'echo "${f}"' in out


def test_branch_assigned_variable_uses_default(convert_ps, bash_check):
    out, _ = convert_ps(
        "if ($x) {\n    $path = 'a'\n} else {\n    $path = 'b'\n}\nWrite-Host \"$path\"\n",
        bash_check=False,
    )
    bash_check(out)
    assert "${path:-}" in out


def test_unassigned_does_not_abort_under_set_u(convert_ps, bash_run):
    out, _ = convert_ps(
        'if (-not (Test-Path "$path")) {\n    Write-Host "Folder at $path missing"\n}\n',
        bash_check=False,
    )
    proc = bash_run(out)
    assert "unbound variable" not in proc.stderr
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("name", ["cd-home.ps1", "cd-root.ps1", "check-bios.ps1"])
def test_real_corpus_no_unbound_variable(bash_check, name):
    from bat2sh.core.encoding import decode_bytes
    from bat2sh.core.engine import convert_text
    from bat2sh.core.settings import ConvertSettings
    from bat2sh.core.types import SourceKind

    decoded = decode_bytes((CORPUS / name).read_bytes(), None)
    out, report = convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(bash_check=False), name
    )
    assert report.error_count == 0, name
    bash_check(out)
    assert "${path:-}" in out or "${model:-}" in out
