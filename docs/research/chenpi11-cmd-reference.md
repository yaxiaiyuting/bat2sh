# ChenPi11/cmd 源码参考可行性分析（bat2sh 深水区参考研究）

> 对象：https://github.com/ChenPi11/cmd —— 在 Unix 上以 C89 重新实现的 `cmd.exe` 解释器。
> 方法：**只读**。本地 clone（`/tmp/ext/cmd-chenpi11`，commit `2290c38`）+ `make` 构建 +
> 与 `wine cmd`（第二 oracle）对照实跑。bat2sh 仓库**未修改**；探针均在 `/tmp/ext/` 下。
> 研究时间：2026-09-16。

---

## 0. 结论速览

| # | 目标 | 结论 | 标注 |
| :--- | :--- | :--- | :--- |
| 1 | 块处理逻辑 → bat2sh 状态机规则 | **不可用（作为正确性模型）**；仅「括号组=不透明 token」思想可用 | ⚠️ 详见 §2 |
| 2 | 展开时机建模 → 修 114 | **部分可用（需适配）**：`%VAR%` 冻结模型正确且有价值；`!VAR!` 模型**是错的** | ⚠️ 详见 §3 |
| 3 | 括号歧义处理 → 直接用于 bat2sh | **需适配**：规则清晰，但**依赖跨行括号配平累积**，而 ChenPi11 恰恰缺这个 | ⚠️ 详见 §4 |
| 4 | 黄金行为对照 / 自动化流程 | **可行，但 oracle 必须换成 wine 的 `cmd`**；ChenPi11 **不能**当 oracle | ✅ 已演示（§5） |

### ⚠️ 两条必须先说的披露（纪律 4）

1. **任务前提已过时**：053 的块栈失同步**已在 v1.9.0 修复**（commit `61a4b44`，5 hunk 非词法层补丁），
   最小复现与真实语料均已正确嵌套（见 §5 的 g01/g02/g03 全 MATCH）。本报告因此把问题重述为：
   **ChenPi11 对「已修的 053」以及「未来若重写解析层」是否有参考价值**——答案是「作为反面/思想参考，不作为模型」。
2. **ChenPi11 的块处理本身是错的**：它对 053 构造**失败方式与 bat2sh 修复前同类**（多行 `else (` 体被提升到
   循环之外）。因此**不能**把它的块处理「翻译成 bat2sh 规则」——那会把 bug 一起搬进来。

---

## 1. 仪器先验证（纪律 9）

| 项 | 结果 |
| :--- | :--- |
| clone | 成功，`git log` 仅 **1 commit**（`2290c38 fix: Fix #2.`） |
| 构建 | `make` 成功，产出 `cmd.exe` / `COMMAND.COM`（`-O3 -Wall -Wextra -Wpedantic` 无阻断） |
| 冒烟 | `cmd.exe /c t1.bat` 正常；`/?` 输出中文帮助（i18n 生效） |
| 第二 oracle | `wine` + `~/.wine/.../cmd.exe` 可用（`WINEDEBUG=-all` 抑制噪声） |
| 规模 | 5 个核心文件共 **3421 行**（cparser 907 / cinterp 860 / bfor 736 / cvars 608 / bif 310） |
| 许可 | **GPLv3**（bat2sh 为 AGPL-3.0-or-later；均 copyleft，**只借鉴思想、不抄代码**） |
| 测试 | 仓库内**无测试目录/文件** |

---

## 2. 目标 1：块处理机制对比

### 2.1 ChenPi11 的架构：AST + argv 重建，**不是**流式块栈

1. **解析器产 AST**：`cparser.c:36-43` 定义节点类型 `NODE_SIMPLE / PIPE / AND / OR / SEQ / GROUP`；
   `cparser.c:65-82` 的 `struct cmd_node` 只有 `argv` 与 `left/right`——**没有**块深度/括号栈字段。
2. **解释器无块状态**：`ccontext.h:73-121` 的 `cmd_context_t` 里**没有** paren/block 相关成员
   （只有 `call_stack`/`local_stack`/`dir_stack`，都跟块无关）。
