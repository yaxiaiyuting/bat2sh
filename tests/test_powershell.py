"""PowerShell 转换器的回归测试。

这些用例锁定当前实现的行为。标注「锁定当前行为」的断言描述的是已知不理想、
留给后续阶段（见 README 第 8 节）改进的输出；届时请同步更新对应用例。
"""

from __future__ import annotations

from bat2sh.core.powershell import PowerShellConverter
from bat2sh.core.types import SourceKind


# ----------------------------------------------------------------------
# 脚本头
# ----------------------------------------------------------------------
def test_header_contains_single_set_e(convert_ps):
    out, report = convert_ps('Write-Host "hi"\n')
    assert out.startswith("#!/usr/bin/env bash\n")
    assert out.count("set -euo pipefail") == 1
    assert report.kind is SourceKind.POWERSHELL


# ----------------------------------------------------------------------
# param() 与 attribute
# ----------------------------------------------------------------------
def test_param_attributes_stripped(convert_ps):
    out, report = convert_ps(
        "param(\n"
        "    [Parameter(Mandatory=$true)]\n"
        "    [string]$Name,\n"
        '    [ValidateSet("a","b")]\n'
        '    [string]$Mode = "a",\n'
        "    [int]$Count = 3\n"
        ")\n"
    )
    assert 'Name="$1"' in out
    assert 'Mode="${2:-a}"' in out
    assert 'Count="${3:-3}"' in out
    assert report.warning_count == 3
    assert report.todo_count == 0
    assert all("attribute 已剥离" in d.message for d in report.warnings[1:])


def test_cmdletbinding_ignored(convert_ps, bash_check):
    out, report = convert_ps(
        "[CmdletBinding()]\nparam(\n    [Parameter(Position=0)]\n    [string]$Path\n)\n"
    )
    assert "[CmdletBinding" not in out
    assert 'Path="$1"' in out
    assert report.error_count == 0
    assert report.todo_count == 0
    assert not any("未知命令" in d.message for d in report.warnings)
    assert any("attribute 已剥离" in d.message for d in report.warnings)
    bash_check(out)


def test_function_param_defaults_and_attrs(convert_ps):
    out, report = convert_ps(
        "function Test-X {\n"
        "    param(\n"
        "        [Parameter(Mandatory=$true)][string]$A,\n"
        "        [int]$B = 2\n"
        "    )\n"
        '    Write-Host "$A $B"\n'
        "}\n"
    )
    assert '    local A="$1"' in out
    assert '    local B="${2:-2}"' in out
    assert report.warning_count == 1


# ----------------------------------------------------------------------
# 命名参数重排
# ----------------------------------------------------------------------
def test_named_args_reordered(convert_ps):
    out, report = convert_ps(
        "function Show-Item {\n"
        "    param([string]$Name, [int]$Count)\n"
        '    Write-Host "$Name $Count"\n'
        "}\n"
        "Show-Item -Count 2 -Name abc\n"
    )
    assert "Show_Item() {" in out
    assert '    local Name="$1"' in out
    assert '    local Count="$2"' in out
    assert "Show_Item abc 2" in out
    assert report.warning_count == 1
    assert "命名参数已改写为位置参数" in report.warnings[0].message


def test_named_args_missing_middle_uses_placeholder(convert_ps):
    out, _ = convert_ps(
        "function F {\n"
        "    param([string]$A, [int]$B)\n"
        '    Write-Host "$A $B"\n'
        "}\n"
        "F -B 2\n"
    )
    assert "F '' 2" in out


def test_named_args_inline_value(convert_ps):
    out, _ = convert_ps(
        "function F {\n"
        "    param([string]$A)\n"
        '    Write-Host "$A"\n'
        "}\n"
        "F -A:abc\n"
    )
    assert "F abc" in out


def test_named_args_unknown_parameter_todo(convert_ps):
    out, report = convert_ps(
        "function F {\n"
        "    param([string]$A)\n"
        '    Write-Host "$A"\n'
        "}\n"
        "F -Z 1\n"
    )
    assert "# TODO: 手动检查: F -Z 1" in out
    assert report.todo_count == 1


