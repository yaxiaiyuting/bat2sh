# Session B1/B2 冷启动自检（只读阶段产出）

> 会话：`session-b1b2`（B1 名称映射 + B2 输出契约 → v1.10.0a1 pre-release）
> 纪律：本文件为**冷启动自检**，只读；写于任何代码改动之前。
> 时间：2026-09-17。分支起点 HEAD = `7048e6c0b59d75b5a28c856c6f8072f03197159a`。

---

## 1. 前置确认（任务书第一节，硬性）

| # | 检查 | 命令 | 结果 |
| :--- | :--- | :--- | :--- |
| 1 | v1.9.2 已发布 | `git tag -l v1.9.2`；`gh release view v1.9.2` | ✅ tag 存在；Release `bat2sh v1.9.2` 存在（`publishedAt 2026-09-16T16:50:50Z`，非 pre-release、非 draft） |
| 2 | 工作区干净 | `git status --porcelain` | ✅ 空 |
| 3 | pytest 全绿 | `python -m pytest -q` | ✅ **1262 passed in 80.04s**（≥1244） |
| 4 | 记录 HEAD | `git rev-parse HEAD` | ✅ `7048e6c0b59d75b5a28c856c6f8072f03197159a` |

**分支**：`session-b1b2`（`git checkout -b` 自 `main`；`git pull` 后 `main` 与 `origin/main` 一致）。
**分支起点 HEAD（回滚点）** = `7048e6c0b59d75b5a28c856c6f8072f03197159a`（已落盘 `/tmp/b1b2/head.lock`）。

**四项全部满足 → 不暂停，继续。**

---

## 2. 本次读过的文档（按任务书第三节顺序）

1. `docs/PROJECT-OVERVIEW.md`（448 行，含 §8.1 会话并发写入防护）
2. `docs/v1.x-roadmap-research.md`（932 行，r2；重点 §1.B B1/B2、§1.C C3/C7、§3 路线图、§3.4 文件级 ROI、§4 验收标准、§5 风险）
3. `docs/v1.9.1-attribution.md`（375 行，L1–L5 分层与 §5 设施清单）
4. `docs/research/chenpi11-cmd-reference.md`（322 行；oracle 权威顺序与 `%VAR%` 冻结）
5. `python/bat2sh/mappings/windows_tools.py`（481 行，`ToolMapping` + `validate_mappings()`）
6. `docs/v1.9.2-design.md`（254 行，v1.9.2 基线）＋ `docs/v1.9.2-rounds.md`（148 行，指标口径）＋ `docs/releases/v1.9.2.md`

配套只读代码：`core/rules.py`（543 行，`BATCH_SIMPLE_MAP`/`BATCH_HANDLER_MAP`/`BATCH_ENV_MAP`）、
`core/batch.py`（3736 行；`mapping_for` 派发 `:2724-2750`、`env_repl` `:1084-1117`、
`cmd_ipconfig` `:3176`、`_env_substring_todo` 行级 TODO 机制 `:2659-2669`）、
`mappings/__init__.py`、`tests/test_mappings_windows_tools.py`、`tools/oracle/golden_harness.py`。

---

## 3. 用自己的话复述

### 3.1 B1 是什么

B1 不是「再加几条命令映射」。现有两条映射资产（`windows_tools.py` 覆盖**命令**、
`registry_map.py` 覆盖**注册表键路径**）都回答不了「同一个东西在另一边叫什么名字」：

