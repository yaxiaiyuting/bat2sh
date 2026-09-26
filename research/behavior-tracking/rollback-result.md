# 覆盖层回滚 + 样本隔离：实测结果

> 时间：2026-09-26 · 状态：**✅ 全部通过**
> 本文件是**真实 Windows guest 上的实测记录**，非推断。
> 设计：`rollback-design.md` · 工具：`tools/` · 原始证据：`tools/results/*.json`
> 基线 HEAD：`e1f8fb4`

## 1. 结论速览

| 环节 | 结果 |
| :--- | :--- |
| 建立干净基线（含 guest 自净） | ✅ 完成 |
| **回滚后 VM 能启动** | ✅ 无错误，6+ 次 |
| **回滚后 Guest Agent 通** | ✅ `guest-ping` → `{"return":{}}`，`state='connected'` |
| **回滚速度（纯操作）** | ✅ **74–77 ms**（判据 < 30 s，**余量 390×**） |
| 完整周期（回滚→采集完成） | **32.2 s**（如实单列，见 §5） |
| **隔离有效** | ✅ **J1 + J2 + J3 全部通过**，含 `C:\poc` **之外**的整盘验证 |
| base 是否被写入 | ✅ **size/mtime/inode 全部不变**（纳秒级 mtime 一致） |
| 采集脚本可复用 | ✅ 入仓 + CLI 化 + 环境检查硬失败 |
| **能批量采了？** | ✅ **能** —— 单样本 ~32 s，全程无人工介入 |

## 2. 建立干净基线（`rollback-design.md` §4.3）

### 2.1 guest 自净（设计 §2 发现的遗留污染）

PoC 声称"基线重置用 guest 内 `rmdir` 清理"，但磁盘上 `C:\poc\samples\work\{a.txt,c.txt}` **仍在**。
若直接以此盘作基线，这两个文件会被**永久固化进"干净状态"**，之后隔离测试会**假通过**。

