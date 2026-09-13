"""GUI 启动入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_DISPLAY_NAME, APP_ID, __version__
from ..core.settings import load_settings
from .main_window import SCRIPT_SUFFIXES, MainWindow
from .theme import apply_theme


def bundled_icon() -> QIcon:
    path = Path(__file__).resolve().parents[1] / "data" / "bat2sh.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon.fromTheme("text-x-script")


def script_paths_from_argv(argv: list[str]) -> list[Path]:
    """从启动参数中提取脚本路径。

    跳过 ``argv[0]``（程序名）、以 ``-`` 开头的选项以及后缀不符的参数；
    路径不存在时由 :meth:`MainWindow.add_paths` 静默忽略。
    """
    return [
        Path(arg)
        for arg in argv[1:]
        if not arg.startswith("-") and Path(arg).suffix.lower() in SCRIPT_SUFFIXES
    ]


def run_gui(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv)
    app = QApplication(args)
    app.setApplicationName("bat2sh")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setOrganizationName("bat2sh")
    app.setWindowIcon(QIcon.fromTheme("bat2sh", bundled_icon()))

    settings = load_settings()
    apply_theme(app, settings.theme)
    window = MainWindow(settings)
    file_paths = script_paths_from_argv(args)
    if file_paths:
        window.open_paths(file_paths)
    window.show()
    return app.exec()
