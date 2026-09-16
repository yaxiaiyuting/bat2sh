"""CLI --fix-todos 测试：多选、合并隐私确认、并行面板、重试、写盘与退出码。

通过注入 fake provider（monkeypatch cli.create_provider）与脚本化 TTY stdin，
不访问网络；本模块带 socket 守卫（autouse）。fake provider 必须线程安全：
``parallel.run_parallel`` 会从多个工作线程调用它。
"""

from __future__ import annotations

import io
import socket
import sys
import threading

import pytest

import bat2sh.cli as cli
from bat2sh.cli import build_parser, main
from bat2sh.core.api import fixer, parallel
from bat2sh.core.api.config import ApiConfig, resolve_api_config, save_api_config
from bat2sh.core.api.provider import ProviderNetworkError, ProviderRateLimitError

M1_BAT = '@echo off\nfor /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
TWO_BAT = (
    '@echo off\n'
    'for /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
    'for /f "usebackq" %%j in (`dir /s`) do echo %%j\n'
)
M2_BAT = '@echo off\ndir /b | findstr /i "foo" | sort /r > out.txt\n'
M3_PS = 'if ($LASTEXITCODE -ne 0) { Write-Host "x" }\n[System.IO.File]::ReadAllText("a")\n'
DEGRADE_PS = "function f { [CmdletBinding()] param([string]$p) Write-Output $p }\nf\n"
API_ARGS = ["--api-base", "https://api.example.test/v1", "--api-model", "demo-model"]


class _ScriptedTty:
    def __init__(self, replies):
        self.replies = list(replies)

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        if not self.replies:
            return ""
        return self.replies.pop(0)


class _NonTty:
    def isatty(self) -> bool:
        return False


def _reply_by_marker(prompt: str) -> str:
    """按待替换行（``>>>`` 标记行）映射回复；并发下调用顺序不定，只能按内容对应。"""
    if '>>> # TODO: 手动检查: for /f "usebackq" %%j' in prompt:
        return 'echo "fixed-s"'
    if '>>> # TODO: 手动检查: for /f "usebackq" %%i' in prompt:
        return 'echo "fixed-b"'
    if ">>> # TODO: 手动检查: [System.IO.File]" in prompt:
        return 'echo "file-read"'
    if ">>> if [[ false ]]; then  # TODO: 手动检查 $LASTEXITCODE" in prompt:
        return "if true; then"
    raise AssertionError("未预置的 prompt: " + prompt[:120])


