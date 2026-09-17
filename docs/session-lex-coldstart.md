# Session C(lex) 冷启动自检 —— 词法层残余 → v1.10.0rc1（只读）

> 分支 `session-lex`（基于 `session-c4`）；会话起点 HEAD = **`68dfbdd`**（= `session-c4`
> 终点，bump commit `8fdae5f` + 其后仅文档 commit）。本文件**只读**产出：未改任何代码。
> 会话时间：2026-09-17。

---

## 一、前置确认（硬性，全部通过）

| # | 检查 | 结果 |
| :--- | :--- | :--- |
| 1 | `git tag -l "v1.10.0b1"` 有输出 | ✅ `v1.10.0b1` |
| 2 | 起点分支 = `session-c4`；起点 HEAD = `68dfbdd` | ✅ `68dfbdd325bb93e0c5d7c9222a3d62fb6c2079fb` |
| 3 | `git status` 干净 | ✅（空输出） |
| 4 | `pytest -q` 全绿 | ✅ **`1360 passed in 80.91s`**（本会话独立复跑，纪律 9） |

开分支命令已执行：`git checkout session-c4` → `git pull`（本地已最新，无 upstream 配置）
→ `git checkout -b session-lex`。**新分支 HEAD 仍 = `68dfbdd`**，已落盘
`/tmp/lex/head.lock`。

---

## 二、读了哪些文档

| # | 文档 | 用途 |
| :--- | :--- | :--- |
| 1 | `docs/PROJECT-OVERVIEW.md`（517 行，含 §8.1 + 纪律 13） | 口径 / 架构 / 块栈与 A1 说明 / 并发写入纪律 |
| 2 | `docs/v1.x-roadmap-research.md`（932 行，r2） | §3.4 文件级 ROI、1.x 下界 46/40、goto 设施 |
| 3 | `docs/session-c4-report.md` | 冲突锚点、Session C 起点、C4 残留 4 条 |
| 4 | `docs/session-b1b2-report.md` | Session A 的 4 处 `batch.py` 锚点 |
| 5 | `docs/v1.9.2-design.md` | A1 `%VAR%` 冻结实现（不得触碰的路径） |
| 6 | `docs/v1.8.3-attribution.md` | 053 同域历史（044/047/053/062 的 D 档归因） |
| 7 | `docs/research/chenpi11-cmd-reference.md` | oracle 权威顺序（ChenPi11 不可作 oracle） |
| 8 | `docs/session-c4-review.md` / `docs/session-b1b2-review.md` | 裁定范式与止损表 |
| 9 | `docs/v1.9.1-attribution.md`（局部） | 135/026/044 的 L1–L5 归因 |

**只读代码锚点**：`core/batch.py`（`_Block` :484、`_guard_unset_variable_refs` :677、
`_compose` :903、`_expand_vars` :926、`_pop_block` :1360、`_close_block_line` :1395、
`_convert_paren_block` :1517、`_label_line` :1585、`_convert_goto` :1623、`_convert_if` :1713、
`_convert_for` :2091、`_emit_for_f` :2208、`_register_assigned` :3535、
`_protect_arith_modulo` :131、`loop_repl`/leak 守卫 :928–935 + :2695–2703、
自动补全警告 :3765）；`git show 61a4b44`（053 修复）。

### 2.1 偏离披露（纪律 4）

- **子代理不可用**：本会话 `task(explore)` 两次均 `ProviderModelNotFoundError:
  Model not found: openai/gpt-5.6-luna-fast`（与路线图 r2 §0.3(2) 记录的同一环境缺陷）。
  故全部研究/诊断由主控用只读工具完成，**无子代理交叉复核**。
- **任务书编号与仪器口径不一致**（见 §3.1），已按「文件名 + 仪器 ID」双向核对后处理。

---

## 三、用我自己的话复述

### 3.1 「词法层残余」是什么

前序会话把 bat 转换器的缺陷按层归因。**块栈/词法层**指：`for`/`if`/`else`/`(` 组的
**括号与循环变量配平**（`_Block` 流式块栈、`_pop_block`、`_close_block_line`、
`_convert_for`/`_convert_if`/`_emit_for_f`）以及**变量/百分号的切分**（`_expand_vars`、
`_protect_arith_modulo`、`env_repl`）。053 的「块栈失同步」已于 **v1.9.0（`61a4b44`）** 修复；
A1 的 `%VAR%` 冻结语义已于 **v1.9.2** 修复。本 session 处理的是**这两次修复之后仍在的残余**：
转换产物出现 `# TODO: 手动检查: …（循环变量 %%x 逸出 for 循环（块结构失同步）…）`
的文件，即转换器**自认为**把某个 `%%X` 丢了循环归属。

**关键前提**：这是**转换器视角**的「失同步」。本会话最重要的发现是：这 4 条里
**只有 2 条真的是块栈失同步**，另 2 条是**守卫误报**（词法层切分问题），见 §3.2。

### 3.2 4 条残余的具体形态（本会话实测）

仪器口径（复用 C4 的只读探针逻辑，本会话在 `/tmp/lex/` 复算）：
**degraded 文件**（`rc==0` 且含 `# TODO`）× TODO 消息含
「循环变量 %%x 逸出 for 循环（块结构失同步）」→ 恰 **4 个文件**。

> ⚠️ **任务书编号核对（纪律 3）**：任务书列 `059 判断分区格式.bat` 与
> `138 批处理生成的CMD命令帮助清单.bat`。按**规范排序口径**（`sorted(relpath)`，即
> `/tmp/b1b2/measure.json`、`/tmp/c4/measure.json` 与 v1.8.3-attribution 共用的编号），
> 实际的 059/138 是**另外两个文件**；任务书给的两个文件名分别排在 **026 / 062**，
> 且**都不是本 session 的靶子**（026 的 TODO 是 `for /f chkntfs` + `goto`；062 是
> `cmd /c` 引号/命令替换，属 rc≠0 的 D 档）。**以仪器实测为准**：

