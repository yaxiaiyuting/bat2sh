# bat2sh 归因矩阵元评估 · 盘点（阶段一，只读）

> 会话：归因矩阵元评估（`bat2sh` 仓库）。**起点 HEAD = `b9f020a`**（= tag `v2.9.0` 发布后 `main` tip，
> tag `v2.9.0` @ `69e6fde`，其后 11 个 commit），分支 `main`，工作区干净。
> **全程只读**：未修改任何代码/测试/既有文档；一切探针与产物在 `/tmp/meta-audit/`。
> 任务：评估外部建议「建立 Degraded Attribution Matrix，按可泛化性分类 82 个 degraded」**会揭示出哪些
> 项目还不知道的东西**。

---

## 0. 前置确认（任务书 §一）

| # | 前置 | 要求 | **实测** | 判定 |
| ---: | :--- | :--- | :--- | :---: |
| 1 | 工作区干净 | 干净 | `git status --porcelain` = 空；HEAD `b9f020a`（`main`） | ✅ |
| 2 | HEAD = v2.9.0 发布后 main tip | — | tag `v2.9.0` @ `69e6fde`；`v2.9.0..HEAD` = **11 commit** | ✅ |
| 3 | `docs/v1.9.1-attribution.md` 存在 | 存在 | 存在（375 行，31 211 B） | ✅ |
| 4 | `docs/v2.5.0-reality-check.md` 存在 | 存在 | **不存在** —— v2.5.0 的 CFG 实测在 `docs/v2.5.0-report.md` §4/§5.1 与 `docs/v2.5.0-verification.md` §三 | ⚠️ **命名偏离** |
| 5 | `docs/v2.6.0-corpus-attribution.md` 存在 | 存在 | 存在（166 行，9 520 B） | ✅ |

> **命名偏离（纪律 4 主动披露）**：仓库中 `reality-check` 命名的文档只有
> `v2.2.0-reality-check.md` 与 `v2.3.0-reality-check.md`。**v2.5.0 的 CFG 实测内容存在且完整**
> （`docs/v2.5.0-report.md` §4 指标表、§5「是否引入静默错」、§5.1 `rc0` 定义性位移、
> §10.1 wine 黄金对照 12/12），只是文件名不同。**未触发「已有归因文档缺失 → 停」**：
> 归因内容齐备，缺的是文件名。本 session 继续。

### 0.1 仪器验证（纪律 9：先验证再报数字）

复跑仓库自带仪器 `tools/corpus-analysis/measure.py`，与 v2.9.0 记录**逐字段比对**：

| 语料 | 命令 | 实测 summary | 发布记录 | 一致 |
| :--- | :--- | :--- | :--- | :---: |
| 老 151 | `--corpus ~/下载/非常批处理 --out /tmp/meta-audit/old151 --json` | `151/149/101/19/82/851/crash 0/timeout 0/convert_error 0` | v2.9.0 基线 `151/149/101/19/82/851` | ✅ **逐字段一致** |
| 新 79 | `--corpus ~/下载/bat-master` + `--corpus ~/下载/windows-batch-script-master` | 合 `79/78/54/27/27/136/0` | v2.6.0 记录 `79/78/54/27/27/136/0` | ✅ **逐字段一致** |

> 口径：`corpus / syntax_ok / rc0 / strict / degraded / degraded_todos / crash`。
> `degraded = rc==0 且含 # TODO`（严格口径，`docs/PROJECT-OVERVIEW.md` §「指标口径」）。
> **仪器可信 → 本 session 后续一切数字以此为基准。**

---

## 1. 已有归因盘点（任务书 §二）

按「维度 / 对象 / 时点」清点 `docs/` 下与 degraded 归因直接相关的文档：

