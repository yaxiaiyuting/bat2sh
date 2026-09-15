"""服务配置读取的结构化 TODO 与 systemctl 引导（v1.6.0 阶段 B / Fix B-P1）。

红线：不做 Windows 服务名 -> Linux unit 的名称映射（无证据），仅引导 + 结构化 TODO。
"""

from __future__ import annotations


def test_get_itemproperty_service_structured(convert_ps, bash_check):
    out, report = convert_ps(
        'Get-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Netlogon" -Name Start\n'
    )
    assert r'# TODO[REG] op=read key="HKLM:\SYSTEM\CurrentControlSet\Services\Netlogon" value="Start"' in out
    assert report.error_count == 0
    bash_check(out)


def test_service_hint_mentions_systemctl(convert_ps):
    _, report = convert_ps(
        'Get-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Netlogon" -Name Start\n'
    )
    assert any(
        "systemctl" in d.message and d.category == "registry" for d in report.todos
    )


def test_service_name_not_invented_mapping(convert_ps):
    out, _ = convert_ps(
        'Get-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Netlogon" -Name Start\n'
    )
    assert "is-active Netlogon" not in out
    assert "is-enabled Netlogon" not in out
    assert "systemctl" not in out


def test_non_service_read_structured_without_hint(convert_ps):
    out, report = convert_ps('Get-ItemProperty -Path "HKCU:\\Software\\Foo" -Name Bar\n')
    assert r'# TODO[REG] op=read key="HKCU:\Software\Foo" value="Bar"' in out
    assert all("systemctl" not in d.message for d in report.todos)


def test_batch_reg_query_service_hint(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nreg query "HKLM\\SYSTEM\\CurrentControlSet\\Services\\Netlogon"\n'
    )
    assert r'# TODO[REG] op=read key="HKLM\SYSTEM\CurrentControlSet\Services\Netlogon"' in out
    assert any("systemctl" in d.message for d in report.todos)
    bash_check(out)
