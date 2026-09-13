"""批处理转换器的回归测试。

这些用例锁定当前实现的行为。标注「锁定当前行为」的断言描述的是已知不理想、
留给后续阶段（见 README 第 8 节）改进的输出；届时请同步更新对应用例。
"""

from __future__ import annotations

import pytest

from bat2sh.core.types import SourceKind


# ----------------------------------------------------------------------
# 脚本头与严格模式
# ----------------------------------------------------------------------
def test_header_contains_single_set_e(convert_bat):
    out, report = convert_bat("@echo off\necho hi\n")
    assert out.startswith("#!/usr/bin/env bash\n")
    assert out.count("set -euo pipefail") == 1
    assert report.kind is SourceKind.BATCH


def test_strict_off_omits_set_e(convert_bat):
    out, _ = convert_bat("@echo off\necho hi\n", strict_mode=False)
    assert "set -euo pipefail" not in out


# ----------------------------------------------------------------------
# 变量与 set
# ----------------------------------------------------------------------
def test_set_and_echo(convert_bat):
    out, report = convert_bat("@echo off\nset VAR=value\necho %VAR%\n")
    assert 'VAR="value"' in out
    assert 'echo "${VAR}"' in out
    assert report.todo_count == 0


def test_set_quoted_value_keeps_spaces(convert_bat):
    out, _ = convert_bat('@echo off\nset "VAR=hello world"\necho %VAR%\n')
    assert 'VAR="hello world"' in out


def test_set_a(convert_bat):
    out, report = convert_bat("@echo off\nset /a x=1+2\necho %x%\n")
    assert "x=$(( 1+2 ))" in out
    assert report.todo_count == 0


def test_set_a_compound(convert_bat):
    out, _ = convert_bat("@echo off\nset /a x=5\nset /a x+=1\n")
    assert "x=$(( 5 ))" in out
    assert "x=$(( x + (1) ))" in out


def test_set_p_read_guarded_for_set_e(convert_bat):
    out, report = convert_bat("@echo off\nset /p NAME=请输入名字: \n")
    assert 'read -rp "请输入名字:" NAME || true' in out
    assert report.warning_count == 0


def test_set_p_read_without_guard_when_strict_off(convert_bat):
    out, _ = convert_bat("@echo off\nset /p V=p\n", strict_mode=False)
    assert 'read -rp "p" V' in out
    assert "|| true" not in out


# ----------------------------------------------------------------------
# if
# ----------------------------------------------------------------------
def test_if_exist_else(convert_bat):
    out, report = convert_bat(
        "@echo off\nif exist config.ini (\n    echo yes\n) else (\n    echo no\n)\n"
    )
    assert 'if [ -e "config.ini" ]; then' in out
    assert "    echo \"yes\"" in out
    assert "else" in out
    assert out.rstrip().endswith("fi")
    assert report.todo_count == 0


def test_if_defined(convert_bat):
    out, _ = convert_bat("@echo off\nif defined VAR echo yes\n")
    assert 'if [ -n "${VAR:-}" ]; then' in out


def test_if_compare(convert_bat):
    out, _ = convert_bat('@echo off\nif "%A%"=="B" echo eq\n')
    assert 'if [ "${A}" = "B" ]; then' in out


# ----------------------------------------------------------------------
# if errorlevel
# ----------------------------------------------------------------------
def test_errorlevel_1_captures_previous_command(convert_bat):
    out, report = convert_bat("@echo off\nmkdir out\nif errorlevel 1 echo failed\n")
    assert "if ! mkdir -p out; then" in out
    assert report.warning_count == 0
    assert report.todo_count == 0


def test_errorlevel_2_uses_status_snapshot(convert_bat):
    out, report = convert_bat("@echo off\nmkdir out\nif errorlevel 2 echo failed\n")
    assert "__bat2sh_status=0" in out
    assert "mkdir -p out || __bat2sh_status=$?" in out
    assert 'if [ "$__bat2sh_status" -ge 2 ]; then' in out
    assert report.warning_count == 1


