"""文件关联读取映射的回归测试（v1.6.0 阶段 B / Fix B-P5）。"""

from __future__ import annotations

import subprocess


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash"], input=script, capture_output=True, text=True)


def test_hkcr_extension_maps_to_xdg_mime(convert_ps, bash_check):
    out, report = convert_ps('Get-ItemProperty -Path "HKCR:\\.txt"\n')
    assert "xdg-mime query default" in out
    assert ".txt" in out
    assert report.error_count == 0
    bash_check(out)


def test_hklm_classes_extension_maps(convert_ps, bash_check):
    out, _ = convert_ps('Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Classes\\.png"\n')
    assert "xdg-mime query default" in out
    assert ".png" in out
    bash_check(out)


def test_batch_reg_query_extension_maps(convert_bat, bash_check):
    out, report = convert_bat('@echo off\nreg query "HKCR\\.pdf"\n')
    assert "xdg-mime query default" in out
    assert report.error_count == 0
    bash_check(out)


def test_non_extension_hkcr_key_still_todo(convert_ps, bash_check):
    out, _ = convert_ps('Get-ItemProperty -Path "HKCR:\\Folder"\n')
    assert "xdg-mime" not in out
    assert "# TODO[REG] op=read" in out
    bash_check(out)


def test_mime_warning_recorded(convert_ps):
    _, report = convert_ps('Get-ItemProperty -Path "HKCR:\\.txt"\n')
    assert any(d.category == "registry" and "xdg-mime" in d.message for d in report.warnings)


def test_mime_sandbox_runs(convert_ps):
    out, _ = convert_ps('Get-ItemProperty -Path "HKCR:\\.txt"\n')
    proc = _run(out)
    assert proc.returncode == 0
