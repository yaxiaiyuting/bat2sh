"""bat2sh Android 入口。

Flet 1.0 的入口是 ft.run（0.x 的 ft.app 已被移除）。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import flet as ft  # noqa: E402

from ui.app import build  # noqa: E402


def main(page: ft.Page) -> None:
    build(page)


ft.run(main)
