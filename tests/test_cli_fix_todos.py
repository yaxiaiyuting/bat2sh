"""CLI --fix-todos 测试：隐私提示、逐条确认、降级、退出码与写盘行为。

通过注入 fake provider（monkeypatch cli.create_provider）与脚本化 TTY stdin，
不访问网络；本模块带 socket 守卫（autouse）。
"""

from __future__ import annotations

import socket
import sys

import pytest

import bat2sh.cli as cli
from bat2sh.cli import main
from bat2sh.core.api.config import ApiConfig, save_api_config
from bat2sh.core.api.provider import ProviderNetworkError, ProviderTimeoutError

M1_BAT = '@echo off\nfor /f "usebackq" %%i in (`dir /b`) do echo %%i\n'
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


class _FakeProvider:
    """脚本化 Provider：逐次调用产出 chunks；可模拟思维链与中途异常。

    - ``replies``：每次 API 调用的完整回复（整段作为一个正文块产出）；
    - ``chunks``：显式正文块序列（覆盖 ``replies``，用于检验逐块流式）；
    - ``error``：每次调用开始时抛出（``complete_stream`` 首次迭代时触发）；
    - ``reasoning``：在首个正文块之前调用 ``on_reasoning`` 的次数；
    - ``mid_error``：产出第 2 块前抛出（模拟流中途 ProviderError/KeyboardInterrupt）。
    """

    def __init__(self, replies=None, error=None, *, chunks=None, reasoning=0, mid_error=None):
        self.replies = list(replies or [])
        self.error = error
        self.chunks = list(chunks) if chunks is not None else None
        self.reasoning = reasoning
        self.mid_error = mid_error
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, timeout: float) -> str:
        return "".join(self.complete_stream(prompt, timeout=timeout))

    def complete_stream(self, prompt: str, *, timeout: float, on_reasoning=None):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if self.chunks is not None:
            reply_chunks = list(self.chunks)
        else:
            if not self.replies:
                raise AssertionError("FakeProvider 无更多预置回复")
            reply_chunks = [self.replies.pop(0)]
        for count in range(1, self.reasoning + 1):
            if on_reasoning is not None:
                on_reasoning(count)
        for index, chunk in enumerate(reply_chunks):
            if index and self.mid_error is not None:
                raise self.mid_error
            yield chunk


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


