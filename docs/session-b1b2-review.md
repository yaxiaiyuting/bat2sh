# Session B1/B2 自我审阅与裁定（只读阶段产出）

> 前置：`docs/session-b1b2-coldstart.md`。本文件在**任何代码改动之前**写成，只读。
> 起点 HEAD = `7048e6c0b59d75b5a28c856c6f8072f03197159a`。
> 目的：给出 B1/B2 的范围、风险、最小复现、止损、退路、替代方案与验收标准，
> 并作出「进入实现 / 收窄实现 / 退回设计文档 / 暂停」的裁定。

---

## 1. 范围（做什么 / 不做什么）

### 1.1 B1 —— 名称映射子系统

| 做 | 不做 |
| :--- | :--- |
| 新建**第三张表**：`python/bat2sh/mappings/windows_names.py`（名称，非命令） | ❌ **不含 `sc→systemctl`**（C7，已后移 v2.0） |
| schema：`NameMapping(win, kind, linux, form, confidence, target_exists, evidence, notes)`；`kind ∈ {env_var, path_root, service}` | ❌ 不发明映射：无 `evidence`/无可依据 Linux 名 → 拒绝或 `form=none` |
| `validate_name_mappings()`：evidence 格式、置信度光谱、D 档约束、kind 专属约束 | ❌ 不改 `windows_tools.py` 既有 37 条（避免回归） |
| 首批（C3 路径/环境）：环境变量 `ProgramFiles`、`AllUsersProfile`；路径根 注册 `drive`（盘符）/`unc`（UNC 共享） | ❌ 不做服务名→unit 的实际映射（无 1.x 宿主，留 C7/v2.0） |
| 集成（**仅 env_var**）：`env_repl` 对**未在 `BATCH_ENV_MAP` 中**的 Windows 专有环境变量做解析 | ❌ **不集成盘符/UNC 的转换**（见 §2.2 churn 证据 → backlog） |
| 降级策略：无等价物 → **行级诚实 TODO**（复用 `_env_substring_todo` 机制，`core/batch.py:2659-2669`） | ❌ 不碰 `convert_backslashes` 的 19 个调用点 |

### 1.2 B2 —— 输出契约子系统

| 做 | 不做 |
| :--- | :--- |
| 新建 `python/bat2sh/mappings/output_contracts.py`：`OutputContract(command, linux_command, shape, keywords, evidence, integrated, notes)` | ❌ **不做解析级输出适配**（路线图 §1.B：1.x 明确不做；风险高） |
| `validate_contracts()`：evidence 必填、`keywords` 非空、`shape=differs` 必须给出差异说明 | ❌ 不改 `ipconfig` 既有 warn 文案（`test_stress_no_crash.FROZEN_WARNINGS` 冻结） |
| 把 `windows_tools.ToolMapping.output_contract=True` 从「notes 子串校验」升级为「**必须有对应契约记录**」（`ping`/`help` 补登记） | ❌ 不改 `for /f` 的 CJK/英文标签既有行为 |
| 首批契约：`ipconfig`（命令已对、输出差异+关键词）、`dxdiag`、`perfmon` | ❌ 不给 `085 显示自己的IP.bat` 造解析翻译（见 §7 收窄说明） |
| 集成：**裸命令** `dxdiag` / `perfmon`（无 `.exe`、当前静默透传 → `command not found`）改为**结构化诚实 TODO** | ❌ 不动 `.exe` 后缀路径（已由既有 exe 分支诚实 TODO） |

### 1.3 B1/B2 的耦合度评估（任务书要求裁定）

**结论：独立，代码上无共享设施，但共享同一套「evidence 必填 + `validate_*()` 守护」纪律。**

- 共享：两者的**校验范式**（`dataclass(frozen=True)` + `validate_*() -> list[str]` + 测试守护）
  与 `evidence` 格式约定。若 B1 先落 schema，B2 可**照抄范式**（复制 ~30 行校验骨架），
  但**不共享数据结构**（名称 vs 命令输出）。
- 不共享：B1 的消费点是 `env_repl`（变量展开）；B2 的消费点是命令派发（`mappings`/handler）。
- 故：**可以只做一个**。本 session 裁定**两个都做**，理由：
  ① 任务书明确要求 v1.10.0a1 = B1+B2；
  ② 两者均可**独立 commit、独立回归**（B1 不依赖 B2，反之亦然）；
  ③ 若其中一个触发止损，另一个不受影响（可只发一个子系统，报告披露）。

---

## 2. 风险（逐项，附具体风险与证据）

### 2.1 B1 集成只作用于 env_var：风险清单

