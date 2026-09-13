"""presets.json 的序列化、容错解析与读写测试。"""

from __future__ import annotations

from bat2sh.core.settings import (
    ConvertSettings,
    delete_preset,
    load_presets,
    parse_presets_json,
    preset_from_dict,
    preset_to_dict,
    presets_path,
    save_presets,
)


def test_preset_roundtrip_is_idempotent():
    settings = ConvertSettings(suffix="bash", indent="2 ", theme="dark", quote_variables=False)
    data = preset_to_dict(settings)
    assert data["suffix"] == ".bash"
    assert data["indent"] == "    "
    restored = preset_from_dict(data)
    assert preset_to_dict(restored) == data


def test_preset_from_dict_missing_keys_use_defaults():
    restored = preset_from_dict({"suffix": ".bash"})
    defaults = ConvertSettings()
    assert restored.suffix == ".bash"
    assert restored.make_executable == defaults.make_executable
    assert restored.theme == defaults.theme
    assert restored.output_dir is None


def test_preset_from_dict_type_errors_fall_back():
    restored = preset_from_dict(
        {"overwrite": "yes", "output_dir": 42, "indent": None, "theme": ["dark"]}
    )
    defaults = ConvertSettings()
    assert restored.overwrite is defaults.overwrite
    assert restored.output_dir is None
    assert restored.indent == defaults.indent
    assert restored.theme == defaults.theme


def test_preset_from_dict_non_dict_returns_defaults():
    assert preset_to_dict(preset_from_dict("abc")) == preset_to_dict(ConvertSettings())
    assert preset_to_dict(preset_from_dict(None)) == preset_to_dict(ConvertSettings())


def test_parse_presets_json_filters_invalid_entries():
    assert parse_presets_json("{bad") == {}
    assert parse_presets_json("[1, 2]") == {}
    parsed = parse_presets_json('{"a": {"suffix": ".sh"}, "": {"suffix": ".x"}, "b": 3}')
    assert set(parsed) == {"a", "b"}
    assert parsed["a"].suffix == ".sh"
    assert parsed["b"].suffix == ".sh"


def test_save_load_delete_presets_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert presets_path() == tmp_path / "bat2sh" / "presets.json"
    assert load_presets() == {}
    first = ConvertSettings(suffix=".bash", strict_mode=False)
    second = ConvertSettings(quote_variables=False)
    save_presets("alpha", first)
    save_presets("beta", second)
    loaded = load_presets()
    assert set(loaded) == {"alpha", "beta"}
    assert preset_to_dict(loaded["alpha"]) == preset_to_dict(first)
    overwritten = ConvertSettings(suffix=".zsh")
    save_presets("alpha", overwritten)
    assert preset_to_dict(load_presets()["alpha"]) == preset_to_dict(overwritten)
    delete_preset("beta")
    assert set(load_presets()) == {"alpha"}


def test_last_exit_code_preset_roundtrip():
    settings = ConvertSettings(last_exit_code="map")
    data = preset_to_dict(settings)
    assert data["last_exit_code"] == "map"
    assert preset_from_dict(data).last_exit_code == "map"
    assert preset_from_dict({"last_exit_code": "bogus"}).last_exit_code == "warn"
    assert preset_from_dict({}).last_exit_code == "warn"
