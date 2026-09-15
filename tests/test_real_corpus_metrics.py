"""v1.8.0 口径回归：同时测出「原始转换口径」与「默认降级口径」两个数字并记录。

口径定义见 docs/v1.8.0-design.md §1.2：
- 原始口径 = ConvertSettings(bash_check=False) 产物通过 `bash -n` 的比例（v1.8.0 发布口径）
- 降级口径 = 默认设置产物（失败时整体降级为注释）通过 `bash -n` 的比例（历史对照）

发布三档规则：如实测出；≥93% 可发；<93% 暂停。禁止为凑数字做激进映射。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from bat2sh.core.encoding import decode_bytes
from bat2sh.core.engine import convert_text
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import SourceKind

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "real-corpus" / "fleschutz"
CORPUS_FILES = sorted(CORPUS_DIR.glob("*.ps1"))
DEGRADE_MARKER = "已降级为注释"
BASELINE_V170_RAW_PERCENT = 75.0


def _convert(path: Path, **options):
    decoded = decode_bytes(path.read_bytes(), None)
    return convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(**options), path.name
    )


def _syntax_ok(text: str) -> bool:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash")
    return subprocess.run([bash, "-n"], input=text, capture_output=True, text=True).returncode == 0


def test_corpus_size_meets_release_gate():
    assert len(CORPUS_FILES) >= 50


def test_dual_caliber_recorded(capsys):
    total = len(CORPUS_FILES)
    raw_pass = 0
    degraded_pass = 0
    for path in CORPUS_FILES:
        raw_text, _ = _convert(path, bash_check=False)
        raw_ok = _syntax_ok(raw_text)
        if raw_ok:
            raw_pass += 1
        default_text, default_report = _convert(path)
        if _syntax_ok(default_text):
            degraded_pass += 1
        if not raw_ok:
            assert DEGRADE_MARKER in default_text, f"{path.name}: 原始失败但未降级"
            assert any(d.category == "syntax" for d in default_report.errors), path.name

    raw_pct = raw_pass / total * 100
    degraded_pct = degraded_pass / total * 100
    with capsys.disabled():
        print(
            f"\n[v1.8.0 口径] 原始口径 {raw_pass}/{total} = {raw_pct:.1f}% "
            f"（v1.7.0 基线 {BASELINE_V170_RAW_PERCENT:.1f}%）｜"
            f"降级口径 {degraded_pass}/{total} = {degraded_pct:.1f}%"
        )

    assert degraded_pass == total
    assert raw_pct > BASELINE_V170_RAW_PERCENT, "原始口径必须相对 v1.7.0 有提升"
    assert raw_pct >= 93.0, f"原始口径 {raw_pct:.1f}% < 93%，按三档规则应暂停"


def test_no_conversion_crash():
    for path in CORPUS_FILES:
        _, report = _convert(path)
        assert all(d.category == "syntax" for d in report.errors), (
            f"{path.name}: 出现非语法类错误（疑似崩溃）: "
            f"{[d.message for d in report.errors]}"
        )
