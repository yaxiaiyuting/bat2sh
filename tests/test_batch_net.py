"""``net user <name> /delete`` → 幂等 ``userdel`` 的回归测试（v1.11.0）。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    return subprocess.run([bash], input=text, capture_output=True, text=True)


def test_net_user_delete_maps_to_guarded_userdel(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nnet user 123 /delete\n")
    assert report.todo_count == 0
    assert "if id -u 123 >/dev/null 2>&1; then userdel 123; fi" in out
    bash_check(out)


def test_net_user_delete_is_noop_for_absent_user(convert_bat):
    out, _ = convert_bat("@echo off\nnet user 123 /delete\n")
    proc = _run(out)
    assert proc.returncode == 0, proc.stderr


def test_net_user_add_stays_todo(convert_bat):
    out, report = convert_bat("@echo off\nnet user 123 /add\n")
    assert report.todo_count == 1
    assert "userdel" not in out


def test_net_other_subcommands_stay_todo(convert_bat):
    for line in ("net start spooler", "net share x=C:\\d", "net user", "net localgroup g u /add"):
        out, report = convert_bat(f"@echo off\n{line}\n")
        assert report.todo_count == 1, line
        assert "userdel" not in out, line


def test_net_user_delete_rejects_shell_metacharacters(convert_bat):
    out, report = convert_bat('@echo off\nnet user "a;rm -rf /" /delete\n')
    assert report.todo_count == 1
    assert "userdel" not in out
    assert "rm -rf" not in out.split("TODO")[0]


def test_net_todo_hint_mentions_useradd_userdel(convert_bat):
    _, report = convert_bat("@echo off\nnet start spooler\n")
    assert "useradd/userdel" in report.todos[0].message
