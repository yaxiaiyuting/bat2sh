"""PowerShell 路径 bash -n 后置校验（P0 安全网）测试：失败降级、跳过开关、--run 拒绝。"""

from __future__ import annotations

from bat2sh.cli import main
from bat2sh.core.powershell import PowerShellConverter
from bat2sh.core.settings import ConvertSettings

BROKEN = "#!/usr/bin/env bash\nif\n"

# 真实还原：多行管道链在当前 PS 转换器下产出 topProcesses=$(ps aux |)（bash -n 失败）
MULTILINE_PIPE_CHAIN = (
    "$topProcesses = Get-Process |\n"
    "    Where-Object { $_.WorkingSet64 -gt 50MB } |\n"
    "    Sort-Object WorkingSet64 -Descending |\n"
    "    Select-Object -First 10 Name, Id,\n"
    '        @{Name = "MemoryMB"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } }\n'
    'Write-Host "Top:"\n'
)


def broken_converter(monkeypatch, **options) -> PowerShellConverter:
    converter = PowerShellConverter(ConvertSettings(**options), "broken.ps1")
    monkeypatch.setattr(converter, "_compose", lambda: BROKEN)
    return converter


def test_broken_output_is_degraded(monkeypatch, bash_check):
    converter = broken_converter(monkeypatch)
    out = converter.convert('Write-Host "hi"\n')
    assert "未通过 bash -n" in out
    assert "原脚本内容（保留为注释，供人工转换）:" in out
    assert '# Write-Host "hi"' in out
    bash_check(out)
    assert converter.report.error_count == 1
    assert converter.report.errors[0].category == "syntax"


def test_ps_pipe_chain_syntax_failure_is_error(convert_ps, bash_check):
    out, report = convert_ps(MULTILINE_PIPE_CHAIN)
    assert report.error_count == 1
    assert report.errors[0].category == "syntax"
    assert "未通过 bash -n" in out
    bash_check(out)


def test_valid_output_not_degraded(convert_ps):
    out, report = convert_ps('Write-Host "hello"\n')
    assert "未通过 bash -n" not in out
    assert report.error_count == 0
    assert 'echo "hello"' in out


def test_no_bash_check_skips_validation(monkeypatch):
    converter = broken_converter(monkeypatch, bash_check=False)
    out = converter.convert('Write-Host "hi"\n')
    assert "未通过 bash -n" not in out
    assert out == BROKEN
    assert converter.report.error_count == 0


def test_degraded_ps_script_is_refused_by_run(tmp_path, monkeypatch):
    monkeypatch.setattr(PowerShellConverter, "_compose", lambda self: BROKEN)
    script = tmp_path / "broken.ps1"
    script.write_text('Write-Host "hi"\n', encoding="utf-8")
    assert main([str(script), "--run", "--yes"]) == 4
