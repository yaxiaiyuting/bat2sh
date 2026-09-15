"""Provider 薄抽象 + OpenAI 兼容实现（stdlib-only，流式 SSE）。

设计依据 ``docs/api-fix-design.md`` §3 与附录 C（v1.5 流式改造）：
- 抽象：``complete(prompt) -> str``（一次性）与 ``complete_stream(prompt) -> Iterator[str]``
  （逐块产出正文）；prompt 构造/清洗/写回不在此层；
- OpenAI 兼容实现基于 stdlib ``urllib.request``（不引入 requests/httpx/openai）；
- endpoint 可配置：``POST {base_url}/chat/completions``，覆盖 OpenAI / Ollama / vLLM / LM Studio；
  统一使用 ``stream: true``（SSE）逐行读取——socket 超时因此是**两次数据之间的空闲超时**，
  不再是整个响应的总时长上限（附录 C）；
- 端点忽略 ``stream`` 返回普通 JSON 时，同一响应按普通响应解析（零额外请求，不做二次非流式回退）；
- 思维链（reasoning_content）默认不产出，仅通过 ``on_reasoning`` 回调报告累计段数；
- 注入式 transport（``Transport`` 协议）便于无网络测试（§6.1）；
- 错误分类与重试策略见 §3.2：仅网络/429/5xx/超时可重试，4xx（除 429）不重试；
  已开始产出内容后发生可重试错误时**不再重试**（避免重复输出）。
"""

from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Callable, Iterator, Protocol

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
    """连接/读取超时（流式下为两次数据之间的空闲超时），可重试。"""


class ProviderNetworkError(ProviderError):
    """DNS/连接失败等网络错误，可重试。"""


class ProviderProtocolError(ProviderError):
    """响应非 JSON / SSE 数据行损坏 / 流意外中断 / 缺正文，不重试。"""


class ProviderRequestError(ProviderError):
    """其它 4xx（如 400/422），语义上不可重试。``status`` 为原始 HTTP 状态码（若可得）。"""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


RETRYABLE_ERRORS = (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderNetworkError,
)


