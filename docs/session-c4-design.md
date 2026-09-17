# C4 goto 控制流 —— 设计契约（v2.0 前瞻 + v1.10.0b1 台账）

> 前置：`docs/session-c4-coldstart.md`、`docs/session-c4-review.md`（裁定 = 收窄后实现，方案 D）。
> 本文件是 C4 的**设计契约**：v1.10.0b1 只交付**形态台账 + 分类器 + 校验器 + 只读报告**，
> **不做任何 goto 语义转换**；语义转换（CFG/状态机）为 **v2.0** 的实现契约。
> 起点 HEAD = `7e645db`。

---

## 0. 结论速览

| 问题 | 结论 |
| :--- | :--- |
| C4 能否在本 session 实现？ | **否**。需完整 CFG；路线图评 15–25 人日、最高风险；与 053（块栈）同域 |
| 收益？ | **degraded 翻转 ≈ 2/86**（唯一阻塞=goto 的 3 文件，其一实为 `for /f` 选项问题）；TODO 数 1362 |
| 撞库可行？ | **否**。形态按「位置×方向×条件×目标」≥ 数十种（任务书判据：几十种 → 状态机） |
| 有可证安全子集？ | **否**（冗余 goto 27 条不落任何 degraded 单设施文件；`:eof` 已实现） |
| v1.10.0b1 交付 | 形态台账（第四张表）+ 分类器 + 校验器 + 只读报告；**零转换改动** |
| 语义转换 | **v2.0**，前置 = B3 黄金对照 + 本台账 + 分阶段闸门 |

---

## 1. 形态分布（语料实测，可复现）

> 仪器：`tools/c4/control_flow_report.py`（扫描器口径，`echo`/`rem` 与 CJK 标签已处理）
> + 转换器口径（`report.todos`，权威）。**仪器先验证**：台账常量与实测逐项一致（8/8 OK）。

### 1.1 扫描器口径（`summarize_goto_lines`）

| 形态键 | 说明 | 语句 | 文件 | 置信度 |
| :--- | :--- | ---: | ---: | :---: |
| `forward_skip` | 前向跳过到后续标签 | 551 | 26 | D |
| `backward_loop` | 回跳（重试/菜单循环） | 446 | 28 | D |
| `in_block_goto` | 控制块（for/if 体）内 | 457 | 8 | D |
| `eof_exit` | `goto :eof` | 93 | 20 | **A（已实现）** |
| `redundant_goto` | 目标 = 下一条非空语句 | 27 | 5 | B |
| `missing_label` | 目标标签不存在 | 8 | 2 | D |
| `dynamic_target` | `goto %VAR%` | 1 | 1 | D |
| **合计** | | **1583** | | |
| `label_in_block`（辅） | 标签位于控制块内（error 层） | 97 | 4 | D |

**方向分布**（含全部 goto）：forward 775 / backward 706 / none 102。

### 1.2 转换器口径（权威）

| 指标 | 值 |
| :--- | ---: |
| 含 goto TODO 的文件 | 39 |
| goto TODO 总数 | 1362 |
| **degraded 内 goto TODO** | **252 / 22 文件** |
| 唯一阻塞=goto 的 degraded 文件 | 3（`合并文本.bat`/`合并文本2.bat`/`合并文本3.bat`），其中 `合并文本2.bat` 实为 `for /f` 选项不可解析 |

### 1.3 宿主

- `135 系统优化.bat`：439 TODO（v1.9.2 后 443），其中 goto=194；**被 goto + sc + L4 多设施阻塞**。
- `031 史上最牛X…bat`：**语法失败**（goto TODO 876，不参与 rc/degraded 统计）。
- 二者合计占 goto TODO 的 78%。

---

## 2. 分阶段方案（v2.0）

> 原则（纪律 1/13）：**先只读量化 → 保守子集 → 黄金对照锁定 → 逐项独立 commit**；
> 任一阶段出现回滚即 **Phase 2C 停下上报**，不 shotgun。

### Phase 0（已完成，v1.10.0b1）

- 形态台账（`core/control_flow.py`）+ 分类器 + 校验器 + 只读报告。
- 产出：形态分布、方向分布、唯一阻塞文件、精确 churn（1362 TODO / 39 文件 / 1583 语句）。
- **零转换改动**。

### Phase 1（v2.0 前置）：CFG 数据模型

