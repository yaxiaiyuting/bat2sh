"""GUI 层纯函数测试：不构造 QApplication，无显示环境依赖。"""

from __future__ import annotations

from bat2sh.gui.dialogs import build_diff_html


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
