# P0 只读诊断 —— oracle 发现的三个缺陷（F1 / F2 / F3）

> 时间：2026-09-27 · 轨道：**产品**（修 bat2sh 代码）· 起点 HEAD：`9c096a4`（锁定，全程未动）
> 前置：路 A 运行时 oracle 已完成（`oracle-result.md` / `oracle-verdict.md`）
> 本文件：**Phase 1 只读诊断**（`src/` `python/` 零改动；`git status` 全程干净）
> 硬闸门：本文件完成后**暂停等用户确认**，不进入 Phase 2

---

## 0. 前置确认（任务书 §一）

| # | 项 | 结果 |
| :-: | :--- | :--- |
| 1 | 工作区干净，HEAD = `9c096a4` | ✅ `git status --porcelain` 空；`HEAD = 9c096a4df26f49f9b57c7efadff81293e992a721` |
| 2 | `oracle-result.md` 存在 | ✅ 292 行 |
| 3 | `oracle-verdict.md` 存在 | ✅ 110 行 |
| 4 | `pytest -q` 全绿 | ✅ **1613 passed**（163.24s，0 failed） |
| 5 | VM `win-behavior` 可用 | ✅ `virsh --connect qemu:///system` 列出（状态 `关闭`，可 `--no-start` 唤醒） |
| 6 | `collect.py` / `collect_linux.py` / `compare.py` 可跑 | ✅ 三者 `--help` 均正常；V1–V5 五个源文件 sha256 与 `oracle-samples.md` §2 **逐一对上** |

**基线指标（供 Phase 3 对比）**：

```
measure.py --corpus ~/下载/非常批处理
{"corpus": 151, "syntax_ok": 149, "rc0": 101, "strict": 19,
 "degraded": 82, "degraded_todos": 851, "crash": 0, "timeout": 0, "convert_error": 0}
```

与 `docs/PROJECT-OVERVIEW.md:21,26` 记载的 2.x 基线**逐字段一致** ⇒ 仪器可复现。

> ⚠️ **工作目录偏离披露**：本 session 的 session workspace 是 `/home/duanjb666/deepseek`，
> 而 bat2sh 仓库在 **`/home/duanjb666/bat2sh`**。全部操作按绝对路径在后者进行。

---

## 1. 诊断方法（只读，可复现）

| # | 手段 | 产出 |
| :-: | :--- | :--- |
| M1 | **最小复现**：直接用 `convert_text` 转 8 组片段，读产物字节（`od -c`） | 三缺陷各自稳定复现，与 oracle 报告逐字一致 |
| M2 | **代码定位**：按 `BATCH_HANDLER_MAP` 分派链回溯到具体函数/行 | 三个根因各自的**唯一**代码锚点 |
| M3 | **151 语料 + examples 全转**，在**产物**里正则找缺陷签名（不是在源文件里找模式） | 真实波及面（见 §5） |
| M4 | **候选补丁 A/B 对照**：把 `python/bat2sh` 拷到 `/tmp` 打不同补丁，量化爆炸半径 | §6 的实测表（仓库本体零改动） |
| M5 | **端到端跑**：把各变体产物丢进沙箱真跑，比对文件系统结果 | §6.3 —— 证明哪套补丁**真的**修好了 |
| M6 | **053/A1 观察名单**：按 `v2.4.0-053-protection.md` §3.3/§3.4 逐文件比对 | §7 —— A1 零回归**可证** |

---

## 2. F1 —— `type` 的 `\` 未转换

### 2.1 复现（M1）

```bat
@echo off
set "W=%~dp0sub"
mkdir "%W%"          →  mkdir -p "${W}"          ✅
echo data>"%W%\f.txt" →  echo "data" >"${W}/f.txt" ✅
copy /y …             →  cp -f "${W}/f.txt" …     ✅
type "%W%\f.txt"      →  cat "${W}\f.txt"        ❌ 反斜杠保留
del "%W%\f.txt"       →  rm -f "${W}/f.txt"      ✅
if exist …            →  if [ -e "${W}/f.txt" ]  ✅
dir /b "%W%"          →  ls -1 "${W}"            ✅
findstr …             →  grep … "${W}/g.txt"     ✅
```

`cat "${W}\f.txt"` 在 bash 里是**字面文件名** `…/sub\f.txt`（`\` 是合法文件名字符）⇒ 必然找不到。

### 2.2 根因（M2）

**唯一锚点：`python/bat2sh/core/batch.py:3349-3358` `cmd_type()`**

```python
def cmd_type(self, lineno: int, args: str, original: str) -> str:
    if args.strip().strip('"').lower() == "nul":
        …
        return ":"
    return ("cat " + args).strip()        # ← args 原样返回，零转换