def test_undefined_function_named_args_todo(convert_ps):
    # 锁定当前行为：未定义函数的命名参数调用会产生两条 TODO 诊断
    out, report = convert_ps("Some-Cmd -Path foo\n")
    assert "# TODO: 手动检查: Some-Cmd -Path foo" in out
    assert report.todo_count == 2


# ----------------------------------------------------------------------
# Join-Path
# ----------------------------------------------------------------------
def test_join_path_helper(convert_ps):
    out, report = convert_ps(
        '$base = "/tmp"\n$p = Join-Path $base "sub/file.txt"\nWrite-Host $p\n'
    )
    assert "__bat2sh_join_path() {" in out
    assert 'p=$(__bat2sh_join_path "${base}" "sub/file.txt")' in out
    assert report.warning_count == 1
    assert "Join-Path" in report.warnings[0].message


def test_join_path_helper_supports_backslash_absolute(convert_ps):
    out, _ = convert_ps('$p = Join-Path "a" "C:\\x"\n')
    assert "== [A-Za-z]:\\\\*" in out


def test_join_path_helper_absolute_child_resets(convert_ps, bash_run):
    out, _ = convert_ps('$p = Join-Path "a" "/abs"\n')
    start = out.index("__bat2sh_join_path() {")
    end = out.index("\n}\n", start) + 3
    script = (
        out[start:end]
        + '\n__bat2sh_join_path "a" "/abs"; echo\n'
        + '__bat2sh_join_path "a" "C:\\x"; echo\n'
    )
    proc = bash_run(script)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["/abs", "C:\\x"]


# ----------------------------------------------------------------------
# 环境变量
# ----------------------------------------------------------------------
def test_env_mapped_and_unlisted(convert_ps):
    out, report = convert_ps(
        "Write-Host $env:USERNAME\nWrite-Host $env:MY_UNLISTED_VAR\n"
    )
    assert 'echo "${USER}"' in out
    assert 'echo "${MY_UNLISTED_VAR}"' in out
    assert report.warning_count == 1
    assert "$env:MY_UNLISTED_VAR 未收录映射" in report.warnings[0].message


def test_braced_automatic_vars_map_fully(convert_ps):
    out, report = convert_ps(
        "Write-Host ${PSScriptRoot}/sub\n"
        "Write-Host ${PSCommandPath}\n"
        "Write-Host ${args}\n"
        "Write-Host ${PSScriptRoot}:$PSScriptRoot\n"
    )
    assert "echo ${SCRIPT_DIR}/sub" in out
    assert "echo ${BASH_SOURCE[0]}" in out
    assert 'echo "$@"' in out
    assert "echo ${SCRIPT_DIR}:${SCRIPT_DIR}" in out
    assert report.warning_count == 0


def test_braced_user_variable_kept(convert_ps):
    out, _ = convert_ps("$MyVar = 1\nWrite-Host ${MyVar}\n")
    assert 'echo "${MyVar}"' in out


def test_braced_env_variable_maps(convert_ps):
    out, report = convert_ps(
        "Write-Host ${env:USERNAME}\nWrite-Host ${env:MY_UNLISTED}\n"
    )
    assert 'echo "${USER}"' in out
    assert 'echo "${MY_UNLISTED}"' in out
    assert report.warning_count == 1


# ----------------------------------------------------------------------
# Get-Date（阶段 3 的 2.4-PS 目标）
# ----------------------------------------------------------------------
def test_get_date_format(convert_ps):
    out, report = convert_ps(
        '$d = Get-Date -Format "yyyy-MM-dd"\nGet-Date -Format "yyyy/MM/dd"\n'
    )
    assert "d=$(date +%Y-%m-%d)" in out
    assert "$(date +%Y/%m/%d)" in out
    assert report.warning_count == 2
    assert report.todo_count == 0


def test_get_date_format_more_tokens(convert_ps):
    out, report = convert_ps(
        'Get-Date -Format "yyyyMMdd"\n'
        '$t = Get-Date -Format "HH:mm:ss"\n'
        '$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"\n'
    )
    assert "$(date +%Y%m%d)" in out
    assert "t=$(date +%H:%M:%S)" in out
    assert "stamp=$(date +%Y-%m-%d %H:%M:%S)" in out
    assert report.warning_count == 3