| # | 风险 | 具体表现 | 缓解 | 证据 |
| :--- | :--- | :--- | :--- | :--- |
| R1 | 把「静默错」改成「诚实 TODO」会**增加** degraded 计数 | `%ProgramFiles%` 现在是 `${ProgramFiles:-}`（静默空串，可能被计为功能完好） | 只对**已非 rc==0** 的文件生效（§2.3 实测）→ 文件级指标不变 | `031` syntax-fail；`077` rc=1 |
| R2 | 行级 TODO 会吞掉整行，可能造成**新静默缺失** | 复用 `_env_substring_todo` 机制，整行变 `# TODO: 手动检查: <原文>` | 该机制自 v1.9.2 已在用且有守卫测试；TODO 原文完整保留 | `core/batch.py:2659-2669` |
| R3 | 新表与 `BATCH_ENV_MAP` **冲突/双源** | 同一个变量两处不同值 | 新增 `test_env_map_consistency`：新表 env_var 条目若有 `linux`，必须与 `BATCH_ENV_MAP` 一致；且**新表只登记未在 `BATCH_ENV_MAP` 的名字** | `core/rules.py:219-244` |
| R4 | 大小写不敏感 | cmd 变量名不区分大小写（`%programfiles%`） | 查找统一 upper；沿用 `env_repl` 的 `upper` 路径 | `core/batch.py:1086` |

### 2.2 B1 **不集成**盘符/UNC：为什么（churn 实测，纪律 9）

对基线产物逐文件扫描（`/tmp/b1b2/baseline_v192.json`）：

| 模式 | 命中**文件数** | 命中**次数** | 其中**当前为功能完好（strict）** | 结论 |
| :--- | ---: | ---: | ---: | :--- |
| `X:/`（Windows 盘符路径） | **35** | 385 | **6**（011/025/060/107/109 + 100） | ❌ 若改成 TODO，**strict 16→10、degraded 86→92** |
| `\\host\share`（UNC） | 4 | 19 | 1（`100 注册表/设注册表某个键的键值为变量2.bat`） | ❌ 同样至少 −1 strict |
| `${ProgramFiles:-}`（静默空串） | 2 | 5 | **0** | ✅ 安全（可集成） |

