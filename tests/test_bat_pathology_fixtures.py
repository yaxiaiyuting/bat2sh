"""bat 真实语料病理 fixture 的回归测试（缺陷 D-3 修复）。

背景（2026-09-20 评估发现）：
仓库 tests/fixtures/ 中**没有任何真实 .bat/.cmd 文件**；PS 侧也只入了 665 个 CC0 语料里
文件名排序最靠前的 60 个（约为最短的一档：中位 33 行、max 177 行）。
而 ~/下载 下真实存在 246 个 bat/cmd，含 GBK 编码、末行无换行、单行 280 字符、
CJK 变量名、延迟展开、reg/wmic 依赖等"病理"。最脏的 151 个中文 bat 此前只在
tools/corpus-analysis/measure.py 里当健壮性基线，**不作为断言测试** ——
即主力功能（bat 转换）长期缺少真实形态的回归覆盖。

许可说明：本目录 fixture 为**本项目原创编写**，只复刻外部语料中观测到的**结构特征**
（编码 / 换行 / 行长 / 变量命名 / 依赖类别），**不复用任何第三方语料内容**。
外部语料（非常批处理、bat-master、windows-batch-script-master）均无 LICENSE，
不宜直接入仓；PS 侧的 fleschutz 语料是 CC0，故此前可以入仓。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bat2sh.core.encoding import decode_bytes
from bat2sh.core.engine import convert_text
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.syntax import bash_syntax_error
from bat2sh.core.types import SourceKind

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bat-pathologies"
FIXTURES = sorted(p.name for p in FIXTURE_DIR.glob("*.bat"))


def count_markers(text: str) -> int:
    """产物中真实 # TODO 标记数（排除脚本头的口径说明行，与 measure.py 同口径）。"""
    n = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# 带有 # TODO 标记") or stripped.startswith("# 该脚本包含"):
            continue
        if "# TODO" in line:
            n += 1
    return n


def convert_fixture(name: str):
    """返回 (decoded, out, report)。"""
    raw = (FIXTURE_DIR / name).read_bytes()
    decoded = decode_bytes(raw, None)
    out, report = convert_text(
        decoded.text, SourceKind.BATCH, ConvertSettings(bash_check=False), name
    )
    return decoded, out, report


def test_fixture_dir_is_not_empty():
    assert FIXTURES, "bat 病理 fixture 目录为空，D-3 覆盖缺口已回归"
    assert len(FIXTURES) >= 9


@pytest.mark.parametrize("name", FIXTURES)
def test_pathology_fixture_converts_without_error(name):
    """全部病理 fixture 必须：不抛异常、无 error、产物 bash -n 通过。"""
    _, out, report = convert_fixture(name)
    assert out.strip(), f"{name}: 产物为空"
    assert report.error_count == 0, f"{name}: 出现转换错误 {[e.message for e in report.errors]}"
    assert bash_syntax_error(out) is None, f"{name}: 产物未通过 bash -n"
    assert report.total_lines > 0, f"{name}: total_lines 未统计"


@pytest.mark.parametrize("name", FIXTURES)
def test_todo_markers_are_always_counted(name):
    """报告诚实性不变量：产物含 # TODO 标记则 todo_count 必须 > 0。

    这是 v2.6.0 A-1（cfg_state.emit 丢弃子报告）与 v2.8.1（PS try/catch 标记未计数）
    两次缺陷的**同类回归守卫**：只要产物里出现了 TODO，--fail-on-todo 就必须能拦住。
    """
    _, out, report = convert_fixture(name)
    markers = count_markers(out)
    if markers > 0:
        assert report.todo_count > 0, (
            f"{name}: 产物含 {markers} 个 # TODO 标记，但 report.todo_count == 0"
            "（--fail-on-todo 会静默失效）"
        )
    assert report.todo_count == len(report.todos)


