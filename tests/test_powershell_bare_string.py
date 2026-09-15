"""v1.8.0 D2：独立字符串语句必须转 echo（不得原样透传成被执行的命令）。"""

from __future__ import annotations

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_bare_string_plain_becomes_echo(convert_ps, bash_check):
    out, report = convert_ps('"hello world"\n', bash_check=False)
    assert report.error_count == 0
    bash_check(out)
    assert 'echo "hello world"' in out


def test_bare_string_with_interpolation(convert_ps, bash_run):
    out, _ = convert_ps('$path = "/tmp"\n"📂$path entered"\n', bash_check=False)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "📂/tmp entered" in proc.stdout


def test_bare_single_quoted_is_literal(convert_ps, bash_run):
    out, _ = convert_ps("$x = 7\n'literal $x'\n", bash_check=False)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "literal $x" in proc.stdout


def test_bare_string_with_unconvertible_subexpression_is_todo(convert_ps):
    out, report = convert_ps('"has $($files.Count) files"\n', bash_check=False)
    assert report.error_count == 0
    assert "# TODO" in out
    assert "echo" not in out


def test_non_string_statement_not_turned_into_echo(convert_ps):
    out, _ = convert_ps("foo \"bar\"\n", bash_check=False)
    assert "echo" not in out


@pytest.mark.parametrize("name", ["cd-up.ps1", "cd-up2.ps1", "cd-up3.ps1", "cd-up4.ps1"])
def test_real_corpus_bare_string_runs(bash_check, name):
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
    assert 'echo "📂' in out
