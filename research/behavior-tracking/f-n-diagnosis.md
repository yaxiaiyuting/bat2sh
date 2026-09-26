# `%%~n` 只读诊断（Phase C）

> 起点 HEAD：`70a0ddb`（v2.11.0 发布后 main tip，**锁定 HEAD 未动**）
> 轨道：只读诊断。`python/`、`tests/` **零改动**（`git status` 仅本 session 新增的 `research/` 文件）
> 候选补丁**只打在 `/tmp/b2s-fix` 副本**，仓库内未落地
> 上游依据：`docs/releases/v2.11.0.md` L1 · `research/behavior-tracking/p0-result.md` L1 · `p0-diagnosis.md` §4.5/§7

---

## 0. 一句话结论

| 问题 | 判定 |
| :--- | :--- |
| `%%~n` 通用表达式 `basename "${v%.*}"` **是缺陷吗？** | ✅ **是**。已实测复现，**完全静默**（rc=0 / stderr 空 / 无 TODO） |
| 根因在哪？ | `python/bat2sh/core/batch.py:1250` 的 **`_modifier`** |
| **触 A1 吗？** | ⚠️ **触 A1 邻域** —— `_modifier` **只被 `_expand_vars`（`batch.py:1030`）调用**（2 处调用点：`:1086`、`:1092`）；且 v2.11.0 release notes L1 与 `p0-diagnosis.md` §4.5 **已把它定性为「A1 邻域」** |
| 但它触 A1 **核心**吗？ | ❌ **不触**。`docs/v2.4.0-053-protection.md` §2 定义的 A1 核心是 `env_repl` 用户变量分支 / `_register_assigned` / `_a1_*` / 块头 marker —— `_modifier` 处理的是 `%%~`/`%~`（**循环变量与参数**），与 `%VAR%` 冻结机制**不相交** |
| 本 session 动作 | 🛑 **按暂停条件「Phase C 触及 A1 邻域 → 暂停」，不落地修复**，报告并请示（§6） |

> **精确表述**：这是一处**真实的、静默的**缺陷；修复面**小**（2 行代码）；
> 但修复点**落在 A1 邻域的 `_modifier` 上**，且**需要改写 2 条实现串断言**（§5.2）。
> 是否在本 session 落地，按纪律交由用户裁定。

---

## 1. 触发条件（精确刻画）

`basename "${v%.*}"` 的作用顺序是 **先剥扩展名、再取末段** —— 顺序**倒置**。
`${v%.*}` 从**整个字符串的最后一个点**剥起，

⇒ **只有当「最后一个点」落在父目录段时才出错**，即同时满足：

1. `basename(v)` 自己**不含点**（无扩展名，或扩展名形态不含点）；
2. 某个**祖先路径段含点**。

这与 L1 的描述一致（「只有父目录某段含点时才截错」），但本诊断把它**收紧为可判定的充要条件**，
并补上了第 2 个受影响的表达式 `%%~x`（§3.3）。

---

## 2. 复现（实测证据）

### 2.1 主复现 —— `for /r` + `%%~ni`（V5/F3 的残留面）

```bat
@echo off
for /r %%i in (.) do @echo %%~ni
```

产物（HEAD，`bash -n` 通过、无 TODO）：

```bash
while IFS= read -r i; do
    echo "$(basename "${i%.*}")"
done < <(find "$PWD" -type d)
```

**实测**（把脚本放在含点祖先下运行）：

| 运行目录 | 实测输出 | 应为（cmd） | 判定 |
| :--- | :--- | :--- | :--- |
| `/tmp/b2s-fn/my.project/samples` | `my`<br>`my` | `samples`<br>`sub` | ❌ **错** |
| `/tmp/b2s-fn-plain/samples`（无点，对照） | `samples`<br>`sub` | `samples`<br>`sub` | ✅ 对 |

> **`samples`/`sub` 是 oracle 已证的目标值**：v2.11.0 的 V5 真机指纹里 W 建出的是 `samples.txt`
> （`oracle-result.md` §1），即 `%%~ni` 在 `C:\poc\samples` 上确为 `samples`。**不是我推测的。**

