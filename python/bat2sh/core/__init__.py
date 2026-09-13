"""核心转换引擎（不依赖任何 GUI 库，可独立用于 CLI 或库调用）。"""

from .types import ConvertReport, Diagnostic, SourceKind
from .settings import ConvertSettings, load_settings, save_settings
from .engine import ConversionResult, convert_file, convert_text, detect_kind

__all__ = [
    "ConvertReport",
    "Diagnostic",
    "SourceKind",
    "ConvertSettings",
    "load_settings",
    "save_settings",
    "ConversionResult",
    "convert_file",
    "convert_text",
    "detect_kind",
]
