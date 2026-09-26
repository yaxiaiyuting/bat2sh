"""编码检测与读写（不依赖 chardet，纯标准库实现）。

检测顺序：UTF-8 BOM -> UTF-16/32 BOM -> UTF-8 -> GBK -> GB18030 -> Latin-1 兜底。
输出统一为 UTF-8 无 BOM、LF 行尾。
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path

# 界面下拉框中可供手动覆盖的编码
SUPPORTED_ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "gbk",
    "gb18030",
    "gb2312",
    "latin-1",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "big5",
    "shift_jis",
    "cp1252",
)

_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


@dataclass
class DecodedFile:
    text: str
    encoding: str
    had_bom: bool = False
    replaced: bool = False
    error: str = ""


def detect_encoding(raw: bytes) -> tuple[str, bool]:
    """返回 (编码名, 是否带 BOM)。"""
    for bom, name in _BOMS:
        if raw.startswith(bom):
            return name, True
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            raw.decode(enc)
            return enc, False
        except UnicodeDecodeError:
            continue
    return "latin-1", False


def decode_bytes(raw: bytes, override: str | None = None) -> DecodedFile:
    """按 override 或自动检测解码字节流。"""
    if override:
        enc = override
        had_bom = any(raw.startswith(bom) for bom, _ in _BOMS)
    else:
        enc, had_bom = detect_encoding(raw)
    try:
        text = raw.decode(enc)
        replaced = False
    except (UnicodeDecodeError, LookupError):
        text = raw.decode(enc, errors="replace")
        replaced = True
    if text.startswith("\ufeff"):
        text = text[1:]
    return DecodedFile(text=text, encoding=enc, had_bom=had_bom, replaced=replaced)


def read_source(path: str | Path, override: str | None = None) -> DecodedFile:
    raw = Path(path).read_bytes()
    return decode_bytes(raw, override)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


#: 行尾类型（``detect_line_endings`` 的返回值）
LINE_ENDING_CRLF = "crlf"
LINE_ENDING_LF = "lf"
LINE_ENDING_MIXED = "mixed"
LINE_ENDING_NONE = "none"


def detect_line_endings(text: str) -> str:
    """返回 ``'crlf' | 'lf' | 'mixed' | 'none'``。

    只统计**行尾**，不看编码：``\\r\\n`` 记 CRLF；把 ``\\r\\n`` 去掉后剩下的单独
    ``\\n`` 或单独 ``\\r`` 记作"非 CRLF 行尾"。单独 ``\\r``（老 Mac 风格）极罕见，
    与 LF 合并计入 ``lf`` —— 对 cmd.exe 而言二者同样不是它期望的 CRLF。

    为什么需要它：实测（``research/behavior-tracking/batch-result.md`` §4.1）
    **只有 LF 换行的 .bat/.cmd 会让 cmd.exe 解析错乱** —— 命令行首被逐行吃掉
    （累积偏移），报"不是内部或外部命令"，退出码 255。只把 LF 换成 CRLF（内容不动）
    重跑，同一个样本从 ``rc=255`` 变成 ``rc=0``。
    """
    crlf = text.count("\r\n")
    remainder = text.replace("\r\n", "")
    other = remainder.count("\n") + remainder.count("\r")
    if crlf and other:
        return LINE_ENDING_MIXED
    if crlf:
        return LINE_ENDING_CRLF
    if other:
        return LINE_ENDING_LF
    return LINE_ENDING_NONE


def write_utf8_lf(path: str | Path, text: str) -> None:
    """按 UTF-8 无 BOM、LF 行尾写出文件。"""
    data = normalize_newlines(text).encode("utf-8")
    Path(path).write_bytes(data)