def test_get_date_format_unknown_token_falls_back(convert_ps):
    out, report = convert_ps('Get-Date -Format "yyyy-MM-dd K"\n')
    assert "$(date)" in out
    assert "含不支持的 token" in report.warnings[0].message
    assert "date +" not in out


def test_get_date_format_unquoted_warns(convert_ps):
    out, report = convert_ps("Get-Date -Format yyyy\n")
    assert "$(date)" in out
    assert "建议加引号" in report.warnings[0].message


def test_get_date_plain(convert_ps):
    out, report = convert_ps("Get-Date\n")
    assert "$(date)" in out
    assert report.warning_count == 0


def test_lastexitcode_default_warn_replaces_line(convert_ps, bash_check):
    out, report = convert_ps("Write-Host $LASTEXITCODE\n")
    assert report.todo_count == 1
    assert report.todos[0].category == "errorlevel"
    assert "LASTEXITCODE" in report.todos[0].message
    assert "${LASTEXITCODE}" not in out
    assert "# TODO: 手动检查: Write-Host $LASTEXITCODE" in out
    assert report.warning_count == 0
    bash_check(out)


def test_lastexitcode_in_condition_default_warn(convert_ps, bash_check):
    out, report = convert_ps("if ($LASTEXITCODE -eq 0) { Write-Host 'ok' }\n")
    assert report.todo_count == 1
    assert report.todos[0].category == "errorlevel"
    assert "${LASTEXITCODE}" not in out
    assert "if [[ false ]]; then  # TODO: 手动检查 $LASTEXITCODE 条件" in out
    bash_check(out)


def test_lastexitcode_map_captures_once_and_reuses(convert_ps, bash_check):
    out, report = convert_ps(
        "$rc = $LASTEXITCODE\nWrite-Host $LASTEXITCODE\n", last_exit_code="map"
    )
    assert out.count("__bat2sh_rc=$?") == 1
    assert "${__bat2sh_rc}" in out
    assert "${LASTEXITCODE}" not in out
    assert "# 近似: $LASTEXITCODE" in out
    assert report.todo_count == 0
    assert report.warning_count == 1
    bash_check(out)


def test_lastexitcode_map_double_reference_same_variable(convert_ps, bash_check):
    out, report = convert_ps(
        "if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 2) { Write-Host 'ok' }\n",
        last_exit_code="map",
    )
    assert out.count("__bat2sh_rc=$?") == 1
    assert out.count("${__bat2sh_rc:-}") == 2
    assert "${LASTEXITCODE}" not in out
    bash_check(out)


def test_lastexitcode_map_runs_under_set_u(convert_ps, bash_run):
    out, _ = convert_ps(
        'Write-Host "start"\nWrite-Host $LASTEXITCODE\n', last_exit_code="map"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["start", "0"]


def test_lastexitcode_in_condition_map(convert_ps, bash_check):
    out, report = convert_ps(
        "if ($LASTEXITCODE -eq 0) { Write-Host 'ok' }\n", last_exit_code="map"
    )
    assert "__bat2sh_rc=$?" in out
    assert "[[ ${__bat2sh_rc:-} = 0 ]]" in out
    assert "${LASTEXITCODE}" not in out
    assert report.todo_count == 0
    bash_check(out)


def test_lastexitcode_key_is_not_camelcase():
    from bat2sh.core import rules

    assert "lastExitcode" not in rules.PS_AUTOMATIC_VARS


def test_question_mark_warns_semantics(convert_ps):
    out, report = convert_ps('if ($?) { Write-Host "ok" }\n')
    assert report.warning_count == 1
    assert report.warnings[0].category == "errorlevel"
    assert "$? 语义不同" in report.warnings[0].message
    assert "if [[ $? ]]; then" in out


def test_ps_date_token_mapping_unit():
    assert PowerShellConverter._ps_date_format("yyyy-MM-dd") == "%Y-%m-%d"
    assert PowerShellConverter._ps_date_format("HH:mm:ss") == "%H:%M:%S"
    assert (
        PowerShellConverter._ps_date_format("yyyy-MM-dd HH:mm:ss")
        == "%Y-%m-%d %H:%M:%S"
    )
    assert PowerShellConverter._ps_date_format("yyyyMMdd") == "%Y%m%d"


# ----------------------------------------------------------------------
# 对象管道（阶段 3 的 2.2 目标）
# ----------------------------------------------------------------------
def test_where_object_pipeline_eq(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Name -eq "a.txt" }\n'
    )
    assert "grep -F -- 'a.txt'" in out
    assert "# 近似: 按整行文本匹配，无法还原 $_.Name 属性语义" in out
    assert report.todo_count == 0
    assert report.warning_count == 1


