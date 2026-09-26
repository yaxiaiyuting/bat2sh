# 安全审查 —— 其它命令（findstr 管道 / attrib / type / set / 控制流等）

审查对象：`bat2sh` @ `70a0ddb`（v2.11.0 发布后 main tip）
审查性质：**只读审查**，未修改仓库任何代码/测试，未 commit。产物与实验文件全部在 `/tmp/audit-misc/`。

> 备注：审查期间兄弟 agent 追加了纯文档提交 `0535cac`（仅 `research/behavior-tracking/f-n-diagnosis.md` 与 `research/session-subagent-status.md`）。`git diff 70a0ddb..0535cac --stat` 不含 `python/`，即**被审代码逐字节未变**，全部结论对当前 HEAD 同样成立。

---

## 1. 审查范围与方法

### 1.1 代码锚点（函数名 + 行号，均指 `python/bat2sh/core/batch.py`）

| 主题 | 函数 | 行号 |
|---|---|---|
| findstr→grep | `BatchConverter.cmd_findstr` | 3685–3763 |
| findstr 模式展开/中文映射 | `_expand_findstr_terms` / `_expand_findstr_literal` / `_map_findstr_term` | 3793–3853 |
| findstr 文件判定启发式 | `_findstr_looks_like_file` | 3765–3768 |
| 管道两段转换 | `_convert_two_segment_pipeline` | 2791–2807 |
| `\|\| true` 过滤段守卫 | `_convert_simple` | 2809–2838（守卫在 2820–2825、2832–2837） |
| 过滤段判定 | `_is_filter_segment` | 2840–2845 |
| `if errorlevel` 改写 | `_errorlevel_condition` / `_take_previous_command` / `_status_condition` | 2114–2148 / 2060–2073 / 2107–2112 |
| `%*`→`$*` 全局替换 | `_expand_vars` | **1094**（`%NAME%` 正则在同一函数 1230） |
| `set` / `set /p` / `set /a` | `cmd_set` / `_set_arithmetic` / `_guard_unset_arith_vars` | 3899–3952 / 3987–4001 / 3977–3985 |
| `$()` 保留式加引号 | `_dq_preserving_substitutions` | 2183–2215 |
| 路径 token 转换 | `_convert_path_token` | 2217–2227 |
| `type`→`cat` | `cmd_type` | 3371–3384 |
| `echo` | `cmd_echo` | 3357–3369（`$` 占位符保护在 2942–2943，还原在 3369） |
| 重定向渲染 | `_render_redirs` / `_append_redirs` | 3139–3156 / 3118–3128 |
| `attrib`→`chmod` | `cmd_attrib` | 3286–3312 |
| `taskkill` | `cmd_taskkill` | 3644–3666 |
| `net` | `cmd_net` | 3262–3284 |
| `reg` | `_parse_reg_invocation` / `_reg_todo_comment` | 3314–3355 |
| `start` | `cmd_start` | 3511–3588 |
| `call` / `goto` / `exit /b` | `_convert_call` / `_convert_goto` / `_convert_exit` | 1781–1838 / 1741–1779 / 1840–1848 |
| 头部 `set -euo pipefail` | `_compose` | 1007–1025（1011–1012） |
| 语法校验降级网 | `known.bat` 实测：`bash -n` 失败 ⇒ 整脚本降级为注释 + `# TODO` + error | — |

### 1.2 CLI 调用方式（一律使用仓库源码，未用 `/usr/bin/bat2sh`）

```bash
cd /home/duanjb666/bat2sh
PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/audit-misc/out/<name>.sh /tmp/audit-misc/in/<name>.bat
bash -n /tmp/audit-misc/out/<name>.sh
```

实验目录：`/tmp/audit-misc/{in,out,sandbox,sb2,sb3,sb4,...}`。
诊断文本用 `--report-json` 提取（`-q` 只给汇总行，看不到 warning 正文）。

### 1.3 哪些只做了文本审查（未执行）

