# 安全审查 —— for 循环体含删除

- 审查对象：`/home/duanjb666/bat2sh`，HEAD `70a0ddb`（v2.11.0 发布后 main tip）
- 审查日期口径：v2.11.0
- 结论一句话：**`for` 系列 + 循环体内删除存在 8 类可复现的破坏性缺陷（最高等级：高）**，其中
  `for /r … rd /s /q "%%i"` 会静默清空整个工作目录；`%%~n` 路径修饰符（v2.11.0 的 F3 只修了一半）
  会让人**递归删掉一个完全不相干的目录**。全部缺陷在 `--cli -q` 默认参数下**不产生任何警告或 TODO**。

---

## 1. 审查范围与方法

### 1.1 代码锚点（函数名 + 行号，均为 `python/bat2sh/core/batch.py`）

| 锚点 | 行号 | 职责 / 与本题的关系 |
| --- | --- | --- |
| `BatchConverter._convert_for` | 2232 | `for` 总入口；分派 `/f`(2247) `/r`(2250) `/l`(2257) `/d`(2265)；`/d` 在 2274–2277 给含通配符的元素**追加尾 `/`** |
| `BatchConverter._emit_for_r` | 2333 | `for /r` → `while read` + `find`。2346 只接受 `set == "."`；2352 拒绝含空白/通配的 root；**2374/2376 生成 `find "$PWD" -type d`（无 `-print0`）**；**2377 `while IFS= read -r <var>`** |
| `BatchConverter._emit_for_f` | 2440 | `for /f` → `while read`；**2606 `first_var = loop_vars[0]`**、**2618 `[ -z "${first_var}" ] && continue`**（只校验第一个 token 变量）；2619 `trim_var = loop_vars[-1]` |
| `BatchConverter._modifier` | 1233 | `%%~n`：1249–1250 → `$(basename "${v%.*}")`；`%%~nx`：1245–1246 → `$(basename "${v}")`；`%%~x`：1251–1252 → `$(echo ".${v##*.}")`；`%%~f`：1247–1248 → `$(readlink -f "…")`；**无 `n` 的 `d/p` 落到 1253 → 原样 `${v}`** |
| `BatchConverter._convert_path_token` | 2217 | 删除目标引号化。**2220–2226：token 含 `*`/`?` 时返回未加引号的 `converted`（或 `"head"/tail`）** |
| `BatchConverter._convert_for_set` | 2722 | 集合 token 化；2725 把 `,`/`;` 重写成空格 |
| `BatchConverter._quote_collection_token` | 2735 | 纯变量集合强制加引号 → `for i in "${FILES}"` |
| `BatchConverter._note_glob` / `utils.needs_nullglob` | 2764 / `utils.py:370` | 只在引号外发现 `*`/`?` 时才 `shopt -s nullglob` 并告警（**不认 `[...]`**） |
| `BatchConverter._guard_unset_variable_refs` | 705 | 给"未见赋值"的变量引用注入 `:-`（`${FILES}` → `${FILES:-}`） |
| `BatchConverter.cmd_del` | 3419 | `del` → `rm -f`（带 `/s` → `rm -rf`），3424 逐 token 走 `_convert_path_token` |
| `BatchConverter.cmd_rmdir` | 3427 | `rd`/`rmdir` → `rm -rf`（带 `/s`）/ `rmdir`，3432 同上 |
| `BatchConverter.cmd_cd` | 3393 | 循环体内 `cd` 会持久化 |
| `BatchConverter._convert_call` / `_label_line` | 1781 / 1703 | `call :label` → `if declare -F label_x; then label_x …`；标签体在"未使用"时仍落到顶层 |

### 1.2 CLI 调用方式（一律使用仓库源码，未使用 `/usr/bin/bat2sh`）

```bash
cd /home/duanjb666/bat2sh
PYTHONPATH=python python3 -m bat2sh --cli -q -o /tmp/audit-for/out/<case>.sh /tmp/audit-for/cases/<case>.bat
bash -n /tmp/audit-for/out/<case>.sh
```

### 1.3 实验目录与可复现资产

- 用例源文件：`/tmp/audit-for/cases/`（76 个 `.bat`，CRLF，`/tmp/audit-for/gen_cases.py` 生成）
- 产物与 `bash -n` 记录：`/tmp/audit-for/out/`、`/tmp/audit-for/results/`（`/tmp/audit-for/run_all.sh` 一键重跑）
- 真实副作用沙箱：`/tmp/audit-for/sandbox/s<用例号>/`（每个用例独立目录，先 `find` 快照 → 执行 → 再 `find` 对比）
- **76/76 用例产物均通过 `bash -n`**（即"语法合法但语义危险"），因此本报告的所有风险都不是语法问题
- 审查期间未修改仓库任何文件（本次审查唯一的写入是本报告），未做任何 `git commit`

### 1.4 版本口径与"原始 HEAD"复核（重要）

审查进行中，**同一 checkout 里有并行会话改动了工作区**（`git status` 出现 `M python/bat2sh/core/batch.py` 等；本次审查自身未触碰这些文件）。
为排除"我的实测是在打过补丁的转换器上跑的"这一污染，全部结论都做了如下复核：

1. **锚点**：本报告所有行号均取自 `git show HEAD:python/bat2sh/core/batch.py`（`70a0ddb`），已逐条比对通过。
2. **产物**：用 `git archive HEAD | tar -x -C /tmp/audit-for/pristine` 取**原始 HEAD** 副本，把 76 个用例全部重新转换，
   与审查期间的产物**逐字节相同**（唯一"差异"是我把 `c79` 存成了 `out/c79.sh` 这个文件名差异）。
3. **副作用**：用原始 HEAD 的产物在全新沙箱重跑全部破坏性实验，**14/14 全部复现，2/2 对照组符合预期**（脚本 `/tmp/audit-for/reverify_effects.sh`，输出 16/16 REPRODUCED）。

**并行会话的未提交改动覆盖到哪里**（供读者判断"哪些已经不用再修"）：该改动只把 `_modifier` 的 `%%~n` 从 `$(basename "${v%.*}")`
改成"先取 basename 再剥扩展名"（`batch.py:1250` 与 `batch.py:1265`），因此

- **G2 已被该未提交改动修掉**（工作区版对 `c87` 产出 `rm -rf "$(<basename>)"`，实测删的是 CWD 下的同名目标，不再误删不相干目录）；
- **其余 7 类（G1/G3/G4/G5/G6/G7/G8）不受影响**：`c02`/`c97`/`c85`/`c03`/`c59`/`c96` 的工作区产物与原始 HEAD **逐字节相同**；
- G4 在打过补丁的版本上**依然成立**（实测：`rm -f $(__bat2sh_b=…).*` 仍被词分割，`my file.txt` 场景下仍删掉无关的 `my` 与 `file.txt`）。

---

## 2. 逐用例表

`IN` = 源 `.bat` 的 `@echo off` 之后的行；`OUT` = 产物关键行（省略脚本头、`set -euo pipefail`、nullglob 告警注释）。
等级口径：**高** = 有可复现的破坏性后果（误删真实文件 / 递归删错目录 / 删掉循环变量自身）；**中** = 会做错事但需附加条件，或只是行为分歧；**低** = 语义偏差、无实测数据损失；**无** = 未发现不安全产物。

