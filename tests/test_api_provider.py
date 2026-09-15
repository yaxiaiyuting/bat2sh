"""Provider 层测试：FakeTransport（流式行迭代器）覆盖成功/鉴权/限流/5xx/超时/流中断/坏 JSON/回退与重试。

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


class CloseSpy:
    """包装行序列并记录 close() 调用（验证流被关闭）。"""

    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        self.closed = True


class FakeTransport:
    """按脚本依次返回 ``(status, lines)``；lines 为行列表/迭代器/CloseSpy；异常实例直接抛出。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request_stream(self, url, headers, body, timeout):
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
    values = dict(base_url="https://api.example.test/v1", model="demo-model", api_key="sk-secret")
    values.update(overrides)
    config = ApiConfig(**values).normalized()
    transport = FakeTransport(responses)
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=lambda _s: None)
    return provider, transport


def chunk(
    content: str = "",
    *,
    role: str | None = None,
    reasoning: str = "",
    finish: str | None = None,
) -> bytes:
    delta: dict[str, str] = {}
    if role is not None:
        delta["role"] = role
    if content:
        delta["content"] = content
    if reasoning:
        delta["reasoning_content"] = reasoning
    event = {"choices": [{"delta": delta, "finish_reason": finish}]}
    return ("data: " + json.dumps(event, ensure_ascii=False)).encode("utf-8")


def sse(*chunks: bytes, done: bool = True) -> list[bytes]:
    lines = list(chunks)
    if done:
        lines.append(b"data: [DONE]")
    return lines


def json_body(content: str = "echo fixed") -> list[bytes]:
    payload = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return [json.dumps(payload).encode("utf-8")]


def failing_after(lines: list[bytes], exc: Exception, count: int):
    """先产出前 count 行，随后抛出 exc（模拟流中途失败）。"""

    def _gen():
        for index, line in enumerate(lines):
            if index >= count:
                raise exc
            yield line

    return _gen()


def test_complete_joins_stream_chunks_and_sends_expected_request():
    provider, transport = make_provider([(200, sse(chunk("echo "), chunk('"fixed"')))])
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
    assert body["stream"] is True


def test_complete_stream_yields_content_chunks():
    provider, _ = make_provider([(200, sse(chunk("a"), chunk("b"), chunk("c")))])
    assert list(provider.complete_stream("p", timeout=1.0)) == ["a", "b", "c"]


def test_complete_without_key_omits_authorization():
    config = ApiConfig(base_url="http://localhost:11434/v1", model="llama").normalized()
    transport = FakeTransport([(200, sse(chunk("ok")))])
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=lambda _s: None)
    assert provider.complete("p", timeout=1.0) == "ok"
    assert "Authorization" not in transport.calls[0]["headers"]


def test_base_url_trailing_slash_normalized():
    provider, transport = make_provider([(200, sse(chunk("x")))], base_url="https://a.test/v1/")
    provider.complete("p", timeout=1.0)
    assert transport.calls[0]["url"] == "https://a.test/v1/chat/completions"


