"""PS 注册表路径不再误译为文件操作的回归测试（v1.6.0 阶段 B / Fix B-2）。"""

from __future__ import annotations


def test_test_path_registry_not_file_op(convert_ps, bash_check):
    out, report = convert_ps('Test-Path "HKLM:\\SOFTWARE\\Foo"\n')
    assert '[[ -e "HKLM' not in out
    assert '[[ -e "HKLM:/SOFTWARE/Foo"' not in out
    assert r'# TODO[REG] op=test key="HKLM:\SOFTWARE\Foo"' in out
    assert report.todo_count == 1
    assert report.todos[0].category == "registry"
    bash_check(out)


def test_get_item_registry_not_file_op(convert_ps, bash_check):
    out, _ = convert_ps('Get-Item -Path "HKCU:\\Software\\MyApp"\n')
    assert "ls -la" not in out
    assert r'# TODO[REG] op=read key="HKCU:\Software\MyApp"' in out
    bash_check(out)


def test_get_childitem_registry_enumerate(convert_ps, bash_check):
    out, _ = convert_ps('Get-ChildItem -Path "HKLM:\\SOFTWARE\\Vendor\\Unmapped"\n')
    assert "ls -la" not in out
    assert r"op=enumerate" in out
    bash_check(out)


def test_new_item_registry_write(convert_ps, bash_check):
    out, _ = convert_ps('New-Item -Path "HKLM:\\SOFTWARE\\MyApp" -Force\n')
    assert "touch" not in out
    assert r'# TODO[REG] op=write key="HKLM:\SOFTWARE\MyApp"' in out
    bash_check(out)


def test_remove_item_registry_delete(convert_ps, bash_check):
    out, _ = convert_ps('Remove-Item -Path "HKLM:\\SOFTWARE\\MyApp" -Recurse\n')
    assert "rm " not in out
    assert r'# TODO[REG] op=delete key="HKLM:\SOFTWARE\MyApp"' in out
    bash_check(out)


def test_all_registry_roots(convert_ps, bash_check):
    for root in ("HKLM", "HKCU", "HKCR", "HKU", "HKCC"):
        out, _ = convert_ps(f'Test-Path "{root}:\\Vendor\\Key"\n')
        assert f'# TODO[REG] op=test key="{root}:\\Vendor\\Key"' in out, root
        assert '[[ -e "' not in out, root
    bash_check(out)


def test_file_paths_unaffected(convert_ps, bash_check):
    out, _ = convert_ps('if (Test-Path "/tmp/x") { Write-Host "y" }\n')
    assert '[[ -e "/tmp/x" ]]' in out
    assert "TODO[REG]" not in out
    assert "los -la" not in out

    out, _ = convert_ps('Get-Item "/tmp/x"\nmkdir_and_test = 1\n')
    assert 'ls -la "/tmp/x"' in out

    out, _ = convert_ps('New-Item -Path "/tmp/x" -Force\n')
    assert 'touch "/tmp/x"' in out

    out, _ = convert_ps('Remove-Item -Path "/tmp/x" -Recurse\n')
    assert 'rm -r "/tmp/x"' in out
    bash_check(out)


def test_condition_registry_uses_false_placeholder(convert_ps, bash_check):
    out, report = convert_ps('if (Test-Path "HKLM:\\SOFTWARE\\Foo") { Write-Host "y" }\n')
    assert "if false; then" in out
    assert '[[ -e "HKLM' not in out
    assert any("注册表路径" in d.message for d in report.todos)
    bash_check(out)


def test_assignment_registry_structured(convert_ps, bash_check):
    out, _ = convert_ps('$ok = Test-Path "HKCU:\\Software\\Bar"\n')
    assert r'# TODO[REG] op=test key="HKCU:\Software\Bar"' in out
    assert "=$((" not in out
    bash_check(out)
