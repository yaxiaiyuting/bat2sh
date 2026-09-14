"""findstr 开关映射：/r 为正则（grep -E），/c: 为字面（grep -F）；中文模式识别与映射。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_r_switch_uses_extended_regex(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /r "^[0-9]" data.txt\n')
    assert 'grep -E "^[0-9]" "data.txt"' in out


def test_c_switch_without_r_is_fixed(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /c:"a.b" data.txt\n')
    assert 'grep -F "a.b" "data.txt"' in out


def test_r_with_c_switch_prefers_regex(convert_bat):
    out, _ = convert_bat('@echo off\nfindstr /r /c:"^[0-9][0-9]*$" numbers.txt\n')
    assert 'grep -E "^[0-9][0-9]*$" "numbers.txt"' in out
    assert "-F" not in out


def test_i_switch(convert_bat):
    out, _ = convert_bat("@echo off\nfindstr /i hello data.txt\n")
    assert "grep -i hello" in out


def test_v_switch(convert_bat):
    out, _ = convert_bat("@echo off\nfindstr /v hello data.txt\n")
    assert "grep -v hello" in out


def test_regex_mode_runtime_matches_number_lines(convert_bat, tmp_path):
    (tmp_path / "numbers.txt").write_text("123\nabc\n45\n", encoding="utf-8")
    out, _ = convert_bat('@echo off\nfindstr /r /c:"^[0-9][0-9]*$" numbers.txt\n')
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    proc = subprocess.run(
        [bash], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "123\n45\n"


# ----------------------------------------------------------------------
# 中文模式：已知映射 / 未知告警 / 纯英文不受影响
# ----------------------------------------------------------------------
def test_known_chinese_pattern_is_mapped(convert_bat):
    out, report = convert_bat('@echo off\nfindstr /i "IPv4 地址" data.txt\n')
    assert 'grep -i "inet " "data.txt"' in out
    assert any("已映射" in d.message and "inet" in d.message for d in report.warnings)
    assert report.todo_count == 0


def test_known_chinese_pattern_with_c_switch_maps(convert_bat):
    out, report = convert_bat('@echo off\nfindstr /c:"物理地址" data.txt\n')
    assert 'grep -F "ether " "data.txt"' in out
    assert any("分隔符不同" in d.message for d in report.warnings)


def test_mapped_pattern_runtime_matches_english_output(convert_bat, tmp_path):
    (tmp_path / "ip.txt").write_text(
        "2: eth0: <BROADCAST,MULTICAST,UP>\n"
        "    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0\n"
        "    inet6 fe80::1/64 scope link\n",
        encoding="utf-8",
    )
    out, _ = convert_bat('@echo off\nfindstr /i "IPv4 地址" ip.txt\n')
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    proc = subprocess.run(
        [bash], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0\n"


def test_unknown_chinese_pattern_warns_without_replacement(convert_bat):
    out, report = convert_bat('@echo off\nfindstr /i "你好世界" data.txt\n')
    assert 'grep -i "你好世界" "data.txt"' in out
    assert any("未收录已知映射" in d.message for d in report.warnings)
    assert report.todo_count == 0


def test_mixed_pattern_with_known_phrase_warns_without_replacement(convert_bat):
    out, report = convert_bat(
        '@echo off\nfindstr /i "IPv4 地址 IPv4 Address" data.txt\n'
    )
    assert "IPv4 地址 IPv4 Address" in out
    assert '-i "inet "' not in out
    assert any(
        "未自动替换" in d.message and "IPv4 地址" in d.message for d in report.warnings
    )


def test_english_pattern_has_no_chinese_warning(convert_bat):
    out, report = convert_bat("@echo off\nfindstr /i IPv4 data.txt\n")
    assert "grep -i IPv4" in out
    assert not any("中文" in d.message for d in report.warnings)