def _timeout_with_advice(
    error: ProviderError, timeout: float, retries: int, context_lines: int
) -> ProviderError:
    """给超时错误附加当前配置与可操作建议（决策②）；非超时错误原样返回。"""
    if not isinstance(error, ProviderTimeoutError):
        return error
    return ProviderTimeoutError(
        f"请求超时：{timeout:g} 秒内未收到数据（已重试 {retries} 次；底层：{error}）。"
        f"建议：调大超时（--api-timeout / BAT2SH_API_TIMEOUT / api.json 的 timeout，"
        f"当前 {timeout:g} 秒），或减小发送上下文"
        f"（--api-context-lines，当前 {context_lines} 行）后重试。"
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
    """连接/读取超时（流式下为两次数据之间的空闲超时）。"""


class TransportNetworkError(TransportError):
    """DNS/连接失败、连接中断等网络错误。"""


class Transport(Protocol):
    """HTTP transport 协议：返回 (status_code, 行迭代器)；网络/超时错误抛 TransportError。

    行迭代器逐行产出响应体（bytes，含换行）。调用方负责在消费结束/放弃时关闭迭代器
    （``close()``，若存在）。
    """

    def request_stream(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, Iterator[bytes]]: ...


def _iter_lines(response) -> Iterator[bytes]:
    """逐行产出响应体；把读取期异常分类为 TransportError；结束后必定关闭响应。"""
    try:
        yield from response
    except (socket.timeout, TimeoutError) as exc:
        raise TransportTimeoutError(str(exc)) from exc
    except http.client.IncompleteRead as exc:
        raise TransportNetworkError(f"响应流中断: {exc}") from exc
    except http.client.HTTPException as exc:
        raise TransportNetworkError(f"HTTP 响应异常: {exc}") from exc
    except OSError as exc:
        raise TransportNetworkError(str(exc)) from exc
    finally:
        response.close()


class UrllibTransport:
    """生产 transport：stdlib urllib。HTTP 错误码正常返回，网络/超时分类抛出。"""

    def request_stream(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, Iterator[bytes]]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            return exc.code, _iter_lines(exc)
        except (socket.timeout, TimeoutError) as exc:
            raise TransportTimeoutError(str(exc)) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise TransportTimeoutError(str(reason)) from exc
            raise TransportNetworkError(str(reason or exc)) from exc
        except OSError as exc:
            raise TransportNetworkError(str(exc)) from exc
        return response.status, _iter_lines(response)


class Provider(Protocol):
    """Provider 薄协议：把 prompt 发给模型，返回纯文本回复（决策 2）。"""

    def complete(self, prompt: str, *, timeout: float) -> str: ...

    def complete_stream(
        self,
        prompt: str,
        *,
        timeout: float,
        on_reasoning: Callable[[int], None] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ) -> Iterator[str]: ...


def redact(text: str, *secrets: str) -> str:
    """把秘密（API key 等）替换为 ``***``；空秘密忽略。"""
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    return result


class OpenAICompatibleProvider:
    """OpenAI 兼容 ``/chat/completions`` 实现（决策 1/2，流式 SSE）。

    ``transport`` 可注入（测试用 FakeTransport），``sleep`` 可注入（测试免等待）。
    统一发送 ``stream: true``；``complete`` 是 ``complete_stream`` 的拼接封装。
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
        self._thinking_param_unsupported = False

    def complete(self, prompt: str, *, timeout: float) -> str:
        return "".join(self.complete_stream(prompt, timeout=timeout))

    def complete_stream(
        self,
        prompt: str,
        *,
        timeout: float,
        on_reasoning: Callable[[int], None] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ) -> Iterator[str]:
        """逐块产出正文（str）。

        ``on_reasoning`` 每收到一段思维链回调累计段数（默认不产出思维链）；
        ``on_warning`` 在兼容性降级（端点拒绝 ``enable_thinking`` 参数）时回调说明文字。
        """
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        include_thinking_param = (
            not self._config.enable_thinking and not self._thinking_param_unsupported
        )
        attempts = 0
        while True:
            payload = {
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": True,
            }
            if include_thinking_param:
                # 仅显式关闭时携带 false；开启交由端点默认（见附录 D）
                payload["enable_thinking"] = False
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            yielded = False
            stream = self._stream_once(url, headers, body, timeout, on_reasoning)
            try:
                for chunk in stream:
                    yielded = True
                    yield chunk
                return
            except RETRYABLE_ERRORS as exc:
                if yielded or attempts >= self._config.max_retries:
                    advice = _timeout_with_advice(
                        exc, timeout, attempts, self._config.context_lines
                    )
                    if advice is exc:
                        raise
                    raise advice from exc
                self._sleep(1.0 * (2**attempts))
                attempts += 1
            except ProviderRequestError as exc:
                if include_thinking_param and exc.status in (400, 422):
                    # 自动降级（方案 C）：端点不认该参数 → 去掉后立即重试，并记忆+告警
                    include_thinking_param = False
                    self._thinking_param_unsupported = True
                    if on_warning is not None:
                        on_warning(
                            "端点不支持 enable_thinking 参数"
                            f"（HTTP {exc.status}），已自动降级：后续请求不再携带该参数"
                        )
                    continue
                raise
            finally:
                stream.close()

    def _stream_once(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
        on_reasoning: Callable[[int], None] | None,
    ) -> Iterator[str]:
        try:
            status, lines = self._transport.request_stream(url, headers, body, timeout)
        except TransportTimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except TransportError as exc:
            raise ProviderNetworkError(f"网络错误: {exc}") from exc
        try:
            self._raise_for_status(status)
            yield from self._consume_stream(lines, on_reasoning)
        except TransportTimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except TransportError as exc:
            raise ProviderNetworkError(f"网络错误: {exc}") from exc
        finally:
            close = getattr(lines, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status in (401, 403):
            raise ProviderAuthError(f"鉴权失败（HTTP {status}），请检查 API key 配置")
        if status == 429:
            raise ProviderRateLimitError("请求过于频繁（HTTP 429）")
        if 500 <= status <= 599:
            raise ProviderServerError(f"服务端错误（HTTP {status}）")
        if not 200 <= status <= 299:
            raise ProviderRequestError(f"请求被拒绝（HTTP {status}）", status)

    def _consume_stream(
        self, lines: Iterator[bytes], on_reasoning: Callable[[int], None] | None
    ) -> Iterator[str]:
        """消费 SSE 行流：产出正文块；支持端点忽略 stream 时的纯 JSON 回退。"""
        content: list[str] = []
        reasoning_count = 0
        saw_done = False
        finish_reason = False
        json_lines: list[str] = []
        mode = "undecided"

        for raw in lines:
            line = (
                raw.decode("utf-8", errors="replace")
                if isinstance(raw, (bytes, bytearray))
                else raw
            )
            line = line.rstrip("\r\n")

            if mode == "json":
                json_lines.append(line)
                continue
            if mode == "undecided":
                if not line.strip():
                    continue
                if line.lstrip().startswith("{"):
                    mode = "json"
                    json_lines.append(line)
                    continue
                if line.startswith("data:"):
                    mode = "sse"
                else:
                    continue  # 注释行 / 未知事件行：忽略

            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                saw_done = True
                break
            try:
                event = json.loads(payload)
            except ValueError as exc:
                raise ProviderProtocolError(f"流式响应数据行不是有效 JSON: {exc}") from exc
            choice: object = {}
            if isinstance(event, dict):
                choices = event.get("choices")
                if isinstance(choices, list) and choices:
                    choice = choices[0]
            if not isinstance(choice, dict):
                choice = {}
            if choice.get("finish_reason"):
                finish_reason = True
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                delta = {}
            piece = delta.get("content")
            if isinstance(piece, str) and piece:
                content.append(piece)
                yield piece
            elif isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"]:
                reasoning_count += 1
                if on_reasoning is not None:
                    on_reasoning(reasoning_count)

        if mode == "json":
            yield self._content_from_json("\n".join(json_lines))
            return
        if mode == "undecided":
            raise ProviderProtocolError("响应为空：既不是 SSE 流也不是 JSON")
        if not (saw_done or finish_reason):
            raise ProviderProtocolError("流式响应意外中断：未收到 [DONE] 或 finish_reason")
        if not content:
            hint = "（仅有思维链 reasoning_content，无正文内容）" if reasoning_count else ""
            raise ProviderProtocolError(f"响应未包含正文内容{hint}")

    @staticmethod
    def _content_from_json(text: str) -> str:
        try:
            parsed = json.loads(text)
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
