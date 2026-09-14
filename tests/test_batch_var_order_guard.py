"""unbound 变量护栏的顺序感知：主流程按"引用点之前的赋值"判定。"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def _run(tmp_path, text: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    script = tmp_path / "order.sh"
    script.write_text(text, encoding="utf-8")
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, cwd=tmp_path, timeout=30
    )


def test_main_flow_ref_before_assignment_guarded(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\necho before=%V%\nset "V=x"\necho after=%V%\n')
    assert 'echo "before=${V:-}"' in out
    assert 'echo "after=${V}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "before=\nafter=x\n"


def test_main_flow_ref_after_assignment_unguarded(convert_bat):
    out, _ = convert_bat('@echo off\nset "V=x"\necho %V%\n')
    assert 'echo "${V}"' in out
    assert "${V:-}" not in out


def test_function_body_ref_not_guarded(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\ncall :SUB\ngoto :eof\n\n"
        ':SUB\nset "INNER=1"\necho %INNER%\ngoto :eof\n'
    )
    assert "${INNER:-}" not in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "1\n"


def test_function_body_ref_with_outer_assignment_not_guarded(convert_bat, tmp_path):
    out, _ = convert_bat(
        "@echo off\nset \"OUTER=x\"\ncall :SUB\ngoto :eof\n\n"
        ":SUB\necho %OUTER%\ngoto :eof\n"
    )
    assert "${OUTER:-}" not in out
    proc = _run(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "x\n"
