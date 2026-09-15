# B3 研究报告：PS 块结构 4 缺陷修复评估（v1.5 阶段归档）

> 研究时间：2026-09-15 · 方法：只读复现 + 代码路径分析（不运行修复）·
> 临时产物：`/tmp/opencode/b3/`（未入仓）· 仓库未被修改。
> 结论：**4 缺陷均静默损坏（bash -n 全过）；建议先做统一块栈加固，再逐项修复。**

# bat2sh v1.4.1 — 4 个 PowerShell 结构性缺陷评估

**范围：** 只读评估。仓库未被触碰（最终 `git status --short` 为空）。所有探针在 `/tmp/opencode/b3/` 下。每次 `bat2sh` 调用均使用 `--print`；没有在输入旁生成 `.sh`。

## 复现摘要（全部 4 个）

`--report-json` 输出到 stderr。**四个中没有一个被降级为注释** — 全部发出静默损坏的 bash；全部 `error_count == 0`，且四个生成的脚本 `bash -n` 均退出 0。

| ID | 文件 | total/converted/unchanged | err | warn | todo | `bash -n` | 结果 |
|----|------|--------------------------|-----|------|------|-----------|---------|
| 105 | `…_038099.ps1` | 31 / 16 / 10 | 0 | 11 | 6 | 0 | 静默损坏 |
| 109 | `…_27eace.ps1` | 43 / 21 / 19 | 0 | 15 | 8 | 0 | 静默损坏 |
| 111 | `…_34c474.ps1` | 52 / 11 / 34 | 0 | 20 | 14 | 0 | 静默损坏 |
| 114 | `…_d5bf28.ps1` | 41 / 24 / 9 | 0 | 15 | 1 | 0 | 静默损坏 |

`bash -n` 安全网（`powershell.py:118-122` → `syntax.py:20-55`）仅是 **语法** 网。泄漏的 token（`begin`、`process`、`end`、`catch`、`finally`、`"dev" { … }`、`"web01" = @{…}`）都是 *语法合法* 的 bash 简单命令，因此不会触发降级。

---

## 缺陷 105 — `[ordered]@{…}` 多行哈希表字面量
文件：`/home/duanjb666/下载/deepseek_powershell_20260914_038099.ps1`

### 1. 损坏输出形态（标准化）
```bash
serverConfig="[ordered]@{"
"web01" = @{ IP = "10.0.1.10"; Role = "Web"; Port = 443 }
"db01"  = @{ IP = "10.0.1.20"; Role = "Database"; Port = 5432 }
# 多余的 }，已忽略
...
for serverName in ; do
    cfg="${serverConfig}[[${serverName}]"
```
未降级。字面量的第 3–5 行被 **原样作为命令** 发出；闭合 `}` 变成"多余的 }"。更糟的是：`$serverConfig.Keys` 塌缩为 **空集合** → `for serverName in ; do`（循环体从不执行）— 静默行为丢失。

### 2. 转换路径 / 根因
- `_match_assignment`（`powershell.py:1612-1619`）匹配 `$serverConfig = [ordered]@{`。
- `_emit_assignment`（`:1621`）没有哈希表字面量处理。`[ordered]` 不是已知类型（`:45-48` 的 `_PS_TYPE_NAMES` 缺少 `ordered`/`version`/`pscustomobject`），因此落入通用回退 `:1729-1742` → 警告 "无法确定右值类型" + `name="$expression"`（`:1741-1742`）。
- `@{…}` **没有多行字面量收集状态**（不同于 here-string，它在 `:76-80, :762-777, :840-851` 有 `_here_end`/`_here_lines`）。后续正文行独立经过 `_convert_statement` → 未知命令（`_convert_cmdlet_line:2056-2057`），闭合 `}` 落到 `_pop_block`（`:2969-2972`）。
- `$x.Keys`/`.Values` 在 `_convert_collection_raw`（`:1452-1453`）中被有意映射为空字符串，产生空 `for` 列表。

