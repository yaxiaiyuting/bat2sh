"""统一入口：默认启动 GUI，带 --cli 时走命令行模式。"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "cli":
        args = args[1:]
    if "--cli" in args:
        from .cli import main as cli_main

        return cli_main([a for a in args if a != "--cli"])
    if any(a in ("-h", "--help", "--version") for a in args):
        from .cli import main as cli_main

        return cli_main(args)

    from .gui.app import run_gui

    return run_gui([sys.argv[0], *args])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
