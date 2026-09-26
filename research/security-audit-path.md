# 安全审查 —— 路径处理（引号 / 通配符 / 变量）

审查对象：`/home/duanjb666/bat2sh`（git HEAD `70a0ddb`，v2.11.0 之后 main tip）
审查日期：本轮 session
结论速览：**3 项高危（同根因族：源文本里的字面 `$()`/反引号变活命令替换 = 命令注入，落到至少 6 个独立触发面）、3 项中危（活通配符误删、字面 `$` 变活变量展开、`%*` 裸展开）、若干低危**。
本类别已知的 `\\?\` 样板（L4/F6）在**当前 HEAD 上已不再产出活通配符**（v2.11.0 的规避是有效的，见 §3.9），但**底层脆弱性（F6）在其它触发面上依然活着**（见 §3.2）。

---

## 1. 审查范围与方法

### 1.1 代码锚点（函数名 + 行号）

| 函数 | 文件:行 | 作用 |
| --- | --- | --- |
| `convert_backslashes` | `python/bat2sh/core/utils.py:176` | 反斜杠→正斜杠；**同时维护引号状态**（`quote = c`，`utils.py:210-214`） |
| `_is_substitution` | `python/bat2sh/core/utils.py:148` | 判定 `\` 后面是不是变量展开插入的替换；显式排除 `\\`、`\\?\`、`\\.\` |
| `needs_nullglob` | `python/bat2sh/core/utils.py:370` | 「引号外有 `*`/`?`」判定（**不看 `[`、`{`、`$`、`` ` ``**） |
| `strip_outer_quotes` | `python/bat2sh/core/utils.py:18` | 剥离最外层成对引号，返回 `(inner, quote)` |
| `tokenize_args` | `python/bat2sh/core/utils.py:104` | 参数切分（**保留引号**） |
| `_expand_vars` | `python/bat2sh/core/batch.py:1030` | `%VAR%`/`%1`/`%%i`/`%~dp0` → `${...}`/`$(...)`；`batch.py:1094` 是 `%*` → `$*` |
| `_dq_preserving_substitutions` | `python/bat2sh/core/batch.py:2183` | 把路径 token 包成 `"..."`；**转义 `\` `"` `` ` ``，但故意原样保留 `$(...)`**（`batch.py:2188-2208`） |
| `_convert_path_token` | `python/bat2sh/core/batch.py:2217` | 路径 token 主入口：`convert_backslashes(_expand_vars(...))` → 通配符回退 / `_dq_preserving_substitutions` |
| `_is_safe_glob_pattern` | `python/bat2sh/core/batch.py:2151` | glob 白名单（排除 `-` 开头、`$(`、`` ` ``、换行） |
| `_convert_for_set` / `_fix_glob_token` / `_note_glob` | `python/bat2sh/core/batch.py:2722` / `:2776` / `:2764` | for 集合：token 化 + glob 修正 + `shopt -s nullglob` 登记 |
| `shopt -s nullglob` 落盘 | `python/bat2sh/core/batch.py:1013-1015` | 脚本头**全局**开关 |
| `cmd_type` | `python/bat2sh/core/batch.py:3371`（返回行 `:3384`） | `type` → `cat` + `convert_backslashes(args)`，**绕过 `_convert_path_token`** |
| `cmd_set` | `python/bat2sh/core/batch.py:3899`（赋值返回行 `:3949-3951`） | `set "P=..."` 值路径用 `_dq_preserving_substitutions` |
| `BATCH_SIMPLE_MAP` 通用分支 | `python/bat2sh/core/batch.py:3052-3054` | `md`/`mkdir`/`ren`/`tree`/`mklink` 等**不做逐 token 引号** |
| `_parse_condition`（`if exist`） | `python/bat2sh/core/batch.py:1974-1996` | `[ -e dq(target) ]` / `compgen -G` |
| `bash -n` 后置校验 + 降级 | `python/bat2sh/core/syntax.py:20/63`，调用点 `batch.py:581-585` | 语法失败整体降级为注释 |

### 1.2 方法

- 全部用**仓库源码**：`cd /home/duanjb666/bat2sh && PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/audit-path/out/<case>.sh /tmp/audit-path/cases/<case>.bat`（**没有**用 `/usr/bin/bat2sh`）。脚本：`/tmp/audit-path/run.sh`、`/tmp/audit-path/drive.py`。
- 100+ 个用例，语料生成器 `/tmp/audit-path/gen_cases.py`（74 例）+ 逐个补充的用例（`i*`/`t*`/`g*`/`h*`/`w1x`）。
- 每条产物都跑 `bash -n`。
- 语义验证：在**干净沙箱**里造真实目录/文件，`bash <产物>` 真执行，比对执行前后文件清单（`/tmp/audit-path/runtime.py`，`RUN`/`>>> CREATED`/`>>> REMOVED` 即真实副作用）。
- **只读**：本 subagent 未改仓库任何代码/测试，未 commit。唯一写入的仓库文件是本报告 `research/security-audit-path.md`。
  （注：本轮 `git status` 另见 `research/behavior-tracking/f-n-diagnosis.md` 与 `python/bat2sh/core/batch.py` 被修改、`research/security-audit-misc.md` 新增——那是**同批并行的另一个 subagent** 的工作，与本审查无关。）
- **口径声明**：本轮全部实验在**转换器工作树与 HEAD `70a0ddb` 内容一致**的时段内跑完；实验只读转换器代码、不依赖工作树后续改动。若并行 subagent 之后改了 `batch.py`（本轮末尾观察到 `_modifier` 的 2 行改动），**结论需按新版本重跑**——本报告的每个代码锚点均以 HEAD `70a0ddb` 为准。

### 1.3 实验目录

| 路径 | 内容 |
| --- | --- |
| `/tmp/audit-path/cases/` | 输入 `.bat` |
| `/tmp/audit-path/out/` | 产物 `.sh` + `.err` |
| `/tmp/audit-path/sandbox/`、`/tmp/globtest/sandbox/`、`/tmp/globtest/sb{,2,3}/` | 真执行沙箱（`/tmp/globtest/*` 用于 §3.2/§3.9 的复现，因为 `/tmp/audit-path/sandbox` 的工作目录内容会被前序实验反复清空） |
| `/tmp/audit-path/{run.sh,drive.py,runtime.py,gen_cases.py}` | 驱动脚本 |

---

## 2. 逐用例表

「产物」列只摘**可执行行**（去掉注释/`set -euo pipefail`）。「实测后果」列为真执行观测。

| # | 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- | --- |
| 1 | DEL | `DEL /F /Q "$(touch /tmp/audit-path/sandbox/PWNED)"` | `rm -f "$(touch …/PWNED)"` | **字面 `$()` 变活命令替换**（实测创建 `PWNED`） | **高** |
| 2 | DEL | `DEL /F /Q $(touch …/PWNED3)` | `rm -f "$(touch …/PWNED3)"` | 同上（无引号输入也活） | **高** |
| 3 | TYPE | ``TYPE `touch …/PWN_TB`.txt`` | ``cat `touch …/PWN_TB`.txt`` | **反引号变活命令替换**（实测创建 `PWN_TB`） | **高** |
| 4 | TYPE | `TYPE %TEMP%\*$(touch …/PWN_TYPE).log` | `cat ${TMPDIR:-/tmp}/*$(touch …/PWN_TYPE).log` | `cmd_type` 绕过引号包装 ⇒ 活 `$()` + 活 glob | **高** |
| 5 | MD | `md "C:\x$(touch …/PWN_MD)"` | `mkdir -p "C:/x$(touch …/PWN_MD)"` | `BATCH_SIMPLE_MAP` 分支不转义 ⇒ 活 `$()`（实测创建 `PWN_MD`） | **高** |
| 6 | SET | `set "P=C:\dir\$(touch …/PWN_SET)"` | `P="C:/dir/$(touch …/PWN_SET)"` | `_dq_preserving_substitutions` 保留 `$()`（实测创建 `PWN_SET`） | **高** |
| 7 | IF | `if exist "$(touch …/PWN_IF)" echo found` | `if [ -e "$(touch …/PWN_IF)" ]; then` | 条件里的活 `$()`（实测创建 `PWN_IF`） | **高** |
| 8 | DEL | `DEL /F /Q C:\dir?\file.txt` | `rm -f C:/dir?/file.txt` | 通配符回退**放弃引号**；`?` 在**目录成分**是活 glob ⇒ 跨目录误删 | **中** |
| 9 | DEL | `DEL /F /Q C:\dir*\file.txt` | `rm -f C:/dir*/file.txt` | 同上（实测删掉 `C:/dirA/file.txt` + `C:/dirB/file.txt`） | **中** |
| 10 | MD | `for %%i in (a b) do md %%i` | `for i in a b; do mkdir -p ${i}; done` | 循环变量在 `md` 里**未加引号**（裸 `${i}`） | **中** |
| 11 | MD | `for %%i in (a b) do md %%i$.txt` | `mkdir -p ${j}$.txt` | 字面 `$` 变**活变量展开** | **中** |
| 12 | DEL | `DEL /F /Q %*` | `rm -f $*` | 裸 `$*`：词分割 + glob（实测传 `*` 时删掉沙箱内 `aa.txt`/`bb.log`） | **中** |
| 13 | DEL | `DEL /F /A /Q \\?\%1`（+ `--no-bash-check`） | `rm -f "\"/?\${1:-}` | 通配符回退产**未闭合引号** ⇒ 非法 bash（默认 `bash -n` 校验会整体降级，故默认不致命） | **低** |
| 14 | DEL | `DEL /F /Q C:\tmp\*.log` | `rm -f "C:/tmp"/*.log` | `*` 是活 glob（引号被移出目录成分） | **低** |
| 15 | DEL | `DEL /F /Q "C:\data\?file.txt"` | `rm -f "C:/data"/?file.txt` | 源里的引号丢失；`?` 变活 glob | **低** |
| 16 | FOR | `for %%i in (*.txt) do echo %%i` + 后续 `mv *.log C:\dst\` | `shopt -s nullglob`（全局）… `mv *.log "C:/dst/"` | 全局 nullglob ⇒ 空匹配时参数静默消失 | **低** |
| 17 | DEL | `DEL /F /Q C:\tmp\[abc].txt` | `rm -f "C:/tmp\[abc].txt"` | 引号内多一个字面 `\`（文件名多字符）；`[abc]` 未变活 glob | **低** |
| 18 | DEL | `DEL /F /Q C:\tmp\{a,b}.txt` | `rm -f "C:/tmp\{a,b}.txt"` | 同上；`{a,b}` 未变活 brace 展开 | **低** |
| 19 | DEL | `DEL /F /Q "C:\it's.txt"`（不成对单引号） | `rm -f "C:/it's.txt"` | 内容一致；单引号在 `"..."` 内安全 | **无** |
| 20 | DEL | `DEL /F /Q "C:\dir\file.txt`（未闭合 `"`） | `rm -f "\"C:/dir/file.txt"` | 引号被转义 ⇒ 合法 bash，语义=字面文件名 | **无** |
| 21 | DEL | `DEL /F /Q "C:\a b" "C:\c d"` | `rm -f "C:/a b" "C:/c d"` | 含空格路径引号保留，无词分割 | **无** |
| 22 | DEL | `DEL /F /Q C:\dir\`（尾随 `\`） | `rm -f "C:/dir/"` | 尾随反斜杠正确转 `/`，引号完整 | **无** |
| 23 | DEL | `DEL /F /Q "C:\dir\$HOME.txt"` | `rm -f "C:/dir\$HOME.txt"` | 字面 `$HOME` **被转义**，未变活变量 | **无** |
| 24 | DEL | ``DEL /F /Q "C:\dir\`id`.txt"`` | ``rm -f "C:/dir\`id\`.txt"`` | 反引号**被转义**（引用路径里安全） | **无** |
| 25 | DEL | `DEL /F /Q "; rm -rf /tmp/.../evil; echo pwned"` | `rm -f "; rm -rf …; echo pwned"` | `;` 被引号封住，实测无副作用 | **无** |
| 26 | DEL | `DEL /F /Q C:\dir\` + `` `touch …` ``（无引号反引号） | `rm -f "\`touch" "…/PWNED4\`"` | token 化把反引号内容拆开并转义，实测未执行 | **无** |
| 27 | DEL | `DEL /F /Q ~\file.txt` | `rm -f "~/file.txt"` | `~` 被引号封住（**注意：这是与 Windows 语义不同的"不做映射"**，但不是注入） | **无** |
| 28 | CD | `cd C:\a b`（引号内/外空格） | `cd "C:/a b"` | 引号保留 | **无** |
| 29 | COPY/MOVE/XCOPY/ROBOCOPY | `copy "C:\a b\x" "C:\c d\"` 等 | `cp "C:/a b/x" "C:/c d/"` | 走 `_convert_path_token`，引号保留；`$()` 亦会活（同 #1，未单列） | 中（同根因） |
| 30 | DIR | `dir /b *.txt` | `compgen -G "*.txt" \|\| true` | 走 `dq(pattern)`，引号完整；**但 `$()` 仍活** | 中（同 #1） |

`w01`（`\\?\` 样板）、`p03`（`\\?\C:\dir\file.txt`）、`w10`/`w11`（`\\?\C:\dir\*.*`）、`w12`（`\\?\C:\dir\`）、`w09`（UNC）等见 §3.9。

---

## 3. 详细分析

### 3.1 【高】活命令替换 `$(...)`：`_dq_preserving_substitutions` 的"故意保留"

**现象**。路径里字面写着的 `$(` 在产物里**不加反斜杠**，于是 bash 在运行时真的执行它。

**最小复现**（§2 用例 1）

```
输入  DEL /F /Q "$(touch /tmp/audit-path/sandbox/PWNED)"
产物  rm -f "$(touch /tmp/audit-path/sandbox/PWNED)"
实测  bash 产物 ⇒ 沙箱内出现新文件 PWNED（rc=0）
```

同型变体（全部实测执行成功）：

| 变体 | 产物片段 | 实测 |
| --- | --- | --- |
| `DEL /F /Q $(…)`（源无引号） | `rm -f "$(…)"` | 创建 `PWNED3` |
| `DEL /F /Q "$(touch …Q)$(touch …Q2)"` | `rm -f "$(…) $(…)"` | 创建 `PWN_Q`、`PWN_Q2` |
| `if exist "$(…)" echo found` | `if [ -e "$(…)" ]; then` | 创建 `PWN_IF` |
| `set "P=C:\dir\$(…)"` | `P="C:/dir/$(…)"` | 创建 `PWN_SET` |
| `dir /b "$(…)"` | `ls -1 "$(…)"` | 创建 `PWN_DIR` |

**根因 + 代码锚点**。`_dq_preserving_substitutions`（`batch.py:2183`，保留逻辑在 `2188-2208`）的设计意图是"**变量展开插入的** `$(...)` 要保留"（`%~f1` → `$(readlink -f "${1:-}")` 确实必须保留）。但函数签名只有 `text: str`，**无法区分**"来自 `%VAR%` 展开的 `$()`"和"源文件里字面写着的 `$()`"；它把两者一视同仁地放进双引号内不转义。前一层 `convert_backslashes` 也不负责转义 `$`。

- 调用点：`_convert_path_token`（`batch.py:2227`）、`_convert_operand`（`batch.py:2162` 经 `dq`）、`cmd_set`（`batch.py:3951`）、`batch.py:3154`。
- "源里字面 `$` 应当转义"在这条路径之外是**有意识**的：`cmd_echo` 用 `_DOLLAR_PLACEHOLDER` → `\$`（`batch.py:3357-3368`），`_expand_vars` 对 `%VAR%` 中间插入的 `$` 也保持字面。**唯独 `_dq_preserving_substitutions` 这条路径漏了这一步。**

**实测后果**：任意命令执行，以运行转换后脚本的权限。攻击面 = 攻击者能影响被转换的 `.bat` 文本（下载来的脚本、`%~dp0` 派生的路径拼接、`for /f` 读入的文件名被回写进路径等）或能影响被引用的变量值（见 §3.3）。至少 6 个独立触发面（DEL/DIR 走 `_convert_path_token`；TYPE/MD 绕过它；SET/IF 各自拼引号）说明这不是单点疏忽，而是**转义责任散落**（见 §4.1 的 R1–R3）。

### 3.2 【高】`type` 绕过 `_convert_path_token`：反引号 + `$()` 全裸

**现象**。`cmd_type`（`batch.py:3371`）的实现是

```python
return ("cat " + convert_backslashes(args)).strip()   # batch.py:3384
```

它既**不调 `_convert_path_token`**（注释里明说是为了"多参数不能单 token 处理"），也不做任何 `$`/反引号转义。

**最小复现**（§2 用例 3）

```
输入  TYPE `touch /tmp/audit-path/sandbox/PWN_TB`.txt
产物  cat `touch /tmp/audit-path/sandbox/PWN_TB`.txt
实测  bash 产物 ⇒ 创建 PWN_TB；rc=1（cat .txt 不存在），命令替换已执行
```

`$()` 版本（§2 用例 4）同样活：`TYPE %TEMP%\*$(touch …).log` → `cat ${TMPDIR:-/tmp}/*$(touch …).log`，实测创建 `PWN_TYPE`。这里还叠加了**裸 `${TMPDIR:-/tmp}` 未加引号**（词分割 + glob）。

**根因**：`BATCH_HANDLER_MAP` 让 `type` 走 handler（`rules.py:47`），handler 自己拼命令，于是绕开了 `_convert_simple_no_pipe` 里 `BATCH_SIMPLE_MAP` 分支（`batch.py:3052-3054`）之外**唯一**做引号处理的那条路径。同类风险：`cmd_echo`（`batch.py:3357`，实测**安全**，见 §2 #23/#24——它显式转义了 `$` 和反引号）证明"这条路径本该转义"，`type` 是漏网。

### 3.3 【高】`set "VAR=..."` 值里的 `$()` 变活

**最小复现**（§2 用例 6）

```
输入  set "P=C:\dir\$(touch /tmp/audit-path/sandbox/PWN_SET)"
产物  P="C:/dir/$(touch /tmp/audit-path/sandbox/PWN_SET)"
实测  bash 产物 ⇒ 创建 PWN_SET
```

**根因**：`cmd_set` 赋值分支（`batch.py:3949-3951`）

```python
value = convert_backslashes(self._expand_vars(value, lineno))
if self.settings.quote_variables or value == "" or re.search(r"[\s$&|()<>]", value):
    return f"{name}={self._dq_preserving_substitutions(value)}"
```

`re.search(r"[\s$&|()<>]", value)` **命中 `$`**（这正是它决定加引号的理由），但加引号用的是会保留 `$()` 的那个函数 ⇒ "因为含 `$` 所以加引号"却"加引号又不转义 `$`"，自相矛盾。

**注意**：变量**值**里的 `$()` 是安全的（`set "P=$(id)"` → `P="$(id)"` 是字面，实测无副作用）；危险的是 **`.bat` 源文本里字面**的 `$()`。

### 3.4 【中】`_convert_path_token` 通配符回退：目录成分的 `*`/`?` 是活 glob（F6 的另一触发面）

**现象**（§2 用例 8/9）。`_convert_path_token`（`batch.py:2217-2227`）：

```python
probe = re.sub(r"\$\{[^}]*\}|\$\([^)]*\)", "", converted)
if "*" in probe or "?" in probe:
    head, sep, tail = converted.rpartition("/")
    head_probe = re.sub(...)             # head 里也有通配符
    if sep and "*" not in head_probe and "?" not in head_probe:
        return f'"{head}"/{tail}'        # head 无通配符 ⇒ 只给 head 加引号
    return converted                     # ★ head 有通配符 ⇒ 整个 token 裸奔
```

`return converted` 这一支**完全不加引号**。

**最小复现**

```
输入  DEL /F /Q C:\dir*\file.txt
产物  rm -f C:/dir*/file.txt
沙箱  C:/dirA/file.txt、C:/dirB/file.txt、C:/keep/file.txt
实测  bash 产物 ⇒ C:/dirA/file.txt 与 C:/dirB/file.txt 被删；C:/keep/file.txt 存活
      （/tmp/globtest/sandbox，BEFORE/AFTER 文件清单已比对）
```

`?` 版本（`C:/dir?/file.txt`）同理；`w02`（`"C:\data\?file.txt"`）是同一支的温和形态：`rm -f "C:/data"/?file.txt` —— **源里显式加的引号丢失了**，`?` 变活 glob。注意 `?` 与 `*` 的危害差：`w13` 的 `rm -f "C:"/*.log`（`C:\*.log`）里 `?`/`*` 只作用于**末段文件名**，匹配范围限于同名目录内；而 §3.4 的 `C:/dir*/file.txt` 把通配符放在**目录成分**，匹配范围跨越整层目录。

**根因**：这是 L4/F6 登记的**同一底层脆弱性**——"路径 token 回退时把字面量当活 glob"。v2.11.0 只在 `convert_backslashes`/`_is_substitution` 里**排除了 `\\?\` 前缀**（`utils.py:169-170`），也就是说 F6 的**唯一**缓解手段是"让 `\?` 保持转义状态"。任何**不经过 `\\?\`** 的通配符都会走到这个裸分支。

**同时暴露的第二个缺陷**：通配符分支**不做 `\`/`"`/`` ` `` 转义**（只有非通配符分支才调 `_dq_preserving_substitutions`），于是 §3.6 的非法 bash 也出在这里。以及 `needs_nullglob`（`utils.py:370`）只看 `*`/`?`，**不看 `[`/`{`** ⇒ `[abc]`、`{a,b}` 永远进不了这条分支（本轮实测它们保持字面，见 §3.7），判定口径与 bash 的实际元字符集合不一致。

### 3.5 【中】`BATCH_SIMPLE_MAP` 通用分支：`md`/`mkdir`/`ren` 路径不逐 token 引号

**现象**（§2 用例 5/10/11）。`batch.py:3052-3054`：

```python
elif first in rules.BATCH_SIMPLE_MAP:
    mapped = rules.BATCH_SIMPLE_MAP[first]
    line = (mapped + " " + convert_backslashes(rest)).strip()
```

只做反斜杠转换，**没有任何 token 级引号/转义**。`md`/`mkdir`/`ren`/`rename`/`tree`/`mklink`/`fc`/`comp`/`where` 全在这张表里（`rules.py:18-42`）。

**最小复现 A（活 `$()`）**

```
输入  md "C:\x$(touch /tmp/audit-path/sandbox/PWN_MD)"
产物  mkdir -p "C:/x$(touch /tmp/audit-path/sandbox/PWN_MD)"
实测  创建 PWN_MD
```

**最小复现 B（活 `$` 变量展开）**

```
输入  for %%i in (a b) do md %%i$.txt
产物  for j in x; do mkdir -p ${j}$.txt; done
      ⇒ bash 先展开 ${j}，实际尝试创建目录 "x$.txt"（Windows 下字面 mkdir x$.txt，目录名里含 $）
实测  rc=0、沙箱内无新目录（`$` 被当变量字符吃掉）
```

**根因**：这条分支把"命令名映射"和"路径转换"混在一处，路径转换退化成了 `convert_backslashes`。`for` 循环变量在**其它**命令里会被 `_convert_path_token` 包成 `"${i}"`（如 `rm -f "${i}"` 见 `v09_for_var`），所以同一份 `%%i` 在不同命令下拿到的安全性不同——即"**同一个路径 token 走到哪条命令分支，决定了它是否被转义**"。

### 3.6 【中/低】`%*` 裸展开 `rm -f $*`；以及通配符回退的非法引号

**(a) `%*` → `$*`（`batch.py:1094`）**。`text.replace("%*", "$*")` 只做替换，**没有外层引号**。

```
输入  DEL /F /Q %*
产物  rm -f $*
沙箱  aa.txt、bb.log
实测  bash 产物.sh '*'                       ⇒ REMOVED: aa.txt, bb.log（真删）
      bash 产物.sh '; touch …/PWN_STAR;'     ⇒ 无副作用（`$*` 展开出的词里 `;` 不是控制操作符，
                                                因为词分割发生在语法解析之后）
```

即：**调用者的参数直接被当 glob 展开**。危害等级中（需要调用者传 `*` 之类的实参），但这是"字面量变活通配符"的又一独立触发面。参照组：`%1` 走 `_convert_path_token` 得到 `"${1:-}"`（带引号，实测同参数下无副作用）——**同一个脚本里 `%1` 安全、`%*` 不安全**。

**(b) 通配符回退产出未闭合引号**（`batch.py:2225` 的 `f'"{head}"/{tail}'` 不转义 `head` 里的 `"`）：

```
输入  DEL /F /A /Q \\?\%1
--no-bash-check 产物  rm -f "\"/?\${1:-}
实测  bash -n 产物 ⇒ rc=2「寻找匹配的 `"' 时遇到了未预期的 EOF」
```

**默认 CLI 会兜住**：`syntax.py:20` 的 `bash_syntax_error` + `degraded_script`（`syntax.py:63`）把整个脚本降级为注释，所以默认路径看到的是"没转换"而不是"坏 bash"。**但凡用 `--no-bash-check`（`settings.bash_check=False`）就不再有这层保护**，得到的是一个既语法非法、又含 `/?/` 通配符的脚本。

### 3.7 【低】`[`、`{`、`\` 的转义口径（与 §3.4 同源，方向相反）

`convert_backslashes` 的 `path_next` / `isalnum` 判定把 `\[`、`\{`、`\'` 的**反斜杠原样保留**（`utils.py:219`、`:199`）：

```
DEL /F /Q C:\tmp\[abc].txt      → rm -f "C:/tmp\[abc].txt"
DEL /F /Q "C:\tmp\[!abc].txt"   → rm -f "C:/tmp\[!abc].txt"
DEL /F /Q C:\tmp\{a,b}.txt      → rm -f "C:/tmp\{a,b}.txt"
```

后果是**文件名多一个反斜杠字符**（Windows 的 `C:\tmp\[abc].txt` ≠ Linux 的 `C:/tmp/\[abc].txt`），不是安全漏洞（`[abc]`、`{a,b}` 在 `"..."` 内保持字面）。但它说明：**`[`/`{` 之所以没变成活 glob，只是因为"路径分隔符转换失败顺带产生了转义"**——是巧合，不是设计。同源的另一面：`for %%i in (...)` 走的是**另一个函数** `_fix_glob_token`（`batch.py:2776`，只认 `*`/`?`），那里 `[ab].txt` **没有**任何转义，实测在 bash 里真的被当字符类展开（`g05`）：

```
输入  for %%i in ([ab].txt) do echo %%i
产物  for i in [ab].txt; do    ← 无引号、无转义
沙箱  a.txt、b.txt
实测  stdout = "a.txt\nb.txt\n" ⇒ 循环体执行两次、每次都拿到一个真实文件名
      （cmd 的集合语义是「逗号/空白分隔的元素列表」，`[ab].txt` 是**一个**字面元素）
```

同族 `g04`（`for %%i in ({a,b}.txt)`）方向相反：`_convert_for_set`（`batch.py:2725`）先把 `,` 换成空格 ⇒ 产物 `for i in {a b}.txt`，实测 stdout `"{a\nb}.txt\n"`（两次迭代、元素被 `,` 切开且丢失 `{`/`}` 配对），**不是** bash 的 brace 展开（因为没有逗号了）。两条合起来说明：`for` 集合既可能被 bash 元字符**多匹配**，也可能被 `,`→空格规则**切错**，`_fix_glob_token` 的元字符集合（只有 `*`/`?`）覆盖不全。

### 3.8 【低】`shopt -s nullglob` 是**全局**开关

`_note_glob`（`batch.py:2764`）只在**首次**发现通配符集合时置位，产物把 `shopt -s nullglob` 放在**脚本头**（`batch.py:1013-1015`），影响**其后所有命令**。

```
输入  for %%i in (*.txt) do echo %%i
      move *.log "C:\dst\"
产物  shopt -s nullglob          ← 全局
      for i in *.txt; do … done
      mv *.log "C:/dst/"
沙箱  keep.log（无 *.txt）
实测  rc=1，"mv: 无法将 'keep.log' 移动至 'C:/dst/'：没有那个文件或目录"
```

具体后果是"**空匹配时参数静默消失 / 参数变成未展开的字面模式**"（这里 `mv` 拿到了字面 `*.log`，落成"目标目录不存在"的错误），**没有**观测到"`rm -rf` 裸奔"（`rm -f` 无参数是安全的；`mv`/`cp`/`ln`/`command -v` 反而更容易出问题）。等级低，但**风险面是全局的**——脚本里任何位置的通配符都受影响，且 nullglob 一旦开启**不会在循环后关闭**。

### 3.9 【无】v2.11.0 的 `\\?\` 样板（L4/F6）在当前 HEAD 上的实测状态

| 输入 | 产物 | 实测/判定 |
| --- | --- | --- |
| `DEL /F /A /Q \\?\%1` | **整体降级为注释**（`bash -n` 发现未闭合引号） | 默认无活代码；`--no-bash-check` 下见 §3.6(b) |
| `echo hi \\?\%1` | `echo "hi \\/?\${1:-}"` | **安全**：bash 里 `\?` = 字面 `?`；实测 `printf '%s' '/\?/x' \| od` 确认为字面 `?`，`for f in /\?/…` 不匹配任何目录 |
| `DEL /F /Q "\\?\C:\dir\*.*"` | `rm -f \/?/C:/dir/*.*` | **本轮实测未误删**（`/tmp/globtest/sb`，沙箱内含 `x/C:/dir/file.txt`、`x/C:/dir/other.log`，执行后两者均在）：`\/?` 的 `\` 逃逸了 `?`，整个模式按字面路径处理 |
| `\\?\C:\dir\file.txt` | `rm -f \/?/C:/dir/file.txt` | 同上，`?` 被逃逸 |
| UNC `\\server\share\*.*` | `rm -f "\/server/share"/*.*` | glob 仅作用于 `\/server/share/` 之下（该路径几乎不存在）；`*.*` 本身是活 glob，属 §3.4 的温和形态 |

**对照组（证明"活"与"不活"的差别，`/tmp/globtest/sb2`）**

```
沙箱     x/C:/dir/file.txt、x/C:/dir/other.log
A 裸 ?    rm -f ?/C:/dir/*.*     ⇒ rc=0，两文件均被删（活 glob）
B 转义 ?  rm -f \/?/C:/dir/*.*   ⇒ rc=0，两文件均在（字面路径，不匹配）
          （A/B 之间已手工把文件 touch 回来；`echo` 亦确认 A 展开、B 不展开）
```

**结论**：v2.11.0 的规避（`utils.py:169-170`：`\?` / `\.` 前的反斜杠不参与替换判定，从而让 `\?` 保持"反斜杠 + `?`"）在当前 HEAD 上**确实生效**——`?` 被 `\` 逃逸，不再匹配"任意单字符目录"。但 §3.4 证明 **F6 的底层脆弱性仍在**：只要路径里出现**不经 `\\?\` 前缀**的 `*`/`?`（尤其出现在目录成分），`_convert_path_token` 就产出一个未加引号的活 glob。换言之，v2.11.0 修的是**一个触发面**，不是根因。

### 3.10 【无】其它属性（本轮实测确认安全）

- 含空格路径（引号内/`%~dp0`/`%TEMP%`）：引号保留，无词分割。
- 未闭合 `"`：被转义成 `\"`，产物合法。
- 不成对单引号（`C:\it's.txt`）：`"C:/it's.txt"` 合法。
- 字面 `$HOME`（`C:\dir\$HOME.txt`）：转义成 `\$`，**未**变活变量。
- 反引号在**引用路径**（`DEL "… `id` …"`）：转义成 `` \` ``，未执行。
- 无引号反引号会**触发 token 切分**（`rm -f "\`touch" "…PWNED4\`"`），实测未执行 ⇒ 不是注入面。
- `;`、`&`、`(`、`)`、`#`、`>`、`^`、制表符：`;`/`(`/`)`/`#` 被引号封住；`&`/`>` 是**真分隔符**（cmd 与 bash 一致，属正确转换，但 `>` 会真的建文件，见 §2 用例 28 的同族 `s08`）。
- `~`：`rm -f "~/file.txt"` 引号内不展开（**与 Windows 语义不同**——Windows 的 `~\file.txt` 是相对路径字面，这里也落成字面，属"不做映射"）。
- 长路径（40 层）：无截断，引号完整。

---

## 4. 结论与建议

### 4.1 真风险（有可复现的破坏性后果）

| 编号 | 风险 | 等级 | 触发面 |
| --- | --- | --- | --- |
| **R1** | **活命令替换 `$()`**：源文本里的字面 `$()` 被原样保留进 `"..."` ⇒ 命令注入 | **高** | `_dq_preserving_substitutions`（`batch.py:2183`）→ `_convert_path_token`（`:2227`，DEL/COPY/MOVE/DIR… 全走这里）、`cmd_set`（`:3951`）、`if exist`（`:1982`）、`batch.py:3154` |
| **R2** | **活命令替换（反引号/`$()`）**：`type` 绕过 `_convert_path_token`，完全不转义 | **高** | `cmd_type`（`batch.py:3371`，返回 `:3384`） |
| **R3** | **活命令替换**：`BATCH_SIMPLE_MAP` 通用分支（`md`/`mkdir`/`ren`/…）不转义 | **高** | `batch.py:3052-3054` |
| **R4** | **字面量变活通配符**：`_convert_path_token` 通配符回退在"目录成分含 `*`/`?`"时整 token 裸奔 ⇒ 跨目录误删 | **中** | `batch.py:2221-2226` |
| **R5** | **字面 `$` 变活变量展开**（`md %%i$.txt`） | **中** | 同 R3 |
| **R6** | **`%*` → 裸 `$*`**：调用者实参被 glob 展开 ⇒ 误删 | **中** | `batch.py:1094` |

R1/R2/R3 同属一个根因族：**"转义责任散落在各调用点，没有单一的'路径 token 安全引用'出口"**。

### 4.2 理论风险（未测出破坏性后果，但值得记账）

- **R7**：通配符回退不转义 `"` ⇒ `--no-bash-check` 下产出非法 bash（默认被 `bash -n` 降级兜住）。
- **R8**：局部 `[abc]`/`{a,b}` 的"巧合转义"（`utils.py:199/219`），以及 `_fix_glob_token` 完全不处理 `[`/`{` 导致的集合语义漂移（`[ab].txt` → `a.txt b.txt`）。
- **R9**：全局 `shopt -s nullglob`（`batch.py:1013`）对后续命令的参数消失效应。
- **R10**：`~/x` 被引号封住 ⇒ 与 Windows 的 `~\x` 语义分歧（不作映射，属设计取舍，非注入）。

### 4.3 建议（本次不做修复，仅建议）

1. **收敛出口（对 R1/R2/R3）**：让**所有**路径/参数 token 都经过**唯一**一个"安全引用"函数，并且把"引用"与"命令替换保留"**显式分开**：
   - 需要保留 `$(...)` 的调用点（`%~f1`、`%~dp0`、`%CD%`）改为传**结构化信息**（"这个占位符是展开产物"），而不是让函数靠猜字符串；
   - 源里字面出现的 `$`、`` ` ``、`$(`, 一律 `\$`、`` \` ``（对齐 `cmd_echo` 已在做的 `_DOLLAR_PLACEHOLDER` 口径）。
2. **`_convert_path_token` 的通配符回退（对 R4）**：把 `return converted` 那一支也做转义（head/tail 分别引用，`"` → `\"`），并让 `probe` 的判定/转义口径与 bash 元字符集合（`* ? [ ] { } ~ $ \` " '` 与 `!`）一致。若无法保证，宁可按 F6 的既有纪律**降级为诚实 TODO**，不要产出未引用的 token。
3. **把 `%*`（对 R6）与 `%%i` 的展开**统一走 `_convert_path_token`，而不是裸 `${...}`/`$*`。
4. **`nullglob`（对 R9）**：改为**只在需要的 `for`/`compgen` 局部**（子 shell 或 `shopt -s nullglob; …; shopt -u nullglob` 成对）开启。
5. **回归测试建议**：为 R1/R2/R3/R4 各加一条"真执行 + 比对文件清单"的用例（本轮 `runtime.py` 的 BEFORE/AFTER 口径可直接复用），断言**沙箱无新增文件、无文件被删**——只断言产物文本形状不足以拦住这类问题（R4 的产物文本 `rm -f C:/dir*/file.txt` "看起来"就是普通 glob）。

---

## 5. 未覆盖 / 存疑

1. **Powershell 路径（`python/bat2sh/core/powershell.py`）完全未审**。同族函数在那里重复实现（`_note_glob` 在 `powershell.py:1728`、`convert_backslashes` 调用点 `:694/:763/:1304/:1918`），本轮只覆盖 batch 线。
2. **`for /f` / `for /r` 的路径来源**未系统覆盖：`for /f` 读文件后把行内容当路径回写（`_emit_for_f`）、`for /r` 的 `find` 改写，我只有零散观测，没有逐例验证。
3. **`if exist` 的 `compgen -G` 分支**只测了 `dir /b` 的形式，未测 `if exist "*.txt"` 这类（`_is_safe_glob_pattern` 的 `-` 开头/`$(`/`` ` `` 排除在真实产物里的表现）。
4. **`%VAR:~N,M%` 子串/替换展开后落进路径**未测（`${VAR:0:2}` 与 `$()` 的交互没验证）。
5. **`del /s` 与 `rm -rf` 的组合**只在 `w01` 家族里看到降级，没有单独构造"`/s` + 活 glob"的破坏性用例。
6. **`--no-bash-check` 之外的关闭路径**（GUI 复选框、`settings.bash_check=False`）未逐一验证；只在 CLI 上确认了 `--no-bash-check` 的效果。
7. **attacker-controlled `.bat` 的完整利用链未做**：R1–R3 证明了"字面 `$()` 会执行"这一**机制**，但没有构造"变量值/文件内容 → 路径 token"的端到端利用（`%VAR%` 值里的 `$()` 是**不**执行的，见 §3.3 末；只有源文本字面才是）。
8. **`\\.\` 设备前缀**只有一条用例（`p11` → `rm -f "\\/./C:/dir/file.txt"`），判定"无"的依据是引号完整 + 无实测副作用，未穷举。
9. **超长路径**只测了 40 层（约 200 字符），未测 >4096 字符或 `ARG_MAX` 边界。
10. **跨平台差异**：本轮的 `bash` 是 5.3.20 / Linux；`globskipdots`、`globasciiranges` 等 `shopt` 默认值在别的发行版可能不同，§3.8 的 nullglob 结论与具体 bash 版本无关，但 §3.4 的 `?`/`*` 匹配集合可能随 `dotglob`/`globstar` 变化（本轮均为 off）。
