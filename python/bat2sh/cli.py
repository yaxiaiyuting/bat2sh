"""命令行模式：``bat2sh --cli input.bat -o output.sh``。"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import APP_DESCRIPTION, __version__
from .core.encoding import decode_bytes, normalize_newlines
from .core.engine import (
    ConversionResult,
    convert_file,
    convert_text,
    detect_kind,
    output_path_for,
)
from .core.settings import ConvertSettings
from .core.types import ConvertReport, SourceKind, report_blocks

RUN_EXIT_TODO = 4
RUN_EXIT_FAILED = 5
DEFAULT_RUN_TIMEOUT = 30.0

_ANSI_COLORS = {
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "todo": "\x1b[90m",
    "ok": "\x1b[32m",
}
_ANSI_RESET = "\x1b[0m"


def color_enabled(stream) -> bool:
    """终端支持色时启用：NO_COLOR（非空）优先关闭，FORCE_COLOR 强制开启（重定向/测试用），
    其余情况要求 TTY 且 TERM != dumb。"""
    env = os.environ
    if env.get("NO_COLOR"):
        return False
    if env.get("TERM", "") == "dumb":
        return False
    force = env.get("FORCE_COLOR", "")
    if force.lower() in ("0", "false"):
        return False
    if force:
        return True
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _paint(text: str, level: str) -> str:
    """按级别着色；level 无对应颜色或空行时原样返回。"""
    color = _ANSI_COLORS.get(level)
    if not text or color is None:
        return text
    return f"{color}{text}{_ANSI_RESET}"


def render_report_text(report: ConvertReport, color: bool) -> str:
    """渲染报告文本；color=True 时按错误红/警告黄/TODO 灰着色（与 GUI 共用 report_blocks）。"""
    blocks = report_blocks(report)
    lines = [_paint(text, level) if color else text for text, level in blocks]
    return "\n".join(lines)


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
    parser.add_argument(
        "--no-bash-check",
        action="store_true",
        help="跳过生成脚本的 bash -n 语法校验（调试用；默认失败时降级为注释）",
    )
    parser.add_argument(
        "--last-exit-code",
        choices=["warn", "map"],
        default="warn",
        help="处理 PowerShell $LASTEXITCODE / 批处理 %%ERRORLEVEL%% 的退出码策略（默认 warn）："
        "warn = 生成 TODO 提示手工复核；"
        "map = 近似映射为 bash $?（首次捕获到 __bat2sh_rc）",
    )
    parser.add_argument("--encoding", help="强制指定输入编码（默认自动检测）")
    parser.add_argument("--no-overwrite", action="store_true", help="输出已存在时拒绝覆盖")
    parser.add_argument("--print", dest="print_only", action="store_true", help="只输出到 stdout，不写文件")
    parser.add_argument("--diff", action="store_true", help="打印源文件与转换结果的 unified diff")
    parser.add_argument("--dry-run", action="store_true", help="只显示将写出的文件，不实际写盘")
    report_group = parser.add_mutually_exclusive_group()
    report_group.add_argument("--report", action="store_true", help="打印转换报告")
    report_group.add_argument(
        "--report-json",
        action="store_true",
        help="以 JSON 格式打印转换报告（与 --report 互斥）",
    )
    parser.add_argument("--fail-on-todo", action="store_true", help="存在 TODO 或错误时返回退出码 3")
    parser.add_argument(
        "--run",
        action="store_true",
        help="转换后执行生成的脚本（不写文件；含 TODO/错误时默认拒绝，退出码 4）",
    )
    parser.add_argument("--force", action="store_true", help="跳过 TODO 防护与执行确认")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过执行确认（非交互环境必需；仍受 TODO 防护，见 --force）",
    )
    parser.add_argument(
        "--run-timeout",
        type=float,
        default=DEFAULT_RUN_TIMEOUT,
        metavar="N",
        help=f"执行超时秒数（默认 {DEFAULT_RUN_TIMEOUT:g}；超时退出码 5）",
    )
    parser.add_argument("--run-cwd", metavar="DIR", help="执行工作目录（默认脚本所在目录）")
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
        last_exit_code=args.last_exit_code,
        bash_check=not args.no_bash_check,
        overwrite=not args.no_overwrite,
    )


def _emit_report(convert_report: ConvertReport, args: argparse.Namespace) -> None:
    if args.report:
        text = render_report_text(convert_report, color_enabled(sys.stderr))
        sys.stderr.write(text + "\n")
    elif args.report_json:
        payload = convert_report.to_json() + "\n"
        # --print 时 stdout 属于脚本本身，JSON 报告只能走 stderr
        stream = sys.stderr if args.print_only else sys.stdout
        stream.write(payload)


def _emit_diff(
    source_text: str, output_text: str, from_name: str, to_name: str, stream
) -> None:
    source_lines = normalize_newlines(source_text).splitlines()
    output_lines = normalize_newlines(output_text).splitlines()
    diff_lines = list(
        difflib.unified_diff(
            source_lines, output_lines, fromfile=from_name, tofile=to_name, lineterm=""
        )
    )
    if not diff_lines:
        return
    stream.write("\n".join(diff_lines) + "\n")


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
    if args.diff:
        _emit_diff(
            decoded.text,
            text,
            path.name,
            output_path_for(path, settings).name,
            sys.stderr,
        )
    _emit_report(convert_report, args)
    return 3 if (convert_report.todo_count or convert_report.error_count) else 0


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
        path,
        settings,
        encoding_override=encoding,
        output_override=output_override,
        write=not args.dry_run,
    )
    if result.error:
        print(f"bat2sh: {result.error}", file=sys.stderr)
        return 2, result
    if args.dry_run:
        if not args.quiet:
            out_path = Path(result.output_path)
            if (
                out_path.exists()
                and not settings.overwrite
                and not settings.backup_existing
            ):
                print(
                    f"bat2sh: 输出文件已存在且未允许覆盖: {out_path}",
                    file=sys.stderr,
                )
                return 2, result
            suffix = (
                "（已存在，将先备份）"
                if out_path.exists() and settings.backup_existing
                else ""
            )
            print(f"[dry-run] 将写出: {out_path}{suffix}", file=sys.stderr)
    elif not args.quiet:
        status = "已写出" if result.written else "未写出"
        report = result.report
        if report.error_count:
            level = "error"
        elif report.warning_count or report.todo_count:
            level = "warning"
        else:
            level = "ok"
        status_line = (
            f"[{status}] {result.source_path} -> {result.output_path}"
            f" | 转换 {report.converted_lines} 行"
            f" | 错误 {report.error_count}"
            f" | 警告 {report.warning_count}"
            f" | TODO {report.todo_count}"
        )
        if color_enabled(sys.stderr):
            status_line = _paint(status_line, level)
        sys.stderr.write(status_line + "\n")
    if args.diff:
        try:
            decoded = decode_bytes(path.read_bytes(), encoding)
        except OSError:
            decoded = None
        if decoded is not None:
            _emit_diff(
                decoded.text,
                result.text,
                path.name,
                Path(result.output_path).name,
                sys.stdout,
            )
    _emit_report(result.report, args)
    return (3 if (result.report.todo_count or result.report.error_count) else 0), result


def _confirm(prompt: str) -> bool:
    sys.stderr.write(prompt + " ")
    sys.stderr.flush()
    try:
        reply = sys.stdin.readline()
    except OSError:
        return False
    return reply.strip().lower() in {"y", "yes"}


def _emit_run_todos(convert_report: ConvertReport) -> None:
    sys.stderr.write(
        f"bat2sh: 转换结果包含 {convert_report.error_count} 处错误、"
        f"{convert_report.todo_count} 处无法自动转换（TODO），已拒绝执行。\n"
    )
    sys.stderr.write("bat2sh: 请人工检查以下位置，或使用 --force 强制执行：\n")
    for diagnostic in (*convert_report.errors, *convert_report.todos):
        sys.stderr.write("  " + diagnostic.format() + "\n")


def _execute_converted(text: str, cwd: Path, timeout: float) -> int:
    try:
        with NamedTemporaryFile(
            "w", suffix=".sh", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(text)
            tmp_path = Path(handle.name)
    except OSError as exc:
        print(f"bat2sh: 无法创建临时脚本: {exc}", file=sys.stderr)
        return RUN_EXIT_FAILED
    try:
        completed = subprocess.run(
            ["bash", str(tmp_path)], cwd=str(cwd), timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        print(f"bat2sh: 执行超时（超过 {timeout:g} 秒），已终止", file=sys.stderr)
        return RUN_EXIT_FAILED
    except OSError as exc:
        print(f"bat2sh: 无法启动 bash: {exc}", file=sys.stderr)
        return RUN_EXIT_FAILED
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
    if completed.returncode < 0:
        print(
            f"bat2sh: 脚本被信号终止（信号 {-completed.returncode}）",
            file=sys.stderr,
        )
        return RUN_EXIT_FAILED
    return completed.returncode


def _run_flow(path: Path, settings: ConvertSettings, args: argparse.Namespace) -> int:
    kind = detect_kind(path)
    if kind is SourceKind.UNKNOWN:
        print(f"bat2sh: 不支持的源文件类型: {path}", file=sys.stderr)
        return 2
    try:
        decoded = decode_bytes(path.read_bytes(), args.encoding)
    except OSError as exc:
        print(f"bat2sh: 读取失败: {exc}", file=sys.stderr)
        return 2
    text, convert_report = convert_text(decoded.text, kind, settings, path.name)
    convert_report.encoding = decoded.encoding

    if (convert_report.todo_count or convert_report.error_count) and not args.force:
        _emit_run_todos(convert_report)
        return RUN_EXIT_TODO

    if not args.quiet:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if not args.force and not args.yes:
        if not sys.stdin.isatty():
            print(
                "bat2sh: 非交互环境执行需显式 --yes（或 --force），已拒绝执行",
                file=sys.stderr,
            )
            return 1
        if not _confirm("将执行以上脚本，继续？[y/N]"):
            print("bat2sh: 已取消执行", file=sys.stderr)
            return 1

    cwd = Path(args.run_cwd).expanduser() if args.run_cwd else path.parent
    if not cwd.is_dir():
        print(f"bat2sh: 工作目录不存在: {cwd}", file=sys.stderr)
        return 2

    return _execute_converted(text, cwd, args.run_timeout)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.inputs:
        build_parser().print_help()
        return 1
    if args.output and len(args.inputs) > 1:
        print("bat2sh: -o/--output 仅适用于单个输入文件，多文件请使用 --outdir", file=sys.stderr)
        return 1
    if args.run and len(args.inputs) > 1:
        print("bat2sh: --run 仅支持单个输入文件", file=sys.stderr)
        return 1
    if args.print_only and args.dry_run and not args.quiet:
        print("bat2sh: --print 模式下不写文件，--dry-run 已忽略", file=sys.stderr)
    settings = settings_from_args(args)
    if args.run:
        path = Path(args.inputs[0])
        if not path.is_file():
            print(f"bat2sh: 文件不存在: {path}", file=sys.stderr)
            return 2
        return _run_flow(path, settings, args)
    blocking_total = 0
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
            blocking_total += result.report.todo_count + result.report.error_count
        elif code == 3:
            blocking_total += 1
    if has_error:
        return 2
    if args.fail_on_todo and blocking_total:
        return 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
