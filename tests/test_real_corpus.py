"""真实语料（CC0）交叉验证：转换管线不崩溃，产物必须是语法合法的 bash。

语料来源与选样规则见 ``tests/fixtures/real-corpus/README.md``。
本测试只做发布门槛中的"崩溃类缺陷 = 0"与"never emit broken bash"两项硬断言；
不做转换质量断言（PowerShell 侧为实验性支持，降级为已知行为）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bat2sh.core.encoding import decode_bytes
from bat2sh.core.engine import convert_text
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import SourceKind

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"
CORPUS_FILES = sorted(CORPUS_DIR.glob("*.ps1"))
DEGRADE_MARKER = "已降级为注释"


def test_corpus_meets_release_gate_size():
    assert len(CORPUS_FILES) >= 50


@pytest.mark.parametrize("path", CORPUS_FILES, ids=lambda p: p.name)
def test_real_corpus_conversion_never_emits_broken_bash(path, bash_check):
    decoded = decode_bytes(path.read_bytes(), None)
    text, report = convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(), path.name
    )
    if any(d.category == "syntax" for d in report.errors):
        assert DEGRADE_MARKER in text.splitlines()[2]
    bash_check(text)
