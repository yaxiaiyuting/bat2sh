# B2 研究报告：注册表智能映射可行性（v1.5 阶段归档）

> 研究时间：2026-09-15 · 方法：只读静态扫描（关键字提取 + 人工归类）·
> 临时产物：`/tmp/opencode/b2/`（未入仓）· 仓库未被修改。
> 结论：**读可做（仅 38 次实测），写一律拒绝（431 次）；且应先修两处前置缺陷。**

# Registry Smart Mapping — bat2sh 可行性

所有分析均为只读完成。临时数据在 `/tmp/opencode/b2/`（`scan.py`、`hits.json`、`analyze.py`、`probe/`）。仓库未被触碰。

**范围说明：** 基于关键字的静态扫描。动态构建的键路径（`$Path`、`%VAR%\...`）被 *低估*，且按定义不可映射 — 该缺口偏向拒绝，而非偏向虚假的"可做"。

---

## 语料覆盖（实测）

| 语料 | 许可证 | 扫描数 | 含注册表构造的文件数 |
|---|---|---:|---:|
| fleschutz_full（`下载/PowerShell-1.6/scripts/**`） | CC0 | 665 | **9** |
| fleschutz fixtures（`tests/fixtures/real-corpus/fleschutz`） | CC0 | 60 | 1 |
| `common_powershell_scripts-main` | MISSING | 13 | 1 |
| `windows-batch-script-master` | 无 | 24 | **0** |
| `bat-master` | 无 | 54 | **3**（一个文件 = 320 行） |
| 根 `下载/*.bat`、`*.ps1` | 用户自有 | 22 | 1 |
| `bat2sh/examples` | 仓库 | 6 | 1 |

关键实测事实：注册表使用 **稀有且集中** — 3 个 `bat-master` 文件（由一个上下文菜单编写脚本主导）和 9/665 个 fleschutz 脚本。`windows-batch-script-master` 语料注册表使用为 **零**。

---

## (a) 清单 — 构造类型 × 数量 × 语料

| 构造 | 次数 | 语料（次数） | 操作 | 说明 |
|---|---:|---|---|---|
| `.reg` 生成/导入（`echo […]>>*.reg`、`reg import`、`regedit /s`） | **321** | bat_master 320、fleschutz_full 1 | 写 294、导入 27 | 仅 **2 个不同的 `.reg` 文件**（`showall.reg`、`open.reg`）跨 3 个脚本；233 行是值内容行 |
| cmd `reg`/`reg.exe` | **78** | bat_master 70、user_downloads 4、examples 4 | 删除 37、导入 26、查询 8、添加 7 | `export/copy/save/restore/load/unload` = **0** |
| 注册表路径上的 PowerShell cmdlet | **45** | fleschutz_full 42、fixtures 1、common 2 | 读 17、写 16、测试 8、删除 4 | `Get-Item`/`Get-ChildItem`/`New-Item`/`Remove-Item`/`Test-Path`/`*-ItemProperty` |
| COM `WScript.Shell` / `.RegRead\|RegWrite\|RegDelete` | **23** | bat_master 23 | 写 20、读 3 | 嵌入在 **生成的 `.vbs`** 中（并非实时 PS COM） |
| .NET `[Microsoft.Win32.Registry*]` | **7** | fleschutz_full 7 | 读 2、未知 5 | 一个脚本（`install-powershell.ps1`） |
| PSProvider（`New-PSDrive -PSProvider Registry`、`Registry::`） | **0** | — | — | 扫描器可处理该构造；在所有语料中 **不存在** |

实测总出现次数：**474**。读类（读+测试）：**38**；写类（写+删除+导入）：**431**。总体 **读:写 ≈ 1:11**（剔除导入后 1:10）。

根分布（实测）：`HKLM` 81、`HKCR` 73、`HKCU` 31、无根/导入 266、`HKU`/`HKCC` **0**。

## (b) 分类 — 用途 × 数量 × 读/写 × 主要键根

