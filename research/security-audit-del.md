# 安全审查 —— 删除类命令（del / deltree / rd / rmdir）

- 审查对象：`/home/duanjb666/bat2sh` @ `70a0ddb`（v2.11.0 后 main tip）
- 审查性质：**只读**。本文件是本次审查唯一写入的文件；未修改任何代码/测试，未 `git commit`。
- 结论口径：**每条结论都附实测证据**（真实产物文本 / `bash -n` 结果 / 真跑后的真实副作用）。
  产物均用仓库源码生成，未使用已安装的 `/usr/bin/bat2sh`。
- **版本漂移说明**：审查期间该 checkout 被并行会话推进（`70a0ddb` → `0535cac` + 工作区改动）。
  已确认**删除类代码路径逐字节未变**（`70a0ddb..工作区` 的 `batch.py` 改动只在 `1247-1265` 的 `%%~n`
  修饰符实现；`cmd_del` / `cmd_rmdir` / `_convert_path_token` / `_split_switches` /
  `_dq_preserving_substitutions` / `rules.BATCH_ENV_MAP` 均未改，锚点行号一致）。
  收尾时对当前工作区重跑了 8 个关键用例，产物与表中记录**完全一致**：
  `del /s /q %WINDIR%\*`→`rm -rf "/"/*`；`rd /s /q \\?\C:\data`→`rm -rf \/?/C:/data`；
  `del /s \`→`rm -rf "/"`；`del "a$b.txt"`→`rm -f "a$b.txt"`；
  `del /s /q "C:\Program Files\*\*.log"`→`rm -rf C:/Program Files/*/*.log`；
  `del "%1"\*.tmp`→`rm -f ""${1:-}""/*.tmp`；`del /f /q %1 %2`→`rm -f "${1:-}" "${2:-}"`；
  `del /s /q "logs dir\*\*.log"`→`rm -rf logs dir/*/*.log`。

---

## 1. 审查范围与方法

### 1.1 代码锚点（函数名 + 行号）

| 锚点 | 位置 | 作用 |
| --- | --- | --- |
| `BatchConverter.cmd_del` | `python/bat2sh/core/batch.py:3419-3425` | `del` / `erase` 的转换；**3423** `command = "rm -rf" if "/s" in flags else "rm -f"`；**3424** 逐 token 调 `_convert_path_token`（**无 `--`**） |
| `BatchConverter.cmd_rmdir` | `batch.py:3427-3433` | `rd` / `rmdir` 的转换；**3429** 同上选 `rm -rf` / `rmdir`；**3432** 逐 token 转换（**无 `--`**） |
| `BatchConverter._convert_path_token` | `batch.py:2217-2227` | 唯一路径出口：**2220** `probe` 去 `${…}`/`$(…)` 后查 `*`/`?`；**2222** `rpartition("/")`；**2224-2225** head 无通配符 → `f'"{head}"/{tail}'`（**手写拼接，未走 `dq()`**）；**2226** head 也有通配符 → **整条不加引号返回** |
| `BatchConverter._dq_preserving_substitutions` | `batch.py:2183-2215` | 无通配符路径的加引号；只转义 `\` `"` `` ` ``，**保留 `$(`…`)` / `${`…`}` 原样** |
| `BatchConverter._split_switches` | `batch.py:3158-3170` | **3163** `/[a-z]{1,3}(…)*`、**3166** `/[a-z](/[a-z]{1,3})+` 把 token 判为开关 |
| `BatchConverter._expand_vars` | `batch.py:1030-1095` | **1094** `%*`→`$*`；**1095** `%N`→`${N:-}`；环境变量映射见 `rules.BATCH_ENV_MAP` |
| `rules.BATCH_HANDLER_MAP` | `rules.py:57-60` | `del`/`erase`→`cmd_del`，`rd`/`rmdir`→`cmd_rmdir`；**没有 `deltree`** |
| `rules.BATCH_ENV_MAP` | `rules.py:219-244` | **224** `HOMEDRIVE: ""`；**225-226** `TEMP/TMP: ${TMPDIR:-/tmp}`；**238** `SYSTEMDRIVE: "/"`；**239** `SYSTEMROOT: ${SystemRoot:-/}`；**240** `WINDIR: "/"`；**242** `LOCALAPPDATA: ${XDG_DATA_HOME:-$HOME/.local/share}` |
| `utils.convert_backslashes` / `_is_substitution` | `utils.py:176-229` / `148-173` | 反斜杠→`/`；**169-170** 的 `\\?`/`\\.` 排除是提交 `743abc1` 加的，其注释**自己写明** `rm -rf \/?/` 会误删（只在"反斜杠转义"这一条路径上生效） |
| `utils.dq` | `utils.py:26-29` | 也**不转义 `$`** |
| 语法降级 | `batch.py:581-586` + `syntax.py:17,71` | 生成脚本 `bash -n` 失败 ⇒ **整文件**降级为注释 |

### 1.2 调用方式

