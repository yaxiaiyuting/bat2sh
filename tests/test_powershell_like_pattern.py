"""v1.8.0 D4：`-like` 通配模式含空格必须转义（引号会关闭 bash 通配）。

旧行为：`[[ $x == *-generic * ]]` 被拆成两个词 → bash 语法错误。
新行为：空白转义为 `[[ $x == *-generic\\ * ]]`，通配语义保留。
"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_like_pattern_with_space_is_escaped(convert_ps, bash_check):
    out, report = convert_ps(
        'if ($Name -like "*-generic *") { Write-Host "match" }\n', bash_check=False
    )
    assert report.error_count == 0
    bash_check(out)
    assert "*-generic\\ *" in out


def test_like_pattern_without_space_unchanged(convert_ps, bash_check):
    out, _ = convert_ps('if ($Name -like "*.txt") { Write-Host "match" }\n', bash_check=False)
    bash_check(out)
    assert "*.txt" in out
    assert "\\ " not in out


def test_notlike_with_space_is_escaped(convert_ps, bash_check):
    out, _ = convert_ps(
        'if ($Name -notlike "*-generic *") { Write-Host "match" }\n', bash_check=False
    )
    bash_check(out)
    assert "*-generic\\ *" in out


def test_like_pattern_runtime_match(convert_ps, bash_run):
    out, _ = convert_ps(
        '$Name = "linux-generic 6.1"\n'
        'if ($Name -like "*-generic *") { Write-Host "MATCHED" } else { Write-Host "NOPE" }\n',
        bash_check=False,
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "MATCHED" in proc.stdout


@pytest.mark.parametrize("name", ["check-cpu.ps1"])
def test_real_corpus_like_pattern(bash_check, name):
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
    assert "*-generic\\ *" in out
