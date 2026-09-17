# tools/c4 —— goto 控制流只读报告

> v1.10.0b1（Session C4）落盘。把 C4（`goto`/控制流）的可行性研究**固化为可重跑的只读报告**。

## 用途

`python3 tools/c4/control_flow_report.py [--corpus DIR] [--json OUT]`

1. 用 `bat2sh.core.control_flow.summarize_goto_lines` 扫描语料，复现**形态台账**
   （`docs/session-c4-design.md` §形态分布）的计数；
2. 用**转换器口径**统计 goto TODO（权威），与台账交叉核对。

**只读**：不写仓库、不改转换器、不跑沙箱。语料缺省 `~/下载/非常批处理`；
不存在时退出码 2（CI 无外部语料，跳过）。

## 口径

- **扫描器口径**（best-effort）：跳过空行/`::` 注释，`echo`/`rem` 行内的 `goto` 视为数据；
  标签支持 CJK；`in_block` 用括号净值近似（非块栈）。
- **转换器口径**（权威）：`ConvertSettings(bash_check=False)` 的 `report.todos`
  中 `category == "control_flow"` 且消息含 `goto` 的条数。
- 两口径**不可互相套用**（覆盖范围不同：扫描器含未触发 TODO 的 goto，转换器含块内 goto 守卫）。

## 本会话实测（语料 151 文件）

| 指标 | 值 |
| :--- | ---: |
| goto 语句（扫描器） | 1583 |
| goto TODO（转换器） | 1362 / 39 文件 |
| degraded 内 goto TODO | 252 / 22 文件 |

## 与 v2.0 的关系

本工具**不改转换**：它是 C4 归 v2.0 后的**证据与起点**（台账 + CFG 前置数据）。
真正的 CFG/状态机实现见 `docs/session-c4-design.md` §分阶段方案。