3. **`if`/`for` 是普通 builtin**（`bif.c`/`bfor.c`），拿到的只是 `argv`；块体由它们
   **从 argv 重新拼字符串，再递归调用 `cmd_run_line`**：
   - `bif.c:258-289`：线性扫描 argv 找 `ELSE`（**无深度跟踪**），`then_cmd`/`else_cmd` = `rebuild_cmd(...)`；
   - `bfor.c:698-706`：`do_cmd` = 把 `argv[argi..]` 用空格拼回一个字符串。
4. **括号**：`cparser.c:514-525` 的规则是——
   - `(` 出现在**命令首**（`argc == 0`）→ `NODE_GROUP`（真块，`cparser.c:432-441`）；
   - `(` 出现在**已有词之后**（`argc > 0`）→ 把**整段已配平** `(...)` 收集为**单个不透明 token**，
     交给 builtin 自行解析（`bfor`/`bif`）。
5. **多行**：`cinterp.c:414-462` 的 `read_line()` **只做 `^` 续行**（`:434`）；
   批处理主循环 `read_line → cmd_run_line`（`cinterp.c:634`/`713`）。
   **没有任何「括号未配平则继续读下一行」的累积逻辑。**

### 2.2 与 bat2sh 的对比

| 维度 | ChenPi11/cmd | bat2sh（v1.9.0 后） |
| :--- | :--- | :--- |
| 模型 | 解释器：AST + 递归 `cmd_run_line` | 转换器：**流式块栈**（`_Block`/`await_paren_close`/`finish_parent`） |
| 块归属 | 由 `if`/`for` builtin 从 argv 重建 | 由 `_convert_if`/`_convert_for`/`_emit_for_f` 发射 + `_pop_block` 收尾 |
| 多行块 | **不支持**（只 `^` 续行） | **支持**（`await_paren_close` + `)` 收尾） |
| 括号歧义 | 首 token=块，否则整段配平括号=不透明 token | `find_matching` + 前缀判据（`text.startswith("(")`） |

### 2.3 实跑证据（053 构造）

`/tmp/ext/work/r1.bat`（与 053 同构）：

```bat
@echo off
for %%i in (a b) do if %%i==a (echo A ) else (if %%i==b (echo B ) else (
echo body1
echo body2
))
echo after
```

| oracle | 输出 | 判定 |
| :--- | :--- | :--- |
| **wine cmd** | `A` / `B` / `after`（body1/body2 **不执行**） | ✅ 正确 |
| **ChenPi11** | `A` / `B` / **`body1` / `body2`** / `after`（body 被**提升到循环外**） | ❌ 错误 |
| bat2sh v1.9.0 | `A` / `B` / `after` | ✅ 正确 |

多行 `for` 体（`/tmp/ext/work/mf.bat`）：

| oracle | `for %%i in (x y) do ( \n echo item=%%i \n )` |
| :--- | :--- |
| wine cmd | `item=x` / `item=y` ✅ |
| ChenPi11 | **`item=%i`**（只跑一次、且在循环外、`%%i` 未替换）❌ |

多行 `if`（`/tmp/ext/work/mb.bat`）：

| oracle | `if 1==1 ( \n echo then-branch \n ) else ( \n echo else-branch \n )` |
| :--- | :--- |
| wine cmd | `then-branch` / `end` ✅ |
| ChenPi11 | `IF: 语法错误` + `then-branch` / **`else-branch`** / `end` ❌ |

**判定：ChenPi11 的块处理逻辑不能翻译成 bat2sh 状态机规则。**
它的失败模式（多行块体被降级为「行外顺序执行」）正是 bat2sh 修复前 053 的同类症状；
其根因是**缺少括号配平的行累积**，而非另一套更正确的算法。

**唯一可借鉴的思想（→ 需适配）**：`cparser.c:514-525` 的
「**行首 `(` = 块；否则整段已配平 `(...)` = 单个不透明 token，交由命令自行解析**」。
它把「`echo (` 是参数」与「`( ... )` 是块」用**位置**（是否命令首）区分开，
比按字符猜括号更稳。但前提是括号在逻辑行内配平——而这正是 ChenPi11 缺的、bat2sh 已有的能力。

