# Session C(lex) 设计说明 —— 词法层残余额账 + 修复草案（v1.10.0rc1）

> 定位：本文件是 `session-lex-review.md` 裁定「**退回设计文档**」后的**主要产出**。
> 它把 4 条残余（044/059/135/138）固化为**只读、可校验、可复现**的台账，
> 并给出**实现级修复草案**（供后续版本执行），**本版不实现任何转换改动**。
> 配套代码：`python/bat2sh/core/lexical_residuals.py`、`tools/lex/lexical_report.py`、
> `tests/test_lexical_residuals.py`。

---

## 1. 背景与定位

- 053 块栈失同步（v1.9.0 / `61a4b44`）与 A1 `%VAR%` 冻结（v1.9.2）之后，
  语料仍剩 **4 个 degraded 文件**触发转换器的**循环变量逸出守卫**
  （消息 `循环变量 %%x 逸出 for 循环（块结构失同步）`，`batch.py:2695-2703`）。
- 任务书把 4 条统称「真块失同步」。**实测证伪**：只有 2 条是块栈/头切分歧义，
  另 2 条是守卫**误报**（词法切分）。
- 因三条机制均**指标中性**（无文件翻转）且风险落在**块栈核心 / A1 热路径**，
  按纪律 1/10 与 1.x「最高风险项」定位，本版**只固化不实现**。

## 2. 台账（第五张只读表）

| ID | 文件（仪器 ID） | 机制 | 触及 053 | 触及 A1 | 风险 | 状态 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **LF-1** | 044 `备份文件/备份服务.bat`、135 `系统优化.bat` | **for 头切分**：外层 `for` 的 `in (…)` 被贪婪正则切到内层 `for` 的 `)` | 同函数核心 | 否 | 中–高 | backlog |
| **LF-2** | 059 `打开快捷方式指向的目录.bat` | **守卫误报**：引号内/nested-`cmd` 字符串里的字面 `%%X` 被当 for 变量 | 否 | **是** | 高 | backlog |
| **LF-3** | 138 `获取U盘盘符和可用容量.bat` | **子串切分**：`_protect_arith_modulo` 不识别 `%VAR:~n,m%`，残余 `%m` 被读成 `%%m` | 否 | 关联 | 低–中 | backlog |

> 任务书列 `059 判断分区格式.bat`、`138 批处理生成的CMD命令帮助清单.bat` 与仪器编号不符
> （详见 `session-lex-coldstart.md` §3.2）；以仪器为准。

## 3. 根因与修复草案

### 3.1 LF-1（044/135）——`for` 头部正则贪婪

**位置**：`core/batch.py:2092`

```python
r"(?i)^for\s+(.*?)%%~?([a-z])\s+in\s+\((.*)\)\s+do\s*(.*)$"
```

**根因**：`\((.*)\)` 贪婪；对 `for %%j in (a) do (for %%s in (b) do echo %%j %%s)`，
`(.*)` 会吃到**内层** `(b)`，于是 `set_text = "a) do (for %%s in (b"`、`body = "echo %%j %%s)"`
→ 外层循环变量丢失、内层 for 未被解析。

**最小复现**（`/tmp/lex/`）：
`for %%j in (a) do (for %%s in (b) do echo %%j %%s)` → 逸出 TODO；
`&&` / 普通 for 变体产物 **`bash -n` 失败**。

**修复草案（收窄）**：

1. 先用现有正则做**粗匹配**拿到 `do` 之后的 `body` 与 `opts/var`；
2. 对 `in (` 起点做**平衡括号扫描**（复用 `find_matching` / `_paren_close_split` 的语义），
   取**第一个**深度归零的 `)` 作为 `set_text` 结束——仅当粗匹配的 `set_text` 内出现
   `) do`（= 已误切）时才回退到平衡扫描，把改动面收窄到真正受影响的 4 个文件。

**churn 上界**：10 行 / 4 文件（031 已语法失败、104 ENV rc2、044、135）。
**为何本版不做**：改的是**所有 for 行的入口正则**（for 是所有循环的咽喉），
且即便修好也**无文件翻转**（044 仍有 path/pipeline TODO；135 仍 443 TODO）→ 净收益 0、核心风险非 0。

### 3.2 LF-2（059）——leak 守卫的引号/nested-`cmd` 盲区

**位置**：`core/batch.py:928-935`（`loop_repl`）+ `:2695-2703`（守卫消费）

```python
def loop_repl(m):
    ch = m.group(1).lower()
    if ch in self._loop_vars:
        return "${%s}" % ch
    self._warn(lineno, f"循环变量 %%{m.group(1)} 出现在 for 循环之外", ...)
    if not self._loop_vars:
        self._loop_var_leak = True          # ← 载荷性兜底
    return "%" + m.group(1)
```

