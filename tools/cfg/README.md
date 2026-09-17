# tools/cfg —— CFG 只读数据模型报告

> v2.1.0（P4）落盘。把 goto 语义转换所需的**控制流图（CFG）**固化为可重跑的只读报告。

## 用途

`python3 tools/cfg/cfg_report.py [--corpus DIR] [--json OUT]`

1. 用 `bat2sh.core.cfg.build_cfg_from_text` 为每个语料文件构建 CFG
   （标签位置表 + goto→标签边）；
2. 汇总形态分布并与 **C4 台账**（`core/control_flow.py`）逐项交叉核对；
3. 输出多入口标签、重复标签、逐文件 `validate_cfg` 问题。

**只读**：不写仓库、不改转换器、不跑沙箱。语料缺省 `~/下载/非常批处理`；
不存在时退出码 2（CI 无外部语料，跳过）。

## 口径

- **行**：逻辑行（`^` 续行累积，与 `batch._logical_lines` 同口径；测试守护）。
- **块深度**：括号净值近似（与 C4 扫描器一致），**不是**转换器 `_Block` 块栈。
- **重复标签**：为与 C4 台账一致，解析目标取**最后一次**出现；重复项在报告末尾暴露。
- **形态键**：复用 `control_flow.classify_goto`（7 个互斥主形态），不新增形态。

## 本会话实测（语料 151 文件）

| 指标 | 值 |
| :--- | ---: |
| goto 边（= C4 扫描器 goto 语句） | 1583 |
| 形态分布 | 与 C4 台账 **8/8 一致** |
| 逐文件 `validate_cfg` 问题 | **0** |

## 与 v2.2 的关系

本工具**不改转换**：它是 goto 高级形态（回跳→循环 / 块内 goto）的**前置数据**。
P5（`redundant_goto` / 顶层 `forward_skip`）经实测翻转 0 且安全子集零收益，
显式归 v2.2.0（见 `docs/v2.1.0-review.md` §8）。