| # | 用例 | 命令 | 产物 | 等级 |
| --- | --- | --- | --- | --- |
| 1 | `c01_for_glob_del` | `for %%i in (*.tmp) do del "%%i"` | `for i in *.tmp; do rm -f "${i}"; done`（+nullglob） | 无 |
| 2 | `c02_forr_rd` | `for /r %%i in (.) do rd /s /q "%%i"` | `while IFS= read -r i; do rm -rf "${i:-}"; done < <(find "$PWD" -type d)` | **高** |
| 3 | `c03_ford_rd` | `for /d %%d in (*) do rd /s /q "%%d"` | `for d in */; do rm -rf "${d}"; done` | **高** |
| 4 | `c04_forf_del` | `for /f %%i in (list.txt) do del "%%i"` | `if [ -r "list.txt" ]; then while read -r i _; do i="${i%$'\r'}"; [ -z "$i" ] && continue; rm -f "${i}"; done < "list.txt"; fi` | 无 |
| 5 | `c05_mod_n` | `for %%i in (*.tmp) do del "%%~ni"` | `rm -f "$(basename "${i%.*}")"` | 低（与 cmd 同） |
| 6 | `c06_mod_nx` | `for %%i in (*.tmp) do del "%%~nxi"` | `rm -f "$(basename "${i}")"` | 无 |
| 7 | `c07_mod_f` | `for %%i in (*.tmp) do del "%%~fi"` | `rm -f "$(readlink -f "${i}")"` | 无 |
| 8 | `c08_mod_dp` | `for %%i in (*.tmp) do del "%%~dpi%%~nxi"` | `rm -f "${i}$(basename "${i}")"` | 中 |
| 9 | `c09_mod_dp_only` | `for %%i in (*.tmp) do rd /s /q "%%~dpi"` | `rm -rf "${i}"` | 中 |
| 10 | `c10_mod_x` | `for %%i in (*) do del "%%~xi"` | `rm -f "$(echo ".${i##*.}")"` | 低 |
| 11 | `c11_ford_mod_n` | `for /d %%d in (*) do del "%%~nd"` | `rm -f "$(basename "${d%.*}")"` | 低（与 cmd 同） |
| 12 | `c12_ford_mod_nx` | `for /d %%d in (*) do del "%%~nxd"` | `rm -f "$(basename "${d}")"` | 无 |
| 13 | `c13_mod_n_glob` | `for %%i in (*.txt) do del "%%~ni.*"` | **`rm -f $(basename "${i%.*}").*`**（未加引号） | **高** |
| 14 | `c14_mod_n_glob2` | `for %%i in (*.txt) do del "%%~ni*"` | **`rm -f $(basename "${i%.*}")*`** | **高** |
| 15 | `c15_forr_mod_n` | `for /r %%i in (.) do del "%%~ni"` | `rm -f "$(basename "${i%.*}")"` | **高** |
| 16 | `c16_forr_mod_nx` | `for /r %%i in (.) do del "%%~nxi"` | `rm -f "$(basename "${i:-}")"` | 无 |
| 17 | `c20_unquoted_del` | `for %%i in (*.tmp) do del %%i` | `rm -f "${i}"`（仍被加引号） | 无 |
| 18 | `c21_unquoted_forf` | `for /f %%i in (list.txt) do del %%i` | `rm -f "${i}"` | 无 |
| 19 | `c22_unquoted_rd` | `for /d %%d in (*) do rd /s /q %%d` | `rm -rf "${d}"` | 无 |
| 20 | `c30_var_collection` | `for %%i in (%FILES%) do del "%%i"` | `for i in "${FILES:-}"; do rm -f "${i}"; done` | 低 |
| 21 | `c31_var_collection_rd` | `for %%i in (%DIRS%) do rd /s /q "%%i"` | `for i in "${DIRS:-}"; do rm -rf "${i}"; done` | 低 |
| 22 | `c32_empty_paren` | `for %%i in () do del "%%i"` | `for i in ; do rm -f "${i}"; done`（0 次迭代） | 无 |
| 23 | `c33_arg_collection` | `for %%i in (%*) do del "%%i"` | `for i in "$@"; do rm -f "${i}"; done` | 低 |
| 24 | `c34_unset_var_del` | `del "%NOPE%"` | `rm -f "${NOPE:-}"` | 无 |
| 25 | `c40_forf_dir_b` | `for /f %%i in ('dir /b *.tmp') do del "%%i"` | `while read -r i _; … rm -f "${i}" ; done < <(compgen -G "*.tmp" \|\| true)` | 无 |
| 26 | `c41_forf_delims` | `for /f "delims=" %%i in (list.txt) do rd /s /q "%%i"` | `while IFS= read -r i _; … rm -rf "${i}"` | 中 |
| 27 | `c42_forf_tokens` | `for /f "tokens=1,2" %%i in (list.txt) do del "%%i %%j"` | `rm -f "${i} ${j}"` | 无 |
| 28 | `c43_forf_skip` | `for /f "skip=1" %%i in (list.txt) do del "%%i"` | `done < <(tail -n +2 < "list.txt")` + `rm -f "${i}"` | 无 |
| 29 | `c44_forf_pipe` | `for /f %%i in ('type list.txt ^\| findstr tmp') do del "%%i"` | `done < <(cat list.txt \| grep tmp)` + `rm -f "${i}"` | 无 |
| 30 | `c45_forf_string` | `for /f %%i in ("a.tmp b.tmp") do del "%%i"` | `done <<< "a.tmp b.tmp"` + `rm -f "${i}"` | 无 |
| 31 | `c46_forf_usebackq` | `for /f "usebackq" %%i in (\`list.txt\`) do del "%%i"` | 整行 TODO | 无 |
| 32 | `c50_space_set` | `for %%i in ("a b.tmp") do del "%%i"` | `for i in "a b.tmp"; do rm -f "${i}"` | 无 |
| 33 | `c51_space_glob` | `for %%i in (*.tmp) do del "%%~ni copy.txt"` | `rm -f "$(basename "${i%.*}") copy.txt"` | 无 |
| 34 | `c52_cn` | `for %%i in (中文*.tmp) do del "%%i"` | `for i in 中文*.tmp; do rm -f "${i}"` | 无 |
| 35 | `c53_dollar` | `for %%i in (*.tmp) do del "$%%i"` | `rm -f "$${i}"`（`$$`=PID） | 低 |
| 36 | `c54_backtick` | `for %%i in (*.tmp) do del "\`%%i\`"` | `rm -f "\`${i}\`"`（已转义） | 无 |
| 37 | `c55_semicolon` | `for %%i in (a.tmp;b.tmp) do del "%%i"` | `for i in a.tmp b.tmp; do rm -f "${i}"` | 无 |
| 38 | `c56_amp` | `for %%i in (a.tmp) do del "%%i" & echo done` | `for i in a.tmp; do rm -f "${i}"; echo "done"; done` | 无 |
| 39 | `c57_pipe_body` | `for %%i in (*.tmp) do del "%%i" \| echo x` | `rm -f "${i}" \| echo "x"` | 无 |
| 40 | `c58_paren_name` | `for %%i in ("(x).tmp") do del "%%i"` | `for i in "(x).tmp"; do rm -f "${i}"` | 无 |
| 41 | `c59_bracket` | `for %%i in (a[1].tmp) do del "%%i"` | `for i in a[1].tmp; do rm -f "${i}"` | **高** |
| 42 | `c60_bang` | `for %%i in (a!.tmp) do del "%%i"` | `for i in a!.tmp; do rm -f "${i}"` | 无 |
| 43 | `c61_question` | `for %%i in (?) do del "%%i"` | `for i in ?; do rm -f "${i}"`（+nullglob） | 低（与 cmd 同） |
| 44 | `c62_star_only` | `for %%i in (*) do del "%%i"` | `for i in *; do rm -f "${i}"`（+nullglob） | 无 |
| 45 | `c63_drive_unc` | `for %%i in (\\?\C:\tmp\*.tmp) do del "%%i"` | `for i in \/?/C:/tmp/*.tmp; do rm -f "${i}"`（`?` 活通配） | 中 |
| 46 | `c64_single_quote` | `for %%i in ('a.tmp') do del "%%i"` | `for i in 'a.tmp'; do rm -f "${i}"` | 无 |
| 47 | `c66_brace` | `for %%i in (file{1,2}.tmp) do del "%%i"` | `for i in file{1 2}.tmp; do rm -f "${i}"`（`,`→空格，拆成两个幻影名） | 低 |
| 48 | `c67_tokens2_glob` | `for /f "tokens=2" %%i in (list.txt) do del "%%i\*.tmp"` | `while read -r _ i _; … rm -f "${i}"/*.tmp`（有 `-z` 守卫） | 无 |
| 49 | `c68_tokens2_rd` | `for /f "tokens=2" %%i in (list.txt) do rd /s /q "%%i"` | `rm -rf "${i}"`（有守卫） | 无 |
| 50 | `c69_tokens2_del` | `for /f "tokens=2" %%i in (list.txt) do del "%%i"` | `rm -f "${i}"`（有守卫） | 无 |
| 51 | `c70_cd_then_del` | `for %%i in (*.tmp) do (cd sub & del "%%i")` | `cd "sub"` + `rm -f "${i}"` | 中 |
| 52 | `c71_cd_then_del_and` | `for %%i in (*.tmp) do (cd sub && del "%%i")` | `cd "sub" && rm -f "${i}"` | 中 |
| 53 | `c72_pushd_del` | `for %%i in (*.tmp) do (pushd sub & del "%%i" & popd)` | `pushd sub` / `rm -f "${i}"` / `popd` | 低 |
| 54 | `c73_cd_block` | `for /d %%d in (*) do (cd "%%d" & del "*.tmp")` | `for d in */; do cd "${d}"; rm -f *.tmp; done` | 中 |
| 55 | `c74_forf_del_after_cd` | `for /f %%i in (list.txt) do (cd sub & del "%%i")` | `cd "sub"` + `rm -f "${i}"` | 中 |
| 56 | `c75_cd_sub_bare` | `for /d %%d in (*) do cd "%%d"` ⏎ `del "*.tmp"` | `for d in */; do cd "${d}"; done` + `rm -f *.tmp` | 中 |
| 57 | `c76_ford_rd_mod_n` | `for /d %%d in (*) do rd /s /q "%%~nd"` | `rm -rf "$(basename "${d%.*}")"` | 低（与 cmd 同） |
| 58 | `c77_forr_n_dotted` | `for /r %%i in (.) do del "%%~ni.tmp"` | `rm -f "$(basename "${i%.*}").tmp"` | **高**（同 #15，见 3.2） |
| 59 | `c78_del_abs_glob` | `for /f %%i in (list.txt) do del "%%i\*"` | `rm -f "${i}"/*` | 中 |
| 60 | `c80_forr_var_root` | `for /r %ROOT% %%i in (.) do rd /s /q "%%i"` | `done < <(cd "${ROOT:-.}" && find "$PWD" -type d)` + `rm -rf "${i:-}"` | **高** |
| 61 | `c81_forr_glob_root` | `for /r *.dir %%i in (.) do rd /s /q "%%i"` | 整行 TODO | 无 |
| 62 | `c82_forr_file_set` | `for /r %%i in (*.tmp) do del "%%i"` | 整行 TODO | 无 |
| 63 | `c83_forr_root_dot_slash` | `for /r . %%i in (.) do rd /s /q "%%i"` | 同 #2 | **高** |
| 64 | `c84_forr_goto` | `for /r %%i in (.) do (rd /s /q "%%i" & goto :eof)` | 整行 TODO | 无 |
| 65 | `c85_forr_del_files` | `for /r %%i in (.) do del "%%i\*.tmp"` | `rm -f "${i:-}"/*.tmp` + `find "$PWD" -type d` | **高** |
| 66 | `c86_forr_rd_mod_f` | `for /r %%i in (.) do rd /s /q "%%~fi"` | `rm -rf "$(readlink -f "${i:-}")"` | **高** |
| 67 | `c87_forr_rd_dot` | `for /r %%i in (.) do rd /s /q "%%~ni"` | `rm -rf "$(basename "${i%.*}")"` | **高** |
| 68 | `c90_setlocal_del` | `setlocal enabledelayedexpansion` + `del "!i!"` | `rm -f "${i}"` | 无 |
| 69 | `c91_call_del` | `for %%i in (*.tmp) do call :kill "%%i"` ⏎ `:kill` ⏎ `del %1` | 循环内 `if declare -F label_kill …`；顶层多出 **`rm -f "${1:-}"`** | **高**（越界发现，见 3.8） |
| 70 | `c95_nested` | `for /d %%d in (*) do for %%f in ("%%d\*.tmp") do del "%%f"` | `bash -n` 失败 → 整脚本降级为注释 | 无 |
| 71 | `c96_tok2_j` | `for /f "tokens=1,2" %%i in (list.txt) do del "%%j\*"` | `rm -f "${j}"/*`（守卫只看 `i`） | **高** |
| 72 | `c97_emptyvar_glob` | `for %%i in (%FILES%) do del "%%i\*"` | `for i in "${FILES:-}"; do rm -f "${i}"/*; done` | **高** |
| 73 | `c98_forr_root_newline` | `for /r build %%i in (.) do del "%%i\*.tmp"` | `rm -f "${i:-}"/*.tmp` + `find "$PWD" -type d` | **高** |
| 74 | `c99_f3` | `for /r %%i in (.) do (cd.>"%%i\%%~ni.txt")` | `cd "." >"${i:-}/$(basename "${i%.*}").txt"` | 中（F3 未修全的写入面；同根因见 3.2） |
| 75 | `c92_call_kill` | 同 #69 | 同 #69 | **高** |
| 76 | `c79_forr_del_star`（补测，为隔离 G5 的 `..` 碎片路径而加） | `for /r %%i in (.) do del "%%i\*"` | `rm -f "${i:-}"/*` + `find "$PWD" -type d` | 中（同 G5，但被 `set -e` 意外挡住，见 3.5） |

