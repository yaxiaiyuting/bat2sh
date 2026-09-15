"""系统状态/重启检测映射的回归测试（v1.6.0 阶段 B / Fix B-P0）。"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REBOOT_KEY = (
    r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion"
    r"\WindowsUpdate\Auto Update\RebootRequired"
)
PENDING_KEY = (
    r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion"
    r"\Component Based Servicing\RebootPending"
)


def _stub_path(tmp_path: Path, rc: int) -> str:
    bin_dir = tmp_path / f"bin{rc}"
    bin_dir.mkdir()
    stub = bin_dir / "needs-restarting"
    stub.write_text(f"#!/bin/sh\nexit {rc}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _run(script: str, path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash"], input=script, capture_output=True, text=True,
        env={**os.environ, "PATH": path},
    )


def test_reboot_required_condition_uses_probe(convert_ps, bash_check):
    out, report = convert_ps(f'if (Test-Path "{REBOOT_KEY}") {{ Write-Host "reboot" }}\n')
    assert "/var/run/reboot-required" in out
    assert '[[ -e "HKLM' not in out
    assert report.error_count == 0
    bash_check(out)


def test_reboot_pending_assignment_uses_probe(convert_ps, bash_check):
    out, _ = convert_ps(f'$pending = Test-Path "{PENDING_KEY}"\n')
    assert "/var/run/reboot-required" in out
    assert "pending=$(" in out
    bash_check(out)


def test_session_manager_test_uses_probe(convert_ps, bash_check):
    out, _ = convert_ps(
        'Test-Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager"\n'
    )
    assert "/var/run/reboot-required" in out
    bash_check(out)


def test_unknown_key_still_structured_todo(convert_ps, bash_check):
    out, report = convert_ps(
        'Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"\n'
    )
    assert "# TODO[REG] op=test" in out
    assert "/var/run/reboot-required" not in out
    assert report.todo_count == 1
    bash_check(out)


def test_reboot_probe_warning_recorded(convert_ps):
    _, report = convert_ps(f'$x = Test-Path "{REBOOT_KEY}"\n')
    assert any(
        d.category == "registry" and "重启检测" in d.message for d in report.warnings
    )


def test_reboot_probe_sandbox_true(convert_ps, tmp_path):
    out, _ = convert_ps(f'if (Test-Path "{REBOOT_KEY}") {{ Write-Host "reboot" }}\n')
    proc = _run(out, _stub_path(tmp_path, rc=1))
    assert proc.returncode == 0
    assert "reboot" in proc.stdout


def test_reboot_probe_sandbox_false(convert_ps, tmp_path):
    out, _ = convert_ps(f'if (Test-Path "{REBOOT_KEY}") {{ Write-Host "reboot" }}\n')
    proc = _run(out, _stub_path(tmp_path, rc=0))
    assert proc.returncode == 0
    assert "reboot" not in proc.stdout
