"""v1.8.1：bat 块结构发射缺陷回归（多行 if/for 的 `)` 粘连、if+for 嵌套）。"""

from __future__ import annotations

import pytest


def test_call_glued_paren_closes_if_block(convert_bat, bash_check, bash_run):
    out, report = convert_bat(
        "@echo off\n"
        'if "%password%"=="10949741" (\n'
        "  echo ok\n"
        "  call :index)\n"
        "echo after\n"
        "goto :eof\n"
        ":index\n"
        "echo idx\n"
        "exit /b\n",
        bash_check=False,
    )
    assert report.error_count == 0
    bash_check(out)
    assert "fi" in out
    assert " )" not in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr


def test_else_glued_paren_closes_block(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\n"
        'if "%x%"=="1" (\n  echo a\n) else (\n  call :sub)\n'
        "goto :eof\n:sub\necho s\nexit /b\n",
        bash_check=False,
    )
    bash_check(out)
    assert " )" not in out


def test_for_glued_paren_closes_loop(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\nfor %%i in (a b) do (\nping 127.1 -n 1>nul)\necho done\n",
        bash_check=False,
    )
    bash_check(out)
    assert "done" in out
    assert " )" not in out


def test_if_for_multiline_body_keeps_both_closers(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nset times=1,2\nif not "%times%"=="" for %%i in (%times%) do (\n'
        "    echo %%i\n)\n",
        bash_check=False,
    )
    assert report.error_count == 0
    bash_check(out)
    assert "done" in out
    assert "fi" in out
    assert out.index("done") < out.index("fi")


@pytest.mark.parametrize("name", ["系统优化.bat", "定时关机.cmd"])
def test_real_corpus_block_forms(name, bash_check):
    from pathlib import Path

    from bat2sh.core.encoding import decode_bytes
    from bat2sh.core.engine import convert_text
    from bat2sh.core.settings import ConvertSettings
    from bat2sh.core.types import SourceKind

    corpus = Path.home() / "下载" / "非常批处理"
    path = next(p for p in corpus.rglob(name) if p.is_file())
    text = decode_bytes(path.read_bytes(), None).text
    out, report = convert_text(
        text, SourceKind.BATCH, ConvertSettings(bash_check=False), name
    )
    assert report.error_count == 0
    bash_check(out)
