"""注册表写类结构化 TODO 的回归测试（v1.6.0 阶段 B / Stage 4）。"""

from __future__ import annotations

import re


def _uncommented(out: str) -> list[str]:
    return [
        line for line in out.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_set_itemproperty_write(convert_ps, bash_check):
    out, report = convert_ps(
        'Set-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name WallpaperStyle -Value 2\n'
    )
    assert r'# TODO[REG] op=write key="HKCU:\Control Panel\Desktop" value="WallpaperStyle"' in out
    assert report.error_count == 0
    assert not [line for line in _uncommented(out) if "HK" in line]
    bash_check(out)


def test_new_itemproperty_write(convert_ps, bash_check):
    out, _ = convert_ps(
        'New-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name Wallpaper -Value "x"\n'
    )
    assert "op=write" in out
    assert "Wallpaper" in out
    bash_check(out)


def test_remove_itemproperty_delete(convert_ps, bash_check):
    out, _ = convert_ps('Remove-ItemProperty -Path "HKCU:\\Software\\MyApp" -Name Setting\n')
    assert "op=delete" in out
    bash_check(out)


def test_new_item_registry_write(convert_ps, bash_check):
    out, _ = convert_ps('New-Item -Path "HKLM:\\SOFTWARE\\MyApp" -Force\n')
    assert "op=write" in out
    bash_check(out)


def test_remove_item_registry_delete(convert_ps, bash_check):
    out, _ = convert_ps('Remove-Item -Path "HKLM:\\SOFTWARE\\MyApp" -Recurse\n')
    assert "op=delete" in out
    bash_check(out)


def test_com_regread_write_delete(convert_ps, bash_check):
    out, _ = convert_ps(
        "$ws = New-Object -ComObject WScript.Shell\n"
        '$val = $ws.RegRead("HKCU\\Software\\MyApp\\Setting")\n'
        '$ws.RegWrite("HKCU\\Software\\MyApp\\Setting", "1")\n'
        '$ws.RegDelete("HKCU\\Software\\MyApp\\Setting")\n'
    )
    assert "op=read" in out and "op=write" in out and "op=delete" in out
    assert "WScript.Shell）注册表 API" in out or "WScript" in out
    bash_check(out)


def test_dotnet_registry_ops(convert_ps, bash_check):
    out, _ = convert_ps(
        '$k = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey("SOFTWARE\\Foo")\n'
        '[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey("Software\\Foo")\n'
    )
    assert "op=read" in out
    assert "op=write" in out
    bash_check(out)


def test_dotnet_delete_subkey(convert_ps, bash_check):
    out, _ = convert_ps(
        '[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKey("Software\\Foo")\n'
    )
    assert "op=delete" in out
    bash_check(out)


def test_write_hint_mentions_config_file(convert_ps):
    _, report = convert_ps('Set-ItemProperty -Path "HKCU:\\Software\\A" -Name B -Value 1\n')
    assert any(
        d.category == "registry" and "编辑对应配置文件" in d.message
        for d in report.todos
    )


def test_batch_reg_add_write(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nreg add "HKCU\\Software\\MyApp" /v Setting /t REG_SZ /d value /f\n'
    )
    assert "op=write" in out
    assert report.error_count == 0
    bash_check(out)


def test_no_uncommented_registry_leak(convert_ps, bash_check):
    out, _ = convert_ps(
        'Set-ItemProperty -Path "HKCU:\\Software\\A" -Name B -Value 1\n'
        'Get-ItemProperty -Path "HKCU:\\Software\\A" -Name B\n'
    )
    assert not [line for line in _uncommented(out) if re.search(r"(?i)HK(CU|LM|CR|U|CC):", line)]
    bash_check(out)