def test_where_object_pipeline_ne(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Name -ne "skip" }\n'
    )
    assert "grep -Fv -- 'skip'" in out
    assert report.todo_count == 0


def test_where_object_unbraced_like(convert_ps):
    out, report = convert_ps('Get-ChildItem "/tmp" | Where-Object Name -like "*.log"\n')
    assert "grep -E -- '.*\\.log'" in out
    assert "# 近似: 按整行文本匹配，无法还原 $_.Name 属性语义" in out
    assert report.todo_count == 0


def test_where_object_whole_line_match(convert_ps):
    out, report = convert_ps(
        'Get-Content "/tmp/a.log" | Where-Object { $_ -match "ERROR" }\n'
    )
    assert "grep -E -- 'ERROR'" in out
    assert "无法还原 $_ 属性语义" in out
    assert report.todo_count == 0


def test_where_object_complex_todo(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Length -gt 10 -and $_.Name -like "*.log" }\n'
    )
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1


def test_where_object_null_value_todo(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Name -eq $null }\n'
    )
    assert report.todo_count == 1


def test_where_object_standalone_single_todo(convert_ps):
    out, report = convert_ps('Where-Object { $_.Name -eq "a" }\n')
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1
    assert "需要管道输入" in report.todos[0].message


def test_where_object_pipeline_bash_n(convert_ps, bash_check):
    out, _ = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Name -like "*.log" }\n'
    )
    bash_check(out)


# ----------------------------------------------------------------------
# here-string（阶段 3 的 2.3 目标）
# ----------------------------------------------------------------------
def test_here_string_literal_standalone(convert_ps, bash_check):
    out, report = convert_ps("@'\nno $expand here\n'@\n")
    assert "cat <<'__BAT2SH_EOF__'" in out
    assert "no $expand here" in out
    assert report.todo_count == 0
    assert report.warning_count == 0
    bash_check(out)


def test_here_string_interpolated_standalone(convert_ps, bash_check):
    out, report = convert_ps('@"\nhello $name\n"@\n')
    assert "cat <<__BAT2SH_EOF__" in out
    assert "hello ${name}" in out
    assert report.todo_count == 0
    assert report.warning_count == 1
    bash_check(out)


def test_here_string_assignment_literal(convert_ps, bash_check, bash_run):
    out, report = convert_ps("$text = @'\nline1\nline2\n'@\nWrite-Host $text\n")
    assert "text=$(cat <<'__BAT2SH_EOF__'" in out
    assert "\n)\n" in out
    assert report.warning_count == 1
    assert "去掉结尾换行" in report.warnings[0].message
    bash_check(out)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "line1\nline2\n"


def test_here_string_assignment_interpolated(convert_ps, bash_check, bash_run):
    out, report = convert_ps(
        '$name = "World"\n$text = @"\nhello $name\ncost $5\n"@\nWrite-Host $text\n'
    )
    assert "text=$(cat <<__BAT2SH_EOF__" in out
    assert "hello ${name}" in out
    assert "cost \\$5" in out
    assert report.warning_count == 2
    bash_check(out)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "hello World\ncost $5\n"


def test_here_string_inside_function_delimiter_at_column_zero(convert_ps, bash_check):
    out, report = convert_ps('function Show-Text {\n@"\nhello $name\n"@\n}\n')
    assert "    cat <<__BAT2SH_EOF__" in out
    assert "\n__BAT2SH_EOF__\n" in out
    assert report.warning_count == 1
    bash_check(out)


def test_here_string_delimiter_collision(convert_ps, bash_check):
    out, _ = convert_ps("@'\n__BAT2SH_EOF__\n'@\n")
    assert "cat <<'__BAT2SH_EOF___'" in out
    assert "\n__BAT2SH_EOF___\n" in out
    bash_check(out)


