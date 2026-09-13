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
