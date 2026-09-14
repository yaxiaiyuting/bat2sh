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
# 注释（rem）
# ----------------------------------------------------------------------
def test_rem_line_becomes_bash_comment(convert_bat):
    out, report = convert_bat("@echo off\nrem 这是一行注释\necho hi\n")
    assert "# 这是一行注释" in out
    assert report.warning_count == 0


def test_rem_is_case_insensitive(convert_bat):
    out, report = convert_bat("@echo off\nREM 大写注释\n")
    assert "# 大写注释" in out
    assert report.warning_count == 0


def test_rem_without_text_becomes_empty_comment(convert_bat):
    out, report = convert_bat("@echo off\nrem\nrem   \n")
    assert out.rstrip().endswith("#\n#")
    assert report.warning_count == 0


def test_rem_inside_if_block(convert_bat):
    out, report = convert_bat("@echo off\nif 1==1 (\n    rem 块内注释\n    echo hi\n)\n")
    assert "# 块内注释" in out
    assert report.warning_count == 0


def test_rem_after_ampersand_is_not_unknown_command(convert_bat):
    out, report = convert_bat("@echo off\necho hi & rem tail\n")
    assert "# tail" in out
    assert not any("未知命令" in d.message for d in report.warnings)


def test_rem_inside_for_f_source_becomes_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%a in ('rem comment') do echo %%a\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert not any("未知命令" in d.message for d in report.warnings)


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


def test_set_a_quoted_expression(convert_bat):
    out, report = convert_bat('@echo off\nset /a "COMPLEX=(10+20)*3/2-5"\n')
    assert "COMPLEX=$(( (10+20)*3/2-5 ))" in out
    assert "_a__COMPLEX" not in out
    assert report.warning_count == 0


def test_set_a_quoted_with_spaces(convert_bat):
    out, report = convert_bat('@echo off\nset /a "TOTAL = 2 + 3"\n')
    assert "TOTAL=$(( 2 + 3 ))" in out
    assert report.warning_count == 0