```

分派链：`_convert_simple_no_pipe` → `first in rules.BATCH_HANDLER_MAP` → `"type": "cmd_type"` → `cmd_type`。
`args` 此时**已**是 `_expand_vars` 之后的文本（`%W%` → `${W}`），但**从未**过 `convert_backslashes`。

### 2.3 为什么只有 `type` 没转（M2，handler 全量审计）

对全部 41 个 `cmd_*` handler 做「是否调用 `convert_backslashes` / `_convert_path_token`」审计：

| 结论 | 证据 |
| :--- | :--- |
| **取文件路径的 handler 里，只有 `cmd_type` 两者皆无** | `cmd_cd`/`cmd_dir`/`cmd_del`/`cmd_rmdir`/`cmd_copy`/`cmd_move`/`cmd_xcopy`/`cmd_find`/`cmd_findstr`/`cmd_attrib`/`cmd_certutil` 全部走 `_convert_path_token`；`cmd_echo`/`cmd_set`/`cmd_start`/`cmd_ping`/`cmd_runas` 走 `convert_backslashes` |
| 其余「两者皆无」的 handler 不取路径 | `cmd_pause`/`cmd_cls`/`cmd_ver`/`cmd_choice`/`cmd_shutdown`/… 无路径参数 |

`type` 同时出现在 `BATCH_SIMPLE_MAP`（`"type": "cat"`，rules.py:19）与 `BATCH_HANDLER_MAP`（rules.py:47）。
**handler 优先**，于是绕开了 `_convert_simple_no_pipe:3032` 那条会做 `convert_backslashes(rest)` 的
`BATCH_SIMPLE_MAP` 分支 —— 这就是「别的命令都转了」的确切原因。

> 补充（oracle 未报、本 session 新发现）：`type` 还有**第二类**失败路径 —— 当 `\` 后面紧跟变量时
> （`type "%destination%\%name_log%_log.log"`），即使补上 `convert_backslashes` 也**仍然不转**，
> 因为展开插入的 `$` 让 `\` 看起来像转义符。见 §4。

### 2.4 修复方案

```python
return ("cat " + convert_backslashes(args)).strip()
```

理由：与 `BATCH_SIMPLE_MAP` 分支（`:3032`）**逐字同构**，不引入新映射（纪律 6）；
`convert_backslashes` 是引号感知的，且只用 `_expand_vars` 之后的文本 ⇒ 与 `cmd_echo` 同款处理。
**不用** `_convert_path_token`：`type a.txt b.txt` 是多参数，`_convert_path_token` 只处理单 token 且会加引号。

### 2.5 影响面（M3/M4 实测）

| 项 | 结果 |
| :--- | :--- |
| 151 语料命中 `type` | **5** 个文件（**行首**口径，= 转换器实际分派到 `cmd_type` 的口径）；其中路径带 `\` 的 **2** 个 |
| 产物字节漂移 | **1/155**（`史上最牛X…` 的 2 行 `cat /\jzcx.txt` → `cat //jzcx.txt`） |
| `todo_count` 变化 | **0** |
| examples 漂移 | **0** |
| 端到端 | ✅ `type "%W%\f.txt"` 修复（rc 1→0、stdout 由空→`data`） |

> `cat //jzcx.txt`：源为 `type %windir%\jzcx.txt`，而 `rules.py:240` 把 `WINDIR` 映射为 `/`（本身有损、**既有行为**）。
> `//x` 在 Linux 上等价 `/x`。属**改善**（`\` 消失），但会动到 053 观察名单里的
> `031 史上最牛X…` ⇒ 按 §3.3 规则**必须解释**（见 §7）。
>
> **口径差异说明（主动披露）**：本节数字是**行首 `type`** 的严格口径（5 个文件，
> 与转换器实际分派面一致）。`oracle-result.md` §3.1 记的是「`type` 出现于 **8** 个文件」，
> 判据更宽（含管道/连接符位置）。本 session 按宽松判据复扫得 **14** 个文件
> —— 三者判据不同，**不是矛盾**，但也不能互相引用为同一数字。

---

## 3. F2 —— `for /d` 集合末元素被当成通配符

### 3.1 复现（M1）

```bat
for /d %%i in (aa,bb,cc) do md %%i
```
```bash
shopt -s nullglob            # ← 被误判为需要
for i in aa bb cc/*/; do     # ← 末元素被追加 /*/
    mkdir -p ${i}