def test_here_string_unclosed_warns(convert_ps):
    out, report = convert_ps('@"\nhello\n')
    assert "# TODO: here-string 未闭合" in out
    assert report.warning_count == 1


# ----------------------------------------------------------------------
# try/catch/finally（阶段 3 的 2.5 目标）
# ----------------------------------------------------------------------
def test_try_catch_single_command(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n} catch {\n    Write-Warning "failed"\n}\n'
    )
    assert 'if ! ls -la "/tmp/a"; then' in out
    assert 'echo "failed" >&2' in out
    assert report.todo_count == 0
    assert report.warning_count == 1
    bash_check(out)


def test_try_catch_inline_full(convert_ps, bash_check):
    out, report = convert_ps('try { risky } catch { Write-Host "x" }\n')
    assert "if ! risky; then" in out
    assert 'echo "x"' in out
    assert out.rstrip().endswith("fi")
    assert report.todo_count == 0
    assert report.warning_count == 2
    bash_check(out)


def test_try_catch_multi_command_falls_back(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Write-Host "one"\n    Write-Host "two"\n'
        '} catch {\n    Write-Host "err"\n}\n'
    )
    assert "if true; then  # TODO: try/catch 未等价转换" in out
    assert "else  # TODO: catch 块" in out
    assert "多余的 }" not in out
    assert report.warning_count == 1
    bash_check(out)


def test_try_catch_typed_keeps_structure(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    risky\n} catch [System.IO.IOException] {\n    Write-Host "io"\n}\n'
    )
    assert "多余的 }" not in out
    assert "if true; then  # TODO: try/catch 未等价转换" in out
    assert any(
        "catch 类型 System.IO.IOException 已忽略" in d.message for d in report.warnings
    )
    assert report.warning_count == 3
    bash_check(out)


def test_try_finally_is_parallel_block(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n} finally {\n    Write-Host "done"\n}\n'
    )
    assert 'ls -la "/tmp/a"' in out
    assert "if true; then  # TODO: finally 块总是执行" in out
    assert 'echo "done"' in out
    assert out.index('ls -la "/tmp/a"') < out.index("if true; then  # TODO: finally")
    assert report.todo_count == 0
    assert report.warning_count == 1
    bash_check(out)


def test_try_catch_finally_combined(convert_ps, bash_check):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n} catch {\n    Write-Host "err"\n'
        '} finally {\n    Write-Host "done"\n}\n'
    )
    assert 'if ! ls -la "/tmp/a"; then' in out
    assert "if true; then  # TODO: finally 块总是执行" in out
    assert "多余的 }" not in out
    assert report.warning_count == 2
    bash_check(out)


def test_bare_try_executes_body(convert_ps, bash_check):
    out, report = convert_ps('try { Write-Host "just" }\nWrite-Host "after"\n')
    assert 'echo "just"' in out
    assert 'echo "after"' in out
    assert report.warning_count == 0
    bash_check(out)


def test_try_empty_body(convert_ps, bash_check):
    out, report = convert_ps('try {\n} catch {\n    Write-Host "err"\n}\n')
    assert "if true; then  # TODO: try/catch 未等价转换" in out
    assert "\n:\n" in out
    assert "else  # TODO: catch 块" in out
    assert report.todo_count == 0
    bash_check(out)


def test_try_empty_catch_inline(convert_ps, bash_check):
    out, report = convert_ps('try { Get-Item "/tmp/a" } catch { }\n')
    assert 'if ! ls -la "/tmp/a"; then' in out
    assert "\n:\nfi" in out
    assert report.todo_count == 0
    bash_check(out)


def test_try_empty_catch_block(convert_ps, bash_check):
    out, _ = convert_ps('try {\n    Get-Item "/tmp/a"\n} catch {\n}\n')
    assert 'if ! ls -la "/tmp/a"; then' in out
    assert "\n:\nfi" in out
    bash_check(out)


def test_try_empty_finally(convert_ps, bash_check):
    out, _ = convert_ps('try { Get-Item "/tmp/a" } finally { }\n')
    assert "if true; then  # TODO: finally 块总是执行" in out
    assert "\n:\nfi" in out
    bash_check(out)


