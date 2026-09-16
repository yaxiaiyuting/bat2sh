"""v1.8.2 A-4a：`set path=…` 后 `%path%` 被误当成 Linux `$PATH` 修复回归。

语料依据（v1.8.2 artifact 分类 §2.A A4）：
- ``批量建立文件夹.bat:7`` ``set path="%~dp1"``、``:9`` ``cd /d %path%``
  → 误产 ``cd "${PATH:-}"``（指向 Linux 环境变量），应为用户变量 ``${path}``。
cmd 变量大小写不敏感，故 ``set TEMP=…`` 应影响 ``%temp%``。
"""

from __future__ import annotations


def test_user_variable_shadows_env_map(convert_bat, bash_check, bash_run):
    out, _ = convert_bat("@echo off\nset path=D:\\x\necho %path%\n", bash_check=False)
    bash_check(out)
    assert 'path="D:/x"' in out
    assert 'echo "${path}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "D:/x"


def test_env_map_still_used_without_user_assignment(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\necho %PATH%\n", bash_check=False)
    bash_check(out)
    assert 'echo "${PATH:-}"' in out


def test_shadow_is_case_insensitive(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset TEMP=C:\\t\necho %temp%\n", bash_check=False)
    bash_check(out)
    assert 'TEMP="C:/t"' in out
    assert 'echo "${TEMP}"' in out


def test_loop_variable_expansion_unaffected(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\nfor %%i in (2 3) do set /a S=%%i*%%i\necho %S%\n", bash_check=False
    )
    bash_check(out)
    assert "S=$(( ${i}*${i} ))" in out