def test_auth_error_not_retried_and_stream_closed():
    spy = CloseSpy([b"nope"])
    provider, transport = make_provider([(401, spy)])
    with pytest.raises(ProviderAuthError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1
    assert spy.closed is True


def test_rate_limit_retried_then_success():
    provider, transport = make_provider([(429, []), (200, sse(chunk("done")))])
    assert provider.complete("p", timeout=1.0) == "done"
    assert len(transport.calls) == 2


def test_rate_limit_exhausts_retries():
    provider, transport = make_provider([(429, []), (429, []), (200, sse(chunk("x")))])
    with pytest.raises(ProviderRateLimitError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 2  # 默认 max_retries=1 → 1 次重试


def test_server_error_retried():
    provider, transport = make_provider([(503, []), (200, sse(chunk("ok")))])
    assert provider.complete("p", timeout=1.0) == "ok"
    assert len(transport.calls) == 2


def test_server_error_exhausted():
    provider, _ = make_provider([(500, []), (500, [])])
    with pytest.raises(ProviderServerError):
        provider.complete("p", timeout=1.0)


def test_timeout_error_retried():
    provider, transport = make_provider([TransportTimeoutError("slow"), (200, sse(chunk("ok")))])
    assert provider.complete("p", timeout=1.0) == "ok"
    assert len(transport.calls) == 2


def test_timeout_exhausted():
    provider, _ = make_provider([TransportTimeoutError("slow"), TransportTimeoutError("slow")])
    with pytest.raises(ProviderTimeoutError):
        provider.complete("p", timeout=1.0)


def test_mid_stream_timeout_not_retried():
    lines = sse(chunk("partial"), chunk("more"))
    provider, transport = make_provider(
        [(200, failing_after(lines, TransportTimeoutError("gap"), 1))]
    )
    with pytest.raises(ProviderTimeoutError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1  # 已产出内容，不重试


def test_mid_stream_partial_then_interrupt():
    lines = sse(chunk("first"), chunk("second"))
    provider, _ = make_provider([(200, failing_after(lines, TransportTimeoutError("gap"), 1))])
    stream = provider.complete_stream("p", timeout=1.0)
    assert next(stream) == "first"
    with pytest.raises(ProviderTimeoutError):
        next(stream)


def test_mid_stream_network_error_not_retried():
    lines = sse(chunk("partial"))
    provider, transport = make_provider(
        [(200, failing_after(lines, TransportNetworkError("reset"), 1))]
    )
    with pytest.raises(ProviderNetworkError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_stream_interrupted_without_terminator():
    provider, transport = make_provider([(200, sse(chunk("partial"), done=False))])
    with pytest.raises(ProviderProtocolError, match="意外中断"):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_finish_reason_without_done_accepted():
    provider, _ = make_provider(
        [(200, [chunk("ok", finish="stop"), chunk("ignored-after-finish", finish="stop")])]
    )
    assert provider.complete("p", timeout=1.0) == "ok" + "ignored-after-finish"


def test_bad_sse_json_protocol_error_not_retried():
    provider, transport = make_provider([(200, [b"data: {not json}", b"data: [DONE]"])])
    with pytest.raises(ProviderProtocolError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_json_fallback_single_line():
    provider, transport = make_provider([(200, json_body("echo fallback"))])
    assert provider.complete("p", timeout=1.0) == "echo fallback"
    assert len(transport.calls) == 1


def test_json_fallback_pretty_multiline():
    pretty = json.dumps(
        {"choices": [{"message": {"content": "multi"}}]}, indent=2
    ).splitlines()
    provider, _ = make_provider([(200, [line.encode() for line in pretty])])
    assert provider.complete("p", timeout=1.0) == "multi"


def test_role_only_first_chunk_ok():
    provider, _ = make_provider([(200, sse(chunk(role="assistant"), chunk("hi")))])
    assert provider.complete("p", timeout=1.0) == "hi"


def test_reasoning_only_protocol_error():
    provider, _ = make_provider([(200, sse(chunk(reasoning="think"), chunk(reasoning="more")))])
    with pytest.raises(ProviderProtocolError, match="思维链"):
        provider.complete("p", timeout=1.0)


def test_reasoning_callback_reports_cumulative_count():
    seen: list[int] = []
    provider, _ = make_provider(
        [(200, sse(chunk(reasoning="t1"), chunk(reasoning="t2"), chunk("final")))]
    )
    result = "".join(provider.complete_stream("p", timeout=1.0, on_reasoning=seen.append))
    assert result == "final"
    assert seen == [1, 2]


def test_empty_content_protocol_error():
    provider, _ = make_provider([(200, [b"data: [DONE]"])])
    with pytest.raises(ProviderProtocolError):
        provider.complete("p", timeout=1.0)


def test_empty_response_protocol_error():
    provider, _ = make_provider([(200, [])])
    with pytest.raises(ProviderProtocolError, match="响应为空"):
        provider.complete("p", timeout=1.0)


def test_other_4xx_request_error_not_retried():
    provider, transport = make_provider([(400, []), (200, sse(chunk("x")))])
    with pytest.raises(ProviderRequestError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_max_retries_zero_no_retry():
    provider, transport = make_provider([(500, [])], max_retries=0)
    with pytest.raises(ProviderServerError):
        provider.complete("p", timeout=1.0)
    assert len(transport.calls) == 1


def test_backoff_schedule():
    sleeps: list[float] = []
    config = ApiConfig(base_url="https://a.test/v1", model="m", max_retries=2).normalized()
    transport = FakeTransport([(500, []), (500, []), (200, sse(chunk("ok")))])
    provider = OpenAICompatibleProvider(config, transport=transport, sleep=sleeps.append)
    assert provider.complete("p", timeout=1.0) == "ok"
    assert sleeps == [1.0, 2.0]


def test_stream_close_propagates_to_transport():
    spy = CloseSpy(sse(chunk("a"), chunk("b")))
    provider, _ = make_provider([(200, spy)])
    stream = provider.complete_stream("p", timeout=1.0)
    assert next(stream) == "a"
    stream.close()
    assert spy.closed is True


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