def test_try_nested_falls_back_to_todo(convert_ps, bash_check):
    out, report = convert_ps(
        "try {\n"
        "    try {\n"
        '        Write-Host "inner"\n'
        "    } catch {\n"
        '        Write-Host "inner catch"\n'
        "    }\n"
        "} catch {\n"
        '    Write-Host "outer catch"\n'
        "}\n"
    )
    assert any("嵌套 try 无法自动转换" in d.message for d in report.todos)
    assert "# TODO: 手动检查: try {" in out
    assert 'echo "outer catch"' in out
    assert "多余的 }" not in out
    assert report.todo_count == 1
    bash_check(out)


# ----------------------------------------------------------------------
# Read-Host / 文件与命令转换
# ----------------------------------------------------------------------
def test_read_host_guarded_for_set_e(convert_ps):
    out, report = convert_ps('$x = Read-Host "请输入"\nWrite-Host $x\n')
    assert 'read -rp "请输入" x || true' in out
    assert report.warning_count == 0


def test_foreach_childitem_nullglob(convert_ps):
    out, report = convert_ps(
        'foreach ($f in Get-ChildItem "/tmp/*.txt") {\n    Write-Host $f\n}\n'
    )
    assert "shopt -s nullglob" in out
    assert 'for f in "/tmp"/*.txt; do' in out
    assert report.warning_count == 1


def test_get_content_tail(convert_ps):
    out, _ = convert_ps('Get-Content "/tmp/a.log" -Tail 5\n')
    assert 'tail -n 5 "/tmp/a.log"' in out


def test_pipeline_select_object_first(convert_ps):
    out, _ = convert_ps('Get-ChildItem "/tmp" | Select-Object -First 3\n')
    assert 'ls -la "/tmp" | head -n 3' in out


def test_pipeline_mixed_converts(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_ -match "log" } | Sort-Object\n'
    )
    assert "grep -E -- 'log' | sort" in out
    assert report.todo_count == 0
    assert report.warning_count == 2


# ----------------------------------------------------------------------
# 数组 / Test-Path 赋值（阶段 5/6 候选）
# ----------------------------------------------------------------------
def test_array_literal_and_inline_foreach(convert_ps):
    out, report = convert_ps(
        '$items = @("a", "b")\nforeach ($i in $items) { Write-Host $i }\n'
    )
    assert 'items=("a"  "b")' in out
    assert 'echo "${i}" }' not in out
    assert '    echo "${i}"\n' in out
    assert out.rstrip().endswith("done")
    assert report.todo_count == 0


def test_inline_foreach_with_multiple_statements(convert_ps):
    out, report = convert_ps(
        '$items = @("a")\nforeach ($i in $items) { Write-Host $i; Write-Host $i }\n'
    )
    assert out.count('echo "${i}"') == 2
    assert out.rstrip().endswith("done")
    assert report.todo_count == 0


def test_test_path_assign_current_behavior(convert_ps):
    # 锁定当前行为：Test-Path 赋值生成 $(-e ...)，运行时无法按预期工作（后续阶段候选）
    out, _ = convert_ps('$ok = Test-Path "/tmp/a"\nWrite-Host $ok\n')
    assert 'ok=$(-e "/tmp/a" && echo true || echo false)' in out


# ----------------------------------------------------------------------
# 严格模式与错误处理
# ----------------------------------------------------------------------
def test_error_action_preference_uses_header_strict(convert_ps):
    out, report = convert_ps('$ErrorActionPreference = "Stop"\nWrite-Host "x"\n')
    assert '（脚本头已启用严格模式）' in out
    assert out.count("set -euo pipefail") == 1
    assert report.warning_count == 1


def test_error_action_preference_emits_set_e_when_strict_off(convert_ps):
    out, report = convert_ps(
        '$ErrorActionPreference = "Stop"\nWrite-Host "x"\n', strict_mode=False
    )
    assert "set -e\n" in out
    assert report.warning_count == 1
    assert "已转换为 set -e" in report.warnings[0].message


def test_throw_return_exit(convert_ps):
    out, report = convert_ps('function F {\n    return 3\n}\nexit 1\nthrow "boom"\n')
    assert "    return 3" in out
    assert "exit 1" in out
    assert 'echo "boom" >&2; exit 1' in out
    assert report.warning_count == 1


