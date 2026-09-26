"""循环变量 `%~dpn` / `%~dpnx` 保留路径回归测试。

语料依据（v1.4.1 沙箱体检 §10，055-bat-master-重命名.bat 等 5 文件 11 处）：
``%%~dpni`` / ``%%~dpnxi`` 之前生成 ``$(basename ...)``，丢弃目录部分；
在 ``dir /s`` 递归场景下会指向错误目录。无 n/x 的 ``%~dpi`` 等保持现状（backlog C2）。
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


def test_dpn_keeps_directory(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nfor %%i in (sub\\inner.txt) do echo %%~dpni\n")
    bash_check(out)
    assert 'echo "${i%.*}"' in out
    assert "basename" not in out


def test_dpnx_keeps_full_path(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nfor %%i in (sub\\inner.txt) do echo %%~dpnxi\n")
    bash_check(out)
    assert 'echo "${i}"' in out
    assert "basename" not in out


def test_path_modifier_without_nx_unchanged(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nfor %%i in (sub\\inner.txt) do echo %%~dpi\n")
    bash_check(out)
    assert 'echo "${i}"' in out


def test_name_only_modifier_returns_basename_without_extension(convert_bat, tmp_path, bash_check):
    """语义：``%%~ni`` 只保留**末段**并去扩展名 ⇒ 真跑应输出 ``inner``。

    旧测试名 ``..._still_use_basename`` + 断言 ``'$(basename "${i%.*}")' in out``
    实际把**缺陷表达式**（先剥扩展名、再取末段，顺序倒置）钉死在测试里 —— 属纪律 8 欠账。
    改为运行产物、断言行为；含点祖先路径的真值见
    ``test_batch_tilde_n_dotted_path.py``。
    """
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("x\n", encoding="utf-8")
    out, _ = convert_bat("@echo off\nfor %%i in (sub\\inner.txt) do echo %%~ni\n")
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "inner\n"


def test_dpn_subdir_path_runtime(convert_bat, tmp_path, bash_check):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("x\n", encoding="utf-8")
    out, _ = convert_bat(
        "@echo off\n"
        "for %%i in (sub\\inner.txt) do echo %%~dpni\n"
        "for %%i in (sub\\inner.txt) do echo %%~dpnxi\n"
    )
    bash_check(out)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "sub/inner\nsub/inner.txt\n"
