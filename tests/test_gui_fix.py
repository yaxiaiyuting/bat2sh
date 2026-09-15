"""GUI API 修复测试：设置页读写、TodoFixDialog 发送/应用/拒绝、主窗口接线（offscreen）。"""

from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bat2sh.gui.main_window as main_window_module  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox  # noqa: E402

from bat2sh.core.api.config import ApiConfig, load_api_config, save_api_config  # noqa: E402
from bat2sh.core.api.provider import ProviderNetworkError  # noqa: E402
from bat2sh.core.engine import convert_text  # noqa: E402
from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.core.types import SourceKind  # noqa: E402
from bat2sh.gui.dialogs import SettingsDialog, TodoFixDialog, TodoFixWorker  # noqa: E402
from bat2sh.gui.main_window import MainWindow  # noqa: E402

TODO_BAT = '@echo off\nfor /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
CLEAN_BAT = "@echo off\r\necho ran-ok\r\n"
DEGRADE_PS = "function f { [CmdletBinding()] param([string]$p) Write-Output $p }\nf\n"

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _app = app
    return app


def _converted(text: str, kind: SourceKind = SourceKind.BATCH):
    return convert_text(text, kind, ConvertSettings(), "demo.bat")


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class _FakeProvider:
    """脚本化流式 Provider（GUI 对话框用）。

    - ``reply``：单块正文（默认整段一次产出）；
    - ``chunks``：显式正文块序列（覆盖 ``reply``，用于检验逐块流式）；
    - ``error``：首次迭代时抛出（模拟调用即失败）；
    - ``reasoning``：在正文之前调用 ``on_reasoning`` 的次数（仅计数，无文本）；
    - ``mid_error``：产出第 2 块前抛出（模拟流中途异常）；
    - ``gate``：正文开始前阻塞，测试观察到思维链状态后再放行；
    - ``body_gate``：首块之后阻塞，测试在流中途触发取消后再放行。
    """

    def __init__(
        self,
        reply: str = "",
        error: Exception | None = None,
        *,
        chunks: list[str] | None = None,
        reasoning: int = 0,
        mid_error: Exception | None = None,
        gate: threading.Event | None = None,
        body_gate: threading.Event | None = None,
    ):
        self.reply = reply
        self.error = error
        self.chunks = list(chunks) if chunks is not None else None
        self.reasoning = reasoning
        self.mid_error = mid_error
        self.gate = gate
        self.body_gate = body_gate
        self.reasoning_text = ""
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, timeout: float) -> str:
        return "".join(self.complete_stream(prompt, timeout=timeout))

    def complete_stream(self, prompt: str, *, timeout: float, on_reasoning=None):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        reply_chunks = list(self.chunks) if self.chunks is not None else [self.reply]
        for count in range(1, self.reasoning + 1):
            if on_reasoning is not None:
                on_reasoning(count)
        if self.gate is not None:
            self.gate.wait(timeout=5.0)
        for index, chunk in enumerate(reply_chunks):
            if index and self.mid_error is not None:
                raise self.mid_error
            if index and self.body_gate is not None:
                self.body_gate.wait(timeout=5.0)
            yield chunk


def _make_api_config(**overrides) -> ApiConfig:
    values = dict(base_url="https://api.test/v1", model="demo-model")
    values.update(overrides)
    return ApiConfig(**values).normalized()


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