def test_like_condition(convert_ps):
    out, _ = convert_ps('if ($name -like "*.log") {\n    Write-Host "log"\n}\n')
    assert "if [[ ${name:-} == *.log ]]; then" in out


def test_math_and_loops(convert_ps):
    out, _ = convert_ps(
        "$x = $x + 1\n"
        "$i = 0\n"
        "while ($i -lt 3) {\n    $i = $i + 1\n}\n"
        "for ($j = 0; $j -lt 2; $j++) {\n    Write-Host $j\n}\n"
        "do {\n    Write-Host \"x\"\n} while ($i -lt 3)\n"
    )
    assert "x=$(( ${x:-0} + 1 ))" in out
    assert "while [[ ${i:-} -lt 3 ]]; do" in out
    assert "for (( j = 0; j < 2; j++ )); do" in out
    assert "while true; do" in out


def test_bash_n_on_sample(convert_ps, bash_check):
    text = (
        "param(\n"
        "    [string]$Source = \"C:\\Data\"\n"
        ")\n"
        "$files = Get-ChildItem \"$Source\\*.txt\"\n"
        "$count = 0\n"
        "foreach ($file in $files) {\n"
        "    Write-Host \"处理 $file\"\n"
        "    $count = $count + 1\n"
        "}\n"
        "if ($count -gt 0) {\n"
        "    Write-Host \"共 $count 个\"\n"
        "} else {\n"
        "    Write-Warning \"没有文件\"\n"
        "}\n"
        "exit 0\n"
    )
    out, _ = convert_ps(text)
    bash_check(out)


# ----------------------------------------------------------------------
# 复杂条件占位（$_ / 对象属性访问）：不再吞掉 ; then
# ----------------------------------------------------------------------
def test_complex_condition_keeps_then_visible(convert_ps, bash_check):
    out, report = convert_ps('if ($x.Length -gt 0) {\n    Write-Host "a"\n}\n')
    assert "if false; then" in out
    assert "0 -eq 1  # TODO" not in out
    assert "复杂条件" in report.todos[0].message
    assert report.todo_count == 1
    assert not any(
        "; then" in line or "; do" in line
        for line in out.splitlines()
        if line.lstrip().startswith("#")
    )
    bash_check(out)


def test_complex_condition_while_placeholder(convert_ps, bash_check):
    out, report = convert_ps('while ($line.Length -gt 0) {\n    $line = "x"\n}\n')
    assert "while false; do" in out
    assert report.todo_count == 1
    bash_check(out)


def test_complex_condition_until_placeholder_never_loops(convert_ps, bash_check, bash_run):
    out, report = convert_ps("until ($idx.Prop) {\n    $idx = 0\n}\n")
    assert "while ! true; do" in out
    assert report.todo_count == 1
    bash_check(out)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr


def test_complex_condition_dollar_underscore(convert_ps, bash_check):
    out, report = convert_ps('if ($_.Count -gt 0) {\n    Write-Host "a"\n}\n')
    assert "if false; then" in out
    assert report.todo_count == 1
    bash_check(out)


def test_complex_condition_elif_structure_kept(convert_ps, bash_check):
    out, report = convert_ps(
        "if ($a -gt 1) {\n"
        '    Write-Host "a"\n'
        "} elseif ($b.Prop) {\n"
        '    Write-Host "b"\n'
        "}\n"
    )
    assert "elif false; then" in out
    assert "elif 0 -eq 1" not in out
    assert report.todo_count == 1
    bash_check(out)


# ----------------------------------------------------------------------
# 属性声明与类型注解（整行忽略 / 去注解，不做类型转换）
# ----------------------------------------------------------------------
def test_attribute_only_line_ignored(convert_ps, bash_check):
    out, report = convert_ps('[CmdletBinding()]\nWrite-Host "hi"\n')
    assert "[CmdletBinding" not in out
    assert 'echo "hi"' in out
    assert report.error_count == 0
    assert report.todo_count == 0
    bash_check(out)