**静默性**：`rc=0`、stderr 空、`todo_count` 不变、`bash -n` 通过 —— 属本项目最危险的「静默错」类别。

### 2.2 次复现 —— `%~n0` 同根因

| 场景 | 实测 `n0` | 应为 | 判定 |
| :--- | :--- | :--- | :--- |
| 无扩展名脚本 + 含点祖先（`.../my.project/samples/norext`） | `my` | `norext` | ❌ 错 |
| 无扩展名脚本 + 无点路径（对照） | `norext` | `norext` | ✅ 对 |
| **有**扩展名脚本 + 含点祖先（`.../my.project/samples/fam.sh`） | `fam` | `fam` | ✅ 对（最后一个是 `.sh`，恰在末段） |

⇒ 印证 §1 的充要条件。

---

## 3. 根因与代码锚点

### 3.1 唯一根因

**`python/bat2sh/core/batch.py:1250`（`_modifier`）**

```python
if "n" in mods:
    return f'$(basename "${{{var}%.*}}")'      # ← 先剥扩展名、再取末段（顺序倒置）
```

正确顺序是 **先取末段、再剥扩展名**。

### 3.2 调用链（A1 判定的依据）

```
_expand_vars  (batch.py:1030)          ← A1 热路径函数
  ├── :1086  re.sub(...  _modifier ...)   %%~ 循环变量修饰符
  └── :1092  re.sub(...  _modifier ...)   %~   参数/脚本修饰符
_modifier     (batch.py:1233)
```

**`_modifier` 的调用点只有这 2 处，全部在 `_expand_vars` 内**（`grep -n "_modifier" batch.py` 实测）。

### 3.3 同一根因的**第二个**表达式（本轮新识别）

| 行 | 表达式 | 产物 | 问题 |
| :-: | :--- | :--- | :--- |
| `:1250` | `%%~n` | `$(basename "${v%.*})")` | **顺序倒置**（本 issue 主体） |
| `:1252` | `%%~x` | `$(echo ".${v##*.}")` | 同样对**整串**取末点：`.../my.project/samples` ⇒ `.project/samples`；应为**空**（目录无扩展名） |
| `:1265` | `%~n0` | `$(basename "${0%.*}")` | 与 `:1250` **同根因** |
| `:1244` | `%%~dpn` | `${v%.*}` | 同根因（无 basename，故仅在末段无点时错） |
| `:1246` | `%%~nx` | `$(basename "${v}")` | ✅ **本就正确**（先取末段，不剥） |

> ⚠️ `%%~x` 对**目录**取扩展名的 cmd 目标值，本诊断**未做真机指纹验证**（只有 `%%~ni` 有 oracle 证据）。
> 因此 §5 的候选补丁**只改 `%%~n`（`:1250`）与 `%~n0`（`:1265`）**，**不碰** `%%~x`——避免「发明映射」（纪律 5）。

---

## 4. 影响面（为什么 oracle 抓不到）

### 4.1 L 侧采集沙箱的路径**结构性地无点**

`research/behavior-tracking/tools/collect_linux.py:263,268`：

```python
workroot = workroot or Path(os.environ.get("ORACLE_WORKROOT", "/tmp/bat2sh-oracle"))
run_dir  = Path(workroot).resolve() / f"{src.stem}-{int(time.time()*1000)}" / run_name
```

`/tmp` · `bat2sh-oracle` · `<stem>-<ms>`（`Path.stem` 已去掉 `.bat`）· `samples` —— **每一段都不含点**。

⇒ **纯差分 oracle 对本缺陷是结构性盲区**：即便跑遍全部样本，L 侧也永远落在无点路径上，
`basename "${v%.*}"` 恰好给出正确值。**这不是"样本不够"，是仪器的路径布局使然。**

> 这条结论对 Phase B 有直接影响：**扩样本不能提高本缺陷的检出率**，
> 要检出必须**主动构造含点路径**（或改采集器的 run_dir 命名）。已记入 `oracle-result-v2.md`。