| 处置 | 结果 |
| :--- | :--- |
| 删 `C:\poc\samples\work\`（`a.txt`、`c.txt`） | ✅ |
| 删 `C:\poc\samples\*.bat`（PoC 样本） | ✅ |
| 删 `C:\poc\run\`（PoC 遗留空目录） | ✅ |
| 保留 `qemu-ga-x86_64.msi`、`virtio-win-gt-x64.msi`、3 个安装日志 | 环境溯源证据 |

自净后 guest 内 `C:\poc`：`ga-install.log`、`ga.log`、`gt.log`、`INSTALL-LOG.txt`、
`qemu-ga-x86_64.msi`、`virtio-win-gt-x64.msi`、空目录 `samples\` —— **6 个文件**，
正好等于后续每次运行的 `before_count = 6`。

### 2.2 冻结基线

| 步骤 | 实测 |
| :--- | :--- |
| 优雅关机（ACPI） | ✅ 干净；关机后 `qemu-img info` 的 **`dirty-flag = False`** |
| 磁盘规格（冻结前） | 虚拟 64 GiB，实际 **10.59 GB**（sparse），无 backing file |
| `mv win-behavior.qcow2 → win-behavior.base.qcow2` | inode `1418147`，size `68730224640`，mtime `20:27:18.350275342` |
| `qemu-img create -b base -F qcow2 win-behavior.qcow2` | ✅ **27 ms**，产出 **197,632 字节**（193 KiB）覆盖层 |
| 域 XML 改动 | **零**（覆盖层与原盘**同名**，`domblklist` 依旧指向 `win-behavior.qcow2`） |

> 覆盖层 193 KiB 对 base 的 10.59 GB —— 这是方案 C 的 O(1) 特性，也是它与"全盘复制"的根本差别。

## 3. 回滚三步验证（`rollback-design.md` §4.1）

| # | 测试 | 判据 | 实测 | 判定 |
| :-- | :--- | :--- | :--- | :--: |
| 1 | 回滚后 VM 能启动 | 无错误 | `virsh start` 无错，`domstate` → `running` | ✅ |
| 2 | 回滚后 Guest Agent 通 | `guest-ping` 成功 | `{"return":{}}`，`channel state='connected'` | ✅ |
| 3 | **回滚速度** | **< 30 s** | **74 / 76 / 77 ms** | ✅ |

Agent 存活语义 = **自动恢复**（回滚必然重启，不是"不中断"）：
`qemu-ga` 随基线固化，启动后**轮询** `guest-ping`（非 `sleep N`），
实测 **16.24–16.29 s** 就绪（三轮方差 < 50 ms）。

### 3.1 base 只读性（隔离的前提，设计 §5.2 待验项）

**独立于工具自检的宿主侧证据** —— 冻结时记录 vs 全部实验结束后：

```
冻结时 : size=68730224640  mtime=2026-09-26 20:27:18.350275342  inode=1418147
结束后 : size=68730224640  mtime=2026-09-26 20:27:18.350275342  inode=1418147
```

**size、mtime（纳秒级）、inode 三者全等** —— 跨越 **6+ 次启动 + 6 次样本执行**，
base **从未被写入一个字节**。

> 机制解释：qcow2 以**只读**方式打开 backing file，全部写入只落覆盖层。
> 这也**证实了设计 §5.2 的推论**：硬断电（`destroy`）不污染基线 ——
> 脏状态只落在**即将被丢弃**的覆盖层里。

## 4. 隔离验证（关键）

### 4.1 实验设计

| 轮次 | 样本 | 产物（实测） |
| :--- | :--- | :--- |
| **A** | `samples/copy.bat` | `C:\poc\samples\work\a.txt`、`work\c.txt`、**`C:\iso-probe\from-a.txt`** |
| **B** | `samples/other.bat` | `C:\poc\samples\work\b-marker.txt`、`payload\b-data.txt`、**`C:\iso-probe\from-b.txt`** |
| **A2** | `samples/copy.bat`（重复） | 同 A |

每轮之间执行**完整回滚**（丢弃覆盖层 + 重建 + 冷启动 + 等 agent）。
清单范围 = `C:\poc` **+ `C:\iso-probe`** —— 后者在 `C:\poc` **之外**，
所以验证的是**整盘 CoW 回滚**，而不是"采集器自己那个目录被清理了"。

### 4.2 三重判据结果

**J1 —— 起点同一性（最强判据）**

```
copy.json        sha256:72d287ebce94b19275ded3c6f5a69babe0f6e4ff2f78dd6638475584421e05df
other.json       sha256:72d287ebce94b19275ded3c6f5a69babe0f6e4ff2f78dd6638475584421e05df
copy-rerun.json  sha256:72d287ebce94b19275ded3c6f5a69babe0f6e4ff2f78dd6638475584421e05df
```

✅ **三次独立运行的起点逐字节相同。** 起点相同 ⇒ 结果之差只能来自样本。

**J2 —— 无跨样本污染**

✅ **3×2 = 6 组有向比对，无任何跨样本残留。** 且给出了正面证据：

| 消失的产物 | 在哪些运行中被确认不存在 |
| :--- | :--- |
| `C:\iso-probe\from-a.txt`、`work\a.txt`、`work\c.txt` | B、A2 |
| `C:\iso-probe\from-b.txt`、`payload\b-data.txt`、`work\b-marker.txt` | A、A2 |

**J3 —— 样本有效性（防空转）**

✅ 三轮 `created` 均为 **3 项**，且全部 ⊆ 各自的 `after_manifest`。
即：样本**确实生效过** —— 否则 J2 会**平凡成立**而什么都证明不了。

### 4.3 重复性

`copy.bat` 跑两次，**退出码 / stdout / 产物集合完全一致**（`exit=0`、`'source-alpha\r\n'`、同样 3 项）。

### 4.4 ⚠️ 为什么不能只看差分（本次的设计级发现）

朴素判据"B 的差分不含 A 创建的文件"**是无效的**。若回滚失败、A 的 `a.txt` 残留：

| | before 清单 | after 清单 | `created` |
| :--- | :--- | :--- | :--- |
| 回滚**成功** | 无 `a.txt` | 无 `a.txt` | `[]` |
| 回滚**失败** | **有** `a.txt` | **有** `a.txt` | `[]` ← **一模一样** |

残留文件在两次运行中都落进 `unchanged`（哈希相同），**差分里根本看不见**。
→ **用差分判隔离会得到系统性假通过。** 这就是必须引入 J1/J2/J3 的原因。

## 5. 计时（如实单列，不偷换概念）

### 5.1 两个指标必须分开

| 指标 | 定义 | 实测 | 判据 |
| :--- | :--- | ---: | :--- |
| **`revert_op_ms`** | **纯回滚操作**（`rm` 覆盖层 + `qemu-img create -b base`） | **74–77 ms** | **< 30 s ✅（余量 390×）** |
| `cycle_ms` | agent 等待开始 → 采集完成 | **32.2 s** | 无判据，**供批量吞吐估算** |

> **本文件的态度**：硬判据按 `revert_op_ms` 判定（这正是任务书"回滚"的字面含义），
> 但 `cycle_ms` 一并如实报出 —— 绝不用"回滚只要 77 毫秒"去掩盖"整轮要 32 秒"。

### 5.2 完整周期分段（三轮实测，方差极小）

| 阶段 | 耗时 | 说明 |
| :--- | ---: | :--- |
| `env_check` | 5.3 s | **含刻意的 5 s DHCP-drop 观测窗口**；纯检查约 0.3 s |
| `revert` | 0.16 s | 停机 + 回滚（停机 0 s，因上轮结束时已停机） |
| `agent_wait` | 16.5 s | 冷启动 → `guest-ping` 就绪 |
| `environment` | 0.54 s | osinfo + agent-info + `chcp` |
| `baseline_manifest` | 3.7–4.4 s | 6 项，含 17 MB MSI 的 SHA256 |
| `upload` | 0.09–0.13 s | 483/596 字节 |
| `execute` | 0.77–1.14 s | 样本本身 |
| `after_manifest` | 9.5–10.6 s | 10 项（比 baseline 慢，残留启动 I/O） |
| **`cycle_ms`** | **32.16–32.33 s** | agent 等待 → 采集完成 |
| `total_ms` | 37.8–38.1 s | 含 env_check |

**批量吞吐估算**：`~32 s + 样本自身执行时间`/样本 → 100 个样本约 **55 分钟**。

### 5.3 停机方式：`destroy` 硬断电可用

按设计 §5.2 的推论，`destroy`（硬断电）**不需要**等待 Windows 优雅关机 ——
脏状态只落**即将被丢弃**的覆盖层。实测 VM 运行中 `destroy` 耗时 **442 ms**。
**优雅关机只在建立基线那一次必要**（保证 base 自身干净）。

## 6. 执行中发现的问题与处置（全部为实测）

### 6.1 🟡 ufw 输出格式陷阱（检查器自己的 bug，两次）

`check_env` 的 ufw 检查**连续两版都是错的**：

| 版本 | 写法 | 错因 |
| :--- | :--- | :--- |
| v1 | `re.search(r"on virbr0\s+ALLOW IN", txt)` | **列顺序反了**：实测 IN 规则的 `on virbr0` 排在 `ALLOW IN` **之前** |
| v2 | 按行匹配 `"virbr0" and "ALLOW IN"` | **字面量错了**：`ufw status`（非 verbose）把入站渲染为 **`ALLOW`**，只有 `status verbose` 才是 `ALLOW IN`；而转发规则两者都是 `ALLOW FWD` |
| **v3（现行）** | `"virbr0" in ln and "ALLOW" in ln and "FWD" not in ln` | ✅ 对两种输出格式都成立 |

> **价值判断**：这两次都是**假失败**（false FAIL），不是假通过。
> 检查器的错误方向是安全的 —— 它宁可拒绝采集，也没有放行一个坏环境。
> **这正是 `check_env` 硬失败设计的意图**（设计 §6.4）：失败必须显式，绝不静默。

### 6.2 🔴 PowerShell「不存在的路径」病理（**导致过一次错误的因果推断**）

**现象**：首次文件清单有时要 **51 s**，有时只要 2.7 s。

**第一次（错误的）归因**：我判断是"Windows 启动 I/O 争用"，并据此把
`--settle-ms` 从 0 改成 10000，还写下"静置不是成本而是净收益"的结论。

**受控实验推翻了它**：

| manifest 范围 | 耗时 |
| :--- | ---: |
| `C:\poc` | **2.7 s** |
| `C:\poc` + **不存在的** `C:\iso-probe` | **39.7 s** |
| `C:\poc` + 不存在的 `C:\iso-probe`（第二次） | 29.6 s |
| `C:\poc`（暖机后） | 2.1 s |

**根因**：`Get-ChildItem -Path` 收到**不存在的路径**会产生 **~30–40 s** 的固定开销
（与 settle、与启动争用**都无关**）。

**这个坑在本场景是必然发生的** —— 探针目录 `C:\iso-probe` 正是被回滚掉的，
所以每次**基线清单**时它都不存在。也就是说：**回滚越干净，这个 bug 越必然触发。**

**处置**：`vm.py::manifest()` 先 `Test-Path -LiteralPath` 过滤不存在的路径。
修复后首次清单稳定在 **3.7–4.4 s**（从 43 s 降下来）。

**再次受控重测 settle**：

| settle | agent就绪→首清单完成 | 首清单 | 次清单 |
| :--- | ---: | ---: | ---: |
| 0 | **21.1 s** | 4.8 s | 11.8 s（抖） |
| 15 s | 34.7 s | 3.4 s | 2.4 s（稳） |

→ **结论反转：settle=0 总周期更短**，静置**不是**净收益。
`--settle-ms` 默认值已改回 **0**；时序稳定性敏感时再开 15000。

> **这次错误的教训**：我在**没有做受控实验**的情况下，把两个同时变化的量
> （settle、scope 是否含不存在路径）中的相关性当成了因果。
> **"看起来合理的机制解释"（启动 I/O 争用）极具欺骗性** —— 它让一个错误的结论显得很有道理。
> 纠错靠的是**单变量受控实验**，不是更仔细地思考。

### 6.3 🔴 J1 判据抓出了它自己的测试设计缺陷

第一次跑 A/B 时，两轮的 `baseline_manifest_hash` **不同**（`b3fa1544…` vs `f7cd1566…`）。

**根因**：baseline 清单在**上传样本之后**采集，所以它天然含各自刚上传的 `.bat`
（`copy.bat` vs `other.bat`）→ 两次运行的"起点"必然不同。

**处置**：把 baseline 清单移到 **`upload` 之前**（采集器动任何东西之前），
并把 `baseline_manifest` **全量存档**（否则 J1 差异无法复核：到底哪个文件不同？）。
修复后 `before_count = 6`（纯环境物），三轮哈希完全一致。

> **这是 J1 判据自己抓出来的** —— 一个能自我证伪的判据，比一个"总是通过"的判据有价值得多。
> 反过来说：**如果当初用的是朴素的差分判据，这个缺陷会完全不可见**（差分两次都是干净的）。

### 6.4 🟡 两处实现小坑

| 坑 | 现象 | 处置 |
| :--- | :--- | :--- |
| argparse | `action="append"` 配 `default=<str>` → `AttributeError: 'str' object has no attribute 'append'` | `default=None`，在 `normalize_scopes()` 里补默认值 |
| PowerShell 条件输出 | 过滤后可能一个路径都不剩 → 必须用 `if($p){...}` 包裹，否则 `ConvertTo-Json` 收到空管道报错 | 已包裹，空结果返回 `{}` |

## 7. 与设计文档的偏离（主动披露）

| # | 设计文档说 | 实测后改为 | 原因 |
| :-- | :--- | :--- | :--- |
| 1 | `--settle-ms` 默认 0 | **保持 0** | 中途曾改为 10000（基于错误归因），受控实验后**改回** —— 见 §6.2 |
| 2 | 方案 D 为"备选" | 保持备选 | 实测 btrfs reflink 可用，但方案 C 更省（193 KiB vs 8 GiB 引用），主选不变 |
| 3 | §5.2 硬断电可用为"**待实测**" | ✅ **已验证** | base 身份全等（§3.1）；`destroy` 442 ms |
| 4 | 设计未提 `--scope` 多路径 | **新增** | 为把探针放在 `C:\poc` 之外，验证**整盘**回滚而非仅目录清理 |
| 5 | 设计未提 `verify.py` | **新增** | J1/J2/J3 必须**可反复跑**，不能靠一次性人工目检 |
| 6 | `results/` 原计划不入仓 | **入仓**（24 KB） | 原始证据比结论摘要更可复核；他人可直接复跑 `verify.py` |

## 8. 遗留问题（如实列出）

| # | 问题 | 影响 | 建议 |
| :-- | :--- | :--- | :--- |
| 1 | **网络外部性不隔离** | 样本对外发包改变对端状态 → 回滚不了 | 批量采集前**必须**定网络策略（断网/黑洞/真实）并写进指纹 |
| 2 | 本工具**不是安全沙箱** | 宿主机侧效应（逃逸类）不隔离 | 定位为**行为观察**设施；若要跑未知恶意样本需另做隔离评估 |
| 3 | 注册表 / 进程 / 网络**未采集** | 23.9% 语料的改系统行为不可见 | 属 L2，见 `collection-design.md` §7 |
| 4 | 读操作 / 瞬时副作用**不可见** | 已在 `poc-result.md` §4.3 实证 | 下一优先级：NTFS last-access + `auditpol` |
| 5 | `input-data`（stdin）方案**未测** | 目前依赖 `< nul` | 对比验证（`collection-design.md` §4.4 S2） |
| 6 | 环境为 **Insider 预发布版 + 审核模式** | 含时间炸弹；非零售行为基线 | 长期采集应换 **LTSC/零售版**（`poc-result.md` §7 #1/#2） |
| 7 | `virsh save`/`restore` 缩短 `cycle_ms` | 未做 | 仅记录；当前 32 s 已够用 |
| 8 | 16.5 s 的冷启动占周期一半 | 未优化 | 若需更快可上 RAM 快照；但冷启动**天然清空进程/内存残留**，是隔离优势 |
| 9 | 覆盖层无大小上限 | 单个样本若写满 64 GiB 会耗尽磁盘 | 每次回滚即删除 → 稳态不增长；批量任务建议加 disk 水位监控 |

## 9. 复现清单

```bash
cd /home/duanjb666/bat2sh/research/behavior-tracking/tools