def test_errorlevel_0_keeps_command(convert_bat):
    out, report = convert_bat("@echo off\nmkdir out\nif errorlevel 0 echo ok\n")
    assert "mkdir -p out" in out
    assert "if true; then" in out
    assert report.warning_count == 0


def test_errorlevel_not_negates(convert_bat):
    out, _ = convert_bat("@echo off\nmkdir out\nif not errorlevel 1 echo ok\n")
    assert "if mkdir -p out; then" in out


def test_errorlevel_consecutive_second_falls_back(convert_bat):
    # 锁定当前行为：N>1 的连续判断只有第一条生成快照，第二条退回 $? 并告警。
    # 该回退在 strict 模式下通常是死代码（README 8.1 第 12 条），阶段 6 再改善。
    out, report = convert_bat(
        "@echo off\nmkdir out\nif errorlevel 2 echo a\nif errorlevel 3 echo b\n"
    )
    assert 'if [ "$__bat2sh_status" -ge 2 ]; then' in out
    assert "if [ $? -ge 3 ]; then" in out
    assert report.warning_count == 2


def test_errorlevel_elif_falls_back(convert_bat):
    # 锁定当前行为：else if errorlevel 无法复用状态快照，退回 $? + 警告（阶段 6 改善）
    out, report = convert_bat(
        "@echo off\nmkdir out\n"
        "if errorlevel 1 (\n  echo one\n) else if errorlevel 2 (\n  echo two\n)\n"
    )
    assert "if ! mkdir -p out; then" in out
    assert "elif [ $? -ge 2 ]; then" in out
    assert report.warning_count == 1


def test_errorlevel_slash_i_warns_but_captures(convert_bat):
    out, report = convert_bat("@echo off\nmkdir out\nif /i errorlevel 1 echo x\n")
    assert "if ! mkdir -p out; then" in out
    assert report.warning_count == 1


def test_errorlevel_after_todo_command_falls_back(convert_bat):
    # 锁定当前行为：上一条命令本身是 TODO 时无法捕获退出码，退回 $? + 警告
    out, report = convert_bat("@echo off\nfoo.exe\nif errorlevel 1 echo failed\n")
    assert "if [ $? -ge 1 ]; then" in out
    assert "# TODO: 手动检查: foo.exe" in out
    assert report.todo_count == 1


# ----------------------------------------------------------------------
# pause / 重定向
# ----------------------------------------------------------------------
def test_pause_redirection_current_behavior(convert_bat):
    # 锁定当前行为：重定向追加在 || true 之后，实际作用于 true 而非 read（阶段 6 候选）
    out, _ = convert_bat("@echo off\npause >nul\n")
    assert 'read -rp "Press Enter to continue..." || true >/dev/null' in out


def test_redirect_order_preserved(convert_bat):
    out, report = convert_bat("@echo off\nfoo > out.txt 2>&1\n")
    assert "foo >out.txt 2>&1" in out
    assert report.warning_count == 1  # 未知命令 foo


# ----------------------------------------------------------------------
# for
# ----------------------------------------------------------------------
def test_for_l(convert_bat):
    out, report = convert_bat("@echo off\nfor /l %%i in (1,1,3) do echo %%i\n")
    assert "for i in $(seq 1 1 3); do" in out
    assert 'echo "${i}"' in out
    assert report.todo_count == 0


def test_for_glob_enables_nullglob(convert_bat):
    out, report = convert_bat("@echo off\nfor %%f in (*.log) do echo %%f\n")
    assert "shopt -s nullglob" in out
    assert "for f in *.log; do" in out
    assert report.warning_count == 1


def test_echo_star_is_literal_no_nullglob(convert_bat):
    out, report = convert_bat('@echo off\necho "*.txt"\necho *.log\n')
    assert "shopt -s nullglob" not in out
    assert 'echo "*.txt"' in out
    assert report.warning_count == 0


def test_for_nested_inner_loop_current_behavior(convert_bat):
    # 锁定当前行为：内层循环的 %%a 展开为未加引号的 ${a}（阶段 5.2/后续候选）
    out, _ = convert_bat(
        "@echo off\nfor %%a in (*.txt) do (\n    for %%b in (%%a) do (\n"
        "        echo %%b\n    )\n)\n"
    )
    assert "for a in *.txt; do" in out
    assert "for b in ${a}; do" in out


