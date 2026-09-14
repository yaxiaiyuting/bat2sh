"""批处理当前目录别名（cd./cd..）、pause 变体与 dir 开关识别回归测试。

语料依据（v1.4.1 批量分析）：
- ``cd.>list.m3u``（更新音乐播放列表test.bat）曾原样输出为未知命令
- ``dir /a-d /b /s``（自己做的mp3 flv提取器.bat）曾把 /a-d 当路径传给 ls
- ``pause...........``（根据TITLE重命名文件.bat）曾原样输出为未知命令
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "probe.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_cd_alias_forms(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ncd.\ncd..\nchdir.\necho ok\n")
    bash_check(out)
    assert 'cd "."' in out
    assert 'cd ".."' in out


def test_cd_alias_truncates_file(convert_bat, tmp_path, bash_check):
    out, _ = convert_bat("@echo off\ncd.>list.m3u\necho ok\n")
    bash_check(out)
    (tmp_path / "list.m3u").write_text("stale\n", encoding="utf-8")
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "list.m3u").read_text(encoding="utf-8") == ""
    assert proc.stdout == "ok\n"


def test_pause_with_trailing_dots(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\npause...........\n")
    bash_check(out)
    assert "read -rp" in out
    assert "pause." not in out


def test_dir_switch_a_dash_not_treated_as_path(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ndir /a-d /b /s \"C:\\Docs\"\n")
    bash_check(out)
    assert "/a-d" not in out
    assert "ls -1R" in out


def test_dir_b_s_keeps_recursive(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ndir /b /s *.txt\n")
    bash_check(out)
    assert "ls -1R" in out