| 用途 | n | 读/测试 | 写 | 导入 | 文件 | 主要标准化键根 |
|---|---:|---:|---:|---:|---:|---|
| 其他（`.reg` 内容 + 导入） | 269 | 4 | 207 | 53 | 6 | `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager`（PendingFileRenameOperations）；其余 `.reg` 值行 |
| 文件关联 | 107 | 0 | 107 | 0 | 1 | `HKCR\*\shell\*`、`HKCR\Folder\shell\*`、`HKCR\CLSID\{…}\InProcServer32`、`HKCR\Directory\Background\shellex\ContextMenuHandlers\*`、`HKCR\AllFilesystemObjects\shell\*` |
| 用户偏好 | 48 | 7 | 41 | 0 | 6 | `HKCU\Control Panel\Desktop`（Wallpaper/TileWallpaper）；`HKCU\…\Explorer\Advanced`（Hidden/HideFileExt/ShowSuperHidden） |
| 应用配置 | 23 | 7 | 16 | 0 | 6 | `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps`；`HKLM\…\CurrentVersion\Fonts`；`HKCU\…\Explorer`（ShellState） |
| 系统状态/重启检测 | 8 | 8 | 0 | 0 | 2 | `…\WindowsUpdate\Auto Update\RebootRequired`、`…\Component Based Servicing\RebootPending`、`…\Control\Session Manager`、`…\CurrentVersion\RunOnce` |
| 安全策略 | 7 | 0 | 7 | 0 | 2 | `HKLM\SYSTEM\CurrentControlSet\Control\Lsa`（LimitBlankPasswordUse） |
| 服务配置 | 6 | 6 | 0 | 0 | 4 | `HKLM\SYSTEM\CurrentControlSet\Services\Netlogon`；`…\Services\SharedAccess\Parameters\FirewallPolicy\DomainProfile` |
| 系统版本 | 3 | 3 | 0 | 0 | 3 | `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform`（BackupProductKeyDefault） |
| 硬件信息 | 2 | 2 | 0 | 0 | 2 | `HKLM\HARDWARE\DESCRIPTION\System\BIOS`；`HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Configuration` |
| 安装检测 | 1 | 1 | 0 | 0 | 1 | `HKLM\|HKCU\…\CurrentVersion\Uninstall\*`（+ `Wow6432Node`） |

[判] `文件关联` 和 `其他` 被同一个上下文菜单编写脚本放大。在 *不同键* 层面，整个扫描语料中只有 **75 个不同的标准化键**。

## (c) 可行性 — 用途 × Linux 对应物 × 等价性 × 难度

| 用途（操作） | Linux 对应物 | 等价性 | 难度 | 需要设计决策 |
|---|---|---|---|---|
| 系统状态/重启检测（测试） | `/var/run/reboot-required`（Debian/Ubuntu）、`needs-restarting -r`（RHEL）、`systemctl` | 近似（发行版相关） | 中 | **是** |
| 服务配置（读） | `systemctl is-active/is-enabled/show <unit>`、unit 文件 | 近似 | 中 | **是**（unit 名称映射） |
| 系统版本（读） | `/etc/os-release`、`uname -r`、`hostnamectl` | 近似 | 低 | **是**（意图：Windows 门控 vs 信息性） |
| 硬件信息（读） | `/sys/class/dmi/id/*`、`/proc/cpuinfo`、`lscpu`、`lspci`、`/sys/class/drm` | 近似 | 低–中 | 无（基础）/ 是（GPU） |
| 安装检测（读） | `dpkg-query -W`、`rpm -qa`、`pacman -Q`、`flatpak list`、`snap list` | 近似 | 中 | **是**（包管理器） |
| 文件关联（读） | `xdg-mime query default`、`~/.config/mimeapps.list` | 近似 | 中 | **是** — 但先例已发布 |
| 文件关联（写） | `.desktop` + `xdg-mime default`；Nautilus/Nemo 脚本；KDE servicemenus | 无统一对应 | 高–不可行 | **是** |
| 用户偏好（写） | `gsettings`/`dconf`（GNOME）、桌面环境专属壁纸工具 | 近似（DE 相关） | 中–高 | **是**（哪个 DE） |
| 应用配置（读/写） | `systemd-coredump`/`coredumpctl`；`~/.local/share/fonts`+`fc-cache`；应用配置文件 | 无对应/近似 | 高 | **是** |
| 安全策略（写） | `sysctl`、PAM、`firewalld`/`nftables`（碎片化） | 无对应 | 高 | **是** |
| 系统策略（读/写） | 无统一 GPO；`/etc`、dconf locks | 无对应 | 不可行 | **是** |

[判] 语义上，注册表键是一个 *命名空间地址*，而不是值。同一个键可以被读/检测/写；目标选择取决于键 + 操作 + 值 + 周围意图。纯字符串替换永远无效。

---

