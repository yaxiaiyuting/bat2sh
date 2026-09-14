"""`<nul set /p=文本`（无变量名、无换行打印）回归测试。

语料依据（v1.4.1 批量分析，3 个脚本）：
- ipchelper.bat: ``set/p=%var%<nul``
- 进度条解析.bat: ``set /p =%\\t%<nul``
- 统计学.bat: ``>>tmp.txt set /p= %%i<nul``
此前被误当成变量赋值（生成 ``_p="文本"``）或原样输出为未知命令。
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


def test_nul_set_p_prints_without_newline(convert_bat, bash_check, tmp_path):
    out, report = convert_bat("@echo off\n<nul set /p=AB<nul\necho C\n")
    bash_check(out)
    assert "printf '%s' \"AB\"" in out
    assert report.todo_count == 0
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "ABC\n"


def test_set_p_prompt_only_variants(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset /p=hello<nul\nset/p=%v%<nul\nset /p =%w%<nul\n")
    bash_check(out)
    assert out.count("printf '%s'") == 3
    assert 'printf \'%s\' "${v:-}"' in out


def test_set_p_redirect_kept(convert_bat, bash_check, tmp_path):
    out, _ = convert_bat("@echo off\n>>tmp.txt set /p= %%i<nul\n")
    bash_check(out)
    assert ">>tmp.txt" in out
    assert "printf '%s'" in out


def test_set_p_without_nul_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nset /p=no redirect\n")
    assert "# TODO: 手动检查: set /p=no redirect" in out
    assert report.todo_count == 1


def test_set_p_with_variable_name_still_reads(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset /p ip=enter ip:\n")
    bash_check(out)
    assert "read -rp" in out
    assert 'printf' not in out
