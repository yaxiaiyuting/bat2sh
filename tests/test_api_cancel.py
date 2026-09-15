"""v1.8.0 主体二：取消在途请求必须 <1s 生效（socket shutdown）。

硬约束（设计 §3.3.1）：只有 `shutdown(SHUT_RDWR)` 能打断阻塞读；
`close()` / `response.close()` 不能。本文件含**显式断言**守护该约束。
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time

import pytest

from bat2sh.core.api import provider as provider_module
from bat2sh.core.api.config import ApiConfig
from bat2sh.core.api.provider import (
    CancelAwareTransport,
    OpenAICompatibleProvider,
    ProviderCancelledError,
)

STALL_SECONDS = 30.0


class _StallHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for index in range(2):
            payload = (
                f'data: {{"choices":[{{"delta":{{"content":"c{index}"}}}}]}}\n\n'.encode()
            )
            self.wfile.write(f"{len(payload):X}\r\n".encode() + payload + b"\r\n")
            self.wfile.flush()
            time.sleep(0.05)
        time.sleep(STALL_SECONDS)


@pytest.fixture
def stall_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StallHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def _provider(port: int) -> tuple[OpenAICompatibleProvider, CancelAwareTransport]:
    config = ApiConfig(
        provider="openai", base_url=f"http://127.0.0.1:{port}/v1", model="m"
    )
    transport = CancelAwareTransport()
    return OpenAICompatibleProvider(config, transport=transport), transport


def test_cancel_interrupts_blocked_read_under_one_second(stall_server):
    provider, transport = _provider(stall_server.server_address[1])
    outcome: dict = {}

    def worker() -> None:
        try:
            list(provider.complete_stream("hi", timeout=30))
            outcome["status"] = "completed"
        except ProviderCancelledError:
            outcome["status"] = "cancelled"
        except BaseException as exc:  # noqa: BLE001
            outcome["status"] = f"error:{type(exc).__name__}"

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    time.sleep(1.0)
    start = time.perf_counter()
    hits = transport.cancel_in_flight()
    thread.join(timeout=5)
    elapsed = time.perf_counter() - start

    assert hits >= 1
    assert outcome["status"] == "cancelled"
    assert elapsed < 1.0, f"取消耗时 {elapsed:.3f}s，未达 <1s"


def test_cancel_uses_shutdown_never_close(monkeypatch):
    """硬约束断言：取消路径必须调用 shutdown，绝不能退化为 close。"""
    transport = CancelAwareTransport()
    transport._active[1] = object()
    calls: dict = {"shutdown": [], "close": []}

    class _SpySocket:
        def shutdown(self, how):
            calls["shutdown"].append(how)

        def close(self):
            calls["close"].append(True)

    spy = _SpySocket()
    monkeypatch.setattr(provider_module, "_socket_of", lambda response: spy)
    hits = transport.cancel_in_flight()

    assert hits == 1
    assert calls["shutdown"] == [socket.SHUT_RDWR]
    assert calls["close"] == [], "取消路径不得使用 close()（无法打断阻塞读）"


def test_cancel_skips_when_socket_unavailable(monkeypatch):
    transport = CancelAwareTransport()
    transport._active[1] = object()
    monkeypatch.setattr(provider_module, "_socket_of", lambda response: None)
    assert transport.cancel_in_flight() == 0


def test_cancel_converts_to_cancelled_error_not_network_error(stall_server):
    provider, transport = _provider(stall_server.server_address[1])
    errors: list = []

    def worker() -> None:
        try:
            list(provider.complete_stream("hi", timeout=30))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    time.sleep(0.8)
    transport.cancel_in_flight()
    thread.join(timeout=5)

    assert len(errors) == 1
    assert isinstance(errors[0], ProviderCancelledError)


def test_cancel_is_not_retryable():
    from bat2sh.core.api.provider import RETRYABLE_ERRORS

    assert ProviderCancelledError not in RETRYABLE_ERRORS


def test_no_cancel_still_times_out_on_idle(stall_server):
    """无取消时，chunk 间空闲超时语义不变（此处用短超时验证仍会超时）。"""
    from bat2sh.core.api.provider import ProviderTimeoutError

    provider, _ = _provider(stall_server.server_address[1])
    with pytest.raises(ProviderTimeoutError):
        list(provider.complete_stream("hi", timeout=0.5))


def test_provider_without_cancel_transport_returns_zero():
    class _NoCancel:
        def request_stream(self, url, headers, body, timeout):
            return 200, iter([])

    config = ApiConfig(provider="openai", base_url="http://localhost/v1", model="m")
    provider = OpenAICompatibleProvider(config, transport=_NoCancel())
    assert provider.cancel_in_flight() == 0