- 同一个**服务**：Windows 的 `wuauserv` / `Spooler` 在 systemd 侧叫什么 unit；
- 同一个**路径根**：`%ProgramFiles%` / `%AllUsersProfile%` / `C:\` / `\\host\share` 在 Linux 语义上落在哪；
- 同一个**环境变量**：`%USERPROFILE%` / `%APPDATA%` … 对应哪个 shell 变量。

B1 要建的是**第三张、面向「名称」的结构化表**：与 `windows_tools.py` 同构（`evidence` 必填、
`confidence` A/B/C/D、`validate_*()` 在测试中守护），但键是**名字**而非命令；并要有
**降级策略**——凡是不能给出有依据的 Linux 名的，一律诚实 TODO，不得硬凑。

B1 **不含** `sc→systemctl`：那是 C7，已被路线图 r2（§3.1）后移 v2.0，任务书亦确认。
本 session 的 B1 首批用例 = **C3 路径/环境**（不依赖 goto）。

### 3.2 B2 是什么

B2 处理的是「**命令被正确翻译了，但输出形态不同**」这一层：
`ipconfig` → `ip addr` 命令是对的，但 `ip addr` 的输出**没有** `IP Address` 这种标签、
列位也不同；`for /f` 解析 `ipconfig` 输出的脚本会把东西解析错。
`windows_tools.ToolMapping.output_contract` 这个字段从 v1.8.1 就存在，但**只被 `notes` 里的
「输出格式」四个字约束着，不驱动任何行为**——B2 要把它从「文档标记」升级为**可执行契约**
（有结构、有校验、被转换器消费）。首批用例：`ipconfig`、`dxdiag`、`perfmon`。

### 3.3 路线图原来怎么假设 B1/B2

| 项 | 路线图裁定 | 计划归属 | 难度 | 风险 | 证据 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **B1** | **1.x 处理** | **v1.9.5**（与 C3 同版） | 4–6 人日 | 中 | §1.B：「当前**不存在**该子系统，仅散落 hint」；`rules.py:151-152` `net`/`sc` 只返回 hint；B1 是 C7 的前置 |
| **B2** | **2.x 处理** | **v2.0** | 8–12 人日 | **高** | §1.B：「1.x 只做『诚实 TODO/警告』收敛，**不做解析级适配**」；v1.8.3 §2.2 的流程感知改法 26/151 churn 被否 |
| 收益口径 | — | 文件翻转 **0**（B1/B2 都不是翻转批） | — | — | §3.4 设施 ROI：`path` 16 TODO/4 文件/**0 单设施翻转**；§3.1 明记「sc/errorlevel/path = TODO 多但文件翻转 0」 |

### 3.4 当前 HEAD

`7048e6c0b59d75b5a28c856c6f8072f03197159a`（= v1.9.2 发布后的 main；任务书称「当前 HEAD」，
本 session 起点与之一致）。

---

## 4. 前提核对（纪律：前提变了就停下报告）

| # | 路线图前提 | 本 session 独立复核 | 是否仍成立 |
| :--- | :--- | :--- | :--- |
| 1 | 版本 v1.9.2 已发布，HEAD 即其发布状态 | tag + Release + `pytest 1262` + 语料 147/102/16/86 全部复现（§5） | ✅ 成立 |
| 2 | B1 子系统**不存在**，只有散落 hint | `rules.py:151` `net`→`"请改用 systemctl/ss"`、`:152` `sc`→`"服务管理请改用 systemctl"`；`BATCH_ENV_MAP` 是**无 evidence 的裸 dict**；`registry_map.py` 只覆盖注册表键 | ✅ 成立 |
| 3 | B1 归属 **1.x** | 成立；但**版本号提前**：任务书把 B1 放进 v1.10.0a1（原 v1.9.5）。属**调度变化**，非前提失效 → 继续，并在 review 记录 | ⚠️ 调度变化 |
| 4 | B2 归属 **2.x**，1.x **不做解析级适配** | 复核确认：`cmd_ipconfig` 只 `_warn("输出格式不同")`＋发 `ip addr`；`ToolMapping.output_contract` 仅被 notes 子串校验（`windows_tools.py:48-49`），确实未驱动行为 | ✅ 成立 |
| 5 | **任务书把 B2 拉进本 session**，描述为「输出格式不同的适配」＋「契约升级为可执行」 | 与前提 4 **直接冲突**：若按字面做解析级适配，即触发路线图 §5 判为「概率高、影响中」的 B2 风险，且违反 §1.B「1.x 不做解析级适配」 | ❌ **冲突（需裁定）** |
| 6 | B1/B2 的收益能体现在文件翻转 | 复核 §3.4：`path` 0 翻转、`sc` 0 翻转、`ipconfig/dxdiag/perfmon` 命中的文件全部已被 goto/终态/语法失败阻塞 | ✅ 成立（= 0 翻转） |

### 4.1 因前提 5 产生的冲突，与任务书验收标准的张力

任务书 §七要求「151 语料指标对比 v1.9.2：**rc==0 提升、degraded 下降、崩溃 0**」。
但按路线图 §3.4/§3.1，B1（`path`）与 B2（输出契约）**预期文件翻转 0**，
且 B1/B2 的正确做法是「把静默错/静默透传**改成诚实 TODO/warn**」——这会**增加** degraded 计数
（诚实化），而不是减少。→ **「rc==0 提升、degraded 下降」在本 scope 内不可达**。

这不是「前提已变」（版本、代码、设施均与路线图一致），而是**任务书对本 session 的收益预期
与路线图 ROI 口径不一致**。处置：不暂停，在 `docs/session-b1b2-review.md` 中显式裁定
（收窄 / 退回），并在 release notes 与报告里**重述客观验收标准**＋主动披露偏离（纪律 3/4）。

---

## 5. 冷启动独立复跑（纪律 9：仪器先验证）

### 5.1 仪器缺陷的发现与修复（重要）

沿用路线图 r2 的仪器 `/tmp/roadmap/measure.py` 首次复跑得到
`strict_functional=0 / degraded=102`，与文档基线 `16/86` 不符。

**根因（已定位）**：产物的**固定脚本头**第 2 行是
`# 带有 # TODO 标记的行无法自动转换，请人工检查`（`core/batch.py:906`），
其中包含字面 `# TODO`。仪器用 `"# TODO" in res.text` 判定 marker → **任何产物都被判为含 TODO**，
strict 恒为 0、degraded 恒等于 rc==0 数。