## 当前转换器行为（实测，`file:line`）

| 构造 | 处理器 | 行为 |
|---|---|---|
| cmd `reg` | `rules.py:81` → `cmd_todo_hint`（`batch.py:2403`） | `rules.py:152` 提示 "注册表在 Linux 无对应物"；处理器 **返回 `None` → 行被从生成脚本中静默丢弃**，仅在 `--report` 中可见。 |
| cmd `regedit` | `rules.py:153`（同一路径） | 同上：仅报告，丢弃。 |
| cmd `reg.exe` | 落入 `.exe` 分支（`batch.py:2321` 附近、`rules.py:36` `BATCH_EXE_MAP`） | TODO "Windows 可执行文件…"，丢弃。 |
| PS `Get/Set-ItemProperty` | `rules.py:374-375,402-403` → `cmd_todo_cmdlet`（`powershell.py:2661`） | `# TODO` 注释 **保留** 在脚本中。 |
| PS `New/Remove-ItemProperty`、`New-PSDrive` | 不在 handler map 中；匹配 `^[A-Z][a-z]+-[A-Z]`（`powershell.py:2051`） | 通用 TODO "未支持的 PowerShell cmdlet"。 |
| 注册表路径上的 PS `Get-Item`/`Get-ChildItem`/`New-Item`/`Remove-Item`/`Test-Path` | `cmd_get_item`（`powershell.py:2682`）、`cmd_get_childitem`、`cmd_new_item`（`2321`）、`cmd_remove_item`（`2292`）、`cmd_test_path`（`2359`） | **静默误译**为文件系统操作：`ls -la "HKLM:/…"`、`touch "HKLM:/…"`、`rm -r "HKLM:/…"`、`[[ -e "HKLM:/…" ]]`。 |
| 赋值中的 `Get-ItemProperty` | 表达式回退 | 直接 **原样保留为引号字符串中的 PowerShell 文本**。 |
| COM / .NET | 对象属性守卫（`powershell.py:2024`） | TODO 注释；下游变量读取静默。 |
| `reg query` 提示 | `suggestions.py:149-155` | 低置信度提示 "读取对应的 Linux 配置文件…"，不自动应用。 |
| 先例：`assoc`/`ftype` | `batch.py:3060/3079` | 已自动映射到 `xdg-mime query default <mime>` 并警告。 |
| 先例：`ver`/`systeminfo` | `batch.py:3010/3014` | 带警告映射到 `uname -a`。 |

**实证探针**（`.venv/bin/bat2sh --cli --print`，文件在 `/tmp/opencode/b2/probe/`）：
- `probe_cmd.bat`（reg query/add/delete/export/import）→ 脚本正文中 **不包含** 任何这些命令；报告显示 3 个 TODO。
- `probe_ps.ps1` → `Set/New/Remove-ItemProperty` = `# TODO`；`New-Item HKLM:\…` → `touch "HKLM:/…"`；`Test-Path` → `[[ -e "HKLM:/…" ]]`；`Get-ChildItem`/`Get-Item` → `ls -la "HKLM:/…"`；`Remove-Item` → `rm -r "HKLM:/…"`。
- `probe_com.ps1` → `New-Object -ComObject WScript.Shell` 被赋值为字面字符串；`RegRead/Write/Delete` = TODO。
- `probe_dotnet.ps1` → `[Microsoft.Win32.Registry]::…` = TODO；下游 `$v` echo 静默。

[判] 有两个缺陷阻碍任何"智能映射"：(1) 批处理 TODO 返回 `None`，丢弃行而不是发出结构化标记；(2) 传给文件 cmdlet 的注册表路径被误译为本地文件。这两者都应在添加映射之前修复。

---

## (d) 可做清单 — 按优先级排序

只有 **只读** 操作可自动映射；可测量市场总量 = **38 个读类出现**。优先级 = 映射置信度 × 实测数量 × 可逆性（读是安全的）。

