"""Provider 薄抽象 + OpenAI 兼容实现（stdlib-only）。

设计依据 ``docs/api-fix-design.md`` §3：
- 抽象只有 ``complete(prompt) -> str``（决策 2），prompt 构造/清洗/写回不在此层；
- OpenAI 兼容实现基于 stdlib ``urllib.request``（不引入 requests/httpx/openai）；
- endpoint 可配置：``POST {base_url}/chat/completions``，覆盖 OpenAI / Ollama / vLLM / LM Studio；
- 注入式 transport（``Transport`` 协议）便于无网络测试（§6.1）；
- 错误分类与重试策略见 §3.2：仅网络/429/5xx/超时可重试，4xx（除 429）不重试。
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol

from .config import ApiConfig


class ProviderError(Exception):
    """Provider 层错误基类。消息不得包含 API key（调用方仍会用 redact 兜底）。"""


class ProviderConfigError(ProviderError):
    """配置问题（未知 provider / 缺少 base_url / model）——调用方应提示配置指引。"""


class ProviderAuthError(ProviderError):
    """401/403：鉴权失败，不重试。"""


class ProviderRateLimitError(ProviderError):
    """429：限流，可退避重试。"""


class ProviderServerError(ProviderError):
    """5xx：服务端错误，可退避重试。"""


class ProviderTimeoutError(ProviderError):
    """连接/读取超时，可重试。"""


class ProviderNetworkError(ProviderError):
    """DNS/连接失败等网络错误，可重试。"""


class ProviderProtocolError(ProviderError):
    """响应非 JSON / 缺 choices[0].message.content，不重试。"""


class ProviderRequestError(ProviderError):
    """其它 4xx（如 400），语义上不可重试。"""


RETRYABLE_ERRORS = (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderNetworkError,
)

_ERROR_CATEGORIES: tuple[tuple[type[ProviderError], str], ...] = (
    (ProviderConfigError, "配置"),
    (ProviderAuthError, "认证"),
    (ProviderRateLimitError, "限流"),
    (ProviderServerError, "服务端"),
    (ProviderTimeoutError, "超时"),
    (ProviderNetworkError, "网络"),
    (ProviderProtocolError, "格式"),
    (ProviderRequestError, "请求"),
)


def error_category(exc: ProviderError) -> str:
    """把 Provider 异常映射为界面用短分类（超时/认证/网络/格式/…）；未知子类返回 "错误"。"""
    for error_type, label in _ERROR_CATEGORIES:
        if isinstance(exc, error_type):
            return label
    return "错误"


class TransportError(Exception):
    """transport 层错误基类。"""


class TransportTimeoutError(TransportError):
    """连接/读取超时。"""


class TransportNetworkError(TransportError):
    """DNS/连接失败等网络错误。"""


class Transport(Protocol):
    """HTTP transport 协议：返回 (status_code, body)；网络/超时错误抛 TransportError。"""

    def request(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]: ...


class UrllibTransport:
    """生产 transport：stdlib urllib。HTTP 错误码正常返回，网络/超时分类抛出。"""

    def request(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except (socket.timeout, TimeoutError) as exc:
            raise TransportTimeoutError(str(exc)) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise TransportTimeoutError(str(reason)) from exc
            raise TransportNetworkError(str(reason or exc)) from exc
        except OSError as exc:
            raise TransportNetworkError(str(exc)) from exc


class Provider(Protocol):
    """Provider 薄协议：把 prompt 发给模型，返回纯文本回复（决策 2）。"""

    def complete(self, prompt: str, *, timeout: float) -> str: ...


def redact(text: str, *secrets: str) -> str:
    """把秘密（API key 等）替换为 ``***``；空秘密忽略。"""
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    return result


class OpenAICompatibleProvider:
    """OpenAI 兼容 ``/chat/completions`` 实现（决策 1/2）。

    ``transport`` 可注入（测试用 FakeTransport），``sleep`` 可注入（测试免等待）。
    """

    def __init__(
        self,
        config: ApiConfig,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._config = config
        self._transport = transport or UrllibTransport()
        self._sleep = sleep

    def complete(self, prompt: str, *, timeout: float) -> str:
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        payload = {
            "model": self._config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        attempts = 0
        while True:
            try:
                status, data = self._transport.request(url, headers, body, timeout)
            except TransportTimeoutError as exc:
                error: ProviderError = ProviderTimeoutError(f"请求超时: {exc}")
            except TransportError as exc:
                error = ProviderNetworkError(f"网络错误: {exc}")
            else:
                try:
                    return self._parse_response(status, data)
                except RETRYABLE_ERRORS as exc:
                    error = exc
            if attempts >= self._config.max_retries:
                raise error
            self._sleep(1.0 * (2**attempts))
            attempts += 1

    @staticmethod
    def _parse_response(status: int, data: bytes) -> str:
        if status in (401, 403):
            raise ProviderAuthError(f"鉴权失败（HTTP {status}），请检查 API key 配置")
        if status == 429:
            raise ProviderRateLimitError("请求过于频繁（HTTP 429）")
        if 500 <= status <= 599:
            raise ProviderServerError(f"服务端错误（HTTP {status}）")
        if not 200 <= status <= 299:
            raise ProviderRequestError(f"请求被拒绝（HTTP {status}）")
        try:
            parsed = json.loads(data.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise ProviderProtocolError(f"响应不是有效 JSON: {exc}") from exc
        content = _extract_content(parsed)
        if not content:
            raise ProviderProtocolError("响应缺少 choices[0].message.content")
        return content


def _extract_content(parsed: object) -> str:
    if not isinstance(parsed, dict):
        return ""
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def create_provider(config: ApiConfig) -> Provider:
    """按 ``config.provider`` 构造 Provider；配置缺失/未知时抛 ProviderConfigError。"""
    if config.provider != "openai":
        raise ProviderConfigError(f"未知的 provider: {config.provider}（当前仅支持 openai）")
    if not config.base_url:
        raise ProviderConfigError("未配置 API 地址 base_url")
    if not config.model:
        raise ProviderConfigError("未配置模型名 model")
    return OpenAICompatibleProvider(config)
