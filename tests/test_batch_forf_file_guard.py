"""for /f 读取文件：文件缺失/不可读时不终止脚本（bat 语义）。"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

DEEPSEEK_CASE = (
    "@echo off\n"
    'for /f "usebackq tokens=*" %%a in ("double quote file.txt") do echo %%a\n'
    "echo 后续继续\n"
)


def _convert(convert_bat, source: str) -> str:
    out, _ = convert_bat(source)
    return out


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "loop.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )


def test_missing_file_does_not_terminate(convert_bat, tmp_path):
    out = _convert(convert_bat, DEEPSEEK_CASE)
    assert 'if [ -r "double quote file.txt" ]; then' in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "后续继续\n"


def test_existing_file_normal_output(convert_bat, tmp_path):
    (tmp_path / "double quote file.txt").write_text("line1\nline2\n", encoding="utf-8")
    out = _convert(convert_bat, DEEPSEEK_CASE)
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "line1\nline2\n后续继续\n"


def test_unreadable_file_does_not_terminate(convert_bat, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root 不受文件权限限制")
    target = tmp_path / "double quote file.txt"
    target.write_text("line1\n", encoding="utf-8")
    target.chmod(0o000)
    try:
        out = _convert(convert_bat, DEEPSEEK_CASE)
        proc = _run(tmp_path, out)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == "后续继续\n"
    finally:
        target.chmod(0o600)


def test_bare_file_form_guarded_and_continues(convert_bat, tmp_path):
    out = _convert(
        convert_bat,
        "@echo off\nfor /f %%a in (missing.txt) do echo %%a\necho 继续\n",
    )
    assert 'if [ -r "missing.txt" ]; then' in out
    assert 'done < "missing.txt"' in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "继续\n"


def test_skip_variant_guarded_and_continues(convert_bat, tmp_path):
    out = _convert(
        convert_bat,
        '@echo off\nfor /f "skip=1" %%a in (missing.txt) do echo %%a\necho 继续\n',
    )
    assert 'if [ -r "missing.txt" ]; then' in out
    assert 'done < <(tail -n +2 < "missing.txt")' in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "继续\n"


def test_command_form_not_guarded(convert_bat, bash_run):
    out = _convert(convert_bat, "@echo off\nfor /f %%a in ('echo hi') do echo %%a\n")
    assert "if [ -r" not in out
    assert 'done < <(echo "hi")' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "hi\n"
