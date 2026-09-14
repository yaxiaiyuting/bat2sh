"""TODO 标记扫描与替换（纯函数，CLI/GUI 共用）。

设计依据 ``docs/api-fix-design.md`` §1.5（方案 A：输出后扫描 + 尽力对齐）与 §4.1（发送边界）、
§9.1（Q7/Q8）：
- 工作列表 = M1（整行）/ M3（行尾追加）/ M4（行内条件）三类动作性标记；
- M2（``# TODO: 复杂管道需手动重写``）不参与 API 修复；M5/M6 为说明/降级文本，直接排除；
- 每次仅发送：标记原文 + 报告元数据（对齐到的源行号/分类/信息）+ 源文件 ±N 行 +
  目标 Bash 相邻 2 行；不发送整文件，上下文中的其它 TODO 文本被替换为占位说明。

不做任何 I/O；``bash -n`` 校验由调用方完成（syntax.bash_syntax_error）。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from ..types import ConvertReport, Diagnostic

# 目标 Bash 行前后固定发送的行数（§4.1：所在生成行及相邻 2 行）
OUTPUT_CONTEXT_LINES = 2
# 源文件上下文上限（与 config.MAX_CONTEXT_LINES 一致；此处仅作文档性常量）
MAX_SOURCE_CONTEXT_LINES = 10

_MARKER_RE = re.compile(r"#\s*TODO\b")
_M2_TEXT = "复杂管道需手动重写"
_M5_TEXT = "带有 # TODO 标记"
_M6_TEXT = "生成脚本未通过 bash -n"
_EXTRACT_KEYS = (": 手动检查条件: ", ": 手动检查: ")
_OTHER_TODO_PLACEHOLDER = "# TODO: （其它待人工检查项，已省略）"


@dataclass
class TodoMarker:
    """生成脚本中一处可操作的 TODO 标记。"""

    out_line: int  # 1-based 输出行号（扫描时）
    kind: str  # "line"（整行注释）| "inline"（代码行内注释）
    line_text: str  # 该输出行的原文
    marker_text: str  # 从 ``#`` 起的注释片段
    original: str = ""  # 从标记提取的原命令（可为空）
    source_line: int = 0  # 对齐到的源文件行号（0 = 未知）
    category: str = ""
    diagnostic_message: str = ""
    ambiguous: bool = False  # 同一 original 对应多条诊断（定位不唯一）


def is_degraded(report: ConvertReport | None) -> bool:
    """整份脚本是否因 ``bash -n`` 失败被降级（category="syntax"）。"""
    if report is None:
        return False
    return any(d.category == "syntax" for d in report.errors)


def scan_todo_markers(
    output_text: str, report: ConvertReport | None = None
) -> list[TodoMarker]:
    """扫描生成脚本中的动作性 TODO 标记（M1/M3/M4），尽力对齐报告元数据。

    - 排除 M2（管道通用标记）、M5（文件头说明）、M6（降级头）；
    - 出现 M6 或报告标记为降级时返回空列表（整份降级不参与修复）；
    - 同一行多个 ``# TODO`` 只取第一个；
    - 对齐按 ``original`` 精确匹配（strip 后），多条命中时取第一条并标记 ambiguous。
    """
    if _M6_TEXT in output_text or is_degraded(report):
        return []
    diagnostics: list[Diagnostic] = []
    if report is not None:
        diagnostics = [*report.todos, *report.errors]
    markers: list[TodoMarker] = []
    for number, line in enumerate(output_text.splitlines(), start=1):
        match = _MARKER_RE.search(line)
        if match is None:
            continue
        if _M5_TEXT in line or _M2_TEXT in line or _M6_TEXT in line:
            continue
        marker = TodoMarker(
            out_line=number,
            kind="line" if not line[: match.start()].strip() else "inline",
            line_text=line,
            marker_text=line[match.start() :].rstrip(),
        )
        marker.original = _extract_original(marker.marker_text)
        if marker.original and diagnostics:
            wanted = marker.original.strip()
            matches = [
                d
                for d in diagnostics
                if d.original and d.original.strip() == wanted
            ]
            if matches:
                chosen = matches[0]
                marker.source_line = chosen.line
                marker.category = chosen.category
                marker.diagnostic_message = chosen.message
                marker.ambiguous = len(matches) > 1
        markers.append(marker)
    return markers


def _extract_original(marker_text: str) -> str:
    for key in _EXTRACT_KEYS:
        if key in marker_text:
            return marker_text.split(key, 1)[1].strip()
    return ""


def _redact_other_todos(line: str) -> str:
    index = line.find("# TODO")
    if index < 0:
        return line
    return line[:index] + _OTHER_TODO_PLACEHOLDER


def build_prompt(
    marker: TodoMarker,
    source_text: str,
    source_name: str,
    output_text: str,
    context_lines: int,
    out_line: int | None = None,
) -> str:
    """构造将发送给 Provider 的完整 prompt（也是隐私提示中展示的原文）。

    ``out_line`` 用于替换过程中行号漂移后的有效行号（默认取 ``marker.out_line``）。
    """
    effective = out_line if out_line is not None else marker.out_line
    parts: list[str] = [
        "你是 bash 转换助手：以下是从 Windows 脚本自动转换到 Bash 时未能自动处理的一处代码。",
        "请给出可直接替换的 Bash 代码。",
        "",
        "要求：",
        "- 只输出替换后的 Bash 代码行（可以多行），不要输出解释、不要 Markdown 代码围栏；",
        f"- 替换范围是下方以 >>> 标记的那一整行（Bash 输出第 {effective} 行）；",
        "- 无法可靠转换时，请原样输出一行保留 TODO 的注释（# TODO: 手动检查: ...）。",
        "",
        "【待处理标记】",
        marker.marker_text,
    ]
    if marker.diagnostic_message or marker.source_line:
        parts.append("")
        parts.append("【报告信息】")
        if marker.source_line:
            parts.append(f"源文件第 {marker.source_line} 行")
        if marker.category:
            parts.append(f"分类: {marker.category}")
        if marker.diagnostic_message:
            parts.append(f"信息: {marker.diagnostic_message}")
    if marker.source_line > 0:
        source_lines = source_text.splitlines()
        index = marker.source_line - 1
        if 0 <= index < len(source_lines):
            start = max(0, index - context_lines)
            end = min(len(source_lines), index + context_lines + 1)
            parts.append("")
            parts.append(
                f"【Windows 源脚本 {source_name} 上下文（第 {start + 1}-{end} 行）】"
            )
            for i in range(start, end):
                prefix = ">>> " if i == index else "    "
                parts.append(prefix + source_lines[i])
    output_lines = output_text.splitlines()
    index = effective - 1
    if 0 <= index < len(output_lines):
        start = max(0, index - OUTPUT_CONTEXT_LINES)
        end = min(len(output_lines), index + OUTPUT_CONTEXT_LINES + 1)
        parts.append("")
        parts.append(f"【当前 Bash 上下文（第 {start + 1}-{end} 行；>>> = 待替换整行）】")
        for i in range(start, end):
            prefix = ">>> " if i == index else "    "
            text = output_lines[i] if i == index else _redact_other_todos(output_lines[i])
            parts.append(prefix + text)
    return "\n".join(parts)


_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_+-]*\s*$")


def clean_completion(raw: str) -> str:
    """清洗模型回复：规范化换行、去掉首尾空行与 Markdown 代码围栏。"""
    if not isinstance(raw, str):
        return ""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and _FENCE_RE.match(lines[0]) and len(lines) > 1 and _FENCE_RE.match(lines[-1]):
        lines = lines[1:-1]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.rstrip() for line in lines).strip("\n")


def _leading_ws(line: str) -> str:
    match = re.match(r"[ \t]*", line)
    return match.group(0) if match else ""


def _reindent(lines: list[str], indent: str) -> list[str]:
    """去掉公共缩进后，为每行套用目标行的缩进（空行保持为空行）。"""
    non_empty = [line for line in lines if line.strip()]
    common = ""
    if non_empty:
        widths = [len(line) - len(line.lstrip()) for line in non_empty]
        common = non_empty[0][: min(widths)]
    result: list[str] = []
    for line in lines:
        if not line.strip():
            result.append("")
            continue
        body = line[len(common) :] if common and line.startswith(common) else line
        result.append(indent + body)
    return result


def apply_replacement(output_text: str, out_line: int, replacement: str) -> str:
    """用 ``replacement``（可多行）替换 ``out_line`` 整行，保持缩进与末尾换行。"""
    trailing = output_text.endswith("\n")
    lines = output_text.splitlines()
    index = out_line - 1
    if index < 0 or index >= len(lines):
        raise ValueError(f"行号超出范围: {out_line}（共 {len(lines)} 行）")
    new_block = _reindent(clean_completion(replacement).splitlines(), _leading_ws(lines[index]))
    result = lines[:index] + new_block + lines[index + 1 :]
    return "\n".join(result) + ("\n" if trailing else "")


def replacement_line_count(replacement: str) -> int:
    return len(clean_completion(replacement).splitlines())


def count_markers(output_text: str, report: ConvertReport | None = None) -> int:
    return len(scan_todo_markers(output_text, report))


def render_diff(
    old_text: str, new_text: str, from_name: str = "当前", to_name: str = "建议"
) -> str:
    """生成聚焦的 unified diff（上下文 2 行）；无差异返回空串。"""
    diff = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=from_name,
            tofile=to_name,
            lineterm="",
            n=2,
        )
    )
    return "\n".join(diff)