def test_set_a_quoted_runs_in_bash(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset /a "COMPLEX=(10+20)*3/2-5"\necho %COMPLEX%\n')
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "40\n"


def test_set_a_without_assignment_prints_value(convert_bat):
    out, report = convert_bat("@echo off\nset /a TOTAL\n")
    assert "echo $(( TOTAL ))" in out
    assert report.warning_count == 0


def test_set_p_read_guarded_for_set_e(convert_bat):
    out, report = convert_bat("@echo off\nset /p NAME=请输入名字: \n")
    assert 'read -rp "请输入名字:" NAME || true' in out
    assert report.warning_count == 0


def test_set_p_read_without_guard_when_strict_off(convert_bat):
    out, _ = convert_bat("@echo off\nset /p V=p\n", strict_mode=False)
    assert 'read -rp "p" V' in out
    assert "|| true" not in out


# ----------------------------------------------------------------------
# %% 间接引用 / 转义百分号
# ----------------------------------------------------------------------
def test_escaped_percent_pair_is_literal(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho 百分号: %%PATH%%\n")
    assert 'echo "百分号: %PATH%"' in out
    assert any("检测到转义百分号 %%" in d.message for d in report.warnings)
    assert not any("循环变量" in d.message for d in report.warnings)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "百分号: %PATH%\n"


def test_triple_percent_indirect_maps_to_bang(convert_bat):
    out, report = convert_bat('@echo off\ncall set "INDIRECT=%%%VAR_NAME%%%"\n')
    assert 'INDIRECT="${!VAR_NAME}"' in out
    assert not any("循环变量" in d.message for d in report.warnings)


def test_triple_percent_single_letter_maps_to_bang(convert_bat):
    out, report = convert_bat('@echo off\ncall set "RESULT=%%%A%%%"\n')
    assert 'RESULT="${!A}"' in out
    assert not any("循环变量" in d.message for d in report.warnings)


def test_for_loop_variable_not_treated_as_escaped_percent(convert_bat):
    out, report = convert_bat("@echo off\nfor %%i in (*.txt) do echo %%i\n")
    assert 'echo "${i}"' in out
    assert not any("转义百分号" in d.message for d in report.warnings)


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
    assert 'if [ "${A:-}" = "B" ]; then' in out


@pytest.mark.parametrize(
    "op,bash_op",
    [
        ("gtr", "-gt"),
        ("lss", "-lt"),
        ("equ", "-eq"),
        ("neq", "-ne"),
        ("geq", "-ge"),
        ("leq", "-le"),
    ],
)
def test_if_numeric_compare_operators(convert_bat, bash_check, op, bash_op):
    out, report = convert_bat(
        f"@echo off\nset /a NUM1=10\nset /a NUM2=3\nif %NUM1% {op} %NUM2% echo yes\n"
    )
    assert f'if [ "${{NUM1}}" {bash_op} "${{NUM2}}" ]; then' in out
    assert not any("未知命令" in d.message for d in report.warnings)
    assert report.todo_count == 0
    bash_check(out)


def test_if_numeric_compare_runs_in_bash(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\nset /a NUM1=10\nset /a NUM2=3\nif %NUM1% gtr %NUM2% echo 大于\n"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "大于\n"


def test_if_numeric_compare_with_paren_blocks(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nset /a NUM1=10\nset /a NUM2=3\n"
        "if %NUM1% lss %NUM2% (echo 小于) else (echo 不小于)\n"
    )
    assert 'if [ "${NUM1}" -lt "${NUM2}" ]; then' in out
    assert 'echo "小于"' in out
    assert 'echo "不小于"' in out
    assert report.todo_count == 0
    bash_check(out)


def test_if_string_compare_with_spaces_stays_string(convert_bat):
    out, _ = convert_bat('@echo off\nif "%MY_VAR%"=="Hello World" echo 相等\n')
    assert 'if [ "${MY_VAR:-}" = "Hello World" ]; then' in out


def test_if_equ_quoted_operands_use_string_compare(convert_bat, bash_run):
    out, report = convert_bat('@echo off\nif "%STR1%" equ "%STR2%" echo same\n')
    assert 'if [ "${STR1:-}" = "${STR2:-}" ]; then' in out
    assert report.warning_count == 0
    proc = bash_run("STR1=abc STR2=abc\n" + out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "same\n"
    assert proc.stderr == ""


def test_if_equ_quoted_strings_differ_no_runtime_error(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nif "%STR1%" equ "%STR2%" echo same\n')
    proc = bash_run("STR1=abc STR2=xyz\n" + out)
    assert proc.stdout == ""
    assert "整数" not in proc.stderr
    assert "integer expression" not in proc.stderr


def test_if_equ_unquoted_variables_stay_numeric(convert_bat):
    out, _ = convert_bat("@echo off\nif %N1% equ %N2% echo same\n")
    assert 'if [ "${N1:-}" -eq "${N2:-}" ]; then' in out


def test_if_neq_unquoted_variables_stay_numeric(convert_bat):
    out, _ = convert_bat("@echo off\nif %X% neq %Y% echo diff\n")
    assert 'if [ "${X:-}" -ne "${Y:-}" ]; then' in out


def test_if_equ_numeric_literals_use_numeric_compare(convert_bat):
    out, _ = convert_bat("@echo off\nif 1 equ 1 echo same\n")
    assert "if [ 1 -eq 1 ]; then" in out


def test_if_equ_bare_word_operands_use_string_compare(convert_bat):
    out, _ = convert_bat("@echo off\nif abc equ abc echo same\n")
    assert 'if [ "abc" = "abc" ]; then' in out


def test_if_neq_quoted_operands_use_string_compare(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nif "%S1%" neq "%S2%" echo diff\n')
    assert 'if [ "${S1:-}" != "${S2:-}" ]; then' in out
    proc = bash_run("S1=abc S2=xyz\n" + out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "diff\n"
    assert proc.stderr == ""


def test_if_exist_glob_uses_compgen(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nif exist *.log echo found\n")
    assert 'if compgen -G "*.log" > /dev/null; then' in out
    assert report.warning_count == 0
    bash_check(out)


def test_if_exist_glob_with_directory_prefix(convert_bat, bash_run, tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "a.log").write_text("x\n", encoding="utf-8")
    out, report = convert_bat("@echo off\nif exist build\\*.log echo found\n")
    assert 'compgen -G "build/*.log"' in out
    assert report.warning_count == 0
    proc = bash_run(f"cd {tmp_path}\n" + out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "found\n"


def test_if_not_exist_glob_negates_compgen(convert_bat, bash_run, tmp_path):
    out, report = convert_bat("@echo off\nif not exist *.log echo none\n")
    assert 'if ! compgen -G "*.log" > /dev/null; then' in out
    assert report.warning_count == 0
    proc = bash_run(f"cd {tmp_path}\n" + out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "none\n"


def test_if_exist_quoted_glob_stays_literal(convert_bat):
    out, report = convert_bat('@echo off\nif exist "*.log" echo yes\n')
    assert '[ -e "*.log" ]' in out
    assert "compgen" not in out
    assert report.warning_count == 0


def test_if_exist_glob_unsafe_pattern_falls_back(convert_bat):
    out, report = convert_bat("@echo off\nif exist $(x)*.log echo yes\n")
    assert "compgen" not in out
    assert "[ -e " in out
    assert report.warning_count == 1
    assert report.warnings[0].category == "glob"


def test_if_exist_plain_no_glob_warning(convert_bat):
    out, report = convert_bat("@echo off\nif exist config.ini echo yes\n")
    assert report.warning_count == 0


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
def test_pause_redirect_binds_to_read(convert_bat):
    out, _ = convert_bat("@echo off\npause >nul\n")
    assert 'read -rp "Press Enter to continue..." >/dev/null || true' in out


def test_set_p_redirect_binds_to_read(convert_bat):
    out, _ = convert_bat("@echo off\nset /p X=prompt >log.txt\n")
    assert 'read -rp "prompt" X >log.txt || true' in out


def test_redirect_order_preserved(convert_bat):
    out, report = convert_bat("@echo off\nfoo > out.txt 2>&1\n")
    assert "foo >out.txt 2>&1" in out
    assert report.warning_count == 1  # 未知命令 foo


# ----------------------------------------------------------------------
# 括号块 ( ... )
# ----------------------------------------------------------------------
def test_paren_block_with_redirect(convert_bat, bash_run, tmp_path):
    out, report = convert_bat("@echo off\n(echo 输出到文件) > redirect.txt\n")
    assert '{ echo "输出到文件"; } >redirect.txt' in out
    assert report.warning_count == 0
    proc = bash_run(f"cd {tmp_path}\n" + out + "\ncat redirect.txt")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "输出到文件\n"


def test_paren_block_multiline(convert_bat, bash_check):
    out, report = convert_bat("@echo off\n(\n    echo a\n    echo b\n) > out.txt\n")
    assert "\n{\n" in out
    assert "} >out.txt" in out
    assert report.todo_count == 0
    bash_check(out)


def test_paren_block_multiple_commands(convert_bat, bash_run, tmp_path):
    out, report = convert_bat("@echo off\n(echo a & echo b) > out.txt\n")
    assert '{ echo "a"; echo "b"; } >out.txt' in out
    assert report.warning_count == 0
    proc = bash_run(f"cd {tmp_path}\n" + out + "\ncat out.txt")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "a\nb\n"


def test_paren_block_with_pipe(convert_bat, bash_run):
    out, report = convert_bat("@echo off\n(echo a & echo b) | grep b\n")
    assert '{ echo "a"; echo "b"; } | grep b' in out
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "b\n"


def test_paren_block_multiline_with_pipe(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\n(\n    echo a\n    echo b\n) | grep b\n")
    assert "} | grep b" in out
    bash_check(out)


def test_paren_block_inline_open_with_later_close(convert_bat, bash_check):
    out, report = convert_bat("@echo off\n(echo a\n    echo b) > out.txt\n")
    assert "\n{\n" in out
    assert "} >out.txt" in out
    assert report.todo_count == 0
    bash_check(out)


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


def test_echo_dot_outputs_blank_line(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho.\necho hi\n")
    assert "echo." not in out
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "\nhi\n"


def test_echo_open_paren_outputs_blank_line(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho(\necho hi\n")
    assert "echo(" not in out
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "\nhi\n"


def test_echo_dot_with_text_echoes_text(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho.hello world\n")
    assert 'echo "hello world"' in out
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "hello world\n"


def test_echo_dot_with_redirect_binds_to_echo(convert_bat):
    out, report = convert_bat("@echo off\necho. > blank.txt\n")
    assert "echo >blank.txt" in out
    assert report.warning_count == 0


# ----------------------------------------------------------------------
# ^ 转义
# ----------------------------------------------------------------------
def test_caret_escaped_special_chars_in_echo(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho 特殊字符: ^& ^| ^< ^> ^^ %%\n")
    assert report.warning_count == 0
    assert 'echo "特殊字符: & | < > ^ %"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "特殊字符: & | < > ^ %\n"


def test_caret_escaped_ampersand_runs_in_bash(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho a^&b\n")
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "a&b\n"


def test_caret_escaped_exclamation(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho 感叹号: ^!\n")
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "感叹号: !\n"


def test_caret_inside_quotes_stays_literal(convert_bat):
    out, report = convert_bat('@echo off\necho "a^&b"\n')
    assert 'echo "a^&b"' in out
    assert report.warning_count == 0


def test_echo_escapes_literal_dollar(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho 价格 $100\n")
    assert 'echo "价格 \\$100"' in out
    assert report.warning_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "价格 $100\n"


def test_echo_keeps_generated_variable_expansion(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\nset NAME=World\necho 你好 %NAME%\n")
    assert 'echo "你好 ${NAME}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "你好 World\n"


def test_echo_escapes_user_braced_and_command_dollar(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\necho ${HOME}\necho $(date)\n")
    assert 'echo "\\${HOME}"' in out
    assert 'echo "\\$(date)"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "${HOME}\n$(date)\n"


def test_for_nested_inner_loop_quotes_variable(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor %%a in (*.txt) do (\n    for %%b in (%%a) do (\n"
        "        echo %%b\n    )\n)\n"
    )
    assert "for a in *.txt; do" in out
    assert 'for b in "${a}"; do' in out
    assert any("%%a 变量集合已加引号" in d.message for d in report.warnings)


def test_for_set_variable_quoted_with_warning(convert_bat):
    out, report = convert_bat("@echo off\nfor %%f in (%LIST%) do echo %%f\n")
    assert 'for f in "${LIST:-}"; do' in out
    assert any("%LIST% 变量集合已加引号" in d.message for d in report.warnings)


def test_for_set_argument_quoted_with_warning(convert_bat):
    out, report = convert_bat("@echo off\nfor %%f in (%1) do echo %%f\n")
    assert 'for f in "${1:-}"; do' in out
    assert any("%1 变量集合已加引号" in d.message for d in report.warnings)


def test_for_set_variable_unquoted_when_quote_variables_off(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor %%f in (%LIST%) do echo %%f\n", quote_variables=False
    )
    assert "for f in ${LIST:-}; do" in out
    assert not any("变量集合已加引号" in d.message for d in report.warnings)


def test_for_f_tokens_star_simple(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%i in ('dir /b') do echo %%i\n"
    )
    assert "while IFS= read -r i; do" in out
    assert 'echo "${i}"' in out
    assert "done < <(ls -1)" in out
    assert report.todo_count == 0
    assert report.warning_count == 0


def test_for_f_without_options_reads_first_token(convert_bat):
    out, report = convert_bat("@echo off\nfor /f %%i in ('dir /b') do echo %%i\n")
    assert "while read -r i _; do" in out
    assert '[ -z "$i" ] && continue' in out
    assert report.warning_count == 0
    assert report.todo_count == 0


def test_for_f_multiline_body(convert_bat, bash_check):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%i in ('dir /b') do (\n"
        "    echo 文件 %%i\n    copy \"%%i\" \"%%i.bak\"\n)\n"
    )
    assert "while IFS= read -r i; do" in out
    assert "done < <(ls -1)" in out
    assert 'cp "${i}" "${i}.bak"' in out
    assert report.todo_count == 0
    bash_check(out)


@pytest.mark.parametrize(
    "line",
    [
        "for /f \"usebackq\" %%i in (`dir /b`) do echo %%i",
        "for /f \"foo\" %%i in ('dir /b') do echo %%i",
    ],
)
def test_for_f_complex_options_todo(convert_bat, line):
    out, report = convert_bat("@echo off\n" + line + "\n")
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_for_f_string_source_todo(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%i in (\"a b c\") do echo %%i\n"
    )
    assert report.todo_count == 1
    assert "字符串/反引号" in report.todos[0].message


def test_for_f_inner_command_todo_falls_back(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"tokens=*\" %%i in ('foo.exe') do echo %%i\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_for_f_todo_comments_multiline_body(convert_bat):
    out, report = convert_bat(
        "@echo off\nfor /f \"usebackq\" %%i in (`dir /b`) do (\n    echo %%i\n)\n"
    )
    assert "# TODO: 手动检查: for /f" in out
    assert "# echo %%i" in out
    assert report.todo_count == 1


def test_for_r_todo(convert_bat):
    out, report = convert_bat("@echo off\nfor /r %%i in (*.txt) do echo %%i\n")
    assert "# TODO: 手动检查: for /r" in out
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
    assert '    echo "${1:-}"' in out
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
    assert 'echo "$(readlink -f "${1:-}")"' in out


# ----------------------------------------------------------------------
# 管道 / 常见命令
# ----------------------------------------------------------------------
def test_pipeline_with_findstr(convert_bat):
    out, report = convert_bat("@echo off\ndir /b | findstr x\n")
    assert "ls -1 | grep x" in out
    assert report.warning_count == 1  # findstr 近似转换告警


def test_more_plus_n_warning_wording(convert_bat):
    out, report = convert_bat("@echo off\nsort a.txt | more +1\n")
    messages = [d.message for d in report.warnings]
    assert any(
        "more +1 参数语义不同（Linux 版无 +1 跳过首行），请核对" == m for m in messages
    )
    assert not any("未知命令 'more'" in m for m in messages)


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


# ----------------------------------------------------------------------
# & 链内 exit（崩溃修复）
# ----------------------------------------------------------------------
def test_exit_in_sequential_chain(convert_bat, bash_check, bash_run):
    out, report = convert_bat('echo a & exit /b 1\n')
    assert 'echo "a"' in out
    assert "exit 1" in out
    assert report.error_count == 0
    bash_check(out)
    proc = bash_run(out)
    assert proc.returncode == 1
    assert proc.stdout.strip() == "a"


def test_exit_bare_in_sequential_chain(convert_bat, bash_check):
    out, _ = convert_bat("echo a & exit\n")
    assert "exit $?" in out
    bash_check(out)


def test_exit_in_function_chain_returns(convert_bat, bash_check):
    out, _ = convert_bat("call :foo\ngoto :eof\n:foo\necho x & exit /b 3\n")
    assert "return 3" in out
    bash_check(out)


def test_no_exit_chain_regression(convert_bat, bash_check):
    out, _ = convert_bat("echo a & echo b\n")
    assert 'echo "a"' in out
    assert 'echo "b"' in out
    bash_check(out)


# ----------------------------------------------------------------------
# @echo off / setlocal 链
# ----------------------------------------------------------------------
def test_chained_echo_off_and_delayed_expansion(convert_bat, bash_check, bash_run):
    out, _ = convert_bat(
        "@echo off&setlocal enabledelayedexpansion\nset x=1\necho !x!\n"
    )
    assert '"off"' not in out
    assert 'x="1"' in out
    assert 'echo "${x}"' in out
    bash_check(out)
    assert bash_run(out).stdout.strip() == "1"


def test_echo_off_silent_mid_chain(convert_bat, bash_check):
    out, _ = convert_bat("echo hi & echo off & echo done\n")
    assert '"off"' not in out
    assert 'echo "hi"' in out
    assert 'echo "done"' in out
    bash_check(out)


def test_echo_on_mid_chain_comment(convert_bat, bash_check):
    out, _ = convert_bat("echo off & echo on & echo hi\n")
    assert "echo on 在 bash 中无对应行为" in out
    assert '"off"' not in out
    bash_check(out)


def test_echo_offset_not_toggle(convert_bat):
    out, _ = convert_bat("echo offset\n")
    assert 'echo "offset"' in out


# ----------------------------------------------------------------------
# !var! 延迟展开（未启用时不得静默泄漏）
# ----------------------------------------------------------------------
def test_bang_var_without_delayed_expansion_todo(convert_bat, bash_check):
    out, report = convert_bat("set x=1\necho !x!\n")
    assert "# TODO" in out
    assert any("延迟展开" in d.message for d in report.todos)
    bash_check(out)


def test_bang_var_with_delayed_expansion_converts(convert_bat, bash_check):
    out, report = convert_bat(
        "setlocal enabledelayedexpansion\nset x=1\necho !x!\n"
    )
    assert 'echo "${x}"' in out
    assert report.todo_count == 0
    bash_check(out)


def test_bang_indirect_with_delayed_expansion(convert_bat):
    out, _ = convert_bat(
        "setlocal enabledelayedexpansion\nset NAME=x\nset x=5\necho !%NAME%!\n"
    )
    assert 'echo "${!NAME}"' in out


def test_literal_bang_text_no_todo(convert_bat):
    out, report = convert_bat('echo "Hello World"\necho done!\n')
    assert report.todo_count == 0


# ----------------------------------------------------------------------
# dir /b 通配（引号通配修复）
# ----------------------------------------------------------------------
def test_dir_b_glob_uses_compgen(convert_bat, bash_check):
    out, _ = convert_bat("dir /b *.txt\n")
    assert 'compgen -G "*.txt"' in out
    bash_check(out)


def test_for_f_dir_b_glob_uses_compgen(convert_bat, bash_check):
    out, _ = convert_bat("for /f \"delims=\" %%i in ('dir /b *.txt') do echo %%i\n")
    assert 'done < <(compgen -G "*.txt" || true)' in out
    bash_check(out)


def test_dir_b_glob_runtime_with_spaces(convert_bat, tmp_path, bash_run):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "my file.txt").write_text("y")
    (tmp_path / "b.md").write_text("z")
    out, _ = convert_bat("dir /b *.txt\n")
    proc = bash_run(f'cd "{tmp_path}"\n' + out)
    assert proc.returncode == 0, proc.stderr
    assert set(proc.stdout.splitlines()) == {"a.txt", "my file.txt"}


def test_dir_b_glob_no_match_runtime(convert_bat, tmp_path, bash_run):
    out, _ = convert_bat("dir /b *.nope\n")
    proc = bash_run(f'cd "{tmp_path}"\n' + out)
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_del_glob_no_match_runtime_safe(convert_bat, tmp_path, bash_run):
    out, _ = convert_bat("del /q *.tmp\n")
    assert "rm -f *.tmp" in out
    proc = bash_run(f'cd "{tmp_path}"\n' + out)
    assert proc.returncode == 0


def test_del_dir_plus_glob_quotes_dir_only(convert_bat, bash_check):
    out, _ = convert_bat("del /q C:\\sub\\*.log\n")
    assert 'rm -f "C:/sub"/*.log' in out
    bash_check(out)


def test_non_glob_paths_stay_quoted(convert_bat):
    out, _ = convert_bat("dir /b sub\ncopy a.txt b.txt\ndel /q file.txt\n")
    assert 'ls -1 "sub"' in out
    assert '"a.txt"' in out and '"b.txt"' in out
    assert 'rm -f "file.txt"' in out
