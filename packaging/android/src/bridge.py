"""bat2sh core 调用桥 —— core 零改动。

core 是纯标准库（既不需要 PySide6 也不需要第三方包），可以整目录打进 Flet 包，
由 packaging/android/sync-core.sh 从 python/bat2sh/ 同步而来。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bat2sh.core.encoding import decode_bytes  # noqa: E402
from bat2sh.core.engine import convert_text  # noqa: E402
from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.core.types import ConvertReport, Diagnostic, SourceKind  # noqa: E402

SUPPORTED_SUFFIXES = ("bat", "cmd", "ps1")
DIAGNOSTIC_DISPLAY_LIMIT = 80


def kind_for(name: str) -> SourceKind:
    return SourceKind.from_suffix(Path(name).suffix)


def default_settings() -> ConvertSettings:
    """Android 侧默认转换设置。

    bash_check 必须为 False —— 这是上一 session 点名的 P1：
    core/syntax.py 的 bash_syntax_error() 用 shutil.which("bash") 找 bash，
    找不到就 return None（静默判通过）。Android 上即便把 $PREFIX/bin/bash
    放进 PATH，subprocess.run 也可能被沙箱拒并被同一个 except 吞掉，
    于是「校验通过」是假的。

    正确做法：这里关掉内建校验，改由 ui/runner.py 显式经 Termux bash 跑
    bash -n，并把「是否真的校验过」如实呈现在报告里。
    """
    s = ConvertSettings()
    s.bash_check = False
    return s.normalized()


@dataclass
class Conversion:
    """一次转换的结果（UI 只认这个结构）。"""

    ok: bool = False
    source_name: str = "input"
    kind: SourceKind = SourceKind.UNKNOWN
    script: str = ""
    report: ConvertReport | None = None
    error: str = ""

    @property
    def output_name(self) -> str:
        stem = Path(self.source_name).stem or "output"
        return stem + ".sh"

    def headline(self) -> str:
        if self.error:
            return "转换失败：" + self.error
        rep = self.report
        if rep is None:
            return "转换完成（无报告）"
        return ("转换完成：%s  %d 行 -> 转换 %d / 未变 %d；错误 %d / 警告 %d / TODO %d"
                % (rep.kind.display_name, rep.total_lines, rep.converted_lines,
                   rep.unchanged_lines, rep.error_count, rep.warning_count,
                   rep.todo_count))

    def diagnostics(self) -> list[str]:
        rep = self.report
        if rep is None:
            return [self.headline()] if self.error else []
        lines = [self.headline()]
        for title, items in (("错误", rep.errors), ("警告", rep.warnings),
                             ("TODO", rep.todos)):
            if not items:
                continue
            lines.append("")
            lines.append("[%s] 共 %d 条" % (title, len(items)))
            for d in items[:DIAGNOSTIC_DISPLAY_LIMIT]:
                lines.append("  " + _format_diagnostic(d))
            if len(items) > DIAGNOSTIC_DISPLAY_LIMIT:
                lines.append("  ... 其余 %d 条省略" % (len(items) - DIAGNOSTIC_DISPLAY_LIMIT))
        return lines


def _format_diagnostic(d: Diagnostic) -> str:
    try:
        return d.format()
    except Exception:  # noqa: BLE001
        return "第 %s 行: %s" % (getattr(d, "line", "?"), getattr(d, "message", d))


def convert(source_text: str, source_name: str) -> Conversion:
    """调用 core 转换。异常一律收敛成 Conversion.error，不向 UI 抛。"""
    kind = kind_for(source_name)
    if kind is SourceKind.UNKNOWN:
        return Conversion(
            source_name=source_name, kind=kind,
            error="不支持的文件类型 %s（只支持 .bat / .cmd / .ps1）" % source_name)
    if not source_text.strip():
        return Conversion(source_name=source_name, kind=kind, error="源内容为空")
    try:
        script, report = convert_text(source_text, kind, default_settings(), source_name)
    except Exception as exc:  # noqa: BLE001
        return Conversion(source_name=source_name, kind=kind,
                          error=type(exc).__name__ + ": " + str(exc))
    return Conversion(ok=True, source_name=source_name, kind=kind,
                      script=script, report=report)


def decode_source(raw: bytes) -> tuple[str, str, bool]:
    """解码源文件字节流。返回 (文本, 编码名, 是否发生过替换)。

    Android 上拿到的 .bat/.cmd 常是 GBK —— 复用 core 的探测逻辑，
    避免在 UI 层另写一套。
    """
    try:
        d = decode_bytes(raw)
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", errors="replace"), "utf-8", True
    return d.text, d.encoding, bool(d.replaced)
