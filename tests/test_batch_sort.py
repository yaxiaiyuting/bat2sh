"""sort 开关转译：/r → -r，/+N → TODO，/o → 重定向。"""

from __future__ import annotations

import subprocess


def test_sort_reverse_switch(convert_bat):
    out, report = convert_bat("@echo off\nsort /r test1.txt > sorted.txt\n")
    assert "sort -r test1.txt >sorted.txt" in out
    assert report.todo_count == 0


def test_sort_reverse_runtime(convert_bat, tmp_path):
    (tmp_path / "nums.txt").write_text("b\na\nc\n", encoding="utf-8")
    out, _ = convert_bat("@echo off\nsort /r nums.txt\n")
    proc = subprocess.run(
        ["bash"], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "c\nb\na\n"


def test_sort_plus_n_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nsort /+3 test.txt\n")
    assert report.todo_count == 1
    assert "# TODO: 手动检查: sort /+3 test.txt" in out


def test_sort_without_switches_unchanged(convert_bat):
    out, _ = convert_bat("@echo off\nsort test.txt\n")
    assert "sort test.txt" in out


def test_sort_no_args_unchanged(convert_bat):
    out, _ = convert_bat("@echo off\nsort\n")
    assert "\nsort\n" in out


def test_sort_output_switch_becomes_redirect(convert_bat):
    out, _ = convert_bat("@echo off\nsort /r /o sorted.txt source.txt\n")
    assert "sort -r source.txt > sorted.txt" in out
