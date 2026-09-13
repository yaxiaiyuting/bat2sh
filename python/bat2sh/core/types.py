"""转换过程中使用的数据类型。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

_CATEGORY_LABELS: tuple[tuple[str, str], ...] = (
    ("command", "命令映射"),
    ("control_flow", "控制流"),
    ("errorlevel", "退出码"),
    ("glob", "通配符"),
    ("path", "路径"),
    ("pipeline", "管道"),
    ("params", "参数"),
    ("objects", "对象模型"),
    ("strings", "字符串与文本"),
    ("variables", "变量"),
)
_OTHER_LABEL = "其他"
_SECTION_DASHES = 33  # 与 ConvertReport.to_text() 的分节线保持一致


class SourceKind(str, Enum):
    """源脚本类型。"""

    BATCH = "bat"
    POWERSHELL = "ps1"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            SourceKind.BATCH: "Windows 批处理",
            SourceKind.POWERSHELL: "PowerShell",
            SourceKind.UNKNOWN: "未知",
        }[SourceKind(self.value)]

    @staticmethod
    def from_suffix(suffix: str) -> "SourceKind":
        suffix = suffix.lower()
        if suffix in (".bat", ".cmd"):
            return SourceKind.BATCH
        if suffix in (".ps1", ".psm1"):
            return SourceKind.POWERSHELL
        return SourceKind.UNKNOWN


@dataclass
class Diagnostic:
    """一条警告或待人工检查项。"""

    line: int
    message: str
    original: str = ""
    category: str = ""

    def format(self) -> str:
        if self.original:
            return f"第 {self.line} 行: {self.message} ｜ 原命令: {self.original}"
        return f"第 {self.line} 行: {self.message}"


@dataclass
class ConvertReport:
    """单个文件的转换报告。"""

    source: str = ""
    kind: SourceKind = SourceKind.UNKNOWN
    encoding: str = "utf-8"
    total_lines: int = 0
    converted_lines: int = 0
    unchanged_lines: int = 0
    warnings: list[Diagnostic] = field(default_factory=list)
    todos: list[Diagnostic] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def todo_count(self) -> int:
        return len(self.todos)

    @property
    def error_count(self) -> int:
        return len(self.todos)

    @staticmethod
    def _diagnostic_dict(diagnostic: Diagnostic) -> dict:
        return {
            "line": diagnostic.line,
            "category": diagnostic.category,
            "message": diagnostic.message,
            "original": diagnostic.original,
        }

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "kind": self.kind.value,
            "kind_display": self.kind.display_name,
            "encoding": self.encoding,
            "total_lines": self.total_lines,
            "converted_lines": self.converted_lines,
            "unchanged_lines": self.unchanged_lines,
            "warning_count": self.warning_count,
            "todo_count": self.todo_count,
            "warnings": [self._diagnostic_dict(d) for d in self.warnings],
            "todos": [self._diagnostic_dict(d) for d in self.todos],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        lines = [
            f"源文件      : {self.source}",
            f"源类型      : {self.kind.display_name}",
            f"输入编码    : {self.encoding}",
            f"总行数      : {self.total_lines}",
            f"已转换行数  : {self.converted_lines}",
            f"保持不变行数: {self.unchanged_lines}",
            f"警告数量    : {self.warning_count}",
            f"无法自动转换: {self.todo_count}",
        ]
        for title, diagnostics in (("警告", self.warnings), ("需要人工检查", self.todos)):
            if not diagnostics:
                continue
            lines.append("")
            lines.append(f"── {title} ─────────────────────────────────")
            for label, group in self._group_diagnostics(diagnostics):
                lines.append(f"  [{label}]")
                lines.extend("    " + d.format() for d in group)
        return "\n".join(lines)

    @staticmethod
    def _group_diagnostics(
        diagnostics: list[Diagnostic],
    ) -> list[tuple[str, list[Diagnostic]]]:
        known = {name: label for name, label in _CATEGORY_LABELS}
        buckets: dict[str, list[Diagnostic]] = {}
        for diagnostic in diagnostics:
            key = diagnostic.category if diagnostic.category in known else ""
            buckets.setdefault(key, []).append(diagnostic)
        groups = [
            (label, buckets[name]) for name, label in _CATEGORY_LABELS if name in buckets
        ]
        if "" in buckets:
            groups.append((_OTHER_LABEL, buckets[""]))
        return groups


def report_blocks(report: ConvertReport) -> list[tuple[str, str]]:
    """把报告拆成 (text, level) 行块，level ∈ {"info", "warning", "todo", "normal"}。

    独立生成 to_text() 的行结构（由测试守护两者一致），供 GUI 按级别着色。
    """
    blocks: list[tuple[str, str]] = [
        (f"源文件      : {report.source}", "info"),
        (f"源类型      : {report.kind.display_name}", "info"),
        (f"输入编码    : {report.encoding}", "info"),
        (f"总行数      : {report.total_lines}", "info"),
        (f"已转换行数  : {report.converted_lines}", "info"),
        (f"保持不变行数: {report.unchanged_lines}", "info"),
        (f"警告数量    : {report.warning_count}", "info"),
        (f"无法自动转换: {report.todo_count}", "info"),
    ]
    for title, diagnostics, level in (
        ("警告", report.warnings, "warning"),
        ("需要人工检查", report.todos, "todo"),
    ):
        if not diagnostics:
            continue
        blocks.append(("", "normal"))
        blocks.append((f"── {title} {'─' * _SECTION_DASHES}", level))
        for label, group in report._group_diagnostics(diagnostics):
            blocks.append((f"  [{label}]", level))
            blocks.extend(("    " + diagnostic.format(), level) for diagnostic in group)
    return blocks
