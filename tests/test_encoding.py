"""编码检测与读写的回归测试。"""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from bat2sh.core.encoding import (
    decode_bytes,
    detect_encoding,
    normalize_newlines,
    read_source,
    write_utf8_lf,
)


def test_plain_utf8():
    assert detect_encoding("你好 world".encode("utf-8")) == ("utf-8", False)


def test_utf8_bom():
    raw = codecs.BOM_UTF8 + "你好".encode("utf-8")
    assert detect_encoding(raw) == ("utf-8-sig", True)
    decoded = decode_bytes(raw)
    assert decoded.text == "你好"
    assert decoded.had_bom is True
    assert decoded.replaced is False


def test_utf16_bom():
    raw = codecs.BOM_UTF16_LE + "hello".encode("utf-16-le")
    assert detect_encoding(raw) == ("utf-16", True)
    assert decode_bytes(raw).text == "hello"


def test_utf32_bom():
    raw = codecs.BOM_UTF32_LE + "hi".encode("utf-32-le")
    assert detect_encoding(raw) == ("utf-32", True)
    assert decode_bytes(raw).text == "hi"


def test_gbk_detected_before_gb18030():
    # GBK 是 GB18030 的子集，检测顺序为 gbk 优先
    raw = "中文测试".encode("gbk")
    assert detect_encoding(raw) == ("gbk", False)
    assert decode_bytes(raw).text == "中文测试"


def test_gb18030_only_char():
    char = "\U00020bb7"  # 𠮷，GBK 无法编码，必须用 GB18030
    with pytest.raises(UnicodeEncodeError):
        char.encode("gbk")
    raw = char.encode("gb18030")
    assert detect_encoding(raw) == ("gb18030", False)
    assert decode_bytes(raw).text == char


def test_latin1_fallback():
    raw = b"\xff\xff\xff"
    assert detect_encoding(raw) == ("latin-1", False)
    decoded = decode_bytes(raw)
    assert decoded.text == "ÿÿÿ"
    assert decoded.replaced is False


def test_override_encoding():
    raw = "中文".encode("gbk")
    decoded = decode_bytes(raw, "gbk")
    assert decoded.text == "中文"
    assert decoded.encoding == "gbk"


def test_invalid_bytes_replaced():
    decoded = decode_bytes(b"caf\xe9", "utf-8")
    assert decoded.replaced is True
    assert "\ufffd" in decoded.text


def test_unknown_override_raises_lookup_error():
    # 锁定当前行为：未知编码名会在兜底解码时抛出 LookupError；
    # CLI/GUI 的编码下拉框只会传入 SUPPORTED_ENCODINGS，暂不受影响。
    with pytest.raises(LookupError):
        decode_bytes(b"abc", "not-a-codec")


def test_normalize_newlines():
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_write_utf8_lf(tmp_path: Path):
    target = tmp_path / "out.sh"
    write_utf8_lf(target, "你好\r\necho hi\r\n")
    data = target.read_bytes()
    assert data == "你好\necho hi\n".encode("utf-8")
    assert not data.startswith(codecs.BOM_UTF8)


def test_read_source_keeps_raw_newlines(tmp_path: Path):
    # 编码层只负责解码，行尾归一化由 engine.convert_text 完成
    target = tmp_path / "a.bat"
    target.write_bytes("echo 中文\r\n".encode("gbk"))
    decoded = read_source(target)
    assert decoded.encoding == "gbk"
    assert decoded.text == "echo 中文\r\n"
