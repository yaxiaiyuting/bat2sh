"""GUI 启动入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_DISPLAY_NAME, APP_ID, __version__
from ..core.settings import load_settings
from .main_window import MainWindow
from .theme import apply_theme


def bundled_icon() -> QIcon:
    path = Path(__file__).resolve().parents[1] / "data" / "bat2sh.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon.fromTheme("text-x-script")


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
    file_args = [arg for arg in args[1:] if not arg.startswith("-")]
    if file_args:
        window.open_paths([Path(arg) for arg in file_args])
    window.show()
    return app.exec()
