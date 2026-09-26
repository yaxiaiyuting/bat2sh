"""行尾检测（LF-only / 混合）—— 行为追踪研究发现的产品回写。

依据：``research/behavior-tracking/batch-result.md`` §4.1（实测）
  · 语料 26.7%（55/206）是 **LF-only**；
  · LF-only 的 .bat/.cmd 会让 **cmd.exe 解析错乱**（命令行首被逐行吃掉、报
    "不是内部或外部命令"、rc=255）；
  · A/B 对照：只把 LF 换成 CRLF（内容一字不改）重跑，同一个样本 rc 从 **255 → 0**。
  ⇒ 这些脚本**在真 Windows 上也跑不对**，bat2sh 应在转换时如实告警。

本测试守护四件事：
  1. 检测本身正确（crlf / lf / mixed / none）；
  2. **只警告不阻断**（产物一字不差、行尾不影响转换结果）；
  3. 只对**批处理**报（PowerShell 解析 LF 正常）；
  4. 警告进了报告（warnings 列表），CLI 也看得到。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bat2sh.core.encoding import detect_line_endings
from bat2sh.core.engine import convert_file
from bat2sh.core.settings import ConvertSettings

REPO_PYTHON = Path(__file__).resolve().parents[1] / "python"

SCRIPT_LINES = (
    "@echo off\n",
    "setlocal\n",
    "set NAME=World\n",
    "echo Hello %NAME%\n",
    "endlocal\n",
)


def _write(tmp_path: Path, name: str, newline: str, lines=SCRIPT_LINES) -> Path:
    """按指定行尾写出：每一行都以 ``newline`` 结尾（CRLF 版不会混进裸 LF）。"""
    path = tmp_path / name
    body = "".join(line.rstrip("\n") + newline for line in lines)
    path.write_bytes(body.encode("utf-8"))
    return path


def _line_ending_warnings(report) -> list[str]:
    return [d.message for d in report.warnings if "换行" in d.message]


# ---------------------------------------------------------------------------
# 1. 检测本身
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\r\nb\r\n", "crlf"),
        ("a\nb\n", "lf"),
        ("a\r\nb\nc\r\n", "mixed"),
        ("a\nb\r\n", "mixed"),
        ("abc", "none"),
        ("", "none"),
        ("\r\n", "crlf"),
        ("\n", "lf"),
        # 单独的 \r（老 Mac 风格）极罕见，与 LF 合并计 —— 对 cmd.exe 同样不是 CRLF
        ("a\rb\r", "lf"),
    ],
)
def test_detect_line_endings(text, expected):
    assert detect_line_endings(text) == expected


# ---------------------------------------------------------------------------
# 2. 只警告不阻断：真的 LF 文件
# ---------------------------------------------------------------------------


def test_lf_only_batch_gets_warning(tmp_path):
    path = _write(tmp_path, "lf.bat", "\n")
    result = convert_file(path, ConvertSettings(), write=False)
    assert result.error == ""
    assert result.text.strip()
    messages = _line_ending_warnings(result.report)
    assert len(messages) == 1
    assert "LF 换行" in messages[0]
    assert "cmd.exe" in messages[0]


def test_crlf_batch_gets_no_warning(tmp_path):
    path = _write(tmp_path, "crlf.bat", "\r\n")
    result = convert_file(path, ConvertSettings(), write=False)
    assert _line_ending_warnings(result.report) == []


def test_mixed_line_endings_get_warning(tmp_path):
    path = tmp_path / "mixed.bat"
    path.write_bytes(b"@echo off\r\necho a\necho b\r\n")
    result = convert_file(path, ConvertSettings(), write=False)
    messages = _line_ending_warnings(result.report)
    assert len(messages) == 1
    assert "混用" in messages[0]


def test_cmd_extension_is_covered(tmp_path):
    path = _write(tmp_path, "lf.cmd", "\n")
    result = convert_file(path, ConvertSettings(), write=False)
    assert len(_line_ending_warnings(result.report)) == 1


def test_powershell_lf_is_not_warned(tmp_path):
    """PowerShell 解析 LF 正常 —— 这条结论只属于 cmd.exe。"""
    path = tmp_path / "lf.ps1"
    path.write_bytes(b'Write-Output "a"\nWrite-Output "b"\n')
    result = convert_file(path, ConvertSettings(), write=False)
    assert _line_ending_warnings(result.report) == []


def test_warning_does_not_change_conversion_output(tmp_path):
    """**核心**：行尾只影响警告，不影响产物 —— 两版转换结果必须一字不差。"""
    # 同名文件放两个目录：脚本头会写源文件名，文件名不同会掩盖真实差异
    (tmp_path / "lf").mkdir()
    (tmp_path / "crlf").mkdir()
    lf = convert_file(_write(tmp_path / "lf", "demo.bat", "\n"), ConvertSettings(), write=False)
    crlf = convert_file(
        _write(tmp_path / "crlf", "demo.bat", "\r\n"), ConvertSettings(), write=False
    )
    assert lf.text == crlf.text
    assert lf.report.todo_count == crlf.report.todo_count
    assert lf.report.error_count == crlf.report.error_count
    assert crlf.report.warning_count + 1 == lf.report.warning_count
    assert lf.written is False  # write=False 时不写盘（警告不触发副作用）


def test_warning_is_reported_in_json(tmp_path):
    path = _write(tmp_path, "lf.bat", "\n")
    result = convert_file(path, ConvertSettings(), write=False)
    payload = json.loads(result.report.to_json())
    assert any("LF 换行" in item["message"] for item in payload["warnings"])
    assert payload["warning_count"] == len(payload["warnings"])


# ---------------------------------------------------------------------------
# 3. CLI 路径
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_PYTHON)}
    return subprocess.run(
        [sys.executable, "-m", "bat2sh", "--cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_report_json_surfaces_lf_warning(tmp_path):
    path = _write(tmp_path, "lf.bat", "\n")
    proc = _run_cli(str(path), "--dry-run", "--report-json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert any("LF 换行" in item["message"] for item in data["warnings"])


def test_cli_crlf_file_has_no_lf_warning(tmp_path):
    path = _write(tmp_path, "crlf.bat", "\r\n")
    proc = _run_cli(str(path), "--dry-run", "--report-json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert not any("LF 换行" in item["message"] for item in data["warnings"])
