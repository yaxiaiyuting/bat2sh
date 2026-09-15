"""硬件信息读取映射的回归测试（v1.6.0 阶段 B / Fix B-P3）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

BIOS_KEY = r"HKLM:\HARDWARE\DESCRIPTION\System\BIOS"
SYS_VENDOR_FILE = Path("/sys/class/dmi/id/sys_vendor")


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash"], input=script, capture_output=True, text=True)


def test_bios_system_manufacturer_maps_to_dmi(convert_ps, bash_check):
    out, report = convert_ps(
        f'Get-ItemProperty -Path "{BIOS_KEY}" -Name SystemManufacturer\n'
    )
    assert "/sys/class/dmi/id/sys_vendor" in out
    assert report.error_count == 0
    bash_check(out)


def test_bios_product_name_maps(convert_ps, bash_check):
    out, _ = convert_ps(f'Get-ItemProperty -Path "{BIOS_KEY}" -Name SystemProductName\n')
    assert "/sys/class/dmi/id/product_name" in out
    bash_check(out)


def test_batch_reg_query_bios_maps(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nreg query "HKLM\\HARDWARE\\DESCRIPTION\\System\\BIOS" /v SystemManufacturer\n'
    )
    assert "/sys/class/dmi/id/sys_vendor" in out
    assert report.error_count == 0
    bash_check(out)


def test_bios_unknown_value_still_todo(convert_ps, bash_check):
    out, _ = convert_ps(f'Get-ItemProperty -Path "{BIOS_KEY}" -Name SomethingElse\n')
    assert "dmi" not in out
    assert "# TODO[REG] op=read" in out
    bash_check(out)


def test_bios_warning_recorded(convert_ps):
    _, report = convert_ps(
        f'Get-ItemProperty -Path "{BIOS_KEY}" -Name SystemManufacturer\n'
    )
    assert any(d.category == "registry" and "dmi" in d.message for d in report.warnings)


def test_bios_sandbox_runs(convert_ps):
    out, _ = convert_ps(
        f'Get-ItemProperty -Path "{BIOS_KEY}" -Name SystemManufacturer\n'
    )
    proc = _run(out)
    assert proc.returncode == 0
    if SYS_VENDOR_FILE.exists():
        assert proc.stdout.strip() == SYS_VENDOR_FILE.read_text(encoding="utf-8").strip()