**根因：** 未注册的多行 `@{ }` 字面量开启符 + 通用 RHS 回退；无大括号/收集器状态；`.Keys` 集合抑制产生空循环。

### 3. 影响面
同一路径：`@{…}`（裸）、`[PSCustomObject]@{…}`（def111 第 31 行）、`[ordered]@{…}`、任何未知 `$v = <literal-with-brace>`，以及许多 RHS 形式使用的通用 `_emit_assignment` 回退。`bash -n` **不会** 掩盖它（输出是合法 bash）。静默数据丢失：是 — `.Keys` → 空循环，`[key]` 索引被搞坏。

### 4. 修复范围
- 新状态：`_hashtable_depth`、`_hashtable_target`、`_hashtable_lines`、`_hashtable_lineno`（镜像 here-string 收集器）。
- 在 `_emit_assignment` 中检测 RHS `@{`（可选前缀 `[ordered]`/`[hashtable]`/`[PSCustomObject]`），**先于** `:1655` 的属性访问检查；在 `_convert_line` 中收集到深度 0 的 `}`。
- 发出：最安全 = 整个字面量注释降级（复用 switch 风格 comment block `:1017-1025`）；更好 = 对扁平标量条目 `declare -A name=( [k]=v … )`，嵌套 → 注释。
- 可选修复 `.Keys`/`.Values`/索引表达式模型（`:1450-1462`）。
- 粗略 LOC：**60–90** 收集器/发射器（+40–60 用于 `.Keys`/索引语义）。连带风险：`[PSCustomObject]@{` 和 `[math]::` 的顺序必须正确；`@{` 检测不得吞掉 script-block `{…}`（例如 `-Action {…}`）。

### 5. 测试路径
镜像 `test_here_string_literal_standalone`（`tests/test_powershell.py:406`）做多行收集，`test_unknown_type_annotation_todo`（`:849`）做断言风格。新增 `tests/test_powershell_structural.py`：
- `test_ordered_hashtable_literal_not_raw(convert_ps, bash_check)` — 断言没有未注释行包含 `[ordered]@{`；断言 `"多余的 }" not in out`；`bash_check(out)`。
- `test_pscustomobject_hashtable_literal(convert_ps, bash_check)`。
- `test_hashtable_keys_collection_nonempty(convert_ps)` — 断言 `for serverName in ;` 不在 out 中（或 `.keys` 会警告）。
这些适配 `pytest -q`（fixtures 在 `tests/conftest.py:47-56`；套件基线 120 passed）。

### 6. 优先级
高严重度（静默行为丢失）× 高成本 → **排名 3**。

---

## 缺陷 109 — try / catch / finally
文件：`/home/duanjb666/下载/deepseek_powershell_20260914_27eace.ps1`

### 1. 损坏输出形态（标准化）
```bash
if true; then  # TODO: try/catch 未等价转换
    ...
    echo ${result}; return 0
else  # TODO: catch 块
:
fi
catch [System.UnauthorizedAccessException] {
...
done
catch {
...
}
finally {
# Write-Debug: "Completed attempt $attempt"
```
未降级。第一个 `else` 附加到 `if true; then`（catch 从不运行）；第 2/3 个 `catch` 和 `finally` 作为 **原生 shell 命令** 发出；块栈失同步（多个"多余的 }"）。

### 2. 转换路径 / 根因
分支派发分布在三处，未覆盖真实世界形态：
- `_dispatch_line:737-751` — 仅当 `_try_buffer is not None` 且 `len(stack)==_try_depth` 时才把行视为边界（`:742-744`）。
- `_convert_statement:980-981` — 仅在 `_try_buffer is not None` 时把 `catch|finally` 路由到 `_close_block_line`。
- `_close_block_line:2747-2813` — 仅当行以 `}` 开头时才处理 `catch`/`finally`（`:2798, :2800`），即 `} catch {` 同行。
- `_handle_catch:2860`、`_handle_finally:2938`。

