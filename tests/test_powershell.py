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


def test_cmdletbinding_current_behavior(convert_ps):
    # 锁定当前行为：[CmdletBinding()] 未被剥离，原样保留并产生「未知命令」警告
    out, report = convert_ps(
        "[CmdletBinding()]\nparam(\n    [Parameter(Position=0)]\n    [string]$Path\n)\n"
    )
    assert "[CmdletBinding()]" in out
    assert 'Path="$1"' in out
    assert any("未知命令 '[CmdletBinding()]'" in d.message for d in report.warnings)


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


# ----------------------------------------------------------------------
# Get-Date（阶段 3 的 2.4-PS 目标）
# ----------------------------------------------------------------------
def test_get_date_format_current_behavior(convert_ps):
    # 锁定当前行为：_expand_inline_cmdlets 抢先替换 Get-Date，
    # 导致 -Format 参数残留为无效 bash，且无警告/无 TODO（阶段 3 修复）。
    out, report = convert_ps(
        '$d = Get-Date -Format "yyyy-MM-dd"\nGet-Date -Format "yyyy/MM/dd"\n'
    )
    assert 'd=$(date) -Format "yyyy-MM-dd"' in out
    assert '$(date) -Format "yyyy/MM/dd"' in out
    assert report.warning_count == 0
    assert report.todo_count == 0


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
def test_where_object_pipeline_todo(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_.Name -eq "a.txt" }\n'
    )
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1
    assert "对象管道（脚本块）无法自动转换" in report.todos[0].message


def test_where_object_unbraced_todo(convert_ps):
    out, report = convert_ps('Get-ChildItem "/tmp" | Where-Object Name -like "*.log"\n')
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1


def test_where_object_standalone_double_todo(convert_ps):
    # 锁定当前行为：独立 Where-Object 会产生两条 TODO 诊断（阶段 3 一并处理）
    out, report = convert_ps('Where-Object { $_.Name -eq "a" }\n')
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 2


# ----------------------------------------------------------------------
# here-string（阶段 3 的 2.3 目标）
# ----------------------------------------------------------------------
def test_here_string_standalone_todo(convert_ps):
    out, report = convert_ps("@'\nno $expand here\n'@\n")
    assert "# TODO: here-string 开始（手动检查）" in out
    assert "# no $expand here" in out
    assert report.todo_count == 1


def test_here_string_assignment_current_behavior(convert_ps):
    # 锁定当前行为：赋值形式的 here-string 未被识别，生成的 bash 与语义不符（阶段 3 修复）
    out, report = convert_ps('$text = @"\nhello $name\n"@\nWrite-Host $text\n')
    assert 'text="@\\""' in out
    assert report.todo_count == 0
    assert report.warning_count >= 1


# ----------------------------------------------------------------------
# try/catch/finally（阶段 3 的 2.5 目标）
# ----------------------------------------------------------------------
def test_try_catch_current_structure(convert_ps):
    out, report = convert_ps(
        'try {\n    Get-Item "/tmp/a"\n} catch {\n    Write-Warning "failed"\n}\n'
    )
    assert "if true; then  # TODO: try/catch 未等价转换" in out
    assert "else  # TODO: catch 块" in out
    assert report.warning_count == 2


def test_try_catch_typed_current_behavior(convert_ps):
    # 锁定当前行为：带类型的 catch 会让后续花括号错位，产生「多余的 }」警告（阶段 3 修复）
    out, report = convert_ps(
        'try {\n    risky\n} catch [System.IO.IOException] {\n    Write-Host "io"\n}\n'
    )
    assert "# 多余的 }，已忽略" in out
    assert report.warning_count == 4


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


def test_pipeline_mixed_todo(convert_ps):
    out, report = convert_ps(
        'Get-ChildItem "/tmp" | Where-Object { $_ -match "log" } | Sort-Object\n'
    )
    assert "# TODO: 手动检查" in out
    assert report.todo_count == 1


# ----------------------------------------------------------------------
# 数组 / Test-Path 赋值（阶段 5/6 候选）
# ----------------------------------------------------------------------
def test_array_literal_current_behavior(convert_ps):
    # 锁定当前行为：单行 foreach 的函数体残留一个多余的右花括号（后续阶段候选）
    out, _ = convert_ps(
        '$items = @("a", "b")\nforeach ($i in $items) { Write-Host $i }\n'
    )
    assert 'items=("a"  "b")' in out
    assert 'echo "${i}" }' in out


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