def test_for_f_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%i in ('dir /b') do echo %%i\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1
    assert "for /f" in report.todos[0].message


def test_for_f_without_options_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /f %%i in ('dir /b') do echo %%i\n")
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_for_d(convert_bat):
    out, _ = convert_bat("@echo off\nfor /d %%d in (sub\\*) do echo %%d\n")
    assert "for d in sub/*/; do" in out


def test_for_empty_glob_protected_by_nullglob(convert_bat):
    out, _ = convert_bat("@echo off\nfor %%f in (*.nomatch) do echo %%f\n")
    assert "shopt -s nullglob" in out
    assert "for f in *.nomatch; do" in out


# ----------------------------------------------------------------------
# 子程序 / 控制流
# ----------------------------------------------------------------------
def test_subroutine_hoisted_with_naked_return(convert_bat):
    out, report = convert_bat(
        "@echo off\ncall :demo hello\ngoto :eof\n\n:demo\n    echo %1\n    goto :eof\n"
    )
    assert "label_demo() {" in out
    assert '    echo "$1"' in out
    # README 8.1 第 13 条：goto :eof 生成裸 return，保留上一条命令的退出码
    assert "\n    return\n" in out
    assert "label_demo hello" in out
    assert report.todo_count == 0
    # 函数体必须出现在调用之前
    assert out.index("label_demo() {") < out.index("label_demo hello")


def test_label_name_sanitized(convert_bat):
    out, _ = convert_bat(
        "@echo off\ncall :my-label\ngoto :eof\n\n:my-label\necho hi\ngoto :eof\n"
    )
    assert "label_my_label() {" in out
    assert "label_my_label" in out
    assert "my-label" not in out


def test_call_other_bat(convert_bat):
    out, report = convert_bat("@echo off\ncall other.bat arg1\n")
    assert 'bash "other.sh" arg1' in out
    assert report.warning_count == 1


def test_goto_eof_top_level(convert_bat):
    out, _ = convert_bat("@echo off\nif errorlevel 1 goto :eof\necho ok\ngoto :eof\n")
    assert out.count("exit 0") == 2


def test_goto_label_todo(convert_bat):
    out, report = convert_bat("@echo off\ngoto end\n:end\necho done\n")
    assert "# TODO: 手动检查: goto end" in out
    assert report.todo_count == 1


def test_exit_b(convert_bat):
    out, _ = convert_bat("@echo off\nexit /b 2\n")
    assert "exit 2" in out


def test_path_modifiers(convert_bat):
    out, _ = convert_bat("@echo off\necho %~dp0\necho %~nx0\necho %~f1\n")
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in out
    assert 'echo "${SCRIPT_DIR}/"' in out
    assert 'echo "$(basename "$0")"' in out
    assert 'echo "$(readlink -f "$1")"' in out


# ----------------------------------------------------------------------
# 管道 / 常见命令
# ----------------------------------------------------------------------
def test_pipeline_with_findstr(convert_bat):
    out, report = convert_bat("@echo off\ndir /b | findstr x\n")
    assert "ls -1 | grep x" in out
    assert report.warning_count == 1  # findstr 近似转换告警


def test_bash_n_on_complex_script(convert_bat, bash_check):
    text = (
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        "set SRC=.\\build\\release\n"
        "if not exist \"%DST%\" mkdir \"%DST%\"\n"
        "call :copy_files\n"
        "if errorlevel 2 exit /b 2\n"
        "for %%F in (\"%SRC%\\*.exe\") do (\n"
        "    echo 复制 %%~nxF\n"
        "    copy /y \"%%F\" \"%DST%\\\"\n"
        ")\n"
        "set /p NAME=请输入: \n"
        "pause\n"
        "goto :eof\n"
        "\n"
        ":copy_files\n"
        "    echo copy\n"
        "    goto :eof\n"
    )
    out, _ = convert_bat(text)
    bash_check(out)
