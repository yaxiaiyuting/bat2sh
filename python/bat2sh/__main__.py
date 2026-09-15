"""统一入口：默认启动 GUI；带 CLI 专用参数时走命令行模式。"""

from __future__ import annotations

import sys


def _cli_option_strings() -> set[str]:
    from .cli import build_parser

    options: set[str] = set()
    for action in build_parser()._actions:
        options.update(action.option_strings)
    return options


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "cli":
        args = args[1:]
    if "--cli" in args:
        from .cli import main as cli_main

        return cli_main([a for a in args if a != "--cli"])
    if args:
        cli_options = _cli_option_strings()
        if any(a.split("=", 1)[0] in cli_options for a in args):
            from .cli import main as cli_main

            return cli_main(args)

    from .gui.app import run_gui

    return run_gui([sys.argv[0], *args])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
