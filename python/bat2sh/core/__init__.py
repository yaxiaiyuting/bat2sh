"""核心转换引擎（不依赖任何 GUI 库，可独立用于 CLI 或库调用）。"""

from .types import ConvertReport, Diagnostic, SourceKind
from .settings import ConvertSettings, load_settings, save_settings
from .encoding import detect_line_endings
from .engine import (
    ConversionResult,
    annotate_line_endings,
    convert_decoded,
    convert_file,
    convert_text,
    detect_kind,
    line_ending_diagnostic,
)

__all__ = [
    "ConvertReport",
    "Diagnostic",
    "SourceKind",
    "ConvertSettings",
    "load_settings",
    "save_settings",
    "ConversionResult",
    "convert_decoded",
    "convert_file",
    "convert_text",
    "detect_kind",
    "detect_line_endings",
    "annotate_line_endings",
    "line_ending_diagnostic",
]