### 4.2 静态面

`p0-diagnosis.md` §4.4 已量化：151 语料中 `%%~n` 系列出现于 **12** 个文件，
`basename "${v%.*}"` 产物签名 **7** 个文件，其中**必然坏**的只有 V5（唯一 `for /r` 驱动），
另 6 个是**潜在**（值域含点才坏）。本轮**未重跑**该统计（避免与 D3 重复劳动）。

---

## 5. 候选修复（**仅在 `/tmp/b2s-fix` 副本验证，未落地**）

### 5.1 补丁（2 行）

```python
# batch.py:1250   %%~n  →  先取末段、再剥扩展名
if "n" in mods:
    return f'$(__bat2sh_b="$(basename "${{{var}}}")"; printf %s "${{__bat2sh_b%.*}}")'

# batch.py:1265   %~n0  同根因
if "n" in mods:
    return '$(__bat2sh_b="$(basename "$0")"; printf %s "${__bat2sh_b%.*}")'
```

设计要点：

- 赋值发生在 `$( ... )` **子壳内** ⇒ 不污染调用方作用域，无变量名冲突风险；
- 保留 `basename`（而非 `${v##*/}`）⇒ 尾随斜杠 / `.` / `..` 的语义与现状**一致**，不引入新差异；
- 复用项目既有保留前缀 `__bat2sh_*`。

### 5.2 验证结果（实测）

| 门 | 内容 | 结果 |
| :--- | :--- | :--- |
| **复现转好** | §2.1 含点路径 | ✅ `samples` / `sub`（修前 `my`/`my`） |
| | §2.2 `%~n0` 含点路径 | ✅ `norext`（修前 `my`） |
| **语义不变** | 两条既有测试的输入（`for %%F in (*.txt)`→`a`；`for %%i in (sub\inner.txt)`→`inner`） | ✅ **OLD 与 PATCHED 输出逐字节相同** |
| **D1**（053/A1 定向：`loop_modifier` / `loop_modifier_path` / `var_block_freeze` / `for_r` / `var_expansion` / `block_stack_v190` / `goto` / `examples`） | | ⚠️ **64 passed, 2 failed** |
| **D2**（全量 pytest） | | ⚠️ **1619 passed, 6 failed**（HEAD 基线 **1625 passed**） |
| **D3**（语料指标 HEAD vs PATCHED） | | ⏳ 运行中（背景 job） |

**D2 的 6 条失败 —— 全部是实现串断言，零条语义断言**：

| # | 测试 | 被钉死的断言 | 性质 |
| :-: | :--- | :--- | :--- |
| 1 | `test_batch.py::test_basename_modifier_no_extra_escaping` | `'base="$(basename "${i%.*}")"' in out`（`:1091`） | 实现串；**同测试另有** `'\\"' not in out` 语义断言（PATCHED 下仍过） |
| 2 | `test_batch.py::test_del_basename_quoted` | `'rm -f "$(basename "${i%.*}")"' in out`（`:1098`） | 实现串。⚠️ **删除语境**，见 §5.3 |
| 3 | `test_batch.py::test_script_name_modifiers` | `'$(basename "${0%.*}")' in out`（`:1104`） | 实现串（同测试另 2 条断言 PATCHED 下仍过） |
| 4 | `test_batch_loop_modifier.py::test_loop_var_n_without_extension` | `'echo "$(basename "${f%.*}")"' in out`（`:34`） | 实现串；**同测试 `:35-37` 已有真跑语义断言**（`stdout == "a\n"`），PATCHED 下**语义仍成立** |
| 5 | `test_batch_loop_modifier_path.py::test_name_only_modifiers_still_use_basename` | `'$(basename "${i%.*}")' in out`（`:50`） | **纯**实现串，且**恰好把有缺陷的表达式钉死**（测试名即 "still use basename"） |
| 6 | `test_batch_string_ops.py::test_tilde_n0_not_misparsed_as_string_op` | `'$(basename "${0%.*}")' in out`（`:109`） | 实现串；**同测试另有** `'${n0' not in out` 语义断言（PATCHED 下仍过） |