def test_attribute_multiline_ignored(convert_ps, bash_check):
    out, report = convert_ps(
        "[CmdletBinding(\n"
        "    SupportsShouldProcess = $true,\n"
        '    ConfirmImpact = "High"\n'
        ")]\n"
        'Write-Host "hi"\n'
    )
    assert "CmdletBinding" not in out
    assert "SupportsShouldProcess" not in out
    assert 'echo "hi"' in out
    assert report.todo_count == 0
    bash_check(out)


def test_validate_alias_outputtype_ignored(convert_ps):
    out, report = convert_ps(
        "[ValidateSet('a', 'b')]\n[Alias('x')]\n[OutputType([string])]\n"
    )
    assert "ValidateSet" not in out
    assert "Alias" not in out
    assert "OutputType" not in out
    assert report.todo_count == 0


def test_type_annotation_stripped_known_types(convert_ps, bash_check):
    out, _ = convert_ps('[string]$name = "foo"\n[int]$count = 5\n')
    assert 'name="foo"' in out
    assert "count=5" in out
    bash_check(out)


def test_type_annotation_bool_and_array(convert_ps):
    out, _ = convert_ps("[bool]$flag = $true\n[array]$arr = @()\n")
    assert "flag=true" in out
    assert "arr=()" in out


def test_type_annotation_alone_on_line_ignored(convert_ps):
    out, report = convert_ps('[string]\n$name = "foo"\n')
    assert "[string]" not in out
    assert 'name="foo"' in out
    assert report.todo_count == 0


def test_unknown_type_annotation_todo(convert_ps, bash_check):
    out, report = convert_ps("[UnknownType]$x = 1\n")
    assert report.todo_count == 1
    assert "不在支持列表" in report.todos[0].message
    assert not any(
        "[UnknownType]" in line and not line.lstrip().startswith("#")
        for line in out.splitlines()
    )
    bash_check(out)


def test_type_cast_statement_todo(convert_ps, bash_check):
    out, report = convert_ps('[int]"5"\n')
    assert report.todo_count == 1
    assert "类型转换" in report.todos[0].message
    assert not any(
        line.lstrip().startswith("[") for line in out.splitlines()
    )
    bash_check(out)


def test_dotnet_static_call_still_objects_todo(convert_ps, bash_check):
    out, report = convert_ps("$l = @()\n[System.Threading.Monitor]::Enter($l)\n")
    assert any(
        ".NET" in d.message and d.category == "objects" for d in report.todos
    )
    assert "::Enter" in out
    assert not any(
        "Monitor" in line and not line.lstrip().startswith("#")
        for line in out.splitlines()
    )
    bash_check(out)


# ----------------------------------------------------------------------
# 算术误报与行尾管道续行
# ----------------------------------------------------------------------
def test_cmdlet_rhs_not_treated_as_arithmetic(convert_ps, bash_check):
    out, report = convert_ps("$x = Get-WmiObject -Class Win32_Foo -ComputerName $C\n")
    assert "$((" not in out
    assert any("无法确定右值类型" in d.message for d in report.warnings)
    bash_check(out)


def test_trailing_pipe_joins_next_line(convert_ps, bash_check):
    out, report = convert_ps(
        "$x = Get-WmiObject -Class Win32_Foo -ComputerName $C |\n"
        "    Where-Object { $_.A -eq 1 }\n"
    )
    assert "$((" not in out
    assert "$( Get-WmiObject" not in out
    assert report.todo_count >= 1
    bash_check(out)


def test_legit_arithmetic_unchanged(convert_ps):
    out, _ = convert_ps("$x = $a + 1 * 2\n$total = $total - 1\n")
    assert "x=$(( ${a:-0} + 1 * 2 ))" in out
    assert "total=$(( ${total:-0} - 1 ))" in out


def test_trailing_pipe_in_here_string_not_joined(convert_ps, bash_check):
    out, _ = convert_ps('$t = @"\na |\nb\n"@\nWrite-Host $t\n')
    assert "a |" in out
    assert "b" in out
    bash_check(out)


def test_trailing_pipe_in_comment_not_joined(convert_ps):
    out, _ = convert_ps("# 注释 |\n$y = 1\n")
    assert "# 注释 |" in out
    assert "y=1" in out


def test_trailing_pipe_at_eof_records_todo(convert_ps, bash_check):
    out, report = convert_ps("$x = Get-Process |\n")
    assert report.todo_count >= 1
    bash_check(out)
