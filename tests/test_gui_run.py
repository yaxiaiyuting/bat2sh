"""GUI "转换并运行" 测试：离屏 QApplication、伪 QProcess、真实执行流。"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
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
LOOP_PS1 = "while ($true) { Start-Sleep -Milliseconds 200 }\n"
CHILD_BAT = "@echo off\r\nstart /b sleep 654321\r\npause\r\n"
PAUSE_BAT = "@echo off\r\npause\r\necho after-pause\r\n"
SLEEP_PATTERN = r"^sleep 654321$"

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
    state_value = "not-running"

    class ProcessChannelMode:
        MergedChannels = "merged"

    class ProcessState:
        NotRunning = "not-running"
        Running = "running"

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
        self.killed = False
        self.written: list[bytes] = []
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
        return _FakeQProcess.state_value

    def processId(self):
        return None

    def write(self, data):
        self.written.append(bytes(data))

    def kill(self):
        self.killed = True


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
    _FakeQProcess.state_value = "not-running"
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
    assert process.program == "bash" or Path(process.program).name == "setsid"
    assert process.working_directory == str(tmp_path)
    assert process.channel_mode == "merged"
    assert process.started
    if Path(process.program).name == "setsid":
        assert process.arguments[0] == "bash"
        script = Path(process.arguments[1])
    else:
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
def test_run_timeout_kills_process(window, tmp_path, fake_dialog):
    """超时来自设置（可配置），不是写死的常量。"""
    window.settings.run_timeout = 0.3
    bat = make_bat(tmp_path, SLEEP_BAT)
    window.open_paths([bat])
    window.run_current()
    process = window._run_process
    assert process is not None
    assert QSignalSpy(process.finished).wait(10000)
    assert "超时" in window.run_status_label.text()
    assert not window.run_stop_button.isEnabled()
    assert window._run_tmp_path is None


def _pgrep_count(pattern: str) -> int:
    proc = subprocess.run(["pgrep", "-fc", pattern], capture_output=True, text=True)
    if proc.returncode != 0:
        return 0
    return int(proc.stdout.strip() or "0")


def test_run_panel_controls_start_disabled(window):
    assert not window.run_stop_button.isEnabled()
    assert not window.run_input.isEnabled()
    assert not window.run_send_button.isEnabled()
    assert window.run_input_row.isHidden()
    window.run_toggle_button.setChecked(True)
    assert not window.run_input_row.isHidden()


def test_run_controls_enable_while_running(window, tmp_path, fake_process, fake_dialog):
    bat = make_bat(tmp_path, CLEAN_BAT)
    window.open_paths([bat])
    window.run_current()
    assert window.run_stop_button.isEnabled()
    assert window.run_input.isEnabled()
    assert window.run_send_button.isEnabled()


@pytest.mark.skipif(shutil.which("bash") is None, reason="未找到 bash")
def test_stop_button_terminates_infinite_loop(window, tmp_path, fake_dialog):
    ps1 = make_bat(tmp_path, LOOP_PS1, name="loop.ps1")
    window.open_paths([ps1])
    window.run_current()
    process = window._run_process
    assert process is not None
    assert window._run_is_active()
    window.run_stop_button.click()
    assert QSignalSpy(process.finished).wait(10000)
    assert "已停止" in window.run_status_label.text()
    assert not window.run_stop_button.isEnabled()
    assert window._run_tmp_path is None


@pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("pgrep") is None,
    reason="未找到 bash/pgrep",
)
def test_stop_kills_child_process_group(window, tmp_path, fake_dialog):
    """停止必须终止整个进程组：后台子进程不遗留（孤儿）。"""
    bat = make_bat(tmp_path, CHILD_BAT)
    try:
        window.open_paths([bat])
        window.run_current()
        process = window._run_process
        assert process is not None
        deadline = time.time() + 5
        while time.time() < deadline and _pgrep_count(SLEEP_PATTERN) == 0:
            QApplication.processEvents()
            time.sleep(0.05)
        assert _pgrep_count(SLEEP_PATTERN) >= 1, "子进程未启动"
        window.run_stop_button.click()
        assert QSignalSpy(process.finished).wait(10000)
        deadline = time.time() + 5
        while time.time() < deadline and _pgrep_count(SLEEP_PATTERN):
            time.sleep(0.05)
        assert _pgrep_count(SLEEP_PATTERN) == 0, "子进程未随进程组终止"
    finally:
        subprocess.run(["pkill", "-f", SLEEP_PATTERN], capture_output=True)


@pytest.mark.skipif(shutil.which("bash") is None, reason="未找到 bash")
def test_send_input_unblocks_read(window, tmp_path, fake_dialog):
    bat = make_bat(tmp_path, PAUSE_BAT)
    window.open_paths([bat])
    window.run_current()
    process = window._run_process
    assert process is not None
    assert window.run_input.isEnabled()
    window.run_input.setText("hello")
    window.run_send_button.click()
    assert QSignalSpy(process.finished).wait(10000)
    panel = window.run_output.toPlainText()
    assert "> hello" in panel
    assert "after-pause" in panel
    assert "退出码 0" in window.run_status_label.text()
    assert not window.run_input.isEnabled()


def test_settings_dialog_roundtrips_run_timeout(tmp_path, monkeypatch):
    from bat2sh.gui.dialogs import SettingsDialog

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    _ensure_app()
    dialog = SettingsDialog(ConvertSettings(run_timeout=42.0))
    try:
        assert dialog.run_timeout_spin.value() == 42
        dialog.run_timeout_spin.setValue(15)
        assert dialog.result_settings().run_timeout == 15.0
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_close_while_running_asks_and_respects_choice(
    window, tmp_path, fake_process, fake_dialog, monkeypatch
):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox

    bat = make_bat(tmp_path, CLEAN_BAT)
    window.open_paths([bat])
    window.run_current()
    fake_process.state_value = "running"
    try:
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.No),
        )
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        assert not fake_process.instances[0].killed

        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
        )
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted()
        assert fake_process.instances[0].killed
    finally:
        window._run_process = None
        fake_process.state_value = "not-running"