按纪律 3，以下命令的产物**只做文本审查**，未真跑：`reg`、`net`、`taskkill`、`start`。
对 `taskkill` 的**匹配宽度**用只读的 `pgrep`（同一套匹配引擎）做了实测；对 `type` 的 `\\?\` 通配符用 `bwrap` 命名空间（不影响宿主）做了真执行。

其余用例（`findstr`/`type`/`echo`/`set`/`attrib`/`call` 等）均在 `/tmp/audit-misc/sandbox*/` 里造真实文件、真执行产物、看真实副作用。

---

## 2. 逐用例表

> 产物片段中的 `|` 在表格里转义为 `\|`。

| # | 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
|---|---|---|---|---|---|
| H1 | findstr + errorlevel | `findstr "needle" haystack.txt`<br>`if errorlevel 1 del keep.txt` | `if ! grep "needle" "haystack.txt" \|\| true; then`<br>`    rm -f "keep.txt"`<br>`fi` | `\|\| true` 被拼进 if 条件 ⇒ `! pipeline \|\| true` **恒为真** ⇒ 分支无条件执行，**实测误删 keep.txt** | **高** |
| H2 | set / type / set /a 的 `$()` | `set X=$(touch PWN_SET)`<br>`type $(touch PWN_TYPE).txt`<br>`set /a NUM=$(touch PWN_ARITH)` | `X="$(touch .../PWN_SET)"`<br>`cat $(touch .../PWN_TYPE).txt`<br>`NUM=$(( $(touch .../PWN_ARITH) ))` | `cmd` 里 `$()` 是字面文本，bash 里**真执行** ⇒ 任意命令执行（实测 3 个 marker 文件被创建） | **高** |
| H3 | echo 重定向 | `echo new-content > log?.txt`<br>`echo second > *.dat` | `echo "new-content" >log?.txt`<br>`echo "second" >*.dat` | 重定向目标未加引号 ⇒ 活通配符展开 ⇒ **实测覆盖 log1.txt / report.dat**（原有数据丢失，rc=0，无 TODO/无告警） | **高** |
| H4 | taskkill（文本审查） | `taskkill /IM notepad.exe /F`<br>`taskkill /IM app*.exe`<br>`taskkill /IM .exe`<br>`taskkill /PID -1` / `/PID 0` | `pkill -f "notepad"`<br>`pkill -f "app*"`<br>`pkill -f ""`<br>`kill -1` / `kill 0` | `pkill -f` 是**无锚定正则**匹配**整条命令行**：`app*` 实测命中 `[kswapd0]`/`[oom_reaper]`/`kwin_wayland_wrapper`；`""` 实测匹配 606/609 个进程；`kill -1`/`kill 0` 无整数校验 | **高** |
| M1 | `%VAR%*` | `set /a size=%n%*1024`<br>`echo v=%n%*2` | `size=$(( %n$*1024 ))`<br>`echo "v=%n$*2"` | `%*`→`$*` 抢先替换，吃掉 `%n%` 的收尾 `%`：算术报错 + 变量未赋值 ⇒ `set -u` 读到时**整脚本中止**（实测 `backup.txt` 从未创建）；非 `/a` 场合静默错值。产物**0 警告 0 TODO** | **中** |
| M2 | type + `\\?\` | `type \\?\C:\secret.txt` | `cat \/?/C:/secret.txt` | `\\?\` → `\/?/`，`?` 是**活单字符通配符**：实测在 bwrap 命名空间里读到 `/q/C:/secret.txt`（越界读取）；同族于 v2.11.0 已知 `rm -rf \/?/` | **中** |
| M3 | attrib | `attrib +r *.txt`<br>`attrib /s +r a.txt` | `if [ -e *.txt ]; then chmod -w *.txt; fi`<br>`if [ -e "/s" ]; then chmod -w "/s"; fi`<br>`if [ -e "a.txt" ]; then chmod -w "a.txt"; fi` | 多匹配时 `[ -e a.txt b.txt ]` rc=2 ⇒ 守卫假 ⇒ **静默不执行**；`/s` 被当成目标路径。权限映射本身正常（`-w`/`+w`，无 777、无 `+x`） | **中** |
| M4 | findstr 开关 | `findstr /f:patterns.txt log.txt`<br>`findstr /g:patterns.txt log.txt`<br>`findstr /b "abc" log.txt` | `grep /f:patterns.txt "log.txt"`<br>`grep /g:patterns.txt "log.txt"`<br>`grep "abc" "log.txt" \|\| true` | `/f:` `/g:` 被当成**搜索模式**（真正模式丢失，且**无开关告警**）；`/b` `/e` `/m` `/o` `/p` 被丢弃（仅 report 告警，产物无痕）⇒ 匹配集合静默改变 | **中** |
| M5 | findstr 裸模式 | `findstr a*b log.txt` | `grep a*b "log.txt" \|\| true` | 裸模式分支（3751–3752）不加引号 ⇒ 模式被 **glob 替换成文件名**；实测 `a*b` → `a1b.txt`，搜索对象变成错误字符串 | **中** |
| M6 | type/call 失败 | `type missing.txt`<br>`call missing.bat` | `cat missing.txt`<br>`bash "missing.sh"` | `cat` 失败 rc=1、`bash missing.sh` rc=127，在 `set -e` 下**中止整脚本** ⇒ 后续全部跳过（实测 `AFTER-TYPE`/第二次 `type` 未执行） | **中** |
| M7 | echo/set 反斜杠 | `echo C:\path\to\file`<br>`set Y=a\b\c` | `echo "C:/path/to/file"`<br>`Y="a/b/c"` | 反斜杠被静默改成 `/` ⇒ 回显文本/变量值被篡改，**无相关告警** | **中** |
| M8 | net user（文本审查） | `net user daemon /delete`<br>`net user root /delete` | `if id -u daemon >/dev/null 2>&1; then userdel daemon; fi`<br>`if id -u root >/dev/null 2>&1; then userdel root; fi` | Windows 账户名直通 Linux 账户库：实测 `id -u` 对 `root`=0 / `bin`=1 / `daemon`=2 / `mail`=8 / `nobody`=65534 全部通过守卫 ⇒ 会真删系统账号 | **中** |
| M9 | start（文本审查） | `start "foo;touch PWNED_SEMI"`<br>`start "my app"` | `nohup foo;touch PWNED_SEMI >/dev/null 2>&1 &`<br>`nohup my app >/dev/null 2>&1 &` | 目标**原样拼接**、引号被剥掉 ⇒ `;`/`&` 成为命令分隔符（注入）；空格目标词分割 | **中** |
| L1 | taskkill 兜底 | `taskkill /F` | `pkill` | 裸 `pkill` 实测只打印用法错误、不杀任何进程，但 **rc=2** ⇒ `set -e` 下中止脚本 | **低** |
| L2 | call 未定义标签 | `call :undefined_label` | `if declare -F label_undefined_label >/dev/null 2>&1; then label_undefined_label; fi` | 静默 no-op（cmd 会报"找不到标签"）⇒ 掩盖拼写错误 | **低** |
| L3 | set /p EOF | `set /p Q=Enter:` | `read -rp "Enter:" Q \|\| true` | EOF 时 cmd 保留原值、bash 置空 | **低** |
| N1 | `>` vs `>>` | `echo a > f` / `echo b >> f` | `echo "a" >f` / `echo "b" >>f` | 截断/追加语义**正确保留** | 无 |
| N2 | echo 特殊字符 | `echo $HOME` `echo *` `echo a;b` `echo a&&b` `echo \`id\`` `echo $(id)` `echo it's` `echo [a] (b)` `echo 100%%` `echo.` `echo > f` | `echo "\$HOME"` `echo "*"` `echo "a;b"` `echo "a" && b` ``echo "\`id\`"`` `echo "\$(id)"` `echo "it's"` `echo "[a] (b)"` `echo "100%"` `echo` `echo >f` | `$`/反引号/`$()`/glob/引号/分号全部正确加引号或转义；`echo.`→`echo` | 无 |
| N3 | set 值特殊字符 | `set X=a"b` `set Z=it's` ``set W=a`b`` `set V=100%%` `set U=back^&slash` `set C=a&b` `set P=pre;echo INJECT;` | `X="a\"b"` `Z="it's"` ``W="a\`b"`` `V="100%"` `U="back&slash"` `C="a"`+`b` `P="pre;echo INJECT;"` | 引号/反引号/`;`/`%` 处理正确（`&` 分行符合 cmd 语义） | 无 |
| N4 | attrib 权限位 | `attrib +r a.txt` / `-r` / `+h` / `+s` | `chmod -w` / `chmod +w` / `# TODO` / `# TODO` | 只映射只读位，**不产生 777、不给 +x**；无对应属性位诚实降级 TODO | 无 |
| N5 | reg（文本审查） | `reg add` / `reg query` / `reg delete` | `# TODO[REG] op=write key="HKLM\Software\Foo" value="Bar": ...` | 全部诚实 TODO（含 `reg query` 读取），**没有**猜测性注册表映射 | 无 |
| N6 | net 其它动词（文本审查） | `net stop spooler` / `net share` | `# TODO: 手动检查: net stop spooler` | 诚实 TODO | 无 |
| N7 | goto / exit /b | `goto :end` / `exit /b 0`（函数内） | `# TODO: 手动检查: goto :end` + 提示下游会被执行 / `return 0` | 诚实降级，并显式提示"原被 goto 跳过的代码在 bash 中会执行" | 无 |

