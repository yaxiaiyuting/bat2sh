# Session C4 自我审阅与裁定（只读阶段产出）

> 前置：`docs/session-c4-coldstart.md`。本文件在**任何代码改动之前**写成，只读。
> 起点 HEAD = `7e645dbe016af780d1789f05692d410e90358b16`（`7e645db`）。
> 目的：给出 C4 的范围、风险、最小复现、止损、退路、替代方案与验收标准，并作出裁定。

---

## 1. 范围（做什么 / 不做什么）

### 1.1 本轮做

| 做 | 说明 |
| :--- | :--- |
| **C4 控制流形态台账子系统**（新模块 `python/bat2sh/core/control_flow.py`） | 把语料实测的 goto 形态固化为**带 `evidence` 的结构化表**（与命令表/名称表/输出契约表并列的**第四张表**），含置信度光谱与「为何不可自动转换」的书面理由 |
| **纯分类器** `classify_goto()` + **CFG-lite 汇总器** `summarize_gotos()` | 只读、纯函数；把每条 goto 归入台账中的形态键 |
| **校验器** `validate_control_flow_patterns()` | 纪律 7：每条必须 `evidence` 指向真实语料；`integrated=True` 仅限已实现项；键唯一；覆盖全部形态 |
| **只读分析工具** `tools/c4/control_flow_report.py`（提交） | 用同一模块复现语料分布，作为可重跑的 evidence |
| **测试** `tests/test_control_flow_taxonomy.py` | schema/校验/分类/覆盖（**不依赖外部语料**，CI 可跑） |
| **CI 触发修正**（独立 commit） | 分支/tag push 也触发 CI（任务书 §六） |
| 文档 | coldstart / review / design / report / release notes |

### 1.2 本轮**不做**（明确边界）

| 不做 | 原因 |
| :--- | :--- |
| ❌ **任何 goto → `while`/`if`/函数/状态机的语义转换** | 需完整 CFG；路线图评 15–25 人日、风险最高、归 v2.0（F1）。**本轮零转换改动** |
| ❌ 改 `_convert_goto` 的产物（TODO 文本/发射逻辑） | 会改产物字节 → examples/测试漂移；且无法证安全 |
| ❌ 改块栈核心（`_Block`/`_pop_block`/`await_paren_close`/`_convert_for`/`_convert_if`/`_label_line`） | 053 同域，最高危；本轮**完全不碰** |
| ❌ 修 4 条「真块失同步」（044/059/135/138） | 块栈/词法层残余，无清晰方案 → 止损（纪律 1） |
| ❌ 改 `_prepass`/标签行号登记 | 属块栈相邻路径；台账模块**不消费转换器内部状态**（纯函数），避免耦合 |
| ❌ B5 解析层重写 / AST | 2.x，与 C4 合并评估 |

> **本轮 C4 = 「把 goto 问题研究清楚并冻结为可校验的代码台账」，不是「把 goto 译出来」。**

---

## 2. 风险（逐项，附具体风险与证据）

### 2.1 核心判断：为什么不做语义转换

| # | 风险 | 具体表现 | 证据 |
| :--- | :--- | :--- | :--- |
| R1 | **触及 053 已修路径** | goto 的派发/守卫与 053 的失稳函数同域：`_prepass`（`batch.py:860-889`）、`_label_line`（`:1585-1617`）、`_convert_for` 的 goto 守卫（`:2300-2307`）、`_convert_if`。任何结构性改动都会落在这批函数上 | `docs/v1.8.3-attribution.md:70,131-133`；`chenpi11-cmd-reference.md` §2.3 |
| R2 | **无 CFG 则必产「看似对、实际错」** | `goto` 可前跳/回跳/跳出/跳入块/动态目标；不知道标签位置与可达性就无法改写。例：`if %n% equ 0 (set k=) else (set k=skip=%n%)` + `… &goto next`（038/040） | 本会话 `goto_patterns`：backward 704 / forward 781 / 块内 462 / 条件 909 |
| R3 | **块内 goto 是硬依赖** | 462 条 goto 位于控制块内；`for /f` 体含 goto 当前整行 TODO（`batch.py:2300`）。一旦要支持，必须动循环体装配（块栈） | 同上 |
| R4 | **动态目标 / 缺标签** | `goto :%LABEL%`（examples/deepseek）、`goto :INSIDE_IF`（跳入块内）等；缺标签 19 条 | `goto_patterns` unknown=19；`examples/deepseek_bat_20260913_faa286.bat:184` |
| R5 | **收益极低** | 唯一阻塞=goto 的 degraded 文件仅 **3**（038/039/040），其中 039 实为 `for /f` 选项不可解析（**非 goto**）→ 真实翻转 ≈ **2/86**；`goto` 的 TODO 高度集中在 2 个文件（`031` 876 条**语法失败**、`135` 194 条**多设施阻塞**） | 本会话 `degraded_buckets` |
| R6 | **撞库不可行** | 形态按「位置×方向×条件×目标」组合 ≥ 十余种（数十细分）→ 依任务书判据「几十种 → 必须状态机」 | 本会话 `goto_patterns` |

