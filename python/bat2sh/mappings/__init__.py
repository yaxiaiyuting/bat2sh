"""Windows→Linux 命令结构化映射表（v1.8.1 起）。"""

from __future__ import annotations

from .windows_tools import (
    CONFIDENCES,
    FORMS,
    TARGET_EXISTS,
    ToolMapping,
    WINDOWS_TOOLS,
    mapping_for,
    validate_mappings,
)

__all__ = [
    "CONFIDENCES",
    "FORMS",
    "TARGET_EXISTS",
    "ToolMapping",
    "WINDOWS_TOOLS",
    "mapping_for",
    "validate_mappings",
]