| 仪器 ID | 文件（实测） | todo | 本会话判定的真实机制 | 是否真·块失同步 |
| :--- | :--- | ---: | :--- | :--- |
| **044** | `备份文件/备份服务.bat` | 7 | `for /f … do ( … & for /f … do …)`：**`_convert_for` 头部正则贪婪**，把外层 `for` 的 `in (…)` 切到内层 `for` 的 `)` 上 | ✅ 是（头切分） |
| **059** | `打开快捷方式指向的目录.bat` | 2 | 真实 `%%i` 落在 `start … cmd /c "…"` 的**引号字符串内**；cmd 语义 = 字面 `%i`；转换器把它当 for 变量→**守卫误报** | ❌ 否（词法误报） |
| **135** | `系统优化.bat` | **443**（v1.9.1 记 439） | 与 044 **同构**（多一层嵌套 `for /f`） | ✅ 是（头切分） |
| **138** | `获取U盘盘符和可用容量.bat` | 7 | `set /a m3=%m3%%m:~0,1%%%%~1`：`_protect_arith_modulo` **不识别 `%VAR:~n,m%` 子串式**，把其收尾 `%` 与后随 `%` 配成取模 → 制造出伪 `%%m` → **守卫误报** | ❌ 否（词法误报） |

**最小复现（本会话实测，`/tmp/lex/repro.py`）**：

- **044/135 同构**（`&` 或 `&&`、`/f` 或普通 `for` 均可）：
  `for %%j in (a) do (for %%s in (b) do echo %%j %%s)` → TODO「逸出」，
  `m2/m5` 变体甚至 **`bash -n` 失败**。
- **059**：`start "t" cmd /c "…for /l %%i in (5,-1,1) do cls…"` → TODO「逸出」；
  更简：`echo "for /l %%i in (…)"` 也 TODO。
- **138**：`set /a m3=%m3%%m:~0,1%%%%~1`（**顶层、无任何 for**）即 TODO「逸出」。

**wine 语义锚定（本会话实测，纪律 9）**：

| 探针 | wine cmd 输出 | 结论 |
| :--- | :--- | :--- |
| `echo %%m` | `%m` | `%%X` 在 for 外 = 字面 `%X`（**不是**循环变量） |
| `echo "for /l %%i in (5,-1,1) do cls"` | `"for /l %i in (5,-1,1) do cls"` | 引号内 `%%X` = 字面 `%X` |
| `for %%i in (a b) do echo [%%i]` | `[a]` `[b]` | for 内 = 循环变量 |

→ 059/138 的插值**语义明确**（字面 `%X`），转换器的 TODO 是**过度保守的守卫误报**；
044/135 的 `%%j/%%s` 在源里**确实**是循环变量，转换器的 TODO 是**头切分错误**的诚实兜底。

### 3.3 当前 HEAD

**HEAD = `68dfbdd`**（分支 `session-lex`；`git rev-parse HEAD` 已落盘 `/tmp/lex/head.lock`）。
回滚点 = `68dfbdd`。

---

## 四、前提核对（纪律 3/9）

| # | 任务书前提 | 核对结果 | 判定 |
| :--- | :--- | :--- | :--- |
| 1 | 「4 条是 Session C 靶子」 | **数量与 ID 成立**（044/059/135/138 恰为 degraded × 失同步守卫的 4 个）；**但文件名为 2 处错记**（059/138 见 §3.2）；**且机制并非统一「块失同步」**（2 真 2 误报） | ⚠️ **部分不成立**（见 §五） |
| 2 | 路线图 §3.4「1.x 下界 46/40」仍成立 | ✅ 成立。46/40 是**设施桶定义**的口径（86 degraded 按「可做设施 vs 阻塞设施」分），自 v1.9.0 起转换产物**零变更**（B1/B2 与 C4 报告均记 0 字节 diff），故该口径不变 | ✅ |
| 3 | goto 阻塞 degraded 实测 **22**（非路线图 **16**） | ✅ **口径差异已澄清**：本会话复算 `/tmp/c4/measure.json` → degraded **86**；其中**含 ≥1 条 goto TODO 的 degraded = 22 文件**、goto TODO 总数 **1362**；路线图 §3.4 的 **16** 是「**阻塞设施桶含 goto** 的文件数」（更严的口径）；C4 另记「**唯一阻塞 = goto** 的 degraded 仅 **3**」。**三者定义不同，均正确**，不得互相套用 | ✅（口径澄清） |
| 4 | v1.9.1 记 135 = 439 TODO；本会话实测 **443** | ⚠️ 偏差 +4：A1 快照 marker / B1/B2 诚实 TODO 引入所致（同一只仪器下 B1/B2/C4 均为 443）。**如实记录** | ⚠️ 已披露 |

**结论**：前提 **未到「已变」程度**（靶子文件集与口径均可定位），但**任务书的「真块失同步」
标签与 2 个文件名有误**。按纪律「任何不确定 → 停」的精神，该差异**不触发暂停**，
但写入审阅（`session-lex-review.md`）作为裁定输入。

---

## 五、是否暂停

**不暂停**，理由：① 4 个靶子文件可用仪器精确定位，编号差异是标注问题而非范围漂移；
② 分支/HEAD/工作区/测试四项前置全部通过；③ 与路线图/前序会话的口径冲突均已定位并披露。
后续按任务书第五节进入**只读自我审阅**。
