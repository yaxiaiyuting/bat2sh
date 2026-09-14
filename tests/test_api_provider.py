"""Provider 层测试：FakeTransport 覆盖成功/鉴权/限流/5xx/超时/坏 JSON 与重试。

本模块带 socket 守卫（autouse）：任何真实网络连接都会让测试失败。
"""

from __future__ import annotations

import json
import socket

import pytest

from bat2sh.core.api.config import ApiConfig
from bat2sh.core.api.provider import (
    OpenAICompatibleProvider,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderNetworkError,
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
    ProviderTimeoutError,
    TransportNetworkError,
    TransportTimeoutError,
    create_provider,
    error_category,
    redact,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - 触发即测试失败
        raise AssertionError("测试不得访问真实网络")

    monkeypatch.setattr(socket, "socket", _boom)


class FakeTransport:
    """按脚本依次返回响应/抛错；记录调用与请求内容。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request(self, url, headers, body, timeout):
        self.calls.append(
            {"url": url, "headers": dict(headers), "body": body, "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("FakeTransport 无更多预置响应")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_provider(responses, **overrides):
    values = dict(
        base_url="https://api.example.test/v1",
        model="demo-model",
        api_key="sk-secret",
    )
    values.update(overrides)
    config = ApiConfig(**values).normalized()
    transport = FakeTransport(responses)
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=lambda _s: None)
    return provider, transport


def ok_body(content: str = "echo fixed"):
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode("utf-8")


def test_complete_success_sends_expected_request():
    provider, transport = make_provider([(200, ok_body('echo "fixed"'))])
    result = provider.complete("PROMPT", timeout=9.5)
    assert result == 'echo "fixed"'
    call = transport.calls[0]
    assert call["url"] == "https://api.example.test/v1/chat/completions"
    assert call["timeout"] == 9.5
    assert call["headers"]["Authorization"] == "Bearer sk-secret"
    assert call["headers"]["Content-Type"] == "application/json"
    body = json.loads(call["body"].decode("utf-8"))
    assert body["model"] == "demo-model"
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert body["temperature"] == 0
    assert body["stream"] is False


def test_complete_without_key_omits_authorization():
    config = ApiConfig(base_url="http://localhost:11434/v1", model="llama").normalized()
    transport = FakeTransport([(200, ok_body())])
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=lambda _s: None)
    assert provider.complete("p", timeout=1.0) == "echo fixed"
    assert "Authorization" not in transport.calls[0]["headers"]


def test_base_url_trailing_slash_normalized():
    provider, transport = make_provider([(200, ok_body())], base_url="https://a.test/v1/")
    provider.complete("p", timeout=1.0)
    assert transport.calls[0]["url"] == "https://a.test/v1/chat/completions"


def test_auth_error_not_retried():
    provider, transport = make_provider([(401, b"nope"), (200, ok_body())])
    with pytest.raises(ProviderAuthError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1
    assert "sk-secret" not in str(ProviderAuthError("鉴权失败（HTTP 401）"))


def test_rate_limit_retried_then_success():
    provider, transport = make_provider([(429, b""), (200, ok_body("done"))])
    assert provider.complete("p", timeout=1.0) == "done"
    assert len(transport.calls) == 2


def test_rate_limit_exhausts_retries():
    provider, transport = make_provider([(429, b""), (429, b""), (200, ok_body())])
    with pytest.raises(ProviderRateLimitError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 2  # 默认 max_retries=1 → 1 次重试


def test_server_error_retried():
    provider, transport = make_provider([(503, b""), (200, ok_body())])
    assert provider.complete("p", timeout=1.0) == "echo fixed"
    assert len(transport.calls) == 2


def test_server_error_exhausted():
    provider, _ = make_provider([(500, b""), (500, b"")])
    with pytest.raises(ProviderServerError):
        provider.complete("p", timeout=1.0)


def test_timeout_error_retried():
    provider, transport = make_provider([TransportTimeoutError("slow"), (200, ok_body())])
    assert provider.complete("p", timeout=1.0) == "echo fixed"
    assert len(transport.calls) == 2


def test_timeout_exhausted():
    provider, _ = make_provider([TransportTimeoutError("slow"), TransportTimeoutError("slow")])
    with pytest.raises(ProviderTimeoutError):
        provider.complete("p", timeout=1.0)


def test_network_error_retried():
    provider, transport = make_provider([TransportNetworkError("dns"), (200, ok_body())])
    assert provider.complete("p", timeout=1.0) == "echo fixed"
    assert len(transport.calls) == 2


def test_network_error_exhausted():
    provider, _ = make_provider([TransportNetworkError("dns"), TransportNetworkError("dns")])
    with pytest.raises(ProviderNetworkError):
        provider.complete("p", timeout=1.0)


def test_bad_json_protocol_error_not_retried():
    provider, transport = make_provider([(200, b"{not json"), (200, ok_body())])
    with pytest.raises(ProviderProtocolError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_missing_content_protocol_error():
    provider, _ = make_provider([(200, json.dumps({"choices": []}).encode())])
    with pytest.raises(ProviderProtocolError):
        provider.complete("p", timeout=1.0)


def test_empty_content_protocol_error():
    provider, _ = make_provider([(200, json.dumps({"choices": [{"message": {"content": ""}}]}).encode())])
    with pytest.raises(ProviderProtocolError):
        provider.complete("p", timeout=1.0)


def test_other_4xx_request_error_not_retried():
    provider, transport = make_provider([(400, b"bad request"), (200, ok_body())])
    with pytest.raises(ProviderRequestError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_max_retries_zero_no_retry():
    provider, transport = make_provider([(500, b"")], max_retries=0)
    with pytest.raises(ProviderServerError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_backoff_schedule():
    sleeps: list[float] = []
    config = ApiConfig(
        base_url="https://a.test/v1", model="m", max_retries=2
    ).normalized()
    transport = FakeTransport([(500, b""), (500, b""), (200, ok_body())])
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=sleeps.append)
    assert provider.complete("p", timeout=1.0) == "echo fixed"
    assert sleeps == [1.0, 2.0]


def test_create_provider_rejects_unknown_provider():
    with pytest.raises(ProviderConfigError):
        create_provider(ApiConfig(provider="ollama", base_url="u", model="m"))


def test_create_provider_requires_base_and_model():
    with pytest.raises(ProviderConfigError):
        create_provider(ApiConfig(model="m"))
    with pytest.raises(ProviderConfigError):
        create_provider(ApiConfig(base_url="https://a.test/v1"))
    provider = create_provider(ApiConfig(base_url="https://a.test/v1", model="m"))
    assert isinstance(provider, OpenAICompatibleProvider)


def test_redact_hides_secrets():
    assert redact("key=sk-secret xx", "sk-secret") == "key=*** xx"
    assert redact("nothing", "") == "nothing"
    assert redact("a sk-1 b sk-1 c", "sk-1") == "a *** b *** c"


@pytest.mark.parametrize(
    ("exc", "label"),
    [
        (ProviderConfigError("x"), "配置"),
        (ProviderAuthError("x"), "认证"),
        (ProviderRateLimitError("x"), "限流"),
        (ProviderServerError("x"), "服务端"),
        (ProviderTimeoutError("x"), "超时"),
        (ProviderNetworkError("x"), "网络"),
        (ProviderProtocolError("x"), "格式"),
        (ProviderRequestError("x"), "请求"),
        (ProviderError("x"), "错误"),
    ],
)
def test_error_category_maps_each_provider_error(exc, label):
    assert error_category(exc) == label
