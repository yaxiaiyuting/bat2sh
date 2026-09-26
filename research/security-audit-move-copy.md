# 安全审查 —— 移动/复制类命令（move / copy / xcopy / robocopy）

> 审查对象：`/home/duanjb666/bat2sh` @ `70a0ddb`（v2.11.0 发布后 main tip）
> 审查方式：**只读**（未修改仓库任何代码/测试，未 commit）+ 全部结论均有实测证据
> 实验目录：`/tmp/audit-mv/`（`cases/`、`cases2/` 输入，`out/` 产物与日志，`sandbox/` 真实副作用）

---

## 1. 审查范围与方法

### 1.1 代码锚点（函数名 + 行号）

| 位置 | 作用 |
| --- | --- |
| `python/bat2sh/core/batch.py:3435-3454` `cmd_copy` | `copy` → `cp` / `cp -f`（`/y` 才加 `-f`）；`nul` → `/dev/null` |
| `python/bat2sh/core/batch.py:3456-3460` `cmd_move` | `move` → `mv` / `mv -f`；**完全不看开关、不产生任何警告** |
| `python/bat2sh/core/batch.py:3462-3467` `cmd_xcopy` | `xcopy` → **恒定** `cp -r`（与 `/s` `/e` `/i` 无关） |
| `python/bat2sh/core/batch.py:3469-3496` `cmd_robocopy` | `robocopy` → `rsync -a`；`/mir` → `--delete`；未知开关/非两路径 → TODO |
| `python/bat2sh/core/batch.py:3498-3509` `_robocopy_dir_token` | 给两端补尾 `/`（模拟"复制目录内容"）；**含 `*`/`?` 时原样返回** |
| `python/bat2sh/core/batch.py:3159-3170` `_split_switches` | `/xxx` 开关识别；正则 `/[a-z]{1,3}(?:[-:][a-z0-9]+)*` |
| `python/bat2sh/core/batch.py:2217-2227` `_convert_path_token` | 路径 token 转换；**含通配符时提前返回，可能整段不加引号** |
| `python/bat2sh/core/batch.py:2183-2215` `_dq_preserving_substitutions` | 加双引号但**故意保留 `$(` 原样**（转义 `\ " \``，不转义 `$`） |
| `python/bat2sh/core/batch.py:1030-1095` `_expand_vars` | `%VAR%`/`%1`/`%%i` → `${VAR:-}`/`${1:-}`/`${i}` |
| `python/bat2sh/core/utils.py:176-229` `convert_backslashes` | `\` → `/`；`\\?\` / `\\.\` 前缀刻意保留 |
| `python/bat2sh/core/rules.py:20-24,52-55` | 简单映射表 + handler 表（`xcopy: cp -r`、`robocopy: rsync -a`、`move: mv`） |
| `python/bat2sh/core/batch.py:184-186` `_ROBOCOPY_IGNORED_FLAGS` | 忽略的输出类开关；`/mov` `/move` **不在**其中（→ TODO） |

> 行号已按审查结束时的实际工作树复核（`grep -n` 逐一确认）。
> 注：审查期间工作树出现过**其他 subagent** 对 `batch.py:1247-1262`（`%%~n` 修饰符）的无关改动，
> 本 subagent 未修改仓库任何文件；该改动不改变上述任何行号，也不在 move/copy 代码路径上。

### 1.2 CLI 调用方式（必须走仓库源码）

```bash
cd /home/duanjb666/bat2sh
PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/audit-mv/out/<case>.sh /tmp/audit-mv/cases/<case>.bat
bash -n /tmp/audit-mv/out/<case>.sh
```

批量复现脚本：`bash /tmp/audit-mv/run.sh`（全部 51 个用例逐个转换 + `bash -n`）。
`\\?\` 破坏性复现脚本：`timeout 90 unshare -rm --propagation private bash /tmp/audit-mv/repro.sh`
（本机 `/` 不可写、无单字符根目录，故用 userns+chroot 造等价环境；脚本自建 `/a/C:/…` 与 `/work`）。

### 1.3 覆盖的输入维度

`?` `*` / 空格 / 中文 / `$` 反引号 `;` `&` `|` `(` `)` `[` `]` `!` 单双引号 / `%1` `%VAR%` `%%i`
/ `/y` `/-y` `/s` `/e` `+/a/b` `/i` `/mir` `/mov` / UNC / 盘符 / `\\?\` / 尾随反斜杠 / 空变量 / 目录 vs 文件目标 / `for` 循环内 / `nul`。

---

## 2. 逐用例表

（产物列只列命令体，均另含 `#!/usr/bin/env bash` + `set -euo pipefail` 头；`bash -n` 除注明外全部 OK）