> **结论**：盘符/UNC 的「诚实 TODO 化」会**净损失 6–7 个功能完好文件**。
> 这不是「r3 顺手改」的规模，且任务书止损点为「改动 > 5 模块」「回归 > M 测试」——
> 盘符改动横跨 35 个语料文件、6 个 strict 文件，**远超 B1 首批应有的边界**。
> → **本版只登记入表（`integrated=False`，notes 标注 backlog），不驱动转换**；
> 具体 TODO 化与盘符语义表（`C:\`→挂载点）**留 v1.9.4/v1.9.5**（路线图 §3.1 原计划）。

### 2.3 B1 env_var 首批的实测影响（最小复现，纪律 9）

| 文件 | rc | 现状 | 接入 `%ProgramFiles%` 诚实 TODO 后的预期 | strict 变化 |
| :--- | ---: | :--- | :--- | :---: |
| `031 史上最牛X…bat` | —（语法失败） | 2 处静默 `${ProgramFiles:-}` | 该行变 TODO；文件本就 syntax-fail | 0 |
| `077 文件备份器V2.3修改版2.cmd` | 1 | 3 处静默 `${ProgramFiles:-}` | 该行变 TODO；rc 可能 1→0（进入 degraded） | 0（本非 rc==0） |
| `快速清理垃圾文件.bat`（`%ALLUSERSPROFILE%`） | 0 | `快速清理垃圾文件.bat` 当前 degraded（todo=1） | +1 TODO（`AllUsersProfile`→`/usr/share` 映射，非 TODO） | 0（若映射成功） |

> `%ALLUSERSPROFILE%` → 映射为 `/usr/share`：与 `BATCH_ENV_MAP["PROGRAMDATA"]="/usr/share"`
> **一致**（现代 Windows 中 `%AllUsersProfile%` 即 `C:\ProgramData`），非发明。证据：
> `corpus/快速清理垃圾文件安装修改版/快速清理垃圾文件.bat:15`。

### 2.4 B2 风险清单

| # | 风险 | 具体表现 | 缓解 | 证据 |
| :--- | :--- | :--- | :--- | :--- |
| R5 | 解析级适配高 churn（v1.8.3 前科） | 流程感知改法 26/151 churn + examples 漂移 | **不做**；只做「契约登记 + 诚实 TODO」 | 路线图 §1.B/§5；v1.8.3 §2.2 |
| R6 | 改 `ipconfig` warn 文案会破冻结测试 | `FROZEN_WARNINGS` 冻结了 `ipconfig 已转换为 ip addr，输出格式不同` | **文案逐字不改**；契约只做**附加**信息 | `tests/test_stress_no_crash.py:30` |
| R7 | `for /f` 既有英文/CJK 行为被误改 | `test_batch_silent_downgrade_v183.py` 两个测试锁定 | 不改该路径；契约表只做**校验层** | `tests/test_batch_silent_downgrade_v183.py:18,28` |
| R8 | 裸 `dxdiag`/`perfmon` → TODO 会动 `135` 的 TODO 数 | `135` 现为 rc==0/degraded（todo=443） | 语料中裸 `dxdiag` 仅 `031`（syntax-fail）；`135` 用 `.exe`（已 TODO）→ **影响 0 个 metric 文件** | `measure.json` `135` P4898/P4938 已是 TODO |
| R9 | 新契约表与 `output_contract` 字段不一致 | `ping`/`help` 的 `output_contract=True` 无契约 | 校验规则要求二者**双向**对应；为 `ping`/`help` 补登记（`integrated=False`） | `windows_tools.py:120,464` |

### 2.5 examples 零漂移风险（实测）

| 检查 | 结果 |
| :--- | :--- |
| `examples/` 中带 `.sh` 对照的 tracked 对：`deploy` / `hello` / `stress_test` / `backup` / `cleanup` | 5 对 |
| tracked `.bat` 中的盘符/UNC 出现次数 | **0** |
| tracked `.bat` 中的 `%ProgramFiles%` / `%AllUsersProfile%` | **0** |
| `examples/deepseek_bat_*.bat`（无 `.sh` 对照） | 含盘符/UNC，但**不受本版集成影响**（盘符/UNC 不集成） |

> → **examples 预期零漂移**，且本版**不刷新** examples（若出现漂移即触发止损）。

---

## 3. 止损点（硬闸门）

| 闸门 | 阈值 | 触发动作 |
| :--- | :--- | :--- |
| 改动模块数 | **> 5 个模块** → 停 | 目前预计：`mappings/windows_names.py`(新)、`mappings/output_contracts.py`(新)、`mappings/__init__.py`、`core/batch.py`、2 个测试文件 = **6 个**（2 个新模块不算「改动」，实测按 4 个既有文件） |
| 语料回归 | **strict（功能完好）由 16 下降** → 停 | 任何 −1 即回滚该 commit |
| 语料回归 | degraded TODO 总数 **> +20** → 停 | 超出即说明 TODO 化过度 |
| pytest | 出现**失败** → 停 | 只允许新增测试与「旧断言编码旧错误行为」的更新（须披露） |
| examples | tracked 对**任何字节漂移** → 停 | 不刷新，先查因 |
| 输出漂移 | 既有产物出现**非预期**字节变化 → 停 | 逐文件 diff 归因 |
| `validate_*()` | 任一映射缺 `evidence` → 停（纪律 7） | 拒绝该条，不硬凑 |
| 块栈核心 | 触及块栈/词法层 → 停 | 两子系统均不该触及 |

---

## 4. 退路

| 项 | 值 |
| :--- | :--- |
| 回滚点 | `7048e6c0b59d75b5a28c856c6f8072f03197159a`（`session-b1b2` 起点） |
| 回滚方式 | `git checkout main`（或 `git reset --hard 7048e6c`）；分支未合并 main |
| 逐 commit 回滚 | 每个 commit 独立、可单独 revert（B1/B2 不互相依赖） |
| 若 B2 触发止损 | 保留 B1，v1.10.0a1 仅含 B1，报告披露 |
| 若 B1 触发止损 | 保留 B2，同理 |
| 若两者都触发 | 分支不合并，写 report，v1.10.0a1 **不发** |

---

## 5. 替代方案（更保守的路）

| 方案 | 内容 | 评估 |
| :--- | :--- | :--- |
| **A. 只做 B1 的「表 + 校验」，零集成**（纯登记） | 建表 + `validate()` + 测试，不接 `env_repl` | 最保守，但价值仅「文档化」；任务书要求「子系统」，且 `%ProgramFiles%` 静默错仍在 → **次优** |
| **B. 只做 B2 的契约校验，不集成** | 建契约表 + 双向校验 | 同上，且 `dxdiag/perfmon` 静默透传仍在 → **次优** |
| **C. 本 session 只做 B1，B2 退回设计文档** | B1（1.x 归属正确）+ B2 留 2.x | **有吸引力**：与路线图 §1.B 的 B2 归属完全一致。但任务书明确要 B1+B2，且 B2 的**框架**是 2.x 的前置，提前落框架风险低 → **备选** |
| **D. 两者都退回设计文档** | 只写报告，不发版 | 过度保守：B1 是路线图 1.x 项目；B2 框架无行为风险 → **不采纳** |
| **E. 采纳即「收窄后实现」（选定）** | B1 表+校验+env_var 集成；B2 契约表+校验+裸 `dxdiag/perfmon` 诚实 TODO；盘符/UNC 与解析级适配留 backlog | **采纳**：风险可控、止损清晰、有退路，且**显式披露**与路线图/任务书的偏差 |

---

## 6. 客观验收标准（替代任务书的「rc==0 提升、degraded 下降」）

> 理由见 `session-b1b2-coldstart.md` §4.1：B1/B2 按路线图 ROI **预期翻转 0**，
> 且其正确做法是诚实化（degraded 可能 +）。故本轮验收改为**可测、可达**的标准：

| # | 标准 | 判据 |
| :--- | :--- | :--- |
| 1 | pytest 全绿且不回退 | ≥1262 passed，0 failed |
| 2 | **strict（功能完好）不回退** | ≥ 16 |
| 3 | **rc==0 不回退** | ≥ 102 |
| 4 | degraded 变化**可解释** | 若 +，逐文件归因到「诚实化」；上限 +3 文件 |
| 5 | degraded TODO 总数变化**有界** | ≤ +20 |
| 6 | 崩溃 / 超时 | 0 / 0 |
| 7 | examples tracked 对 | 零字节漂移（不刷新） |
| 8 | 映射/契约条目 | 每条有 `evidence`；`validate_name_mappings()==[]`、`validate_contracts()==[]` |
| 9 | 静默错收敛 | `%ProgramFiles%` 静默空串 → 诚实 TODO；裸 `dxdiag/perfmon` 静默透传 → 诚实 TODO（有最小复现测试） |
| 10 | 新子系统单测 | B1/B2 schema、校验、查找、集成行为各有测试 |
| 11 | `release-preflight.sh` | 通过 |
| 12 | tag 上 CI | 3.12/3.13/3.14 全绿 |

---

## 7. 裁定

| 判断 | 结果 |
| :--- | :--- |
| 风险可控？ | 是。核心行为改动仅 2 处（env_var 诚实 TODO、裸 `dxdiag/perfmon` 诚实 TODO），且都落在**非 strict 文件**（§2.3/§2.4-R8 实测）。 |
| 止损清晰？ | 是。§3 的 8 条闸门均可机械判定；strict 由 16 下降即停。 |
| 有退路？ | 是。§4，起点 HEAD 锁定，两子系统可独立取舍。 |
| 前提已变？ | **部分冲突**（B2 的解析级适配与路线图相悖；收益预期与 ROI 口径不符）→ 不暂停，**收窄**处理并披露。 |
| 任务书要求的「rc==0 提升、degraded 下降」可达？ | **否**（路线图 §3.4 预期翻转 0）。已在 §6 重述为客观标准，并将在 report/release notes 披露。 |

### **裁定：收窄后实现（方案 E）**

**收窄内容（必须在 commit message 与 report 中披露）**：

1. **B2 不做解析级输出适配**（路线图 §1.B 的 1.x 红线）；本版 B2 = 契约**框架 + 登记 + 校验**
   ＋ 裸 `dxdiag`/`perfmon` 的诚实 TODO。`output_contract` 由「notes 子串」升级为「**必须有契约记录**」。
   → 因此 `085 显示自己的IP.bat`（唯一可能翻转的 ipconfig 解析文件）**本版不翻转**，留 2.x。
2. **B1 不集成盘符/UNC**（churn 35 文件 / 6 strict，远超首批边界）；仅入表登记（`integrated=False`）
   ＋ backlog。1.x 内的盘符语义表留 v1.9.4/v1.9.5。
3. **B1 env_var 只新增未映射的 Windows 专有变量**（首批 `ProgramFiles`→诚实 TODO、
   `AllUsersProfile`→`/usr/share`），不改既有 `BATCH_ENV_MAP` 的值（零输出漂移）。

**B1/B2 一起做**（任务书裁定权）：两者独立、共享校验范式、可独立回滚 → 同版交付。

**若实现期发现**：strict 下降、examples 漂移、pytest 失败、或映射缺 evidence → 立即按 §3 止损，
回退到起点 HEAD，写报告，v1.10.0a1 不发。

**「退回设计文档」未被采纳的理由**：退回到设计文档适用于「风险 > 收益且退路不清」；
本 scope 经收窄后风险可控（改动集中在 2 个新模块 + `env_repl` 一处 + 命令派发一处），
且 B1 本身即路线图 1.x 项目。退回会让 B1 的 1.x 价值无谓延后。
