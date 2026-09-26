"""``for /r`` → ``find`` 转换的回归测试（v1.11.0；v2.11.0 起产出**绝对路径**）。

断言转换的**语义**（递归枚举目录、值域与 cmd 的 `for /r` 同形），
而非编码转换器当前行为。

v2.11.0 变更（F3）：`find .` → `cd <root> && find "$PWD"`。
- cmd 的 `for /r %%i in (.)` 给的本来就是**完整路径**（`C:\\poc\\samples\\sub`），
  绝对路径更接近真机；
- `find .` 的值域是 `.` 与 `./sub` —— **每个值都带前导点**，使 `%%~n` 的映射
  `basename "${v%.*}"` 被剥成空串（oracle V5 静默建出字面文件 ``.\\.txt``）。
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest


def _realpaths(stdout: str) -> set[str]:
    """把产物打印的路径归一成真实路径，用于**值域语义**断言（而非字面前缀）。"""
    return {os.path.realpath(p) for p in stdout.split()}


def test_for_r_dot_converts_to_find_dir_loop(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do echo %%i\n")
    assert report.todo_count == 0
    assert "while IFS= read -r i; do" in out
    assert '-type d)' in out and "find " in out
    assert "for i in" not in out
    bash_check(out)


def test_for_r_enumerates_directories_recursively(convert_bat, tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "c").mkdir()
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do echo %%i\n")
    assert report.todo_count == 0
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    proc = subprocess.run(
        [bash], input=out, capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    # 语义：根目录自身 + 全部子目录（递归），且是**完整路径**（cmd `for /r` 口径）
    assert _realpaths(proc.stdout) == {
        os.path.realpath(p) for p in (tmp_path, tmp_path / "a",
                                      tmp_path / "a" / "b", tmp_path / "c")
    }
    for token in proc.stdout.split():
        assert os.path.isabs(token), f"应为完整路径: {token!r}"


def test_for_r_root_value_can_be_resolved_to_a_basename(convert_bat, tmp_path):
    """F3 的**运行语义**：根目录的值必须能取出目录名（cmd `%%~ni` 的含义）。

    旧实现 `find .` 让根的值 = `.`，`basename "${v%.*}"` 被剥成空串 ⇒
    `%%~ni` 产空 ⇒ 静默建出字面文件 ``.\\.txt``（oracle V5）。
    """
    (tmp_path / "samples").mkdir()
    out, report = convert_bat(
        '@echo off\nfor /r %%i in (.) do (cd.>"%%i\\%%~ni.txt")\n'
    )
    assert report.todo_count == 0
    (tmp_path / "samples" / "run.sh").write_text(out, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(tmp_path / "samples" / "run.sh")],
        capture_output=True, text=True, cwd=tmp_path / "samples", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    created = sorted(p.name for p in (tmp_path / "samples").iterdir())
    assert created == ["run.sh", "samples.txt"]


def test_for_r_block_body_converts(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /r %%i in (.) do (\n  echo %%i\n)\n"
    )
    assert report.todo_count == 0
    assert "while IFS= read -r i; do" in out
    assert '-type d)' in out and "find " in out
    bash_check(out)


def test_for_r_variable_root_defaults_to_current_dir(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nfor /r %back% %%a in (.) do echo %%a\n")
    # 语义：变量根被解析，且 `cd` 进该根后再枚举（对相对/绝对根都正确）
    assert 'cd "${back:-.}"' in out
    assert '-type d)' in out
    assert report.todo_count == 0
    bash_check(out)


def test_for_r_file_set_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (*.jpg) do echo %%i\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_r_body_with_goto_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (.) do goto done\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_r_glob_root_remains_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (*.txt) do echo %%i\n")
    assert report.todo_count == 1
    assert "find" not in out


def test_for_l_and_plain_for_unaffected(convert_bat, bash_check):
    out_l, report_l = convert_bat("@echo off\nfor /l %%i in (1,1,3) do echo %%i\n")
    assert "for i in $(seq 1 1 3); do" in out_l
    assert "find" not in out_l
    assert report_l.todo_count == 0
    bash_check(out_l)

    out_p, report_p = convert_bat("@echo off\nfor %%i in (a b) do echo %%i\n")
    assert "for i in a b; do" in out_p
    assert "find" not in out_p
    assert report_p.todo_count == 0
    bash_check(out_p)


def test_for_f_file_form_unaffected(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"delims=\" %%i in (data.txt) do echo %%i\n"
    )
    assert report.todo_count == 0
    assert 'done < "data.txt"' in out
    assert "find" not in out
    bash_check(out)