| # | 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- | --- |
| 1 | copy | `copy "C:\d\$(touch /tmp/…/PWNED_NC).txt" "D:\out\"` | `cp "C:/d/$(touch /tmp/audit-mv/sandbox/PWNED_NC).txt" "D:/out/"` | 路径里的 `$()` 被**真实执行** | **高** |
| 2 | copy | `copy "a^>b*.txt" dst\` | `cp a^>b*.txt "dst/"` | `>` 变重定向，**已有文件被截断为 0 字节** | **高** |
| 3 | copy | `copy "AT&T report*.txt" "D:\out\"` | `cp AT&T report*.txt "D:/out/"` | `&` 变控制符 → 复制不发生、rc=127、`set -e` 截断脚本 | **高** |
| 4 | move | `move "my doc*\f.txt" dst\` | `mv my doc*/f.txt "dst/"` | 词分割 → **CWD 里无关文件 `my` 被移走（源被删）** | **高** |
| 5 | copy | `copy "my doc*\f.txt" dst\` | `cp my doc*/f.txt "dst/"` | 同上：无关文件 `my` 被**错误复制**进 dst，目标文件未被复制 | **高** |
| 6 | xcopy | `xcopy /s /e srcdir dstdir`（dstdir 已存在） | `cp -r "srcdir" "dstdir"` | 目标已存在同名文件时**静默覆盖**（cmd 的 xcopy 在批处理里仍提示） | **高** |
| 7 | move | `move \\?\C:\a\b.txt dst\` | `mv \/?/C:/a/b.txt "dst/"` | `?` 是**活通配符** → 无关根级目录里的文件被移走 | **高** |
| 8 | copy | `copy f.txt \\?\C:\backup\` | `cp "f.txt" \/?/C:/backup/` | 写到**无关根级目录**（工作根之外） | **高** |
| 9 | xcopy | `xcopy srcdir dstdir`（无 `/s`，dstdir 不存在） | `cp -r "srcdir" "dstdir"` | 无 `/s` 也**递归**复制子目录（超范围复制） | 中 |
| 10 | xcopy | `xcopy /s /e srcdir dstdir`（dstdir 已存在） | `cp -r "srcdir" "dstdir"` | 语义应为"合并进 dstdir"，实际**嵌套成 dstdir/srcdir/** | 中 |
| 11 | move | `move * dst\` | `mv * "dst/"` | 连**目录**一起搬；dst 自身命中时报错并**部分执行** | 中 |
| 12 | move | `move /-y a.txt b.txt` | `mv "/-y" "a.txt" "b.txt"` | `/-y` 未识别成开关 → 变字面路径 → 参数个数错误、命令失败 | 中 |
| 13 | copy | `copy /-y a.txt b.txt` | `cp "/-y" "a.txt" "b.txt"` | 同上；"要求覆盖前提示"的意图丢失 | 中 |
| 14 | xcopy | `xcopy src dst /e /-y` | `cp -r "src" "dst" "/-y"` | 多出幽灵参数 → `cp` 报错（loud） | 中 |
| 15 | copy | `copy a.txt dstdir\link.txt`（link→外部文件） | `cp "a.txt" "dstdir/link.txt"` | `cp` 穿透符号链接，**越界覆盖链接目标** | 中 |
| 16 | robocopy | `robocopy C:\src D:\dst /MIR` | `rsync -a --delete "C:/src/" "D:/dst/"` | 盘符被 rsync 当**远程主机**（实测发起 ssh 连接 `c`/`d`） | 中 |
| 17 | robocopy | `robocopy src dst /MIR` | `rsync -a --delete "src/" "dst/"` | 目标端多余文件被删 —— 与 `/MIR` 语义**一致**（忠实） | 无 |
| 18 | robocopy | `robocopy src dst /MIR`（src 不存在 / 通配无匹配） | `rsync -a --delete "src/" "dst/"` | rc=23，**不清洗目标**（安全） | 无 |
| 19 | robocopy | `robocopy src dst /MOV` | `# TODO: 手动检查: robocopy src dst /MOV` | 删源语义不静默丢弃，交人工 | 无 |
| 20 | copy | `copy %1 %2`（未传参） | `cp "${1:-}" "${2:-}"` | 空串 → rc=1 报错，**未发生 `cp x /`** | 无 |
| 21 | move | `move "%DOESNOTEXIST%" "D:\dst\"` | `mv "${DOESNOTEXIST:-}" "D:/dst/"` | 空串 → rc=1，无破坏 | 无 |
| 22 | copy | `copy "中文 文件.txt" "中文 目录\"` | `cp "中文 文件.txt" "中文 目录/"` | 引号正确，安全 | 无 |
| 23 | copy | `copy "a!b*.txt" dst\` | `cp a!b*.txt "dst/"` | 非交互 shell 无历史展开，`!` 安全 | 无 |
| 24 | copy | `copy "C:\d\[ab]*.txt" dst\` | `cp "C:"/d\[ab]*.txt "dst/"` | `[` 被转义为字面（与 cmd 一致） | 无 |
| 25 | copy | `copy "C:\d\`id`*.txt" dst\` | 降级为 `# TODO: …未通过 bash -n 语法检查…` | **防线有效**：反引号/不配对括号被拦下 | 无 |
| 26 | for | `for %%i in (*.txt) do move %%i dst\` | `shopt -s nullglob` + `mv "${i}" "dst/"` | 引号 + nullglob，安全 | 无 |
| 27 | copy | `copy f.txt /tmp` | `cp "f.txt"` | `/tmp` 被当开关吞掉，目标参数消失（有 1 条警告） | 低 |
| 27b | copy | `copy a.txt b.txt /tmp` | `cp "a.txt" "b.txt"` | 被吞参数使 `b.txt` 变成目标并**静默覆盖**（rc=0，cmd 侧 `/t` 是非法开关会报错） | 中 |
| 28 | copy | `copy a.txt D:\out\*` | `cp "a.txt" "D:/out"/*` | 通配无匹配时创建**字面文件名 `*`** | 低 |
| 29 | copy | `copy f.txt \\server\share\` | `cp "f.txt" "\\/server/share/"` | 实为相对路径（字面 `\` 目录），rc=1 失败，无越界写入 | 低 |
| 30 | copy | `copy a.txt+b.txt c.txt` | `cp "a.txt+b.txt" "c.txt"` | cmd 的合并语法丢失，失败（loud） | 低 |
| 31 | robocopy | `robocopy C:\a\f.txt D:\dst` | `rsync -a "C:/a/f.txt/" "D:/dst/"` | 文件源被补尾 `/` → rc=23 Not a directory | 低 |
| 32 | xcopy | `xcopy /s /e srcdir dstdir`（源含符号链接） | `cp -r "srcdir" "dstdir"` | 链接被**原样复制**（`dst/linkdir -> ../big`），内容没复制 | 低 |
| 33 | robocopy | `robocopy C:\out\*.txt D:\bak /MIR` | `rsync -a --delete "C:/out"/*.txt "D:/bak/"` | 实测：通配源时 rsync **不执行** `--delete` 清洗（比担心的更安全） | 无 |
| 34 | copy | `copy nul empty.txt` / `copy secret.txt nul` | `cp /dev/null "empty.txt"` / `cp "secret.txt" /dev/null` | 与 cmd 一致（丢弃输出） | 无 |
| 35 | copy | `copy a.txt b.txt`（无 `/y`） | `cp "a.txt" "b.txt"` | 实测静默覆盖；但 MS 文档称批处理内 cmd 亦不提示 → 见 §5 存疑 | 低（存疑） |
| 36 | move | `move a.txt b.txt`（无 `/y`） | `mv "a.txt" "b.txt"` | 同上；`move` 文档明确"批处理内默认不提示" → **忠实** | 无 |

---

## 3. 详细分析

### 3.1 【高】路径文本被当作活的 shell 代码（转义缺失）

**现象**：只要路径 token 里出现 `*`/`?`（走 `_convert_path_token` 的提前返回分支，`batch.py:2221-2226`），
或者出现 `$(`（`_dq_preserving_substitutions` 故意不转义 `$`，`batch.py:2183-2215`），
原文就会**原封不动**进入产物命令行，`&` `;` `|` `>` `$()` 全部按 shell 语法生效。

**最小复现 1（命令替换，无需通配符）**

```
输入: copy "C:\d\$(touch /tmp/audit-mv/sandbox/PWNED_NC).txt" "D:\out\"
产物: cp "C:/d/$(touch /tmp/audit-mv/sandbox/PWNED_NC).txt" "D:/out/"
执行: rc=1（cp 找不到文件），但 PWNED_NC 已被创建 → 实测 YES
```

双引号**不能**阻止 `$()` 执行；实测副作用文件落在工作根之外。

**最小复现 2（`>` 截断已有文件）**

```
输入: copy "a^>b*.txt" dst\        （cmd 侧 ^> 表示文件名里的字面 >）
产物: cp a^>b*.txt "dst/"
执行前 b1.txt = "PRECIOUS"；执行后 rc=1，b1.txt 大小 = 0 字节
```

`^` 未被剥离、`>` 未被转义 ⇒ 重定向把**无关文件清零**。这是本节里最直接的"静默破坏"。

**最小复现 3（`&` 让复制根本不发生）**

```
输入: copy "AT&T report*.txt" "D:\out\"
产物: cp AT&T report*.txt "D:/out/"
执行: cp AT&T 被后台化（"在 'AT' 后缺少要操作的目标文件"）
      → 下一条命令 T … → bash: T: 未找到命令，rc=127
      → 因 set -euo pipefail，脚本**在此终止**（实测后续行未执行）
```

`;`（`cp a;b*.txt "dst/"`）、`|`（`cp a|b*.txt "dst/"`）同理。

**根因**：`_convert_path_token` 在两条路径上放弃引号/转义：
`batch.py:2225` 只给 head 加引号，tail 裸奔；`batch.py:2226` 整个 token 原样返回（连空格都不再保护）。
`_dq_preserving_substitutions` 为了保留转换器自己生成的 `$(...)`（`for /f` 等），选择不转义 `$`，
但**无法区分**"转换器生成的替换"与"源文本里用户写的 `$(`"。

> 对照：`del` 已知风险（`rm -rf \/?/${1:-}`）是同一类；本类在 move/copy 上多了"截断已有文件"和"整条命令被截断"两种后果。

### 3.2 【高】目录部分含通配符 + 空格 ⇒ 词分割 ⇒ 对 CWD 无关文件动手

**现象**：通配符在**目录段**时（`head_probe` 也含 `*`/`?`），`batch.py:2226` 把整段原样返回，
用户写在 bat 里的引号被剥掉（`utils.py:18-23` `strip_outer_quotes` 先剥离），空格重新变成参数分隔符。

**最小复现（相对路径，最干净）**

```
输入: move "my doc*\f.txt" dst\       产物: mv my doc*/f.txt "dst/"
沙箱: ./my（无关文件）、./my doc1/f.txt（真正想移的文件）
执行: rc=1；dst/ 里出现 my（内容 MY-PLAIN-FILE）
      'my' 还在 CWD? NO —— 被移走（源删除）
      'my doc1/f.txt' 还在? YES（真正目标根本没动）
stderr: mv: 对 'doc*/f.txt' 调用 stat 失败
```

`copy` 版本（`cp my doc*/f.txt "dst/"`）同样把无关的 `my` 复制进目标、真正目标未复制。

**为什么现实**：Windows 上 `C:\Program Files*\...`、`C:\my doc*\...` 这类"带空格的目录 + 通配符"是合法写法；
产物落到 Linux 后，第一段 `C:/Program` 变成相对路径、第二段 `Files*/app/conf.ini` 变成**以 CWD 为根的 glob**，
匹配到什么就复制/移动什么。**实测已复现"无关文件被移走"（源删除）。**

### 3.3 【高】`xcopy` 无 `/y` ⇒ `cp -r` 静默覆盖（cmd 侧会提示）

```
输入: xcopy /s /e srcdir dstdir        产物: cp -r "srcdir" "dstdir"
实测: 源为文件、目标目录已存在同名文件时
      cp -r "srcdir/a.txt" "dstdir"  →  rc=0，dstdir/a.txt 由 ORIGINAL 变为 NEW（静默覆盖）
```

- MS 文档 xcopy：*"By default, you're prompted to overwrite."* —— **没有**"批处理内例外"这一条
  （[xcopy.md](https://raw.githubusercontent.com/MicrosoftDocs/windowsserverdocs/main/WindowsServerDocs/administration/windows-commands/xcopy.md)）。
- 转换器把 `/y` 与"无 `/y`"映射成同一个 `cp -r`，`cmd_xcopy`（`batch.py:3462-3467`）**不做任何提示/警告**
  （实测 `xcopy /s /e src dst` 的警告数 = 0），差别被完全抹平 ⇒ 数据丢失且无感知。

> **对父任务前提的更正**：`copy` / `move` 两条**不是**同类问题。MS 文档明确写了批处理内例外：
> `move`：*"The default is to prompt before overwriting files, unless the command is run from within a batch script."*
> （[move.md](https://raw.githubusercontent.com/MicrosoftDocs/windowsserverdocs/main/WindowsServerDocs/administration/windows-commands/move.md)）
> `copy`：*"…unless the copy command is executed in a batch script."*
> （[copy.md](https://raw.githubusercontent.com/MicrosoftDocs/windowsserverdocs/main/WindowsServerDocs/administration/windows-commands/copy.md)）
> 即 **bat 内的 `copy`/`move` 本来就不提示**，`cp`/`mv` 的静默覆盖对这两条是忠实的；
> 只有 `xcopy` 是真正的语义丢失。残留不确定性见 §5。

### 3.4 【高】`\\?\` 前缀 ⇒ 活的 `?` 通配符（与已知 `del` 风险同类）

```
输入: move \\?\C:\a\b.txt dst\      产物: mv \/?/C:/a/b.txt "dst/"
输入: copy f.txt \\?\C:\backup\     产物: cp "f.txt" \/?/C:/backup/
```

`convert_backslashes` 刻意保留 `\\?\`（`utils.py:160-165` 注释），但 `\` 在 bash 里只是转义了 `/`：
产物等价于 `/?/C:/a/b.txt` —— `?` 匹配**任意单字符根目录**。

**实测复现**（userns+chroot，脚本 `/tmp/audit-mv/repro.sh`；本机 `/` 不可写，无法直接造 `/a`）：

| 场景 | 结果 |
| --- | --- |
| 负对照：`/` 下无单字符目录 | `mv: 对 '/?/C:/a/b.txt' 调用 stat 失败`，rc=1（安全） |
| 存在无关目录树 `/a/C:/a/b.txt` | `mv \/?/C:/a/b.txt "dst/"` → **rc=0**，`dst/b.txt` 出现，`/a/C:/a/` 变空 ⇒ **无关文件被移走（源被删）** |
| 存在无关目录树 `/a/C:/backup/` | `cp "important.txt" \/?/C:/backup/` → **rc=0**，文件被写进 `/a/C:/backup/`（**工作根之外**），`/work` 下无产出 |

即：**该转义却没转义的通配符**，同一 token 内的空格也不再被引号保护（`\\?\C:\very long path\…` → 词分割）。
触发前提是 `/` 下存在单字符目录（真机罕见，但**不是不可能**；参考 v2.11.0 的 `rm -rf \/?/` 结论）。

### 3.5 【中】`xcopy` 语义整体失真（递归 / 合并 / 空目录 / 开关）

| cmd 语义 | 产物 `cp -r` 实测 |
| --- | --- |
| 无 `/s`：只处理**单层目录** | `xcopy srcdir dstdir` → 子目录 `sub/g.txt` **也被复制**（超范围） |
| 目标已存在：把源**合并进**目标目录 | `cp -r srcdir dstdir` → 生成 `dstdir/srcdir/…`（**位置错**，`dstdir/f.txt` 原样不动） |
| `/h` 才复制隐藏/系统文件、`/k` 保留只读、`/r` 复制只读、`/d` 按日期 | 全部忽略，实测**警告数 0** |
| 目标不存在且无 `/i` 时会问 F/D | 直接建目录（行为不同但不破坏） |

### 3.6 【中】`move *` / `cp *`：目录也搬，且目标自身命中会中途失败

```
输入: move * dst\   产物: mv * "dst/"
实测: dst/ 里同时出现 a.txt 与 **整个目录 sub/**（cmd 的 move 通配只处理文件）
      rc=1，stderr: mv: 无法将目录 'dst' 移动至自身的子目录 'dst/dst'
      ⇒ 命令**部分成功**（部分文件已移动、命令报错），脚本状态不一致
```

### 3.7 【中】`/-y` 未被当作开关 ⇒ 幽灵路径参数

`_split_switches` 的正则 `/[a-z]{1,3}(?:[-:][a-z0-9]+)*`（`batch.py:3163`）要求 `/` 后紧跟字母，
因此 `/-y`（cmd 里表示"覆盖前**要求**提示"）落入 targets：

```
move /-y a.txt b.txt   → mv "/-y" "a.txt" "b.txt"    （3 参数 → mv 把最后当目录 → 报错）
copy /-y a.txt b.txt   → cp "/-y" "a.txt" "b.txt"    （同上）
xcopy src dst /e /-y   → cp -r "src" "dst" "/-y"      （同上）
```

后果是"参数个数变化 + 命令失败"（loud，无静默数据丢失），但用户**显式要求提示**的语义彻底丢失。
注意 `cmd_move` 从不发警告 ⇒ 除产物本身外没有任何提示。

### 3.8 【中】`cp` 穿透符号链接目标（越界写入）

```
沙箱: out/link.txt -> ../outside/target.txt
产物: cp "a.txt" "out/link.txt"
实测: rc=0，outside/target.txt 内容由 OUTSIDE-ORIGINAL 变为 NEW（链接本身未被替换）
```

`mv` 不穿透（替换链接本身），`cp` 穿透。Windows 侧无等价物，属 `cp` 继承行为而非映射选择，
但 `xcopy → cp -r` 的产物在 Linux 工作目录里确实会写到"目标目录之外"。

### 3.9 【中】robocopy 盘符路径被 rsync 当成**远程主机**

```
产物: rsync -a --delete "C:/src/" "D:/dst/"
实测: rsync 把 C:/ 当主机 c、D:/ 当主机 d →
      "rsync: connection unexpectedly closed" + "ssh: Could not resolve hostname c/d"（rc=255）
两边都有盘符时: "The source and destination cannot both be remote."（rc=1）
```

即 robocopy 映射在正常 Windows 路径下**不可用且语义变成网络传输**：本机若存在同名 ssh 别名/主机（`c`、`d`），
会真的发起远端传输。`/MIR` 的 `--delete` 在"源为远程、目标为本地"时清洗的是**本地目标**（该组合未实测，见 §5）。

### 3.10 【低】其他实测差异

- **开关吞路径**：`copy f.txt /tmp` → `cp "f.txt"`（`/tmp`、`/etc`、`/mnt` 等 1–3 字母 POSIX 路径会被 `_split_switches` 当开关），目标参数消失、命令必然失败；有 1 条警告。
  **被吞的是中间参数时更危险**（实测 i31）：`copy a.txt b.txt /tmp` → `cp "a.txt" "b.txt"` → rc=0，`b.txt` 由 `ORIGINAL-B` 变为 `NEW-A`（**静默覆盖**）。cmd 侧 `/t` 是非法开关会直接报错，不存在这个覆盖动作。
- **目标通配**：`copy a.txt D:\out\*` → `cp "a.txt" "D:/out"/*`；无匹配时 `D:/out` 下出现**字面文件名 `*`**（rc=0）。
- **UNC**：`\\server\share\` → `"\\/server/share/"` = 以 CWD 为根的相对路径（首段是字面 `\` 目录名）⇒ rc=1 失败，**没有**写到 `/server/share`，无越界写入。
- **`copy a+b`** 合并语法丢失（`cp "a.txt+b.txt"` 失败）。
- **robocopy 文件源**：`_robocopy_dir_token` 无条件补 `/` → `rsync -a "C:/a/f.txt/"` → rc=23 `Not a directory`（robocopy 本可复制该文件）。
- **源内符号链接**：`cp -r` 原样复制链接（`dst/linkdir -> ../big`），内容不复制；若链接指向 `/` 或 `~/.ssh`，指向树外的链接会出现在目标端。

### 3.11 【无】已验证安全 / 忠实的行为

| 项 | 证据 |
| --- | --- |
| 空变量 / 缺参 | `%1`、`%VAR%` → `${1:-}`/`${VAR:-}` 且**始终加双引号**；`mv "" "D:/dst/"`、`cp "a.txt" ""` 均 rc=1 失败，**未发生 `mv x /`** |
| `robocopy /MIR` → `--delete` | 目标端多余文件/目录被删（与 `/MIR` = `/E`+`/PURGE` 一致）；源缺失 → rc=23 **不清洗**；通配源 → rsync 实测**不**执行清洗 |
| `/MOV` `/MOVE` | 不在忽略表 ⇒ 诚实 TODO，不静默丢掉"复制后删源" |
| 引号 | 不含通配符时一律双引号（空格、中文、`;`、`&`、`(` 均被保护，见 c14/c15/i6） |
| `!` / `[` `]` | 非交互无历史展开；`\[ab]` 正确转义为字面 `[` |
| 反引号、不配对括号 | 产物 `bash -n` 失败 → **自动降级为 TODO 注释**（防线有效，实测 c22/c24/i1） |
| `for %%i in (*) do move %%i` | 自动加 `shopt -s nullglob` + `"${i}"` 引号 |
| 尾随反斜杠 | `"C:\src dir\"` → `"C:/src dir/"`（正确） |
| `nul` | `copy nul f` → `cp /dev/null f`；`copy f nul` → `cp f /dev/null`（与 cmd 一致） |

---

## 4. 结论与建议

### 4.1 真风险（有可复现破坏性后果）

1. **路径文本当 shell 代码**（§3.1，高）：`$()` 真执行、`>` 真截断、`&`/`;`/`|` 真分割并截断脚本。
   影响面最大的不是"恶意文件名"，而是**普通文件名**：`AT&T report*.txt`、`v1 & v2*.zip`、`a>b*.txt` 这类完全正常的 Windows 文件名一旦与通配符同 token 就会炸。
2. **词分割导致对 CWD 无关文件执行 cp/mv**（§3.2，高）：实测"无关文件被移走"（源删除）。
3. **`xcopy` 无 `/y` 的静默覆盖**（§3.3，高）：cmd 会提示、`cp -r` 不会。
4. **`\\?\` 的 `?` 变活通配符**（§3.4，高）：实测误移无关文件、写入无关根级目录。
   （触发前提为 `/` 下存在单字符目录，属条件性高危，但后果与已知 `del` 风险同级。）

### 4.2 理论/条件性风险（不建议按高危处理）

- **`copy`/`move` 无 `/y` 的静默覆盖**：文档口径下 bat 内 cmd 本来就不提示 ⇒ 对这两条**是忠实的**，不应算转换缺陷。
- **UNC / 盘符**：产物在 Linux 上必然失败（rc≠0，loud），未观察到越界写入；风险主要是"不可用"与"rsync 误当远程"。
- **`cp` 穿透符号链接**：继承自 `cp`，非映射选择；只有在目标目录被不可信方放入链接时才可利用。
- **`/-y`、`/tmp` 被吞**：破坏是"命令报错"，不是静默数据丢失。

### 4.3 建议（不含修复实现，仅给方向）

1. **转义优先于引号拼接**：含通配符的分支至少应对非通配字符做 shell 转义（`\ `、`\;`、`\&`、`\>`、`\(`…），
   并保证 head 引号 + tail 转义的组合不会把 `$(` 留在"活"的位置；同时把"源文本里用户写的 `$(`"与"转换器生成的替换"区分开（占位符化后再还原）。
2. **`xcopy` 的覆盖语义要么保真要么显式警告**：至少在没有 `/y` 时给出"cmd 会提示、产物不会"的警告；`cmd_xcopy` 现在 0 警告是最容易被忽略的一环（`cmd_move` 同理，至少应警告无法识别的 `/-y`）。
3. **通配符身份**：对来自 `\\?\`/`\\.\` 前缀的 `?` 要么继续报 TODO/警告，要么按字面转义（`\?`），不要让它以未加引号的形式进入命令行。
4. **`_split_switches` 收紧**：`/[a-z]{1,3}` 会吞掉 `/tmp`、`/etc` 等真实路径，建议要求开关后面要么是行尾要么是另一开关，或对不存在的开关保持原样并只警告。
5. **robocopy**：明确声明"盘符路径在 Linux 无对应物"，不要产出会被 rsync 解释为远程主机的 `X:/...`；`/MIR` 的 `--delete` 建议保持现有警告强度（实测其删除范围是忠实的）。
6. **回归测试建议**：把 §2 表中 1–8 号用例固化为 golden case（含 `\\?\` 的 chroot/userns 复现脚本思路）。

---

## 5. 未覆盖 / 存疑

1. **cmd.exe 侧全部未实机对照**（本机无 Windows）：`copy`/`move`/`xcopy`/`robocopy` 的原始语义均引自 MS Learn 文档。
   其中 `copy`/`move`"批处理内默认不提示"这一条直接决定了 §3.3 的定级，**建议由有 Windows 环境的人复核一次**（`copy` 文档原句有歧义："By default, you are prompted when you replace this setting, unless the copy command is executed in a batch script."）。
2. **`xcopy` 的 F/D 交互提示、`/h` `/k` `/d` `/u` `/a` `/m` 等被忽略开关**的实测差异未做（只做了 `/s` `/e` `/i` `/y`）。
3. **`copy /a`（ASCII，遇 CTRL+Z 截断）与 `/b`** 的差异未测；`/z`（可重启复制）未测。
4. **robocopy 的 `/MIR` + 文件筛选/排除列表**未与真 robocopy 对照；"源为远程主机 + `--delete` 清洗本地目标"只是由 `rsync` 语义推断，**未实测**。
5. **`\\?\` 破坏性复现的前提**：真机 `/` 下需存在单字符目录；本机 `/` 不可写、无此目录，我用 `unshare -rm` + chroot 造了等价环境（`/tmp/audit-mv/repro.sh`）。"`?` 是活通配符"这一点是确定的；"是否在某个真实环境中命中"取决于该前提是否满足。
6. **`for /f` / `for /r` / `%%~nxF` 等修饰符生成的 move/copy 参数**未系统覆盖（只覆盖了 `for %%i in (*.txt)` 与 `for /d`）。
7. **move/copy 与重定向、管道、`&&`/`||` 组合**（`split_redirects` / pipeline 路径）未覆盖；`copy x > log` 之类未验证。
8. **`%~dp0` 等参数修饰符在 move/copy 参数中的展开**未单独验证。
9. **多源形式** `copy a.txt b.txt dst\` → `cp "a.txt" "b.txt" "dst/"`（复制两个文件）；cmd 的 `copy` 只有一个 source，但**cmd 侧报错还是忽略多余参数未实测**，故未列入正式风险。
10. **只读目标 / 权限位差异**（Windows 只读文件 vs Linux 0444）未测：非交互下 `cp`/`mv` 对只读目标的实际行为可能又是一处差异。
11. `%*`（`move %* `）、`shift` 后 `%1` 变化、`call :label` 传参等**运行时参数形态**未覆盖。
12. `robocopy` 的 `/MIR` 与 `-a` 的属性/时间戳保真度（rsync `-a` 保留权限/属主/时间戳 vs robocopy 的 `/COPY:DAT`）未做行为对照。

---

### 附：关键实验证据索引

| 证据 | 位置 |
| --- | --- |
| 全部用例批量转换 + `bash -n` | `bash /tmp/audit-mv/run.sh`（输入 `/tmp/audit-mv/cases/*.bat`，产物/日志 `/tmp/audit-mv/out/`） |
| 注入类用例（`$()` `&` `>` 等） | `/tmp/audit-mv/cases2/i*.bat` → `/tmp/audit-mv/out/i*.sh` |
| `\\?\` 破坏性复现（userns+chroot） | `timeout 90 unshare -rm --propagation private bash /tmp/audit-mv/repro.sh`（另见 `repro2.sh`、`repro3.sh`） |
| 真实副作用沙箱 | `/tmp/audit-mv/sandbox/{S1,S3,S4,S5,R5,R6,R7,R10,R13,R14,R18,R19,R21,…}` |
| 警告计数（0 警告） | `PYTHONPATH=python python3 -m bat2sh --cli -o /tmp/… /tmp/audit-mv/cases/c01_copy_noY.bat` 等（见 §2 说明） |
