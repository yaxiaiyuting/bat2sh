"""GUI 启动入口。"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_DISPLAY_NAME, APP_ID, __version__
from ..core.settings import load_settings
from .main_window import SCRIPT_SUFFIXES, MainWindow
from .theme import apply_theme

MAX_LOG_BYTES = 1_000_000


def gui_log_path() -> Path:
    """GUI 诊断日志路径（XDG_STATE_HOME/bat2sh/gui.log，默认 ~/.local/state）。"""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "bat2sh" / "gui.log"


def install_gui_logging() -> None:
    """GUI 模式下把进程诊断输出（stdout/stderr）重定向到日志文件。

    .desktop / 终端启动的 GUI 不面向终端：Qt/KDE 警告（门户注册失败、KIO 提示）
    与未捕获异常不应污染启动它的终端，统一落到 :func:`gui_log_path`。
    打开或重定向失败时保持原行为，绝不抛出。
    """
    path = gui_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.write_text("", encoding="utf-8")
        log = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    sys.stdout = log
    sys.stderr = log
    log.write(
        f"=== bat2sh GUI {__version__} 启动 "
        f"{datetime.now():%Y-%m-%d %H:%M:%S} (pid {os.getpid()}) ===\n"
    )


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
    install_gui_logging()
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