`bash -n`：76/76 全部通过（#70 是转换器主动降级，产物本身也是合法注释）。

---

## 3. 详细分析

> 每个小节格式：**现象 → 最小复现 → 根因 + 代码锚点 → 实测后果**。
> "cmd 侧"结论凡是本机无法执行 `cmd.exe` 验证的，均显式标注 **[cmd 侧未实测]**。

### 3.1 【高】G1：`for /r … rd /s /q "%%i"` 清空整个工作目录（含脚本自身）

**现象**：`for /r %%i in (.) do rd /s /q "%%i"` 的产物把 `find "$PWD" -type d` 的**第一个值（= 工作目录自身）**交给 `rm -rf`，于是第一次迭代就把整棵树（含正在运行的脚本）删掉。

```
while IFS= read -r i; do
    rm -rf "${i:-}"
done < <(find "$PWD" -type d)
```

**最小复现**（`/tmp/audit-for/sandbox/s02`，用例 `c02_forr_rd`）：

```
BEFORE: s02/  s02/run.sh  s02/sub1/a.txt  s02/sub2/deep/b.txt  s02/top.txt
$ bash ./run.sh ; echo rc=$?
rc=0
AFTER : /tmp/audit-for/sandbox/s02 不存在（整个目录连同 run.sh 被删）
```

