"""v2.5.0 Stage 2：CFG 标签分派状态机（`core/cfg_state.py`）语义测试。

纪律 14：断言 **cmd 语义**（由 bash 实跑输出验证），不编码转换器现况。
门控默认关闭，故本测试直接调用 ``cfg_state.emit``，不依赖默认转换路径。
"""

from __future__ import annotations

from bat2sh.cli import build_parser, settings_from_args
from bat2sh.core.cfg_state import emit, evaluate
from bat2sh.core.settings import ConvertSettings, resolve_cfg_state_machine, save_settings


def _emit(text: str) -> str | None:
    return emit(text, ConvertSettings(), "fixture.bat")


# --- 门控 -----------------------------------------------------------------


def test_evaluate_eligible_simple_loop():
    decision = evaluate("@echo off\n:Top\necho a\ngoto Top\n")
    assert decision.ok is True
    assert decision.reasons == ()
    assert decision.label_edges == 1


def test_evaluate_rejects_no_label_edges():
    decision = evaluate("@echo off\necho a\n")
    assert decision.ok is False
    assert "no_label_edges" in decision.reasons


def test_evaluate_rejects_label_in_block():
    decision = evaluate("@echo off\nif x (\n:Inner\necho a\n)\n")
    assert decision.ok is False
    assert "label_in_block" in decision.reasons


def test_evaluate_rejects_missing_and_dynamic():
    decision = evaluate("@echo off\ngoto Nowhere\ngoto %VAR%\n")
    assert decision.ok is False
    assert "missing_label" in decision.reasons
    assert "dynamic_target" in decision.reasons


def test_evaluate_rejects_duplicate_labels():
    decision = evaluate("@echo off\n:Dup\necho a\ngoto Dup\n:Dup\necho b\n")
    assert decision.ok is False
    assert "duplicate_labels" in decision.reasons


def test_evaluate_rejects_call_targets():
    decision = evaluate("@echo off\ncall :Sub\ngoto Top\n:Top\n:Sub\necho s\n")
    assert decision.ok is False
    assert "call_targets" in decision.reasons


def test_emit_returns_none_when_ineligible():
    assert _emit("@echo off\necho a\n") is None
    assert _emit("@echo off\nif x (\n:Inner\necho a\n)\n") is None


# --- 发射结构 -------------------------------------------------------------


def test_emit_has_dispatch_scaffold():
    out = _emit("@echo off\n:Top\necho a\ngoto Top\n")
    assert out is not None
    assert "__bat2sh_pc=__bat2sh_start" in out
    assert "while :; do" in out
    assert "case ${__bat2sh_pc} in" in out
    assert "__L_1)  # :Top" in out
    assert "__bat2sh_exit) exit 0 ;;" in out
    assert "esac" in out


def test_emit_no_goto_todo():
    from bat2sh.core.cfg_state import _DispatchConverter

    converter = _DispatchConverter(ConvertSettings(), "x.bat")
    converter.convert("@echo off\n:Top\necho a\ngoto Top\n")
    assert converter.report.todo_count == 0


# --- 门控接线（默认关闭 / opt-in） ----------------------------------------


def test_gate_default_on_uses_state_machine(convert_bat):
    out, report = convert_bat("@echo off\n:Top\necho loop\ngoto Top\n")
    assert "__bat2sh_pc" in out
    assert report.todo_count == 0


def test_gate_off_keeps_honest_todo(convert_bat):
    out, report = convert_bat("@echo off\n:Top\necho loop\ngoto Top\n", cfg_state_machine=False)
    assert "# TODO: 手动检查: goto Top" in out
    assert "__bat2sh_pc" not in out


def test_gate_on_emits_state_machine(convert_bat):
    out, report = convert_bat("@echo off\n:Top\necho loop\ngoto Top\n", cfg_state_machine=True)
    assert "__bat2sh_pc=__bat2sh_start" in out
    assert "while :; do" in out
    assert report.todo_count == 0


def test_gate_on_ineligible_falls_back_to_todo(convert_bat):
    out, report = convert_bat("@echo off\ngoto :NOWHERE\necho x\n", cfg_state_machine=True)
    assert "# TODO: 手动检查: goto :NOWHERE" in out
    assert "__bat2sh_pc" not in out


def test_gate_on_goto_eof_unchanged(convert_bat):
    out, report = convert_bat("@echo off\ngoto :eof\n", cfg_state_machine=True)
    assert "exit 0" in out
    assert report.todo_count == 0


# --- 回滚通道（CLI > 环境变量 > 配置文件） --------------------------------


def test_rollback_cli_wins_over_env(monkeypatch):
    monkeypatch.setenv("BAT2SH_CFG_STATE", "1")
    assert resolve_cfg_state_machine(False) is False
    assert resolve_cfg_state_machine(True) is True


def test_rollback_env_off(monkeypatch):
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("BAT2SH_CFG_STATE", value)
        assert resolve_cfg_state_machine() is False
    monkeypatch.setenv("BAT2SH_CFG_STATE", "1")
    assert resolve_cfg_state_machine() is True


def test_rollback_file_config(monkeypatch):
    monkeypatch.delenv("BAT2SH_CFG_STATE", raising=False)
    save_settings(ConvertSettings(cfg_state_machine=False))
    assert resolve_cfg_state_machine() is False
    save_settings(ConvertSettings(cfg_state_machine=True))
    assert resolve_cfg_state_machine() is True


