"""v2.5.0 Stage 1：CFG 基本块 + 流分析（`core/cfg_blocks.py`）语义测试。

纪律：断言 CFG 语义（块划分/边/回边循环/多入口/入口障碍），不编码转换器现况。
本模块为**只读**前置（不接转换器），故测试不依赖任何外部语料。
"""

from __future__ import annotations

from bat2sh.core.cfg_blocks import analyze_flow, analyze_text, build_blocks, detect_loops
from bat2sh.core.cfg import logical_lines


def _analyze(text: str):
    return analyze_text(text)


# --- 块划分 ---------------------------------------------------------------


def test_linear_script_is_single_block():
    _cfg, flow, _lines = _analyze("@echo off\necho a\necho b\n")
    assert len(flow.blocks) == 1
    assert flow.blocks[0].label is None
    assert flow.blocks[0].successors == ()
    assert flow.blocks[0].predecessors == ()


def test_label_starts_new_block():
    _cfg, flow, _lines = _analyze("@echo off\necho before\n:Top\necho after\n")
    assert len(flow.blocks) == 2
    assert flow.blocks[0].label is None
    assert flow.blocks[1].label == "Top"
    # 落空：block0 -> block1
    assert flow.blocks[0].successors == (1,)
    assert flow.blocks[1].predecessors == (0,)


def test_goto_successor_is_target_block():
    _cfg, flow, _lines = _analyze("@echo off\ngoto End\necho dead\n:End\necho live\n")
    # block0 以 goto 结尾 -> 后继为 End 块（不回落到 dead 块）
    assert flow.blocks[0].successors == (2,)
    assert 0 not in flow.blocks[1].predecessors


def test_goto_following_line_is_block_leader():
    _cfg, flow, _lines = _analyze("@echo off\n:Top\ngoto Top\necho after\n")
    # goto 后继行是 leader
    starts = [block.start_index for block in flow.blocks]
    assert 3 in starts


# --- 回边循环 -------------------------------------------------------------


def test_backward_goto_forms_loop():
    _cfg, flow, _lines = _analyze("@echo off\n:Top\necho loop\ngoto Top\n")
    assert len(flow.loops) == 1
    loop = flow.loops[0]
    assert loop.label == "top"
    assert loop.backward_edges == 1
    # header 是 :Top 所在块；tail 是 goto 所在块
    assert flow.blocks[loop.header_block].label == "Top"


def test_forward_goto_is_not_loop():
    _cfg, flow, _lines = _analyze("@echo off\ngoto End\necho x\n:End\necho y\n")
    assert flow.loops == ()


def test_two_backward_gotos_group_by_header():
    _cfg, flow, _lines = _analyze(
        "@echo off\n:Top\nif a goto Top\nif b goto Top\n"
    )
    assert len(flow.loops) == 1
    assert flow.loops[0].backward_edges == 2
    assert len(flow.loops[0].tail_blocks) >= 1


def test_nested_loops_two_headers():
    _cfg, flow, _lines = _analyze(
        "@echo off\n:Outer\necho o\n:Inner\necho i\ngoto Inner\ngoto Outer\n"
    )
    headers = {flow.blocks[loop.header_block].label for loop in flow.loops}
    assert headers == {"Outer", "Inner"}


# --- 多入口 / 重复标签 ----------------------------------------------------


def test_multi_entry_label_detected():
    _cfg, flow, _lines = _analyze(
        "@echo off\nif a goto Shared\nif b goto Shared\n:Shared\necho s\n"
    )
    assert "shared" in flow.multi_entry_labels


def test_single_entry_not_multi():
    _cfg, flow, _lines = _analyze("@echo off\n:Only\necho x\n")
    assert flow.multi_entry_labels == ()


def test_duplicate_labels_detected():
    _cfg, flow, _lines = _analyze("@echo off\n:Dup\necho a\n:Dup\necho b\n")
    assert "dup" in flow.duplicate_labels


def test_label_in_block_detected():
    _cfg, flow, _lines = _analyze("@echo off\nif x (\n:Inner\necho a\n)\n")
    assert flow.label_in_block is True


def test_top_level_labels_not_in_block():
    _cfg, flow, _lines = _analyze("@echo off\n:Top\necho a\n")
    assert flow.label_in_block is False


# --- 入口障碍 -------------------------------------------------------------


def test_missing_and_dynamic_flags():
    _cfg, flow, _lines = _analyze("@echo off\ngoto Nowhere\ngoto %VAR%\n")
    assert flow.has_missing is True
    assert flow.has_dynamic is True


def test_call_and_goto_targets_collected():
    _cfg, flow, _lines = _analyze(
        "@echo off\ncall :Helper\ngoto Target\n:Target\n:Helper\necho h\n"
    )
    assert "helper" in flow.call_targets
    assert "target" in flow.goto_targets


# --- 只读一致性 -----------------------------------------------------------


def test_block_edges_are_symmetric():
    text = "@echo off\n:Top\necho a\nif x goto End\ngoto Top\n:End\necho e\n"
    _cfg, flow, _lines = _analyze(text)
    for block in flow.blocks:
        for successor in block.successors:
            assert block.id in flow.blocks[successor].predecessors
        for predecessor in block.predecessors:
            assert block.id in flow.blocks[predecessor].successors


def test_blocks_cover_all_lines_contiguously():
    text = "@echo off\n:Top\necho a\nif x goto End\ngoto Top\n:End\necho e\n"
    _cfg, flow, lines = _analyze(text)
    covered = []
    for block in flow.blocks:
        covered.extend(range(block.start_index, block.end_index + 1))
    assert sorted(covered) == list(range(len(lines)))


def test_empty_script_has_single_empty_block():
    _cfg, flow, _lines = _analyze("")
    assert len(flow.blocks) == 1
    assert flow.blocks[0].successors == ()
    assert flow.loops == ()


def test_build_blocks_empty_lines_returns_nothing():
    cfg, _flow, lines = _analyze("")
    assert build_blocks(cfg, []) == ()


def test_detect_loops_matches_analysis():
    text = "@echo off\n:Top\necho a\ngoto Top\n"
    cfg, flow, lines = _analyze(text)
    assert detect_loops(cfg, flow.blocks) == flow.loops


def test_build_blocks_rejects_mismatched_lines():
    cfg, _flow, _lines = _analyze(":A\n:B\necho a\n")
    import pytest

    with pytest.raises(ValueError):
        build_blocks(cfg, [":A"])


def test_logical_lines_continuation_keeps_block_indices():
    text = "@echo off\n:Top\n^\necho a\ngoto Top\n"
    logical = logical_lines(text)
    _cfg, flow, _lines = analyze_text(text)
    assert len(flow.blocks) >= 1
    # 逻辑行累积后块覆盖全部逻辑行
    covered = []
    for block in flow.blocks:
        covered.extend(range(block.start_index, block.end_index + 1))
    assert sorted(covered) == list(range(len(logical)))
