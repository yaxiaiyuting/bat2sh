"""Windows→Linux 结构化映射表（命令 v1.8.1 起；名称 B1/v1.10.0a1 起）。"""

from __future__ import annotations

from .windows_names import (
    NAME_KINDS,
    NameMapping,
    WINDOWS_NAMES,
    env_mapping_for,
    name_mapping_for,
    path_root_mapping_for,
    unmappable_env_names_in,
    validate_name_mappings,
)
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
    "NAME_KINDS",
    "TARGET_EXISTS",
    "NameMapping",
    "ToolMapping",
    "WINDOWS_NAMES",
    "WINDOWS_TOOLS",
    "env_mapping_for",
    "mapping_for",
    "name_mapping_for",
    "path_root_mapping_for",
    "unmappable_env_names_in",
    "validate_mappings",
    "validate_name_mappings",
]
