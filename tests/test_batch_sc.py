"""``sc`` 结构化诚实 TODO（``# TODO[SC]``，v2.2.0）回归测试。

断言语义（纪律 14）：
- 只**解析**动作/服务名/参数，**不映射** Windows 服务名 → systemd unit（纪律 7）；
- 解析失败**回退**通用诚实 TODO（不崩、不丢行）；
- 与 ``--fix-todos`` 扫描器（``core/api/fixer.py``）兼容。

**不依赖外部语料**（CI 可跑）。
"""

from __future__ import annotations

from bat2sh.core.api import fixer


def test_sc_config_is_structured_with_service_and_params(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc config Spooler start= auto\n")
    assert '# TODO[SC] op=config service="Spooler" params="start=auto"' in out


def test_sc_stop_has_no_params(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc stop Spooler\n")
    assert '# TODO[SC] op=stop service="Spooler": 手动检查: sc stop Spooler' in out


def test_sc_query_without_service(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc query\n")
    assert '# TODO[SC] op=query: 手动检查: sc query' in out


def test_sc_query_state_is_a_param_not_a_service(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc query state= all\n")
    assert '# TODO[SC] op=query params="state=all"' in out
    assert "service=" not in out


def test_sc_delete_names_the_service(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc delete MySvc\n")
    assert '# TODO[SC] op=delete service="MySvc"' in out


def test_sc_remote_host_is_captured(convert_bat) -> None:
    out, _ = convert_bat("@echo off\nsc \\\\srv query Spooler\n")
    assert 'host="\\\\srv"' in out
    assert 'op=query' in out
    assert 'service="Spooler"' in out


def test_sc_never_invents_systemd_unit(convert_bat) -> None:
    out, report = convert_bat("@echo off\nsc config AeLookupSvc start= disabled\n")
    assert "systemctl" not in out
    assert "systemctl enable" not in out
    assert "systemctl disable" not in out
    assert any(d.category == "service" for d in report.todos)


def test_sc_parse_failure_falls_back_to_plain_todo(convert_bat) -> None:
    for line in ("sc /?", "sc", "sc /help"):
        out, report = convert_bat(f"@echo off\n{line}\n")
        assert "# TODO[SC]" not in out, line
        assert "# TODO: 手动检查: " in out, line
        assert report.todo_count >= 1, line


def test_sc_registers_one_todo_per_line(convert_bat) -> None:
    out, report = convert_bat("@echo off\nsc config A start= auto\nsc stop B\n")
    assert report.todo_count == 2
    assert out.count("# TODO[SC]") == 2


def test_sc_todo_is_scannable_by_fixer(convert_bat) -> None:
    out, report = convert_bat("@echo off\nsc config Spooler start= auto\n")
    markers = [m for m in fixer.scan_todo_markers(out, report) if "SC]" in m.line_text]
    assert len(markers) == 1
    assert markers[0].original == "sc config Spooler start= auto"
    assert markers[0].category == "service"


def test_sc_emits_no_silent_drop_warning(convert_bat) -> None:
    _, report = convert_bat("@echo off\nsc config X start= auto\nsc query\n")
    assert [w for w in report.warnings if w.category == "loss"] == []


def test_sc_output_passes_bash_syntax(convert_bat, bash_check) -> None:
    out, _ = convert_bat(
        "@echo off\n"
        "sc config Spooler start= auto\n"
        "sc query state= all\n"
        'sc description X "hello world"\n'
        "sc /?\n"
    )
    bash_check(out)
