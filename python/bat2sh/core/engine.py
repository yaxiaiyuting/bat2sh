"""转换引擎入口：文件识别、转换、写出、备份、权限。"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .batch import BatchConverter
from .encoding import normalize_newlines, read_source, write_utf8_lf
from .powershell import PowerShellConverter
from .settings import ConvertSettings
from .types import ConvertReport, Diagnostic, SourceKind


def detect_kind(path: str | Path) -> SourceKind:
    return SourceKind.from_suffix(Path(path).suffix)


def convert_text(
    text: str, kind: SourceKind, settings: ConvertSettings, source_name: str = "input"
) -> tuple[str, ConvertReport]:
    """转换文本，返回 (bash 脚本内容, 报告)。"""
    if kind is SourceKind.BATCH:
        converter = BatchConverter(settings, source_name)
    elif kind is SourceKind.POWERSHELL:
        converter = PowerShellConverter(settings, source_name)
    else:
        raise ValueError(f"不支持的源文件类型: {source_name}")
    result = converter.convert(normalize_newlines(text))
    return result, converter.report


@dataclass
class ConversionResult:
    source_path: str
    output_path: str
    kind: SourceKind
    encoding: str
    text: str = ""
    report: ConvertReport = field(default_factory=ConvertReport)
    written: bool = False
    backup_path: str | None = None
    source_backup_path: str | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def output_path_for(source_path: str | Path, settings: ConvertSettings) -> Path:
    src = Path(source_path)
    suffix = settings.suffix or ".sh"
    if not suffix.startswith("."):
        suffix = "." + suffix
    directory = Path(settings.output_dir).expanduser() if settings.output_dir else src.parent
    return directory / (src.stem + suffix)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_output(result: ConversionResult, settings: ConvertSettings) -> ConversionResult:
    """写出转换结果：备份（可选）-> 写 UTF-8/LF -> chmod +x（可选）。"""
    out_path = Path(result.output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if settings.backup_source:
            src = Path(result.source_path)
            if src.is_file():
                source_backup = src.with_name(src.name + f".bak-{_timestamp()}")
                shutil.copy2(src, source_backup)
                result.source_backup_path = str(source_backup)
        if out_path.exists():
            if settings.backup_existing:
                backup = out_path.with_name(out_path.name + f".bak-{_timestamp()}")
                shutil.copy2(out_path, backup)
                result.backup_path = str(backup)
            elif not settings.overwrite:
                result.error = f"输出文件已存在且未允许覆盖: {out_path}"
                return result
        write_utf8_lf(out_path, result.text)
        if settings.make_executable:
            mode = out_path.stat().st_mode
            os.chmod(
                out_path,
                mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            )
        result.written = True
    except OSError as exc:
        result.error = f"写入失败: {exc}"
    return result


def convert_file(
    source_path: str | Path,
    settings: ConvertSettings,
    encoding_override: str | None = None,
    write: bool = True,
    output_override: str | Path | None = None,
) -> ConversionResult:
    """转换单个文件。失败时通过 ``result.error`` 返回错误信息。"""
    src = Path(source_path)
    kind = detect_kind(src)
    result = ConversionResult(
        source_path=str(src),
        output_path=str(
            Path(output_override).expanduser() if output_override else output_path_for(src, settings)
        ),
        kind=kind,
        encoding=encoding_override or "",
    )
    if kind is SourceKind.UNKNOWN:
        result.error = f"不支持的源文件类型: {src.name}（仅支持 .bat/.cmd/.ps1）"
        return result
    try:
        decoded = read_source(src, encoding_override)
    except OSError as exc:
        result.error = f"读取失败: {exc}"
        return result
    result.encoding = decoded.encoding
    try:
        text, report = convert_text(decoded.text, kind, settings, src.name)
    except Exception as exc:  # 转换器内部错误不应让 GUI 崩溃
        result.error = f"转换失败: {exc}"
        return result
    report.encoding = decoded.encoding
    if decoded.replaced:
        report.warnings.append(
            Diagnostic(0, f"输入编码 {decoded.encoding} 无法解码全部字节，已用替换字符代替")
        )
    result.text = text
    result.report = report
    if write:
        write_output(result, settings)
    return result
