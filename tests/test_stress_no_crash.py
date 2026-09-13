"""examples/stress_test.bat 压力测试回归 fixture。

只断言：转换不崩溃、输出非空、报告 JSON 可解析、警告清单稳定。
不断言转换率与具体生成结果——脚本故意极端，转换率会随改进浮动；
警告文案一旦变化会命中下方冻结清单，请核对转换结果后同步更新。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bat2sh.core.engine import convert_file
from bat2sh.core.settings import ConvertSettings

STRESS_BAT = Path(__file__).resolve().parents[1] / "examples" / "stress_test.bat"

FROZEN_WARNINGS = [
    (16, 'variables', '%DATE% 的转换可能不完全等价'),
    (16, 'variables', '%TIME% 的转换可能不完全等价'),
    (84, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (114, 'glob', '检测到通配符集合，已在脚本头添加 shopt -s nullglob：无匹配时循环体不执行'),
    (138, 'command', 'ver 已转换为 uname -a'),
    (144, 'variables', '%SystemRoot% 的转换可能不完全等价'),
    (154, 'command', '已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确'),
    (165, 'command', 'ipconfig 已转换为 ip addr，输出格式不同'),
    (165, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (167, 'command', 'netstat 已转换为 ss，输出格式不同'),
    (167, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (167, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (173, 'command', 'tasklist 已转换为 ps aux，输出格式不同'),
    (173, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (182, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (186, 'variables', '检测到转义百分号 %% ，已按字面 %% 处理'),
    (208, 'variables', '%SystemRoot% 的转换可能不完全等价'),
    (215, 'command', 'certutil -hashfile 已转换为 md5sum，输出格式不同（无 CertUtil 头部与指纹格式）'),
    (215, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (219, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (223, 'command', 'more +1 参数语义不同（Linux 版无 +1 跳过首行），请核对'),
    (235, 'command', 'robocopy 已转换为 rsync -a，请检查选项语义'),
    (244, 'command', '已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确'),
    (248, 'command', '已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确'),
    (249, 'command', '已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确'),
    (291, 'errorlevel', '$? 只能反映紧邻上一条命令的退出码，请检查语句顺序'),
    (293, 'errorlevel', 'cmdextversion 在 Linux 无对应检查，恒为假'),
    (297, 'command', 'assoc 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令'),
    (298, 'command', 'ftype 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令'),
    (306, 'command', 'systeminfo 已转换为 uname -a，信息量不同'),
    (306, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (310, 'command', 'driverquery 已转换为 lsmod，语义不同（仅内核模块，无驱动服务详情）'),
    (310, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (310, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (310, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (310, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (314, 'command', 'tasklist 已转换为 ps aux，输出格式不同'),
    (314, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (314, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (314, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (324, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (324, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (324, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (328, 'command', "未知命令 'query'，请确认 Linux 下可用"),
    (340, 'control_flow', '循环变量 %~s 不在 for 循环上下文中'),
    (341, 'control_flow', '循环变量 %~a 不在 for 循环上下文中'),
    (342, 'control_flow', '循环变量 %~t 不在 for 循环上下文中'),
    (343, 'control_flow', '循环变量 %~z 不在 for 循环上下文中'),
    (399, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (403, 'command', 'findstr 已转换为 grep，正则语法可能存在差异'),
    (418, 'control_flow', 'eol=; 仅近似为跳过以 ; 开头的行；Windows 在行中间遇到 ; 会截断，请核对'),
    (424, 'command', '已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确'),
    (433, 'command', 'netstat 已转换为 ss，输出格式不同'),
    (436, 'command', 'tasklist 已转换为 ps aux，输出格式不同'),
    (445, 'command', 'ipconfig 已转换为 ip addr，输出格式不同'),
    (448, 'command', 'systeminfo 已转换为 uname -a，信息量不同'),
    (451, 'command', 'driverquery 参数 ^| findstr /i "Running" 已忽略（Linux 无对应过滤）'),
    (451, 'command', 'driverquery 已转换为 lsmod，语义不同（仅内核模块，无驱动服务详情）'),
    (460, 'command', "未知命令 'query'，请确认 Linux 下可用"),
    (466, 'command', 'certutil -hashfile 已转换为 md5sum，输出格式不同（无 CertUtil 头部与指纹格式）'),
    (469, 'command', 'robocopy 已转换为 rsync -a，请检查选项语义'),
    (475, 'command', 'assoc 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令'),
    (478, 'command', 'ftype 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令'),
    (512, 'command', 'ver 已转换为 uname -a'),
]


@pytest.fixture(scope="module")
def stress_result():
    assert STRESS_BAT.is_file(), f"缺少压力测试 fixture: {STRESS_BAT}"
    return convert_file(STRESS_BAT, ConvertSettings(), write=False)


def test_stress_conversion_does_not_crash(stress_result):
    assert stress_result.error == ""
    assert stress_result.text.strip()
    assert stress_result.written is False


def test_stress_report_json_is_parseable(stress_result):
    payload = json.loads(stress_result.report.to_json())
    assert payload["kind"] == "bat"
    assert payload["warning_count"] == len(payload["warnings"])
    assert payload["todo_count"] == len(payload["todos"])
    assert all(isinstance(item["line"], int) for item in payload["warnings"])
    assert all(item["message"] for item in payload["warnings"])


def test_stress_warning_list_is_stable(stress_result):
    actual = [(d.line, d.category, d.message) for d in stress_result.report.warnings]
    assert actual == FROZEN_WARNINGS, "警告清单已变化：请核对转换结果并同步更新 FROZEN_WARNINGS"


def test_stress_output_passes_bash_n(stress_result, bash_check):
    bash_check(stress_result.text)
