"""v1.8.0 D6：`+=` 复合赋值必须保留基值（旧行为覆盖为 `=`）。"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_string_append_keeps_base(convert_ps, bash_run):
    out, report = convert_ps(
        '$s = "a"\n$s += "b"\nWrite-Host "$s"\n', bash_check=False
    )
    assert report.error_count == 0
    assert 's+="b"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "ab" in proc.stdout


def test_numeric_append(convert_ps, bash_run):
    out, _ = convert_ps("$n = 1\n$n += 2\nWrite-Host \"$n\"\n", bash_check=False)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "3" in proc.stdout


def test_plain_assignment_not_rewritten(convert_ps):
    out, _ = convert_ps('$s = "a"\n', bash_check=False)
    assert "s+=" not in out


@pytest.mark.parametrize(
    ("name", "needle"),
    [("cd-crashdumps.ps1", 'path+="\\AppData'), ("check-apps.ps1", 'reply+=", ')],
)
def test_real_corpus_append(name, needle):
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
