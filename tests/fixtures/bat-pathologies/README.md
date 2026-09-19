# bat 病理 fixture（缺陷 D-3 修复）

## 为什么有这个目录

2026-09-20 的项目评估发现：**仓库里没有任何真实形态的 .bat/.cmd 测试语料**。

- `tests/fixtures/` 下此前只有 `real-corpus/fleschutz/`（60 个 .ps1），
  且是 665 个 CC0 语料按文件名排序的**前 60 个**，属于最短的一档（中位 33 行、max 177 行）。
- `~/下载` 下真实存在 **246 个 bat/cmd**，其中包含 GBK 编码（107 个）、
  末行无换行（12 个）、单行最长 280 字符、单文件最长 14,724 行等"病理"形态。
- 最"脏"的 151 个中文 bat 此前只在 `tools/corpus-analysis/measure.py` 里作为
  **健壮性基线**跑一遍，**不进入任何断言测试** —— 即主力功能（bat 转换）长期缺少
  真实形态的回归覆盖。

## 许可与来源（重要）

本目录的 fixture 均为**本项目原创编写**，仅复刻外部语料中观测到的**结构特征**
（编码、换行、行长、变量命名、依赖类别），**不含任何第三方语料内容**。

原因：外部 bat 语料（`非常批处理`、`bat-master`、`windows-batch-script-master`）
**均未附带 LICENSE**，直接入仓会给 AGPL-3.0-or-later 的仓库带来许可风险。
PS 侧的 fleschutz 语料是 **CC0 1.0**，属于公有领域，因此可以入仓 —— 这解释了
为什么此前只有 PS 侧有真实语料 fixture。

## fixture 清单与对应的真实语料特征

| 文件 | 编码 / 形态 | 复刻的真实语料特征 |
| :--- | :--- | :--- |
| `gbk-encoded.bat` | GBK 字节 | 非常批处理 151 个中 107 个为 GBK |
| `utf8-bom.bat` | UTF-8 BOM | 真实语料中 664 个文件带 BOM |
| `no-trailing-newline.bat` | 末字节非换行 | 真实语料中 12 个文件末行无换行 |
| `long-single-line.bat` | 单行 2036 字符 | 真实语料单行最长 280 字符（此处取更极端的值） |
| `cjk-variable-name.bat` | UTF-8，中文变量名 | 中文批处理的 `set 变量=值` 用法（backlog P-1） |
| `delayed-expansion.bat` | `!VAR!` 延迟展开 | 中文批处理常见的 `enabledelayedexpansion`（backlog P-2） |
| `registry-and-wmic.bat` | `reg` / `wmic` / `sc` / `net` | 环境依赖类，必须显式 TODO 而非静默丢弃 |
| `nested-blocks.bat` | 嵌套 `if` / `for` 括号块 | B5 跨行括号块形态 |
| `call-goto-labels.bat` | `call :label` / `goto` / `exit /b` | goto / 子程序标签形态 |

## 断言内容

见 `tests/test_bat_pathology_fixtures.py`。覆盖三类：

1. **健壮性**：全部 fixture 不抛异常、`error_count == 0`、产物通过 `bash -n`。
2. **报告诚实性不变量**：产物含 `# TODO` 标记 `=>` `report.todo_count > 0`。
   这是 v2.6.0 A-1 与 v2.8.1 两次缺陷（`--fail-on-todo` 静默失效）的同类回归守卫。
3. **编码与形态保真**：GBK/BOM 正确识别；末行无换行不丢最后一条命令；
   超长单行不被截断；环境依赖命令被登记为 TODO。

## 未决事项（见评估报告 D-5）

等长中文变量名会被重命名为**同一标识符**（如两个三字变量都变成 `___`）。
当前实现会**告警**（`变量名 'X' 与 'Y' 重命名后同名（___），请人工重命名`），
但**不登记 TODO**，因此该产物 `todo_count == 0`，会被"rc==0 严格口径"算作
**功能完好**，而实际语义已不正确。

`test_cjk_rename_collision_is_announced` 目前只锁定"至少要有告警"这一底线。
建议后续把该冲突从 warning 提升为 TODO，使 `--fail-on-todo` 能拦住它 ——
但这会改变全量语料的 degraded 计数，需作为独立变更评估。