---

## 3. 详细分析

### H1（高）`findstr` + `if errorlevel` ⇒ 条件恒真，误执行分支（实测误删）

**现象**
`findstr`（以及任何以 `grep` 结尾的管道）是 cmd 里最常用的"是否包含某串"判据，脚本标准写法就是紧跟 `if errorlevel 1`。产物把 `grep` 行加了 `|| true` 防 `set -e` 中止，但 `if errorlevel` 改写时又把**整行（含 `|| true`）**搬进了 if 条件。

**最小复现**（`/tmp/audit-misc/in/repro_d.bat`）

```bat
@echo off
findstr "needle" haystack.txt
if errorlevel 1 del keep.txt
echo still-here
```

产物：

```bash
# bat 过滤语义：未匹配不终止脚本
if ! grep "needle" "haystack.txt" || true; then
    rm -f "keep.txt"
fi
echo "still-here"
```

实测（`/tmp/audit-misc/sandbox/`，`haystack.txt` **确实包含** `needle`，`keep.txt` 存在）：

```
$ bash repro_d.sh
needle here
still-here
rc=0
$ ls
haystack.txt  repro_d.sh          ← keep.txt 已被删除
```

cmd 语义下 `findstr` 命中 ⇒ errorlevel 0 ⇒ `if errorlevel 1` 为假 ⇒ `keep.txt` 必须保留。**产物误删了它。**

**根因 + 代码锚点**
1. `_convert_simple`（2809–2838）对 `grep` 结尾的段追加 `|| true`：2820–2825（管道）与 2832–2837（单段）。
2. `_errorlevel_condition`（2114–2148）在 `threshold == 1` 时走 `previous = self._take_previous_command()`（2127）取回**已经带 `|| true` 的那一行**，再在 2148 返回 `f"! {previous}"`。

于是得到 `! grep ... || true`。bash 里 `!` 只作用于管道，`||` 优先级更低 ⇒ 整式 = `(!(grep ...)) || true` ⇒ **任何情况下状态都是 0**。已单独验证该优先级：

```bash
$ if ! echo hi | grep -q zzz || true; then echo "THEN taken"; else echo "ELSE taken"; fi
THEN taken            ← 未匹配也走 then
$ if ! echo hi | grep -q hi  || true; then echo "THEN taken"; else echo "ELSE taken"; fi
THEN taken            ← 匹配也走 then
```

**同一根因的第二形态：`%ERRORLEVEL%` 两个分支同时触发**
输入 `findstr "needle" haystack.txt` / `if errorlevel 1 echo NOT FOUND` / `if %errorlevel%==0 echo FOUND`，在 `haystack.txt` 含 `needle` 时实测：

```
$ bash err1.sh
has needle inside
NOT FOUND          ← cmd 不会打印
FOUND
rc=1
```

（`__bat2sh_rc=$?` 取到的是前面 `if...fi` 整体的状态 0，故两个分支都进。）

**对照（说明这是 `|| true` 拼接特有的问题，不是 `if errorlevel` 本身坏）**

- `type missing.txt` + `if errorlevel 1 echo TYPE-MISSING` → `if ! cat missing.txt; then echo "TYPE-MISSING"; fi` —— **正确**。
- `attrib +r a.txt` + `if errorlevel 1 echo ATTRIB-FAILED` → `if ! if [ -e "a.txt" ]; then chmod -w "a.txt"; fi; then ...` —— 语法合法，语义可接受。

**测试输入**：`/tmp/audit-misc/in/{repro_d,err1,el2}.bat`；产物 `/tmp/audit-misc/out/{repro_d,err1,el2}.sh`。

---

### H2（高）`$(...)` / `$(( ))` 在非 `echo` 命令中保持活跃 ⇒ 任意命令执行