| # | 用途 | 证据 | 建议目标（设计） | 置信度 |
|---|---|---|---:|---|
| **P0** | 系统状态/重启检测 | 8 读，2 文件 | 探测 `/var/run/reboot-required`、`needs-restarting -r`、`systemctl` 状态 | 高 [判] |
| **P1** | 服务配置 | 6 读，4 文件 | `systemctl is-active/is-enabled/show <unit>`；映射知名服务名 | 高 [判] |
| **P2** | 系统版本 | 3 读 | `/etc/os-release`（`PRETTY_NAME`、`VERSION_ID`）、`uname -r` | 高 [判] |
| **P3** | 硬件信息 | 2 读 | `/sys/class/dmi/id/{sys_vendor,product_name,board_name}`、`lscpu`、`lspci` | 中 [判] |
| **P4** | 安装检测 | 1 读 | 包管理器查询（`dpkg-query`/`rpm -qa`/`pacman -Q`） | 中 [判] |
| **P5** | 文件关联 **读** | 注册表测得 0，但 `assoc`/`ftype` 已映射 | 扩展现有 `xdg-mime query default` 映射 | 中 [判] |

设计建议 [需设计决策]：实现一个 **键规则表**，以 `(标准化根+路径模式, 值名称, 操作)` → `{template, confidence}` 为键，**仅当键是字面量** 且 **操作 ∈ {读, 测试, 枚举}** 时应用。所有其他情况发出结构化 TODO，*保留* 根/路径/值/操作（例如机器可读的 `# TODO[REG] key=… op=… value=…`），以便 `--fix-todos`/API 可以处理。这沿用了现有 `assoc`/`ver` 先例和 `suggestions.py:149`。

## (e) 拒绝清单 — 及理由

| 拒绝项 | 数量 [测] | 理由 |
|---|---:|---|
| 所有注册表 **写**（`reg add/delete/copy/save/restore/load/unload`、`Set/New/Remove-ItemProperty`、注册表路径上的 `New-Item`/`Remove-Item`） | 378 | Linux 没有统一的可写注册表；每个键指向不同的子系统（DE、服务、包、内核） |
| `reg import` / `regedit /s` / `.reg` 生成 | 53 + 321 行 | `.reg` 是 Windows 专属序列化；没有导入目标；`echo […]>>*.reg` 是文件编写，不是实时写入 |
| COM `WScript.Shell.RegRead/RegWrite/RegDelete` | 23 | Windows Script Host 是 Windows 专属 |
| .NET `[Microsoft.Win32.Registry*]` | 7 | Windows 专属 BCL |
| PSProvider（`New-PSDrive -PSProvider Registry`、`Registry::`） | 0（构造） | Windows 专属 provider |
| 文件关联 **写** — `HKCR\CLSID\{…}\InProcServer32`、`shellex\ContextMenuHandlers`、`shell\*` | 107 | Windows Explorer COM shell-extension 模型；Linux DE 脚本机制不可互换 |
| 安全策略写（`LSA\LimitBlankPasswordUse`、防火墙策略） | 7 | 安全敏感；`sysctl`/PAM/防火墙目标碎片化 |
| 系统策略（GPO） | 0 | 无统一 Linux 策略存储 |
| `HKU`/`HKCC` 任意键 | 0 | 无合理映射 |
| 动态/变量键路径 | [判] 低估 | 无法静态解析 → 仅 TODO |

## (f) 判据、置信度、来源

**已应用判据**（按要求）：
1. **读/写分离。** 每个读/测试操作都是 *候选*；每个写/删除/导入都被拒绝。实测分布 38 读类 vs 431 写类（≈1:11）— 写侧是压倒性多数，且结构上不可映射。
2. **键路径决定目标。** 分类由标准化键路径驱动，而非命令形式。例如 `Test-Path` 作用于 `…\Run` ≠ `Test-Path` 作用于文件系统路径；同样的 *动词*，不同的 *语义*。
3. **上下文决定语义。** 同一个键可以被读（check-os）、测试（check-pending-reboot）或写（set-wallpaper）。用途分类使用键 + 值 + 邻近注释上下文；无法解析意图时标记为 其他 / 需人工判断 而非强行归类。

**置信度水平**
- **实测 [测]：** 出现次数、构造/语料覆盖、读:写比、根分布、当前转换器行号和探针输出。扫描 *精确性* 高置信；计数是 **下界**（未捕获动态路径；范围内不包含非 PS/非 bat shell 方言）。
- **判断 [判]：** 用途分类边界、可行性/等价性评级、优先级排序、映射目标。中–高置信；分类是启发式，并已对照源上下文抽查。
- **推想 [需设计决策]：** 具体映射模板、DE/包管理器/服务选择、键规则表 schema。这些是提案，不是既定映射。

