"""启动参数载入测试：离屏 QApplication，验证 argv → 文件列表 → 预览转换。

不显示窗口、不进入事件循环；直接构造 QMainWindow 并调用启动路径。
所有配置写入均由 ``XDG_CONFIG_HOME`` 隔离到临时目录。
"""

from __future__ import annotations

import os

import pytest

# 必须在构造 QApplication 之前选择离屏平台（CI 无显示环境）。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.gui.app import script_paths_from_argv  # noqa: E402
from bat2sh.gui.main_window import MainWindow  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    """保证进程内存在唯一的 QApplication，并防止其被垃圾回收。"""
    global _app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _app = app
    return app


@pytest.fixture()
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    _ensure_app()
    win = MainWindow(ConvertSettings())
    try:
        yield win
    finally:
        win.close()
        QApplication.processEvents()


def test_script_paths_from_argv_filters_options_and_suffixes():
    got = script_paths_from_argv(
        ["bat2sh", "a.bat", "B.CMD", "c.ps1", "note.txt", "-v", "--cli"]
    )
    assert [path.name for path in got] == ["a.bat", "B.CMD", "c.ps1"]


def test_script_paths_from_argv_empty():
    assert script_paths_from_argv(["bat2sh"]) == []
    assert script_paths_from_argv(["bat2sh", "-x", "--flag"]) == []


def test_startup_empty_argv_no_error(window):
    window.open_paths(script_paths_from_argv(["bat2sh"]))
    assert window.files == []
    assert window.file_list.count() == 0


def test_startup_single_bat_loads_and_converts(window, tmp_path):
    bat = tmp_path / "hello.bat"
    bat.write_text("@echo off\r\necho hello\r\n", encoding="utf-8")
    window.open_paths(script_paths_from_argv(["bat2sh", str(bat)]))
    assert [entry.path for entry in window.files] == [bat]
    assert window.current is not None
    assert window.current.path == bat
    assert "hello" in window.output_editor.toPlainText()
    # 停在预览态：不自动写出、不自动执行
    assert not (tmp_path / "hello.sh").exists()


def test_startup_mixed_argv_loads_only_scripts(window, tmp_path):
    bat = tmp_path / "a.bat"
    bat.write_text("echo a\r\n", encoding="utf-8")
    ps1 = tmp_path / "b.ps1"
    ps1.write_text('Write-Host "b"\n', encoding="utf-8")
    note = tmp_path / "note.txt"
    note.write_text("hi\n", encoding="utf-8")
    window.open_paths(
        script_paths_from_argv(["bat2sh", str(bat), str(note), str(ps1)])
    )
    assert sorted(entry.path.name for entry in window.files) == ["a.bat", "b.ps1"]
    assert window.current is not None
    assert window.current.path == ps1


def test_startup_missing_and_wrong_suffix_ignored_silently(window, tmp_path):
    missing = tmp_path / "missing.bat"
    window.open_paths(script_paths_from_argv(["bat2sh", str(missing)]))
    assert window.files == []
    window.open_paths([tmp_path / "note.txt"])
    assert window.files == []


def test_startup_duplicate_paths_deduplicated(window, tmp_path):
    bat = tmp_path / "dup.bat"
    bat.write_text("echo dup\r\n", encoding="utf-8")
    window.open_paths(script_paths_from_argv(["bat2sh", str(bat), str(bat)]))
    assert len(window.files) == 1