```bash
cd /home/duanjb666/bat2sh
PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/audit-del/out/<case>.sh /tmp/audit-del/cases/<case>.bat
PYTHONPATH=python python3 -m bat2sh --cli -q --no-bash-check -o /tmp/audit-del/out/<case>.raw.sh …   # 看降级前的原始产物
bash -n /tmp/audit-del/out/<case>.sh
```
报告口径用 `--report`（`-q` 会把警告吞进报告，不打印）。

### 1.3 实验目录与规模

- `/tmp/audit-del/cases`：**120** 个手工用例（含 `?`、`*`、空格、中文、`$`、反引号、`;`、`&`、`|`、`()`、`[]`、`!`、单双引号、`%1`、`%VAR%`、`%%i`、`%*`、`/s /q /f /a /p`、盘符、UNC、`\\?\`、`\\.\`、尾随反斜杠、空变量、`..`、`~`、`%WINDIR%`/`%SystemDrive%`/`%TEMP%`/`%LOCALAPPDATA%`）。
  结果清单：`/tmp/audit-del/sweep.json`、`sweep2.json`。
- `/tmp/audit-del/out`：转换产物（`.sh` 默认产物 + `.raw.sh` 关闭语法校验的产物）。
- 真跑：`/tmp/audit-del/rt/<case>/`（真文件、真副作用）+ 记录 `runtime{,2..7}.json`。
- 根锚定用例（产物指向 `/`）：**绝不在真机跑**，在 `bwrap` 假根（`--bind /tmp/audit-del/fakeroot /`，系统目录只读 bind）里跑，比对前后目录树；命令见 `run2.py`–`run7.py`。

---

## 2. 逐用例表

`产物(bash)` 列是默认产物的实际命令行（`set -euo pipefail` 略）；`⏎` 表示换行。等级为**该用例**的风险等级。

### 2.1 `\\?\` / `\\.\` 前缀类（本次最高等级来源之一）

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| rd /s /q | `rd /s /q \\?\C:\data` | `rm -rf \/?/C:/data` | `?` 成活通配符：实测**递归删掉 `/x/C:/data`、`/y/C:/data` 两个 bat 从未提及的目录** | **高** |
| del | `del \\?\C:\data` | `rm -f \/?/C:/data` | 同上（文件版）：实测删掉 `/x/C:/data`、`/y/C:/data` 两个文件 | **高** |
| del | `del \\?\C:\*\*.log` | `rm -f \/?/C:/*/*.log` | 实测删掉 `/q/C:/x/a.log`（`?`=`q`），`w/C:/a.log` 幸存 | **高** |
| del | `del \\?\%1\file.txt` | `rm -f \/?\${1:-}/file.txt` | `?` 活 + 变量被 `\$` 变成**字面量**：实测删掉 `q${1:-}/file.txt`、`z${1:-}/file.txt`；而实参 `target` 指向的 `q/target/file.txt` **幸存** | **高** |
| del | `del \\?\%DIR%\file.txt` | `rm -f \/?\${DIR}/file.txt` | `\$` 使变量名变字面量 ⇒ 静默删不到目标，同时 `?` 仍是活通配符 | 中 |
| del | `del \\.\C:\f.txt` | `rm -f "\\/./C:/f.txt"` | 加引号 → 字面反斜杠路径，删不到（欠删） | 低 |
| del | `del \\?\UNC\server\share\f.txt` | `rm -f \/?/UNC/server/share/f.txt` | 同 `\\?\` 类，实测路径不存在 → 目前删不到，但 `?` 仍是活通配符 | 中 |
| del /s /q | `DEL /F /A /Q \\?\%1`（v2.11.0 已知案例） | **整文件降级为注释**（`--no-bash-check` 原始产物：`rm -f "\"/?\${1:-}`） | 形态已变：不再产出 `rm -rf \/?/${1:-}`，但原始产物**引号不闭合** ⇒ 默认整文件降级（删除被静默跳过） | 中 |
| del /s /q | `del "\\?\%CD%\*.log"` | 整文件降级为注释（raw：`rm -f \/?\$(pwd)/*.log`） | 同上（引号不闭合 + `\$` 使 `$(pwd)` 变字面量） | 中 |

### 2.2 根锚定 / 空变量 ⇒ `rm -rf "/"`、`rm -rf "/"/*`、`rm -rf ""/*`

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| del /s /q | `del /s /q %WINDIR%\*` | `rm -rf "/"/*` | 实测：**假根下所有可写顶层条目（含 `data/d1/f.txt`）被递归删除**；GNU 对 `/*` **无** preserve-root 保护 | **高** |
| del /s /q | `del /s /q %SystemDrive%\*` | `rm -rf "/"/*` | 同上（`SYSTEMDRIVE:"/"`） | **高** |
| del /s /q | `del /s /q %DIR%\*`（DIR 未设） | `rm -rf "${DIR:-}"/*` → 运行期 `""/*` | 实测：同上，整根可写条目被删 | **高** |
| del /s /q | `del /s /q "%DIR%"\*`（DIR 未设） | `rm -rf ""${DIR:-}""/*` | 引号错位使 `${DIR:-}` 脱引号 → 实测整根被删 | **高** |
| del /s /q | `del /s /q %HOMEDRIVE%\*` | `rm -rf ""/*` | `HOMEDRIVE:""` → 头为空 ⇒ `""/*`，实测整根被删 | **高** |
| del /s | `del /s \*` | `rm -rf ""/*` | 实测整根被删（`\*`→`/*`，head 为空被拼成 `""`） | **高** |
| del /s /q | `del /s /q \*.*` | `rm -rf ""/*.*` | 同形态（根下带点条目） | 中 |
| rd /s /q | `rd /s /q \` | `rm -rf "/"` | 实测：GNU 拒删（`在 '/' 进行递归操作十分危险`）⇒ 真机无损失；但产物本身是"根递归删除" | **高**（构造）/ 中（GNU 实测后果） |
| del /s /q | `del /s /q %WINDIR%` | `rm -rf "/"` | 同上，但连"根下条目"都不需要 | 高 |
| rd /s /q | `rd /s /q %SystemDrive%` | `rm -rf "/"` | 同上 | 高 |
| del /s /q | `del /s /q "%TEMP%\*"` | `rm -rf "${TMPDIR:-/tmp}"/*` | 实测：删掉同机"其他用户"的 `other_user/payroll.xlsx` | 中 |
| rd /s /q | `rd /s /q "%TEMP%"` | `rm -rf "${TMPDIR:-/tmp}"` | 实测：整个 TMPDIR 树被删（宿主机 TMPDIR 未设时即 `rm -rf /tmp`） | 中 |
| rd /s /q | `rd /s /q %LOCALAPPDATA%` | `rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}"` | 删的是 XDG 数据目录（浏览器/应用数据） | 中 |
| del /s /q | `del /s /q %SystemRoot%\Temp\*` | `rm -rf "${SystemRoot:-/}/Temp"/*` | Linux 上 `SystemRoot` 恒未设 ⇒ `/Temp/*`（若存在则整删） | 中 |
| del /s /q | `del /s /q %1*`（无实参） | `rm -rf ${1:-}*` → `rm -rf *` | 实测：假根下所有条目（含子目录树）被删；cmd 的 `del` 不删目录 | 中 |
| del /s /q | `del /s /q %1*`（实参 `/`） | `rm -rf ${1:-}*` → `rm -rf /*` | 实测：假根被整体清空，且**无** preserve-root 保护（只需 1 个实参） | 中 |
| rd /s /q | `rd /s /q %1`（实参 `/`） | `rm -rf "${1:-}"` | 实测：GNU 拒删 → 真机无损失；非 GNU `rm` 未测 | 低 |
| del | `del %1`（无实参） | `rm -f "${1:-}"` | 实测：什么都没删（`rm -f ""` 静默成功）——**"空变量退化成 rm -rf /" 不成立** | 无 |
| rd /s /q | `rd /s /q %1`（实参 `~`，`HOME=/data`） | `rm -rf "${1:-}"` | 实测：`~` 被引号保护、未展开 → 未删 `$HOME`。**未发现 `rm -rf ~` / `$HOME` 构造** | 无 |
| rd /s /q | `rd /s /q ~` | `rm -rf "~"` | 同上（引号保护） | 无 |
| del | `del \` | `rm -f "/"` | 实测：`rm: 无法删除 '/': 是一个目录`（无 `-r`） | 无 |
| rd /s /q | `rd /s /q \\` | `rm -rf "\\/"` | 字面反斜杠路径，删不到 | 无 |

### 2.3 字面 `$`（变量展开 / 命令替换）

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| del | `del "a$b.txt"` | `rm -f "a$b.txt"` | 实测（`b=SECRET`）：删掉 **`aSECRET.txt`**，`a$b.txt` 幸存 ⇒ 误删 | **高** |
| del | `del "a$(touch PWNED).txt"` | `rm -f "a$(touch PWNED).txt"` | 实测：执行了 `touch`（生成 `PWNED`）并删掉 `a.txt` ⇒ 路径字面量可执行任意命令 | **高** |
| del | `del "C:\$Recycle.Bin\desktop.ini"` | `rm -f "C:\\$Recycle.Bin/desktop.ini"` | 实测：`set -u` 报 `Recycle: 未绑定的变量`，rc=1 ⇒ 整脚本中止（多行脚本会半途而废） | 中 |
| del | `del "C:\logs\app$HOME.log"` | `rm -f "C:/logs/app$HOME.log"` | `$HOME` 被展开 ⇒ 目标名改变 | 中 |
| del | `del "a%b%c.txt"` | `rm -f "a${b:-}c.txt"` | 同源（`%` 被当变量） | 低 |

### 2.4 引号丢失 / 词分割 / 通配符回退

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| del /s /q | `del /s /q "logs dir\*\*.log"` | `rm -rf logs dir/*/*.log` | 实测：**删掉 bat 从未提及的文件 `logs`**；意图目标 `logs dir/q/a.log` 幸存（`dir/x/a.log` 被误删同类） | **高**（误删） |
| del | `del "%1"\*.tmp`（实参 `my dir`） | `rm -f ""${1:-}""/*.tmp` | 实测：**删掉文件 `my`**；`my dir/x.tmp` 幸存 | **高**（误删） |
| del /f /s /q | `del /f /s /q %*`（实参 `"my dir"`） | `rm -rf $*` | 实测：删掉文件 `my` + 整个 `dir/` 树（含 `inner.txt`） | **高**（误删） |
| del /s /q | `del /s /q "C:\Program Files\*\*.log"` | `rm -rf C:/Program Files/*/*.log` | 含空格路径**整条脱引号** → 词分割（同上机制） | 中 |
| del | `del "C:\dir\*\*.txt"` | `rm -f C:/dir/*/*.txt` | 同上（无空格时仅欠删） | 中 |
| del | `del C:\my dir\file.txt` | `rm -f "C:/my" "dir/file.txt"` | 词分割，但 cmd 同样按空白切分 ⇒ 与源语义一致 | 无 |
| del /s /q | `del /s /q "%DIR%\*.tmp"` | `rm -rf "${DIR:-}"/*.tmp` | head 加引号正确 | 无 |
| del /s /q | `del /s /q "%~dp0*.tmp"` | `rm -rf "${SCRIPT_DIR}"/*.tmp` | 正确加引号 | 无 |
| del | `del "C:\我的 文档\*.txt"` | `rm -f "C:/我的 文档"/*.txt` | 实测：只删 `a.txt`，`b.log`/`sub/c.txt` 幸存 | 无 |

### 2.5 参数注入 / `rm` 选项

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| del /f /q | `del /f /q %1 %2`（实参 `-rf victim`） | `rm -f "${1:-}" "${2:-}"` | 实测：`victim/` 整树（含子目录/文件）被**递归**删除 ⇒ `rm` 选项注入 | 中 |
| del /s /q | `del /s /q %1 %2`（实参 `--no-preserve-root /`） | `rm -rf "${1:-}" "${2:-}"` | 实测：假根被整体清空（绕过 GNU preserve-root） | 中 |
| del /s /q | `del /s /q %1`（实参 `/`） | `rm -rf "${1:-}"` | GNU 拒删（真机无损失） | 低 |

### 2.6 `del /s` 语义放大（`rm -rf` 删目录）/ 其它

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| erase /s /q | `erase /s /q C:\temp\*` | `rm -rf "C:/temp"/*` | 实测：`C:/temp/sub/` 整个子目录（含文件）被删；cmd 的 `del /s` 不删目录 | 中 |
| del /s /q | `del /s /q ..\*`（cwd=`child`） | `rm -rf ".."/*` | 实测：父目录整树被删，连 cwd 自身 `child/` 也被删 ⇒ 越出工作目录 | 中 |
| del /s /q | `del /s /q *` | `rm -rf *` | cwd 内所有条目（含目录树）被删 | 中 |
| del /s /q | `del /s /q C:\logs\\*` | 整文件降级为注释（raw：`rm -rf "C:/logs\"/*`） | 引号不闭合 ⇒ `bash -n` 失败；坏产物在 `--no-bash-check`/无 `bash` 时会被写出 | 中 |
| del | `del ..\..\*.*` | `rm -f "../.."/*.*` | 相对上级路径，与 cmd 同向（欠删） | 低 |
| del | `del *.*` | `rm -f *.*` | bash 的 `*.*` 要求含点 ⇒ 无扩展名文件漏删（欠删，fails safe） | 低 |
| del | `del .` / `del ..` | `rm -f "."` / `rm -f ".."` | 实测：GNU 拒删 | 无 |
| del | `del ~/*` | `rm -f "~"/*` | `~` 加引号不展开 | 无 |

### 2.7 开关吞路径 / 未映射命令 / 交互语义

| 命令 | 输入(bat) | 产物(bash) | 风险 | 等级 |
| --- | --- | --- | --- | --- |
| rd | `rd /tmp` | `rmdir` | `/tmp` 被 `_split_switches` 当开关吞掉 ⇒ 目标丢失、bare `rmdir` 报错；`set -e` 下整脚本中止 | 低 |
| rd | `rd /etc` | `rmdir` | 同上（`/[a-z]{1,3}` 全匹配即吞） | 低 |
| rmdir /s /q | `rmdir /s /q /tmp` | `rm -rf` | 同上（bare `rm -rf` 报错，不删任何东西） | 低 |
| rd /s /q | `rd /s /q /a/b` | `rm -rf` | `/[a-z](/[a-z]{1,3})+` 命中 ⇒ 整条路径被吞 | 低 |
| del | `del /tmp/foo.txt` | `rm -f "/tmp/foo.txt"` | 首段 ≥4 字母 ⇒ 不误吞（边界已实测） | 无 |
| deltree | `deltree C:\temp` | `deltree C:/temp` | **未映射**，保留字面命令；运行期 command not found（`set -e` 下 rc=127 中止）；报告有"未知命令 'deltree'"警告 | 低 |
| deltree /y | `deltree /y C:\temp` | `deltree /y C:/temp` | 同上 | 低 |
| del /p | `del /p *.tmp` | `rm -f *.tmp` | `/p` 交互确认被丢弃 ⇒ 无提示直接删；报告警告"`del 开关 /p 未处理`" | 低 |
| del /a | `del /a /q C:\x.txt` | `rm -f "C:/x.txt"` | `/a`（属性过滤）丢弃，报告警告 | 低 |
| del /s /q | `del /s /q C:\Users\%USERNAME%\*` | `rm -rf "C:/Users/${USER:-}"/*` | 引号正确（`/s` 放大问题同 2.6） | 低 |
| del | `del %1` / `del "%1"`（无实参） | `rm -f "${1:-}"` | 实测无副作用 | 无 |
| del | `del "C:\my dir\file.txt"` | `rm -f "C:/my dir/file.txt"` | 实测：只删目标文件 | 无 |
| del | `del a[b].txt` / `del a;b.txt` / `del "a(b).txt"` / `del a`b.txt` / `del a!b.txt` / `del "a&b.txt"` | 分别 `rm -f "a[b].txt"` / `"a;b.txt"` / `"a(b).txt"` / `"a\`b.txt"` / `"a!b.txt"` / `"a&b.txt"` | 实测：只删同名文件（`ab.txt`/`b.txt`/`a` 幸存） | 无 |
| del | `del a\|b.txt` | `rm -f "a" \| b.txt` | 管道语义与 cmd 一致（忠实） | 无 |
| for | `for %%i in (*.tmp) do del %%i` | `shopt -s nullglob` ⏎ `for i in *.tmp; do rm -f "${i}"; done` | 循环变量带引号 | 无 |
| del | `del %TEMP%\*.tmp` | `rm -f "${TMPDIR:-/tmp}"/*.tmp` | 单文件级用法可接受 | 无 |
| del | `del D:\file.txt` | `rm -f "D:/file.txt"` | 盘符未映射 ⇒ 变成 cwd 下相对目录 `D:`（欠删） | 低 |

---

## 3. 详细分析

### F1（高）空/特殊环境变量 + `\*` ⇒ 根锚定 `rm -rf "/"/*` 或 `rm -rf ""/*`

**现象**：`del /s /q %WINDIR%\*`（或 `%SystemDrive%\*`、`del /s \*`、`del /s /q %DIR%\*` 且 DIR 未设）产出的 bash 是 `rm -rf "/"/*` 或 `rm -rf ""/*`——一个把**文件系统根下所有条目递归删除**的命令，且 GNU `rm` 的 `--preserve-root` 保护对这种形态**完全无效**（保护只针对字面操作数 `/`）。

**最小复现**
```bash
printf 'del /s /q %%WINDIR%%\\*\r\n' > /tmp/audit-del/cases/d02.bat
cd /home/duanjb666/bat2sh && PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/x.sh /tmp/audit-del/cases/d02.bat
grep '^rm' /tmp/x.sh      # → rm -rf "/"/*
```
（`%WINDIR%` 是**已定义**的 Windows 变量，`rules.py:240` 映射为 `/`，所以不需要任何"奇怪输入"。）

**根因 + 锚点**
1. `rules.py:238/240`（`SYSTEMDRIVE`/`WINDIR` → `"/"`）、`rules.py:224`（`HOMEDRIVE` → `""`）；`TEMP` → `${TMPDIR:-/tmp}`（225-226）。
2. `batch.py:1095` 把缺参/未设变量变成 `${VAR:-}`，**空展开后不设任何守卫**。
3. `utils.py:215-220`：`\` 后跟 `*`（`*` 在 `path_next` 集合里）被判为路径分隔符 ⇒ `\*` → `/*`；`\` 在末尾也变成 `/`（217-218）。
4. `batch.py:2222-2226`：通配符分支只按**最后一个 `/`** 切一刀；head 为空（`""/*`）或 head 为 `/`（`"/"/*`）时都直接返回，把"空展开 + 绝对根"变成 glob。

**实测后果**（`bwrap` 假根，`--bind fakeroot /`，系统目录只读 bind）
| 产物 | 假根变化 |
| --- | --- |
| `rm -rf "/"/*`（d02/d03/r13） | `data/`、`other.txt`、`art.sh`、`tmp/`、`run/` 全部被递归删除 |
| `rm -rf ""/*`（d07/r17） | 同上（`""/*` 与 `/*` 是同一个词） |
| `rm -rf "${DIR:-}"/*`（r12，DIR 未设） | 同上 |
| `rm -rf ""${DIR:-}""/*`（r32，DIR 未设） | 同上 |
| `rm -rf "/"`（d01/d04/d08/r22） | GNU 拒绝（`在 '/' 进行递归操作十分危险`，rc=1）⇒ 真机无损失；产物本身仍是"根递归删除" |

只读 bind 的 `/usr /lib /bin` 等幸存**只因为挂载只读**；真机上这些目录是可写的，会一并被删。

**补充**：`del %1` / `rd /s /q %1` 这类**无通配符**形态是**安全**的（`rm -f "${1:-}"`，实测无副作用）；危险只出现在"空展开 + `\*`/`\` 根锚定"与"引号错位"形态。

### F2（高）`\\?\` 前缀的 `?` 成为活通配符 —— v2.11.0 已知类**未真正消除**

**现象**：`\\?\` 是 Windows"关闭通配符解释"的扩展长度前缀；转换后前缀被拆成 `\/?/`，其中 `?` 在 bash 里是**活通配符**（匹配任意单字符），于是删除目标被放大到"根下任意单字符目录"。

**最小复现**
```bash
printf 'rd /s /q \\\\?\\C:\\data\r\n' > /tmp/audit-del/cases/c05.bat   # 源：rd /s /q \\?\C:\data
# 产物：rm -rf \/?/C:/data
mkdir -p /tmp/FR/{x,y}/C:/data && touch /tmp/FR/{x,y}/C:/data/inner.txt
bwrap --bind /tmp/FR / … bash /art.sh      # 见 /tmp/audit-del/run7.py
```
**实测后果**：`/x/C:/data`、`/y/C:/data` **两个 bat 从未提及的目录被递归删除**（`z/C:/other.txt` 幸存）。文件版（`del \\?\C:\data`）同样删掉 2 个文件；`del \\?\C:\*\*.log` 删掉 `/q/C:/x/a.log`。

**变量版更糟**：`del \\?\%1\file.txt` → `rm -f \/?\${1:-}/file.txt`——`\$` 把 `$` 转义成**字面量**，于是（a）实参 `$1` 完全失效（`q/target/file.txt` 幸存）；（b）删除目标变成"任意单字符 + 字面 `${1:-}`"的目录，实测 `q${1:-}/file.txt`、`z${1:-}/file.txt` **两个文件被删**。

**根因 + 锚点**
- `batch.py:2220-2226`：通配符分支只负责"head 加引号"，**从不判断 `?`/`*` 是不是来自"不该是通配符"的来源**（`\\?\`、`\\.\`、盘符、UNC）。
- `utils.py:169-170`（提交 `743abc1`，commit message 为"fix(F5): \ 后接变量展开时未转换为路径分隔符"）：该排除**只阻止了"反斜杠→斜杠"这一步**，注释里自己写明"`rm -rf \/?/` 会误删根下单字符目录……属'不做映射'，**维持既有行为**"。⇒ 风险被记录但未消除。
- `tests/test_batch_backslash_paths.py:120-128` 只断言 `\\?\%1` 这一形态（`"\\${1:-}" in out`），且用 `bash_check=False`、不做 `bash -n`；而 HEAD 该形态的原始产物是 `rm -f "\"/?\${1:-}`（**引号不闭合**），默认管线把**整文件**降级成注释（`syntax.py:71`）——测试通过 ≠ 产物可用。

### F3（高）字面 `$` 未转义 ⇒ 误删别的文件 + 命令替换执行

**现象**：`del "a$b.txt"` → `rm -f "a$b.txt"`；`del "a$(touch PWNED).txt"` → `rm -f "a$(touch PWNED).txt"`。

**最小复现（误删）**
```bash
printf 'del "a$b.txt"\r\n' > in.bat        # 产物 rm -f "a$b.txt"
mkdir -p /tmp/sb && cd /tmp/sb && touch 'a$b.txt' aSECRET.txt
b=SECRET bash /tmp/out.sh && ls      # → aSECRET.txt 被删，a$b.txt 幸存
```
**实测后果**
| 用例 | 结果 |
| --- | --- |
| `del "a$b.txt"`，`b=SECRET` | **删掉 `aSECRET.txt`**（bat 从未提及的文件），真目标幸存 |
| `del "a$(touch PWNED).txt"` | **执行 `touch` 生成 `PWNED`**，并删掉 `a.txt`（`$(…)` 输出为空 ⇒ 目标名被改写） |
| `del "C:\$Recycle.Bin\desktop.ini"` | `set -u` 报 `Recycle: 未绑定的变量`，rc=1 ⇒ 整脚本中止（多行脚本前半已执行、后半静默跳过） |

**根因 + 锚点**：`batch.py:2183-2215` `_dq_preserving_substitutions` 有意保留 `$(…)`/`${…}`（为变量展开服务），但它无法区分"生成器插入的替换"与"源里的字面 `$`"；`utils.py:26-29` 的 `dq()` 同样不转义 `$`。⇒ 路径字面量里的 `$` 一律被 bash 二次解释。

### F4（高）通配符回退在"中间路径段含通配符"时整条脱引号 ⇒ 词分割误删

**现象**：`del /s /q "logs dir\*\*.log"` → `rm -rf logs dir/*/*.log`（**整条没有任何引号**）。

**最小复现**
```bash
printf 'del /s /q "logs dir\\*\\*.log"\r\n' > in.bat
mkdir -p sb/'logs dir'/q sb/dir/x sb/logs && touch sb/logs sb/'logs dir'/q/a.log sb/dir/x/a.log
cd sb && bash /tmp/out.sh && ls     # → 文件 logs 与 dir/x/a.log 被删；logs dir/q/a.log 幸存
```
**根因 + 锚点**：`batch.py:2222-2226`——`rpartition("/")` 只把"最后一个 `/` 之前"当 head；当**中间段**含 `*`/`?` 时 `head_probe` 也含通配符，条件不成立就 `return converted`（**完全不加引号**）。同一行的 `f'"{head}"/{tail}'` 还会给**已经带引号**的 head 再套一层引号：`del "%1"\*.tmp` → `rm -f ""${1:-}""/*.tmp`，`${1:-}` 因此落在引号之外 ⇒ 词分割/通配（实测删掉文件 `my`；DIR 未设时退化成 `""/*` 并整根删除）。

### F5（中）targets 前缺 `--`：`rm` 选项注入

**现象/实测**：`del /f /q %1 %2` → `rm -f "${1:-}" "${2:-}"`；以 `-rf victim` 调用时，`victim/` **整树被递归删除**（实测含 `victim/deep/x.txt`）。以 `--no-preserve-root /` 调用时，假根被整体清空（实测），即绕过 GNU 根保护。cmd 侧 `del` 既不递归（无 `/s`）也不删目录，故这是**放大**而非等价。
**根因 + 锚点**：`batch.py:3424`、`3432` 直接 `" ".join(...)`，从未插入 `--`；变量即使加了引号也不能阻止 `-x` 被当作选项。

### F6（中）`%*` → 未加引号的 `$*`

**现象/实测**：`del /f /s /q %*` → `rm -rf $*`；以 `"my dir"` 调用时实测删掉文件 `my` 与整个 `dir/` 树。cmd 侧 `%*` 会保留实参原有的引号信息，bash 的 `$*` 丢失了这一点。
**根因 + 锚点**：`batch.py:1094`（`%*`→`$*`）+ `batch.py:2221-2226`（`$*` 含 `*` ⇒ 走通配符分支 ⇒ 不加引号）。

### F7（中）`del /s` 用 `rm -rf` 实现 ⇒ 删目录，超出 cmd 语义

**实测**：`erase /s /q C:\temp\*` → `rm -rf "C:/temp"/*` 删掉 `C:/temp/sub/`（整个子目录含文件）；`del /s /q ..\*` → `rm -rf ".."/*` 把父目录整树删掉（连 cwd 自身也被删）；`del /s /q *` → `rm -rf *` 同理。
**根因 + 锚点**：`batch.py:3423`（`/s` ⇒ `rm -rf`）。cmd 的 `del /s` 只删**文件**、保留目录骨架；`rm -rf` 连目录一起删。这条在"空变量/根锚定"叠加时就是 F1。

### F8（中）Windows 路径映射到共享/全局位置

`rules.py:225-226` `TEMP/TMP → ${TMPDIR:-/tmp}`：实测 `rd /s /q "%TEMP%"` 把整个 TMPDIR 树删掉；`del /s /q "%TEMP%\*"` 删掉了同机"其他用户"的文件。Windows 的 `%TEMP%` 是**每用户**目录，Linux 未设 `TMPDIR` 时 `/tmp` 是**全机共享**目录 ⇒ 越界删除。`LOCALAPPDATA → ${XDG_DATA_HOME:-$HOME/.local/share}`（242）同理删的是应用数据目录。属"映射口径"问题，报告里对应 `BATCH_ENV_WARN` **不含 TEMP/TMP**。

### F9（低）`_split_switches` 把 Linux 绝对路径当开关吞掉（fails safe）

`rd /tmp` → `rmdir`、`rd /etc` → `rmdir`、`rmdir /s /q /tmp` → `rm -rf`、`rd /s /q /a/b` → `rm -rf`（实测均为**不带操作数**的命令，rc≠0，不删任何东西）。危险方向是"静默不删 + `set -e` 中止后续命令"。锚点 `batch.py:3163/3166`；边界实测：首段 ≥4 字母（`/tmp/foo.txt`）不会被吞。

### F10（低）`deltree` 未映射、`/p` `/a` 被丢弃

`rules.py:57-60` 无 `deltree`；`deltree C:\temp` → 字面 `deltree C:/temp`，运行期 command not found（`set -e` 下 rc=127、脚本中止）。`--report` 会给出"未知命令 'deltree'"与"`del 开关 /p 未处理`"警告（实测报告：`错误 1 / 警告 4`）。风险是"破坏性动作静默丢失"和"交互确认被跳过"，不是误删。

### F11（低）引号闭合缺陷导致整文件降级为注释

`del /s /q C:\logs\\*` → 原始产物 `rm -rf "C:/logs\"/*`（head 以 `\` 结尾，`"` 被转义 ⇒ 引号不闭合）；`DEL /F /A /Q \\?\%1` → 原始产物 `rm -f "\"/?\${1:-}`（同源）。默认管线用 `bash -n` 兜住并**整文件**降级（`batch.py:581-586`、`syntax.py:71`），代价是**同一文件里所有其他删除也一并失效**（静默）。绕过路径：`--no-bash-check`；以及 `bash` 不在 PATH 时 `bash_syntax_error` 返回 `None`（`syntax.py:24-25`）⇒ 守护失效。锚点 `batch.py:2225`（手写 `f'"{head}"/{tail}'`，未用 `dq()`/`_dq_preserving_substitutions`）。

---

## 4. 结论与建议

### 真风险（有实测破坏性后果）

1. **F1（高）**：`%WINDIR%`/`%SystemDrive%`/空变量 + `\*`/`\` ⇒ `rm -rf "/"/*`、`rm -rf ""/*`。实测"假根所有可写顶层条目被递归删除"，且 `/*` 形态**不受** GNU preserve-root 保护。
2. **F2（高）**：`\\?\` 前缀的 `?` 活通配符：实测递归删掉 2 个 bat 从未提及的目录 / 删掉 2 个文件；变量版还会把 `$1` 变成字面量。
3. **F3（高）**：路径字面量里的 `$` 未转义 ⇒ 删错文件（`a$b.txt` → 删 `aSECRET.txt`）+ `$(…)` 命令执行。
4. **F4（高）**：中间段通配符 ⇒ 整条脱引号（实测删掉文件 `logs` / 文件 `my`）。
5. **F5、F6（中）**：缺 `--` 的选项注入（实测递归删目录、`--no-preserve-root /` 清空假根）；`%*` → `rm -rf $*` 词分割（实测删掉 `my` 与 `dir/` 树）。
6. **F7、F8（中）**：`del /s` → `rm -rf` 删目录；`%TEMP%` → `/tmp` 越界删除其他用户文件。

### 理论风险（可能成立但未取得破坏性实测）

- `rm -rf "/"`（F1 的 `"/"` 形态）：**GNU coreutils 9.11 实测拒绝**，真机无损失；但在 busybox/toybox/BSD/macOS 的 `rm` 上大概率直接执行——本机无这些 `rm`，**未实测**（见第 5 节）。
- `--no-preserve-root` 注入（F5）需要调用方传入特殊实参；已实测"注入确实生效"，但触发依赖实参内容。
- `/a` 属性过滤未实现导致的隐藏文件差异（Windows hidden vs Linux dotfile）未做行为对照。

### 建议（只给方向，本次不做修复）

1. 通配符"来源判定"：来自 `\\?\`、`\\.\`、盘符、UNC 前缀的 `?`/`*` **不得**作为活通配符（转义或整体 `--` + 引号）；只有源里**字面写出**的通配符才保留。
2. 空展开守卫：任何由变量展开得到的路径，若展开后为空/根，禁止直接拼进 `rm`（`[[ -n … ]] || exit`／显式 TODO 降级）。
3. 引号：通配符回退分支统一用 `dq()`/`_dq_preserving_substitutions` 的转义器（含 `$`），并按"最后一段通配符"定位 head，而不是"最后一个 `/`"。
4. 始终插入 `--`（`rm -f -- "${1:-}"`）。
5. `$` 与 `%`：字面 `$` 必须转义为 `\$`；只有生成器自己插入的 `${…}`/`$(…)` 才允许裸奔（给生成物打标记而不是"猜"）。
6. `del /s` 不要用 `rm -rf`；用 `find … -type f -delete` 之类保持"只删文件"语义。
7. `SYSTEMDRIVE`/`WINDIR` 映射为 `/`、`HOMEDRIVE` 映射为空串这两个映射建议改为"诚实 TODO"（映射到根是删除类命令的放大器）。
8. 降级粒度改为**逐行**（一行坏不应让整个脚本的删除全部静默失效）。

---

## 5. 未覆盖 / 存疑

1. **cmd.exe 侧语义未实测**（本机无 Windows）：第 3/4 节里"cmd 的 `del` 不删目录""`del /s` 只删文件""`*.*` 匹配所有""`/p` 会提示"属 cmd 已知语义，**不是本机实测**；因此"语义放大"的判定方向可信，倍数未量化。
2. **非 GNU `rm` 未实测**：busybox/toybox 未安装（`which busybox toybox` 失败）。所以 `rm -rf "/"` 在 busybox/BSD 上的"真删"结论是**推断**；GNU 下实测为拒绝。
3. **根锚定用例在 `bwrap` 假根中实测**：`/usr /lib /bin /sbin /etc` 是只读 bind 所以幸存；真机上它们可写。只验证了"所有可写顶层条目被递归删除"这一点。
4. **未跑测试套件**（只读审查，避免副作用）；只读了 `tests/test_batch_backslash_paths.py`、`tests/test_batch.py` 的相关断言。
5. 未覆盖：`del` 位于 `if/for` 块、`call` 函数体、`goto`/CFG 状态机（`cfg_state.py`）路径下的产物；`--fix-todos`/GUI/API 入口（`engine.convert_text` 与 CLI 共用 `convert()`，语法降级同样生效，但 `bash_check=False` 的调用方会拿到坏产物）。
6. 未测：符号链接（`rm -rf dir/*` 与 symlink 的交互）、只读/ACL/immutable 文件、`rm` 的 `-i` 别名环境（`alias rm='rm -i'` 不生效于脚本，未验证）、并发/竞态。
7. 共享 `/tmp` 越界删除用 sandbox 模拟 `TMPDIR`，未在多用户真机验证。
8. 未审计同样使用 `_convert_path_token` 的 `copy`/`move`/`xcopy`/`robocopy`/`type`/`dir` 等命令族——F3/F4/F5 的根因是**共用**的，缺陷可能外溢，本次只审删除类。
9. 只做了 120 个手工用例，**不是穷举/模糊测试**："未发现"≠"不存在"；尤其 `%VAR%` 组合、嵌套引号、`!` 延迟展开在块内的展开时机未系统覆盖。
10. `del /q %1` 类"引用已有语料库"的规模化扫描未做（本次全部为构造用例）。
