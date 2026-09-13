"""GUI "转换并运行" 测试：离屏 QApplication、伪 QProcess、真实执行流。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QToolBar  # noqa: E402

from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.gui.main_window import (  # noqa: E402
    MainWindow,
    needs_todo_confirmation,
    todo_display_lines,
)
from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind  # noqa: E402

TODO_BAT = (
    "@echo off\n"
    'for /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
    "echo after-todo\n"
)
CLEAN_BAT = "@echo off\r\necho ran-ok\r\n"
SLEEP_BAT = "@echo off\r\ntimeout /t 2 /nobreak >nul\r\necho late\r\n"

_app: QApplication | None = None


def _ensure_app() -> QApplication:
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


class _FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeQProcess:
    instances: list["_FakeQProcess"] = []

    class ProcessChannelMode:
        MergedChannels = "merged"

    class ProcessState:
        NotRunning = "not-running"

    class ExitStatus:
        NormalExit = "normal"
        CrashExit = "crash"

    class ProcessError:
        FailedToStart = "failed-to-start"

    def __init__(self, parent=None):
        self.program = None
        self.arguments: list[str] = []
        self.working_directory = None
        self.channel_mode = None
        self.started = False
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.errorOccurred = _FakeSignal()
        _FakeQProcess.instances.append(self)

    def setProcessChannelMode(self, mode):
        self.channel_mode = mode

    def setWorkingDirectory(self, directory):
        self.working_directory = directory

    def setProgram(self, program):
        self.program = program

    def setArguments(self, arguments):
        self.arguments = list(arguments)

    def start(self):
        self.started = True

    def state(self):
        return _FakeQProcess.ProcessState.NotRunning

    def kill(self):
        pass


class _FakeDialog:
    instances: list["_FakeDialog"] = []
    result = QDialog.DialogCode.Accepted

    def __init__(self, title, header, body, confirm_text="执行", parent=None):
        self.title = title
        self.header = header
        self.body = body
        self.confirm_text = confirm_text
        _FakeDialog.instances.append(self)

    def exec(self):
        return _FakeDialog.result


@pytest.fixture()
def fake_process(monkeypatch):
    import bat2sh.gui.main_window as main_window_module

    _FakeQProcess.instances.clear()
    monkeypatch.setattr(main_window_module, "QProcess", _FakeQProcess)
    return _FakeQProcess


@pytest.fixture()
def fake_dialog(monkeypatch):
    import bat2sh.gui.main_window as main_window_module

    _FakeDialog.instances.clear()
    _FakeDialog.result = QDialog.DialogCode.Accepted
    monkeypatch.setattr(main_window_module, "RunConfirmDialog", _FakeDialog)
    return _FakeDialog


def make_bat(tmp_path: Path, text: str, name: str = "demo.bat") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_run_action_in_toolbar_and_panel_collapsible(window):
    assert window.action_run.text() == "转换并运行"
    toolbar = window.findChild(QToolBar)
    assert toolbar is not None
    assert toolbar.widgetForAction(window.action_run) is not None
    assert window.run_output.isHidden()
    window.run_toggle_button.setChecked(True)
    assert not window.run_output.isHidden()
    assert window.run_toggle_button.text() == "折叠"
    window.run_toggle_button.setChecked(False)
    assert window.run_output.isHidden()


def test_needs_todo_confirmation_and_lines():
    assert needs_todo_confirmation(None) is False
    report = ConvertReport(source="x.bat", kind=SourceKind.BATCH)
    assert needs_todo_confirmation(report) is False
    assert todo_display_lines(report) == []
    report.todos = [Diagnostic(2, "管道段", original="cmd | cmd")]
    assert needs_todo_confirmation(report) is True
    assert len(todo_display_lines(report)) == 1
    assert "第 2 行" in todo_display_lines(report)[0]


def test_run_starts_bash_in_script_dir(window, tmp_path, fake_process, fake_dialog):
    bat = make_bat(tmp_path, CLEAN_BAT)
    window.open_paths([bat])
    window.run_current()
    assert len(fake_process.instances) == 1
    process = fake_process.instances[0]
    assert process.program == "bash"
    assert process.working_directory == str(tmp_path)
    assert process.channel_mode == "merged"
    assert process.started
    script = Path(process.arguments[0])
    assert script.suffix == ".sh"
    assert 'echo "ran-ok"' in script.read_text(encoding="utf-8")
    assert [dialog.title for dialog in fake_dialog.instances] == ["执行确认"]
    assert fake_dialog.instances[0].body == window.current.output_text


def test_run_todo_dialog_cancel_aborts_start(
    window, tmp_path, fake_process, fake_dialog
):
    bat = make_bat(tmp_path, TODO_BAT)
    window.open_paths([bat])
    fake_dialog.result = QDialog.DialogCode.Rejected
    window.run_current()
    assert [dialog.title for dialog in fake_dialog.instances] == [
        "存在无法自动转换的语句"
    ]
    assert "for /f" in fake_dialog.instances[0].body
    assert fake_process.instances == []
    assert "已取消执行" in window.status_label.text()


def test_run_todo_accepted_then_preview_starts(
    window, tmp_path, fake_process, fake_dialog
):
    bat = make_bat(tmp_path, TODO_BAT)
    window.open_paths([bat])
    window.run_current()
    assert [dialog.title for dialog in fake_dialog.instances] == [
        "存在无法自动转换的语句",
        "执行确认",
    ]
    assert len(fake_process.instances) == 1
    assert fake_process.instances[0].started


def test_run_regenerates_when_editor_modified(
    window, tmp_path, fake_process, fake_dialog
):
    bat = make_bat(tmp_path, CLEAN_BAT)
    window.open_paths([bat])
    window.output_editor.setPlainText("echo tampered\n")
    window.run_current()
    preview = fake_dialog.instances[-1]
    assert preview.title == "执行确认"
    assert "tampered" not in preview.body
    assert preview.body == window.current.output_text


@pytest.mark.skipif(shutil.which("bash") is None, reason="未找到 bash")
def test_run_real_process_streams_to_panel(window, tmp_path, fake_dialog):
    bat = make_bat(tmp_path, CLEAN_BAT)
    window.open_paths([bat])
    window.run_current()
    process = window._run_process
    assert process is not None
    assert QSignalSpy(process.finished).wait(10000)
    assert "ran-ok" in window.run_output.toPlainText()
    assert "退出码 0" in window.run_status_label.text()
    assert window._run_tmp_path is None
    assert not window.run_output.isHidden()


@pytest.mark.skipif(shutil.which("bash") is None, reason="未找到 bash")
def test_run_timeout_kills_process(window, tmp_path, fake_dialog, monkeypatch):
    import bat2sh.gui.main_window as main_window_module

    monkeypatch.setattr(main_window_module, "RUN_TIMEOUT_MS", 300)
    bat = make_bat(tmp_path, SLEEP_BAT)
    window.open_paths([bat])
    window.run_current()
    process = window._run_process
    assert process is not None
    assert QSignalSpy(process.finished).wait(10000)
    assert "超时" in window.run_status_label.text()
    assert window._run_tmp_path is None
