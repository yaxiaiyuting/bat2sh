"""v1.8.2 2c/A-6：延迟展开动态变量名 → 诚实 TODO（保守，不硬修）。

语料依据（v1.8.2 artifact 分类 §2.A A7 / §10.3 A-6）：
- ``随机替换欢迎界面和桌面.bat:9`` ``set s!w!="%%~fi"``（名字本身含变量）
  → 旧产物 ``s__w_=…``（静默错误）
- ``随机替换欢迎界面和桌面.bat:13`` ``copy !s%_r%! …`` → 旧产物残留 ``!s${_r}!``

用户裁定 3：A-6「不硬修，升级为诚实 TODO」（纪律 1）。
"""

from __future__ import annotations


def test_dynamic_set_name_becomes_todo(convert_bat):
    out, report = convert_bat(
        '@echo off\nsetlocal enabledelayedexpansion\nset /a w+=1\nset s!w!="x"\n'
    )
    assert "s__w_" not in out
    assert "# TODO: 手动检查: set s${w}=\"x\"" in out
    assert report.todo_count >= 1


def test_residual_dynamic_reference_becomes_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nsetlocal enabledelayedexpansion\ncopy !s%_r%! dst\n"
    )
    assert "!s${_r}!" not in out
    assert "# TODO: 手动检查:" in out
    assert report.todo_count >= 1


def test_plain_delayed_variable_still_converts(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nsetlocal enabledelayedexpansion\nset x=5\necho !x!\n"
    )
    bash_check(out)
    assert 'echo "${x}"' in out
    assert report.todo_count == 0