done
```

`nullglob` 下 `cc/*/` 若无匹配 ⇒ **整个词被静默删除**，`cc` 从未被建。

### 3.2 根因（M2）

**唯一锚点：`python/bat2sh/core/batch.py:2265-2268`（`_convert_for` 内）**

```python
elif "/d" in opts_lower:
    if not items.endswith("*"):
        items = items.rstrip(" *") + "/*"      # ← 对**整串**做尾部追加
    items += "/"
```

**「为什么总是最后一个」的确切答案**：`items` 不是列表，而是 `_convert_for_set` 返回的
**已拼接好的单个字符串**（`"aa bb cc"`，`_convert_for_set:2700-2709` 末尾 `" ".join(fixed)`）。
`items.rstrip(" *") + "/*"` 与 `items += "/"` 都是**字符串尾部操作** ⇒ 只能命中**最后一个 token**。
与随机无关，是**纯位置性**的。

单元素 `(aa)` 会得到 `aa/*/` —— 说明作者原意是「单元素时把该元素当目录前缀、枚举其子目录」，
但 (a) 该语义并非 cmd 语义，(b) 实现在**多元素**下退化成「只改末元素」。

### 3.3 `for /d` 的 cmd 语义（证据，非推测）

`oracle-result.md` §3.2 的真机指纹是硬证据：V1 源为

```bat
for /d %%i in (樱野,王子变青蛙,其他) do md %%i
```

**W（真机 cmd.exe）建出 3 个目录** `樱野`/`王子变青蛙`/`其他`。
这三个目录在循环开始时**都不存在** ⇒ **不含通配符的元素被 cmd 按字面产出，不做存在性检查、不做通配符展开**。
对照 `for /d %%d in (sub\*)`（`tests/test_batch.py:699`）：含通配符时才对**目录**做匹配。

⇒ 正确映射规则（两条，均有证据）：

| 元素形态 | cmd 行为 | bash 映射 |
| :--- | :--- | :--- |
| 无 `*`/`?` | 字面产出 | **原样**（不加任何后缀） |
| 含 `*`/`?` | 按目录匹配 | 追加 `/`（bash 尾斜杠 = 只匹配目录） |

### 3.4 修复方案

```python
elif "/d" in opts_lower:
    items = " ".join(
        (t + "/") if ("*" in t or "?" in t) and not t.endswith("/") else t
        for t in tokenize_args(items)
    )
```

**逐元素**判定，取代**整串尾部**追加。`tokenize_args` 是引号/`$(...)` 感知的，且对
`_convert_for_set` 的输出幂等（其输出本就是它拼的）。

自检：`sub\*` → `_convert_for_set` → `sub/*` → 含 `*` → `sub/*/` ⇒ `tests/test_batch.py::test_for_d`
断言 `for d in sub/*/; do` **仍成立**（已实测通过）。`(*)` → `*/` 不变。`(aa,bb,cc)` → `aa bb cc` ✅。

**附带正确效果**：V1 的 `items` 不再含通配符 ⇒ `_note_glob` 不再注入 `shopt -s nullglob`
与该行误导性注释（**这正是 F2 静默的帮凶**）。

### 3.5 影响面（M3/M4 实测）

| 项 | 结果 |
| :--- | :--- |
| 151 语料命中 `for /d` | **2** 个文件；逗号列表 **1** 个（V1） |
| 产物字节漂移（F1+F2） | **2/155** |
| `todo_count` 变化 | **0** |
| examples 漂移 | **0**（`examples/stress_test.bat:114` 是 `for /d %%d in (*)` ⇒ `*/` 不变） |
| 端到端 | ✅ 建出 `aa`/`bb`/`cc`（基线只建 2 个） |

---

## 4. F3 —— `for /r` + `%%~ni` 建出字面文件

### 4.1 复现（M1，`od -c` 实证）

```bat
for /r %%i in (.) do (cd.>"%%i\%%~ni.txt")
```
```bash
while IFS= read -r i; do
    cd "." >"${i:-}\\$(basename "${i%.*}").txt"
done < <(find . -type d)
```
实际建出 **6 字符文件 `.\.txt`**（`od -c` = `. \ . t x t`），应为 `samples.txt`。

### 4.2 根因是两个**互相独立**的机制

#### F3-a：反斜杠后接变量 ⇒ 转换顺序倒置

`_render_redirs:3130` 是 `convert_backslashes(self._expand_vars(inner, lineno))` ——
**先展开、后转反斜杠**。源里的 `\` 紧跟 `%%~ni`，展开后变成紧跟 `$`；
而 `convert_backslashes`（`utils.py:148`）只在 `\` 后是路径字符/字母数字时才换，
看到 `$` 便判为「转义符」而**保留**。随后 `_dq_preserving_substitutions:2208` 又把 `\` 转义成 `\\`。

> **这不是 F3 专有**。同一机制在 151 语料里命中 **14 个文件 / 48 处**（M3 实测），
> 例如 `文件备份器V2.3修改版2.cmd`：`}"${destination}\${name_log}_log.log"` ——
> 产物是**带字面反斜杠的文件名**。本 session 把这部分单列为 **F5 候选**（§8.2），
> **只修 F3 用到的那一处**，不趁机扩大改动面。

#### F3-b：`%%~ni` 的 bash 表达式对 `find` 的值域不成立

**锚点：`batch.py:1250`（`_modifier`）**

```python
if "n" in mods:
    return f'$(basename "${{{var}%.*}}")'
