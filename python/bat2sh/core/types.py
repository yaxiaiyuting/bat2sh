"""转换过程中使用的数据类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
        if self.warnings:
            lines.append("")
            lines.append("── 警告 ─────────────────────────────────")
            lines.extend("  " + d.format() for d in self.warnings)
        if self.todos:
            lines.append("")
            lines.append("── 需要人工检查 ─────────────────────────")
            lines.extend("  " + d.format() for d in self.todos)
        return "\n".join(lines)
