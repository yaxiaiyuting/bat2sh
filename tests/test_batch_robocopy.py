"""robocopy → rsync 开关映射回归测试（v1.4.1 语料分析）。

语料依据：
- ``robocopy /MIR emp .siyuan``（windows-batch-script-master/删除嵌套.bat，153 处）
- ``robocopy . . test1.txt /NJH /NJS /NDL /NC /NS``（deepseek_bat_20260913_895203.bat）

此前 ``/MIR`` 等开关被当作路径传给 rsync；且 ``rsync -a src dst`` 会把源目录嵌套进目标，
与 robocopy“复制目录内容”的语义不符（已用 bwrap 沙箱验证）。
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_robocopy_mir_maps_to_delete(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nrobocopy /MIR emp .siyuan\n")
    bash_check(out)
    assert 'rsync -a --delete "emp/" ".siyuan/"' in out


def test_robocopy_e_ignored_flag(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nrobocopy emp .siyuan /E\n")
    bash_check(out)
    assert 'rsync -a "emp/" ".siyuan/"' in out
    assert "--delete" not in out


def test_robocopy_output_flags_ignored(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nrobocopy emp .siyuan /NJH /NJS /NDL /NC /NS\n")
    bash_check(out)
    assert 'rsync -a "emp/" ".siyuan/"' in out


def test_robocopy_unknown_flag_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nrobocopy /PURGE emp .siyuan\n")
    assert "# TODO: 手动检查: robocopy /PURGE emp .siyuan" in out
    assert report.todo_count == 1
    assert "rsync" not in out


def test_robocopy_file_filter_form_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nrobocopy . . test1.txt /NJH /NJS\n")
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1


def test_robocopy_mirror_runtime_semantics(convert_bat, tmp_path):
    rsync = shutil.which("rsync")
    if rsync is None:
        pytest.skip("未安装 rsync")
    out, _ = convert_bat("@echo off\nrobocopy /MIR emp .siyuan\n")
    (tmp_path / "emp").mkdir()
    (tmp_path / ".siyuan").mkdir()
    (tmp_path / "emp" / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / ".siyuan" / "a.txt").write_text("OLD", encoding="utf-8")
    (tmp_path / ".siyuan" / "extra.txt").write_text("EXTRA", encoding="utf-8")
    script = tmp_path / "mirror.sh"
    script.write_text(out, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in (tmp_path / ".siyuan").iterdir()) == ["a.txt"]
    assert (tmp_path / ".siyuan" / "a.txt").read_text(encoding="utf-8") == "A"