> **结论：风险最高 + 收益 ≈ 2 文件 → 语义转换在本 session 不做**（纪律 1「保守 TODO 优于激进转换」）。

### 2.2 本轮「做」的部分的风险清单

| # | 风险 | 缓解 | 证据/验证 |
| :--- | :--- | :--- | :--- |
| R7 | 台账数字与语料脱节（「看起来对」） | 所有计数以本会话只读实测为准，工具可复现；模块不驱动转换 | `/tmp/c4/*.py`（只读探针，仓库外） |
| R8 | 新增模块成为无人消费的「死代码」 | 由 `tools/c4/` 工具 + 测试消费；台账提供 `classify_goto()`/`summarize_gotos()` 纯函数 | 提交后 `pytest` 覆盖 |
| R9 | 校验器流于形式 | 校验规则可机械判定：`evidence` 非空且形如 `文件:行`、键唯一、`integrated=True` 仅 `eof_return`、每个枚举形态出现在覆盖表 | `validate_control_flow_patterns()==[]` |
| R10 | 与既有表（命令/名称/契约）职责重叠 | 台账是**控制流形态**，不映射命令/名称；文件独立、无交叉依赖 | 新文件，未 import 其他 mappings |
| R11 | **改动模块数 > 5** | 预计：`core/control_flow.py`(新)、`tools/c4/`(新)、`tests/test_control_flow_taxonomy.py`(新)、`.github/workflows/test.yml`、docs + 版本 2 处 = 既有文件 **3**（CI + pyproject + `__init__`），未超 5 | 见 §3 |
| R12 | CI 触发修正误伤 | 只**新增** `branches: session-*` 与 `tags: v*`，不移除既有 main/PR；不改 job | `.github/workflows/test.yml` |

### 2.3 examples 漂移风险

- 本轮**零转换改动** → **examples 零字节漂移**（预期，且不刷新）。
- 唯一含 goto 的 example 是 `examples/deepseek_bat_20260913_faa286.bat`（**无 `.sh` 对照**）→ 无 tracked 对。

### 2.4 四条残余（044/059/135/138）—— 为何不碰

- 均为块栈/词法层残余（「循环变量逸出」「`%%%%`+`%~1`」「内层 cmd 串」），
  与 `_convert_for`/块栈核心强相关；**无通过只读分析确认的清晰方案**。
- 纪律：**触及 053 已修路径且无清晰方案 → 停**（`docs/v1.9.2-rounds.md:99-102` 已将其重分类到 2.x）。

---

## 3. 最小复现（每条靶子）

| 目标 | 最小复现 | 当前产物 | 判定 |
| :--- | :--- | :--- | :--- |
| 前向跳过 | `if exist x goto skip` / 命令 / `:skip` | `# TODO: 手动检查: goto skip` + 后续代码在 bash 中会执行 | 诚实 TODO（非静默坏码）；需 CFG |
| 回跳重试循环 | 038/040：`:lp` … `… &goto lp` | `# TODO`（for/f + goto） | 同上 |
| 块内 goto | `for … do ( … &goto next )` | `# TODO（循环体含 goto…）`（`:2300`） | 同上 |
| `goto :eof` 顶层 | `goto :eof` | `exit 0` | **已正确实现**（`:1625-1628`） |
| `goto :eof`（函数内） | `:f` … `goto :eof` | `return` | 已正确实现 |
| 缺标签 | `goto nolabel` | `# TODO: 手动检查: goto nolabel` | 诚实 TODO |
| 冗余 goto | `goto next` + 下一行 `:next` | `# TODO`（8 条，仅 `031`） | 无余量，不做 |
| 块内标签 | `for … do ( :inner … )` | **error 层**「标签位于控制块内」 | 已响亮拒绝（4 文件） |

> 复现命令（只读，仓库外）：`python3 /tmp/c4/goto_scan.py`、`/tmp/c4/goto_patterns.py`、
> `/tmp/c4/degraded_buckets.py`、`/tmp/c4/safe_subset.py`、`/tmp/c4/residual4.py`。

---

## 4. 止损点（硬闸门）

| 闸门 | 阈值 | 触发动作 |
| :--- | :--- | :--- |
| 转换产物字节变化 | **任何**既有产物非预期变化 → 停 | 本轮预期 0；出现即回滚该 commit |
| examples tracked 对漂移 | 任何字节 → 停 | 不刷新，先查因 |
| strict（功能完好）由 16 下降 | −1 → 停 | 本轮理论上不可能（零转换改动）；触碰即回滚 |
| degraded TODO 总数变化 | 非 0 → 停 | 同上 |
| pytest | 出现**失败** → 停 | 只允许新增测试 |
| 改动模块 > 5 | 超 → 停 | 预计 3 个既有文件 |
| 触及块栈核心 | 任何改动触及 `_Block`/`_pop_block`/`_prepass`/`_convert_for`/`_convert_if`/`_label_line` → 停 | 本轮为硬红线 |
| 台账缺 `evidence` | 任一条 → 停（纪律 7） | 拒绝该条，不硬凑 |
| HEAD 并发变化 | ≠ 起点且非本会话 commit → 停 | 报告并发写入 |
| tag 后 CI 红 | → 停，**不 force-push** | 修在后续 commit |