**第一个** 独立行 `catch` 被 `_dispatch_line` 边界捕获；一旦 `_handle_catch` 消耗 `_try_buffer`（`:2884-2888`），`:980` 的守卫为假，因此 **所有后续独立 `catch`/`finally` 落入 `_convert_cmdlet_line` 并被原样发出**。真实脚本绝大多数使用 `}`-换行-`catch`（在 `下载` 中：2/2 catch 文件为独立行，**0** 同行），而测试套件只测试 `} catch {` 同行。

此外，多臂 try/catch 无法映射到 bash `if/else`（只有一个 `else`）；`_handle_catch` 的"简化"分支 `:2912-2936` 构建 `if true; then … else … fi` 骨架，其 `else` 不可达 — **catch/finally 体静默永不执行**。

**根因：** 独立分支关键字（`catch`/`finally`，以及独立行的 `else`/`elseif`）未被派发到块分支处理器；加上多臂语义无法实现为 `if/else`。

### 3. 影响面
所有 try/catch/finally 形态、嵌套 try（`:983-991`）、`else`/`elseif` 关联（同一 `_close_block_line`，已列入 backlog），以及 12 个现有 try 测试。降级是 **形态相关** 的：一个最小双 catch 探针 *确实* 降级了（bash `-n` 报 "unexpected else"），而真实 def109 通过了 `bash -n` — 同一构造、不同臂内容 → 不确定结果。静默行为丢失：是（catch/finally 体永不执行）。

### 4. 修复范围
- 修复 A（派发）：在 `_convert_statement` 中，无论 `_try_buffer` 如何，提前把 `^(catch|finally)\b`（以及 `^else(if)?\b`）路由到 `_close_block_line`。约 5–10 LOC，但对多臂不充分。
- 修复 B（稳健）：当 try 有 >1 个 catch 臂或任何带类型臂时，将整个 try/catch/finally 降级为 switch 风格 comment block（`:1017-1025`），而不是伪造 `if/else`。约 30–50 LOC。
- 连带风险：`_handle_catch`/`_handle_finally`/`_finalize_bare_try`/`_try_depth`/`_branch_is_empty` 紧密耦合；触碰派发可能使 12 个通过的 try 测试回归。

### 5. 测试路径
镜像 `test_try_catch_multi_command_falls_back`（`tests/test_powershell.py:495`）和 `test_try_catch_typed_keeps_structure`（`:507`）。新增：
- `test_try_catch_standalone_catch_lines(convert_ps, bash_check)` — 断言没有未注释的 `^\s*catch\b`；断言 `"多余的 }" not in out`；断言 catch 体内容被保留（注释或发出）；`bash_check`。
- `test_try_multiple_catch_arms_degrade(convert_ps, bash_check)` — `report.error_count == 0`；无原生 `catch [`；无悬空 `else`。
- `test_try_finally_on_own_line(convert_ps, bash_check)`。
约定匹配 `convert_ps` + `bash_check` fixtures（`tests/conftest.py:47, 59`）。

### 6. 优先级
最高频率（CC0 fleschutz 语料 57/60 = 95% 使用 try/catch；backlog 明确点名）× 中等成本 → **排名 1**。

---

## 缺陷 111 — 高级函数 `begin` / `process` / `end`
文件：`/home/duanjb666/下载/deepseek_powershell_20260914_34c474.ps1`

### 1. 损坏输出形态（标准化）
```bash
Get_SystemReport() {

    begin {
    # TODO: 手动检查: $allResults = [System.Collections.ArrayList]::new()
}
process {
for computer in ${ComputerName}; do
...
catch {
echo "Failed to query ${computer}: ${_}" >&2
# 多余的 }，已忽略
end {
```
未降级。`begin {`/`process {`/`end {` 被 **原样发出**（未知命令），且因为它们从不压栈，`begin` 后的 `}` 弹出 **function** 块 → 大括号对齐移位，`end` 体落在错误作用域，多余 `}`。

