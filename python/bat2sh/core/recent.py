"""最近打开文件记录（XDG 配置目录，JSON）。

纯函数负责解析与列表更新，读写包装单独放置，便于 headless 测试。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def recent_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bat2sh" / "recent.json"


def parse_recent_json(raw: str) -> list[Path]:
    """容错解析：坏 JSON / 非列表 / 含非字符串项 → 返回空列表。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    if not all(isinstance(item, str) and item for item in data):
        return []
    return [Path(item) for item in data]


def update_recent_list(
    existing: list[Path], opened: list[Path], cap: int = 10
) -> list[Path]:
    """新项在前、按 ``resolve()`` 去重、截断到 cap；不修改传入列表。"""
    if cap <= 0:
        return []
    result: list[Path] = []
    seen: set[Path] = set()
    for path in [*opened, *existing]:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
        if len(result) >= cap:
            break
    return result


def load_recent() -> list[Path]:
    try:
        raw = recent_path().read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_recent_json(raw)


def save_recent(paths: list[Path]) -> None:
    target = recent_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([str(p) for p in paths], ensure_ascii=False, indent=2) + "\n"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