- 在**不改转换产物**的前提下，构建 `:label` 位置表与 goto→标签边（前向/回跳/跨块）。
- 新增只读校验：每条 goto 必须落入台账形态；不可归类者 → 报告。
- 闸门：`validate_control_flow_patterns()==[]`、语料零漂移。

### Phase 2（v2.0）：单形态试点（低风险优先）

- 顺序：`redundant_goto`（可证 no-op）→ **顶层前向 skip**（`if → goto` 的 guard 形态）。
- 每形态：黄金对照用例（wine）+ 最小复现 + 独立 commit + 全量回归 + churn 上限（建议 ≤10 文件）。
- **硬前提**：B3 harness 覆盖该形态；examples 零漂移。

### Phase 3（v2.0）：回跳 → 循环

- `backward_loop` → `while/until`；需识别出口条件（errorlevel/输入变量）。
- 难点：出口依赖运行时值 → 不能静态全知；**不可证安全的回跳维持诚实 TODO**。

### Phase 4（v2.0）：块内 goto + 块内标签

- 与 053 同域：块栈必须已由 B3 黄金对照覆盖；先解决「for/f 体含 goto」的 break/continue 映射。
- 与 B5（行首 `(` 判据 / 括号跨行累积）同期评估。

### 明确不做（终态）

- `dynamic_target`（`goto %VAR%`）：目标运行时求值，静态不可判 → 诚实 TODO。
- `missing_label`：目标不存在 → 诚实 TODO。
- 跳入块内的 `goto`（cmd 危险写法）→ 保持 error 层响亮拒绝。

---

## 3. 风险与止损（继承路线图 §5 + Session C4 审阅 §4）

| 风险 | 翻车方式 | 缓解 |
| :--- | :--- | :--- |
| 块栈回归 | 改 goto 触及 `_prepass`/`_label_line`/`_convert_for`/`_convert_if` | B3 黄金对照 + 全量 pytest + examples 零漂移；churn 硬上限 |
| 「看似对」的错译 | 前向 skip 目标被多处跳入时当作单出口 | CFG 可达性分析；不可证安全 → TODO |
| 回跳出口不可知 | 出口依赖 errorlevel/变量 | 保持诚实 TODO，不发明映射 |
| 数字硬凑 | 为翻转数激进转换 | 纪律 1/13；翻转如实记录 |

**全局止损**：每 commit 全量 pytest；examples 零字节漂移；崩溃 0；任一回滚 → 停下上报。

---

## 4. v1.10.0b1 的验收（台账版）

| # | 标准 | 判据 |
| :--- | :--- | :--- |
| 1 | 台账校验 | `validate_control_flow_patterns() == []` |
| 2 | 台账可复现 | `tools/c4/control_flow_report.py` 8/8 OK（台账常量 == 实测） |
| 3 | 零转换改动 | 151 语料产物与 session-b1b2 基线**逐字节一致** |
| 4 | 指标不劣化 | 语法 147/151、rc==0 102、功能完好 16、degraded 86、TODO 894、崩溃 0 |
| 5 | examples | tracked 对零字节漂移 |
| 6 | wine harness | 6/6 MATCH |
| 7 | pytest | 只增不减（1344 → 1360） |

---

## 5. 纪律对照

| 纪律 | 落实 |
| :--- | :--- |
| 1 保守 TODO | 不实现不可证安全的形态；语义转换留 v2.0 |
| 2 只读诊断先行 | coldstart + review + `/tmp/c4/*` 探针，实现前完成 |
| 3 主动披露偏离 | 任务书「v1.9.2 修 053」「4 条残余=C4 靶子」不准确，已披露 |
| 4 不发明映射 | 台账每条带 `evidence`（语料 `文件:行`），校验器守护 |
| 6 置信度光谱 | A=`eof_exit`；B=`redundant_goto`；D=其余 |
| 7 缺 evidence 拒绝 | `validate_control_flow_patterns()` |
| 9 仪器先验证 | 台账常量与实测 8/8 一致后才落盘 |
| 10 锁定 HEAD | 起点 `7e645db`；每次写前校验 |
| 13 语义正确性与 rc==0 并列 | 零转换改动 → 语义与 rc 均持平，不硬凑提升 |
| 14 断言验证语义 | 新测试断言**形态分类语义**（非编码当前行为） |
