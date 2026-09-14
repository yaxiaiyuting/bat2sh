"""report_blocks 与 report_level_color 的回归测试。"""

from __future__ import annotations

import re

from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind, report_blocks
from bat2sh.gui.theme import report_level_color


def _rich_report() -> ConvertReport:
    report = ConvertReport(source="demo.bat", kind=SourceKind.BATCH)
    report.total_lines = 10
    report.converted_lines = 8
    report.unchanged_lines = 2
    report.errors = [Diagnostic(1, "语法错误", category="syntax")]
    report.warnings = [Diagnostic(2, "路径一", category="path")]
    report.todos = [Diagnostic(5, "管道段", category="pipeline")]
    return report


def test_report_blocks_warnings_only():
    report = _rich_report()
    report.todos = []
    report.errors = []
    levels = [level for _text, level in report_blocks(report)]
    assert levels[:9] == ["info"] * 9
    assert "warning" in levels
    assert "todo" not in levels


def test_report_blocks_todos_only():
    report = _rich_report()
    report.warnings = []
    report.errors = []
    levels = [level for _text, level in report_blocks(report)]
    assert levels[:9] == ["info"] * 9
    assert "todo" in levels
    assert "warning" not in levels


def test_report_blocks_errors_only():
    report = _rich_report()
    report.warnings = []
    report.todos = []
    levels = [level for _text, level in report_blocks(report)]
    assert levels[:9] == ["info"] * 9
    assert "error" in levels
    assert "warning" not in levels
    assert "todo" not in levels


def test_report_blocks_sections_in_severity_order():
    levels = [level for _text, level in report_blocks(_rich_report())]
    assert levels.index("error") < levels.index("warning") < levels.index("todo")


def test_report_blocks_empty_report_has_only_info():
    report = ConvertReport(source="demo.bat", kind=SourceKind.BATCH)
    assert [level for _text, level in report_blocks(report)] == ["info"] * 9


def test_report_blocks_reconstructs_to_text():
    for report in (_rich_report(), ConvertReport(source="x.bat", kind=SourceKind.BATCH)):
        blocks = report_blocks(report)
        assert "\n".join(text for text, _level in blocks) == report.to_text()


def test_report_level_color_error_warning_todo_and_defaults():
    for level in ("error", "warning", "todo"):
        assert report_level_color(level, dark=True) is not None
        assert report_level_color(level, dark=False) is not None
    assert report_level_color("info", dark=True) is None
    assert report_level_color("info", dark=False) is None
    assert report_level_color("normal", dark=True) is None
    assert report_level_color("normal", dark=False) is None


def test_report_level_color_key_sets_consistent():
    for level in ("error", "warning", "todo"):
        assert report_level_color(level, dark=True) != report_level_color(level, dark=False)
    for level in ("info", "normal", "unknown", ""):
        assert report_level_color(level, dark=True) is None
        assert report_level_color(level, dark=False) is None


def test_report_level_color_hex_format():
    pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
    for level in ("error", "warning", "todo"):
        for dark in (True, False):
            color = report_level_color(level, dark)
            assert color is not None and pattern.match(color)
