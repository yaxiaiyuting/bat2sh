"""脚本落盘 / bash -n 校验 / 运行 —— 全部经内嵌 Termux 的 bash。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from termux import Termux  # noqa: E402

_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def safe_name(name: str) -> str:
    out = "".join(c if c in _SAFE else "_" for c in (name or "")).strip("._") or "output"
    if not out.endswith(".sh"):
        out += ".sh"
    return out


class ScriptRunner:
    """把产物落到应用工作目录，再用 Termux bash 校验 / 执行。

    注意：产物首行是 core 生成的 #!/usr/bin/env bash，而 Android 上
    /usr/bin/env 并不存在 —— 直接 ./x.sh 会 ENOENT（Phase A 探针 D2 实测）。
    所以这里一律用 bash <script> 显式解释，绝不依赖 shebang。
    """

    def __init__(self, termux: Termux) -> None:
        self.tx = termux
        self.last_path: Path | None = None

    def stage(self, script_text: str, out_name: str) -> Path:
        self.tx.prepare_dirs()
        p = self.tx.work / safe_name(out_name)
        p.write_text(script_text, encoding="utf-8")
        try:
            os.chmod(p, 0o755)
        except OSError:
            pass
        self.last_path = p
        return p

    def check(self, path: Path) -> tuple[bool, bool, str]:
        """返回 (是否真的跑了校验, 是否通过, 信息)。"""
        return self.tx.syntax_check(path)

    def run(self, path: Path, timeout: float = 60.0):
        """返回 (rc, stdout, stderr, mode)。"""
        return self.tx.run_script(path, timeout=timeout)
