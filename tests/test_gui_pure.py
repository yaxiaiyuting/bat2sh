"""GUI 层纯函数测试：不构造 QApplication，无显示环境依赖。"""

from __future__ import annotations

from bat2sh.core.engine import output_path_for
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import ConvertReport, SourceKind
from bat2sh.gui.dialogs import build_diff_html
from bat2sh.gui.main_window import (
    SourceFile,
    collect_script_paths,
    entry_to_result,
    filter_new_paths,
)
from bat2sh.gui.theme import (
    accent_color,
    diff_colors,
    palette_hex,
    status_text_color,
)


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


def test_collect_script_paths_filters_by_suffix(tmp_path):
    for name in ("a.bat", "b.CMD", "c.ps1", "d.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    got = collect_script_paths([tmp_path])
    assert sorted(p.name for p in got) == ["a.bat", "b.CMD", "c.ps1"]


def test_collect_script_paths_sorted_and_limited(tmp_path):
    for name in ("c.bat", "a.bat", "b.bat"):
        (tmp_path / name).write_text("", encoding="utf-8")
    got = collect_script_paths([tmp_path], limit=2)
    assert [p.name for p in got] == ["a.bat", "b.bat"]


def test_collect_script_paths_single_file_and_missing(tmp_path):
    script = tmp_path / "solo.bat"
    script.write_text("", encoding="utf-8")
    other = tmp_path / "note.txt"
    other.write_text("", encoding="utf-8")
    assert collect_script_paths([script]) == [script]
    assert collect_script_paths([tmp_path / "missing.bat", other]) == []


def test_filter_new_paths_dedupes_resolved_and_keeps_order(tmp_path):
    target = tmp_path / "a.bat"
    target.write_text("", encoding="utf-8")
    alias = tmp_path / "sub" / ".." / "a.bat"
    existing = set()
    got = filter_new_paths(existing, [target, alias])
    assert got == [target]
    assert existing == set()
    assert filter_new_paths({target.resolve()}, [target]) == []


def test_diff_colors_single_source_matches_palette_hex():
    for dark in (True, False):
        base, text = diff_colors(dark)
        assert (base, text) == (palette_hex(dark)["base"], palette_hex(dark)["text"])


def test_diff_colors_keep_committed_values():
    assert diff_colors(True) == ("#232629", "#eff0f1")
    assert diff_colors(False) == ("#fcfcfc", "#232629")


def test_accent_color_is_theme_highlight():
    assert accent_color(True) == accent_color(False) == "#3daee9"


def test_status_text_color_success_and_error_are_distinct_per_theme():
    for dark in (True, False):
        success = status_text_color("success", dark)
        error = status_text_color("error", dark)
        assert success is not None and error is not None
        assert success != error
    assert status_text_color("success", True) != status_text_color("success", False)
    assert status_text_color("success", True).startswith("#")
    assert status_text_color("info", True) is None
