"""安装检测映射的回归测试（v1.6.0 阶段 B / Fix B-P4）。"""

from __future__ import annotations

import subprocess

UNINSTALL_APP = (
    r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Notepad++"
)
UNINSTALL_ROOT = r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash"], input=script, capture_output=True, text=True)


def test_uninstall_app_maps_to_package_query(convert_ps, bash_check):
    out, report = convert_ps(
        f'Get-ItemProperty -Path "{UNINSTALL_APP}" -Name DisplayName\n'
    )
    assert "dpkg-query" in out and "rpm -q" in out and "pacman -Q" in out
    assert "Notepad++" in out
    assert report.error_count == 0
    bash_check(out)


def test_uninstall_enumerate_lists_packages(convert_ps, bash_check):
    out, _ = convert_ps(f'Get-ChildItem -Path "{UNINSTALL_ROOT}"\n')
    assert "dpkg-query -W" in out and "rpm -qa" in out and "pacman -Q" in out
    bash_check(out)


def test_batch_reg_query_app_maps(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\n'
        'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Notepad++"\n'
    )
    assert "pacman -Q" in out
    assert report.error_count == 0
    bash_check(out)


def test_wow6432node_variant_maps(convert_ps, bash_check):
    out, _ = convert_ps(
        'Get-ItemProperty -Path '
        '"HKLM:\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Foo" '
        "-Name DisplayName\n"
    )
    assert "pacman -Q" in out and "Foo" in out
    bash_check(out)


def test_package_warning_recorded(convert_ps):
    _, report = convert_ps(f'Get-ItemProperty -Path "{UNINSTALL_APP}" -Name DisplayName\n')
    assert any(d.category == "registry" and "包管理器" in d.message for d in report.warnings)


def test_package_query_sandbox_runs(convert_ps):
    out, _ = convert_ps(f'Get-ItemProperty -Path "{UNINSTALL_APP}" -Name DisplayName\n')
    proc = _run(out)
    assert proc.returncode == 0
    assert proc.stdout.strip()
