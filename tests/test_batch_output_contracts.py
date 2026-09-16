"""B2 输出契约在 ``core/batch.py`` 中的集成行为（v1.10.0a1）。

本版**只接管裸命令**（``dxdiag`` / ``perfmon``，原为静默透传 → command not found），
带 ``.exe`` 的形态与 ``ipconfig`` / ``ping`` / ``help`` 的既有行为**保持不变**。
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("source", "command"),
    (("dxdiag /t out.txt\n", "dxdiag"), ("perfmon /report\n", "perfmon")),
)
def test_bare_command_becomes_structured_todo(convert_bat, bash_check, source, command):
    script, report = convert_bat(source)
    assert f"# TODO: 手动检查: {source.strip()}" in script
    assert report.todo_count == 1
    assert "输出契约" in report.todos[0].message
    assert "无对应物" in report.todos[0].message
    bash_check(script)


def test_exe_form_keeps_existing_generic_todo(convert_bat):
    _script, report = convert_bat("dxdiag.exe /t out.txt\n")
    assert report.todo_count == 1
    assert "输出契约" not in report.todos[0].message
    assert "Windows 可执行文件在 Linux 无对应物" in report.todos[0].message


def test_ipconfig_behavior_is_unchanged(convert_bat, bash_check):
    script, report = convert_bat("ipconfig /all\n")
    assert "ip addr show" in script
    assert report.todo_count == 0
    assert any("ipconfig 已转换为 ip addr" in w.message for w in report.warnings)
    bash_check(script)


def test_ping_contract_is_registered_not_consumed(convert_bat):
    script, report = convert_bat("ping -n 1 127.0.0.1\n")
    assert "ping -c 1 127.0.0.1" in script
    assert report.todo_count == 0


def test_help_behavior_is_unchanged(convert_bat):
    _script, report = convert_bat("help dir\n")
    assert report.todo_count >= 1
    assert not any("输出契约" in d.message for d in report.todos)


def test_forf_english_label_still_todo(convert_bat):
    _script, report = convert_bat(
        'for /f "tokens=15" %%i in (\'ipconfig ^| find /i "ip address"\') do set ip=%%i\n'
    )
    assert report.todo_count >= 1


def test_forf_cjk_mapping_still_converts(convert_bat):
    script, report = convert_bat(
        'for /f "tokens=2 delims=:" %%a in (\'ipconfig ^| findstr /i "IPv4"\') do echo %%a\n'
    )
    assert report.todo_count == 0
    assert "grep" in script


def test_unknown_command_still_warns(convert_bat):
    _script, report = convert_bat("frobnicate --now\n")
    assert report.todo_count == 0
    assert any("未知命令" in w.message for w in report.warnings)