```

`${i%.*}` 从**整个字符串的最后一个点**起剥。对 `for %%f in (*.txt)` 的值 `a.txt` ⇒ `a` ✅
（`tests/test_batch_loop_modifier.py:33` 覆盖的就是这种）。
但 `_emit_for_r:2354` 用 `find . -type d` 取值，值域是 **`.` 与 `./sub`** —— **每个值都带前导点**：

| `i` | `${i%.*}` | `basename` | 应为（cmd `%%~ni`） |
| :--- | :--- | :--- | :--- |
| `.` | `""` | `""` | `samples`（工作根目录名） |
| `./sub` | `""` | `""` | `sub` |

⇒ 对 `find` 值域**恒为空**。这正是「`.\.txt`」的由来。
（`%%~nxi` 用 `basename "${i}"`，对 `.` 得 `.` —— 同类问题，只是不显眼。）

### 4.3 修复方案（两步，缺一不可）

**M5 实测：只做任一步都不够** ——
只修 F3-b ⇒ `. \samples.txt`（仍是错文件名）；只修 F3-a ⇒ `.txt`（名字仍空）。

**F3-a（窄修）**：`batch.py:3130` 把顺序倒过来

```python
converted = self._expand_vars(convert_backslashes(inner), lineno)
```

只作用于**重定向目标**。cmd 里 `\` 本就不是转义符，先转换与后转换对 `\word` 完全等价
（`convert_backslashes` 的字符集判据不依赖 `$`），差别**只**出现在「`\` 后跟变量」这一种形态。

**F3-b**：`batch.py:2354` 让 `find` 产出**绝对路径**

```python
if target in (".", '""'):
    close_word = 'done < <(find "$PWD" -type d)'
else:
    close_word = f'done < <(cd {target} && find "$PWD" -type d)'