**根因 + 锚点**：`_emit_for_r`（`batch.py:2333`）只接受 `in (.)`（2346），root 为空时按 cmd 语义取当前目录；2374 生成 `find "$PWD" -type d`，其值域**包含根目录自身**（这与 cmd `for /r %%i in (.)` 一致），但产物没有任何"不要删除工作目录 / 正在被遍历的树"的守卫。`cmd_rmdir`（`batch.py:3427`）对 `/s /q` 直接产出 `rm -rf`。

**为什么 GNU rm 的 `.`/`..` 保护救不了**：实测 `rm -rf "."` 会被拒绝（`rm: 拒绝删除 '.' 或 '..' 目录：跳过 '.'`，rc=1，见 3.11 的 `c41` 实验），但 `for /r` 的值是**绝对路径**（v2.11.0 为修 F3 特意改成 `find "$PWD"`，见 `batch.py:2363-2372` 的注释与 `tests/test_batch_for_r.py:57-75`），因此该保护完全不生效。

**实测后果**：整棵目录树被递归删除、**脚本自身被删除**、`rc=0` 无任何报错。若该脚本被从 `$HOME`、项目根或数据目录调用（`cd <dir> && ./convert.sh`），后果是同等规模的数据损失。
**cmd 侧未实测**：cmd 中 `rd /s /q <当前工作目录>` 会因目录被占用而失败，因此 cmd 至多删除子目录、不会删掉工作目录本身；此判断未在本机执行验证，但即便不打这条折扣，产物本身"静默删掉运行目录"也已构成高等级风险。

**同根因变体（全部实测产物同形）**：`c80`（`for /r %ROOT%`，`ROOT` 未设置时 `:-.` 兜底成当前目录）、`c83`（`for /r .`）、`c86`（`rd /s /q "%%~fi"` → `rm -rf "$(readlink -f …)"`，`readlink -f` 仍解析出绝对路径）。

**补充实测（遍历与删除时机，回答"会不会删掉正在遍历的目录"）**：

```
$ while IFS= read -r i; do echo "ITER <$i>"; rm -rf "$i"; done < <(find "$PWD" -type d)
ITER <…/s02t>            ← 第一次迭代就删掉了根
ITER <…/s02t/d>  <…/s02t/d/e>  <…/s02t/d/e/f>  <…/s02t/b>  <…/s02t/b/c>  <…/s02t/a>
rc=0
```

即 `find` 因为已经持有已打开目录的 fd，**删掉根之后仍会把 7 个值全部吐完**，不存在"遍历中断从而误删"的额外路径；净效果就是"全部删光 + rc=0"。`< <(find …)` 进程替换在子壳里跑，`cd` 不污染主壳（`batch.py:2363-2366` 的注释成立）。

---

### 3.2 【高】G2：`%%~n` 的 F3 修复只覆盖"路径里没有点"的情形 ⇒ 删错文件 / 递归删错目录

**现象**：`%%~n` 被映射成 `$(basename "${v%.*}")`。`${v%.*}` 是从**整串**最后一个 `.` 处截断，而不是从 **basename** 的最后一个 `.` 处截断。只要最后一个路径分隔符出现在最后一个 `.` 之后（= 祖先目录名里有点），`%%~n` 就会静默给出另一个名字，而这个名字被直接当作删除目标。

**映射正确性边界（逐值实测，`$${v%.*}` 与 cmd `%~n` 对照）**：

| 循环值 `v` | `${v%.*}` | basename → 产物 `%%~n` | cmd `%~n` | 判定 |
| --- | --- | --- | --- | --- |
| `my.dir/`（`for /d` 值） | `my` | `my` | `my` | 一致 |
| `sub/` | `sub/` | `sub` | `sub` | 一致 |
| `my.dir.old/` | `my.dir` | `my.dir` | `my.dir` | 一致 |
| `a.tmp` | `a` | `a` | `a` | 一致 |
| `/tmp/x/samples` | `/tmp/x/samples` | `samples` | `samples` | 一致（F3 单测覆盖的就是这一档） |
| **`/tmp/x.v1/samples`** | **`/tmp/x`** | **`x`** | `samples` | **不一致** |
| **`/tmp/x.v1/sub1`** | **`/tmp/x`** | **`x`** | `sub1` | **不一致** |

**最小复现 A（删错文件，实测）**：用例 `c15_forr_mod_n`，在路径含点的目录里运行

```
$ pwd → /tmp/audit-for/sandbox/s15c/root.v1        (祖先目录名 root.v1 含点)
BEFORE: ./root(无关文件)  ./run.sh  ./sub1/keep.txt
$ bash ./run.sh ; echo rc=$?
rc=0
AFTER : ./run.sh  ./sub1/keep.txt      ← 无关文件 root 被删；真正的目标一个没动
```

**最小复现 B（递归删错目录，实测，最严重）**：用例 `c87_forr_rd_dot`
`for /r %%i in (.) do rd /s /q "%%~ni"` → `rm -rf "$(basename "${i%.*}")"`

```
$ pwd → /tmp/audit-for/sandbox/s15b/root.v1
BEFORE: ./root.v1  ./root.v1/root/data.txt("PRECIOUS-DATA")  ./root.v1/sub1  ./run.sh
$ bash ../run.sh ; echo rc=$?
rc=0
AFTER : ./root.v1  ./root.v1/sub1  ./run.sh      ← root.v1/root 连同 data.txt 被递归删除
```

**最小复现 C（F3 自身的回归证明，实测）**：用例 `c99_f3`，源 `for /r %%i in (.) do (cd.>"%%i\%%~ni.txt")`

```
A) 路径无点：…/f3clean/samples   → 生成 samples.txt          （= tests/test_batch_for_r.py:57 断言的行为）
B) 同脚本、祖先目录叫 f3.v2：…/f3.v2/samples
   → 生成的是 samples/f3.txt（应为 samples/samples.txt）     ← F3 未修全
```

**根因 + 锚点**：`_modifier` 的 `%%~n` 分支（`batch.py:1249-1250`）用 `basename "${v%.*}"`；F3 的修复手段（`_emit_for_r` 产出绝对路径，`batch.py:2363-2376`）只解决了"值带前导 `./` 导致 `%%~n` 变空"，没有解决"截断按整串最后一个点"这一层。`tests/test_batch_for_r.py:63` 用的 `tmp_path/"samples"` 恰好不含点，因此单测通过而真实点目录路径失败。

**实测后果**：把 `%%~n` 用作删除目标时，删掉的是**同名的、完全不相干的**文件；用 `rd /s /q` 时是**递归删除一个不该动的目录**。这满足"高"的判据（误删 / 递归删错目录）。
**说明**：`for /d` 档（`my.dir/` → `my`）与 cmd `%~n` **一致**，属继承自源脚本的固有陷阱，不计入本缺陷（用例 #11/#57/#76 记为"低（与 cmd 同）"）。

---

### 3.3 【高】G3：循环变量为空 + 通配尾巴 ⇒ 通配被锚定到文件系统根 `/`

**现象**：两个机制叠加——(a) `_quote_collection_token` 给纯变量集合加引号，`_guard_unset_variable_refs` 再补 `:-`，于是"集合为空"从 **0 次迭代**变成 **1 次空值迭代**；(b) `_convert_path_token` 在 token 含 `*`/`?` 时把通配符放在引号**外**。空值 + 引号外的 `/*` ⇒ 词变成 `/*`，glob 到根目录全部条目。

**最小复现 A（空变量集合，实测）**：用例 `c97_emptyvar_glob`

