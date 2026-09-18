"""命令行模式：``bat2sh --cli input.bat -o output.sh``。"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import APP_DESCRIPTION, __version__
from .core.api import fixer, parallel
from .core.api.config import (
    load_api_config,
    missing_requirements,
    resolve_api_config,
)
from .core.api.provider import (
    ProviderConfigError,
    create_provider,
    redact,
)
from .core.encoding import decode_bytes, normalize_newlines
from .core.engine import (
    ConversionResult,
    convert_file,
    convert_text,
    detect_kind,
    output_path_for,
    write_output,
)
from .core.settings import ConvertSettings, resolve_cfg_state_machine
from .core.types import ConvertReport, SourceKind, report_blocks

RUN_EXIT_TODO = 4
RUN_EXIT_FAILED = 5
FIX_EXIT_CONFIG = 6
DEFAULT_RUN_TIMEOUT = 30.0
FIX_MAX_RETRY_ROUNDS = 3

_ANSI_COLORS = {
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "todo": "\x1b[90m",
    "ok": "\x1b[32m",
}
_ANSI_RESET = "\x1b[0m"


def color_enabled(stream, mode: str = "auto") -> bool:
    """终端支持色时启用：NO_COLOR（非空）优先关闭，FORCE_COLOR 强制开启（重定向/测试用），
    TERM 为 dumb 或未设置时关闭（.desktop 启动的进程不继承 shell 环境），其余情况要求 TTY。
    任何检测失败一律保守返回 False，绝不抛出。

    ``mode`` 为命令行显式开关时压过环境探测（优先级 显式 > 环境 > TTY）：

    - ``"never"``（``--no-color``）→ 恒关，压过 ``FORCE_COLOR`` 与 TTY；
    - ``"always"``（``--color``）→ 恒开，压过 ``NO_COLOR`` 与非 TTY；
    - ``"auto"``（默认）→ 环境探测逻辑（保持既有行为）。
    """
    if mode == "never":
        return False
    if mode == "always":
        return True
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
    if not env.get("TERM", ""):
        return False
    try:
        return bool(stream.isatty())
    except Exception:  # 检测失败 = 保守关色（stream 无 isatty / 已关闭 / 其它异常）
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
        "--cfg-state",
        dest="cfg_state",
        action="store_const",
        const=True,
        default=None,
        help="启用 CFG 标签分派状态机（默认启用；优先级 CLI > 环境变量 > 配置文件）",
    )
    parser.add_argument(
        "--no-cfg-state",
        dest="cfg_state",
        action="store_const",
        const=False,
        help="禁用 CFG 状态机（回退 v2.4.0 的 goto 诚实 TODO 行为；逃生通道）",
    )
    parser.add_argument(
        "--no-bash-check",
        action="store_true",
        help="跳过生成脚本的 bash -n 语法校验（调试用；默认失败时降级为注释）",
    )
    parser.add_argument(
        "--last-exit-code",
        choices=["warn", "map"],
        default="map",
        help="处理 PowerShell $LASTEXITCODE / 批处理 %%ERRORLEVEL%% 的退出码策略（默认 map）："
        "map = 近似映射为 bash $?（首次捕获到 __bat2sh_rc）；"
        "warn = 生成 TODO 提示手工复核",
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
        help="跳过执行确认（非交互环境必需；仍受 TODO 防护，见 --force；不适用于 --fix-todos）",
    )
    parser.add_argument(
        "--run-timeout",
        type=float,
        default=DEFAULT_RUN_TIMEOUT,
        metavar="N",
        help=f"执行超时秒数（默认 {DEFAULT_RUN_TIMEOUT:g}；超时退出码 5）",
    )
    parser.add_argument("--run-cwd", metavar="DIR", help="执行工作目录（默认脚本所在目录）")
    parser.add_argument(
        "--fix-todos",
        action="store_true",
        help="调用 API 为无法自动转换的 TODO 生成修复建议（需交互终端；多选后合并为一次隐私确认，"
        "并行执行并显示聚合面板；diff 确认后才写入；API 建议仍需人工复核；与 --run 互斥；"
        "# TODO[REG]（注册表写类）是结构化 TODO，不自动修复，仅作为 API 处理输入）",
    )
    parser.add_argument(
        "--api-provider", default=None, help="API 类型（当前仅 openai；默认读配置文件/环境变量）"
    )
    parser.add_argument(
        "--api-base", default=None, help="API 地址（OpenAI 兼容；如 https://api.openai.com/v1）"
    )
    parser.add_argument("--api-model", default=None, help="模型名（如 gpt-4o-mini）")
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key（不推荐：会进入 shell 历史；建议用 BAT2SH_API_KEY 或配置文件）",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=None,
        metavar="N",
        help="API 空闲超时秒数（默认 30；流式响应中两次数据到达的最大间隔）",
    )
    parser.add_argument(
        "--api-context-lines",
        type=int,
        default=None,
        metavar="N",
        help="发送的源文件上下文行数（默认 3，上限 10）",
    )
    parser.add_argument(
        "--max-concurrency",
        "--parallel",
        dest="max_concurrency",
        type=int,
        default=None,
        metavar="N",
        help="TODO 并行修复的并发数（默认 3，范围 1-16；"
        "也可用 BAT2SH_MAX_CONCURRENCY 或 ~/.config/bat2sh/api.json 的 max_concurrency 配置）",
    )
    parser.add_argument(
        "--enable-thinking",
        dest="enable_thinking",
        action="store_true",
        default=None,
        help="启用模型思维链（更准但更慢；默认关；对应配置文件字段 enable_thinking）",
    )
    parser.add_argument(
        "--no-thinking",
        dest="enable_thinking",
        action="store_false",
        default=None,
        help="关闭模型思维链（默认；对 Qwen3 等混合思考模型生效）",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument(
        "--color",
        dest="color",
        action="store_const",
        const="always",
        default="auto",
        help="强制启用 ANSI 色彩（即使输出被重定向/非 TTY；覆盖 NO_COLOR）",
    )
    color_group.add_argument(
        "--no-color",
        dest="color",
        action="store_const",
        const="never",
        help="禁用 ANSI 色彩（优先级高于 FORCE_COLOR 与 TTY 检测；遵循 no-color.org）",
    )
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
        cfg_state_machine=resolve_cfg_state_machine(args.cfg_state),
    )


def _emit_report(convert_report: ConvertReport, args: argparse.Namespace) -> None:
    if args.report:
        text = render_report_text(convert_report, color_enabled(sys.stderr, args.color))
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
        if color_enabled(sys.stderr, args.color):
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


def _api_cli_values(args: argparse.Namespace) -> dict[str, object]:
    return {
        "provider": args.api_provider,
        "base_url": args.api_base,
        "model": args.api_model,
        "api_key": args.api_key,
        "timeout": args.api_timeout,
        "context_lines": args.api_context_lines,
        "enable_thinking": args.enable_thinking,
        "max_concurrency": args.max_concurrency,
    }


_SELECTION_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")


def _one_line(text: str, limit: int = 72) -> str:
    """折叠空白为单行并按长度截断（面板/隐私提示共用）。"""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3] + "..."


def _parse_selection(text: str, count: int) -> list[int]:
    """解析 ``1,3-5`` 为去重后的 1-based 序号；越界忽略，无法识别时抛 ``ValueError(token)``。"""
    chosen: list[int] = []
    seen: set[int] = set()
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        match = _SELECTION_RE.match(token)
        if match is None:
            raise ValueError(token)
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if end < start:
            start, end = end, start
        for number in range(start, end + 1):
            if 1 <= number <= count and number not in seen:
                seen.add(number)
                chosen.append(number)
    return chosen


class _FixPanel:
    """并行修复聚合面板：每条 TODO 一行，按状态着色。

    ``parallel.run_parallel`` 在内部锁内串行回调事件，本类无需自带锁。
    TTY 用 ANSI 原地刷新整块；非 TTY 追加式逐行输出（测试依赖此路径）。
    """

    _TAIL_LIMIT = 60
    _STATUS_LEVELS = {
        parallel.STATUS_DONE: "ok",
        parallel.STATUS_FAILED: "error",
        parallel.STATUS_SKIPPED: "warning",
        parallel.STATUS_RUNNING: "todo",
        parallel.STATUS_PENDING: "todo",
    }

    def __init__(self, tasks, stream, *, color: bool, tty: bool, secret: str = "") -> None:
        self._tasks = list(tasks)
        self._by_index = {task.index: task for task in tasks}
        self._stream = stream
        self._color = color
        self._tty = tty
        self._secret = secret
        self._tails: dict[int, str] = {}
        self._lines_drawn = 0
        self._last_append = ""

    def handle(self, event: parallel.FixEvent) -> None:
        task = self._by_index.get(event.index)
        if task is not None and not event.chunk:
            task.status = event.status
            task.detail = event.detail
        if event.chunk:
            tail = self._tails.get(event.index, "") + event.chunk
            self._tails[event.index] = tail[-self._TAIL_LIMIT :]
        if self._tty:
            self._redraw()
        else:
            self._append(event)

    def _line(self, task) -> str:
        line = parallel.format_status_line(task)
        tail = self._tails.get(task.index, "")
        if task.status == parallel.STATUS_RUNNING and tail:
            line += " | " + tail.replace("\n", " ")
        line = redact(line, self._secret)
        if self._color:
            level = self._STATUS_LEVELS.get(task.status)
            if level is not None:
                line = _paint(line, level)
        return line

    def _append(self, event: parallel.FixEvent) -> None:
        if event.chunk:
            line = f"[#{event.index}] {event.chunk}"
        else:
            line = self._line(self._by_index[event.index])
        if not line or line == self._last_append:
            return
        self._stream.write(line + "\n")
        self._stream.flush()
        self._last_append = line

    def _redraw(self) -> None:
        lines = [self._line(task) for task in self._tasks]
        if self._lines_drawn:
            self._stream.write(f"\x1b[{self._lines_drawn}A")
        for line in lines:
            self._stream.write("\r\x1b[K" + line + "\n")
        self._stream.flush()
        self._lines_drawn = len(lines)


def _fix_counts(selected) -> tuple[int, int, list]:
    """返回 (已修复数, 跳过数, 失败任务列表)；合并丢弃的条目已就地标记为 failed。"""
    fixed = sum(1 for t in selected if t.status == parallel.STATUS_DONE)
    skipped = sum(1 for t in selected if t.status == parallel.STATUS_SKIPPED)
    failed = [t for t in selected if t.status == parallel.STATUS_FAILED]
    return fixed, skipped, failed


def _emit_fix_summary(selected, secret: str) -> None:
    fixed, skipped, failed = _fix_counts(selected)
    print(
        f"bat2sh: TODO 处理完成：修复 {fixed} / 跳过 {skipped} / 失败 {len(failed)}"
        f"（共 {len(selected)} 条选中）",
        file=sys.stderr,
    )
    print(
        "bat2sh: 注意：API 建议仍需人工复核，不保证语义正确。",
        file=sys.stderr,
    )
    if failed:
        print("bat2sh: 以下条目未修复：", file=sys.stderr)
        for task in failed:
            print(
                "  " + redact(parallel.format_status_line(task), secret),
                file=sys.stderr,
            )


def _fix_todos_flow(path: Path, settings: ConvertSettings, args: argparse.Namespace) -> int:
    """``--fix-todos`` 主流程：多选 → 一次隐私确认 → 并行修复 → 聚合 diff → 一次写盘。

    退出码（§10）：0 全部处理（含无可修复）；1 非交互拒绝 / 用户 q / Ctrl+C；
    2 转换或写盘错误；3 仍有未修复项（跳过 + 失败）或取消应用；6 API 配置错误。
    """
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

    if fixer.is_degraded(convert_report):
        print(
            "bat2sh: 生成脚本未通过 bash -n，已整体降级为注释；无可修复 TODO（请人工转换）",
            file=sys.stderr,
        )
        return 3

    markers = fixer.scan_todo_markers(text, convert_report)
    if not markers:
        print(
            "bat2sh: 未发现可修复 TODO（管道整块标记与降级头不参与 API 修复）",
            file=sys.stderr,
        )
        return 0

    if not sys.stdin.isatty():
        print(
            "bat2sh: --fix-todos 需要交互终端（每次发送前必须确认，不可绕过），已拒绝",
            file=sys.stderr,
        )
        return 1

    api_config = resolve_api_config(_api_cli_values(args), os.environ, load_api_config())
    missing = missing_requirements(api_config)
    if missing:
        print("bat2sh: API 配置不完整: " + "；".join(missing), file=sys.stderr)
        print(
            "bat2sh: 请用 --api-base/--api-model、环境变量或 ~/.config/bat2sh/api.json 配置",
            file=sys.stderr,
        )
        return FIX_EXIT_CONFIG
    try:
        provider = create_provider(api_config)
    except ProviderConfigError as exc:
        print(f"bat2sh: API 配置错误: {exc}", file=sys.stderr)
        return FIX_EXIT_CONFIG

    all_tasks = parallel.plan_tasks(
        markers, decoded.text, path.name, text, api_config.context_lines
    )
    selected = all_tasks
    if len(all_tasks) > 1:
        for task in all_tasks:
            print(
                f"{task.index}. 第 {task.out_line} 行: {_one_line(task.marker.marker_text)}",
                file=sys.stderr,
            )
        sys.stderr.write(
            "bat2sh: 选择要修复的条目（如 1,3-5；回车=全部；q=取消）[all] "
        )
        sys.stderr.flush()
        try:
            choice = sys.stdin.readline()
        except OSError:
            choice = ""
        lowered = choice.strip().lower()
        if lowered in ("q", "quit"):
            print("bat2sh: 已取消", file=sys.stderr)
            return 1
        if lowered not in ("", "all"):
            try:
                indices = _parse_selection(choice.strip(), len(all_tasks))
            except ValueError as exc:
                print(f"bat2sh: 未识别的选择: {exc}", file=sys.stderr)
                return 3
            if not indices:
                return 3
            selected = [all_tasks[index - 1] for index in indices]

    sys.stderr.write(
        f"bat2sh: 即将把 {len(selected)} 条 TODO 发送到外部服务：{api_config.base_url}\n"
    )
    sys.stderr.write(
        "bat2sh: 内容将离开本机，可能被服务提供方记录（prompt 不含 API key）。\n"
    )
    sys.stderr.write("── 将发送的条目 ────────────\n")
    for task in selected:
        sys.stderr.write(
            f"#{task.index} 第 {task.out_line} 行: {_one_line(task.marker.marker_text)}\n"
        )
    sys.stderr.write("───────────────────────────\n")
    if not _confirm(f"bat2sh: 发送 {len(selected)} 条到 {api_config.base_url}？[y/N]"):
        print("bat2sh: 已取消发送，未写盘", file=sys.stderr)
        return 3

    color = color_enabled(sys.stderr, args.color)
    panel = _FixPanel(
        selected,
        sys.stderr,
        color=color,
        tty=color and sys.stderr.isatty(),
        secret=api_config.api_key,
    )
    if not args.quiet:
        print(
            f"bat2sh: 并发 {api_config.max_concurrency}（--max-concurrency 可调）",
            file=sys.stderr,
        )

    pending = selected
    try:
        for _round in range(FIX_MAX_RETRY_ROUNDS):
            parallel.run_parallel(
                pending,
                provider,
                text=text,
                timeout=api_config.timeout,
                on_event=panel.handle,
                max_concurrency=api_config.max_concurrency,
            )
            failures = [t for t in selected if t.status == parallel.STATUS_FAILED]
            if not failures or not sys.stdin.isatty():
                break
            for task in failures:
                print(
                    redact(parallel.format_status_line(task), api_config.api_key),
                    file=sys.stderr,
                )
            if not _confirm(f"bat2sh: 重试失败的 {len(failures)} 条？[y/N]"):
                break
            for task in failures:
                task.status = parallel.STATUS_PENDING
                task.replacement = ""
                task.detail = ""
                task.retries = 0
            pending = failures
    except KeyboardInterrupt:
        print("\nbat2sh: 已中断，未写盘（本次会话修改已丢弃）", file=sys.stderr)
        return 1

    merged, dropped = parallel.merge_replacements(text, selected)
    for task in dropped:
        print(
            "bat2sh: 合并丢弃："
            + redact(parallel.format_status_line(task), api_config.api_key),
            file=sys.stderr,
        )
    fixed, skipped, failed = _fix_counts(selected)

    apply_confirmed = True
    if merged != text:
        diff_text = fixer.render_diff(text, merged, "当前", "建议")
        if diff_text:
            sys.stderr.write(diff_text + "\n")
        apply_confirmed = _confirm(f"bat2sh: 应用全部 {fixed} 处修改？[y/N]")
        if not apply_confirmed:
            print("bat2sh: 已取消应用，未写盘", file=sys.stderr)

    write_code = 0
    if merged != text and apply_confirmed:
        if args.print_only:
            sys.stdout.write(merged)
            if not merged.endswith("\n"):
                sys.stdout.write("\n")
        elif args.dry_run:
            if not args.quiet:
                print(f"[dry-run] 将写出修复后的脚本（{fixed} 处修改）", file=sys.stderr)
        else:
            output_override = args.output if args.output else None
            result = ConversionResult(
                source_path=str(path),
                output_path=str(
                    Path(output_override).expanduser()
                    if output_override
                    else output_path_for(path, settings)
                ),
                kind=kind,
                encoding=decoded.encoding,
                text=merged,
                report=convert_report,
            )
            write_output(result, settings)
            if result.error:
                print(f"bat2sh: {result.error}", file=sys.stderr)
                write_code = 2
            elif not args.quiet:
                print(
                    f"[已写出] {result.output_path}（API 修复 {fixed} 处，请复核后再使用）",
                    file=sys.stderr,
                )

    _emit_fix_summary(selected, api_config.api_key)
    if write_code:
        return write_code
    if not apply_confirmed or skipped or failed:
        return 3
    return 0


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
    if args.fix_todos and args.run:
        print(
            "bat2sh: --fix-todos 与 --run 互斥（请先修复并确认，再自行运行脚本）",
            file=sys.stderr,
        )
        return 1
    if args.fix_todos and len(args.inputs) > 1:
        print("bat2sh: --fix-todos 仅支持单个输入文件", file=sys.stderr)
        return 1
    if args.print_only and args.dry_run and not args.quiet:
        print("bat2sh: --print 模式下不写文件，--dry-run 已忽略", file=sys.stderr)
    settings = settings_from_args(args)
    if args.fix_todos:
        path = Path(args.inputs[0])
        if not path.is_file():
            print(f"bat2sh: 文件不存在: {path}", file=sys.stderr)
            return 2
        return _fix_todos_flow(path, settings, args)
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