def test_rollback_cli_flag_wins_over_env_and_file(monkeypatch):
    monkeypatch.setenv("BAT2SH_CFG_STATE", "1")
    save_settings(ConvertSettings(cfg_state_machine=True))
    args = build_parser().parse_args(["--no-cfg-state", "x.bat"])
    assert settings_from_args(args).cfg_state_machine is False


def test_cli_flag_cfg_state_enables():
    args = build_parser().parse_args(["--cfg-state", "x.bat"])
    assert settings_from_args(args).cfg_state_machine is True


def test_cli_default_is_state_machine_enabled(monkeypatch):
    monkeypatch.delenv("BAT2SH_CFG_STATE", raising=False)
    args = build_parser().parse_args(["x.bat"])
    assert settings_from_args(args).cfg_state_machine is True


def test_cli_no_cfg_state_keeps_goto_todo(monkeypatch):
    monkeypatch.delenv("BAT2SH_CFG_STATE", raising=False)
    args = build_parser().parse_args(["--no-cfg-state", "x.bat"])
    settings = settings_from_args(args)
    out, report = emit_fixture("@echo off\n:Top\necho loop\ngoto Top\n", settings)
    assert "# TODO: 手动检查: goto Top" in out
    assert "__bat2sh_pc" not in out


def emit_fixture(text: str, settings: ConvertSettings):
    from bat2sh.core.engine import convert_text
    from bat2sh.core.types import SourceKind

    return convert_text(text, SourceKind.BATCH, settings, "fixture.bat")


# --- 交互式循环告警（非阻断） ---------------------------------------------


def test_interactive_loop_warning_non_blocking(convert_bat):
    text = (
        "@echo off\n"
        ":Top\n"
        "set /p choice=请选择: \n"
        "if \"%choice%\"==\"q\" goto Done\n"
        "goto Top\n"
        ":Done\n"
        "echo bye\n"
    )
    out, report = convert_bat(text, cfg_state_machine=True)
    assert "__bat2sh_pc" in out  # 仍转换（不阻断）
    assert any("交互式" in w.message for w in report.warnings)


def test_non_interactive_loop_no_warning(convert_bat):
    text = "@echo off\n:Top\nset n=%n%x\necho %n%\nif not \"%n%\"==\"xxx\" goto Top\n"
    _out, report = convert_bat(text, cfg_state_machine=True)
    assert not any("交互式" in w.message for w in report.warnings)


# --- 报告保真（v2.6.0 缺陷修复） ------------------------------------------


def test_state_machine_preserves_report(convert_bat):
    """状态机文件必须保留子转换器报告：total_lines/todo_count 不得恒为 0。

    v2.5.0 缺陷：子报告被丢弃 → `--fail-on-todo` 静默失效。
    """
    text = "@echo off\n:Top\nreg add HKCU\\X /v Y\nif 1==0 goto Top\n"
    out, report = convert_bat(text)
    assert "__bat2sh_pc" in out
    assert report.total_lines == 5
    assert report.todo_count >= 1


def test_state_machine_fail_on_todo_predicate(convert_bat):
    text = "@echo off\n:Top\nreg add HKCU\\X /v Y\nif 1==0 goto Top\n"
    _out, report = convert_bat(text)
    assert bool(report.todo_count or report.error_count) is True


# --- 运行时语义（cmd 语义） -----------------------------------------------


def test_backward_loop_conditional_runtime(bash_run):
    text = (
        "@echo off\nset n=0\n:Top\nset /a n+=1\necho %n%\n"
        "if %n% lss 3 goto Top\necho done\n"
    )
    out = _emit(text)
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["1", "2", "3", "done"]


def test_forward_skip_skips_dead_code(bash_run):
    out = _emit("@echo off\ngoto End\necho dead\n:End\necho live\n")
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["live"]


def test_in_block_for_goto_breaks_loop(bash_run):
    out = _emit(
        "@echo off\nfor %%i in (a b c) do (\n  echo %%i\n  goto Out\n)\n:Out\necho out\n"
    )
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    # cmd：第一轮打印 a，goto 跳出整个 for
    assert result.stdout.splitlines() == ["a", "out"]


def test_if_block_goto_skips_rest(bash_run):
    out = _emit(
        "@echo off\nif 1==1 (\n  echo yes\n  goto Done\n)\necho no\n:Done\necho done\n"
    )
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["yes", "done"]


def test_multi_entry_label(bash_run):
    out = _emit(
        "@echo off\nset x=2\nif %x%==1 goto A\nif %x%==2 goto B\n"
        ":A\necho a\ngoto :eof\n:B\necho b\n"
    )
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["b"]


def test_goto_eof_preserved(bash_run):
    out = _emit("@echo off\n:Top\necho t\nif 1==1 goto :eof\ngoto Top\n")
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["t"]


def test_nested_loop_continue_count(bash_run):
    # 两层 for 内的 goto 需 continue 3
    text = (
        "@echo off\nfor %%i in (a b) do (\n  for %%j in (x y) do (\n"
        "    echo %%i %%j\n    goto Out\n  )\n)\n:Out\necho out\n"
    )
    out = _emit(text)
    assert out is not None
    assert "continue 3" in out
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["a x", "out"]


def test_multi_arm_ordering(bash_run):
    text = (
        "@echo off\nset n=0\n:First\nset /a n+=1\necho f%n%\n"
        "if %n% lss 2 goto First\ngoto Second\n:Second\necho second\n"
    )
    out = _emit(text)
    assert out is not None
    result = bash_run(out)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["f1", "f2", "second"]
