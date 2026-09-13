"""命令行模式：``bat2sh --cli input.bat -o output.sh``。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_DESCRIPTION, __version__
from .core.encoding import decode_bytes
from .core.engine import ConversionResult, convert_file, convert_text, detect_kind
from .core.settings import ConvertSettings
from .core.types import ConvertReport, SourceKind


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bat2sh",
        description=APP_DESCRIPTION,
        epilog="示例: bat2sh --cli deploy.bat -o deploy.sh",
    )
    parser.add_argument("inputs", nargs="*", help="待转换的 .bat/.cmd/.ps1 文件")
    parser.add_argument("--cli", action="store_true", help="启用命令行模式（启动器兼容用）")
    parser.add_argument("-o", "--output", help="输出文件（仅单文件输入时可用）")
    parser.add_argument("--outdir", help="输出目录（默认与源文件同目录）")
    parser.add_argument("--suffix", default=".sh", help="输出文件后缀（默认 .sh）")
    parser.add_argument("--no-exec", action="store_true", help="不添加可执行权限")
    parser.add_argument("--backup", action="store_true", help="覆盖输出前备份旧文件")
    parser.add_argument("--backup-source", action="store_true", help="转换前备份源文件")
    parser.add_argument(
        "--indent", choices=["2", "4", "tab"], default="4", help="缩进风格（默认 4 空格）"
    )
    parser.add_argument("--no-quote-vars", action="store_true", help="变量不强制加双引号")
    parser.add_argument("--no-strict", action="store_true", help="不添加 set -euo pipefail")
    parser.add_argument("--encoding", help="强制指定输入编码（默认自动检测）")
    parser.add_argument("--no-overwrite", action="store_true", help="输出已存在时拒绝覆盖")
    parser.add_argument("--print", dest="print_only", action="store_true", help="只输出到 stdout，不写文件")
    report_group = parser.add_mutually_exclusive_group()
    report_group.add_argument("--report", action="store_true", help="打印转换报告")
    report_group.add_argument(
        "--report-json",
        action="store_true",
        help="以 JSON 格式打印转换报告（与 --report 互斥）",
    )
    parser.add_argument("--fail-on-todo", action="store_true", help="存在 TODO 时返回退出码 3")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    parser.add_argument("--version", action="version", version=f"bat2sh {__version__}")
    return parser


def settings_from_args(args: argparse.Namespace) -> ConvertSettings:
    output_dir = str(Path(args.outdir).expanduser()) if args.outdir else None
    indent = {"2": "  ", "4": "    ", "tab": "\t"}[args.indent]
    return ConvertSettings(
        output_dir=output_dir,
        suffix=args.suffix,
        make_executable=not args.no_exec,
        backup_existing=args.backup,
        backup_source=args.backup_source,
        indent=indent,
        quote_variables=not args.no_quote_vars,
        strict_mode=not args.no_strict,
        overwrite=not args.no_overwrite,
    )


def _emit_report(convert_report: ConvertReport, args: argparse.Namespace) -> None:
    if args.report:
        sys.stderr.write(convert_report.to_text() + "\n")
    elif args.report_json:
        sys.stderr.write(convert_report.to_json() + "\n")


def _print_only(
    path: Path, settings: ConvertSettings, encoding: str | None, args: argparse.Namespace
) -> int:
    kind = detect_kind(path)
    if kind is SourceKind.UNKNOWN:
        print(f"bat2sh: 不支持的源文件类型: {path}", file=sys.stderr)
        return 2
    decoded = decode_bytes(path.read_bytes(), encoding)
    text, convert_report = convert_text(decoded.text, kind, settings, path.name)
    convert_report.encoding = decoded.encoding
    sys.stdout.write(text)
    _emit_report(convert_report, args)
    return 3 if convert_report.todo_count else 0


def run_one(
    path: Path,
    settings: ConvertSettings,
    encoding: str | None,
    args: argparse.Namespace,
) -> tuple[int, ConversionResult | None]:
    if args.print_only:
        code = _print_only(path, settings, encoding, args)
        return code, None
    output_override = args.output if args.output else None
    result = convert_file(
        path, settings, encoding_override=encoding, output_override=output_override
    )
    if result.error:
        print(f"bat2sh: {result.error}", file=sys.stderr)
        return 2, result
    if not args.quiet:
        status = "已写出" if result.written else "未写出"
        print(
            f"[{status}] {result.source_path} -> {result.output_path}"
            f" | 转换 {result.report.converted_lines} 行"
            f" | 警告 {result.report.warning_count}"
            f" | TODO {result.report.todo_count}"
        )
    _emit_report(result.report, args)
    return (3 if result.report.todo_count else 0), result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.inputs:
        build_parser().print_help()
        return 1
    if args.output and len(args.inputs) > 1:
        print("bat2sh: -o/--output 仅适用于单个输入文件，多文件请使用 --outdir", file=sys.stderr)
        return 1
    settings = settings_from_args(args)
    todo_total = 0
    has_error = False
    for raw_path in args.inputs:
        path = Path(raw_path)
        if not path.is_file():
            print(f"bat2sh: 文件不存在: {path}", file=sys.stderr)
            has_error = True
            continue
        code, result = run_one(path, settings, args.encoding, args)
        if code == 2:
            has_error = True
        if result is not None:
            todo_total += result.report.todo_count
        elif code == 3:
            todo_total += 1
    if has_error:
        return 2
    if args.fail_on_todo and todo_total:
        return 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
