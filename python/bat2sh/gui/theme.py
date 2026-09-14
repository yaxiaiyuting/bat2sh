"""主题处理：默认跟随系统，可切换深色/浅色。

优先使用 Qt 6.5+ 的 QStyleHints.setColorScheme（KDE/Wayland 下表现最佳），
在不支持的版本上退化为手工调色板。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _color_scheme(name: str):
    try:
        return getattr(Qt.ColorScheme, name)
    except AttributeError:
        return None


def system_is_dark(app: QApplication) -> bool:
    try:
        current = app.styleHints().colorScheme()
        if current == _color_scheme("Dark"):
            return True
        if current == _color_scheme("Light"):
            return False
    except AttributeError:
        pass
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(49, 54, 59)
    base = QColor(35, 38, 41)
    text = QColor(239, 240, 241)
    button = QColor(61, 66, 71)
    highlight = QColor(61, 174, 233)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 145, 150))
    disabled = QColor(120, 125, 130)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return palette


def light_palette() -> QPalette:
    palette = QPalette()
    window = QColor(239, 240, 241)
    base = QColor(252, 252, 252)
    text = QColor(35, 38, 41)
    button = QColor(239, 240, 241)
    highlight = QColor(61, 174, 233)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(41, 128, 185))
    return palette


def apply_theme(app: QApplication, mode: str) -> bool:
    """应用主题，返回当前是否为深色。"""
    mode = mode if mode in ("system", "light", "dark") else "system"
    hints = app.styleHints()
    scheme_name = {"system": "Unknown", "light": "Light", "dark": "Dark"}[mode]
    scheme = _color_scheme(scheme_name)
    switched = False
    if scheme is not None:
        try:
            hints.setColorScheme(scheme)
            switched = hints.colorScheme() == scheme
        except AttributeError:
            switched = False
    if mode == "system":
        dark = system_is_dark(app)
        if not switched:
            app.setPalette(app.style().standardPalette())
    else:
        dark = mode == "dark"
        if not switched:
            app.setPalette(dark_palette() if dark else light_palette())
    return dark


def report_level_color(level: str, dark: bool) -> str | None:
    """报告行级别 → 前景色 hex；info/normal → None（使用默认前景色）。"""
    colors = {
        "error": "#ff6b6b" if dark else "#c62828",
        "warning": "#ffb454" if dark else "#b26a00",
        "todo": "#8c9196" if dark else "#787d82",
    }
    return colors.get(level)
