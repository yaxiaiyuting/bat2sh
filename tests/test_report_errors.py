"""三色报告 errors 层回归测试：分类规则 / JSON 字段 / GUI 计数与着色。"""

from __future__ import annotations

import json

from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind, report_blocks
from bat2sh.gui.main_window import (
    counts_text,
    error_display_lines,
    needs_todo_confirmation,
)
from bat2sh.gui.theme import report_level_color

LABEL_IN_BLOCK = "@echo off\nif 1==1 (\n:SKIP\necho done\n)\n"


# ----------------------------------------------------------------------
# 分类规则：什么算 error
# ----------------------------------------------------------------------
def test_label_in_control_block_is_error(convert_bat):
    out, report = convert_bat(LABEL_IN_BLOCK)
    assert report.error_count == 1
    assert report.todo_count == 0
    diagnostic = report.errors[0]
    assert diagnostic.category == "control_flow"
    assert "位于控制块内" in diagnostic.message
    # 生成脚本中的注释约定保持不变，便于用户统一检索
    assert "# TODO: 手动检查" in out


def test_top_level_label_is_not_error(convert_bat):
    _out, report = convert_bat("@echo off\n:TOP\necho done\n")
    assert report.error_count == 0
    assert report.todo_count == 0


def test_plain_warning_case_stays_warning(convert_bat):
    _out, report = convert_bat("@echo off\nipconfig\n")
    assert report.warning_count == 1
    assert report.error_count == 0


def test_bash_n_failure_is_error(monkeypatch, bash_check):
    from bat2sh.core.batch import BatchConverter
    from bat2sh.core.settings import ConvertSettings

    broken = "#!/usr/bin/env bash\nif\n"
    converter = BatchConverter(ConvertSettings(), "broken.bat")
    monkeypatch.setattr(converter, "_compose", lambda: broken)
    out = converter.convert("@echo off\necho hi\n")
    bash_check(out)
    assert converter.report.error_count == 1
    assert converter.report.todos == []
    assert converter.report.errors[0].category == "syntax"


# ----------------------------------------------------------------------
# JSON 字段
# ----------------------------------------------------------------------
def _report_with_errors() -> ConvertReport:
    report = ConvertReport(source="demo.bat", kind=SourceKind.BATCH)
    report.errors = [
        Diagnostic(6, "必须人工处理: 标签 :SKIP 位于控制块内", original=":SKIP", category="control_flow")
    ]
    report.warnings = [Diagnostic(1, "路径一", category="path")]
    report.todos = [Diagnostic(2, "待办一", category="pipeline")]
    return report


def test_to_dict_contains_errors_field():
    data = _report_with_errors().to_dict()
    assert data["error_count"] == 1
    assert data["warning_count"] == 1
    assert data["todo_count"] == 1
    assert data["errors"][0]["line"] == 6
    assert data["errors"][0]["category"] == "control_flow"
    assert data["errors"][0]["original"] == ":SKIP"
    assert set(data["errors"][0]) == {"line", "category", "message", "original"}


def test_to_json_roundtrip_includes_errors():
    payload = _report_with_errors().to_json()
    data = json.loads(payload)
    assert data["error_count"] == 1
    assert "位于控制块内" in data["errors"][0]["message"]


def test_report_blocks_order_error_before_warning_before_todo():
    levels = [level for _text, level in report_blocks(_report_with_errors())]
    assert levels.index("error") < levels.index("warning") < levels.index("todo")
    assert "错误数量    : 1" in "\n".join(text for text, _ in report_blocks(_report_with_errors()))


# ----------------------------------------------------------------------
# GUI 计数与纯函数
# ----------------------------------------------------------------------
def test_counts_text_none_defaults():
    assert counts_text(None) == "错误 0 · 警告 0 · TODO 0 · 已转换 0/0"


def test_counts_text_reports_three_levels():
    report = _report_with_errors()
    report.total_lines = 10
    report.converted_lines = 7
    text = counts_text(report)
    assert text == "错误 1 · 警告 1 · TODO 1 · 已转换 7/10"


def test_needs_todo_confirmation_includes_errors():
    report = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    assert needs_todo_confirmation(report) is False
    report.errors = [Diagnostic(1, "必须人工处理", category="syntax")]
    assert needs_todo_confirmation(report) is True


def test_error_display_lines_format():
    report = _report_with_errors()
    lines = error_display_lines(report)
    assert len(lines) == 1
    assert "第 6 行" in lines[0]


def test_report_level_color_error_is_red_family():
    dark = report_level_color("error", dark=True)
    light = report_level_color("error", dark=False)
    assert dark is not None and light is not None and dark != light
    assert report_level_color("info", dark=True) is None
