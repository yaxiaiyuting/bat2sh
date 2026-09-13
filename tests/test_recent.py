"""recent.json 的解析、列表更新与读写测试。"""

from __future__ import annotations

from pathlib import Path

from bat2sh.core.recent import (
    load_recent,
    parse_recent_json,
    recent_path,
    save_recent,
    update_recent_list,
)


# ----------------------------------------------------------------------
# parse_recent_json
# ----------------------------------------------------------------------
def test_parse_recent_json_valid():
    assert parse_recent_json('["/a/x.bat", "/b/y.ps1"]') == [
        Path("/a/x.bat"),
        Path("/b/y.ps1"),
    ]
    assert parse_recent_json("[]") == []


def test_parse_recent_json_bad_json_returns_empty():
    assert parse_recent_json("{not json") == []
    assert parse_recent_json("") == []


def test_parse_recent_json_non_list_returns_empty():
    assert parse_recent_json('{"a": 1}') == []
    assert parse_recent_json('"text"') == []


def test_parse_recent_json_non_string_items_return_empty():
    assert parse_recent_json('["a.bat", 3]') == []
    assert parse_recent_json('["a.bat", ""]') == []


# ----------------------------------------------------------------------
# update_recent_list
# ----------------------------------------------------------------------
def test_update_recent_list_dedupes_same_file_two_paths(tmp_path):
    target = tmp_path / "a.bat"
    target.write_text("", encoding="utf-8")
    alias = tmp_path / "sub" / ".." / "a.bat"
    assert update_recent_list([alias], [target]) == [target]
    assert update_recent_list([target], [alias]) == [alias]


def test_update_recent_list_puts_new_first_and_caps():
    existing = [Path(f"/old/{i}.bat") for i in range(3)]
    opened = [Path("/new/1.bat"), Path("/new/2.bat")]
    result = update_recent_list(existing, opened, cap=4)
    assert result[:2] == opened
    assert result[2:] == existing[:2]
    assert update_recent_list(existing, opened, cap=0) == []


def test_update_recent_list_does_not_mutate_inputs(tmp_path):
    existing = [tmp_path / "a.bat"]
    opened = [tmp_path / "b.bat"]
    result = update_recent_list(existing, opened)
    assert existing == [tmp_path / "a.bat"]
    assert opened == [tmp_path / "b.bat"]
    assert result == opened + existing


# ----------------------------------------------------------------------
# load / save
# ----------------------------------------------------------------------
def test_load_save_recent_roundtrip_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert recent_path() == tmp_path / "bat2sh" / "recent.json"
    assert load_recent() == []
    paths = [tmp_path / "a.bat", tmp_path / "b.ps1"]
    save_recent(paths)
    assert load_recent() == paths
    save_recent(paths)
    assert load_recent() == paths
    assert list((tmp_path / "bat2sh").glob("*.tmp")) == []
