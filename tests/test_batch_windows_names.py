"""B1 名称映射在 ``core/batch.py`` 中的集成行为（v1.10.0a1）。

覆盖：``form=none`` 环境变量 → 行级诚实 TODO；映射型环境变量 → Linux 值 + 警告；
转义 ``%%X%%`` 不误判；脚本自赋值的同名变量按用户变量处理；盘符/UNC 登记未集成。
"""

from __future__ import annotations


def test_program_files_becomes_line_level_todo(convert_bat, bash_check):
    script, report = convert_bat("echo %ProgramFiles%\n")
    assert "# TODO: 手动检查: echo %ProgramFiles%" in script
    assert report.todo_count == 1
    assert "无对应物" in report.todos[0].message
    bash_check(script)


def test_program_files_todo_in_simple_command(convert_bat, bash_check):
    script, report = convert_bat('md "%ProgramFiles%\\App"\n')
    assert "# TODO: 手动检查: md \"%ProgramFiles%\\App\"" in script
    assert report.todo_count == 1
    bash_check(script)


def test_escaped_percent_pair_is_not_a_variable(convert_bat):
    script, report = convert_bat("echo %%ProgramFiles%%\n")
    assert report.todo_count == 0
    assert '"%ProgramFiles%"' in script


def test_all_users_profile_maps_to_usr_share_with_warning(convert_bat, bash_check):
    script, report = convert_bat('rm -f "%ALLUSERSPROFILE%\\DrWatson\\*.*"\n')
    assert '/usr/share/DrWatson' in script
    assert report.todo_count == 0
    assert any("ALLUSERSPROFILE" in w.message.upper() for w in report.warnings)
    bash_check(script)


def test_all_users_profile_lookup_is_case_insensitive(convert_bat):
    script, _report = convert_bat("echo %allusersprofile%\n")
    assert "/usr/share" in script


def test_script_assigned_name_is_treated_as_user_variable(convert_bat, bash_check):
    script, report = convert_bat('set ProgramFiles=D:\\pf\necho %ProgramFiles%\\x\n')
    assert report.todo_count == 0
    assert "ProgramFiles=\"D:/pf\"" in script
    assert "${ProgramFiles}/x" in script
    bash_check(script)


def test_if_header_condition_is_a_documented_limitation(convert_bat, bash_check):
    script, report = convert_bat('if exist "%ProgramFiles%\\App" echo found\n')
    assert report.todo_count == 0
    assert "${ProgramFiles:-}" in script
    bash_check(script)


def test_block_body_todo_keeps_blocks_balanced(convert_bat, bash_check):
    script, report = convert_bat('if exist "x" (\n  md "%ProgramFiles%\\App"\n)\n')
    assert report.todo_count == 1
    assert "# TODO: 手动检查: md \"%ProgramFiles%\\App\"" in script
    bash_check(script)


def test_drive_letters_are_registered_not_integrated(convert_bat):
    script, report = convert_bat("copy D:\\data\\a.txt E:\\backup\\\n")
    assert script == convert_bat("copy D:\\data\\a.txt E:\\backup\\\n")[0]
    assert "D:/data/a.txt" in script
    assert report.todo_count == 0


def test_unc_paths_are_registered_not_integrated(convert_bat):
    script, report = convert_bat("dir \\\\server\\share\n")
    assert report.todo_count == 0
    assert "server/share" in script


def test_mapped_env_vars_are_unchanged(convert_bat):
    script, _report = convert_bat("echo %SystemRoot%\\System32\\cmd.exe\n")
    assert "${SystemRoot:-/}/System32/cmd.exe" in script