```

三个理由：
1. **同时修好 `%%~n` 与 `%%~nx` 且不碰 `_modifier`**（A1 热路径，§7）—— 绝对路径无前导 `./`，
   `basename "${i%.*}"` 自然成立；
2. **让 `%%i` 更接近 cmd**：cmd 的 `for /r` 产出的是 `C:\poc\samples\sub` 这样的**绝对路径**，
   而当前产物给的是 `.`/`./a` —— 这是一处**此前未被 oracle 报出的保真度缺口**；
3. `cd {target} && find "$PWD"` 对**相对根与绝对根都正确**，且 `cd` 发生在进程替换的子壳里，
   不污染主壳 cwd。

> ❌ **已否决的写法**：`find "$PWD"/{target}`。M4 实测它在 `美化文件夹背景.bat` 上产出
> `find "$PWD"/"${back:-.}"` —— 若 `back` 是绝对路径（cmd 完全允许），会退化成 `<cwd>/E:/…`，
> **引入新缺陷**。`cd` 形式无此问题。

### 4.4 影响面（M3/M4 实测）

| 项 | 结果 |
| :--- | :--- |
| 151 语料命中 `for /r` | **6** 个文件；`%%~n` 系列 **12** 个文件 |
| `basename "${v%.*}"` 产物签名 | **7** 个文件；其中**必然坏**的只有 V5（唯一 `for /r` 驱动）；另 6 个是**潜在**（值域含点才坏） |
| 产物字节漂移（F1+F2+F3） | **6/155** |
| `todo_count` 变化 | **0** |
| examples 漂移 | **0** |
| 端到端 | ✅ `for /r %%i in (.)` 产出 `samples.txt`；`for /r sub %%i in (.)` 产出 `sub/sub.txt` |

### 4.5 已知限制（**必须随版本披露**）

1. **`%%~n` 的通用表达式仍是 `basename "${v%.*}"`，未加固。**
   绝对路径后，只有当**父目录某段含点**（如 `~/my.project/`）时才会截错。
   比修复前（`find .` ⇒ 恒坏）严格更好，但**未根除**。
   彻底加固要把 `_modifier:1250` 改成「先取末段、再剥扩展名」，那是 **A1 热路径** ⇒ 需另开带防护的改动。
   **本 session 不做**，登记 backlog。
2. **`%%i` 的值由相对变绝对** —— 语义变化。这是**向 cmd 靠拢**，但会改变依赖 `%%i` 文本形态的脚本行为，须披露。
   连带 `tests/test_batch_for_r.py` **4 条断言需重写**（§6.4）。
3. **F5 未修**：`\` 后接变量的**非重定向**形态（45 处 / 13 文件）**仍然错**（§8.2）。

---

## 5. 三个缺陷的关系与优先级输入

| | F1 | F2 | F3 |
| :--- | :--- | :--- | :--- |
| 根因数 | 1（`cmd_type` 绕过） | 1（整串尾部追加） | **2**（顺序倒置 + `%%~n` 值域） |
| 静默程度 | 半静默（stderr 有错、rc 被污染） | **完全静默** | **完全静默** |
| 代码锚点 | `cmd_type:3358` | `_convert_for:2265-2268` | `_render_redirs:3130` + `_emit_for_r:2354` |
| 触 053 域 | ❌ 否 | ⚠️ **是（函数级）** | ⚠️ **是（函数级，`_emit_for_r`）** |
| 触 A1 域 | ❌ 否 | ❌ 否 | ❌ 否 |
| 漂移 | 1/155 | +1 = 2/155 | +4 = 6/155 |
| 需改测试 | 0 | 0 | **4**（`test_batch_for_r.py`） |

**关键判断：三个修复都**不**需要触 `_expand_vars` / `env_repl` / `_a1_*` / `_register_assigned`。**

「通用修 F3-a / F5」的写法（在 `_expand_vars` 顶部加「反斜杠后接变量」预转换）**确实**修好了三缺陷，
但 M4 实测漂移从 **6/155 涨到 17/155**，且**正面命中 A1 热路径** ⇒ **本 session 不采用**。

---

## 6. 修复方案汇总与爆炸半径（M4/M5 全量实测）

### 6.1 变体对照表

在 `/tmp` 的 `python/bat2sh` **副本**上打补丁（仓库零改动），转换 **151 语料 + 4 examples = 155 文件**：

| 变体 | 补丁 | F1 | F2 | F3 | 产物漂移 | todo 变化 | examples 漂移 |
| :--- | :--- | :-: | :-: | :-: | ---: | ---: | ---: |
| `base` | 无 | ❌ | ❌ | ❌ | — | — | — |
| `F1` | `cmd_type` + `convert_backslashes` | ✅ | ❌ | ❌ | 1/155 | 0 | **0** |
| `F1F2` | + 逐元素 `/d` | ✅ | ✅ | ❌ | 2/155 | 0 | **0** |
| `F1F2_F3babs` | + `find "$PWD"/…`（**已否决**写法） | ✅ | ✅ | ❌ | 5/155 | 0 | 0 |
| `F1F2_F3rinly` | + 只换 `_render_redirs` 顺序 | ✅ | ✅ | ❌ | 4/155 | 0 | 0 |
| **`rec`（推荐）** | + `cd` 式绝对 `find` | **✅** | **✅** | **✅** | **6/155** | **0** | **0** |
| `F1F2_F3all_gen` | 通用预转换（触 A1） | ✅ | ✅ | ✅ | **17/155** | 0 | 0 |

### 6.2 推荐方案的 6 个漂移文件（逐行 diff 已人工复核，**全部是改善**）

| 文件 | 变化 | 判定 |
| :--- | :--- | :--- |
| `快速创建文件夹.bat`（V1） | `for i in 樱野 王子变青蛙 其他/*/` → `… 其他`；删掉误加的 `shopt -s nullglob` | ✅ F2 修复 |
| `以文件夹名为名建立文本文件.cmd`（V5） | `\\$(basename …)` → `/$(basename …)`；`find . -type d` → `find "$PWD" -type d` | ✅ F3 修复 |
| `史上最牛X…`（031） | `cat /\jzcx.txt` → `cat //jzcx.txt` ×2 | ✅ F1 修复（`//` 与 `/` 在 Linux 等价） |
| `文件备份器V2.3修改版2.cmd` | `}"${destination}\\${name_log}…"` → `}"${destination}/${name_log}…"` ×2 | ✅ F3-a 修复（原为字面反斜杠文件名） |
| `查找最新的文件.bat` | `find . -type d` → `find "$PWD" -type d` | ✅ 同 F3-b；无其它行为变化 |
| `美化文件夹背景.bat` | `find "${back:-.}" -type d` → `cd "${back:-.}" && find "$PWD" -type d` | ✅ 绝对/相对根都对 |

`todo_count` **155 个文件全部未变**；**examples 4 个文件零字节漂移**。

### 6.3 端到端验证（M5，沙箱真跑）

| 变体 | F1 `type "%W%\f.txt"` | F2 `for /d %%i in (aa,bb,cc)` | F3 `for /r %%i in (.)` | F3b `for /r sub %%i in (.)` |
| :--- | :--- | :--- | :--- | :--- |
| `base` | ❌ rc=1、stdout 空 | ❌ 只建 `aa,bb` | ❌ `.\.txt` | ❌ `sub\sub.txt` |
| **`rec`** | ✅ rc=0、`data` | ✅ `aa,bb,cc` | ✅ `samples.txt` | ✅ `sub/sub.txt` |

### 6.4 需同步更新的测试（4 条，全在 `tests/test_batch_for_r.py`）

| 行 | 现断言 | 问题 | 改为 |
| ---: | :--- | :--- | :--- |
| 18 | `'done < <(find . -type d)' in out` | 编码现况 | 语义：`find` + `-type d` + `"$PWD"` |
| 36 | `{".", "./a", "./a/b", "./c"} <= enumerated` | 编码现况（相对路径） | 语义：递归枚举**全部**目录（含根），可用 `realpath` 归一后比较 |
| 45 | `'done < <(find . -type d)' in out` | 同上 | 同上 |
| 51 | `'find "${back:-.}" -type d' in out` | 编码现况 | 语义：变量根被解析且 `cd` 进该根 |

> 这 4 条**不是**「测试挡路就改测试」：它们断言的正是**当前实现细节**（相对路径、字面命令串），
> 而 §4.3 已论证 cmd 语义是绝对路径 ⇒ 按**纪律 9**（断言验证语义）重写。
> 副本实测结果：`8 failed, 1605 passed` —— 8 条失败里 **4 条是上述待改断言**，
> 另 4 条是 `test_packaging.py`（最小副本未拷 `bat2sh.desktop` / MIME XML，**与本次改动无关**）。
> 即：**除这 4 条外无任何回归** —— 含 `test_for_d`、`test_batch_block_stack_v190.py`、
> `test_batch_var_block_freeze.py`、`test_batch_loop_modifier.py`、`test_batch_loop_modifier_path.py`
> 在内的 053/A1 专项全部保持通过。

---

## 7. 053 / A1 判定（逐项，按 `docs/v2.4.0-053-protection.md`）

### 7.1 是否触及保护域

| 修复 | 代码锚点 | §2 是否列为保护域 | 判定 |
| :--- | :--- | :--- | :--- |
| F1 | `cmd_type`（`batch.py:3358`） | 否 | ✅ **不触 053/A1** |
| F2 | `_convert_for`（`batch.py:2265-2268`） | **是**（§2「块发射 · `_convert_for`」） | ⚠️ **触 053（函数级）**；改动点在 `items` 计算，**不 push/pop 块栈、不碰 marker** |
| F3-a | `_render_redirs`（`batch.py:3130`） | 否 | ⚠️ 不触保护域，但**全局改变重定向目标的展开顺序** ⇒ 按 D3 逐文件 diff 观察 |
| F3-b | `_emit_for_r`（`batch.py:2354`） | **是**（§2「块发射 · `_emit_for_r`」） | ⚠️ **触 053（函数级）**；只改 `close_word` 字符串构造，**不 push/pop 块栈** |
| 全部 | `_expand_vars` / `env_repl` / `_a1_*` / `_register_assigned` | 是 | ✅ **零改动** |

⇒ **A1 域零改动**；**053 域为函数级命中（2 处），改动点均在块栈机制之外**。
按 §3，**每个 commit 仍必须跑 D1–D4 四道检测**。

### 7.2 观察名单（已在推荐变体上**预先实测**，消除 Phase 2 的意外）

| 名单 | 判据 | 推荐变体实测 |
| :--- | :--- | :--- |
| §3.4 **A1 覆盖 7 文件** | `__bat2sh_snap_*` 行变化 ⇒ 暂停 | ✅ **7/7 行数未变**（109/21/6/5/0/2/0） |
| §3.3 **053 覆盖 5 文件** | rc/todo/markers/字节变化 ⇒ 暂停解释 | ✅ 4/5 **字节未变**；仅 `031 史上最牛X…` 变化 = **2 行 `cat`**（F1 直接效果，已解释）；**5/5 `todo_count` 未变** |
| 全量 151 | `todo_count` 变化 | ✅ **0 变化** |

⇒ Phase 2 若出现**上述之外**的变化，即为真回归。

### 7.3 建议的防护流程（Phase 2 执行）

按 `v2.4.0-053-protection.md` §3：

- **D1** 053+A1 专项 126 条 → 全绿
- **D2** 全量 pytest → ≥1613 passed（只增不减）
- **D3** `measure.py` 指标（`151/149/101/19/82/851/crash 0` **逐字段不变**）+ 逐文件判据 diff + 产物字节 diff
- **D4** examples 零漂移 + wine 6/6（`test_oracle_wine.py`）
- 每 commit 记录回滚锚点；**A1 回归 / 053 覆盖文件不可解释变化 ⇒ 立即回滚并停**

---

## 8. 修复优先级与顺序（风险升序）

### 8.1 建议顺序

| 序 | Commit | 风险 | 理由 |
| :-: | :--- | :--- | :--- |
| **1** | `fix(F1): type 命令的 \ 转换` | **最低** | 不触保护域；1 行；漂移 1/155；examples 0；端到端已证 |
| **2** | `fix(F2): for /d 末元素消失` | **中低** | 触 053 域（函数级）；4 行；漂移 +1；**附带去掉误导性 nullglob** |
| **3** | `fix(F3): for /r + %%~ni` | **最高** | **两个根因**；触 053 域（函数级）；漂移 +4；**语义变化（`%%i` 相对→绝对）**；需改 4 条测试；有 §4.5 已知限制 |

**每个 commit 独立可回滚**（D3 逐文件 diff 可归因）。F3 若在闸门被判定为过激，
**退路**是把 F3-a/F3-b 拆成两个 commit，或整体降级为「诚实 TODO」（见 §8.3）。

### 8.2 **新发现（oracle 未报）**：F5 候选 —— `\` 后接变量的**非重定向**形态

| 项 | 内容 |
| :--- | :--- |
| 现象 | `X\${Y}` / `X\$(` —— 反斜杠在产物里**保留**（甚至被 `\\` 加倍），成为字面文件名字符 |
| 根因 | 与 F3-a **同一机制**：`convert_backslashes` 在 `_expand_vars` **之后**运行 |
| 实测面 | 151 语料 **14 文件 / 48 处**；推荐方案只修掉其中 **1 文件 / 3 处** ⇒ **仍有 13 文件 / 45 处** |
| 举例 | `文件备份器V2.3修改版2.cmd`（余 3 处）、`提取IE缓存的指定文件.bat`（7 处）、`史上最牛X…`（11 处） |
| 彻底修法 | `_expand_vars` 顶部加「反斜杠后接变量」预转换 —— **触 A1 热路径**，M4 实测漂移 6→17/155 |
| 本 session 处置 | **不修**。按纪律 3 **主动披露**，登记为下一 session 的候选（需先走 053/A1 防护设计） |

> 这与任务书「只修 F1/F2/F3」不冲突：F3 的修复只取该机制在**重定向目标**上的那一处，
> 已足够让 `for /r` 复现转正，且**不扩大改动面**。F5 的完整修复应独立立项。

### 8.3 F3 的保守退路（若闸门认为绝对路径改动过大）

把 `for /r` 循环体内出现 **`%%~n`家族 或 `\`紧跟循环变量** 的形态降级为**诚实 TODO**
（不再产出静默错误的 bash）。零语义风险，代价是丢掉 `for /r` + `%%~n` 的转换能力。
**本 session 倾向不采用**（§6.3 已证明推荐方案在三类复现上端到端正确、examples 零漂移），
但作为硬闸门的备选方案列出。

---

## 9. 硬闸门 —— 待用户确认的四项

| # | 问题 | 本 session 建议 |
| :-: | :--- | :--- |
| **G1** | **F3-b 是否接受「`find` 产出绝对路径」**（连带 `%%i` 由 `.`/`./a` 变成绝对路径、需改 4 条测试断言）？ | **接受**。它同时修好 `%%~n`/`%%~nx` 而不碰 A1 热路径，且让 `%%i` 更接近 cmd（§4.3 三个理由） |
| **G2** | **F3-a 只做「重定向目标」窄修**（V5 复现够用），**F5 的另 45 处不修**？ | **是**。遵循「保守 + 不扩大改动面」；F5 单独立项（§8.2） |
| **G3** | **F3 触 053 域（`_emit_for_r` 函数级）是否走 v2.4.0 四道防护流程**（D1–D4 + §3.3/§3.4 观察名单）？ | **是**。§7.2 已预跑观察名单：A1 7/7 未变、053 仅 031 变化且可解释 |
| **G4** | **版本号**：`v2.10.1`（patch）还是 `v2.11.0`（minor）？ | **v2.10.1**。三处均为缺陷修复、无新功能。**但**：F3-b 改变了 `for /r` 的 `%%i` 值形态（相对→绝对），严格说是一处**行为变更** ⇒ 若用户认为需按 minor 披露，则取 `v2.11.0`。**请裁定** |

---

## 10. 纪律自查

| # | 纪律 | 执行 |
| :-: | :--- | :--- |
| 1 | 保守 TODO 优于激进转换 | ✅ 否决了「通用预转换」（漂移 6→17 且触 A1）；为 F3 备了 TODO 退路（§8.3） |
| 2 | 主动披露偏离 | ✅ 4 条：workspace 路径（§0）、F5 新缺陷（§8.2）、F3 已知限制（§4.5）、需改 4 条测试（§6.4） |
| 3 | **只读诊断先行** | ✅ 仓库 `git status` 全程干净；所有补丁只打在 `/tmp` 副本上 |
| 4 | 不发明映射 | ✅ `for /d` 的规则由**真机指纹**（V1 建出 3 目录）导出，非推测；`%%~ni` 目标值由 W 产物 `samples.txt` 导出 |
| 5 | 仪器先验证 | ✅ `measure.py` 基线 `151/149/101/19/82/851` 与文档记载逐字段一致；5 个样本 sha256 与 `oracle-samples.md` 对齐 |
| 6 | 锁定 HEAD | ✅ 全程 `9c096a4` |
| 7 | 测试断言验证语义 | ✅ §6.4 指出 4 条断言编码现况并按语义重写；§7.2 用 A1 snap 行（语义面）而非字节全等做 A1 判据 |

---

## 11. 一句话结论

> **三个缺陷的根因全部定位到唯一代码锚点，且三者互不相同**：
> F1 是 `cmd_type` 绕过了 `convert_backslashes`（其余取路径的 handler 都不绕）；
> F2 是把**拼接好的整串**当成列表做尾部追加（所以恒错最后一个）；
> F3 是**两个独立机制**叠加（转换顺序倒置 + `%%~n` 表达式对 `find` 值域恒为空）。
>
> **推荐方案（`rec`）已在 155 文件上实测**：三缺陷端到端全部转正，
> 漂移 **6/155（逐行复核均为改善）**、`todo_count` **0 变化**、examples **零漂移**、
> **A1 覆盖 7 文件 snap 行 7/7 未变**、053 覆盖 5 文件仅 1 个可解释地变了 2 行。
> **不需要触碰 `_expand_vars`（A1 热路径）。**
>
> 同时披露：诊断中新发现 **F5**（`\` 后接变量的非重定向形态，13 文件 / 45 处，与 F3-a 同机制），
> 本 session **不修**，留待独立立项。
>
> **现暂停，等 §9 的 G1–G4 裁定。**

---

## 12. 硬闸门裁定（用户已确认，2026-09-27）

| # | 裁定 | 影响 |
| :-: | :--- | :--- |
| **G1** | ✅ **接受** `find` 产出绝对路径（`%%i` 相对→绝对，4 条测试断言重写） | F3-b 定案 |
| **G2** | ⚠️ **一并修 F5**（走 A1 防护流程） | **范围扩大**：F5 从「只披露」变为「本 session 实现」 |
| **G3** | ✅ 按 v2.4.0 四道防护流程（D1–D4 + §3.3/§3.4 观察名单）执行 | 每 commit 跑全量检测 |
| **G4** | ✅ **v2.11.0**（minor） | `%%i` 值形态变化按 minor 披露 |

### 12.1 G2 触发的设计修订（**Phase 2 前置，已实测**）

F5 的初版候选写在 `_expand_vars` 顶部（通用预转换），实测漂移 **17/155**。
但更优的落点是 **`utils.convert_backslashes`**：让它认识「展开插入的替换」。

**为什么更好**：`convert_backslashes` 只在转换器**已经判定为路径**的调用点被调用，
因此天然避开 `# TODO[REG]` 里那些**注册表**键路径（`HKLM\SOFTWARE\…\%input%`）——
预转换写法会把它们改成 `/`，在同一串里与未转换的 `\SOFTWARE` 混排。

**实测（`/tmp` 副本，仓库零改动）**：

| 变体 | 漂移 | todo 变化 | examples | 端到端 |
| :--- | ---: | ---: | ---: | :--- |
| `gen2` = F1+F2+F3b+**F5(convert_backslashes)** | **16/155** | 0 | 0 | F1 F2 F3 F3r F5 ✅ |
| `gen3` = gen2 + **`\\?\` 前缀排除** | 15/155 | 0 | 0 | 同上 |
| **`gen4` = gen3 + A1 占位符识别（定案）** | **15/155** | **0** | **0** | 全部 ✅ |

### 12.2 定案设计（4 个 commit）

| 序 | Commit | 锚点 | 说明 |
| :-: | :--- | :--- | :--- |
| 1 | `fix(F1)` | `batch.py cmd_type` | 补 `convert_backslashes` |
| 2 | `fix(F2)` | `batch.py _convert_for` `/d` 分支 | 逐元素判通配符 |
| 3 | `fix(F5)` | `utils.py convert_backslashes` + `_is_substitution` | **F3-a 的全量面**；F3 的**使能**修复 |
| 4 | `fix(F3)` | `batch.py _emit_for_r` | `cd <root> && find "$PWD"` |

> **顺序偏离披露（纪律 4）**：任务书列的顺序是 F1→F2→**F3**→F5。
> 实测表明 **F5 是 F3 的使能修复**（F3 的 `%%~ni` 与 `\` 分隔符必须同时修好才不产出错文件名），
> 且 F5 的通用写法**完全覆盖** F3-a 的窄修。
> 若按原序先做 F3（含 F3-a 窄修），commit 4 就必须**回退** F3-a 的代码（两种写法在 `\\%VAR%`
> 上行为不一致）⇒ 制造无谓 churn。故改为**依赖序** F1→F2→F5→F3。

### 12.3 F5 的两条边界（实测得出，非推测）

| 边界 | 处置 | 证据 |
| :--- | :--- | :--- |
| **`\\` 连写** | **不转换** | 连写是 UNC/字面反斜杠，交给原有规则整体保留，与现有行为一致 |
| **`\\?\` / `\\.\` 前缀** | **不转换** | `全删.bat`：`DEL /F /A /Q \\?\%1`。若转换，`_convert_path_token` 的通配符回退会产出**未加引号的 `rm -rf \/?/${1:-}`**（`?` 成为活通配符，可能误删根下单字符目录）。Windows 扩展长度前缀 Linux 无对应物，属「不做映射」（同盘符/UNC）；**维持既有行为**，把底层脆弱性登记为 **F6**（§8.2 同级的下一 session 候选） |
| **A1 块内冻结占位符** | **转换** | `提取IE缓存的指定文件.bat`：`convert_backslashes` 在 `_a1_resolve` **之前**运行，`\<A1 marker>` 同样变成字面反斜杠。识别后可修好 4 行 |

### 12.4 定案变体的合规证据（M6）

| 判据 | 结果 |
| :--- | :--- |
| §3.4 A1 覆盖 7 文件 —— 快照**赋值**行 | ✅ **7/7 完全一致**（38/11/3/3/0/1/0 行） |
| 全量 155 文件 `todo_count` | ✅ **0 变化** |
| examples | ✅ **0 字节漂移** |
| `bash -n` 语法通过数 | ✅ base 2 失败 → 定案仍 2 失败，**无新增** |
| 端到端（F1/F2/F2b/F3/F3r/F5a/F5b/F5c） | ✅ **8/8** |