---

## 3. 目标 2：变量展开时机

### 3.1 ChenPi11 的模型

- `cvars.c:424` 的 `cmd_expand_vars(ctx, line)` 是**单遍文本展开器**：`%%`→`%`、
  `%VAR%`→值、`!VAR!`→值（仅当 `ctx->delayed_expand`）。
- `cinterp.c:123` 在 `cmd_parse` **之前**对**整条逻辑行**调用一次展开；
  builtin 递归调用 `cmd_run_line` 时**会再展开一次**。
- `cvars.c:52-108` `lookup_var`：未定义变量返回 `NULL`，调用方**不输出任何字符**
  → **未定义变量 = 空串，绝不报错**（cmd 语义的忠实建模）。

### 3.2 实跑：两种展开的时机**并非都正确**

`/tmp/ext/work/ea.bat`（立即展开）与 `eb.bat`（延迟展开）：

```bat
set v=1
for %%i in (a b) do (set v=2 & echo immediate=%v%)     :: ea
setlocal enabledelayedexpansion
set v=1
for %%i in (a b) do (set v=2 & echo delayed=!v!)       :: eb
```

| 用例 | wine cmd（正确） | ChenPi11 | bat2sh v1.9.0 |
| :--- | :--- | :--- | :--- |
| ea `%v%` | `immediate=1` ×2 | `immediate=1` ×2 ✅ | **`immediate=2` ×2 ❌** |
| eb `!v!` | `delayed=2` ×2 | **`delayed=1` ×2 ❌**（冻结了） | `delayed=2` ×2 ✅ |

114 原始形态（`/tmp/ext/work/v114.bat`）：

```bat
setlocal enabledelayedexpansion
set str1=
for %%i in (a b) do set str1=!str1!%%i
echo [%str1%]
```

| oracle | 输出 |
| :--- | :--- |
| wine cmd | **`[ab]`** ✅ |
| ChenPi11 | **`[b]`** ❌（`!str1!` 在 for 行解析时冻结为空） |
| bat2sh v1.9.0 | `[ab]` ✅（v1.8.3 已修：先替换后登记，自引用得 `:-`） |

### 3.3 结论与可用点

- **ChenPi11 的 `!VAR!` 模型是错的**（把「执行时求值」实现成了「行解析时冻结」）→
  **不能用它指导 114**。114 本身已在 v1.8.3/v1.9.0 修好（自引用 `:-` 守护 + 顺序调整）。
- **可用的语义佐证**：`cvars.c:52-108` 明确建模「**未定义变量 → 空串，不报错**」。
  这为 bat2sh 的 `_guard_unset_variable_refs` 采用 `${X:-}` 提供了**语义依据**：
  在 cmd 里未定义引用本就是空串，`:-` 是**语义等价**而非「防御性猜测」。
- **可用的设计点（`%VAR%` 冻结）**：ChenPi11 把 `%VAR%` 在**行解析时展开一次**，
  循环体内**不再变化** → ea 用例正确。**bat2sh 当前把它错译成了运行时活引用**
  （§5 的 g05 证据）。这是本次分析发现的**真实缺陷**，且**ChenPi11 的正确面正好指向修法**。

---

## 4. 目标 3：解析器括号歧义

### 4.1 ChenPi11 的规则（`cparser.c`）

| 情形 | 处理 | 行号 |
| :--- | :--- | :--- |
| `(` 位于**命令首**（`argc == 0`） | `NODE_GROUP`（真块，递归 `stmt_list` 到 `)`） | `:432-441` |
| `(` 位于**已有词之后**（`argc > 0`） | 收集**整段已配平** `(...)` 为**单个 argv token** | `:514-525` |
| `)` | 终止当前词收集（`break`） | `:~488` |
| 未配平（行尾 `depth > 0`） | **不闭合**：token 只到行尾，**无跨行续读** | `:520-525` + `cinterp.c:434` |