### 2. 转换路径 / 根因
`_convert_statement`（`:974-1127`）有 `if`（`:1004`）、`foreach`（`:1009`）、`for`（`:1013`）、`switch`（`:1017`）、`try`（`:1027`）、`do`（`:1059`）、`function`（`:1066`）、`param`（`:1070`）、裸 `{`（`:1074`）的处理器 — 但 **没有 `begin`/`process`/`end`/`clean`/`dynamicparam`**。它们落到 `_convert_cmdlet_line` → 未知命令透传（`:2056-2057`），不压 `_Block`。`_Block` kinds 只有 `if/else/for/while/function/try/catch/finally/do/group/comment`（`:54`），没有覆盖生命周期阶段。

**根因：** 生命周期块关键字是未注册的大括号开启符 → 无块状态 → 大括号失同步 + 原样泄漏。

### 3. 影响面
所有高级函数（非常常见）；同一函数中 `begin`/`process`/`end` 之后的任何构造；`_pop_block`/`_finish` 自动闭合行为（`:2969-2979, :3012-3020`）。`bash -n` 不掩盖。行未丢失但结构被合并（52 源行 → 43 发出）。运行时 **响亮**（`begin: command not found`，`set -e` 中止），但转换器报告 `error_count == 0`。

### 4. 修复范围
在通用 cmdlet 回退之前添加处理器：检测 `^(begin|process|end|clean|dynamicparam)\b` 及可选 `{`；压入 `_Block("group","}")`（安全，保持大括号平衡）或 comment block，并警告 PowerShell 管道阶段语义无 bash 等价物；像 `_emit_function` 尾部（`:1522-1531`）那样处理内联 `{ … }`。约 25–40 LOC。连带风险：字面名为 `end`/`process` 的用户命令（罕见）；缩进偏移因为 `group` 增加一个栈层；`process` 内嵌套 try 会改变 `_try_depth` 引用，但仍相对，因此 OK。

### 5. 测试路径
镜像 `test_empty_function_gets_colon`（`tests/test_powershell.py:1061`）和 `test_cmdletbinding_ignored`（`:44`）。新增：
- `test_advanced_function_begin_process_end(convert_ps, bash_check)` — 断言没有未注释的 `^\s*(begin|process|end)\b`；断言 `"多余的 }" not in out`；断言 process 体语句被保留；`bash_check`。
- `test_advanced_function_no_dangling_brace(convert_ps)` — 大括号计数/栈健全性。
适配 `pytest -q` 及现有 fixtures。

### 6. 优先级
高严重度（损坏整个函数）× 低–中成本 → **排名 2**。

---

## 缺陷 114 — switch 语句 + `[version]` 类型字面量
文件：`/home/duanjb666/下载/deepseek_powershell_20260914_d5bf28.ps1`

### 1. 损坏输出形态（标准化）
```bash
# TODO: 手动检查: $action = switch ($Environment.ToLower()) {
"dev"     { "Deploy to DEV with debug flags" }
"staging" { "Deploy to STAGING with smoke tests" }
"prod"    { "Deploy to PRODUCTION with approval gate" }
default   { throw "Unknown environment: ${Environment}" }
}
...
minVersion="[version]\"2.0.0\""
currentVersion="[version]${Version}"
```
未降级。只有 switch 头被 TODO；**臂原样泄漏**。`[version]` 转换被作为字面字符串发出。

