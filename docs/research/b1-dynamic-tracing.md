# B1 研究报告：PS 动态追踪可行性（v1.5 阶段归档）

> 研究时间：2026-09-15 · 方法：只读实验（便携 pwsh 7.4.6 + bwrap 沙箱 + Trace 捕获）·
> 临时产物：`/tmp/opencode/b1/`（未入仓）· 仓库未被修改。
> 结论：**值得做 —— 作为静态转换器的补充，而非替代。**

# bat2sh Dynamic Tracing Feasibility Report

**Date:** 2026-09-15 · **Scratch root:** `/tmp/opencode/b1/` · **Repo:** `/home/duanjb666/bat2sh`（未被修改；见 §9）

## 0. TL;DR 结论

**值得做 —— 作为静态转换器的补充，而非替代。** 动态追踪在技术上可行（便携 pwsh 7.4.6 在 `bwrap` 下无头运行、网络隔离、~20 秒超时），且能揭示静态分析可证明无法获得的东西：运行时分支选择、原生命令身份、别名/版本语义差异、以及哪些静态 TODO 实际可达。但在 Linux 沙箱下，整个 Windows/WMI/注册表表面永远不会执行，因此它无法生成主要的迁移 TODO 清单。建议范围："可达代码验证 + 未知命令发现"。MVP 工作量 ≈ 1.5–3 人周。

## 1. pwsh 安装

便携、无包管理器、无系统安装：

```bash
mkdir -p /tmp/opencode/b1/pwsh && cd /tmp/opencode/b1/pwsh
curl -L -o pwsh.tar.gz \
  https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/powershell-7.4.6-linux-x64.tar.gz
mkdir -p 7.4.6 && tar -xzf pwsh.tar.gz -C 7.4.6 && chmod +x 7.4.6/pwsh
```

```
$ /tmp/opencode/b1/pwsh/7.4.6/pwsh --version
PowerShell 7.4.6
$ .../pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
7.4.6
```

（选择 7.4.x 作为 LTS；7.4.6 验证 HTTP 200。GitHub API 被限流，因此直接探测发布 URL。）

## 2. 沙箱配方与各项调整

运行器：`/tmp/opencode/b1/sandbox/run.sh`。有效命令（bwrap 来自 `sb.py`，加上已记录的增量）：

```bash
timeout -k 5 20 bwrap \
  --unshare-all --die-with-parent \
  --ro-bind /usr /usr \
  --ro-bind /etc /etc \                      # 新增（必需 — 见下）
  --ro-bind /tmp/opencode/b1/pwsh/7.4.6 /opt/pwsh \   # 新增便携 pwsh
  --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --symlink usr/bin /bin --symlink usr/sbin /sbin \
  --proc /proc --dev /dev --tmpfs /tmp \
  --bind "$WORKDIR" "$WORKDIR" --chdir "$WORKDIR" \
  env -i HOME="$WORKDIR" PATH=/opt/pwsh:/usr/bin:/usr/sbin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    TERM=dumb POWERSHELL_TELEMETRY_OPTOUT=1 DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    POWERSHELL_UPDATECHECK=Off DOTNET_NOLOGO=1 \
  /opt/pwsh/pwsh -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$WORKDIR/script.ps1"
```

相对 `sb.py` 的调整，逐项验证：
- **`--ro-bind /etc /etc` 是必需的。** 没有它 pwsh 在初始化时即死：`The shell cannot be started. A failure occurred during initialization: No such file or directory`（重复）。基础 `sb.py` 配方不绑定 `/etc`；它只对 bash 有效。
- **`--ro-bind <pwsh> /opt/pwsh`** 新增；`PATH` 以 `/opt/pwsh` 开头。
- **使用 `env -i`** 而非普通 `env`，以免宿主机代理变量（`127.0.0.1:10808`）泄漏进来。网络确实被阻断：`Invoke-WebRequest https://example.com` → `Resource temporarily unavailable (example.com:443)`；使用普通 `env` 时同样被拒绝。
- **`HOME`** 指向可写的 bind-mounted 工作目录（已验证：`Set-Content "$HOME/probe.txt"` 持久化）。
- 按要求设置 `POWERSHELL_TELEMETRY_OPTOUT`、`DOTNET_CLI_TELEMETRY_OPTOUT`；为确定性新增 `POWERSHELL_UPDATECHECK=Off`、`DOTNET_NOLOGO=1`。
- `timeout -k 5` 保护有效：`Start-Sleep 60` 脚本返回 **rc=124**。
- `--print`/report 运行是只读的；从未从仓库执行任何内容。

## 3. 选中的脚本（10 个）

选择覆盖逻辑密集、多样化的 Linux 可达分支；语料中不存在 `check-uptime`。

