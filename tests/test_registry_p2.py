"""系统版本读取映射的回归测试（v1.6.0 阶段 B / Fix B-P2）。"""

from __future__ import annotations

import subprocess

CURRENT_VERSION_KEY = r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash"], input=script, capture_output=True, text=True)


def test_product_name_maps_to_os_release(convert_ps, bash_check):
    out, report = convert_ps(
        f'Get-ItemProperty -Path "{CURRENT_VERSION_KEY}" -Name ProductName\n'
    )
    assert "/etc/os-release" in out
    assert "PRETTY_NAME" in out
    assert report.error_count == 0
    bash_check(out)


def test_current_version_maps_to_version_id(convert_ps, bash_check):
    out, _ = convert_ps(
        f'Get-ItemProperty -Path "{CURRENT_VERSION_KEY}" -Name CurrentVersion\n'
    )
    assert "VERSION_ID" in out
    bash_check(out)


def test_batch_reg_query_product_name_maps(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nreg query "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion" /v ProductName\n'
    )
    assert "/etc/os-release" in out
    assert report.error_count == 0
    bash_check(out)


def test_unknown_value_still_structured_todo(convert_ps, bash_check):
    out, report = convert_ps(
        f'Get-ItemProperty -Path "{CURRENT_VERSION_KEY}" -Name SomethingElse\n'
    )
    assert "os-release" not in out
    assert "# TODO[REG] op=read" in out
    assert report.todo_count == 1
    bash_check(out)


def test_os_release_warning_recorded(convert_ps):
    _, report = convert_ps(
        f'Get-ItemProperty -Path "{CURRENT_VERSION_KEY}" -Name ProductName\n'
    )
    assert any(d.category == "registry" and "os-release" in d.message for d in report.warnings)


def test_os_release_sandbox_runs(convert_ps):
    out, _ = convert_ps(
        f'Get-ItemProperty -Path "{CURRENT_VERSION_KEY}" -Name ProductName\n'
    )
    proc = _run(out)
    assert proc.returncode == 0
    assert proc.stdout.strip()
