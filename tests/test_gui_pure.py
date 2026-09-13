"""GUI 层纯函数测试：不构造 QApplication，无显示环境依赖。"""

from __future__ import annotations

from bat2sh.core.engine import output_path_for
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import ConvertReport, SourceKind
from bat2sh.gui.dialogs import build_diff_html
from bat2sh.gui.main_window import SourceFile, entry_to_result


def test_build_diff_html_contains_table_and_names():
    html = build_diff_html("echo a\n", 'echo "a"\n', "demo.bat", "demo.sh", dark=False)
    assert "<table" in html
    assert "demo.bat" in html
    assert "demo.sh" in html


def test_build_diff_html_color_mode():
    dark = build_diff_html("a\n", "b\n", "x.bat", "x.sh", dark=True)
    light = build_diff_html("a\n", "b\n", "x.bat", "x.sh", dark=False)
    assert "background:#232629" in dark
    assert "color:#eff0f1" in dark
    assert "background:#fcfcfc" in light
    assert "color:#232629" in light


def test_build_diff_html_escapes_markup():
    html = build_diff_html(
        "<script>alert(1)</script>\n", "safe\n", "a.bat", "a.sh", dark=False
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_entry_to_result_defaults(tmp_path):
    entry = SourceFile(path=tmp_path / "demo.bat", kind=SourceKind.BATCH)
    settings = ConvertSettings()
    result = entry_to_result(entry, settings)
    assert result.source_path == str(tmp_path / "demo.bat")
    assert result.output_path == str(output_path_for(tmp_path / "demo.bat", settings))
    assert result.encoding == "utf-8"
    assert result.text == ""
    assert result.kind is SourceKind.BATCH
    assert isinstance(result.report, ConvertReport)


def test_entry_to_result_passthrough(tmp_path):
    report = ConvertReport(source="demo.bat", kind=SourceKind.BATCH)
    entry = SourceFile(
        path=tmp_path / "demo.bat",
        kind=SourceKind.BATCH,
        source_text="raw",
        output_text="echo ok\n",
        detected_encoding="gbk",
        output_path=tmp_path / "custom.sh",
        report=report,
    )
    result = entry_to_result(entry, ConvertSettings())
    assert result.output_path == str(tmp_path / "custom.sh")
    assert result.encoding == "gbk"
    assert result.text == "echo ok\n"
    assert result.report is report
