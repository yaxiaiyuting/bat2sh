"""设置页"测试连接"按钮测试：offscreen + mock transport，不真实调用 API。"""

from __future__ import annotations

import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from bat2sh.core.api.config import ApiConfig  # noqa: E402
from bat2sh.core.api.provider import (  # noqa: E402
    OpenAICompatibleProvider,
    TransportNetworkError,
    TransportTimeoutError,
)
from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.gui.dialogs import ConnectionTestWorker, SettingsDialog  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _app = app
    return app


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class _FakeTransport:
    """按序返回预设响应：``(status, body)`` 元组或待抛出的异常实例。"""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict, bytes, float]] = []

    def request(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _factory(transport: _FakeTransport):
    def _create(config: ApiConfig) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(config, transport=transport, sleep=lambda _delay: None)

    return _create


def _make_dialog(transport: _FakeTransport, **config_overrides) -> SettingsDialog:
    _ensure_app()
    values = dict(base_url="https://api.test/v1", model="demo-model", api_key="test-key")
    values.update(config_overrides)
    config = ApiConfig(**values).normalized()
    return SettingsDialog(ConvertSettings(), config, api_test_factory=_factory(transport))


def _chat_ok(content: str = "ok") -> tuple[int, bytes]:
    payload = {"choices": [{"message": {"content": content}}]}
    return 200, json.dumps(payload).encode("utf-8")


def test_connection_test_success_reports_latency():
    transport = _FakeTransport(_chat_ok())
    dialog = _make_dialog(transport)
    dialog.api_test_button.click()
    assert _wait_until(lambda: "✓" in dialog.api_test_status.text())
    text = dialog.api_test_status.text()
    assert "连接成功" in text and "ms" in text
    url, headers, body, timeout = transport.calls[0]
    assert url == "https://api.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert timeout == ConnectionTestWorker.TIMEOUT == 10.0
    payload = json.loads(body)
    assert payload["model"] == "demo-model"
    assert payload["messages"][0]["content"] == ConnectionTestWorker.PROMPT
    assert _wait_until(lambda: dialog.api_test_button.isEnabled())
    assert dialog._test_worker is None
    dialog.close()


def test_connection_test_success_tooltip_redacts_key():
    transport = _FakeTransport(_chat_ok("your key is test-key"))
    dialog = _make_dialog(transport)
    dialog.api_test_button.click()
    assert _wait_until(
        lambda: dialog._test_worker is None and "✓" in dialog.api_test_status.text()
    )
    tooltip = dialog.api_test_status.toolTip()
    assert "test-key" not in tooltip and "***" in tooltip
    dialog.close()


def test_connection_test_timeout_classified():
    transport = _FakeTransport(
        TransportTimeoutError("timed out"), TransportTimeoutError("timed out")
    )
    dialog = _make_dialog(transport)
    dialog.api_test_button.click()
    assert _wait_until(lambda: "✗" in dialog.api_test_status.text())
    assert "超时" in dialog.api_test_status.text()
    assert len(transport.calls) == 2  # 默认 max_retries=1：超时重试一次
    assert _wait_until(lambda: dialog.api_test_button.isEnabled())
    dialog.close()


def test_connection_test_auth_failure_not_retried():
    transport = _FakeTransport((401, b"{}"))
    dialog = _make_dialog(transport)
    dialog.api_test_button.click()
    assert _wait_until(lambda: "✗" in dialog.api_test_status.text())
    assert "认证" in dialog.api_test_status.text()
    assert len(transport.calls) == 1
    dialog.close()


def test_connection_test_network_error_redacts_key():
    transport = _FakeTransport(
        TransportNetworkError("connect failed for key=test-key"),
        TransportNetworkError("connect failed for key=test-key"),
    )
    dialog = _make_dialog(transport, api_key="test-key")
    dialog.api_test_button.click()
    assert _wait_until(lambda: "✗" in dialog.api_test_status.text())
    text = dialog.api_test_status.text()
    assert "网络" in text
    assert "test-key" not in text and "***" in text
    dialog.close()


def test_connection_test_missing_config_without_factory_call():
    _ensure_app()
    calls: list[ApiConfig] = []

    def _factory_should_not_run(config: ApiConfig):
        calls.append(config)
        raise AssertionError("缺少配置时不应构造 provider")

    dialog = SettingsDialog(
        ConvertSettings(),
        ApiConfig(),
        api_test_factory=_factory_should_not_run,
    )
    dialog.api_test_button.click()
    assert "缺少配置" in dialog.api_test_status.text()
    assert dialog.api_test_status.text().startswith("✗")
    assert calls == []
    dialog.close()


def test_connection_test_status_cleared_when_config_changes():
    transport = _FakeTransport(_chat_ok())
    dialog = _make_dialog(transport)
    dialog.api_test_button.click()
    assert _wait_until(
        lambda: "✓" in dialog.api_test_status.text() and dialog._test_worker is None
    )
    dialog.api_model_edit.setText("another-model")
    assert dialog.api_test_status.text() == ""
    dialog.close()
