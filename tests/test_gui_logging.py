"""GUI 诊断输出重定向测试（P0：GUI 终端输出泄漏）。

GUI 模式（``run_gui``）下进程的 stdout/stderr 必须落到 XDG state 日志，
不得向启动它的终端输出任何内容。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_PYTHON = Path(__file__).resolve().parents[1] / "python"
_STATE_CLEAN = ("XDG_STATE_HOME", "XDG_CONFIG_HOME")


def _gui_env(tmp_path: Path) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items() if key not in _STATE_CLEAN
    }
    env["PYTHONPATH"] = str(REPO_PYTHON)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def test_gui_log_path_follows_xdg_state_home(tmp_path, monkeypatch):
    from bat2sh.gui.app import gui_log_path

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert gui_log_path() == tmp_path / "state" / "bat2sh" / "gui.log"


def test_install_gui_logging_redirects_stdout_and_stderr(tmp_path):
    script = (
        "import sys\n"
        "from bat2sh.gui.app import install_gui_logging\n"
        "install_gui_logging()\n"
        "print('stdout-marker')\n"
        "sys.stderr.write('stderr-marker\\n')\n"
        "sys.stderr.flush()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=_gui_env(tmp_path),
        timeout=60,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""
    text = (tmp_path / "state" / "bat2sh" / "gui.log").read_text(encoding="utf-8")
    assert "stdout-marker" in text
    assert "stderr-marker" in text


def test_install_gui_logging_truncates_oversized_log(tmp_path):
    from bat2sh.gui.app import MAX_LOG_BYTES

    log = tmp_path / "state" / "bat2sh" / "gui.log"
    log.parent.mkdir(parents=True)
    log.write_text("x" * (MAX_LOG_BYTES + 1), encoding="utf-8")

    script = (
        "from bat2sh.gui.app import install_gui_logging\n"
        "install_gui_logging()\n"
        "print('after-truncate')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=_gui_env(tmp_path),
        timeout=60,
    )
    assert proc.returncode == 0
    assert log.stat().st_size < MAX_LOG_BYTES
    assert "after-truncate" in log.read_text(encoding="utf-8")


def test_gui_startup_emits_nothing_to_terminal(tmp_path):
    """真实入口启动 GUI：stdout/stderr 零输出，诊断只进日志。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "bat2sh"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_gui_env(tmp_path),
    )
    try:
        time.sleep(2.5)
        assert proc.poll() is None, "GUI 启动失败或提前退出"
    finally:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=15)
    assert stdout == b""
    assert stderr == b""
    assert (tmp_path / "state" / "bat2sh" / "gui.log").exists()