```
IN : for %%i in (%FILES%) do del "%%i\*"
OUT: for i in "${FILES:-}"; do
         rm -f "${i}"/*
     done
$ env -u FILES bash <(sed 's/rm -f/printf "ARG <%s>\n"/' out/c97_emptyvar_glob.sh )   # 只把 rm 换成打印，参数文本完全不变
ARG </bin>  ARG </boot>  ARG </dev>  ARG </etc>  ARG </home>  ARG </lib>  ARG </lib64>
ARG </mnt>  ARG </nix>  ARG </opt>  ARG </proc> ARG </root> ARG </run>  ARG </sbin>
ARG </srv>  ARG </sys>  ARG </tmp>  ARG </usr>  ARG </var>
```

即若按原样执行，`rm -f` 收到的操作数是**根目录下的全部条目**（`-f` 不提示、不因目录报错而停）。`/` 自身被 GNU rm 保护（"it is dangerous to operate recursively on '/'"），但根下的**普通文件**（如 `/swapfile`、`/vmlinuz`、`/initrd.img`）会被静默删除。
**发散性**：cmd 侧 `for %i in (%FILES%)` 在 `FILES` 未定义时集合为空 ⇒ **0 次迭代**（对照组：用例 `c32` 的字面空集合被正确转成 `for i in ; do`，0 次迭代）。因此这一条是**纯映射缺陷**，不是继承风险。

**最小复现 B（`for /f` 的非首 token 为空，实测）**：用例 `c96_tok2_j`

```
IN : for /f "tokens=1,2" %%i in (list.txt) do del "%%j\*"
OUT: while read -r i j _; do
         j="${j%$'\r'}"
         [ -z "$i" ] && continue          ← 守卫只检查 loop_vars[0]（= i）
         rm -f "${j}"/*
     done < "list.txt"
list.txt 第一行 "onlyonefield" ⇒ j 为空 ⇒ 参数展开为 /bin /boot … /var（printf 替身实测，同上）
```

**根因 + 锚点**：`_quote_collection_token`（`batch.py:2735-2748`）+ `_guard_unset_variable_refs`（`batch.py:705-735`）让空集合产生一个空词；`_convert_path_token`（`batch.py:2220-2226`）在探测到通配符时返回未加引号的 `converted`，把 `*` 留在引号外；`_emit_for_f` 的守卫只取 `first_var = loop_vars[0]`（`batch.py:2606`）并只校验它（`batch.py:2618`），其余 token 变量可以为空。三者叠加 ⇒ 根锚定 glob。

**实测后果**：删除目标集合从"某个目录下的一批文件"逃逸为"文件系统根下的全部条目"。本机用 `printf` 替身验证参数展开，未对 `/` 真正执行 `rm`（避免自毁），但展开结果本身即破坏性后果的直接证据。
**cmd 侧未实测**：`del "\*"` 在 cmd 中会触发通配删除的 `Are you sure (Y/N)?` 确认，而 `rm -f` 无任何确认，因此即便 cmd 侧同样危险，产物在**非交互脚本中的实际破坏力更高**。

---

### 3.4 【高】G4：未加引号的 `$( … )` + 通配 ⇒ 命令替换被再次词分割，删错文件

**现象**：`del "%%~ni.*"` 的 token 含 `*`，`_convert_path_token` 走"通配回退"分支返回未加引号的整体，于是 `$(basename …)` 的结果会经历词分割与 glob 展开。

**最小复现 A（实测）**：用例 `c13_mod_n_glob`

```
IN : for %%i in (*.txt) do del "%%~ni.*"
OUT: for i in *.txt; do
         rm -f $(basename "${i%.*}").*
     done
$ cd /tmp/audit-for/sandbox/s13        # 目录里同时有 "my file.txt"(目标)、my(无关)、file.txt(无关)
BEFORE: file.txt  my  my file.txt
$ bash out/c13_mod_n_glob.sh ; echo rc=$?
rc=0
AFTER : my file.txt                     ← 目标文件没被删；两个无关文件 my 与 file.txt 被删
```

语义完全反了：`my file` 被词分割成 `my` + `file.*`，于是删除的是 `my` 和 glob `file.*`（命中 `file.txt`），而 `my file.txt` 保留。

**最小复现 B（实测）**：用例 `c14_mod_n_glob2`

```
IN : for %%i in (*.txt) do del "%%~ni*"
OUT: rm -f $(basename "${i%.*}")*
$ cd /tmp/audit-for/sandbox/s14       # my file.txt + my + file.log
BEFORE: file.log  my  my file.txt
$ bash out/c14_mod_n_glob2.sh ; echo rc=$?
rc=0
AFTER : my file.txt                    ← 无关的 my 与 file.log 被删，目标保留
```

**根因 + 锚点**：`_convert_path_token`（`batch.py:2217-2227`）——探测到通配符时 `return converted`（2226）或 `return f'"{head}"/{tail}'`（2225），只有无通配符时才走 `_dq_preserving_substitutions`（2227）加引号。`_modifier` 的 1249-1250 产出的 `$( … )` 因此暴露在词分割下。

**实测后果**：删错文件（真实数据丢失），且**目标文件反而幸存**，用户很难从"文件没删掉"联想到"别的文件被删了"。

---

### 3.5 【高】G5：`find` 不带 `-print0` + 按行 `read` ⇒ 目录名含换行时**越界删除**

**现象**：`_emit_for_r` 用 `find "$PWD" -type d`（无 `-print0`）配 `while IFS= read -r`。目录名里若含换行符，一个值会裂成两行：第一行是绝对路径前缀，**第二行是相对片段，被当成相对当前脚本 CWD 的路径**。当 `for /r <root>` 的 root 不是 CWD 时，该相对片段解析到的目录**根本不在遍历范围内**。

**最小复现（实测）**：用例 `c98_forr_root_newline`

```
IN : for /r build %%i in (.) do del "%%i\*.tmp"
OUT: while IFS= read -r i; do
         rm -f "${i:-}"/*.tmp
     done < <(cd "build" && find "$PWD" -type d)

沙箱 s98： build/x\nvictim/inside.tmp（遍历范围内的目标）
          victim/important.tmp     （在 build/ **之外**，不属于遍历范围）
$ (cd build && find "$PWD" -type d)     # 三行，第三行是被换行劈出来的相对片段
/tmp/audit-for/sandbox/s98/build
/tmp/audit-for/sandbox/s98/build/x
victim
$ bash ./run.sh ; echo rc=$?
rc=0
$ ls victim            # 空！important.tmp 被删
```

**最小复现 B（默认 root 也能越界，实测，最干净）**：用例 `c85_forr_del_files`
`for /r %%i in (.) do del "%%i\*.tmp"` → `rm -f "${i:-}"/*.tmp`
把遍历根里的某个目录命名为 `x\n..`（文件名不含 `/`，合法），其换行后的碎片正好是 `..`，于是相对解析指向**遍历根的父目录**：

```
沙箱 s80： OUTER/VICTIM.tmp（在遍历根 WALK 之外）  OUTER/WALK/inwalk.tmp（树内）
          OUTER/WALK/x\n..（恶意目录名）
$ (cd WALK && find "$PWD" -type d | cat -A)
/tmp/audit-for/sandbox/s80/OUTER/WALK$
/tmp/audit-for/sandbox/s80/OUTER/WALK/x$
..$                                  ← 第 3 个值 = 相对片段 ".."
$ cd WALK && bash ./run.sh ; echo rc=$?
rc=0
AFTER : OUTER/VICTIM.tmp 被删除（越界！）；OUTER/WALK/inwalk.tmp 被删（root 迭代，属预期）
```