### 2. 转换路径 / 根因
两个独立原因：
- **Switch：** 守卫 `re.match(r"(?i)^switch\b", text)`（`powershell.py:1017`）要求 `switch` 在语句开头。这里它是 `$action = switch (…) {` 的 RHS，因此 `_match_assignment`（`:1612`）先捕获。`_emit_assignment` 通过属性访问检查（`:1655-1656`，匹配 `$Environment.ToLower`）更早将其 TODO，且 **没有压入 comment/switch 块** — 因此臂被当作普通语句处理并泄漏，switch 的闭合 `}` 被外层函数块消耗（大括号失同步）。语句开头的 *裸* `switch` 会安全地注释降级（`:1017-1025`）— 已由探针确认。
- **`[version]`：** RHS 类型转换未被剥离。`_PS_TYPE_NAMES`（`:45-48`）缺少 `version`/`pscustomobject`/`ordered`；语句前置注解由 `_classify_annotated_statement`（`:936-972`）处理，但 RHS `[type]value` 没有。`_emit_assignment` 落到 `:1741-1742` → `minVersion="[version]\"2.0.0\""`。（Bash 字符串 `-lt` 也是字典序，不是语义版本比较。）

**根因：** switch 仅在语句开头识别（赋值包裹的 switch 丢失块状态）；RHS 类型转换前缀从不剥离。

### 3. 影响面
管道/赋值/表达式中的 switch、`=>__` script-block 臂，以及所有赋值中的 RHS 转换 `[int]`、`[string]`、`[version]`、`[datetime]` 等。`bash -n` 不掩盖。静默行为丢失：`$action` 从未赋值；`$isValid` 是未转换的字符串表达式（`isValid="(...) -or (...)"`），因此后续 `if [[ ${isValid:-} ]]` 始终为真。

### 4. 修复范围
- **Switch 部分：** 由统一未知大括号开启符回退覆盖（见下）；或者，在属性访问 TODO 之前检测 RHS 中的 `switch` 并打开 comment/pending 容器。约 20–30 LOC。
- **`[version]` 部分：** 在 `_emit_assignment`/`_convert_expression` 中剥离前导 `[type]` 转换（并将 `version` 等加入可识别转换集合），可选地对版本比较语义发出警告。约 10–15 LOC。
- 连带风险：剥离顺序重要 — `.NET` 静态（`]::`）在 `:1657-1658` 处理且必须优先于通用 `[type]` 剥离；`[PSCustomObject]@{` 必须先被哈希表收集器捕获。

### 5. 测试路径
镜像 `test_unknown_type_annotation_todo`（`tests/test_powershell.py:849`）/ `test_type_cast_statement_todo`（`:860`）做转换，`test_where_object_complex_todo`（`:374`）做 TODO 断言风格。新增：
- `test_switch_in_assignment_arms_not_raw(convert_ps, bash_check)` — 没有未注释行以带引号臂开头（`"dev"`）；无 `"多余的 }"`；`bash_check`。
- `test_version_typecast_rhs_stripped(convert_ps, bash_check)` — 断言 `minVersion="2.0.0"` 且没有未注释的 `[version]`。
- `test_version_comparison_warns_semantics(convert_ps)` — 警告类别 `control_flow`。
适配 `pytest -q`。

### 6. 优先级
中严重度 × 中成本（转换部分便宜）→ **排名 4**。

---

## 语料频率证据
CC0 语料 `tests/fixtures/real-corpus/fleschutz/*.ps1`（60 文件）：
```
try       57/60 (95%)     catch     57/60 (95%)     finally 0
begin{ / process{ / end{  0             switch    0
[ordered]@ / @{ / [PSCustomObject]@ / [version]   0
```
更广的 `tests/fixtures` + `examples`（62 个 `.ps1`）：相同画像（try/catch 主导；无哈希表/switch/高级函数样本）。

