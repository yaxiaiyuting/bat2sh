"""v1.8.2 A-2b：cmd 合并开关（`/q/s`、`/b/s/adh`）修复回归。

语料依据（v1.8.2 artifact 分类 §2.A A3）：
- ``第三方工具/wselect…/原版.bat:3`` ``dir /b/s/adh C:\\`` → 误产
  ``ls -la "/b/s/adh" "C:/"``（合并开关被当路径）
- ``卸载inf文件.CMD:1`` ``rd "%APPDATA%\\DemoCreator" /q/s`` → 误产
  ``rmdir "…" "/q/s"``

``date /t`` 原语料为粘连形态 ``date/t``（归 A-2a）；空格形态的 handler 因会改动
``examples/stress_test.bat`` 产物与冻结告警快照，本批**暂缓**（见 release 披露）。
"""

from __future__ import annotations

import pytest


def test_dir_combined_switches_not_path(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\ndir /b/s/adh C:\\ >"%temp%\\t.txt"\n')
    bash_check(out)
    assert '"/b/s/adh"' not in out
    assert "ls -1R" in out


def test_rd_combined_switch_becomes_rm_rf(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nrd "%APPDATA%\\DemoCreator" /q/s\n')
    bash_check(out)
    assert 'rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/DemoCreator"' in out
    assert '"/q/s"' not in out


def test_del_combined_switch(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\ndel /f/q/s "x"\n')
    bash_check(out)
    assert 'rm -rf "x"' in out


def test_date_t_still_todo_until_switch_handling_revisited(convert_bat):
    out, report = convert_bat("@echo off\ndate /t >>out.txt\n")
    assert report.todo_count == 1
    assert "date +%Y-%m-%d" not in out


@pytest.mark.parametrize("posix_path", ["/usr/bin/target", "/opt/app/bin/x"])
def test_posix_path_not_split_as_switches(convert_bat, bash_check, posix_path):
    out, _ = convert_bat(f'@echo off\ncopy a.txt "{posix_path}"\n')
    bash_check(out)
    assert f'"{posix_path}"' in out
