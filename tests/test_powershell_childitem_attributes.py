"""v1.8.0 D7：`Get-ChildItem -attributes Directory/!Directory` 过滤语义必须区分。

旧行为：两种过滤都转成同一个 glob，`$files` 与 `$folders` 内容相同（静默错误）。
新行为：`Directory` -> find -type d；`!Directory` -> find -type f。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"


def test_directory_filter_uses_type_d(convert_ps, bash_check):
    out, report = convert_ps(
        '$folders = Get-ChildItem "/tmp" -attributes Directory\n', bash_check=False
    )
    assert report.error_count == 0
    bash_check(out)
    assert "-type d" in out
    assert "folders=(" in out


def test_not_directory_filter_uses_type_f(convert_ps, bash_check):
    out, _ = convert_ps(
        '$files = Get-ChildItem "/tmp" -attributes !Directory\n', bash_check=False
    )
    bash_check(out)
    assert "-type f" in out


def test_filters_differ(convert_ps):
    out, _ = convert_ps(
        '$f = Get-ChildItem "/p" -attributes Directory\n'
        '$g = Get-ChildItem "/p" -attributes !Directory\n',
        bash_check=False,
    )
    assert "-type d" in out and "-type f" in out


def test_unsupported_attributes_falls_back_with_warning(convert_ps):
    out, report = convert_ps(
        '$x = Get-ChildItem "/p" -attributes Hidden\n', bash_check=False
    )
    assert report.error_count == 0
    assert any("无法可靠映射" in d.message for d in report.warnings)


def test_real_corpus_attributes_runtime(tmp_path, bash_check):
    from bat2sh.core.encoding import decode_bytes
    from bat2sh.core.engine import convert_text
    from bat2sh.core.settings import ConvertSettings
    from bat2sh.core.types import SourceKind

    (tmp_path / "file1.txt").write_text("a", encoding="utf-8")
    (tmp_path / "dir1").mkdir()
    decoded = decode_bytes((CORPUS / "cd-desktop.ps1").read_bytes(), None)
    out, report = convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(bash_check=False), "cd-desktop.ps1"
    )
    assert report.error_count == 0
    bash_check(out)
    assert "-type d" in out or "-type f" in out