| # | 脚本 | LOC | 理由 |
|---|--------|-----|------|
| 1 | check-cpu.ps1 | 85 | 函数、`/sys` 探测、分支、Windows-WMI 回退 |
| 2 | check-firewall.ps1 | 31 | Linux 分支通过 `sudo ufw` 调外部命令 |
| 3 | check-drive-space.ps1 | 58 | `Get-PSDrive`、算术、`Read-Host` 回退 |
| 4 | check-file.ps1 | 127 | here-string CSV、`ConvertFrom-Csv`、字节 I/O、管道 |
| 5 | check-ipv4-address.ps1 | 41 | 纯函数 + 正则（无外部依赖） |
| 6 | check-bios.ps1 | 41 | `sudo dmidecode`、静默退出路径 |
| 7 | check-drives.ps1 | 59 | `Get-PSDrive` 枚举 + 循环 |
| 8 | build-repo.ps1 | 177 | 最大：12 路分支树、外部构建工具 |
| 9 | check-easter-sunday.ps1 | 28 | `[DateTime]` 逻辑 + 动态兄弟脚本调用 |
| 10 | check-gpu.ps1 | 48 | Linux 分支是显式 TODO/no-op；Windows WMI |

补充探针（不计入）：**add-firewall-rules.ps1** — Windows 专属 cmdlet + 权限 + 交互性。

## 4. 逐脚本结果

| 脚本 | rc | 分类 | 证据（简短） |
|--------|----|----------------|------------------|
| check-cpu | 0 | **RAN** | `✅ 64-bit CPU (16 cores)` |
| check-firewall | 0 | **FAILED-ENV**（权限） | `sudo: The "no new privileges" flag is set` → `ufw` 从未运行 |
| check-drive-space | 0 | **RAN** | `✅ Drive / uses 0% of 16GB (16GB free)` |
| check-file | 0 | **RAN***（部分） | 运行了但 `/usr/bin/sort: invalid option -- 'e'`；逻辑损坏（见 §6） |
| check-ipv4-address | 0 | **RAN** | `✅ IPv4 192.168.11.22 is valid` |
| check-bios | 0 | **FAILED-ENV**（权限） | `sudo` 被阻止 → `$model` 为空 → 静默 `exit 0` |
| check-drives | 0 | **RAN** | `✅ Drive / uses 0% of 15GB ...` |
| build-repo | 0 | **RAN** | `WARNING: Sorry, no make rule applies to: 📂usr`（最后一个 `else`） |
| check-easter-sunday | 1 | **FAILED-ENV**（缺少兄弟脚本） | `The term '.../speak-english.ps1' is not recognized` |
| check-gpu | 0 | **RAN**（no-op） | Linux 分支为空 → `exit 0`、零输出 |
| *add-firewall-rules（额外）* | 1 | **FAILED-MISSING-CMDLET** | `The term 'New-NetFirewallRule' is not recognized` |

### 失败分类（10 个选中脚本）

| 类别 | 数量 | 脚本 |
|----------|-------|---------|
| RAN | 7 | cpu, drive-space, file*, ipv4, drives, build-repo, gpu |
| FAILED-ENV — 权限 | 2 | firewall, bios |
| FAILED-ENV — 缺少兄弟依赖 | 1 | easter-sunday |
| FAILED-MISSING-CMDLET | 0（10 个中）/ 1（补充） | add-firewall-rules |
| FAILED-PARSE | 0 | — |
| 其他 | 0 | — |

*与语料设计一致：大多数 fleschutz 脚本都有 Linux 分支，因此 RAN 比例高，但每个 Windows 专属分支在这台主机上都是死代码。

## 5. 追踪方法

原始数据：`/tmp/opencode/b1/traces/{A,B,C}-<script>/`，驱动脚本在 `/tmp/opencode/b1/drivers/`，测试框架在 `/tmp/opencode/b1/sandbox/`。

| 方法 | 产出 | 结果 | 局限 |
|--------|----------------|-------------|-------------|
| **A** `Set-PSDebug -Trace 1` | 已执行源码行 + 已走分支（stdout `DEBUG: n+ >>>> ...`） | **10/10 脚本** | 无解析后命令名/参数；包含赋值；冗长 |
| **B** cmdlet 函数 shim + PATH 原生命令 shim | 精确的 `CMDLET <name> <args>` / `NATIVE <name> <argv>` | 10/10，15 个不同命令 | 包裹 pipeline cmdlet 会破坏 `$input`；自递归陷阱（已用模块限定日志调用修复）；无法感知隐式输出、操作符、正则 |
| **C** `Trace-Command -Name CommandDiscovery -PSHost` | 解析后名称 + 类型（cmdlet/function/script/application） | 10/10 | 极嘈杂的路径探测；无参数 |

