"""CLI stdout/stderr 分流回归测试（subprocess 捕获真实管道）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_PYTHON = Path(__file__).resolve().parents[1] / "python"
BAT = "@echo off\necho hello\n"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_PYTHON)}
    return subprocess.run(
        [sys.executable, "-m", "bat2sh", "--cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def make_bat(tmp_path: Path) -> Path:
    path = tmp_path / "demo.bat"
    path.write_text(BAT, encoding="utf-8")
    return path


def test_report_json_stdout_is_pure_json(tmp_path):
    proc = run_cli(str(make_bat(tmp_path)), "--report-json")
    assert proc.returncode == 0
    assert proc.stdout.startswith("{")
    data = json.loads(proc.stdout)
    assert data["source"] == "demo.bat"


def test_report_json_status_on_stderr(tmp_path):
    proc = run_cli(str(make_bat(tmp_path)), "--report-json")
    assert "[已写出]" in proc.stderr
    assert "[已写出]" not in proc.stdout


def test_print_stdout_is_only_script(tmp_path):
    proc = run_cli(str(make_bat(tmp_path)), "--print")
    assert proc.returncode == 0
    assert proc.stdout.startswith("#!/usr/bin/env bash")
    assert "[已写出]" not in proc.stdout


def test_human_mode_status_on_stderr(tmp_path):
    proc = run_cli(str(make_bat(tmp_path)))
    assert proc.returncode == 0
    assert "[已写出]" in proc.stderr
    assert proc.stdout == ""