所以 `echo (`、`for /f in ('...')`、`if x==1 (…)` 都能被区分：
- `echo (` → `echo` 之后 `(` → 不透明 token → 交给 `echo` 当参数；
- `for /f ... in ('dir/b *.bat')` → `in` 之后的 `('...')` 是配平组 → 不透明 token → `bfor` 自行解析；
- `if x==1 (…)` → `if` 之后的 `(…)` 是不透明 token → `bif` 重建后再递归解析。

### 4.2 对比 bat2sh 的 053 根因

bat2sh 的 053 根因（v1.9.0 前）：`_convert_if` 对**行尾未配平**的 `else (` 仍 `pop`+补 `fi`，
与对称的 `_close_block_line`（保留 `await_paren_close` 块）不一致 → 块栈失同步。

ChenPi11 **不存在**这个不一致（它压根没有块栈），但它**用另一种方式失败**：
未配平就丢弃闭合，靠「下一行当独立行执行」。**两者是同一难点的两种错误解**。

### 4.3 判定

**需适配**。「行首 `(`=块 / 否则配平组=不透明 token」是**可直接采用的判据**，
但**必须配合「括号未配平时继续累积下一行」**（ChenPi11 缺、bat2sh 已有）。
若未来 bat2sh 重写解析层为 AST，这条判据 + 行累积是**推荐组合**；
当前 v1.9.0 的流式块栈已能正确处理 053（§5 g01–g03 全 MATCH），**无迁移必要**。

---

## 5. 目标 4：黄金行为对照（自动化流程）

### 5.1 oracle 选择（关键）

- **ChenPi11 不能作 oracle**：它在 053 构造上输出错误结果（§2.3），
  用它做黄金值会把 bug 固化。
- **wine 的 `cmd.exe` 可用**：`~/.wine/drive_c/windows/system32/cmd.exe`，
  需 `WINEDEBUG=-all` 抑制驱动噪声、输入需 CRLF、输出需去 `\r`/ANSI/行尾空格。

### 5.2 已演示的流程（`/tmp/ext/golden/`）

```
for f in g0*.bat:
  golden = wine cmd /c w_$f.bat | norm      # norm: 去 ANSI/CR/行尾空格/空行
  bat2sh = bat2sh --cli $f.bat -o $f.sh ; bash $f.sh | norm
  比对 golden vs bat2sh
```

结果（6 例，2026-09-16）：

| 用例 | 构造 | golden（wine） | bat2sh | 判定 |
| :--- | :--- | :--- | :--- | :--- |
| g01 | 053 同构（两分支） | `A B after` | `A B after` | ✅ MATCH |
| g02 | 053 同构（else 体命中） | `skipA skipB body=c done` | 同 | ✅ MATCH |
| g03 | 多行 `if/else` | `then-branch end` | 同 | ✅ MATCH |
| g04 | `!v!` 延迟展开 | `d=2 d=2` | `d=2 d=2` | ✅ MATCH |
| g05 | `%v%` 立即展开 | `i=1 i=1` | **`i=2 i=2`** | ❌ **DIFF** |
| g06 | 114 自引用 | `[ab]` | `[ab]` | ✅ MATCH |

**流程可行性：成立。** yield：5/6 MATCH；并**发现 bat2sh 一个真实缺陷**（g05）。

### 5.3 由 harness 发现的新缺陷（g05）

```bat
set v=1
for %%i in (a b) do (set v=2 & echo i=%v%)
```

wine cmd → `i=1 i=1`（`%v%` 在 **for 行解析时**展开一次，循环内**冻结**）。
bat2sh 产物（`g05.sh`）：

```bash
v="1"
for i in a b; do
    v="2"
    echo "i=${v}"        # ← 运行时活引用：得到 2
done
```

对比 g04（`!v!`）的产物：

```bash
    echo "d=${v}"        # 同一形态
```

→ **bat2sh 把 `%VAR%`（立即）与 `!VAR!`（延迟）在循环体内译成了同一种「运行时活引用」**。
延迟正确；立即**丢失了「解析时冻结」语义**。这是**本次分析最有价值的产物**：
ChenPi11 的 ea 用例（`%v%` 冻结）证明了正确模型，且与 wine 一致。