**最佳组合：B 用于命令清单 + A 用于控制流/分支覆盖**，C 仅用于恢复 B 漏掉的名称（例如 `Set-StrictMode`、`%`）。B 必须通过驱动包装器注入，因为把 `Set-PSDebug` 前置到脚本 `param()` 之前会导致解析错误。

**一个标准化示例**（`/tmp/opencode/b1/traces/NORMALIZED-EXAMPLE-check-drives.txt`）：

```
Write-Progress "Querying drives..."
Get-PSDrive -PSProvider FileSystem
Write-Progress -completed "Done."
Get-PSDrive /
Get-PSDrive Temp
Write-Host "✅ Drive / uses 0% of 15GB (15GB free), Temp uses 0% of 15GB (15GB free)"
```

## 6. 追踪 vs 静态 TODO — 汇总发现

静态总计（10 个脚本）：**107 个 TODO**、152 个警告、6 个错误（`/tmp/opencode/b1/out/report/*.json`）。TODO 类别分布：

| 类别 | 数量 | % of 107 |
|----------|------:|---------:|
| `$LASTEXITCODE` / `throw` 控制流 | 40 | 37.4% |
| 对象属性访问（`$obj.Prop`） | 25 | 23.4% |
| `$Error[...]`/错误格式化 | 18 | 16.8% |
| 其他 / 类型推断 / 杂项 | 10 | 9.3% |
| **不支持的 PowerShell cmdlet（命令级）** | **6** | **5.6%** |
| .NET 静态调用（`[math]::`、`[DateTime]::`） | 5 | 4.7% |
| `return` 语义 | 3 | 2.8% |

**追踪相比静态 TODO 增加的内容：**
1. **运行时分支解析。** `build-repo` 记录了 15 次 `Test-Path` 调用，并证明只有最后一个 `else` 会执行 — 静态 TODO 无法指出 12 个分支中哪些是活分支。
2. **解析后命令身份 / 别名差异。** 在 pwsh 7 中，`sort` **不是** `Sort-Object` 的别名 — 它解析为 `/usr/bin/sort`（`Get-Command sort` → Application）。因此 `check-file` 在运行时报错，而转换器把 `sort-object → sort` 映射。静态分析无法检测这种版本/别名语义差异。
3. **静态从未标记的原生命令。** `sudo ufw status`、`sudo dmidecode` 以 `NATIVE` 出现；`check-bios` 根本没有 sudo 相关 TODO。
4. **动态脚本调用。** `& "$PSScriptRoot/speak-english.ps1"` 被执行并识别（A + C）；静态只发出一个字符串 TODO。
5. **函数调用图。** `BuildFolder`、`GetCPUTemperature`、`IsIPv4AddressValid`、`Check-Header`、`Bytes2String` 中哪些实际运行 — 哪些是死代码。
6. **仅运行时可见的 pwsh-7 不兼容性。** 已确认 `Get-Content -Encoding Byte` → `'Byte' is not a supported encoding name`（PS7 已移除），以及原生 `sort` 管道错误。`check-file` 静态报告显示 **0 个 TODO / 4 个警告**，但运行时报错。
7. **Linux 下的死代码。** `check-gpu` 有 10 个静态 TODO（全部是 Windows WMI 属性访问），但执行 **零条命令** — 追踪显示整个文件的有意义主体在 Linux 上不可达。

**追踪遗漏的内容：**
1. **所有未走的 Windows 分支** — `Get-WmiObject`/`Get-CimInstance`/`New-NetFirewallRule`/注册表 `gp` 从不执行，因此追踪看不到静态 TODO 专门要捕捉的任何命令。这是决定性的局限。
2. **异常/catch 路径**（例如占 TODO 16.8% 的 `$Error[...]` 行）。
3. **非命令 TODO** — 94.4% 的静态 TODO（对象属性、`$LASTEXITCODE`、.NET 静态、格式化）对命令级追踪不可见。
4. **隐式输出** — `check-ipv4`/`check-easter` 发出裸字符串；B 什么都不记录，A 显示该行。
5. **交互式脚本**（`Read-Host`、`Get-Credential`）无法非交互运行 → 追踪不完整/受阻。
6. **缺少兄弟依赖**表现为错误，而不是命令。

## 7. 翻译率

**方法：** 跨 10 次运行的 B 方法 `CMDLET`/`NATIVE` 名称并集，加上仅 C 方法发现的命令名（`Set-StrictMode`、`%`≡`ForEach-Object`、`ConvertFrom-Csv`）；排除驱动自身的 `Get-Command`、脚本定义函数和动态脚本路径。每个名称通过导入 `rules.py` 分类：`PS_TODO_CMDLETS`/`cmd_todo_cmdlet` → TODO；`PS_HANDLER_MAP` → mapped(handler)；`PS_SIMPLE_CMDLETS` → mapped(simple)；`PS_POSIX_KEEP` → passthrough；否则 unknown。

不同追踪命令名 = **15**。

