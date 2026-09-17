"""Windows→Linux 结构化映射表（命令 v1.8.1 起；名称/输出契约 B1/B2 v1.10.0a1 起）。"""

from __future__ import annotations

from .output_contracts import (
    CONTRACT_SHAPES,
    OUTPUT_CONTRACTS,
    OutputContract,
    contract_for,
    validate_contracts,
)
from .windows_names import (
    NAME_KINDS,
    WINDOWS_NAMES,
    NameMapping,
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
    "CONTRACT_SHAPES",
    "FORMS",
    "NAME_KINDS",
    "OUTPUT_CONTRACTS",
    "TARGET_EXISTS",
    "NameMapping",
    "OutputContract",
    "ToolMapping",
    "WINDOWS_NAMES",
    "WINDOWS_TOOLS",
    "contract_for",
    "env_mapping_for",
    "mapping_for",
    "name_mapping_for",
    "path_root_mapping_for",
    "unmappable_env_names_in",
    "validate_contracts",
    "validate_mappings",
    "validate_name_mappings",
]