**修复**：`/tmp/b1b2/measure.py` 的 marker 判定改为逐行扫描并排除该固定头行
（与 `docs/v1.9.1-attribution.md` §0.1「排除脚本头」一致）。

**修复后复现**（本 session 独立跑，`/tmp/b1b2/baseline_v192.json`）：

| 指标 | 文档 v1.9.2 | 本 session 复跑 | 一致 |
| :--- | ---: | ---: | :---: |
| pytest | 1262 | **1262 passed** | ✅ |
| 语料 | 151 | 151 | ✅ |
| 语法通过 | 147/151 | **147/151** | ✅ |
| rc==0（原始） | 102 | **102** | ✅ |
| rc≠0 | 45 | **45** | ✅ |
| 功能完好（严格） | 16 | **16** | ✅ |
| degraded | 86 | **86** | ✅ |
| 崩溃 / 超时 | 0 / 0 | **0 / 0** | ✅ |
| degraded TODO 总数 | 895 | **894** | ⚠️ **−1** |

> **仪器验证通过**：147/102/16/86 逐项与 v1.9.2 记录一致 → 仪器可用。
> **一处偏离（纪律 3）**：`degraded TODO 总数` 我测得 894，文档记 895（−1）。
> 已定位边界：`075 改名复制文件.cmd` 属「1 条标记 / 0 条登记」（A10），
> 它计入 degraded 文件数但对 TODO 总数贡献 0；文档 895 疑为 913−18 的算术值而非直接求和。
> 该差异为**仪器边界差**，不影响任何 headline 指标。后续所有 commit 的 TODO 总数均用**同一只新仪器**作纵向对比。

### 5.2 「145 分母口径」的口径更正（纪律 3）

任务书 §6.3/§8.5 写「151 语料重跑（**145 分母**口径）」。**实际不是 145**：

- `145/151` 是 **v1.8.3 时期**的语法通过数；v1.9.0 起为 **147/151**（v1.9.0 发布说明 §指标表）。
- v1.9.2 的 rc==0 分母（= 语法通过数）是 **147**，不是 145。
- 处置：本 session 一律按**当前真实分母 147** 记录 rc==0，并在报告/release notes 明示口径；
  不沿用任务书的 145，以避免「假分母」。

### 5.3 本 session 新增的只读探针（最小复现）

`/tmp/b1b2/probe.py`、`probe2.py`（均只读，仓库外）。关键复现（当前 HEAD 行为）：

| 输入 | 当前产物 | 判定 |
| :--- | :--- | :--- |
| `echo %ProgramFiles%` | `echo "${ProgramFiles:-}"` | ❌ **静默错**（无 TODO：运行期展开为空） |
| `echo %SystemRoot%\System32\cmd.exe` | `echo "${SystemRoot:-/}/System32/cmd.exe"` | ⚠️ 已映射 + warn（既有） |
| `dir \\server\share` | `ls -la "\\/server/share"` | ❌ **路径被拼坏**（`\` + `/server/share`），且无 warn/TODO |
| `dxdiag /t out.txt` | `dxdiag /t out.txt`（原样）+ 泛化 warn「未知命令」 | ⚠️ 运行期 `command not found`，非结构化 |
| `perfmon /report` | `perfmon /report`（原样）+ 泛化 warn「未知命令」 | ⚠️ 同上 |
| `ipconfig /all` | `ip addr show` + warn「输出格式不同」 | ✅ 命令层正确；输出契约缺口 |
| `for /f ... ('ipconfig ^| find /i "ip address"')` | 诚实 TODO（`core/batch.py:2230-2239`） | ✅ 已有（英文标签路径） |
| `for /f ... ('ipconfig ^| findstr "IPv4 地址"')` | `while … < <(ip addr \| grep "inet ")` | ✅ 已有 CJK 关键词映射 |

---

## 6. 回滚点

| 项 | 值 |
| :--- | :--- |
| 分支 | `session-b1b2` |
| 起点/回滚 HEAD | `7048e6c0b59d75b5a28c856c6f8072f03197159a` |
| 锁文件 | `/tmp/b1b2/head.lock`（内容同起点 HEAD） |
| 基线指标存档 | `/tmp/b1b2/baseline_v192.json`（本 session 复跑，仪器已验证） |
| 仪器 | `/tmp/b1b2/measure.py`（已修 marker 头行缺陷）+ `/tmp/b1b2/summary.py`（后处理汇总） |

---

## 7. 结论

- 前置四项**全部满足**；分支起点 HEAD 已锁定。
- 路线图前提 **1/2/3/4/6 仍成立**；**前提 5（B2 的 1.x 解析级适配）与任务书冲突** → 转入
  `docs/session-b1b2-review.md` 作显式裁定，不在冷启动阶段暂停。
- 发现并修复一处**仪器缺陷**（固定头行被当作 TODO marker）；修复后基线逐项复现 v1.9.2。
- 发现两处**任务书口径偏离**（145 分母；收益预期），已在 §5.2/§4.1 披露。