**一个值得记录的偶然缓冲**：若循环体是 `del "%%i\*"`（用例 `c79`）而不是 `del "%%i\*.tmp"`，则 root 迭代的 glob 会把那个**目录**也带上 → `rm` 报 "Is a directory" 返回 1 → `set -e` 在到达 `..` 迭代**之前**中止脚本（实测 `rc=1`，父目录的 `VICTIM.txt` 幸存）。也就是说这类越界是否命中，取决于循环体的 glob 是否恰好命中一个目录——完全不可依赖。

**根因 + 锚点**：`_emit_for_r` 的 `find`（`batch.py:2374` / `2376`）与行式读取头（`batch.py:2377`）组合；GNU find 默认 `-print` 用 `\n` 分隔，文件名中的 `\n` 无转义。修复面很窄（`-print0` + `read -r -d ''`），但现状是"**不可信目录名 → 越界删除**"。
**cmd 侧未实测**：Windows 文件名实际很难包含换行，因此这不是"cmd 语义"争论，而是**产物在 Linux 上面对不可信目录树（解压出来的压缩包、下载目录、共享挂载）时新增的删除面**。同一路径的 `rm -rf "%%i"` 变体（3.1）后果更重——该相对片段会被 `rm -rf` 直接递归删除（但 `..` 这一档被 GNU rm 自身保护挡住）。
**等级**：高（实测越界删除真实文件、`rc=0`、无告警）。前提是遍历树里存在含换行的目录名。

---

### 3.6 【高】G6：`for /d … rd /s /q "%%d"` 对"指向目录的符号链接"会递归删除**链接目标**

**现象**：`for /d %%d in (*)` 的产物是 `for d in */`，bash 的 `*/` **包含指向目录的符号链接**（实测 `MATCH <l2/>`）；`/d` 档位还会把值处理成**以 `/` 结尾**（`batch.py:2274-2277`）。`rm -rf "linkdir/"` 在尾斜杠下会解析链接并递归删除目标内容。

**最小复现（实测）**：用例 `c03_ford_rd`

```
$ cd /tmp/audit-for/sandbox/s03
BEFORE: linkdir -> realdir   other/   realdir/inside.txt("TARGET-DATA")
$ bash out/c03_ford_rd.sh ; echo rc=$?
rc=0
AFTER : linkdir -> realdir(悬空)   other 被删   realdir **整个消失**（inside.txt 一并被删）
对照实验： rm -rf "linkdir"   （无尾斜杠）→ 只删链接本身，realdir/inside.txt 完好
```

**根因 + 锚点**：`/d` 的尾 `/` 追加（`batch.py:2274-2277`）+ `cmd_rmdir` 对 `/s /q` 直接产出 `rm -rf`（`batch.py:3427-3433`）。循环变量命名的是**链接**，实际被删除的却是**链接指向的目录树**。
**cmd 侧未实测**：Windows 上 `rd /s /q <junction/symlink>` 按文档只删除重解析点本身而不遍历目标；该判断本机无法执行验证。即便如此，"枚举到的是链接、被删的是目标"本身已构成误删（判据中的"递归删错目录"）。

---

### 3.7 【高】G7：未加引号的集合 token 里的 `[...]` 是活 glob ⇒ 删错文件

**现象**：cmd 的通配符只有 `*` 和 `?`，而 bash 还有 `[...]`。`for %%i in (a[1].tmp)` 的集合 token 未被引号保护，产物直接把它当模式展开。

**最小复现（实测）**：用例 `c59_bracket`

```
IN : for %%i in (a[1].tmp) do del "%%i"
OUT: for i in a[1].tmp; do
         rm -f "${i}"
     done
$ cd /tmp/audit-for/sandbox/s59      # 同时存在 a1.tmp(无关) 与 a[1].tmp(目标)
BEFORE: a1.tmp  a[1].tmp
$ bash out/c59_bracket.sh ; echo rc=$?
rc=0
AFTER : a[1].tmp                     ← 无关的 a1.tmp 被删，目标保留
```

**根因 + 锚点**：`_convert_for_set`（`batch.py:2722-2731`）只对"纯变量 token"加引号（`_quote_collection_token`，2735），字面 token 原样输出；`utils.needs_nullglob`（`utils.py:370-383`）只识别 `*`/`?`，所以**连 nullglob 与告警都不会触发**（实测 `--report-json`：该用例 warnings = 0）。
**实测后果**：误删真实文件；且"无匹配时回退字面值"与"有匹配时删错文件"两种行为随目录内容变化，用户无法预期。

---

### 3.8 【高】G8（越界发现，非 `for` 特有）：`call :label` 里的删除逃出循环，变成 `rm -f "$1"`

**现象**：用例 `c91/c92`，源

```
for %%i in (*.tmp) do call :kill "%%i"
:kill
del %1
```

产物：

```
for i in *.tmp; do
    if declare -F label_kill >/dev/null 2>&1; then label_kill "${i}"; fi
done
# :kill（标签，未使用，保留为注释）
rm -f "${1:-}"
```

**实测后果（两个方向都错）**：

```
$ cd /tmp/audit-for/sandbox/s92 ; ls → a.tmp b.tmp run.sh victim.txt
$ bash ./run.sh victim.txt ; echo rc=$?
rc=0
$ ls → a.tmp b.tmp run.sh        ← ①循环体内的 del 一次都没执行（label_kill 未定义，静默跳过）
                                    ②顶层多出的 rm -f "${1:-}" 把脚本第一个参数 victim.txt 删了
```

**根因 + 锚点**：`_convert_call`（`batch.py:1781`）对 `call :label` 产出 `if declare -F label_x`，而 `_label_line`（`batch.py:1703`）在判定标签"未使用"时把标签体留在**顶层**（注释写着"标签，未使用，保留为注释"），此时 `%1` → `${1:-}` 指向**脚本自身的命令行参数**。
**等级**：高（可复现误删真实文件），但归因是 `call`/标签处理，不是 `for` 删除映射本身；列出是因为"循环体内的删除"在此被搬到了循环外并换了语义。

---

### 3.9 【中】`%%~dpi` / `%%~pi` 被映射成循环变量本身

**现象/实测产物**：

```
IN : for %%i in (*.tmp) do rd /s /q "%%~dpi"      →  OUT: rm -rf "${i}"
IN : for %%i in (*.tmp) do del "%%~dpi%%~nxi"     →  OUT: rm -f "${i}$(basename "${i}")"
```

`%%~dpi` 在 cmd 里是"目录部分"，产物却是文件自身；`%%~dpi%%~nxi` 变成路径拼接垃圾（`/x/a.tmpa.tmp`）。
**根因 + 锚点**：`_modifier`（`batch.py:1233-1253`）只在 `"n" in mods` 时处理 `d/p`（1241-1244），没有 `n` 的 `dp`/`p` 落到 1253 `return f"${{{var}}}"`。
**等级**：中——这两个形状在实测中"破坏力反而小于 cmd"（cmd 的 `%%~dpi` 指向目录 ⇒ 真删目录），但语义是错的，且一旦拼接结果与真实路径碰撞就会误删。未观察到数据损失，故不判高。

### 3.10 【中】`cd` / `pushd` 后删除：工作目录持久化 + 相对路径

**实测产物**（用例 `c73_cd_block`）：

```
for d in */; do
    cd "${d}"
    rm -f *.tmp
done
```