| # | 文档 | 时点 | 归因维度 | 覆盖对象 | 时点是否当前 |
| ---: | :--- | :--- | :--- | :--- | :--- |
| 1 | `docs/v1.8.1-attribution.md` | v1.8.1 | Windows 命令映射表（37 条，`evidence` 必填） | 映射层 | 机制仍在（`mappings/windows_tools.py`） |
| 2 | `docs/v1.8.3-attribution.md` | v1.8.3 | **A 缺陷 / B 源畸形 / C 环境依赖 / D 交互挂起 / S 测量 artifact / ENV** | 46 条 rc≠0 | 分类法沿用中 |
| 3 | **`docs/v1.9.1-attribution.md`** | **v1.9.0** | **L1–L5 层**（L1 现有设施 / L2 单命令 / L3 子系统 / L4 语义理解 / L5 源畸形） | **86 degraded（全量）/ 914 TODO** | ⚠️ **陈旧**（现 82 / 851） |
| 4 | `docs/v1.11.0-reclassification.md` | v1.11.0 | **桶归属**（goto/regsvr32/registry/sc/thirdparty/l4obj/for/attrib/office/other）+ **「涉及文件 / 单设施文件」两列** | 86 degraded / 894 TODO，**逐条 29+17+10 行** | ⚠️ **陈旧**（现 82 / 851） |
| 5 | `docs/v2.2.0-reality-check.md` | v2.2.0 | **可翻转文件数**（实测协议：不数 TODO，数可翻转文件） | goto 回跳/块内/P5/sc/registry/B5 | 协议有效，数字陈旧 |
| 6 | `docs/v2.3.0-reality-check.md` | v2.3.0 | 同上 + 触 053 / 需 CFG 高级 两列 | 同上 | 协议有效，数字陈旧 |
| 7 | `docs/v2.3.0-2x-closure.md` §2.2 | v2.3.0 | **桶 × rc==0 单桶文件数 × 归属** | 85 degraded | ⚠️ **陈旧**（现 82） |
| 8 | **`docs/v2.5.0-report.md` §1/§4/§5.1/§10.1** | **v2.5.0** | **goto 8 形态归属 + CFG 实测翻转 + wine 12/12** | CFG 影响面 | 有效（本轮未变） |
| 9 | `docs/v2.5.0-verification.md` §三 | v2.5.0 | 发布门槛指标（degraded 82） | 全语料 | 有效 |
| 10 | **`docs/v2.6.0-corpus-attribution.md`** | **v2.6.0** | **A/B/C/D/S + CFG on/off 隔离 + 新语料** | **79 新语料**（与老 151 零重叠） | 有效 |
| 11 | `docs/ps-assessment-reality.md` / `-verdict.md` | v2.8.1 | 语义/语法上限（strict 0/664，硬 D 41.7%） | PS 664 | 有效 |

### 1.1 一个重要事实：归因已**内建在产品里**

本 session 对 82 个 degraded 的 **851 条 TODO** 逐条提取 `message` 的括注 reason，得到
**51 种互异 reason 字符串**（完全枚举，非抽样）：

| reason（截断） | TODO 数 |
| :--- | ---: |
| （COM 组件注册机制在 Linux 无对应物，目标物不存在，保持诚实 TODO。） | **216** |
| （goto 跨函数跳转无法自动重构，请手动改为函数调用或循环） | **206** |
| （Windows 服务名在 Linux 无同名 systemd unit，请手工确认等价服务后再用 systemctl） | **169** |
| （Linux 无统一可写注册表，请改为编辑对应配置文件） | **29** |
| （如 setupapi）属 Windows 专有机制，目标物不存在。） | 21 |
| （语料自带 Windows 控制台工具，目标物不存在。） | 21 |
| （beep 等），目标物不存在。） | 17 |
| （重定向或字面量），无法自动转换） | 15 |
| （运行期可能为空），静态不可知，已保守标记） | 14 |
| （Windows 可执行文件在 Linux 无对应物） | 14 |
| （`C:\…` 与 `/usr`、`/opt`、`/usr/local` 语义不同），硬映射会产出「看似对、实际错」的路径） | 12 |
| （如 `%date%`/`%time%`）做子串依赖 Windows 区域格式，静态不等价） | 11 |
| （start 的目标 regedit 在 Linux 无对应物，请手工改写） | 9 |
| （tokens/delims/usebackq）） | 9 |
| （`if /i` 含通配符或复杂表达式，无法自动转换） | 8 |
| …（余 36 种，1–7 条/种） | … |
| **合计** | **851** |

> **含义**：degraded 的**根因分类已经是转换器的输出**，而不是需要外部矩阵去补的空白。
> 51 种 reason 的粒度**细于** ChatGPT 建议的任何「按可泛化性分 3 类」的方案。

---

## 2. 已有归因的覆盖（任务书 §2.1）

| 文档 | 归因维度 | 覆盖 |
| :--- | :--- | :--- |
| v1.9.1 | L1–L5 层（可修难度） | **全部** degraded（86 条，时点为 v1.9.0） |
| v2.5.0 | goto 形态（8 形态逐项归属）+ CFG 实测 | CFG 影响面；**实测翻转 0**（strict 19→19） |
| v2.6.0 | A/B/C/D/S 类 + CFG on/off 隔离 | 79 新语料（27 degraded） |
| v1.11.0 | 桶归属 + 单设施文件 + 逐条归属 | 86 degraded / 894 TODO |
| v2.2.0 / v2.3.0 | 可翻转文件数（实测协议） | 各重点项，裁定「翻转 0」 |
| v1.8.3 | A/B/C/D/S/ENV 根因分类法 | 46 条 rc≠0（分类法为后续沿用） |
| ps-assessment | 语义上限 | PS 664 |

