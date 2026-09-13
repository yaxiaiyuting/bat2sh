"""CLI --run 自动执行测试：TODO 防护、确认、超时与退出码。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from bat2sh.cli import main

CLEAN_BAT = "@echo off\necho marker>ran.txt\n"
TODO_BAT = (
    "@echo off\n"
    'for /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
    "echo marker>ran.txt\n"
)
SLEEP_BAT = "@echo off\ntimeout /t 2 /nobreak >nul\necho late\n"
EXIT7_BAT = "@echo off\necho hi>r7.txt\nexit /b 7\n"


def make_bat(tmp_path: Path, text: str, name: str = "demo.bat") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class _NonTtyStdin:
    def isatty(self) -> bool:
        return False


class _FakeTtyStdin:
    def __init__(self, reply: str):
        self.reply = reply

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        return self.reply


def test_run_todo_rejected_exit_4(tmp_path, capfd):
    path = make_bat(tmp_path, TODO_BAT)
    code = main([str(path), "--run"])
    captured = capfd.readouterr()
    assert code == 4
    assert "TODO" in captured.err
    assert "for /f" in captured.err
    assert captured.out == ""
    assert not (tmp_path / "ran.txt").exists()


def test_run_todo_with_force_executes_without_yes(tmp_path, capfd):
    path = make_bat(tmp_path, TODO_BAT)
    code = main([str(path), "--run", "--force"])
    assert code == 0
    assert (tmp_path / "ran.txt").is_file()
    assert capfd.readouterr().out.startswith("#!/usr/bin/env bash")


def test_run_clean_with_yes_executes(tmp_path, capfd):
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run", "--yes"])
    captured = capfd.readouterr()
    assert code == 0
    assert (tmp_path / "ran.txt").is_file()
    assert captured.out.startswith("#!/usr/bin/env bash")


def test_run_non_tty_without_yes_refuses_exit_1(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(sys, "stdin", _NonTtyStdin())
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run"])
    assert code == 1
    assert "非交互环境" in capfd.readouterr().err
    assert not (tmp_path / "ran.txt").exists()


def test_run_tty_accept_executes(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(sys, "stdin", _FakeTtyStdin("y\n"))
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run"])
    assert code == 0
    assert "将执行以上脚本，继续？" in capfd.readouterr().err
    assert (tmp_path / "ran.txt").is_file()


def test_run_tty_decline_exit_1(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(sys, "stdin", _FakeTtyStdin("\n"))
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run"])
    assert code == 1
    assert "已取消执行" in capfd.readouterr().err
    assert not (tmp_path / "ran.txt").exists()


def test_run_timeout_exit_5(tmp_path, capfd):
    path = make_bat(tmp_path, SLEEP_BAT)
    started = time.monotonic()
    code = main([str(path), "--run", "--yes", "--run-timeout", "1"])
    elapsed = time.monotonic() - started
    assert code == 5
    assert "超时" in capfd.readouterr().err
    assert elapsed < 1.9


def test_run_cwd_controls_working_directory(tmp_path, capfd):
    path = make_bat(tmp_path, CLEAN_BAT)
    workdir = tmp_path / "work"
    workdir.mkdir()
    code = main([str(path), "--run", "--yes", "--run-cwd", str(workdir)])
    assert code == 0
    assert (workdir / "ran.txt").is_file()
    assert not (tmp_path / "ran.txt").exists()


def test_run_missing_cwd_exit_2(tmp_path, capfd):
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run", "--yes", "--run-cwd", str(tmp_path / "nope")])
    assert code == 2
    assert "工作目录不存在" in capfd.readouterr().err


def test_run_propagates_script_exit_code(tmp_path):
    path = make_bat(tmp_path, EXIT7_BAT)
    assert main([str(path), "--run", "--yes"]) == 7
    assert (tmp_path / "r7.txt").is_file()


def test_run_bash_missing_exit_5(tmp_path, monkeypatch, capfd):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    path = make_bat(tmp_path, CLEAN_BAT)
    code = main([str(path), "--run", "--yes"])
    assert code == 5
    assert "无法启动 bash" in capfd.readouterr().err


def test_run_rejects_multiple_inputs(tmp_path, capfd):
    first = make_bat(tmp_path, CLEAN_BAT, "a.bat")
    second = make_bat(tmp_path, CLEAN_BAT, "b.bat")
    code = main([str(first), str(second), "--run", "--yes"])
    assert code == 1
    assert "仅支持单个输入文件" in capfd.readouterr().err
