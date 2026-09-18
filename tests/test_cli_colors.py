"""CLI 三色输出回归测试：颜色启用条件 / NO_COLOR / JSON 纯净 / 错误退出码。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_PYTHON = Path(__file__).resolve().parents[1] / "python"

ERROR_BAT = "@echo off\nif 1==1 (\n:SKIP\necho done\n)\n"
WARNING_BAT = "@echo off\nipconfig\n"
CLEAN_BAT = "@echo off\necho hello\n"

RED = "\x1b[31m"
YELLOW = "\x1b[33m"
GREEN = "\x1b[32m"
RESET = "\x1b[0m"


def run_cli(
    *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("NO_COLOR", "FORCE_COLOR", "TERM")
    }
    env["PYTHONPATH"] = str(REPO_PYTHON)
    env["TERM"] = "xterm-256color"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "bat2sh", "--cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def make_bat(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "demo.bat"
    path.write_text(text, encoding="utf-8")
    return path


# ----------------------------------------------------------------------
# 颜色启用条件
# ----------------------------------------------------------------------
def test_color_enabled_respects_no_color_and_force_color(monkeypatch):
    from bat2sh import cli

    class _FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert cli.color_enabled(_FakeTty()) is True

    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.color_enabled(_FakeTty()) is False

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert cli.color_enabled(_FakeTty()) is False

    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("FORCE_COLOR", "0")
    assert cli.color_enabled(_FakeTty()) is False

    monkeypatch.setenv("FORCE_COLOR", "1")
    assert cli.color_enabled(_FakeTty()) is True


def test_color_enabled_term_unset_is_conservatively_off(monkeypatch):
    """.desktop 启动时不继承 TERM：未设置/空值一律关色，且不得抛出。"""
    from bat2sh import cli

    class _FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert cli.color_enabled(_FakeTty()) is False

    monkeypatch.setenv("TERM", "")
    assert cli.color_enabled(_FakeTty()) is False


def test_color_enabled_force_color_overrides_missing_term(monkeypatch):
    """FORCE_COLOR 优先级保持不变：TERM 缺失时仍强制开启。"""
    from bat2sh import cli

    class _FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert cli.color_enabled(_FakeTty()) is True


def test_color_enabled_never_raises_on_broken_stream(monkeypatch):
    """任何检测异常（isatty 抛错 / stream 为 None）都保守关色，不向上抛。"""
    from bat2sh import cli

    class _BrokenStream:
        def isatty(self):
            raise RuntimeError("boom")

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert cli.color_enabled(_BrokenStream()) is False
    assert cli.color_enabled(None) is False


def test_render_report_text_plain_matches_to_text():
    from bat2sh.cli import render_report_text
    from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind

    report = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    report.errors = [Diagnostic(1, "必须人工处理", category="syntax")]
    report.warnings = [Diagnostic(2, "路径一", category="path")]
    assert render_report_text(report, color=False) == report.to_text()


# ----------------------------------------------------------------------
# 三色渲染（FORCE_COLOR 强制开启，便于在管道中测试）
# ----------------------------------------------------------------------
def test_error_report_is_red_with_force_color(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(
        str(path), "--report", "-o", str(tmp_path / "out.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    assert proc.returncode == 0
    assert "── 错误" in proc.stderr
    assert RED in proc.stderr
    assert RESET in proc.stderr


def test_warning_report_is_yellow(tmp_path):
    path = make_bat(tmp_path, WARNING_BAT)
    proc = run_cli(
        str(path), "--report", "-o", str(tmp_path / "out.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    assert proc.returncode == 0
    assert "── 警告" in proc.stderr
    assert YELLOW in proc.stderr
    assert RED not in proc.stderr


def test_clean_status_line_is_green(tmp_path):
    path = make_bat(tmp_path, CLEAN_BAT)
    proc = run_cli(
        str(path), "-o", str(tmp_path / "out.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    assert proc.returncode == 0
    assert GREEN in proc.stderr
    assert RED not in proc.stderr
    assert YELLOW not in proc.stderr


def test_error_status_line_is_red(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(
        str(path), "-o", str(tmp_path / "out.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    assert proc.returncode == 0
    assert RED in proc.stderr
    assert "错误 1" in proc.stderr


def test_no_color_disables_ansi_even_with_force_color(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(
        str(path),
        "--report",
        "-o",
        str(tmp_path / "out.sh"),
        env_extra={"FORCE_COLOR": "1", "NO_COLOR": "1"},
    )
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stderr
    assert "\x1b[" not in proc.stdout


def test_pipe_without_force_color_has_no_ansi(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(str(path), "--report", "-o", str(tmp_path / "out.sh"))
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stderr


# ----------------------------------------------------------------------
# JSON 纯净与错误字段
# ----------------------------------------------------------------------
def test_report_json_includes_errors_and_stays_pure(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(str(path), "--report-json", "-o", str(tmp_path / "out.sh"))
    assert proc.returncode == 0
    assert proc.stdout.startswith("{")
    assert "\x1b[" not in proc.stdout
    data = json.loads(proc.stdout)
    assert data["error_count"] == 1
    assert data["errors"][0]["category"] == "control_flow"
    assert data["errors"][0]["message"]


# ----------------------------------------------------------------------
# 错误并入阻断逻辑
# ----------------------------------------------------------------------
def test_fail_on_todo_counts_errors(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(str(path), "--fail-on-todo", "-o", str(tmp_path / "out.sh"))
    assert proc.returncode == 3


def test_print_mode_with_fail_on_todo_counts_errors(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(str(path), "--print", "--fail-on-todo")
    assert proc.returncode == 3
    assert proc.stdout.startswith("#!/usr/bin/env bash")


def test_run_refuses_errors(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(str(path), "--run", "--yes")
    assert proc.returncode == 4
    assert "已拒绝执行" in proc.stderr


# ----------------------------------------------------------------------
# v2.7.0：--color / --no-color 显式开关与四场景色彩矩阵
# ----------------------------------------------------------------------
def test_color_enabled_explicit_modes(monkeypatch):
    from bat2sh import cli

    class _NonTty:
        def isatty(self) -> bool:
            return False

    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert cli.color_enabled(_NonTty(), "never") is False
    assert cli.color_enabled(_NonTty(), "always") is True

    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.color_enabled(_NonTty(), "always") is True
    assert cli.color_enabled(_NonTty(), "never") is False


def test_no_color_flag_overrides_force_color(tmp_path):
    path = make_bat(tmp_path, ERROR_BAT)
    proc = run_cli(
        str(path),
        "--report",
        "--no-color",
        "-o",
        str(tmp_path / "out.sh"),
        env_extra={"FORCE_COLOR": "1"},
    )
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stderr
    assert "\x1b[" not in proc.stdout


def test_color_flag_forces_ansi_in_pipe_and_overrides_no_color(tmp_path):
    path = make_bat(tmp_path, CLEAN_BAT)
    proc = run_cli(
        str(path),
        "--color",
        "-o",
        str(tmp_path / "out.sh"),
        env_extra={"NO_COLOR": "1"},
    )
    assert proc.returncode == 0
    assert GREEN in proc.stderr
    assert "\x1b[" not in proc.stdout


def test_color_flags_are_mutually_exclusive():
    proc = run_cli("--color", "--no-color")
    assert proc.returncode == 2
    assert "not allowed with" in proc.stderr


def test_color_matrix_four_scenarios(tmp_path):
    """TTY(模拟) / NO_COLOR / 非 TTY / --no-color 四场景：stdout 永不含 ANSI。"""
    path = make_bat(tmp_path, ERROR_BAT)
    tty_like = run_cli(
        str(path), "--report", "-o", str(tmp_path / "t.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    no_color = run_cli(
        str(path),
        "--report",
        "-o",
        str(tmp_path / "n.sh"),
        env_extra={"FORCE_COLOR": "1", "NO_COLOR": "1"},
    )
    plain = run_cli(str(path), "--report", "-o", str(tmp_path / "p.sh"))
    flag = run_cli(
        str(path),
        "--report",
        "--no-color",
        "-o",
        str(tmp_path / "f.sh"),
        env_extra={"FORCE_COLOR": "1"},
    )
    assert RED in tty_like.stderr
    assert "\x1b[" not in no_color.stderr
    assert "\x1b[" not in plain.stderr
    assert "\x1b[" not in flag.stderr
    for proc in (tty_like, no_color, plain, flag):
        assert "\x1b[" not in proc.stdout


# ----------------------------------------------------------------------
# v2.7.0：报告结论摘要行
# ----------------------------------------------------------------------
def test_render_report_summary_levels():
    from bat2sh.cli import render_report_summary
    from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind

    clean = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    assert render_report_summary(clean, False) == "结论: 转换完成，无错误 / 警告 / 待人工检查"

    warned = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    warned.warnings = [Diagnostic(1, "路径", category="path")]
    assert "1 警告" in render_report_summary(warned, False)

    errored = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    errored.errors = [Diagnostic(1, "语法", category="syntax")]
    assert "存在 1 处错误" in render_report_summary(errored, False)


def test_report_summary_appended_on_stderr_with_color(tmp_path):
    path = make_bat(tmp_path, WARNING_BAT)
    proc = run_cli(
        str(path), "--report", "-o", str(tmp_path / "out.sh"), env_extra={"FORCE_COLOR": "1"}
    )
    assert proc.returncode == 0
    assert "结论:" in proc.stderr
    assert YELLOW in proc.stderr
    assert "结论:" not in proc.stdout


def test_report_summary_clean_is_plain_without_color(tmp_path):
    path = make_bat(tmp_path, CLEAN_BAT)
    proc = run_cli(str(path), "--report", "-o", str(tmp_path / "out.sh"))
    assert proc.returncode == 0
    assert "结论: 转换完成，无错误 / 警告 / 待人工检查" in proc.stderr
    assert "\x1b[" not in proc.stderr


# ----------------------------------------------------------------------
# v2.7.0：多文件批量进度指示
# ----------------------------------------------------------------------
def test_multi_file_progress_prefix(tmp_path):
    first = tmp_path / "a.bat"
    first.write_text(CLEAN_BAT, encoding="utf-8")
    second = tmp_path / "b.bat"
    second.write_text(WARNING_BAT, encoding="utf-8")
    proc = run_cli(str(first), str(second), "--outdir", str(tmp_path / "out"))
    assert proc.returncode == 0
    assert "[1/2]" in proc.stderr
    assert "[2/2]" in proc.stderr


def test_single_file_has_no_progress_prefix(tmp_path):
    path = make_bat(tmp_path, CLEAN_BAT)
    proc = run_cli(str(path), "-o", str(tmp_path / "out.sh"))
    assert proc.returncode == 0
    assert "[1/1]" not in proc.stderr
    assert "[已写出]" in proc.stderr