**现象**
cmd 里 `$(` 没有任何特殊含义，是字面文本。产物在**除 `echo` 之外**的所有命令里都没有转义 `$`：`_dq_preserving_substitutions`（2183–2215）是**刻意保留** `$(...)` 的（双引号挡不住命令替换）。

**最小复现**（`/tmp/audit-misc/in/inj1.bat`）

```bat
@echo off
set E=a$(touch /tmp/audit-misc/sandbox/PWNED_SUBST)
echo %E%
```

产物：

```bash
E="a$(touch /tmp/audit-misc/sandbox/PWNED_SUBST)"
echo "${E}"
```

实测：

```
$ cd /tmp/audit-misc/sandbox && bash inj1.sh
a
rc=0
$ ls
PWNED_SUBST          ← $(...) 被真的执行了
```

**多命令验证**（`/tmp/audit-misc/in/dollar1.bat` + `set4.bat`，产物 + 实跑）

| 输入(bat) | 产物(bash) | 实测 |
|---|---|---|
| `set X=$(touch .../PWN_SET)` | `X="$(touch .../PWN_SET)"` | `PWN_SET` 被创建 |
| `type $(touch .../PWN_TYPE).txt` | `cat $(touch .../PWN_TYPE).txt` | `PWN_TYPE` 被创建 |
| `set /a NUM=$(touch .../PWN_ARITH)` | `NUM=$(( $(touch .../PWN_ARITH) ))` | `PWN_ARITH` 被创建（算术上下文里也执行） |
| `del $(touch .../PWN_DEL)` | `rm -f "$(touch .../PWN_DEL)"` | 同族（该行因前一行 rc=1 在 `set -e` 下未到达） |
| `copy a.txt $(touch .../PWN_COPY)` | `cp "a.txt" "$(touch .../PWN_COPY)"` | 同族 |
| `echo $(id)`（**对照**） | `echo "\$(id)"` | **安全**，字面打印 `$(id)` |
| `echo "in quotes $(...)"`（对照） | `echo "in quotes \$(...)"` | **安全** |

**根因 + 代码锚点**
- `$` → `_DOLLAR_PLACEHOLDER` 的保护**只对 `echo` 行生效**：`_convert_simple_no_pipe` 2942–2943（`if re.match(r"(?i)^@?\s*echo(?:\s|$)", body)`），还原在 `cmd_echo` 3369。
- `cmd_set`（3949–3951）走 `_dq_preserving_substitutions`（2183–2215）——该函数在 2188–2208 显式把 `$(...)` 原样搬进双引号内（只转义 `\`、`"`、反引号）。
- `_convert_path_token`（2217–2227）同样以 `_dq_preserving_substitutions` 收尾 ⇒ `del`/`copy`/`move` 等所有走它的目标参数都带这个性质。
- `cmd_type`（3384）更彻底：`"cat " + convert_backslashes(args)`，**完全不加引号**，`$(...)` 与反引号都是活的。

**后果性质**：源文件里出现 `$(`/反引号（cmd 下是普通字符）⇒ 产物执行任意命令。**这是源码静态注入，不是变量值注入**（`%VAR%` 展开成 `"${VAR}"`，变量内容不会被二次求值，这点已验证是安全的）。

---

### H3（高）重定向目标不加引号 ⇒ 通配符展开覆盖无关文件

**现象**
`_render_redirs` 只在目标"原本带引号"或"含空白"时才加引号（3153），**不考虑 `*` `?` `[`**。bash 会对未加引号的重定向目标做 pathname expansion；cmd 不做，`echo x > *.dat` 在 Windows 上只会创建一个名字就叫 `*.dat` 的文件。

**最小复现**（`/tmp/audit-misc/in/redirglob.bat`）

```bat
@echo off
echo new-content > log?.txt
echo second > *.dat
```

产物：

```bash
echo "new-content" >log?.txt
echo "second" >*.dat
```

实测（`/tmp/audit-misc/sbr/`，预置 `log1.txt` = `PRECIOUS-ORIGINAL-DATA`，`report.dat` = `OTHER-DATA`）：

```
=== before ===      log1.txt  report.dat
=== RUN artifact ===
$ bash redirglob.sh
rc=0
=== after ===
--- log1.txt ---
new-content          ← PRECIOUS-ORIGINAL-DATA 被覆盖
--- report.dat ---
second               ← OTHER-DATA 被覆盖
```

**根因 + 代码锚点**：`_render_redirs` 3139–3156，尤其是 3153：
`if quote or re.search(r"\s", converted): converted = self._dq_preserving_substitutions(converted)` —— 只有空白触发加引号。`?`/`*`/`[` 命中时目标裸奔。
诊断侧：`--report-json` 对该输入**只有 LF 换行告警**，无 TODO、无 glob 告警 ⇒ 完全静默。

**为什么严重**：两个被覆盖的文件都是**无关的既有文件**（用户并不想写它们），属于"越界写入 + 静默数据丢失"。`>>` 同样受影响（会往错文件追加）。

---

### H4（高，文本审查 + 只读 pgrep 实测）`taskkill /IM` → `pkill -f`：无锚定正则 + 命令行匹配 ⇒ 杀错进程

**现象**

| 输入(bat) | 产物(bash) |
|---|---|
| `taskkill /IM notepad.exe /F` | `pkill -f "notepad"` |
| `taskkill /IM app*.exe` | `pkill -f "app*"` |
| `taskkill /IM .exe` | `pkill -f ""` |
| `taskkill /PID -1` | `kill -1` |
| `taskkill /PID 0` | `kill 0` |
| `taskkill /PID abc` | `kill abc` |
| `taskkill /F` | `pkill` |