# 0) 前置：域关机 + 尚未建基线时，一次性建立
virsh -c qemu:///system shutdown win-behavior
python3 collect.py --establish-baseline

# 1) 采集三种本（每轮自动回滚）
python3 collect.py --sample samples/copy.bat  --output results/copy.json \
    --scope 'C:\poc' --scope 'C:\iso-probe'
python3 collect.py --sample samples/other.bat --output results/other.json \
    --scope 'C:\poc' --scope 'C:\iso-probe'
python3 collect.py --sample samples/copy.bat  --output results/copy-rerun.json \
    --scope 'C:\poc' --scope 'C:\iso-probe'

# 2) 验证隔离（J1/J2/J3 + 重复性 + base 只读性）
python3 verify.py results/copy.json results/other.json results/copy-rerun.json

# 3) 独立复核 base 未被写入
sudo stat -c '%s %y %i' /var/lib/libvirt/images/win-behavior.base.qcow2
#   期望：68730224640 2026-09-26 20:27:18.350275342 +0800 1418147
```

## 10. 判定

| 问题 | 答案 |
| :--- | :--- |
| 回滚方案可行？ | ✅ **方案 C（独立 overlay qcow2）**，域 XML 零改动 |
| 回滚速度？ | ✅ **纯操作 74–77 ms**（判据 < 30 s）；完整周期 **32.2 s**（如实单列） |
| 隔离有效？ | ✅ **J1+J2+J3 全通过**，含 `C:\poc` 之外的整盘验证；base 纳秒级未变 |
| 采集脚本可复用？ | ✅ 入仓 `tools/`，CLI 化，环境检查硬失败，失败可诊断 |
| **能批量采了？** | ✅ **能** —— ~32 s/样本，无人工介入 |
| 最大的意外收获？ | **PowerShell「不存在路径」30–40 s 病理** —— 且它曾让我做出一个**错误的因果推断**，靠受控实验才纠正 |