def make_bat(tmp_path, text: str, name: str = "demo.bat"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_settings_dialog_api_roundtrip():
    _ensure_app()
    api = _make_api_config(api_key="secret", timeout=12.0, context_lines=5)
    dialog = SettingsDialog(ConvertSettings(), api)
    try:
        assert dialog.api_base_edit.text() == "https://api.test/v1"
        assert dialog.api_model_edit.text() == "demo-model"
        assert dialog.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
        assert dialog.api_timeout_spin.value() == 12
        assert dialog.api_context_spin.value() == 5
        dialog.api_base_edit.setText("https://changed.test/v1/")
        dialog.api_timeout_spin.setValue(45)
        result = dialog.result_api_config()
        assert result.base_url == "https://changed.test/v1"
        assert result.timeout == 45.0
        assert result.api_key == "secret"
        assert result.model == "demo-model"
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_open_settings_persists_api_config(tmp_path, window, monkeypatch):
    saved = _make_api_config(base_url="https://saved.test/v1", model="saved-model")

    class _FakeSettingsDialog:
        class DialogCode:
            Accepted = "accepted"

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return "accepted"

        def result_settings(self):
            return ConvertSettings()

        def result_api_config(self):
            return saved

    monkeypatch.setattr(main_window_module, "SettingsDialog", _FakeSettingsDialog)
    window.open_settings()
    loaded = load_api_config()
    assert loaded.base_url == "https://saved.test/v1"
    assert loaded.model == "saved-model"
    assert window.api_config.base_url == "https://saved.test/v1"


def test_todo_fix_dialog_lists_markers_and_payload():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    dialog = TodoFixDialog(text, report, TODO_BAT, _make_api_config())
    try:
        assert dialog.marker_list.count() == 1
        assert ">>> " in dialog.payload_view.toPlainText()
        assert "https://api.test/v1" in dialog.privacy_label.text()
        assert not dialog.apply_button.isEnabled()
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_send_apply_updates_text():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(),
        provider_factory=lambda _config: _FakeProvider('echo "fixed-for"'),
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: dialog.apply_button.isEnabled())
        assert dialog.diff_view.toHtml()
        dialog.apply_button.click()
        assert dialog.applied_count == 1
        assert 'echo "fixed-for"' in dialog.result_text()
        assert "全部处理完成" in dialog.status_label.text()
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_rejects_bad_bash():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(),
        provider_factory=lambda _config: _FakeProvider('echo "unterminated'),
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: "未通过 bash -n" in dialog.status_label.text())
        assert not dialog.apply_button.isEnabled()
        assert "# TODO" in dialog.result_text()
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_failure_keeps_todo():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(api_key="sekret"),
        provider_factory=lambda _config: _FakeProvider(
            error=ProviderNetworkError("boom sekret")
        ),
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: "API 调用失败" in dialog.status_label.text())
        assert "sekret" not in dialog.status_label.text()
        assert dialog.send_button.isEnabled()
        assert dialog.applied_count == 0
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_streams_panel_then_applies():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(),
        provider_factory=lambda _config: _FakeProvider(
            chunks=['echo ', '"streamed-ok"']
        ),
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: 'echo "streamed-ok"' in dialog.stream_view.toPlainText())
        assert _wait_until(lambda: dialog.apply_button.isEnabled())
        assert dialog.diff_view.toHtml()
        dialog.apply_button.click()
        assert dialog.applied_count == 1
        assert 'echo "streamed-ok"' in dialog.result_text()
    finally:
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_reasoning_shows_count_only():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    gate = threading.Event()
    fake = _FakeProvider(chunks=['echo "reason-ok"'], reasoning=2, gate=gate)
    fake.reasoning_text = "思维链内部机密不应显示"
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(),
        provider_factory=lambda _config: fake,
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: "思考中" in dialog.status_label.text())
        assert "思维链 2 段" in dialog.status_label.text()
        assert fake.reasoning_text not in dialog.stream_view.toPlainText()
        gate.set()
        assert _wait_until(lambda: dialog.apply_button.isEnabled())
        panel = dialog.stream_view.toPlainText()
        assert 'echo "reason-ok"' in panel
        assert "思维链" not in panel
    finally:
        gate.set()
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_dialog_stop_cancel_keeps_todo():
    _ensure_app()
    text, report = _converted(TODO_BAT)
    gate = threading.Event()
    fake = _FakeProvider(chunks=['echo "partial"', 'echo "rest"'], body_gate=gate)
    dialog = TodoFixDialog(
        text,
        report,
        TODO_BAT,
        _make_api_config(),
        provider_factory=lambda _config: fake,
    )
    try:
        dialog.send_button.click()
        assert _wait_until(lambda: 'echo "partial"' in dialog.stream_view.toPlainText())
        assert dialog.stop_button.isEnabled()
        dialog.stop_button.click()
        assert "正在停止接收" in dialog.status_label.text()
        assert not dialog.stop_button.isEnabled()
        gate.set()
        assert _wait_until(lambda: "已停止接收" in dialog.status_label.text())
        assert dialog.send_button.isEnabled()
        assert dialog.skip_button.isEnabled()
        assert not dialog.stop_button.isEnabled()
        assert not dialog.apply_button.isEnabled()
        assert dialog.diff_view.toPlainText() == ""
        panel = dialog.stream_view.toPlainText()
        assert 'echo "partial"' in panel
        assert 'echo "rest"' not in panel
        assert "# TODO" in dialog.result_text()
        assert dialog.applied_count == 0
    finally:
        gate.set()
        dialog.deleteLater()
        QApplication.processEvents()


