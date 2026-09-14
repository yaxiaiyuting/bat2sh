"""API 修复配置：加载 / 合并（CLI > env > file）/ 校验 / 原子写。

实现依据 ``docs/api-fix-design.md`` §2.3 与 §9.1：
- Q6：独立文件 ``~/.config/bat2sh/api.json``（JSON，原子写 + 0600），不引入 TOML 依赖；
- Q3：不内置任何具体服务商默认（base_url/model 默认空串，缺失即报错）；
- 优先级：CLI 显式项 > 环境变量 > 文件 > 默认值。

本模块只依赖标准库，不导入 GUI。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

# 当前只实现 OpenAI 兼容（决策 1/2）；新增 provider 时在此登记
PROVIDER_CHOICES = ("openai",)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_CONTEXT_LINES = 3
MAX_CONTEXT_LINES = 10
MIN_TIMEOUT = 1.0
MAX_TIMEOUT = 600.0
MAX_RETRIES = 5

API_ENV_KEYS: dict[str, str] = {
    "provider": "BAT2SH_API_PROVIDER",
    "base_url": "BAT2SH_API_BASE",
    "model": "BAT2SH_API_MODEL",
    "api_key": "BAT2SH_API_KEY",
    "timeout": "BAT2SH_API_TIMEOUT",
    "context_lines": "BAT2SH_API_CONTEXT_LINES",
}

_NUMERIC_FIELDS = ("timeout", "max_retries", "context_lines")


@dataclass
class ApiConfig:
    """API 修复配置。

    ``base_url`` / ``model`` 默认空串：未显式配置时由调用方报错并给出配置指引
    （Q3 最保守选择，避免把任何商业服务商设为默认）。
    ``api_key`` 允许为空（本地端点常无鉴权，此时不发送 Authorization 头）。
    """

    provider: str = "openai"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    context_lines: int = DEFAULT_CONTEXT_LINES

    def normalized(self) -> "ApiConfig":
        data = asdict(self)
        provider = data["provider"]
        data["provider"] = (
            provider.strip() if isinstance(provider, str) and provider.strip() else "openai"
        )
        for key in ("base_url", "model", "api_key"):
            if not isinstance(data[key], str):
                data[key] = ""
        data["base_url"] = data["base_url"].strip().rstrip("/")
        data["model"] = data["model"].strip()
        data["api_key"] = data["api_key"].strip()
        data["timeout"] = _clamp_number(data["timeout"], DEFAULT_TIMEOUT, MIN_TIMEOUT, MAX_TIMEOUT)
        data["max_retries"] = int(
            _clamp_number(data["max_retries"], DEFAULT_MAX_RETRIES, 0, MAX_RETRIES)
        )
        data["context_lines"] = int(
            _clamp_number(data["context_lines"], DEFAULT_CONTEXT_LINES, 0, MAX_CONTEXT_LINES)
        )
        return ApiConfig(**data)


def _clamp_number(value: object, default: float, low: float, high: float) -> float:
    """数值容错：bool/非数值/越界（<=0 且下界为正）回退默认，其余夹取到 [low, high]。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    if number != number:  # NaN
        return default
    if number <= 0 and low > 0:
        return default
    return min(max(number, low), high)


def api_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bat2sh" / "api.json"


def api_config_from_dict(data: object) -> ApiConfig:
    """容错构造：非 dict / 未知键 / 缺字段 / 类型不符 → 回退默认值，不抛异常。"""
    defaults = ApiConfig()
    if not isinstance(data, dict):
        return defaults
    values: dict[str, object] = {}
    for name in ApiConfig.__dataclass_fields__:
        default = getattr(defaults, name)
        candidate = data.get(name, default)
        if isinstance(default, str):
            values[name] = candidate if isinstance(candidate, str) else default
        elif isinstance(default, (int, float)):
            values[name] = (
                candidate
                if isinstance(candidate, (int, float)) and not isinstance(candidate, bool)
                else default
            )
        else:
            values[name] = candidate
    return ApiConfig(**values).normalized()


def load_api_config(path: str | Path | None = None) -> ApiConfig:
    target = Path(path) if path else api_config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ApiConfig()
    return api_config_from_dict(raw)


def save_api_config(config: ApiConfig, path: str | Path | None = None) -> None:
    """原子写（``.tmp`` + ``replace``）并 ``chmod 0600``（配置可能含明文 key）。"""
    target = Path(path) if path else api_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(config.normalized()), ensure_ascii=False, indent=2) + "\n"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def _coerce_value(name: str, value: object) -> object | None:
    """把 CLI/env 的原生值转为字段类型；无法转换返回 None（调用方回退低优先级值）。"""
    if name in _NUMERIC_FIELDS:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if number != number:  # NaN
            return None
        return number if name == "timeout" else int(number)
    if isinstance(value, str):
        return value
    return None


def resolve_api_config(
    cli: Mapping[str, object] | None,
    env: Mapping[str, str],
    file_config: ApiConfig | None,
) -> ApiConfig:
    """逐字段合并：CLI 显式项（非 None / 非空白）> env（非空）> 文件 > 默认。"""
    base = file_config.normalized() if file_config is not None else ApiConfig()
    data = asdict(base)
    for name, env_key in API_ENV_KEYS.items():
        cli_value = cli.get(name) if cli else None
        if cli_value is not None and not (
            isinstance(cli_value, str) and not cli_value.strip()
        ):
            value: object | None = cli_value
        else:
            env_value = env.get(env_key) if env else None
            if env_value is None or (isinstance(env_value, str) and not env_value.strip()):
                continue
            value = env_value
        coerced = _coerce_value(name, value)
        if coerced is not None:
            data[name] = coerced
    return ApiConfig(**data).normalized()


def missing_requirements(config: ApiConfig) -> list[str]:
    """返回缺失的必填项说明（用于错误消息；空列表 = 可发起请求）。"""
    missing: list[str] = []
    if not config.base_url:
        missing.append("base_url（--api-base / BAT2SH_API_BASE / ~/.config/bat2sh/api.json）")
    if not config.model:
        missing.append("model（--api-model / BAT2SH_API_MODEL / ~/.config/bat2sh/api.json）")
    return missing