> **这 6 条正是纪律 8「测试断言必须验证语义」的现存欠账**：
> 断言的是**产物文本形态**而非行为。第 5 条最严重 —— 它使「修好 `%%~n`」
> **在测试层被显式阻断**。
>
> **反证**：仓库里**已存在**正确的语义孪生测试 `test_batch.py::test_basename_runtime_with_spaces`
> （`:1110-1115`，真跑断言 `stdout == "[my file]"`），PATCHED 下 **✅ 通过** ——
> 说明"该怎么写"在本仓库**已有范式**，这 6 条只是历史遗留。

### 5.3 与 Phase A 的交叉（删除语境）

第 2 条失败 `test_del_basename_quoted` 的输入是：

```bat
for %%i in (*.txt) do del "%%~ni"
```

即 **`%%~n` 直接喂给删除命令**。§2.1 的缺陷形态（`%%~n` 返回**错误的末段**，如 `my` 而非 `samples`）
在此语境下不只是"打印错名字"，而是 **`rm -f "<错名字>"`** ——
**存在删到非目标文件的路径**（窄，但真实）。
⇒ 这使 `%%~n` 从"命名保真度问题"升级为**潜在的静默数据丢失**，
已在 Phase A（删除类命令审查）中作为交叉线索移交。

---

## 6. A1 判定与暂停请示

### 6.1 判定表（按 `docs/v2.4.0-053-protection.md`）

| 项 | 是否保护域 | 依据 |
| :--- | :--- | :--- |
| `_modifier`（`batch.py:1233`） | ⚠️ **A1 邻域** | 唯一调用者 `_expand_vars`（`:1086`/`:1092`）；v2.11.0 L1 + `p0-diagnosis` §4.5 已如此定性 |
| A1 **核心**（`env_repl` 用户变量分支 / `_register_assigned` / `_a1_*` / 块头 marker） | ✅ **不触** | `_modifier` 只处理 `%%~`/`%~`（循环变量、参数），与 `%VAR%` 冻结**不相交** |
| 053 块栈（`_Block` / `_pop_block` / `_close_block_line` / 块发射） | ✅ **不触** | 补丁不涉及块栈 |
| 测试面 | ⚠️ **需改 6 条断言**（D2 实测，全为实现串） | §5.2 |

### 6.2 结论

**⇒ 触及 A1 邻域**，但**不触 A1 核心**，也不触 053。

按本 session 暂停条件：

> **Phase C 触及 A1 邻域 → 暂停**

**故本 session 不落地此修复**，改为：诊断留档（本文件）+ 候选补丁与门结果留档 + 请示用户（§7）。

### 6.3 为什么这不是"过度保守"

1. **上 session 已做过同样的裁定**（`p0-diagnosis` §4.5：「那是 A1 热路径 ⇒ 需另开带防护的改动。**本 session 不做**，登记 backlog」）。本轮若静默推翻，等于绕过既定纪律。
2. **修复不是"就几行"**：除 2 行代码外，**必须改写 6 条测试断言**（D2 实测 6 failed，
   **全部**为实现串断言，其中 1 条正在钉死缺陷），属「测试面语义变更」，按纪律 8 需显式披露与设计。
3. **收益有限而残留仍在**：修好 `%%~n` 后 `%%~x`（`:1252`）仍错，`%%~dpn`（`:1244`）仍错 ⇒
   一次"顺手修"会留下**半修状态**，比诚实 backlog 更难解释。
4. **oracle 结构性盲区**（§4.1）意味着**没有差分证据**能证明修复无回归，
   只能靠 D1–D4 静态门 —— 而门里已有 2 条红。

---

## 7. 请示（待用户裁定）