**根因**：cmd 语义下 `%%X` **只在活动 for 体内**才是循环变量；否则是**字面 `%X`**
（wine 实测：`echo "for /l %%i in (…)"` → `"for /l %i in (…)"`）。
`loop_repl` 只看 `_loop_vars` 是否为空，无法区分「**引号内/嵌套 `cmd /c` 字符串里的字面 `%%X`**」
与「**真失同步漏出的 for 变量**」。

**修复草案（若做）**：在 `_expand_vars` 入口做**引号/字符串态**标注，
对「处于引号内」或「处于 `cmd /c "…"` / `start … "…"` 等 nested-command 字符串内」的 `%%X`
按**字面**处理且**不置 leak**；对引号外、且 `_loop_vars` 为空的 `%%X` **保持**现有守卫。

**为何本版不做**：

1. 触 **`_expand_vars`（A1 已修热路径）**，并落在 **Session A 锚点 `:1097-1114`（`env_repl`）附近**；
2. 守卫是载荷性兜底——误收窄会把 044/135 的**真**失同步从「TODO（安全）」降级为
   「`%j` 字面（**静默错**）」，直接违反纪律 1/13；
3. 收益为 0（059 仍 degraded）。

### 3.3 LF-3（138）——`_protect_arith_modulo` 子串盲区

**位置**：`core/batch.py:128-152`

```python
_ARITH_VAR_RE = re.compile(r"%([^\W\d]\w*)%")     # 只认 %VAR%，不认 %VAR:~n,m%
...
if text.startswith("%%", index):
    following = text[index + 2 : index + 3]
    if not (following.isascii() and following.isalpha()):
        out.append(_PERCENT_MODULO); index += 2; continue
```

**根因**：对 `set /a m3=%m3%%m:~0,1%%%%~1`，`%m:~0,1%` 不被识别；
其**收尾 `%`** 与下一个 `%` 配成 `%%` → 被替换为取模占位符 → 残留 `%m` 被后续
`loop_repl` 读成 `%%m` → 守卫误报。

**修复草案（若做）**：在 `_protect_arith_modulo` 中并列识别**子串式**
`%VAR:~[^%]*%`（与 `_expand_vars` 的子串正则同源），整段透传后再找 `%%`。

**为何本版不做**：① 138 源行本身退化（wine `set /a m3=…` 报错、值不变），
「修成什么」语义不明；② churn 仅 083/138 两文件、收益 0；
③ 违反纪律 13（语义正确性与 rc==0 并列）——宁可保守 TODO。

## 4. 替代方案裁定

| 方案 | 结论 |
| :--- | :--- |
| A 修 LF-1 头正则 | ❌ 本版不做（草案已备，见 §3.1）→ v2.0/后续 |
| B 修 LF-2 守卫 quote-aware | ❌ 不做（双红线 + 载荷性） |
| C 修 LF-3 子串识别 | ❌ 不做（退化源 + 收益 0） |
| D 撞库模板 | ❌ 不采用（C4 已判形态数十种） |
| E 只读台账 + 工具 | ✅ **采用**（本版） |

## 5. 验收（客观）

1. `validate_lexical_residuals() == []`；
2. `python3 tools/lex/lexical_report.py` 复现 4 条残余（8/8 或 CORPUS 计数一致）；
3. pytest ≥ 1360 且 0 failed；
4. 转换产物**逐字节 0 diff**；examples 0 漂移；
5. 151 语料：语法 147 / rc==0 102 / strict 16 / degraded 86 / 崩溃 0；
6. wine harness 6/6；
7. `release-preflight.sh` 通过；tag 上 CI 全绿。

## 6. 纪律对照

| 纪律 | 落实 |
| :--- | :--- |
| 1 保守 TODO | 4 条全部维持现有诚实 TODO，零转换改动 |
| 2 只读诊断先行 | 冷启动/review/复现/矩阵/churn 全部在实现决定前完成 |
| 3 主动披露偏离 | 任务书编号/文件名偏差、135=443（非 439）、子代理不可用 |
| 4 不发明映射 | 每条 residual 附 `file:line` + 最小复现 + wine 实测 |
| 6 置信度光谱 | 台账每条 `confidence`（A–D），D 档不得标 fixed |
| 7 缺 evidence 拒绝 | `validate_lexical_residuals()` 强制 evidence 非空 |
| 9 仪器先验证 | wine 锚定 + 只读复现 + churn 上界 |
| 10 锁定 HEAD | 起点 `68dfbdd`，每次写前校验 |
| 13 语义与 rc==0 并列 | LF-1 若做可修「`bash -n` 失败」形态；本版仍以「不引入静默错」为先 |