def test_gbk_fixture_is_detected_and_content_preserved():
    raw = (FIXTURE_DIR / "gbk-encoded.bat").read_bytes()
    decoded = decode_bytes(raw, None)
    assert decoded.encoding == "gbk", f"GBK 未被识别（得到 {decoded.encoding}）"
    assert decoded.error == ""
    assert "测试目录" in decoded.text
    _, out, _ = convert_fixture("gbk-encoded.bat")
    assert "测试目录" in out


def test_utf8_bom_fixture_is_detected():
    raw = (FIXTURE_DIR / "utf8-bom.bat").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "fixture 本身丢了 BOM"
    decoded = decode_bytes(raw, None)
    assert decoded.had_bom is True
    assert decoded.encoding == "utf-8-sig"
    assert "bom-demo" in decoded.text


def test_missing_trailing_newline_keeps_last_command():
    raw = (FIXTURE_DIR / "no-trailing-newline.bat").read_bytes()
    assert not raw.endswith(b"\n"), "fixture 本身不再是末行无换行"
    _, out, _ = convert_fixture("no-trailing-newline.bat")
    assert "tail" in out, "末行无换行时最后一条命令被丢弃"
    assert bash_syntax_error(out) is None


def test_very_long_single_line_is_not_truncated():
    _, out, _ = convert_fixture("long-single-line.bat")
    assert "段0-" in out, "超长行头部丢失"
    assert "段59-" in out, "超长行尾部丢失（疑似截断）"
    assert max(len(line) for line in out.splitlines()) > 2000


def test_environment_dependency_fixture_is_flagged_as_todo():
    """reg add / wmic / sc query 等 Linux 无对应物的命令必须显式 TODO，而非静默丢弃。"""
    _, out, report = convert_fixture("registry-and-wmic.bat")
    assert report.todo_count >= 3
    assert count_markers(out) >= 3
    joined = " ".join(t.message for t in report.todos)
    for needle in ("reg add", "wmic", "sc query"):
        assert needle in joined, f"{needle} 未被登记为 TODO"


def test_cjk_variable_rename_is_announced():
    _, out, report = convert_fixture("cjk-variable-name.bat")
    assert "已重命名" in " ".join(w.message for w in report.warnings)
    # 中文**变量引用**必须换成合法标识符；但作为普通文本出现在 echo 里的中文应原样保留
    assert "%源目录%" not in out, "cmd 风格的变量引用未被转换"
    assert "${___}" in out, "未使用重命名后的标识符"
    assert "源目录是" in out, "echo 中的中文文本不应被改写"


def test_cjk_rename_collision_is_announced():
    """等长中文变量名会被重命名为同一标识符 —— 当前实现**只告警、不登记 TODO**。

    这里锁定"至少要有告警"这一底线（不能让冲突完全静默）。
    见评估报告 D-5：该冲突产物语义已不正确，却因 todo_count==0 被算作"功能完好"，
    建议后续把冲突从 warning 提升为 TODO，使 --fail-on-todo 能拦住。
    """
    src = (
        "@echo off\n"
        "set 源目录=C:\\aaa\n"
        "set 备份夹=D:\\bbb\n"
        "echo %源目录%\n"
        "echo %备份夹%\n"
    )
    out, report = convert_text(
        src, SourceKind.BATCH, ConvertSettings(bash_check=False), "collide.bat"
    )
    joined = " ".join(w.message for w in report.warnings)
    assert "重命名后同名" in joined, "重命名冲突未告警（完全静默）"
    assert report.error_count == 0
    assert bash_syntax_error(out) is None


def test_delayed_expansion_is_converted():
    """backlog P-2：!VAR! 延迟展开在当前实现中被正确转换为 bash 变量展开。"""
    _, out, report = convert_fixture("delayed-expansion.bat")
    assert report.error_count == 0
    assert "!计数!" not in out, "延迟展开语法未被转换，残留在产物中"
    assert bash_syntax_error(out) is None