| 命令 | 类别 | 详情 |
|---------|-------|--------|
| Get-Location, Set-StrictMode | mapped(simple) | `pwd`, `:` |
| Get-Content, Get-Item, Resolve-Path, Test-Path, Write-Host, Write-Warning, `%` | mapped(handler) | cmd_* |
| Get-PSDrive, New-Object | TODO | 驱动器无对应物 / cmd_todo_cmdlet |
| sort | passthrough(posix) | 在 `PS_POSIX_KEEP` 中（但见别名差异 §6） |
| Write-Progress, ConvertFrom-Csv, sudo | **unknown** | 无规则条目 |

| 类别 | 数量 | % |
|-------|------:|--:|
| mapped（handler + simple） | 9 | 60.0% |
| TODO-mapped | 2 | 13.3% |
| passthrough（posix keep） | 1 | 6.7% |
| unknown | 3 | 20.0% |
| **mapped + TODO** | **11** | **73.3%** |

注意：分母很小且有分支偏差（只执行了 Linux 可达命令）。`Write-Progress`（几乎所有脚本都使用）和 `sudo` 是值得注意的未覆盖/未知项。

## 8. 结论：值得做（作为补充）— 理由 + 工作量

**为何值得做：**
- 端到端可行性已证明：便携 pwsh + bwrap + `--unshare-all`、无网络、`timeout` 安全、HOME 可写、每脚本 `< 25 s`。
- 在本语料上交付了具体的、静态不可见的价值：活分支覆盖、原生命令发现、别名/版本破坏（`sort`、`-Encoding Byte`）、动态脚本调用、死代码确认（`check-gpu`）。
- 可作为现有 `--print`/报告管线上的 *可选验证环节* 集成，并复用 `sb.py` 的沙箱形态。

**为何不能作为替代：**
- 最高价值的迁移目标（WMI、注册表、Windows 专属 cmdlet）正是无法在 Linux 上执行的代码。单靠追踪会低报 Windows 专属 TODO，必须与静态结果合并。
- 覆盖率取决于宿主环境；`sudo`/交互式脚本会扭曲结果。

**工作量估算（MVP，1 名工程师）：约 1.5–3 周**
1. pwsh 便携下载器/缓存（`~/.cache/bat2sh/pwsh-7.4.x`）+ 版本固定 — 0.5 天
2. bwrap 运行器（复用 `sb.py` + `/etc`、pwsh bind、`env -i`、timeout）— 0.5–1 天
3. Shim 生成器：通过 `Get-Command` 的模块限定 cmdlet 转发；跳过/正确处理 pipeline-input cmdlet；原生 PATH shim — 3–5 天
4. Trace→normalize 管线（A 行追踪 + B cmd 日志 + C discovery；去重/归一化；合并）— 3–5 天
5. 映射分类器接入 `rules.py` + 分支/TODO 可达性报告 — 2–3 天
6. CLI 表面（`bat2sh --trace-run`、JSON）+ 防护 + 测试 — 2–3 天
7. 语料测试框架 / 文档 — 1–2 天

**承诺前建议的下一步：** 运行全部 60 个语料文件（便宜，约 15 分钟）加上 Windows 专属纯静态对比集，以评估"未知命令"发现的 ROI — 当前在 Linux 分支偏置样本上仅 3/15 unknown。如果 unknown/TODO 发现保持低位，功能应界定为 *可达 TODO 验证* 而非命令挖掘。

## 9. 只读合规与事件

- 所有临时数据仅位于 `/tmp/opencode/b1/`。
- **事件（已披露）：** 我的第一批次使用了 `--report-json` **未带** `--print`；CLI 默认写输出，因此在仓库 fixture 旁创建了 **11 个 `.sh` 文件**。我通过 `git status` 发现，精确删除了这 11 个未跟踪文件（开始时仓库干净，已验证），并重新以只读方式运行报告。从未修改任何已跟踪文件。
- **安全报告调用（已验证不写任何内容）：** `bat2sh --cli --dry-run --report-json <file>`（使用此方式，不要裸 `--report-json`）。转换文本请用 `--print`。
- 最终检查：

```
$ git -C /home/duanjb666/bat2sh status --short
(empty)
```

**空 — 仓库未被触碰。**（仅 gitignore 的 `__pycache__/*.pyc` 缓存因运行被认可的 `.venv/bin/bat2sh` 而刷新；没有任何已跟踪或 fixture 内容改变。）

**原始数据参考：** `/tmp/opencode/b1/traces/{A,B,C}-*`、`/tmp/opencode/b1/out/{print,report}/`、`/tmp/opencode/b1/sandbox/{run,trace_run,make_shims,batch*}.sh`、`/tmp/opencode/b1/drivers/trace{A,B,C}-generic.ps1`、`/tmp/opencode/b1/pwsh/7.4.6`。
