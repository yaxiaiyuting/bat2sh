"""B2 输出契约子系统框架单测（v1.10.0a1）。

重点：``windows_tools.output_contract=true`` 必须**有实据**（交叉强制），
以及 ipconfig 契约的中文关键词必须与既有 ``_FINDSTR_CJK_MAP`` 行为一致（防漂移）。
"""

from __future__ import annotations

import re

from bat2sh.core.batch import _FINDSTR_CJK_MAP
from bat2sh.mappings import (
    CONTRACT_SHAPES,
    OUTPUT_CONTRACTS,
    WINDOWS_TOOLS,
    OutputContract,
    contract_for,
    validate_contracts,
)


def make(**kwargs) -> OutputContract:
    base = dict(
        command="demo",
        linux_command="demo-linux",
        shape="differs",
        evidence="corpus/demo.bat:1",
        keywords=(),
        integrated=True,
        notes="输出差异说明。",
    )
    base.update(kwargs)
    return OutputContract(**base)  # type: ignore[arg-type]


def test_real_table_passes_validation():
    assert validate_contracts() == []


def test_shapes_are_documented():
    assert CONTRACT_SHAPES == ("equivalent", "differs", "none")


def test_every_contract_has_corpus_evidence():
    assert OUTPUT_CONTRACTS
    for item in OUTPUT_CONTRACTS:
        assert re.match(r"^corpus/.+:\d+$", item.evidence), item.command


def test_empty_contracts_and_no_tools_flag_passes():
    assert validate_contracts((), ()) == []


def test_missing_evidence_is_rejected():
    assert any("evidence" in e for e in validate_contracts((make(evidence=""),), ()))


def test_bad_shape_is_rejected():
    assert any("shape 非法" in e for e in validate_contracts((make(shape="sorta"),), ()))


def test_empty_command_is_rejected():
    assert any("command 为空" in e for e in validate_contracts((make(command=""),), ()))


def test_differs_requires_output_note():
    bad = validate_contracts((make(notes="随便写点什么"),), ())
    assert any("输出差异" in e for e in bad)


def test_none_requires_empty_linux_command_and_note():
    bad = validate_contracts(
        (make(shape="none", linux_command="lshw", notes="无对应物。"),), ()
    )
    assert any("shape=none" in e for e in bad)


def test_none_passes_when_wellformed():
    entry = make(shape="none", linux_command="", notes="Linux 无对应物。目标物不存在。")
    assert validate_contracts((entry,), ()) == []


def test_equivalent_requires_linux_command():
    bad = validate_contracts((make(shape="equivalent", linux_command=""),), ())
    assert any("equivalent" in e for e in bad)


def test_keywords_must_be_pairs_with_windows_side():
    bad = validate_contracts((make(keywords=(("", "x"),)),), ())
    assert any("keywords" in e for e in bad)


def test_integrated_false_requires_backlog_note():
    bad = validate_contracts((make(integrated=False),), ())
    assert any("backlog" in e for e in bad)


def test_registered_contract_with_backlog_passes():
    entry = make(integrated=False, notes="输出差异说明；本版仅登记（backlog）。")
    assert validate_contracts((entry,), ()) == []


def test_duplicate_command_is_rejected():
    bad = validate_contracts((make(), make()), ())
    assert any("重复" in e for e in bad)


def test_output_contract_flag_requires_contract_record():
    class FakeTool:
        def __init__(self, win: str) -> None:
            self.win = win
            self.output_contract = True

    bad = validate_contracts((), (FakeTool("orphan"),))
    assert any("output_contract=true" in e for e in bad)


def test_every_flagged_tool_has_a_contract():
    for tool in WINDOWS_TOOLS:
        if tool.output_contract:
            assert contract_for(tool.win) is not None, tool.win


def test_contract_lookup_is_case_insensitive_and_strips_wrappers():
    for token in ("ipconfig", "IPCONFIG", "%ipconfig%", '"ipconfig"'):
        entry = contract_for(token)
        assert entry is not None and entry.command == "ipconfig"


def test_contract_lookup_does_not_strip_exe():
    assert contract_for("dxdiag") is not None
    assert contract_for("dxdiag.exe") is None


def test_unknown_command_has_no_contract():
    assert contract_for("definitely-not-a-command") is None


def test_ipconfig_keywords_match_findstr_cjk_map():
    entry = contract_for("ipconfig")
    assert entry is not None
    mapping = dict(entry.keywords)
    for win_keyword, (linux_keyword, _diff) in _FINDSTR_CJK_MAP.items():
        assert mapping[win_keyword] == linux_keyword


def test_first_batch_commands():
    assert {item.command for item in OUTPUT_CONTRACTS} == {
        "ipconfig",
        "dxdiag",
        "perfmon",
        "ping",
        "help",
    }


def test_only_dxdiag_perfmon_are_consumed_for_degradation():
    consumed = {item.command for item in OUTPUT_CONTRACTS if item.integrated}
    assert consumed == {"ipconfig", "dxdiag", "perfmon"}
