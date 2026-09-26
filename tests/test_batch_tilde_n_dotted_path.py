"""``%%~n`` / ``%~n0`` 的**含点祖先路径**回归测试（v2.11.1，F-N）。

缺陷（`batch.py` `_modifier`）：``%%~n`` 旧映射为 ``$(basename "${v%.*}")`` ——
**先剥扩展名、再取末段**，顺序倒置。``${v%.*}`` 剥的是**整串最后一个点**，
⇒ 仅当「``basename(v)`` 自身不含点」且「某祖先路径段含点」时截错：

    /tmp/.../my.project/samples   # 旧: `my`（祖先前缀）  正确: `samples`

本缺陷**完全静默**（rc=0、stderr 空、无 TODO、``bash -n`` 通过），
且既有测试全部在**无点路径**上运行 ⇒ 结构性地抓不到。故本文件专测含点祖先：

1. ``test_for_r_name_modifier_dotted_ancestor``：真缺陷触发面（``%%~ni``）；
2. ``test_script_name_n0_dotted_ancestor``：``%~n0`` 同根因；
3. ``test_for_r_name_modifier_no_dot_control``：无点路径**对照**（防修 A 坏 B）。

> 目标值来自 v2.11.0 真机 oracle 指纹：``%%~ni`` 在 ``C:\\poc\\samples`` 上为 ``samples``
> （W 侧建出 ``samples.txt``），非推测。
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

FOR_R_N = "@echo off\nfor /r %%i in (.) do @echo %%~ni\n"


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    return bash


def _run_script(
    script_text: str, cwd, filename: str = "probe.sh"
) -> subprocess.CompletedProcess:
    """把产物写成真实脚本文件，在 **cwd** 下执行（``$0``/``$PWD`` 才符合真机语义）。"""
    cwd.mkdir(parents=True, exist_ok=True)
    script = cwd / filename
    script.write_text(script_text, encoding="utf-8")
    return subprocess.run(
        [_bash(), str(script)], capture_output=True, text=True, cwd=cwd, timeout=30
    )


def test_for_r_name_modifier_dotted_ancestor(convert_bat, tmp_path):
    """含点祖先（``my.project``）下 ``%%~ni`` 必须给**末段名**，而非祖先前缀 ``my``。"""
    dotted = tmp_path / "my.project" / "samples"
    (dotted / "sub").mkdir(parents=True)
    out, report = convert_bat(FOR_R_N)
    assert report.todo_count == 0
    proc = _run_script(out, dotted)
    assert proc.returncode == 0, proc.stderr
    # find 的根即 <cwd>/my.project/samples ⇒ 末段 `samples`（无点，不被剥）+ `sub`
    # 修复前：末段无点而祖先段含点 ⇒ 两个值都被剥成祖先前缀 `my`
    assert proc.stdout == "samples\nsub\n"


def test_for_r_name_modifier_no_dot_control(convert_bat, tmp_path):
    """对照组：**无点**路径下同一脚本结果不变（防止修好含点路径却弄坏无点路径）。"""
    plain = tmp_path / "samples"
    (plain / "sub").mkdir(parents=True)
    out, report = convert_bat(FOR_R_N)
    assert report.todo_count == 0
    proc = _run_script(out, plain)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "samples\nsub\n"


def test_for_r_name_modifier_sibling_dirs_dotted_ancestor(convert_bat, tmp_path):
    """含点祖先下多个子目录各自取自己的末段名（非同一个错误前缀）。"""
    dotted = tmp_path / "my.project" / "samples"
    (dotted / "alpha").mkdir(parents=True)
    (dotted / "beta").mkdir()
    out, _ = convert_bat(FOR_R_N)
    proc = _run_script(out, dotted)
    assert proc.returncode == 0, proc.stderr
    # find 的遍历顺序不保证：断言**值集合**而非顺序
    assert sorted(proc.stdout.splitlines()) == ["alpha", "beta", "samples"]


def test_script_name_n0_dotted_ancestor(convert_bat, tmp_path):
    """``%~n0`` 在含点祖先下必须给**脚本名去扩展**，而非祖先段 ``my``。

    关键：产物必须以**无扩展名**的文件名执行 —— 缺陷的充要条件之一是
    ``basename($0)`` 自身不含点。若把脚本叫 ``x.sh``，``${0%.*}`` 恰好只吃掉 ``.sh``，
    缺陷被掩盖（这正是既有测试抓不到它的原因之一）。
    """
    dotted = tmp_path / "my.project" / "samples"
    dotted.mkdir(parents=True)
    out, _ = convert_bat("@echo off\necho %~n0\n", source_name="norext.bat")
    proc = _run_script(out, dotted, "norext")
    assert proc.returncode == 0, proc.stderr
    # $0 = /…/my.project/samples/norext ⇒ 去扩展名 = 源脚本名 norext.bat 的主名
    assert proc.stdout == "norext\n"


def test_script_name_n0_no_dot_control(convert_bat, tmp_path):
    """对照组：无点路径下 ``%~n0`` 结果不变。"""
    plain = tmp_path / "samples"
    plain.mkdir()
    out, _ = convert_bat("@echo off\necho %~n0\n", source_name="norext.bat")
    proc = _run_script(out, plain, "norext")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "norext\n"


def test_del_n_quoted_dotted_ancestor_deletes_right_name(convert_bat, tmp_path):
    """删除语境（潜在静默数据丢失面）：含点祖先下 ``del "%%~ni"`` 必须删**正确**目标。

    循环项必须是**无扩展名**文件（``basename`` 自身不含点）—— 这才是缺陷充要条件；
    修复前的错名（祖先段 ``my``）在 ``rm -f`` 下**静默成功**（目标不存在）且漏删真目标。
    """
    dotted = tmp_path / "my.project" / "samples"
    dotted.mkdir(parents=True)
    (dotted / "keepme").write_text("x", encoding="utf-8")
    (dotted / "dryrun.txt").write_text("x", encoding="utf-8")
    out, _ = convert_bat('@echo off\nfor %%i in (*) do del "%%~ni"\n')
    proc = _run_script(out, dotted)
    assert proc.returncode == 0, proc.stderr
    assert not (dotted / "keepme").exists(), "无扩展名目标未被删除（缺陷：删了错名 my）"
    assert (dotted / "dryrun.txt").exists(), "带扩展名文件的 del %%~ni 目标是 dryrun，须保留"