```
$ cd /tmp/audit-for/sandbox/s73    # sub1/a.tmp  sub2/b.tmp  top.tmp
$ bash ./run.sh ; echo rc=$?
rc=1
stderr: ./run.sh: 第 9 行：cd: sub2/: 没有那个文件或目录
AFTER : sub1/(空)  sub2/b.tmp  top.tmp     ← 第 1 轮删了 sub1/a.tmp；第 2 轮 cd 失败，脚本被 set -e 中止
```

`cd` 跨迭代持久化（`cmd_cd`，`batch.py:3393-3397`；`for` 体在 2292/2301 逐行展开）⇒ 第 2 轮的相对 `cd` 是相对第 1 轮之后的 CWD。**cmd 侧**：cmd 的 `cd` 同样是全局的，第 2 轮也会 cd 失败，但 cmd 无 `set -e`、不会中止，会继续在 `sub1` 里执行 `del "*.tmp"`。因此产物是"**静默地做了一半就退出**"（部分删除 + `rc=1`），与 cmd 的"继续做错"不同；若 `sub1/sub2` 恰好存在，产物会在**错误目录**里完成删除。判中（未构造出实际误删，且主要语义继承自源脚本）。

### 3.11 【中】`for /f "delims=" … rd /s /q "%%i"`：列表里的 `.` / `..` 造成中途退出

**实测**：用例 `c41_forf_delims`，`list.txt` 含 `.`、`..`、`sub`、`<绝对路径>/keepdir`：

```
$ bash ./run.sh ; echo rc=$?
rc=1
stderr: rm: 拒绝删除 '.' 或 '..' 目录：跳过 '.'
AFTER : keepdir/ 仍在（未被删），sub 未被删（顺序版实验里 sub 在前时被删，keepdir 因中止幸存）
```

`rm -rf "${i}"` + `set -e`：`. `行让 `rm` 返回 1 ⇒ 整个循环中止。后果是"部分删除 + 静默停止"，且该保护纯属偶然（换顺序就删到别的东西）。判中。

### 3.12 【中】`\\?\` 前缀里的 `?` 成为活通配符

用例 `c63_drive_unc`：`for %%i in (\\?\C:\tmp\*.tmp) do del "%%i"` → `for i in \/?/C:/tmp/*.tmp; do rm -f "${i}"; done`。
`?` 在集合里是活的单字符通配。**实测局限**：该模式以 `/` 开头（锚定在文件系统根），非 root 用户无法在 `/<单字符>/...` 处构造可匹配目录，因此本机**没有跑出真实匹配与删除**（dry-run `for i in \/?/C:/tmp/*.tmp` 无匹配 ⇒ 因 nullglob 而 0 次迭代）。判为**中（理论风险，未实测命中）**。
这与 v2.11.0 已记录的 `DEL /F /A /Q \\?\%1` → `rm -rf \/?/${1:-}`（`tests/test_batch_backslash_paths.py:120-128` 有专门测试）属同一类；参数位（未加引号）版本的危险性更高，本报告不重复认定。

### 3.13 【中】F3 未修全的"写入"面：写错文件名 / 覆盖已有文件

见 3.2 最小复现 C：`cd.>"%%i\%%~ni.txt"` 在祖先目录名含点时生成 `samples/f3.txt` 而非 `samples/samples.txt`。若该错名文件已存在，`>` 会**截断覆盖**它。属同一根因，单独列出因为它的后果是"写坏文件"而非"删错文件"。

### 3.14 【低】其余偏差（均有实测产物，无实测数据损失）

- `c10` `%%~xi`：`$(echo ".${i##*.}")`。名字无扩展名时 bash 给 `.sub`，cmd `%~xi` 给空串 ⇒ 若存在同名隐藏文件 `.sub` 会被误删（未实测命中）。
- `c53` `$` 字面量：`del "$%%i"` → `rm -f "$${i}"`（`$$` = PID）⇒ 删的是 `<PID><名字>`，必然不命中；cmd 中 `$` 是字面量。
- `c66` `{a,b}`：`_convert_for_set` 把 `,` 重写成空格（`batch.py:2725`）⇒ `file{1,2}.tmp` 变成两个幻影词 `file{1`、`2}.tmp`（cmd 中 `{` 是字面量，只删一个名字）。
- `c72` `pushd`：产物保留 `pushd sub`，bash 的 `pushd` 会把目录栈**打印到 stdout**（cmd 的 `pushd` 也打印，故仅提示）。
- `c61`/`c62` `?` / `*` 集合：cmd 同样按通配处理，属继承风险。
- `c30`/`c31`/`c33` 变量/参数集合被强制加引号（`"${FILES:-}"`、`"$@"`）：改变 cmd 的空白拆词语义（转换器有对应 warning，实测 warnings=1）；空值本身是**安全的**——实测 `rm -f ""` / `rm -rf ""` 返回 **rc=0 且无任何动作**，也不会触发 `set -e`。
- `c05`/`c11`/`c76` `%%~ni`/`%%~nd` 在"相对名字"档位与 cmd `%~n` 一致（都按 basename 最后一个点切分），会删掉同名的无扩展名兄弟文件，但 cmd 同样如此。
- `c91`/`c92` 已在 3.8 单列。

### 3.15 【无】确认安全的形态

- `for %%i in (*.tmp) do del "%%i"` → `for i in *.tmp; do rm -f "${i}"; done`（+nullglob）：绝对路径无、引号完整。实测 `a.tmp`/`b.tmp` 被删、`keep.txt` 保留。
- `for /f %%i in (list.txt) do del "%%i"` → 有 `-r` 文件守卫、`\r` 修剪、空行 `continue`、`rm -f "${i}"` 全引用；实测按预期只删列表内文件。
- `for /f` 的 `tokens=` / `skip=` / 管道 / 字符串 / `usebackq` 各形态：引号与守卫齐全；`usebackq` 反引号与 `for /r` 非 `.` 集合、含 `goto` 循环体、root 含通配符等一律**诚实降级为 TODO**（`c46/c81/c82/c84`），未产出不安全产物。
- 特殊字符 `;` `&` `|` `(` `)` `!` `'` 反引号：分隔与转义正确（`c55/c56/c57/c58/c60/c64`）；中文与空格路径正确（`c50/c52`；含空格集合走 `_fix_glob_token`→`"head"/tail` 时引号在，见 `c51`）。
- 嵌套 `for`（`c95`）导致 `bash -n` 失败时，转换器把整个脚本降级为注释，安全。

---

## 4. 结论与建议

### 4.1 真风险（有实测破坏性后果，建议按序处理）

| 优先级 | 缺陷 | 用例 | 一句话 |
| --- | --- | --- | --- |
| P0 | G1 `for /r` 删循环变量自身 | c02/c80/c83/c86 | `rm -rf "$PWD"` 静默清空整棵工作目录（含脚本自身），`rc=0` |
| P0 | G2 `%%~n` 截断按整串最后一个点 | c15/c77/c87（证明 c99） | 祖先目录名含点 ⇒ 删错文件 / **递归删错目录**（**注：已有并行会话的未提交改动专门修这一条，见 1.4**） |
| P0 | G3 空变量 + 通配尾 ⇒ 根锚定 glob | c97/c96 | `rm -f "${i}"/*` 在 `i` 为空时展开成 `/bin /boot …` |
| P1 | G4 未加引号 `$( … )` + 通配 | c13/c14 | 命令替换被词分割 ⇒ 删掉无关文件、目标反而幸存（**打过并行补丁后仍成立**） |
| P1 | G5 `find` 无 `-print0` + 行式 read | c85/c98（c79 为对照） | 目录名含换行 ⇒ 相对碎片解析到遍历范围之外并被删除（默认 root 下 `..` 碎片可删父目录内容） |
| P1 | G6 `for /d` + 目录符号链接 | c03 | `rm -rf "link/"` 递归删除链接**目标** |
| P1 | G7 `[...]` 集合是活 glob | c59 | 删 `a1.tmp` 而不是 `a[1].tmp`，且**无 nullglob、无告警** |
| P2 | G8 `call :label` 里的删除逃出循环 | c91/c92 | 循环内删除被静默丢弃；顶层 `rm -f "${1:-}"` 删掉脚本参数 |