---

## 5. 退路

| 项 | 值 |
| :--- | :--- |
| 回滚点 | `7e645dbe016af780d1789f05692d410e90358b16`（`7e645db`） |
| 回滚方式 | `git checkout session-b1b2` / `git reset --hard 7e645db`；分支**不合并 main** |
| 逐 commit 回滚 | CI 修正、台账框架、文档各自独立，可单独 revert |
| 若台账框架触发止损 | 撤销该 commit；仍可发「仅 CI 修正 + 文档」的 b1（须披露） |
| 若整体触发止损 | 分支不合并，写报告，**v1.10.0b1 不发** |

---

## 6. 替代方案（更保守/更激进的路）

| 方案 | 内容 | 评估 |
| :--- | :--- | :--- |
| **A. 退回设计文档**（最保守） | 只写 C4 设计，不发版、不写码 | **合格**（任务书明示）；但 C4 研究结论无法机检、无法防「反复评估」→ 次优 |
| **B. 撞库式模态转换** | 对 3–5 个高频形态做模板替换 | ❌ 形态数十种，覆盖不了；且「看似对」风险高（任务书：撞库只能兜底） |
| **C. 全量 CFG 状态机** | 实现完整 goto 分析 | ❌ 15–25 人日、最高风险、单 session 不可控；路线图归 v2.0 |
| **D. 收窄：语义转换留白 + 台账框架 + 诊断/分析设施**（**选定**） | 零转换改动，交付 C4 形态台账（带 evidence/校验/纯函数）+ 只读工具 + 测试 + 文档；CI 修正 | ✅ 风险可控（不碰转换器）、止损清晰、有退路、可机检；为 v2.0 铺路 |

---

## 7. 客观验收标准

| # | 标准 | 判据 |
| :--- | :--- | :--- |
| 1 | pytest 全绿且不回退 | ≥ 1344 passed，0 failed |
| 2 | **转换产物零漂移** | 151 语料产物与基线逐字节一致（本轮预期 0 变化） |
| 3 | **strict（功能完好）不回退** | = 16 |
| 4 | rc==0 不回退 | = 102 |
| 5 | degraded / TODO 总数不回退 | degraded = 86；degraded TODO = 894 |
| 6 | 崩溃 / 超时 | 0 / 0 |
| 7 | examples tracked 对 | 零字节漂移（不刷新） |
| 8 | 台账条目 | 每条有 `evidence`（真实语料 `文件:行`）；`validate_control_flow_patterns() == []` |
| 9 | 覆盖 | 台账形态覆盖 `summarize_gotos()` 在合成样例上产生的全部键 |
| 10 | 新增模块单测 | schema / 校验 / 分类 / 汇总各有测试 |
| 11 | wine harness 通过率不下降 | `tools/oracle/golden_harness.py` 6/6（无 wine 则 skip，不 fail） |
| 12 | `release-preflight.sh` | 通过 |
| 13 | tag 上 CI | 3.12/3.13/3.14 全绿（并发分支/tag 触发） |
| 14 | CI 修正生效 | 分支 push 与 tag push 均触发 workflow |

---

## 8. 裁定

| 判断 | 结果 |
| :--- | :--- |
| 风险可控？ | 是——**零转换改动**，不碰块栈；新增模块为只读台账 |
| 止损清晰？ | 是（§4 十余条硬闸门，产物零漂移可机检） |
| 有退路？ | 是（§5，起点 HEAD 锁定） |
| 前提已变？ | 局部偏差（任务书「v1.9.2 修 053」「4 条残余=C4 靶子」不准确）→ 已披露，不构成暂停 |
| 语义转换可达？ | **否**——需 CFG，15–25 人日、风险最高、翻转 ≈ 2/86 → 归 v2.0 |
| 是否「退回设计文档」？ | **否**——但把设计**固化为可校验的代码台账 + 只读工具**（方案 D），比纯文档更强且同样零风险 |

### **裁定：收窄后实现（方案 D）**

**收窄内容（须在 commit message / report / release notes 披露）**：

1. **不做任何 goto 语义转换**；`_convert_goto` 等转换路径**逐字节不变**。
   → `strict 16 / degraded 86 / TODO 894` 预期完全持平（**不硬凑提升**）。
2. **C4 交付形态 = 「控制流形态台账 + 分类器 + 校验器 + 只读分析工具」**，
   即任务书 Commit 2 的「C4 子系统框架」；为 v2.0 的 CFG/状态机提供 typed 起点与 evidence。
3. **4 条真块失同步（044/059/135/138）不碰**（块栈核心，无清晰方案 → 止损）。
4. **撞库不采用**（形态数十种，无法覆盖；任务书判据成立）。

**若实现期发现**：产物字节变化、examples 漂移、pytest 失败、strict 下降、
或任何改动触及块栈核心 → 立即按 §4 止损，回退到起点 HEAD，写报告，b1 不发。