`cmd_taskkill`（3644–3666）：`/IM` 只剥掉结尾的 `.exe`（3663）后直接进 `pkill -f`（3664），**不做锚定、不转义正则、不做进程名校验**；`/PID` 的值**不做整数校验**（3655–3661）。

**实测证据（只读，未真跑 pkill）**：`pgrep` 与 `pkill` 共用同一匹配引擎。

```
$ pgrep -af "app*" | head -5
120 [oom_reaper]
142 [kswapd0]
175 [kworker/R-zswap-shrink]
1584 /usr/bin/kwin_wayland_wrapper --xwayland
2470 bwrap --unshare-all ...
```

`app*` 作为 ERE = "ap" + 任意个 "p"，于是 `reaper`、`zswap`、`wrapper` 全中 —— 包括**桌面合成器 `kwin_wayland`** 和内核工作线程。

```
$ pgrep -f "" | wc -l
606            （总进程数 609）
```

即 `taskkill /IM .exe` → `pkill -f ""` 会向**几乎所有本用户可发信号的进程**发 SIGTERM，包括当前会话/桌面。

**旁证（事故级实测）**：审查过程中我用 `pkill -f "notepad-daemon"` 清理自己的测试进程，结果**把我自己的 shell 杀掉了** —— 因为该 shell 的命令行文本里也含 `notepad-daemon`。这正是 `pkill -f` 匹配整条命令行的过匹配特性（`[killed by signal: SIGTERM]`）。

**`kill -1` / `kill 0`**：`kill -1` = 向所有有权限的进程发信号；`kill 0` = 向当前**进程组**全部成员发信号。产物把 cmd 里非法的 `-1`/`0` 原样透传。**未执行**（会波及宿主），此处为文本级判断 + POSIX `kill(1)` 语义；同族的 `kill <非数字>` 只是报错。

**兜底形态 `taskkill /F` → 裸 `pkill`**：实测裸 `pkill` 只打印 `pkill: 没有指定匹配标准` 且**不杀任何进程**（安全性 OK），但 **rc=2**，在 `set -euo pipefail` 下会中止脚本：

```
$ bash -c 'set -euo pipefail; pkill; echo "REACHED"'; echo "outer rc=$?"
outer rc=2          ← REACHED 未打印
```

---

### M1（中）`%VAR%` 紧跟 `*` 被 `%*`→`$*` 抢先替换

**现象**：`%N%*3` 被解析成 `%N` + `%*` + `3` → `%N$*3`。

**代码锚点**：`_expand_vars` 行 **1094** `text = text.replace("%*", "$*")` —— 一次**全局字符串替换**，而 `%NAME%` 的正则替换在同一函数 1230 行才执行。因为 `%N%` 的收尾 `%` 与后面的 `*` 组成 `%*`，被先吃掉。

**实测**（`/tmp/audit-misc/in/star_r2.bat`）

```bat
set n=2
set /a size=%n%*1024
echo size is %size%
copy data.txt backup.txt
echo DONE
```

产物：

```bash
n="2"
size=$(( %n$*1024 ))
echo "size is ${size}"
cp "data.txt" "backup.txt"
echo "DONE"
```

实跑（`/tmp/audit-misc/sbs2/`）：

```
$ bash star_r2.sh
rc=1
backup.txt: NEVER-CREATED
[stderr] 行 7: %n1024 : 算术语法错误：需要操作数
         行 8: size: 未绑定的变量
```

⇒ `size` 未赋值，读到它时 `set -u` **中止整脚本**：`size is ...` 没打印、**`cp` 从未执行**、`DONE` 没打印。

**静默性**：`--report-json` 对该输入**只报 LF 换行**，0 warning / 0 TODO。`bash -n` 通过。

**非 `/a` 形态 = 纯静默错值（rc=0）**：`echo val=%N%*2` → `echo "val=%N$*2"` 实跑输出 `val=%N2`；`set S=%N%*2` → `S="%N$*2"`；`if "%N%"=="5" echo eq%N%*` → 输出 `eq%N`。全部无告警。
（若写成 `echo v=%N%*2 > cfg.txt`，则会把 `v=%N2` 这种**错误内容**静默写进文件。）

---

### M2（中）`type \\?\C:\x.txt` → `cat \/?/C:/x.txt`：活通配符，越界读取

**产物**：`cat \/?/C:/secret.txt`。bash 里 `\/` 只是转义了 `/`（仍是路径分隔符），而 `?` **未被转义 ⇒ 活通配符，匹配任意单字符目录**。

**实测（真跑真实产物，用 `bwrap` 建命名空间，不影响宿主）**：在命名空间里把 `/q` 绑到含 `C:/secret.txt` 的目录，

```
$ bwrap --tmpfs / ... --bind /tmp/audit-misc/sb3/mountsrc /q ... bash -c 'cd /work && bash tg.sh'
UNINTENDED-FILE-READ-VIA-GLOB
```

（`tg.sh` 就是 bat2sh 对 `type \\?\C:\secret.txt` 的真实产物，未作任何修改。）对照 `printf '%s\n' \/?/C:/secret.txt` 在同样环境下输出 `/q/C:/secret.txt`，证明 `?` 确实在做单字符匹配。