def test_todo_fix_worker_cancel_during_reasoning_emits_cancelled():
    """思考阶段点击停止：下一次思维链回调即触发取消（无需等待正文块），且不产出成功结果。"""
    _ensure_app()
    events: list[str] = []
    worker_ref: dict = {}

    class _ReasoningCancelProvider:
        """模拟：思考阶段用户点了“停止接收”，随后仍有一段思维链回调。"""

        def complete(self, prompt: str, *, timeout: float) -> str:
            return "".join(self.complete_stream(prompt, timeout=timeout))

        def complete_stream(self, prompt: str, *, timeout: float, on_reasoning=None):
            if on_reasoning is not None:
                on_reasoning(1)
            worker_ref["worker"].request_cancel()  # 模拟用户点击“停止接收”
            if on_reasoning is not None:
                on_reasoning(2)  # 回调内应立即取消
            yield 'echo "never"'

    worker = TodoFixWorker(_ReasoningCancelProvider(), "prompt", 1.0)
    worker_ref["worker"] = worker
    worker.cancelled.connect(lambda: events.append("cancelled"))
    worker.failed.connect(lambda message: events.append(f"failed:{message}"))
    worker.succeeded.connect(lambda raw: events.append(f"succeeded:{raw}"))
    worker.run()  # 同步驱动：确定性验证“思考阶段取消”路径
    assert events == ["cancelled"]


def test_main_window_fix_action_enabled_after_conversion(window, tmp_path):
    assert window.action_fix_todos.text() == "API 修复 TODO"
    todo = make_bat(tmp_path, TODO_BAT)
    window.open_paths([todo])
    assert window.action_fix_todos.isEnabled()
    window.clear_files()
    assert not window.action_fix_todos.isEnabled()
    clean = make_bat(tmp_path, CLEAN_BAT, "clean.bat")
    window.open_paths([clean])
    assert not window.action_fix_todos.isEnabled()


def test_main_window_fix_todos_applies_dialog_result(window, tmp_path, monkeypatch):
    save_api_config(_make_api_config())
    window.api_config = load_api_config()
    todo = make_bat(tmp_path, TODO_BAT)
    window.open_paths([todo])

    class _FakeTodoFixDialog:
        applied_count = 2

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def result_text(self):
            return "echo fixed-all\n"

    monkeypatch.setattr(main_window_module, "TodoFixDialog", _FakeTodoFixDialog)
    window.fix_todos()
    assert window.output_editor.toPlainText() == "echo fixed-all\n"
    assert window.current.output_text == "echo fixed-all\n"
    assert "已应用 2 处" in window.status_label.text()


def test_main_window_fix_todos_missing_config_warns(window, tmp_path, monkeypatch):
    todo = make_bat(tmp_path, TODO_BAT)
    window.open_paths([todo])
    calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: calls.append(args[2] if len(args) > 2 else "")),
    )
    window.fix_todos()
    assert calls and "API 配置不完整" in calls[0]


def test_main_window_fix_todos_degraded_info(window, tmp_path, monkeypatch):
    ps = make_bat(tmp_path, DEGRADE_PS, "degraded.ps1")
    window.open_paths([ps])
    assert not window.action_fix_todos.isEnabled()
    calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: calls.append(args[2] if len(args) > 2 else "")),
    )
    window.fix_todos()
    assert calls and "已整体降级" in calls[0]


def test_main_window_fix_todos_rejected_dialog_keeps_editor(window, tmp_path, monkeypatch):
    save_api_config(_make_api_config())
    window.api_config = load_api_config()
    todo = make_bat(tmp_path, TODO_BAT)
    window.open_paths([todo])
    original = window.output_editor.toPlainText()

    class _RejectedDialog:
        applied_count = 0

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

        def result_text(self):
            return "echo should-not-apply\n"

    monkeypatch.setattr(main_window_module, "TodoFixDialog", _RejectedDialog)
    window.fix_todos()
    assert window.output_editor.toPlainText() == original