---

## 6. 具体建议

### S1 采纳 wine-cmd 黄金对照为回归设施（**可直接用**）

- 建 `tests/` 之外的 research harness：`wine cmd /c` vs `bat2sh→bash`，规范化后逐例比对。
- 覆盖对象：嵌套块（`for`+`if/else(`）、多行 `if/else`、`%VAR%`/`!VAR!` 时机、`goto`、管道+重定向。
- 非 Linux/无 wine 时 skip（与现有 CI 语料策略一致）。
- **注意**：wine 自身是重实现，权威性低于真机；建议对争议样例人工复核一次（写进测试注释）。

### S2 修 `%VAR%` 冻结语义（**需适配，建议进 backlog 并评估**）

- **判据**：`%VAR%` 在**块（`for`/`if` 体）解析时**求值一次；`!VAR!` 在执行时求值。
- **可能的映射**：若 `%VAR%` 出现在块体内，在**块入口**插入快照赋值，块内引用快照：
  ```bash
  __b2s_snap_v="${v}"          # 块入口（或 for 行前）
  for i in a b; do v="2"; echo "i=${__b2s_snap_v}"; done
  ```
  无块嵌套时保持现状（避免全局 churn）。
- **风险**：变量名必须避开用户命名空间（沿用现有 `__bat2sh_*` 前缀约定）；
  需评估 churn（`%VAR%` 在循环体内极常见）。**必须先做 churn 计量再决定**。

### S3 块解析判据（**需适配，仅在重写解析层时**）

- 采用「行首 `(`=块 / 否则整段配平 `(...)`=不透明 token」；
- **并补上 ChenPi11 缺的那一半**：括号未配平时**继续累积后续行**（bat2sh 现有 `await_paren_close` 已实现等价能力）。

### S4 未定义变量语义（**可直接用，作为纪律依据**）

- 引用 `cvars.c:52-108`：cmd 未定义变量 = **空串、不报错**。
- 据此，`_guard_unset_variable_refs` 的 `${X:-}` 是**语义等价翻译**，不是防御性猜测——
  可作为该设计决策的书面依据（对 085 的「流程感知 guard」争论亦有帮助）。

---

## 7. 风险提示

| # | 风险 | 说明 |
| :--- | :--- | :--- |
| R1 | **把 ChenPi11 当 oracle** | 已在 053 构造上证明其错误；会固化 bug。**禁止**。 |
| R2 | **借鉴其块处理算法** | 它缺少跨行括号累积，是 **053 同类失败**；照搬即引入 bug。 |
| R3 | **成熟度** | 仅 **1 commit**、**无测试**、GPLv3；不是经过验证的语义权威。 |
| R4 | **许可证** | ChenPi11 为 GPLv3，bat2sh 为 AGPL-3.0-or-later。本次**只借鉴思想、未抄代码**；后续亦应严守「不复制 C 代码」。 |
| R5 | **wine 的权威性** | wine cmd 亦为重实现；争议样例需真机/文档二次确认。 |
| R6 | **S2 的 churn** | `%VAR%` 冻结修复会触及大量循环体产物；**不得**未计量直接实现（纪律 1/9）。 |
| R7 | **架构错配** | 解释器 vs 转换器：ChenPi11 可在运行时求值，bat2sh 必须**静态**决定；任何「运行时等价物」的引入都要先证明静态可判定。 |

---

## 8. 纪律对照

| 纪律 | 落实 |
| :--- | :--- |
| 1 保守 TODO | 未改任何代码；S2 明确要求先做 churn 计量 |
| 2 只读诊断先行 | 全程只读；bat2sh 仓库未修改（仅新增本文件） |
| 3 主动披露偏离 | 披露：053 已于 v1.9.0 修复（任务前提过时）；ChenPi11 块处理本身错误 |
| 4 不发明映射 | 每条结论附 `file:line` 或实跑输出 |
| 5 仪器先验证 | 先 clone+构建+冒烟，再用双 oracle（wine / ChenPi11）对照 |
