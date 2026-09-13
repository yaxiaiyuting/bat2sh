"""过滤型管道（grep/findstr 结尾）加 || true 兜底，对齐 bat 过滤语义。"""

from __future__ import annotations


def test_findstr_pipe_gets_fallback(convert_bat):
    out, _ = convert_bat("@echo off\ndir /b | findstr x\n")
    assert "ls -1 | grep x || true" in out
    assert "# bat 过滤语义：未匹配不终止脚本" in out


def test_grep_pipe_gets_fallback(convert_bat):
    out, _ = convert_bat("@echo off\necho hello | grep hello\n")
    assert 'echo "hello" | grep hello || true' in out


def test_non_filter_pipe_has_no_fallback(convert_bat):
    out, _ = convert_bat("@echo off\ntype test.txt | sort\n")
    assert "| sort" in out
    assert "|| true" not in out


def test_multi_stage_pipe_stays_todo(convert_bat):
    out, _ = convert_bat("@echo off\ntype f | findstr x | findstr y\n")
    assert "# TODO" in out
    assert "|| true" not in out


def test_filter_pipe_runtime_continues(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\necho hello | findstr zzz\necho after\n")
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "after\n"


def test_for_f_pipe_unaffected(convert_bat):
    out, _ = convert_bat(
        "@echo off\nfor /f %%a in ('dir | findstr x') do echo %%a\n"
    )
    assert "# TODO" in out
    assert "|| true" not in out


def test_set_prefix_display_gets_fallback(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\nset MY_VAR\n")
    assert 'env | grep -E "^MY_VAR" || true' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
