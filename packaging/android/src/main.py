"""bat2sh Android 入口。

Flet 1.0 的入口是 ft.run（0.x 的 ft.app 已被移除）。

**顺序很重要**：`XDG_CONFIG_HOME` 必须在任何 `bat2sh.core.*` 被 import 之前注入 ——
`ui.app` 在 import 阶段就会 `import bridge`，而 bridge 会拉起 core。
所以注入放在本文件最前面（早于 import flet / import ui.app）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# API 配置路径注入（决策 2：Flet 层注入 XDG_CONFIG_HOME，core 零改动）
#
# core/api/config.py 的 api_config_path() 第一优先级就是 XDG_CONFIG_HOME：
#     base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
# 因此这里改环境变量即可把 api.json 落到应用私有目录，
# Android 上实际落点：
#     <FLET_APP_STORAGE_DATA>/config/bat2sh/api.json
# 实测见 docs/android-api-assessment.md §4.2。
#
# 仅当 Flet 提供了 FLET_APP_STORAGE_DATA（= 跑在 Flet 容器里）才覆盖，
# 这样桌面 smoke test 仍会读用户真实的 ~/.config/bat2sh/api.json。
# ---------------------------------------------------------------------------
_storage = os.environ.get("FLET_APP_STORAGE_DATA")
if _storage:
    os.environ["XDG_CONFIG_HOME"] = os.path.join(_storage, "config")

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import flet as ft  # noqa: E402

from ui.app import build  # noqa: E402


def main(page: ft.Page) -> None:
    build(page)


ft.run(main)