**静默性**：`--report-json` 对该输入只有 LF 换行告警；无 TODO、无 glob 告警。
**根因 + 锚点**：`cmd_type` 3384 只用 `convert_backslashes(args)`，既不加引号也不做 glob 保护；`_convert_path_token`（2217–2227）虽有 glob 处理，但 `cmd_type` 刻意没走它（见 3380–3383 注释：为支持多参数）。
**注**：`\\?\` 系列在 HEAD 上并非全都漏 —— `del /F /A /Q \\?\%1` + `copy \\?\C:\a.txt` 这一例因生成结果 `bash -n` 失败，被整脚本降级为注释 + error（`/tmp/audit-misc/out/known.sh` 实测）。`cat \/?/...` 是**合法语法**，所以逃过了那张网。同族于 v2.11.0 已知的 `rm -rf \/?/${1:-}`。

---

### M3（中）`attrib +r <glob>` 守卫在多匹配时失效 ⇒ 静默不执行；`/s` 被当作目标

**产物**：`attrib +r *.txt` → `if [ -e *.txt ]; then chmod -w *.txt; fi`

**实测守卫行为**：

```
$ [ -e a.txt b.txt ]            # 两个匹配
bash: 第 3 行：[: a.txt: 需要二元运算符      rc=2 ⇒ if 为假 ⇒ chmod 完全不执行
$ [ -e a.txt ]                  # 一个匹配
rc=0                            ⇒ chmod 执行
```

即：**同一句 `attrib +r *.txt`，匹配 1 个文件时生效、匹配 ≥2 个文件时静默失效**（`set -e` 不会因此中止，因为它在 if 条件里）。

**`/s` 被当目标**：`cmd_attrib`（3292–3294）用 `re.fullmatch(r"[+-][A-Za-z]+", t)` 区分开关与目标，`/s` 两者都不匹配 ⇒ 落进 `targets`：

```
$ attrib /s +r a.txt
if [ -e "/s" ]; then chmod -w "/s"; fi ; if [ -e "a.txt" ]; then chmod -w "a.txt"; fi
```

本机 `/s` 不存在故为 no-op，但若存在就会被 `chmod`。`--report-json` 的 warning 只写 "attrib +r → chmod -w"，**没有任何 `/s` 被吞掉的提示**。

**权限映射本身：无问题（等级 无）** —— 只映射只读位（`+r`→`chmod -w`、`-r`→`chmod +w`），`+h`/`+s`/`+a`/`+r +h` 等一律诚实降级为 `# TODO`。实测**没有**出现 `chmod 777`、`chmod +x`、`chmod 000` 之类过宽/过窄位；`attrib +r -r` 按"最后一个生效"取 `+w`，与 cmd 一致。

---

### M4（中）`findstr /f:` `/g:` 被当成搜索模式；`/b` `/e` `/m` `/o` `/p` 被丢弃

产物（`/tmp/audit-misc/out/find2.sh`）：

```
grep /f:patterns.txt "log.txt" || true      ← findstr /f:patterns.txt log.txt
grep /g:patterns.txt "log.txt" || true      ← findstr /g:patterns.txt log.txt
grep "abc" "log.txt" || true                ← findstr /b "abc" log.txt   （/b 丢失）
grep "abc" "log.txt" || true                ← findstr /e "xyz" ...（模式对，但锚定丢失）
```

`cmd_findstr` 的开关白名单（3706）写的是 `low in ("/b","/e","/m","/o","/p","/f:")` —— **`/f:` 形式的带参开关永远匹配不上**（实际 token 是 `/f:patterns.txt`），于是落进 `positionals`，被 `_findstr_looks_like_file` 判为"不像文件"后**当成裸搜索模式**（3716–3721），真正的模式串成了被搜文件。`/g:` 连白名单都没有。

`--report-json` 对 `/f:`、`/g:` 两行**完全没有开关告警**（只有通用的"findstr 已转换为 grep"）；对 `/b` `/e` `/m` `/o` `/p` 有"开关未处理"告警，但**产物本身无痕**（不留 TODO）⇒ 报告不看的人会拿到静默改变匹配集合的脚本。

---

### M5（中）`findstr` 裸模式不加引号 ⇒ 模式被 glob 替换

`cmd_findstr` 3751–3752：

```python
if len(terms) == 1 and not terms[0][1] and bare_token is not None and not literal_terms:
    pattern_text = bare_token        # 裸发射，不加引号
```

**实测**（`/tmp/audit-misc/sb2/`，目录里有 `a1b.txt`，`log.txt` 内容为 `a1b.txt`）：

```
产物：grep a*b "log.txt" || true
$ bash fg.sh
a1b.txt
a1b.txt        ← 模式 a*b 被 glob 换成文件名 a1b.txt，搜的是错字符串
```

若 `log.txt` 不含该文件名，则 rc=1 被 `|| true` 吞掉 ⇒ **一条都不输出**（用户会误判"没匹配"）。无匹配文件时 bash 保留 `a*b` 字面量，grep 按 BRE 解释 `*` —— 又是第三种语义。

---

### M6（中）`type` / `call` 失败即 `set -e` 中止 ⇒ 后续全部跳过

产物（`/tmp/audit-misc/out/type1.sh`）：`type missing.txt` → `cat missing.txt`（**无任何守卫**）。

```
$ bash type1.sh          # missing.txt 不存在
rc=1
[stderr] cat: missing.txt: 没有那个文件或目录
```

`echo "AFTER-TYPE"`、随后**成功**的 `type present.txt`、`echo "AFTER-SECOND"` 全都没执行。cmd 下 `type` 失败只置 errorlevel 1 并继续。

同族：`call missing.bat` → `bash "missing.sh"` → rc=127 中止（实测 `AFTER-MISSING` 未打印）；`type *` 在目录含子目录时 → `cat *` 对目录报错 rc=1 中止，同时还把 cwd 下**所有**文件（含产物自身）都 cat 了出来。

**注**：项目对同类问题是有意识的 —— `rm -f`（`cmd_del`）、`userdel` 存在性守卫（`cmd_net` 3263–3267 注释明确写"避免目标物不存在把 rc==0 变成失败"）。`grep` 段也加了 `|| true`（虽然拼接方式出了问题，见 H1）。**唯独 `cat`（type）没有这层保护**。

---

### M7（中）`echo` / `set` 值里的 `\` 被静默改成 `/`

```
echo C:\path\to\file   →   echo "C:/path/to/file"      （cmd 会原样打印 C:\path\to\file）
set Y=a\b\c            →   Y="a/b/c"                   （cmd 里值是 a\b\c）
```

`cmd_echo`（3358）与 `cmd_set`（3949）都无条件走 `convert_backslashes`。`--report-json` 对这两行**没有任何反斜杠相关告警**（echo2 的告警只有 `%%i` 越界和 `ampersand`/`pipe` 未知命令）。属于"`bash -n` 过、无 TODO、行为错"的静默类别。

---

### M8（中，文本审查）`net user <name> /delete` → `userdel <name>`：账户名直通

产物：`if id -u daemon >/dev/null 2>&1; then userdel daemon; fi`

守卫只检查**Linux** 账户库里有没有同名账号（`cmd_net` 3270–3283，正则仅限 `[A-Za-z0-9._-]+`）。实测本机：

```
root -> 0     bin -> 1     daemon -> 2     mail -> 8     nobody -> 65534     sys/adm/lp/games/news/uucp -> (absent)
```

⇒ Windows 脚本里任何叫 `root`/`bin`/`daemon`/`mail`/`nobody` 的**普通业务账号**被删除时，会命中 Linux 的**系统账号**并真执行 `userdel`。这是名称空间碰撞，不是语法错误：产物、`bash -n`、TODO 检查全过。**未执行 `userdel`**（会改系统），结论为文本级 + 只读 `id -u` 佐证。

---

### M9（中，文本审查）`start <target>` 原样拼接 ⇒ 目标内的 `;` / `&` 成为命令分隔符

产物（`/tmp/audit-misc/out/start3.sh`）：

```bash
nohup foo;touch PWNED_SEMI >/dev/null 2>&1 &
nohup x&touch PWNED_AMP >/dev/null 2>&1 &
```

对应 `start "foo;touch PWNED_SEMI"` / `start "x&touch PWNED_AMP"`。

`cmd_start` 3523 用 `tokens[0].strip("\"'")` **剥掉引号**，3524 展开变量，3528–3535 判 `is_path`，3585 `command = (target + " " + rest).strip()`，3588 `f"nohup {command} >/dev/null 2>&1 &"` —— 全程**没有再加引号或转义**。只要目标不含 `\` `/` `%` `:` 且不以 `$`/`~`/`./`/`../`/已知后缀结尾（is_path 为假），就走这条裸拼路径。

同族的引号丢失（无注入但语义错）：`start "my app"` → `nohup my app >/dev/null 2>&1 &`（跑的是 `my` 带参数 `app`）。
**未执行这些产物**（`start` 按要求只做文本审查）。

---

### 低等级三项

- **L1** `taskkill /F`（无可解析参数）→ 裸 `pkill`：实测仅打印用法错误、**不杀进程**（安全），但 rc=2 ⇒ `set -e` 下中止脚本。
- **L2** `call :undefined_label` → `if declare -F label_undefined_label >/dev/null 2>&1; then label_undefined_label; fi`：静默 no-op，cmd 会报"找不到批处理标签"；会掩盖拼写错误。
- **L3** `set /p Q=Enter:` → `read -rp "Enter:" Q || true`：EOF 时 cmd 保留变量原值、bash 置空（配合 `%Q%`→`${Q:-}` 差异被吸收）。

---

## 4. 结论与建议

### 4.1 真风险（有实测破坏性后果/任意执行）

| 编号 | 等级 | 一句话 | 建议方向（不实施） |
|---|---|---|---|
| H1 | 高 | `grep` 段的 `|| true` 被 `if errorlevel` 改写搬进 if 条件 ⇒ 条件恒真 ⇒ **误执行分支（实测误删文件）** | `_errorlevel_condition` 取回 `previous` 后应先**剥掉尾部 `|| true` 守卫**再取反（`! (grep ...)`），或改为 `grep ...; if [ $? -ge N ]` 显式取码，绝不把 `\|\|` 留在条件里 |
| H2 | 高 | 非 `echo` 命令里的 `$()`/反引号**真执行** ⇒ 任意命令执行（实测 3 个 marker） | `_dq_preserving_substitutions` 应转义 `$(`/`` ` ``（与 `cmd_echo` 的占位符口径统一），或把 2942–2943 的 `$` 占位符保护从 `echo` 提升到**所有** handler |
| H3 | 高 | 重定向目标未加引号 ⇒ glob 展开**覆盖无关既有文件**（实测两处数据丢失） | `_render_redirs` 3153 的加引号条件加入 glob 元字符（`*?[`）；cmd 从不对重定向目标做 glob，应一律加引号 |
| H4 | 高 | `taskkill /IM` → `pkill -f`（无锚定正则 + 匹配整命令行）；`/IM .exe` → `pkill -f ""`（实测匹配 606/609 进程）；`/PID -1\|0` → `kill -1\|0` 无校验 | 至少改为 `pkill -x`/`pgrep -x` 精确进程名匹配 + 对 `/PID` 做 `^\d+$` 校验并拒绝 `-1`/`0`；`pkill -f ""` 与裸 `pkill` 必须显式拒绝而不是发射 |

### 4.2 真风险（静默错误，后果为非破坏性但确定的行为偏差）

| 编号 | 等级 | 一句话 |
|---|---|---|
| M1 | 中 | `%VAR%*` 被 `%*`→`$*` 吃掉 ⇒ `set /a` 场景**中止整脚本**（实测 `backup.txt` 未创建）、其它场景静默错值；**0 告警 0 TODO** |
| M2 | 中 | `type \\?\...` → `cat \/?/...`，`?` 活通配符 ⇒ 越界**读取**（已在命名空间中真跑证实） |
| M3 | 中 | `attrib +r <glob>` 的 `[ -e *.txt ]` 守卫多匹配时 rc=2 ⇒ 静默不执行；`/s` 被当目标路径（无告警） |
| M4 | 中 | `findstr /f:`/`/g:` 被当模式（真正模式丢失、无开关告警）；`/b /e /m /o /p` 丢弃 |
| M5 | 中 | `findstr` 裸模式不加引号 ⇒ 模式被 glob 换成文件名（实测搜到错字符串 / 静默无输出） |
| M6 | 中 | `type`/`call` 失败在 `set -e` 下中止整脚本（`cat` 缺守卫，与项目已有的 `rm -f`/`userdel` 幂等口径不一致） |
| M7 | 中 | `echo`/`set` 值里的 `\` 静默改成 `/`（输出文本/变量值被篡改，无告警） |
| M8 | 中 | `net user <name> /delete` → `userdel <name>`：`root`/`bin`/`daemon`/`mail`/`nobody` 直通 Linux 系统账号 |
| M9 | 中 | `start` 目标裸拼接、引号被剥 ⇒ `;`/`&` 成为命令分隔符（注入） |

### 4.3 理论风险 / 需人工判断

- H4 的 `kill -1` / `kill 0`、M8 的 `userdel`、M9 的 `start` 注入：**产物文本已确证**，但按纪律未真跑（会改系统）。其中 `pkill -f` 的过匹配已用只读 `pgrep` 实测，另有一次"误杀自己 shell"的真实旁证。
- M1 的"中止整脚本"依赖 `set -euo pipefail`（默认开）**且**该变量随后被读取；两者都成立时后果确定，只写不读时表现为静默未赋值。
- `findstr` 的正则方言差异（findstr vs BRE/ERE 在 `+` `?` `|` `(` `)` `{}` 上的行为）**未验证** —— 需要 Windows 侧对照，本次没有下任何结论。

### 4.4 明确不是风险的部分（本项实测无问题）

- `>` / `>>` 语义**正确保留**（无误截断）。
- `echo` 的 `$`、`$(...)`、反引号、`*`、`;`、`&&`、`|`、`&`、`'`、`"`、`[]()`、`%%`、`echo.`、`echo > f` 全部正确加引号/转义/占位符保护。
- `set VAR=value` 含 `"`、反引号、`;`、`&`、`|`、`%`、`!` 的转义正确（`&`/`|` 分行符合 cmd 语义）。
- `attrib` 的**权限位映射**本身无过宽/过窄问题（无 `777`、无 `+x`、无 `chmod 000`）；`+h/+s/+a` 诚实降级 TODO。
- `reg add/query/delete` → 全部 `# TODO[REG]`，不做猜测性注册表映射；`net stop`/`net share` 等 → 诚实 TODO。
- `goto` 未转换时不仅留 TODO，还额外提示"原被跳过的代码在 bash 中会执行"；`exit /b` 在函数内正确变 `return`。
- `call :label` 的标签未定义时用 `declare -F` 守卫（安全但静默，见 L2）。
- 生成脚本 `bash -n` 失败时整脚本降级为注释 + `# TODO` + error（实测见 `known.sh`），是一张有效的兜底网。

---

## 5. 未覆盖 / 存疑

1. **只做文本审查的命令**：`reg`、`net`（含 `userdel`）、`taskkill`（含 `kill -1`/`kill 0`/`pkill`）、`start`。它们的**产物文本**和 shell 语义已确证，但破坏性后果未真跑。其中 `pkill -f` 的匹配宽度用只读 `pgrep` 做了等效实测，`kill -1`/`kill 0` 只有 POSIX 语义 + 文本判断。
2. **`findstr` 与 `grep` 的正则方言差异**未验证（`+ ? | ( ) { }`、`\<`/`\>` 词边界、`/r` 的默认开启关系）。需要 Windows 侧 `findstr` 实测做对照，本次**没有**下结论。
3. **`type` 的多文件头部输出**：cmd 的 `type a.txt b.txt` 会打印文件名头，`cat a.txt b.txt` 不会 —— 只观察到格式差异，未评级（不影响安全）。
4. **`/f:` 的语义**我只按 MS 文档判定（从文件读取模式串），未在 Windows 上实测，因此 M4 的"真正模式丢失"是基于产物文本 + 文档的判断。
5. **`attrib` 对目录**：`chmod -w <dir>` 会阻止在该目录内创建文件（cmd 的只读属性不阻止），未构造用例评级。
6. **`set /a` 的其它表达式形态**（`<<`、`>>`、`&`、`|`、`^`、十六进制、负数除模）未系统覆盖；只验证了 `%VAR%*` 这一条冲突路径。
7. **`%*` 冲突的完整变体**未穷举（如 `%VAR%*` 之外，是否还有 `%VAR%?`、`%VAR%%VAR2%*` 等相邻组合的其它占位符碰撞）。已确认的只有 `%VAR%` 紧跟 `*`。
8. 未做**全量语料回归**：本次是定向构造用例（约 20 个 .bat），没有跑仓库自带语料/测试集，因此不能声称"已覆盖全部其它命令"。
9. `_DOLLAR_PLACEHOLDER` 的还原只挂在 `cmd_echo`（3369），我未逐一枚举**所有**不经过 `cmd_echo` 的 handler 是否还有别的 `$` 泄漏点（已验证泄漏：`cmd_set`、`cmd_type`、`cmd_del`、`cmd_copy`、`set /a`）；可能仍有未发现的 handler。

---

*实验文件：`/tmp/audit-misc/{in,out,sandbox,sandbox2,sb2,sb3,sbr,sbs,sbs2,sbc,sbd,sbe}/`。仓库内唯一新增文件为本报告。*