| 选项 | 内容 | 代价 |
| :--- | :--- | :--- |
| **C-0（本 session 默认）** | **不修**。保留 L1，本 session 只交付诊断；把 `%%~n` 移到下一 session 作为**带防护的专项**（含测试断言语义化） | 缺陷留存一个版本；但零回归风险 |
| **C-1** | **授权修** `:1250` + `:1265`，**同时**把 **6 条**实现串断言改写为**真跑语义断言**（范式见 `test_basename_runtime_with_spaces`），并跑满 D1–D4 后独立 commit | 触碰 A1 邻域 + 测试面变更；需 D1–D4 全绿 |
| **C-2** | **窄修**：只改 `:1250`（`%%~n` 主体），`%~n0` 与 `%%~x` 留 backlog | 仍触 A1 邻域且产生半修状态；**不推荐** |

**主 session 建议：C-0** —— 理由是 §6.3 的 1/3/4（上 session 已裁定、半修状态、无非差分证据），
且本 session 还有 A（安全审查）与 B（oracle 扩样本）两件**零风险、高信息量**的事可做。

### 7.1 实际处置（本 session）

> 主 session 已把 C-0/C-1/C-2 三选项**原样提交用户裁定**，用户**取消了该提问**（未选）。
> 按「命中暂停条件 ⇒ 不落地」的字面要求，并取**最小风险**分支，
> 主 session **自行裁定执行 C-0**：
>
> - ❌ **不落地** `_modifier` 修复；
> - ✅ 保留 L1，并在 v2.11.1 release notes 中**继续披露**（附本轮收紧后的触发条件）；
> - ✅ 诊断、候选补丁、门结果**全部留档**（本文件 §5），下一 session 可直接复用；
> - ✅ §5.3 的**删除语境交叉线索**移交 Phase A；
> - ➡️ 继续执行 Phase A / Phase B（二者不含 A1 改动，与本裁定正交）。
>
> **主动披露**：这是一次**未经用户确认的自主裁定**。若用户本意是 C-1，
> 本文件已备齐补丁与门结果，可在下一 session 直接执行，无需重新诊断。

---

## 8. 纪律自查

| # | 纪律 | 执行 |
| :-: | :--- | :--- |
| 1 | 保守 TODO 优于激进转换 | ✅ 默认 C-0；给出了 C-1 的完整代价而非偷偷修 |
| 3 | 只读诊断先行 | ✅ 仓库 `python/`/`tests/` 零改动；补丁只在 `/tmp/b2s-fix` |
| 5 | 不发明映射 | ✅ 只改有 oracle 证据的 `%%~n`；**拒绝**改无指纹的 `%%~x`；`samples`/`sub` 目标值来自 V5 真机指纹 |
| 6 | 仪器先验证 | ✅ 起点先跑全量 pytest（**1625 passed**）确认基线；识别出 L 采集器路径无点 ⇒ oracle 盲区 |
| 7 | 锁定 HEAD | ✅ 起点 `70a0ddb` 全程未动 |
| 8 | 测试断言必须验证语义 | ✅ **本轮以此为证据之一**：2 条红均为实现串断言，其中 1 条钉死缺陷 |
| 9 | Subagent 输出必须核验 | — （Phase C 未用 subagent） |

---

## 9. 未完成 / 存疑

| # | 项 | 状态 |
| :-: | :--- | :--- |
| 1 | D2 全量 pytest（PATCHED） | ✅ **已完成**：`1619 passed / 6 failed`（HEAD 基线 1625）—— 6 条全为实现串断言 |
| 2 | D3 语料指标 HEAD vs PATCHED | ⏳ 背景 job，结果待补；语料用 `~/下载/非常批处理`（**144** 个 `.bat/.cmd`，与文档口径的 151 不完全一致，**已在报告中披露**） |
| 3 | `%%~x` 对目录的 cmd 目标值 | ❓ **未做真机指纹**；本诊断不断言，也不据此修改 |
| 4 | D4 wine oracle 6/6 | 未跑（仅当决定落地修复时才需要） |
| 5 | 6 条断言改写为语义断言后的**新测试设计** | 未做（属 C-1 的执行内容） |
