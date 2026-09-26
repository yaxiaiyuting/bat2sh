"""`start` 的模态框风险告警 —— 行为追踪研究发现的产品回写。

依据：``research/behavior-tracking/batch-result.md`` §4.2（实测）
  · s13 `HOTFIX.CMD`：`start "" "E:\\软件\\…\\打开系统自带命令行参考.bat"`；
  · s16 `范例.bat`：`start "" "BalloonTip.exe" …`；
  · 两者都**不含** `pause` / `set /p`（静态"非交互"筛选通过），但 `start` 找不到目标时
    Windows 会弹**模态错误框**，非交互环境里无人点"确定" ⇒ 进程**永不退出**，
    采集端只能等到 150 s+ 超时。

bat2sh 在 Linux 侧**无法**检查 Windows 目标是否存在 ⇒ 只声明"无法验证 + 失败方式不同"，
**不猜**目标在不在（纪律：保守 TODO 优于激进转换）。这里用**警告**而非 TODO：
"无法确认存在"不等于"需要人工改写"，而 TODO 会改变 CLI 退出码。

本测试守护：该报的报（字面量路径 / 裸程序名 / 含变量），不该报的不报（普通命令），
且**产物一字不改**。
"""

from __future__ import annotations

import pytest


def _messages(report) -> list[str]:
    return [d.message for d in report.warnings]


def test_literal_windows_path_is_flagged(convert_bat):
    out, report = convert_bat(
        '@echo off\nstart "" "E:\\软件\\CMDOW\\打开系统自带命令行参考.bat"\n'
    )
    hazards = [m for m in _messages(report) if "模态框" in m]
    assert len(hazards) == 1
    assert "字面量路径" in hazards[0]
    assert "无法" in hazards[0] and "存在" in hazards[0]
    # 产物不变：仍然是 xdg-open（告警不是改写）
    assert 'xdg-open "E:/软件/CMDOW/打开系统自带命令行参考.bat" &' in out
    assert report.todo_count == 0


def test_bare_executable_name_is_flagged(convert_bat):
    """s16 式：裸程序名（无路径）—— 同样无法静态确认存在。"""
    out, report = convert_bat('@echo off\nstart "" "BalloonTip.exe" /t x\n')
    hazards = [m for m in _messages(report) if "模态框" in m]
    assert len(hazards) == 1
    assert "裸程序名" in hazards[0]
    assert "nohup BalloonTip.exe" in out
    assert report.todo_count == 0


def test_variable_target_is_flagged_as_unverifiable(convert_bat):
    out, report = convert_bat(
        "@echo off\nset mydir=D:\\tools\nstart \"\" \"%mydir%\\a.exe\"\n"
    )
    hazards = [m for m in _messages(report) if "模态框" in m]
    assert len(hazards) == 1
    assert "含变量" in hazards[0]
    assert "xdg-open" in out
    assert report.todo_count == 0


@pytest.mark.parametrize(
    "line",
    [
        "start /wait notepad",          # 普通命令：存在与否不是脚本能决定的，不报
        "start /b python worker.py",    # 同上
        "start",                        # 无目标：已有专门警告
    ],
)
def test_plain_command_targets_are_not_flagged(convert_bat, line):
    _, report = convert_bat("@echo off\n" + line + "\n")
    assert not [m for m in _messages(report) if "模态框" in m]


def test_windows_only_command_still_becomes_todo(convert_bat):
    """既有路径不能被新告警挤掉：Windows 专有命令仍然是 TODO（todo 计数不变）。"""
    out, report = convert_bat('@echo off\nSTART /WAIT REGEDIT /S "x.reg"\n')
    assert "# TODO: 手动检查: START /WAIT REGEDIT" in out
    assert report.todo_count == 1
