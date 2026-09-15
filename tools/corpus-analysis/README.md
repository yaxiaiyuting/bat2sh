# 语料批量分析（v1.4.1）

对 114 个真实 Windows 脚本做"转换 → 静态分析 → bwrap 沙箱运行 → 结果关联"的
体检数据与可复现脚本。**本目录不含任何无许可语料的原文片段。**

## v1.8.0 新增：PS 静默错误复检

`ps_silent_check.py`：对 `tests/fixtures/real-corpus/fleschutz/`（CC0，60 个 .ps1）
重跑静默错误测量（只读）。定义为「产物 `bash -n` 通过、沙箱运行 rc==0，
但可见行为（rc/归一化 stdout）与原始 pwsh 不一致」。

```bash
python3 tools/corpus-analysis/ps_silent_check.py \
    --pwsh /path/to/portable-pwsh --out /tmp/bat2sh-ps-silent
```

缺省不带 `--pwsh` 时只做 bash 侧统计。依赖 bwrap、bash、python3。

## 数据来源

| 语料 | 许可状态 | 处理方式 |
| --- | --- | --- |
| bat-master（54 个 .bat） | 无许可 | 仅统计，原文未入 repo |
| windows-batch-script-master（24 个 .bat/.cmd） | 无许可 | 同上 |
| common_powershell_scripts-main（13 个 .ps1） | MIT 死链 | 同上 |
| `~/下载` 根目录用户脚本（22 个 .bat/.ps1） | 用户自有 | 同上 |
| PowerShell-1.6（665 个 .ps1） | CC0（fleschutz/PowerShell） | 已入 `tests/fixtures/`，本轮不重复分析 |

v1.4.1 分析总计 114 个文件（92 bat + 22 ps1）。

## 归档内容

- `results-anonymized.json`：脱敏分析结果（114 条记录；文件名、分类、计数、错误类型、命令 token；
  已移除脚本原文、stdout/stderr 全文、绝对路径）
- `analyze.py`：分析脚本（`run` 子命令复现分析；`anonymize` 子命令生成脱敏版）
- `sb.py`：单文件 bwrap 沙箱验证封装
- `README.md`：本文件

## 统计摘要（v1.4.1，修复后复扫）

- 转换：OK 95（无 TODO 34 / 含 TODO 61）、DEGRADED 19、FAILED 0
- 沙箱运行（93 个已运行；19 降级未运行、2 危险构造跳过）：
  - 完全可用（USABLE）**54**；转换通过但运行失败 39
  - 失败分类：RC_NONZERO 21、MISSING_FILE 10、MISSING_CMD 8、TIMEOUT 0、CRASH 0
- 沙箱拒绝（`mount` 危险构造，跳过不运行）：`hiddenDIsk.bat`、`mountvol.bat`
- MISSING_CMD 高频 token：`adb`(7)、`powercfg`(3)、`cscript`、`finally`、`process`、`web01` 等
  （PS 侧结构性残留与 Windows 专有工具各占一部分）
- 对比 v1.4.0 基线（同语料）：完全可用 48 → 54（+6）；"转换通过但运行失败" 45 → 39

## 复现方式

```bash
# 1) 批量分析（只读源文件；输出到独立目录）
python3 tools/corpus-analysis/analyze.py run \
    --downloads ~/下载 \
    --out /tmp/bat2sh-corpus-out
# 每文件：默认设置转换一次 + 运行失败时关闭 strict_mode 复跑一次
# 产物：/tmp/bat2sh-corpus-out/{results.json,converted/,runs/}

# 2) 生成脱敏版（移除原文/输出/绝对路径）
python3 tools/corpus-analysis/analyze.py anonymize \
    --input /tmp/bat2sh-corpus-out/results.json \
    --output /tmp/results-anonymized.json

# 3) 单文件沙箱验证
python3 tools/corpus-analysis/sb.py ~/下载/bat-master/hello.bat mytag --out /tmp/sb-out
```

依赖：Python 3.12+、`bwrap`（bubblewrap）、`bash`、`rsync`（可选，部分用例）。

## 沙箱安全边界

- `bwrap --unshare-all`：无网络、独立 PID/IPC/UTS/cgroup/user 命名空间
- 只读挂载 `/usr`；**不挂载**真实 `$HOME` / `/etc` / `/var` / `/root`
- 仅将临时 workdir 读写挂载进沙箱；`HOME` 指向 workdir
- 运行前静态扫描危险构造（`rm -r /`、`mkfs`、`dd of=/dev/*`、`mount`、fork bomb、
  `curl|sh` 等），命中即跳过不运行

## 脱敏规则与校验（v1.4.1）

移除字段：`bash`（转换后脚本全文）、`conversion.{todos,warnings,errors}[].original/message`、
`run*.stdout_head`、`run*.stderr`、`run*.workdir`、`source_path`、`summary.failure_reasons_top`、
`summary.todo_originals_top`；文件级文本聚合为 `*_categories` 计数。

保留字段：文件名（`id`）、分组、类型、行数、分类计数、`rc`/时长/`stdin`/字节数、
`correlation`、`fixtures`（脚本引用的文件名）、`missing_commands`（stderr 中的命令 token）。

校验（对 114 个源文件逐字符串比对）：
- 长度 ≥ 8 的字符串命中源文件内容：**0 处**（仅 `fixtures`/`missing_commands` 字段允许命中）
- 绝对路径类字符串（`/home/`、`/var/`、`/tmp/`、用户名）：**0 处**
- 多行字符串：**0 处**
- 含中文的字段：仅文件名（`id`）与本文件/`meta` 中的说明文字

> 人工抽查提示：`fixtures` 与 `missing_commands` 为文件名/命令 token（非原文句子），
> 其中 `missing_commands` 含少量来自 PS 转换残留的标识符（如 `dev`、`staging`、`cache01`）。

## 许可声明

本目录不含任何无许可语料的原文片段。统计结果仅包含计数、分类与标识符级 token；
语料源文件始终位于仓库之外，分析过程只读。
