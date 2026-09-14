"""API 配置层测试：容错解析、优先级合并（CLI > env > file）、原子写与 0600。"""

from __future__ import annotations

import json
import os
import stat

from bat2sh.core.api.config import (
    ApiConfig,
    api_config_from_dict,
    api_config_path,
    load_api_config,
    missing_requirements,
    resolve_api_config,
    save_api_config,
)


def test_config_path_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert api_config_path() == tmp_path / "bat2sh" / "api.json"


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config = load_api_config()
    assert config == ApiConfig()
    assert config.base_url == ""
    assert config.model == ""


def test_load_bad_json_returns_defaults(tmp_path):
    target = tmp_path / "api.json"
    target.write_text("{bad", encoding="utf-8")
    assert load_api_config(target) == ApiConfig()


def test_from_dict_tolerates_types():
    config = api_config_from_dict(
        {
            "provider": 42,
            "base_url": " https://example.test/v1/ ",
            "model": "m",
            "api_key": "k",
            "timeout": "soon",
            "max_retries": True,
            "context_lines": "3",
        }
    )
    assert config.provider == "openai"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "m"
    assert config.api_key == "k"
    assert config.timeout == 30.0
    assert config.max_retries == 1
    assert config.context_lines == 3


def test_from_dict_non_dict_returns_defaults():
    assert api_config_from_dict("x") == ApiConfig()
    assert api_config_from_dict(None) == ApiConfig()


def test_normalized_clamps_numbers():
    assert ApiConfig(timeout=-5).normalized().timeout == 30.0
    assert ApiConfig(timeout=9999).normalized().timeout == 600.0
    assert ApiConfig(max_retries=-1).normalized().max_retries == 0
    assert ApiConfig(max_retries=99).normalized().max_retries == 5
    assert ApiConfig(context_lines=-1).normalized().context_lines == 0
    assert ApiConfig(context_lines=99).normalized().context_lines == 10
    assert ApiConfig(context_lines=0).normalized().context_lines == 0


def test_resolve_precedence_cli_over_env_over_file():
    file_config = ApiConfig(base_url="https://file.test/v1", model="file-model", timeout=10.0)
    env = {
        "BAT2SH_API_BASE": "https://env.test/v1",
        "BAT2SH_API_MODEL": "env-model",
        "BAT2SH_API_KEY": "env-key",
    }
    cli = {"base_url": "https://cli.test/v1", "timeout": 5.0}
    resolved = resolve_api_config(cli, env, file_config)
    assert resolved.base_url == "https://cli.test/v1"
    assert resolved.model == "env-model"
    assert resolved.api_key == "env-key"
    assert resolved.timeout == 5.0
    assert resolved.context_lines == 3


def test_resolve_blank_values_fall_through():
    file_config = ApiConfig(base_url="https://file.test/v1", model="file-model")
    resolved = resolve_api_config(
        {"base_url": "  ", "model": None},
        {"BAT2SH_API_MODEL": ""},
        file_config,
    )
    assert resolved.base_url == "https://file.test/v1"
    assert resolved.model == "file-model"


def test_resolve_invalid_env_number_falls_back():
    resolved = resolve_api_config(
        None, {"BAT2SH_API_TIMEOUT": "abc"}, ApiConfig(timeout=12.0)
    )
    assert resolved.timeout == 12.0
    resolved2 = resolve_api_config(None, {"BAT2SH_API_TIMEOUT": "45"}, ApiConfig())
    assert resolved2.timeout == 45.0


def test_resolve_unknown_provider_kept():
    resolved = resolve_api_config({"provider": "ollama"}, {}, ApiConfig())
    assert resolved.provider == "ollama"


def test_missing_requirements_lists_fields():
    assert missing_requirements(ApiConfig(base_url="u", model="m")) == []
    missing = missing_requirements(ApiConfig())
    assert len(missing) == 2
    assert any("base_url" in item for item in missing)
    assert any("model" in item for item in missing)


def test_save_load_roundtrip_and_permissions(tmp_path):
    target = tmp_path / "api.json"
    config = ApiConfig(
        provider="openai",
        base_url="https://example.test/v1",
        model="demo-model",
        api_key="secret-value",
        timeout=12.5,
        context_lines=5,
    )
    save_api_config(config, target)
    assert load_api_config(target) == config.normalized()
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["api_key"] == "secret-value"
    assert not target.with_name(target.name + ".tmp").exists()


def test_save_api_config_atomic_replace_no_tmp_left(tmp_path):
    target = tmp_path / "api.json"
    save_api_config(ApiConfig(base_url="https://a.test/v1"), target)
    save_api_config(ApiConfig(base_url="https://b.test/v1"), target)
    assert load_api_config(target).base_url == "https://b.test/v1"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