class _FakeProvider:
    """线程安全脚本化 Provider：记录 prompt，按内容或按调用序返回回复。

    ``reply_for(prompt)`` 返回 ``str``（单块）或 ``list[str]``（多块）或异常实例；
    ``responses`` 为按调用顺序消费的同类结果序列（用于「先失败后成功」）。
    """

    def __init__(self, reply_for=None, *, responses=None):
        self._reply_for = reply_for
        self._responses = list(responses) if responses is not None else None
        self._cursor = 0
        self._lock = threading.Lock()
        self.prompts: list[str] = []

    def _next(self, prompt):
        with self._lock:
            self.prompts.append(prompt)
            if self._responses is not None:
                result = self._responses[self._cursor % len(self._responses)]
                self._cursor += 1
                return result
        return self._reply_for(prompt)

    def complete(self, prompt: str, *, timeout: float) -> str:
        return "".join(self.complete_stream(prompt, timeout=timeout))

    def complete_stream(
        self, prompt, *, timeout, on_reasoning=None, on_warning=None, on_rate_limit=None
    ):
        result = self._next(prompt)
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, str):
            result = [result]
        yield from result


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for key in (
        "BAT2SH_API_PROVIDER",
        "BAT2SH_API_BASE",
        "BAT2SH_API_MODEL",
        "BAT2SH_API_KEY",
        "BAT2SH_API_TIMEOUT",
        "BAT2SH_API_CONTEXT_LINES",
        "BAT2SH_MAX_CONCURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)

    def _boom(*args, **kwargs):  # pragma: no cover - 触发即测试失败
        raise AssertionError("测试不得访问真实网络")

    monkeypatch.setattr(socket, "socket", _boom)


def _install_provider(monkeypatch, provider):
    created = []
    monkeypatch.setattr(
        cli, "create_provider", lambda config: created.append(config) or provider
    )
    return created


def _install_fast_parallel(monkeypatch, sleeps=None):
    """注入 sleep/jitter，避免真实退避等待并记录退避序列。"""
    real = parallel.run_parallel

    def wrapper(tasks, provider, **kwargs):
        kwargs["sleep"] = sleeps.append if sleeps is not None else (lambda _s: None)
        kwargs["jitter"] = lambda: 1.0
        return real(tasks, provider, **kwargs)

    monkeypatch.setattr(parallel, "run_parallel", wrapper)


def _write(tmp_path, text, name="demo.bat"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(tmp_path, monkeypatch, text, argv=(), replies=(), provider=None, name="demo.bat"):
    provider = provider or _FakeProvider(_reply_by_marker)
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(list(replies)))
    path = _write(tmp_path, text, name=name)
    code = main([str(path), "--fix-todos", *argv, *API_ARGS])
    return code, path, provider


# ---------------------------------------------------------------------------
# 多选 / 隐私合并
# ---------------------------------------------------------------------------


def test_merged_privacy_prompt_appears_exactly_once(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, TWO_BAT, replies=["\n", "y\n", "y\n"]
    )
    err = capfd.readouterr().err
    assert code == 0
    assert err.count("发送 2 条到 https://api.example.test/v1？[y/N]") == 1
    assert "发送本条" not in err
    assert "将发送的内容（原文" not in err
    assert "应用这条修改" not in err
    assert len(provider.prompts) == 2
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-b"' in out and 'echo "fixed-s"' in out


def test_yes_does_not_bypass_merged_privacy(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, argv=["--yes"], replies=[]
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "发送 1 条到 https://api.example.test/v1？[y/N]" in err
    assert provider.prompts == []
    assert not path.with_suffix(".sh").exists()


def test_multi_select_subset_sends_only_selected_prompt(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, TWO_BAT, replies=["2\n", "y\n", "y\n"]
    )
    err = capfd.readouterr().err
    assert code == 0
    assert len(provider.prompts) == 1
    assert '>>> # TODO: 手动检查: for /f "usebackq" %%j' in provider.prompts[0]
    assert '>>> # TODO: 手动检查: for /f "usebackq" %%i' not in provider.prompts[0]
    assert "选择要修复的条目" in err
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-s"' in out
    assert "手动检查: for /f \"usebackq\" %%i" in out


def test_manual_check_todo_remains_when_other_selected(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, TWO_BAT, replies=["1\n", "y\n", "y\n"]
    )
    assert code == 0
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-b"' in out
    assert "手动检查: for /f \"usebackq\" %%j" in out
    assert 'echo "fixed-s"' not in out


def test_selection_cancel_exit_1(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(tmp_path, monkeypatch, TWO_BAT, replies=["q\n"])
    err = capfd.readouterr().err
    assert code == 1
    assert "已取消" in err
    assert provider.prompts == []
    assert "发送 2 条到" not in err
    assert not path.with_suffix(".sh").exists()


def test_selection_out_of_range_is_empty_exit_3(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(tmp_path, monkeypatch, TWO_BAT, replies=["99\n"])
    err = capfd.readouterr().err
    assert code == 3
    assert "发送" not in err
    assert provider.prompts == []
    assert not path.with_suffix(".sh").exists()


def test_selection_unparsable_exit_3(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(tmp_path, monkeypatch, TWO_BAT, replies=["abc\n"])
    err = capfd.readouterr().err
    assert code == 3
    assert "未识别的选择: abc" in err
    assert provider.prompts == []
    assert not path.with_suffix(".sh").exists()


# ---------------------------------------------------------------------------
# 写盘分支 / 并发参数
# ---------------------------------------------------------------------------


def test_success_path_writes_once(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n", "y\n"]
    )
    err = capfd.readouterr().err
    assert code == 0
    assert err.count("[已写出]") == 1
    assert "API 修复 1 处" in err
    assert "TODO 处理完成：修复 1 / 跳过 0 / 失败 0（共 1 条选中）" in err
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-b"' in out
    assert "手动检查: for /f" not in out


def test_print_only_stdout_and_no_file(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, argv=["--print"], replies=["y\n", "y\n"]
    )
    captured = capfd.readouterr()
    assert code == 0
    assert 'echo "fixed-b"' in captured.out
    assert "[已写出]" not in captured.err
    assert not path.with_suffix(".sh").exists()


def test_dry_run_keeps_file_absent(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, argv=["--dry-run"], replies=["y\n", "y\n"]
    )
    err = capfd.readouterr().err
    assert code == 0
    assert "[dry-run] 将写出修复后的脚本（1 处修改）" in err
    assert not path.with_suffix(".sh").exists()


def test_concurrency_one_serial_path_completes(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        TWO_BAT,
        argv=["--max-concurrency", "1"],
        replies=["\n", "y\n", "y\n"],
    )
    err = capfd.readouterr().err
    assert code == 0
    assert "并发 1（--max-concurrency 可调）" in err
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-b"' in out and 'echo "fixed-s"' in out


def test_concurrency_greater_than_todos_completes(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        TWO_BAT,
        argv=["--parallel", "16"],
        replies=["\n", "y\n", "y\n"],
    )
    err = capfd.readouterr().err
    assert code == 0
    assert "并发 16（--max-concurrency 可调）" in err
    assert len(provider.prompts) == 2


# ---------------------------------------------------------------------------
# 错误隔离 / 限流 / 重试
# ---------------------------------------------------------------------------


def test_error_isolation_one_fails_others_applied(tmp_path, monkeypatch, capfd):
    def reply_for(prompt: str):
        if '>>> # TODO: 手动检查: for /f "usebackq" %%j' in prompt:
            return ProviderNetworkError("网络断了")
        return _reply_by_marker(prompt)

    provider = _FakeProvider(reply_for)
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        TWO_BAT,
        replies=["\n", "y\n", "n\n", "y\n"],
        provider=provider,
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "网络断了" in err
    assert "失败 1" in err
    assert "以下条目未修复" in err
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-b"' in out
    assert 'echo "fixed-s"' not in out
    assert "dir /s" in out  # 失败条目保留 TODO


def test_rate_limit_backoff_reduces_concurrency(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(lambda _p: ProviderRateLimitError("429"))
    delays: list[float] = []
    _install_fast_parallel(monkeypatch, sleeps=delays)
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        M1_BAT,
        replies=["y\n", "n\n"],
        provider=provider,
    )
    err = capfd.readouterr().err
    assert code == 3
    assert delays == [1.0, 2.0]
    assert "并发降至 1" in err
    assert "失败 1" in err
    assert not path.with_suffix(".sh").exists()


def test_failed_then_retry_succeeds_and_writes(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(
        responses=[ProviderNetworkError("boom"), 'echo "fixed-retry"']
    )
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        M1_BAT,
        replies=["y\n", "y\n", "y\n"],
        provider=provider,
    )
    err = capfd.readouterr().err
    assert code == 0
    assert "重试失败的 1 条？[y/N]" in err
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "fixed-retry"' in out
    assert "失败 0" in err


def test_keyboard_interrupt_discards_and_no_write(tmp_path, monkeypatch, capfd):
    def boom(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(parallel, "run_parallel", boom)
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n"]
    )
    err = capfd.readouterr().err
    assert code == 1
    assert "已中断" in err
    assert "未写盘" in err
    assert not path.with_suffix(".sh").exists()


# ---------------------------------------------------------------------------
# 合并（从后往前 + 行号偏移）
# ---------------------------------------------------------------------------


def test_back_to_front_merge_with_multiline_later_item(tmp_path, monkeypatch, capfd):
    def reply_for(prompt: str):
        if ">>> # TODO: 手动检查: [System.IO.File]" in prompt:
            return 'echo "file-read"\n: done'
        return "if true; then"

    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        M3_PS,
        argv=["--last-exit-code", "warn"],
        replies=["\n", "y\n", "y\n"],
        provider=_FakeProvider(reply_for),
        name="demo.ps1",
    )
    err = capfd.readouterr().err
    assert code == 0
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert "if true; then" in out
    assert 'echo "file-read"' in out
    assert ": done" in out
    assert "手动检查 $LASTEXITCODE" not in out
    assert "手动检查: [System.IO.File]" not in out
    assert out.index("if true; then") < out.index('echo "file-read"')


# ---------------------------------------------------------------------------
# 配置优先级 / 夹取
# ---------------------------------------------------------------------------


def _resolved_max_concurrency(argv, env, file_config):
    args = build_parser().parse_args(argv)
    return resolve_api_config(cli._api_cli_values(args), env, file_config).max_concurrency


def test_max_concurrency_priority_and_clamping():
    env = {"BAT2SH_MAX_CONCURRENCY": "9"}
    file_config = ApiConfig(max_concurrency=5)
    assert _resolved_max_concurrency(["x.bat"], env, file_config) == 9
    assert _resolved_max_concurrency([], {}, ApiConfig()) == 3
    assert _resolved_max_concurrency(["x.bat", "--max-concurrency", "7"], env, file_config) == 7
    assert _resolved_max_concurrency(["x.bat", "--parallel", "7"], {}, file_config) == 7
    assert _resolved_max_concurrency(["x.bat"], {}, file_config) == 5
    assert _resolved_max_concurrency(["x.bat", "--max-concurrency", "0"], {}, ApiConfig()) == 3
    assert _resolved_max_concurrency(["x.bat", "--max-concurrency", "-4"], {}, ApiConfig()) == 3
    assert _resolved_max_concurrency(["x.bat", "--max-concurrency", "99"], {}, ApiConfig()) == 16


def test_max_concurrency_cli_reaches_provider(tmp_path, monkeypatch):
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        M1_BAT,
        argv=["--max-concurrency", "7"],
        replies=["y\n", "y\n"],
    )
    assert code == 0
    assert path.with_suffix(".sh").exists()


# ---------------------------------------------------------------------------
# 面板（非 TTY 追加）
# ---------------------------------------------------------------------------


def _panel_tasks():
    marker = fixer.TodoMarker(
        out_line=6,
        kind="line",
        line_text="# TODO: 手动检查: x",
        marker_text="# TODO: 手动检查: x",
    )
    return parallel.plan_tasks([marker], "x\n", "demo.bat", "# TODO: 手动检查: x\n", 3)


def test_panel_tty_redraws_in_place_with_ansi_and_tail():
    tasks = _panel_tasks()
    tasks[0].status = parallel.STATUS_RUNNING
    stream = io.StringIO()
    panel = cli._FixPanel(tasks, stream, color=True, tty=True)
    panel.handle(parallel.FixEvent(1, parallel.STATUS_RUNNING, "", "echo hi"))
    panel.handle(parallel.FixEvent(1, parallel.STATUS_DONE))
    out = stream.getvalue()
    assert "\x1b[1A" in out
    assert "\x1b[K" in out
    assert "echo hi" in out
    assert "#1 第6行 done" in out


def test_panel_non_tty_appends_without_ansi_or_duplicates():
    stream = io.StringIO()
    panel = cli._FixPanel(_panel_tasks(), stream, color=False, tty=False)
    panel.handle(parallel.FixEvent(1, parallel.STATUS_RUNNING))
    panel.handle(parallel.FixEvent(1, parallel.STATUS_RUNNING))
    panel.handle(parallel.FixEvent(1, parallel.STATUS_RUNNING, "", "echo hi"))
    panel.handle(parallel.FixEvent(1, parallel.STATUS_DONE))
    out = stream.getvalue()
    assert "\x1b[" not in out
    assert out.count("#1 第6行 running") == 1
    assert "[#1] echo hi" in out
    assert "#1 第6行 done" in out


# ---------------------------------------------------------------------------
# --help / 既有语义（降级、无标记、配置错误、key 脱敏等）
# ---------------------------------------------------------------------------


def test_reg_marker_documented_in_help():
    assert "[REG]" in build_parser().format_help()


def test_fix_todos_degraded_exit_3(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, DEGRADE_PS, replies=["y\n"], name="demo.ps1"
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "已整体降级" in err
    assert provider.prompts == []


def test_fix_todos_no_markers_exit_0(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(tmp_path, monkeypatch, M2_BAT, replies=["y\n"])
    err = capfd.readouterr().err
    assert code == 0
    assert "未发现可修复 TODO" in err
    assert provider.prompts == []


def test_fix_todos_non_tty_refused_before_api(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(lambda _p: "")
    created = _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _NonTty())
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "需要交互终端" in err
    assert created == []
    assert provider.prompts == []


def test_fix_todos_missing_config_exit_6(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos"])
    err = capfd.readouterr().err
    assert code == 6
    assert "API 配置不完整" in err
    assert "base_url" in err and "model" in err


def test_fix_todos_unknown_provider_exit_6(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main(
        [
            str(path),
            "--fix-todos",
            "--api-provider",
            "ollama",
            "--api-base",
            "https://a.test/v1",
            "--api-model",
            "m",
        ]
    )
    err = capfd.readouterr().err
    assert code == 6
    assert "API 配置错误" in err


def test_fix_todos_mutually_exclusive_with_run(tmp_path, monkeypatch, capfd):
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", "--run", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "互斥" in err


def test_fix_todos_send_declined_keeps_todo_and_no_write(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(tmp_path, monkeypatch, M1_BAT, replies=["n\n"])
    err = capfd.readouterr().err
    assert code == 3
    assert provider.prompts == []
    assert "已取消发送，未写盘" in err
    assert not path.with_suffix(".sh").exists()


def test_fix_todos_apply_declined(tmp_path, monkeypatch, capfd):
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n", "\n"]
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "已取消应用，未写盘" in err
    assert "修复 1 / 跳过 0 / 失败 0" in err
    assert not path.with_suffix(".sh").exists()


def test_fix_todos_model_punts_counts_skipped(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(
        lambda _p: '# TODO: 手动检查: for /f "usebackq" %%i in (`dir /b`) do echo %%i'
    )
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n"], provider=provider
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "跳过 1" in err
    assert not path.with_suffix(".sh").exists()


def test_fix_todos_bash_n_gate_rejects_suggestion(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(lambda _p: 'echo "unterminated')
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n", "n\n"], provider=provider
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "未通过 bash -n" in err
    assert "失败 1" in err
    assert not path.with_suffix(".sh").exists()


def test_fix_todos_key_redacted_in_errors(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(
        lambda _p: ProviderNetworkError("boom Authorization=Bearer sekret-123")
    )
    code, path, provider = _run(
        tmp_path,
        monkeypatch,
        M1_BAT,
        argv=["--api-key", "sekret-123"],
        replies=["y\n", "n\n"],
        provider=provider,
    )
    err = capfd.readouterr().err
    assert code == 3
    assert "sekret-123" not in err
    assert "***" in err
    assert not path.with_suffix(".sh").exists()


def test_fix_todos_streams_chunks_to_stderr_not_stdout(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(lambda _p: ['echo "str', 'eamed"'])
    code, path, provider = _run(
        tmp_path, monkeypatch, M1_BAT, replies=["y\n", "y\n"], provider=provider
    )
    captured = capfd.readouterr()
    assert code == 0
    assert '[#1] echo "str' in captured.err
    assert 'eamed"' in captured.err
    assert 'echo "str' not in captured.out
    assert 'eamed"' not in captured.out
    out = path.with_suffix(".sh").read_text(encoding="utf-8")
    assert 'echo "streamed"' in out


def test_fix_todos_uses_env_config(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("BAT2SH_API_BASE", "https://env.example.test/v1")
    monkeypatch.setenv("BAT2SH_API_MODEL", "env-model")
    provider = _FakeProvider(lambda _p: 'echo "from-env"')
    created = _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos"])
    err = capfd.readouterr().err
    assert code == 0
    assert "https://env.example.test/v1" in err
    assert created[0].base_url == "https://env.example.test/v1"
    assert created[0].model == "env-model"


def test_fix_todos_uses_file_config(tmp_path, monkeypatch, capfd):
    save_api_config(ApiConfig(base_url="https://file.test/v1", model="file-model"))
    provider = _FakeProvider(lambda _p: 'echo "from-file"')
    created = _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos"])
    err = capfd.readouterr().err
    assert code == 0
    assert "https://file.test/v1" in err
    assert created[0].base_url == "https://file.test/v1"