用户语料 `/home/duanjb666/下载/*.ps1`（10 文件）：
```
@{ (any hashtable) 7/10      [PSCustomObject]@ 3/10     try 2/10     catch 2/10
switch 2/10                  [ordered]@ 1/10            finally 1/10
begin{ / process{ / end{ 1/10                          [version] 1/10
standalone "}"+newline+"catch": 2/2 catch files;   same-line "} catch": 0
```
要点：(a) try/catch 无处不在，但 **测试套件只覆盖同行 `} catch {` 形态，而用户语料中该形态出现 0 次**；(b) 通用哈希表 `@{` 常见（70%），值得一等收集器；(c) switch/高级函数/`[ordered]`/`[version]` 频率较低但各至少命中一次，且每次都静默损坏结构。

---

## 最终排名表

| 排名 | 缺陷 | 严重度 | 修复成本 | 共享根因 | 已降级？ | 静默丢失？ |
|------|--------|----------|----------|-------------|-----------|--------------|
| 1 | **109** try/catch/finally 独立行 + 多臂 | 高（95% 语料） | 中 | 分支关键字派发 + 块栈 | 形态相关 | 是（catch/finally 永不运行） |
| 2 | **111** begin/process/end | 高 | 低–中 | 未注册大括号开启符 | 否 | 结构性 |
| 3 | **105** `[ordered]@{…}` 字面量 | 高 | 高 | 未注册 `@{` 字面量 + 通用 RHS 回退 | 否 | 是（`.Keys` 空循环） |
| 4 | **114** 赋值内 switch + `[version]` | 中（转换便宜） | 中 | 未注册大括号开启符 + RHS 转换 | 否 | 是（`$action` 未赋值） |

## 建议 — 先统一重构，再针对性修复
一次 **统一的块栈加固** 可解决 4 个中 3 个的共享根因（105、111 和 114 的 switch 半），并降低 109 风险：

1. **集中大括号开启识别** — 登记的构造头注册表（`if/elseif/else/foreach/for/while/do/function/try/catch/finally/begin/process/end/clean/dynamicparam/switch`）加上回退：当逻辑行开启一个没有已登记块认领的 `{`/`@{`（且非内联平衡或已知字面量）时，压入安全 `_Block("comment")` 容器，使正文 **被注释且大括号平衡** 而不是原样泄漏。这彻底止住原样泄漏 + 大括号失同步类问题，并对新构造未来防护。（约 40–60 LOC）
2. **统一分支派发** — 将独立 `catch`/`finally`/`else`/`elseif` 路由到分支处理器，无论 `_try_buffer` 如何；多臂/带类型 try 复用注释降级路径。（109）
3. **RHS 类型转换剥离** — `_emit_assignment` 中的 `[version]`/`[type]`。（114-转换）
4. **哈希表字面量语义** — 收集器 → `declare -A`（扁平）或注释降级，加上 `.Keys`/索引处理。（105）

**建议顺序：** 先做统一块栈遍历（修复 111 + switch-114 泄漏 + 105 泄漏 + 防止各处大括号失同步），再做 109 多臂语义，然后 114 `[version]`，最后 105 深层哈希表/`.Keys` 语义。如果必须严格逐缺陷推进，顺序为 **109 → 111 → 105 → 114**，但每个零散补丁都会重新触碰同一批 `_convert_statement`/`_close_block_line`/`_pop_block` 代码，统一遍历的改动量更低。

**关于安全网的说明：** 当前 `bash -n` 降级无法捕获上述任何一项（所有输出都是语法合法的 bash）；无论选择哪种修复，都要添加 **断言语义不变量的 fixture 测试**（无未注释泄漏关键字、无悬空 `else`、内容保留），而不是依赖 `bash -n`。

## Git 状态（最终）
```
$ git -C /home/duanjb666/bat2sh status --short
(empty)
```
仓库干净。两个 `下载/*.sh` 文件是预先存在的批处理派生输出（2026-09-14），不是本次会话产生的（所有运行都使用 `--print`）。现有套件基线：`120 passed`（`tests/test_powershell.py` + `tests/test_powershell_syntax_guard.py`）。制品：`/tmp/opencode/b3/out/def{105,109,111,114}.print.out` 和 `…report.json`。