**结论**：已有归因**覆盖全部 degraded**，且**两个维度都齐**——「根因」（A/B/C/D/S、L1–L5、10 桶、51 reason）
与「影响面 / 可翻转性」（单设施文件数、可翻转文件数、桶 × 文件矩阵）。

### 2.1 已有归因是否覆盖「可泛化性」

| ChatGPT 的「可泛化性」的等价测量 | 已有文档是否已有 |
| :--- | :--- |
| 「这条规则涉及几个文件」 | ✅ **`v1.11.0-reclassification.md` §0 表第 3 列「涉及文件」**（逐桶） |
| 「这个文件是否只被一条规则阻塞」 | ✅ **同表第 4 列「单设施文件」**（逐桶） |
| 「一个文件能否被单一规则翻转」 | ✅ **`v2.2.0`/`v2.3.0-reality-check.md` 的「可翻转文件数」列**（逐项） |
| 「一规则一文件 vs 一规则多文件」 | ⚠️ **未以单一标量命名**，但可由上两列直接导出（本 session 已导出，见 `attribution-meta-value.md` §3） |

> **判定**：**「可泛化性」维度已被隐式覆盖**（以「涉及文件 / 单设施文件 / 可翻转文件」三列的形式）。
> ChatGPT 的建议**新增的是一个标量名（Generalization Ratio），不是一个新的分析维度**。

---

## 3. ChatGPT 建议的增量（任务书 §2.2）

| ChatGPT 维度 | 已有归因是否覆盖 | 证据 |
| :--- | :--- | :--- |
| root cause 聚类 | ✅ **已覆盖，且粒度更细** | v1.8.3 A/B/C/D/S 五分法 + v1.9.1 L1–L5 五分法 + v1.11.0 十桶 + **产物自带 51 种 reason** |
| 可泛化性 | ✅ **已隐式覆盖** | v1.11.0 §0「涉及文件 / 单设施文件」；v2.2/v2.3「可翻转文件数」 |
| Generalization Ratio | ⚠️ **未命名**（可零成本导出） | 本 session 已算出：规则级 **0.96 文件/规则**；历史执行规则 **≤1.00**（见 value §3） |
| 预期影响（files） | ✅ **已覆盖** | v1.9.1 §5.1–5.4「覆盖 TODO」列；v1.11.0 单设施文件数；v2.2/v2.3 可翻转文件数 |

**增量判定**：4 项中 **3 项已被覆盖**，1 项（GR）是一个尚未命名的标量，可由已有数据在只读条件下直接算出。
「按可泛化性分类 82 个 degraded」**不会新增信息**，只会换一种投影重排已有结论。

---

## 4. 偏离与置信度披露（纪律 3/4/5）

| # | 项 | 说明 | 置信度 |
| ---: | :--- | :--- | :---: |
| 1 | **`v2.5.0-reality-check.md` 不存在** | 内容在 `v2.5.0-report.md` §4/§5.1 + `v2.5.0-verification.md` §三；**未按字面触发暂停条件**（见 §0 表 #4） | A |
| 2 | **「v2.6.0 新增的映射」不存在** | `git log 2ffa49b..v2.6.0` = 3 commit，唯一代码改动 `306ea35`（`core/cfg_state.py` `_merge_report`，36 行）——**v2.6.0 零新增映射**。任务书 §3.3 的前提不成立；本 session 改为对**现存 82 degraded 的规则级泛化比**与**历史已执行映射的泛化比**做实测（value §3） | A |
| 3 | 桶边界为**独立复算**，非重跑原探针 | v1.11.0 §0 已声明「分桶为主观判定」；本 session 按同文档判据重新实现，`registry 31` vs 原 `29`、`goto 223` vs 原 `240–255`、`l4obj 51` vs 原 `32`、`for 16` vs 原 `30`、`thirdparty 50` vs 原 `61`。**差异已定位**（`删除右键"新建"菜单项目.bat` 的 2 条 `reg delete` 在两种口径下分别落 `registry`/`goto`；`start /w regedit` 与 MMC 组落 `l4obj`）。**不影响结构结论**（单桶 61 / 多桶 20 / marker 1） | B |
| 4 | v1.9.1 的 L1–L5 计数**未重做**（纪律 5） | 该文档时点为 v1.9.0（86/914）；现 82/851。差值来自 v2.5.0 的 4 文件定义性 `rc0` 位移与 v2.6.0 的 A-1 计数校正，**已有归属**，不重算 | A |
| 5 | 只读边界 | 未改任何仓库文件；探针在 `/tmp/meta-audit/`（`probe_*.py` / `probe_targets.sh`）；measure 产物在 `/tmp/meta-audit/*`。`git status` 收尾仍为空 | A |

---

> **本文件为归因盘点（阶段一）。** 增量评估见 `docs/attribution-meta-value.md`；
> 判定见 **`docs/attribution-meta-verdict.md`**（核心）。
