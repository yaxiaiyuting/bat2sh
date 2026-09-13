"""转换设置与持久化（JSON，不依赖 GUI 库）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 缩进风格：名称 -> 实际缩进字符
INDENT_CHOICES: dict[str, str] = {
    "2 空格": "  ",
    "4 空格": "    ",
    "Tab": "\t",
}
INDENT_BY_VALUE: dict[str, str] = {v: k for k, v in INDENT_CHOICES.items()}

THEME_CHOICES = ("system", "light", "dark")


@dataclass
class ConvertSettings:
    """全部转换选项。"""

    # 输出位置
    output_dir: str | None = None          # None = 与源文件同目录
    suffix: str = ".sh"
    overwrite: bool = True
    backup_existing: bool = False          # 覆盖输出前备份旧文件
    backup_source: bool = False            # 转换前备份源文件

    # 输出权限
    make_executable: bool = True

    # 代码风格
    indent: str = "    "
    quote_variables: bool = True
    strict_mode: bool = True
    last_exit_code: str = "warn"  # 退出码策略（PowerShell $LASTEXITCODE / 批处理 %ERRORLEVEL%）: warn | map
    bash_check: bool = True        # 生成脚本 bash -n 后置校验；失败则降级为注释（CLI: --no-bash-check）

    # 界面
    theme: str = "system"
    last_dir: str = ""

    def indent_label(self) -> str:
        return INDENT_BY_VALUE.get(self.indent, "4 空格")

    def normalized(self) -> "ConvertSettings":
        data = asdict(self)
        if data["indent"] not in INDENT_BY_VALUE:
            data["indent"] = "    "
        if data["theme"] not in THEME_CHOICES:
            data["theme"] = "system"
        if data["last_exit_code"] not in ("warn", "map"):
            data["last_exit_code"] = "warn"
        if not isinstance(data["bash_check"], bool):
            data["bash_check"] = True
        if not data["suffix"]:
            data["suffix"] = ".sh"
        if not data["suffix"].startswith("."):
            data["suffix"] = "." + data["suffix"]
        return ConvertSettings(**data)


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bat2sh" / "settings.json"


def load_settings(path: str | Path | None = None) -> ConvertSettings:
    target = Path(path) if path else config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ConvertSettings()
    known = set(ConvertSettings.__dataclass_fields__)
    data = {k: v for k, v in raw.items() if k in known}
    try:
        return ConvertSettings(**data).normalized()
    except TypeError:
        return ConvertSettings()


def save_settings(settings: ConvertSettings, path: str | Path | None = None) -> None:
    target = Path(path) if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(settings.normalized()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def presets_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bat2sh" / "presets.json"


def preset_to_dict(settings: ConvertSettings) -> dict:
    """转换成可持久化的 dict（先 normalized）。"""
    return asdict(settings.normalized())


def preset_from_dict(data: dict) -> ConvertSettings:
    """容错构造：非 dict / 未知键 / 缺字段 / 类型不符 → 回退默认值，不抛异常。"""
    defaults = ConvertSettings()
    if not isinstance(data, dict):
        return defaults
    values: dict[str, object] = {}
    for name in ConvertSettings.__dataclass_fields__:
        default = getattr(defaults, name)
        candidate = data.get(name, default)
        if default is None:
            values[name] = candidate if isinstance(candidate, str) else None
        elif isinstance(default, bool):
            values[name] = candidate if isinstance(candidate, bool) else default
        elif isinstance(default, str):
            values[name] = candidate if isinstance(candidate, str) else default
        else:
            values[name] = candidate
    return ConvertSettings(**values).normalized()


def parse_presets_json(raw: str) -> dict[str, ConvertSettings]:
    """容错解析 presets.json；坏 JSON / 非 dict → 空字典。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        name: preset_from_dict(value)
        for name, value in data.items()
        if isinstance(name, str) and name
    }


def load_presets() -> dict[str, ConvertSettings]:
    try:
        raw = presets_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_presets_json(raw)


def _write_presets(presets: dict[str, ConvertSettings]) -> None:
    target = presets_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {name: preset_to_dict(settings) for name, settings in presets.items()}
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)


def save_presets(name: str, settings: ConvertSettings) -> None:
    """保存命名预设；同名覆盖。"""
    presets = load_presets()
    presets[name] = settings.normalized()
    _write_presets(presets)


def delete_preset(name: str) -> None:
    presets = load_presets()
    if name in presets:
        del presets[name]
        _write_presets(presets)