**无许可语料处理：** `common_powershell_scripts-main`、`windows-batch-script-master`、`bat-master` 仅用于 **统计**；本文未引用任何原文 — 只有标准化键路径、构造类型和操作计数。CC0（fleschutz）和用户自有/仓库文件可按构造形式引用。

**仓库完整性：** `git -C /home/duanjb666/bat2sh status --short` 输出零行 — **工作树干净**，无文件被修改、暂存或创建；未执行 git 写操作；所有临时数据限于 `/tmp/opencode/b2/`。

---

## § 实现结果（v1.6.0 阶段 B，2026-09-16）

> 本节由实现阶段追加，记录 B2 结论的落地与更正。相关 commit：`1bc9c9e`（B-1）、`4b57669`（B-2）、
> `ba8ea0d`（P0）、`b438ac6`（P1）、`ad95efb`（P2）、`4399adc`（P3）、`37298f6`（P4）、`ea849b2`（P5）、
> `75b51b1`（写类）。

### 更正
- **`regedit` / `reg.exe` 原未被丢弃。** §当前转换器行为 称二者“同路径 / 丢弃”有误：实测仅精确 `reg`
  （`rules.BATCH_HANDLER_MAP → cmd_todo_hint` 返回 `None`）被派发器整行丢弃；`regedit` 走
  `BATCH_TODO_COMMANDS`、`reg.exe` 走 `.exe` 分支，均已保留为普通 TODO。
- **静默误译已消除。** `Test-Path` / `Get-Item` / `Get-ChildItem` / `New-Item` / `Remove-Item` 的 `HK*:`
  路径不再生成 `[[ -e "HKLM:/…" ]]` / `ls -la` / `touch` / `rm -r`。

### 已修两个前置缺陷
1. **reg 行不再静默丢弃** → 结构化 TODO，覆盖 `reg` / `regedit` / `reg.exe`。
2. **PS 注册表路径不再误译为文件操作**（根前缀 HKLM/HKCU/HKCR/HKU/HKCC）。

结构化 TODO 形态（机读；末尾 `: 手动检查: <原命令>` 保留以兼容 `fixer.scan_todo_markers`）：

```
# TODO[REG] op=<read|write|delete|import|export|test|enumerate> key="<路径>" value="<值名>": 手动检查: <原命令>
```

### 已实现映射（16 条规则条目，全部只读；`core/registry_map.py`）
| 级别 | 条目 | 键/值（字面量） | 目标 |
|---|---|---|---|
| P0 | 3 | RebootRequired / RebootPending / Session Manager | `/var/run/reboot-required` + `needs-restarting -r` 回退 |
| P2 | 2 | ProductName / CurrentVersion·CurrentBuildNumber | `/etc/os-release` 的 PRETTY_NAME / VERSION_ID |
| P3 | 8 | BIOS 值名（SystemManufacturer 等） | `/sys/class/dmi/id/*` |
| P4 | 2 | `Uninstall\<app>` 读取 / `Uninstall` 枚举（含 Wow6432Node） | dpkg-query / rpm / pacman 探测 |
| P5 | 1 | `HKCR\.ext`（兼容 `HKLM\SOFTWARE\Classes` 前缀） | `xdg-mime query default/filetype` |

### 拒绝（红线：无证据不发明）
- **P1 服务名 → systemd unit**：无 Windows 服务名与 Linux unit 等价性的证据 → **不映射**，仅输出结构化
  TODO 并追加 `systemctl is-active/is-enabled/show` 引导。
- **全部写类（431 次）**：结构化 TODO（`op=write/delete/import`），覆盖 cmd `reg add/delete/import`、
  PS `Set/New/Remove-ItemProperty`、注册表路径上的 `New/Remove-Item`、COM `WScript.Shell`、
  `.NET Microsoft.Win32.Registry`。
- `.reg` 生成/导入、PSProvider、动态/变量键路径：维持拒绝。

### 语料计数说明
读:写 ≈ 1:11 的实测分布未变；可自动映射的读类总量上限仍为 **38**。实现后，无 Linux 对应物的读
（服务名、未收录值名、动态键）仍按结构化 TODO 处理。

### 测试
新增 64 例（`tests/test_registry_batch.py`、`tests/test_registry_ps.py`、`tests/test_registry_p0..p5.py`、
`tests/test_registry_writes.py`），含键形态断言、结构化 TODO 断言与**沙箱运行验证**
（stub PATH 重启探针、`/etc/os-release`、dmi 文件比对、包管理器查询、`xdg-mime`）。