def _write(tmp_path, text, name="demo.bat"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_fix_todos_success_writes_once(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=['echo "fixed-for"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 0
    assert "即将把以下内容发送到外部服务" in err
    assert "https://api.example.test/v1" in err
    assert "将发送的内容（原文，可复核）" in err
    assert "发送本条？[y/N/q]" in err
    assert "应用这条修改？[y/N]" in err
    assert '+echo "fixed-for"' in err
    assert "API 修复 1 处" in err
    out = (tmp_path / "demo.sh").read_text(encoding="utf-8")
    assert 'echo "fixed-for"' in out
    assert "手动检查: for /f" not in out
    assert len(provider.prompts) == 1
    assert ">>> " in provider.prompts[0]


def test_fix_todos_streams_chunks_to_stderr_not_stdout(tmp_path, monkeypatch, capfd):
    """流式正文逐块写到 stderr 与接收提示；stdout 保持干净；最终仍写盘。"""
    provider = _FakeProvider(chunks=['echo "str', 'eamed"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    captured = capfd.readouterr()
    assert code == 0
    assert "正在接收模型输出" in captured.err
    assert 'echo "str' in captured.err
    assert 'eamed"' in captured.err
    assert 'echo "str' not in captured.out
    assert 'eamed"' not in captured.out
    out = (tmp_path / "demo.sh").read_text(encoding="utf-8")
    assert 'echo "streamed"' in out


def test_fix_todos_reasoning_status_without_text(tmp_path, monkeypatch, capfd):
    """思维链仅显示段数状态行（含第 25 段刷新），不显示思维链文本；正文照常显示。"""
    provider = _FakeProvider(replies=['echo "reasoned"'], reasoning=25)
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 0
    assert "模型思考中" in err
    assert "思维链 1 段" in err
    assert "思维链 25 段" in err
    assert 'echo "reasoned"' in err


def test_fix_todos_keyboard_interrupt_mid_stream(tmp_path, monkeypatch, capfd):
    """流中途 Ctrl+C：退出码 1、不写盘，状态行清理不崩溃且提示未写盘。"""
    provider = _FakeProvider(
        chunks=['echo "partial"', 'echo "never"'], mid_error=KeyboardInterrupt()
    )
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "已中断" in err
    assert "未写盘" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_mid_stream_provider_error_keeps_todo(tmp_path, monkeypatch, capfd):
    """流中途 ProviderError：本条保留 TODO、不写盘，流程按既有语义结束。"""
    provider = _FakeProvider(
        chunks=['echo "partial"', 'echo "never"'], mid_error=ProviderTimeoutError("slow")
    )
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "本条保留 TODO" in err
    assert "失败 1" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_send_declined_keeps_todo_and_no_write(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=['echo "never"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["n\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert provider.prompts == []
    assert not (tmp_path / "demo.sh").exists()
    assert "跳过 1" in err
    assert "API 建议仍需人工复核" in err


def test_fix_todos_api_failure_isolated(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(error=ProviderNetworkError("boom"))
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "API 调用失败（本条保留 TODO）" in err
    assert "失败 1" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_quit_discards_accepted_changes(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=["if true; then\necho ok", 'echo "file"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n", "q\n"]))
    path = _write(tmp_path, M3_PS, name="demo.ps1")
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "未写盘" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_non_tty_refused_before_api(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=[])
    created = _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _NonTty())
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "需要交互终端" in err
    assert created == []
    assert provider.prompts == []


def test_fix_todos_yes_does_not_bypass_privacy(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=[])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty([]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", "--yes", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "发送本条？" in err
    assert provider.prompts == []
    assert not (tmp_path / "demo.sh").exists()


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
        [str(path), "--fix-todos", "--api-provider", "ollama", "--api-base", "https://a.test/v1", "--api-model", "m"]
    )
    err = capfd.readouterr().err
    assert code == 6
    assert "API 配置错误" in err


def test_fix_todos_bash_n_gate_rejects_suggestion(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=['echo "unterminated'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "未通过 bash -n" in err
    assert "失败 1" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_apply_declined(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=['echo "fixed"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "跳过 1" in err
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_model_punts_counts_skipped(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=["# TODO: 手动检查: for /f \"usebackq\" %%i in (`dir /b`) do echo %%i"])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "模型未给出可用修改" in err
    assert "跳过 1" in err


def test_fix_todos_no_markers_exit_0(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=[])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M2_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 0
    assert "未发现可修复 TODO" in err
    assert provider.prompts == []


def test_fix_todos_degraded_exit_3(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=[])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, DEGRADE_PS, name="demo.ps1")
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 3
    assert "已整体降级" in err
    assert provider.prompts == []


def test_fix_todos_mutually_exclusive_with_run(tmp_path, monkeypatch, capfd):
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", "--run", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 1
    assert "互斥" in err


def test_fix_todos_print_only(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=['echo "printed"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", "--print", *API_ARGS])
    captured = capfd.readouterr()
    assert code == 0
    assert 'echo "printed"' in captured.out
    assert not (tmp_path / "demo.sh").exists()


def test_fix_todos_key_redacted_in_errors(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(
        error=ProviderNetworkError("boom Authorization=Bearer sekret-123")
    )
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos", *API_ARGS, "--api-key", "sekret-123"])
    err = capfd.readouterr().err
    assert code == 3
    assert "sekret-123" not in err
    assert "***" in err


def test_fix_todos_offset_after_multiline_replacement(tmp_path, monkeypatch, capfd):
    provider = _FakeProvider(replies=["if true; then\necho ok", 'echo "file-read"'])
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n", "y\n", "y\n"]))
    path = _write(tmp_path, M3_PS, name="demo.ps1")
    code = main([str(path), "--fix-todos", *API_ARGS])
    err = capfd.readouterr().err
    assert code == 0
    assert "API 修复 2 处" in err
    assert "第 9 行" in provider.prompts[1]
    out = (tmp_path / "demo.sh").read_text(encoding="utf-8")
    assert "if true; then" in out
    assert 'echo "file-read"' in out
    assert "手动检查 $LASTEXITCODE" not in out
    assert "手动检查: [System.IO.File]" not in out
    assert out.count("TODO") == 1  # 仅剩 M5 文件头说明


def test_fix_todos_uses_env_config(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("BAT2SH_API_BASE", "https://env.example.test/v1")
    monkeypatch.setenv("BAT2SH_API_MODEL", "env-model")
    provider = _FakeProvider(replies=['echo "from-env"'])
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
    provider = _FakeProvider(replies=['echo "from-file"'])
    created = _install_provider(monkeypatch, provider)
    monkeypatch.setattr(sys, "stdin", _ScriptedTty(["y\n", "y\n"]))
    path = _write(tmp_path, M1_BAT)
    code = main([str(path), "--fix-todos"])
    err = capfd.readouterr().err
    assert code == 0
    assert "https://file.test/v1" in err
    assert created[0].base_url == "https://file.test/v1"