**可发现性**：以上用例在 `--cli -q` 与 `--report-json` 下 **warnings/todos 均为 0**（`c11`/`c13` 只有一条与缺陷无关的 nullglob 告警，`c97` 只有"变量集合已加引号"告警）。也就是说，用户从转换报告里**看不出**这些产物会误删。

### 4.2 理论风险（未实测命中，或主要继承自源脚本）

- G-`?`（3.12，`\\?\` 前缀的 `?` 活通配）：本机无法在文件系统根构造匹配目录，只验证到"模式里 `?` 是活的"。
- `%%~xi`（无扩展名 → `.name`）、`$`→`$$`、`{a,b}` 逗号重写：偏差明确但未构造出真实数据损失。
- `for /d` + `%%~n`（3.2 表首行）：与 cmd 语义一致，属源脚本固有陷阱而非映射缺陷。
- 3.10 的 `cd` 持久化：主要语义继承自 cmd；产物的差异（`set -e` 中途退出）方向是"更少破坏"。
- 所有 cmd 侧断言（`rd` 不能删工作目录、`rd` 不遍历重解析点、`for` 空集合 0 次迭代、cmd 通配删除有 Y/N 确认）**均标注为 [cmd 侧未实测]**，本机没有 `cmd.exe`/wine 可用。

### 4.3 建议（本次不做任何修复）

1. **给"删除类命令 + 循环变量"加静态风险闸门**：当 `del/erase/rd/rmdir`（或 `copy/move` 的删除式覆盖）的目标 token 同时含循环变量引用与通配符时，参照现有 `_for_todo_lines`（`batch.py:2709`）降级为 TODO，或至少产出与 `tests/test_batch_backslash_paths.py:120-128` 同级的高危告警（现有告警体系已有 `category="glob"`）。
2. **`for /r` 值域需要两处硬化**：`find … -print0` + `read -r -d ''`；以及"根目录自身"这一值应显式排除或加守卫（`for /r` 的删除目标等于 `$PWD` 时不应直接交给 `rm -rf`）。
3. **`%%~n` 的表达式应在 basename 之后切分**（即先取 basename 再剥扩展名），并补一条"祖先目录名含点"的回归测试——现有 `tests/test_batch_for_r.py:57-75` 的 `tmp_path` 恰好不含点，因此漏掉了 F3 的剩余部分（建议单测里显式使用 `/…/a.b/samples` 形状的路径）。
4. **空值必须与"一个空词"区分**：`"${FILES:-}"` 让空集合变成 1 次空值迭代；配合引号外的通配符即变成根 glob。空值应 `continue` 或整体 TODO，且 `for /f` 的 `-z` 守卫应覆盖**全部** `loop_vars`（现在只覆盖 `loop_vars[0]`，`batch.py:2606`）。
5. **未加引号的 `$( … )` 不应出现在删除参数位**：`_convert_path_token` 的通配回退分支（`batch.py:2226`）宜对命令替换/变量做引号保护，只把真正需要 glob 的字面通配符留在引号外。
6. **通配符识别应包含 `[...]`**：`utils.needs_nullglob`（`utils.py:370-383`）与 `_note_glob`（`batch.py:2764`）目前都不认方括号，导致 `a[1].tmp` 既无 nullglob 也无告警。
7. 建议为以上每条补一条**运行语义**测试（不只是 `bash -n`）：在临时目录里真跑产物并断言"被删文件集合"。本仓库已有 `subprocess.run(bash)` 的先例（`tests/test_batch_for_r.py:44-54`）。

---

## 5. 未覆盖 / 存疑

1. **cmd 真机对照全部缺失**：本机没有 `cmd.exe`/wine，因此所有"cmd 会怎样"的判断都是文档/经验推断，已在正文逐条标注 **[cmd 侧未实测]**。受影响的判断包括：`rd /s /q` 对工作目录与重解析点的行为、`for %i in ()` 的 0 次迭代、`del "\*"` 的 Y/N 确认、`%~n` 对 `my.dir` 的切分、`for /f` 缺 token 时 `%j` 是空还是字面 `%j`。
2. **未对 `/` 真正执行根级 `rm`**：G3 用"把 `rm` 换成 `printf`、参数文本完全不变"的替身验证了操作数展开为 `/bin /boot …`，未验证真实删除结果（避免自毁）。
3. **G6 未在 Windows 侧验证重解析点语义**；Linux 侧只验证了 `rm -rf "link/"` 会删链接目标、`rm -rf "link"` 不会。
4. **G5 只用了"含换行的目录名"这一种不可信输入**，没有穷举其他 find 值域注入（例如目录名含 `\r`、以 `-` 开头等）。`rm -f "-rf"` 这类选项注入只做了推理，未实测。
5. **未覆盖的 `for` 形态**：`for /l`（数值循环）体内的删除、`for /f` 的 `tokens=*`/多段 `tokens`、`for /r` 的非 `.` 集合（一律 TODO，未深挖 TODO 是否会被用户手工改写错）、`for %%i in ("a b") do (rd /s /q "%%i")` 之外的引号组合、`skip`/`eol` 与删除的组合、延迟展开 `!var!` 与删除的组合（`c90` 仅覆盖简单形态）。
6. **未做 fuzz**：76 个用例是手工设计的关键形态，不是全组合；`_convert_for_set`、`_fix_glob_token`、`_dq_preserving_substitutions` 的边界（如同时含 `$(`、反引号、`*`、空格、`[` 的 token）只覆盖了少数代表。
7. **未审查 diff/报告链路**：`--diff`、`--report`、`--run`（`--run` 会真执行产物，本次刻意未用，以免在仓库工作目录里执行删除）、`--fix-todos` 的 LLM 回填路径均未触及。
8. **未评估 `cmd_del` / `cmd_rmdir` 的开关映射完备性**：`attrib` 式开关（`/a`、`/p`、`/s` 与 `/q` 的组合）只按现有告警逻辑观察，未逐一构造。
9. **`research/` 目录此前只有 `behavior-tracking/` 与 `session-subagent-status.md`**，没有既有安全审计基线可比对；本报告是该主题的第一份。
10. **并行会话的工作区改动未纳入审查**：审查期间工作区出现了 `M python/bat2sh/core/batch.py`、`M tests/test_batch.py`、`?? research/security-audit-path.md` 等（非本次审查所为）。我只把工作区版当作"对 G2 的候选修复"做了 1.4 的对照，**没有审查这些改动本身**（例如 `__bat2sh_b` 变量在嵌套/并发场景下是否有新问题、`tests/test_batch_tilde_n_dotted_path.py` 的覆盖是否充分）。若要以"当前工作区"为口径发布结论，需要重跑一遍完整实验。
11. **未测 `--no-quote-vars` / `--no-strict` 等非默认开关**：本报告全部结论都在默认设置（`--cli -q`）下取得。`--no-quote-vars` 会去掉 `_quote_collection_token` 的引号，很可能放大 G3/G4（空值与词分割），但未实测。
