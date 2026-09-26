# 采集框架设计：三层行为采集

> 时间：2026-09-26 · 状态：**设计定稿，L3 待 VM 就绪后执行**
> 前置：`env-audit.md`（宿主栈健康，仅缺 ISO）
> 证据分级：**【实证】**= 本 session 在本机亲自验证；**【文档】**= 本机 QEMU 官方文档原文；**【知识】**= 通用知识，**未在本 session 验证**（下一 session 需复核）

## 1. 目标与范围

为 bat2sh 的**静态转换结果**提供**运行时行为真值**：让 `.bat` 在**真实 Windows** 上执行，记录它到底做了什么，再与转换后 `.sh` 的行为对比。

**本文档覆盖三层采集的完整设计**，但**本 session 只实现 L3（输出效果层）**。
理由见 §5：L3 不需要内核代码、不需要 guest 侧开发，是**最快的可行性判据**。

**明确不做**：不改 bat2sh 任何代码（研究基础设施，不是产品功能）。

## 2. 三层采集模型

| 层 | 观测对象 | 回答的问题 | 本 session |
| :-- | :--- | :--- | :--- |
| **L1 API 调用** | Win32 / NT API（`CreateFileW`、`RegSetValueExW`…） | 脚本调用了哪些**语义操作**？ | ⏸ 下一 session |
| **L2 系统调用 / 内核 I/O** | syscall、文件/注册表/网络 I/O | 实际**触达**了哪些资源？ | ⏸ 下一 session（部分可由 L3 近似） |
| **L3 输出效果** | stdout / stderr / 退出码 / 文件系统差分 | **可观测的最终结果**是什么？ | ✅ **本 session** |

三层的价值递增但成本也递增。L3 单独就能支撑「转换后的 `.sh` 是否产生同样的可见结果」这一核心判据。

## 3. 工具调研与评估

### 3.1 QEMU TCG 插件框架 —— ❌ **实测否决**（本 session 最重要的工具结论）

任务书 §4.2 把「QEMU 插件」列为 L1 候选。**本 session 做了决定性实验**：

**装置**：最小 Linux guest（静态 `init`，`/boot/vmlinuz-linux-cachyos` + 自制 initramfs），
自建 QEMU 插件（`qemu-plugin.h`，注册 `tb_trans` / `syscall` / `atexit` 计数器），
**同一 guest、同一插件，只切换加速器**：

```bash
# TCG（软件模拟）
qemu-system-x86_64 -accel tcg -cpu max -m 512 -kernel /boot/vmlinuz-linux-cachyos \
  -initrd tiny.cpio.gz -append "console=ttyS0 rdinit=/init" \
  -display none -serial stdio -no-reboot -plugin ./plug.so
# → PLUGIN_RESULT tb=92424 insns=451440 syscalls=0
# → 客户机启动耗时 2.66 s

# KVM（硬件加速）
qemu-system-x86_64 -accel kvm -cpu host -m 512 -kernel /boot/vmlinuz-linux-cachyos \
  -initrd tiny.cpio.gz -append "console=ttyS0 rdinit=/init" \
  -display none -serial stdio -no-reboot -plugin ./plug.so
# → PLUGIN_RESULT tb=0 insns=0 syscalls=0     ← 完全失效
# → 客户机启动耗时 0.24 s（快 11 倍）
```

| 加速器 | 插件加载 | 插桩回调 | 结论 |
| :--- | :--- | :--- | :--- |
| TCG | ✅ | **tb=92424，insns=451440** | 有效 |
| **KVM** | ✅（QEMU **不报错、不警告**） | **tb=0，insns=0** | **完全失效** |

> **⚠️ 这是本次调研最重要的发现，且是一个"沉默的陷阱"**：
> KVM 下 QEMU **照常加载插件、不报任何错**，插件只是**永远不会被调用**。
> 一个不知情的实现者会得到「插件跑通了、输出是空的」的结论，并误以为**被观测的脚本什么都没做**。
> 这类**静默失败**会直接污染研究结论。

**机制**：TCG 插件插桩的是 **TCG 翻译块（translation block）**。KVM 下客户机指令由 CPU 直接执行，
**没有翻译过程**，因此没有插桩点，插件的 `install` 被调用后再无任何回调。

**含义**：

| 选项 | 可行性 |
| :--- | :--- |
| Windows + KVM + TCG 插件 | ❌ 插件失效 |
| Windows + TCG（放弃 KVM） | ❌ **不实用** —— 本实验最小的 Linux guest 已慢 11 倍；完整 Windows 10 启动/执行会慢到无法接受 |
| Windows + KVM + 其他机制 | ✅ 必须走 **guest 侧插桩**（§3.6、§7） |

**结论：QEMU TCG 插件路线对本项目不可用。** 这一条同时**否决了基于同一机制的第三方框架**
（包括任务书提到的「Novgorod State University QEMU 插件框架」，若其确实基于 TCG 插件 API）。

### 3.2 Cuckoo Sandbox / CAPEv2

| 项 | 评估 |
| :--- | :--- |
| Cuckoo Sandbox | **已停止维护**（原项目多年无更新），被 CAPEv2 取代。不建议作为基础。〔知识，待复核〕 |
| CAPEv2 | 活跃维护的社区 fork，是当前开源 Windows 动态分析的事实标准，**功能上远超本项目需求**。 |
| 与本项目的关系 | 它解决的是**恶意样本分析**（反沙箱、持久化、C2 提取）；我们要的是**行为真值**（脚本做了什么 I/O）。**目标不同，但底层机制高度重叠**。 |
| 可直接用？ | ⚠️ **不建议整体引入**。它是重量级编排系统（数据库、结果服务器、Web UI、多 VM 调度），引入成本远高于 PoC 收益。 |
| 值得借鉴的部分 | **它的 guest 侧设计**：CAPEv2 在 guest 内注入 monitor DLL 挂钩 NT API，这正是绕过 §3.1 TCG 墙的**正确机制**（guest 侧插桩而非宿主侧插桩）。**这是 L1 层的首选借鉴对象。** |
| 许可 | GPL 系（CAPEv2 为 GPL-3.0）〔知识，待复核〕。用作**参考设计**不受影响；若**链接/分发**则需评估与 AGPL-3.0 的兼容性。 |

> **结论：不作为依赖引入，作为 L1 层的架构参考。**

### 3.3 "Crucible"（任务书提到的「五信号监控」）

**未能证实。** 本 session 未能找到名为 "Crucible"、以「五信号监控」为特征的沙箱/行为分析项目。〔知识，待复核〕

已知同名物是 Trail of Bits 的 **Crucible**（Rust 模糊测试框架），与「五信号监控」无关。

> **处置：不纳入设计。** 若用户能提供出处（论文/仓库链接），下一 session 复核后重新评估。
> **本 session 不基于该未证实引用做任何设计决策。**

### 3.4 "Novgorod State University QEMU 插件框架"

**未能证实。** 未找到该名称的公开框架。〔知识，待复核〕

> **处置：不纳入设计。** 且如 §3.1 所示，**任何基于 QEMU TCG 插件 API 的方案在本项目场景下都不可用**，
> 因此即使该框架存在，**也需先回答"它是否支持 KVM"**，否则同样出局。

### 3.5 VMI（虚拟机自省）

LibVMI / DRAKVUF / Volatility 系：从**宿主机外部**读取 guest 内存，**无需 guest 侧 agent**，理论上最干净。

| 优点 | 缺点 |
| :--- | :--- |
| 无 guest 侧足迹（脚本无法察觉被观测） | 需要 **guest 内核符号/调试信息**，Windows 10 支持脆弱 |
| 抗规避 | DRAKVUF 主要面向 **Xen**；KVM 支持有限且需特定 QEMU 版本〔知识，待复核〕 |
| 可覆盖 L1+L2 | **工程量最大**，与"最小 PoC"目标冲突 |

> **结论：本 session 不采用；留作 L1/L2 的长期备选。**

### 3.6 QEMU Guest Agent（QGA）—— ✅ **本 session 选用**

宿主侧**已就绪**（`virsh qemu-agent-command` 可用），无需宿主侧开发。
语义**来自本机 QEMU 11.1.1 官方文档原文**（`/usr/share/doc/qemu/qemu/interop/qemu-ga-ref.html`）。

**完整命令清单（已核对，无遗漏）**：
`guest-sync`、`guest-ping`、`guest-get/set-time`、`guest-info`、`guest-shutdown`、
`guest-file-{open,close,read,write,seek,flush}`、`guest-fsfreeze-{status,freeze,freeze-list,thaw}`、
`guest-fstrim`、`guest-suspend-*`、`guest-network-get-{interfaces,route}`、
`guest-get/set-vcpus`、`guest-get-disks`、`guest-get-fsinfo`、`guest-set-user-password`、
`guest-get/set-memory-blocks`、**`guest-exec` / `guest-exec-status`**、
`guest-get-{host-name,users,timezone,osinfo,devices,diskstats,cpustats,load}`、
`guest-ssh-{get,add,remove}-authorized-keys`

**⚠️ 关键缺口：【文档】QGA 没有任何「目录列举」命令。**
`guest-file-*` 只能对**已知路径**做 open/read/write/seek/flush，**无法枚举目录**。
→ **文件系统差分必须靠 `guest-exec` 在 guest 内跑命令生成清单**（§4.3）。

## 4. 最小采集方案（L3 输出效果层）

### 4.1 整体流程

```
 快照恢复（干净基线）
      ↓
 [基线清单]  guest-exec: 生成目标目录的文件清单 → 读回
      ↓
 [传脚本]    guest-file-open/write/close（或 base64 写入）
      ↓
 [执行]      guest-exec: cmd.exe /c "script.bat" < nul
      ↓
 [轮询]      guest-exec-status（out-data 仅在进程退出后才填充 → 必须轮询）
      ↓
 [后置清单]  同样方式生成 → 读回
      ↓
 [差分]      两个清单对比 → filesystem 变化
      ↓
 [指纹]      JSON（stdout/stderr 存 base64 + 解码文本 + 退出码 + 差分）
```

### 4.2 `guest-exec` 语义（【文档】，逐条核实）

| 字段 | 语义 | 对本项目的意义 |
| :--- | :--- | :--- |
| `path` | 可执行文件路径 | `cmd.exe`（**注意：需绝对路径或 PATH 可达**） |
| `arg` | **字符串数组**，直接作为 argv | **没有 shell**。`<`、`>`、`\|` **不会被解释** —— 除非整个字符串交给 `cmd /c` 这一层 |
| `input-data` | **base64，写入进程 stdin** | ✅ **stdin 是支持的**（比 `< nul` 更干净） |
| `capture-output` | bool 或 mode 枚举 | 见下 |
| 返回 | `pid` | 需再查 `guest-exec-status` |

**`capture-output` 模式（QEMU 8.0+）**：`none` / `stdout` / `stderr` / `separated` / `merged`

> **⚠️ 文档原文：`merged` —— "Not effective on windows guests."**
> 因此**在 Windows 上必须用 `separated`**（或旧式 `flag: true`）来同时拿到 stdout 和 stderr。
> 这是一个**只在 Windows guest 上才暴露的坑**。

**`guest-exec-status` 返回**（【文档】）：

| 字段 | 语义 | 用途 |
| :--- | :--- | :--- |
| `exited` | 是否已终止 | **轮询条件** |
| `exitcode` | 正常终止时的退出码 | → 指纹 `exit_code` |
| `signal` | 异常终止码（**Windows 上 = 未处理异常码**） | → 崩溃检测（如 `0xC0000005` 访问违例） |
| `out-data` | base64 stdout，**仅在进程退出后才填充** | → 指纹 `stdout` |
| `err-data` | base64 stderr，同上 | → 指纹 `stderr` |
| **`out-truncated`** | **stdout 因大小限制未完整捕获** | **⚠️ 必须检查** |
| **`err-truncated`** | **stderr 因大小限制未完整捕获** | **⚠️ 必须检查** |

> **静默截断是本方案的第二个陷阱**：输出超限时 QGA **不报错**，只是截断并置 `*-truncated`。
> **不检查该标志，指纹会静默丢失输出**，且丢失方式不可预测。→ 指纹中**必须记录**这两个布尔值。

### 4.3 文件系统差分（§3.6 缺口的解法）

因 QGA **无目录列举命令**，差分必须在 guest 内生成清单。两种做法：

| 方案 | 命令 | 评价 |
| :--- | :--- | :--- |
| **D1（推荐）** | `powershell -NoProfile -Command "Get-ChildItem -Recurse -Force \| Select FullName,Length,LastWriteTime \| ConvertTo-Json"` | **结构化 JSON**，**不受系统语言影响**。Win10 LTSC 自带 PS 5.1 |
| D2 | `cmd /c dir /s /b /a` | 简单，但**输出是本地化文本**（中文 Windows → 中文表头），解析脆弱，且**无大小/时间** |

> **选 D1。** 理由：**被测脚本是 cmd/bat，但采集工具不必是**。
> 用 PowerShell 产出 JSON 可以**彻底规避本地化文本解析**这个长期维护陷阱。

**差分的前置条件**：先 `guest-fsfreeze-freeze` 再生成清单、`guest-fsfreeze-thaw` 后执行，
保证清单反映**落盘状态**而非 in-flight 缓存。参照实现：先 freeze → 清单 → thaw → 执行 → freeze → 清单 → thaw。

**已知盲区（净差分的固有边界，见 `poc-samples.md` §5）**：

| 不可见 | 说明 |
| :--- | :--- |
| **读操作** | `type`、`copy` 源、`if exist` 探测 —— 净差分无痕迹 |
| **瞬时副作用** | 建后即删的文件（P2 的 `b.txt` —— **已在 wine 实证复现**） |
| **同内容覆写** | 内容不变的重写 |
| 纯内存计算 | 无文件副作用（如 P3 的递归） |

> **这是 L3 的天花板，不是 bug。** 跨过它需要 guest 侧插桩（§7）。

### 4.4 交互处理

语料 **53.7% 交互式**（含 `pause`/`set /p`，见 `poc-samples.md` §2.1）。两条路：

| 方案 | 做法 | 评价 |
| :--- | :--- | :--- |
| **S1（本 session 选用）** | `arg: ["/c", "script.bat < nul"]` —— `cmd.exe` 会解释 `/c` 字符串内的重定向 | 一行解决；**已在 wine 实证**（`pause` 立即返回） |
| S2 | `input-data: ""`（base64 空串）→ stdin 立即 EOF | ✅ **语义更干净**（不依赖 shell 重定向），**下一 session 优先验证** |
| S3 | 剥离 `pause` 行 | ❌ **篡改被测对象**，破坏真值语义 |

> **采用 S1**，S2 作为下一 session 的一等候选。
> 副作用：stdout 会多一行 `请按任意键继续. . .`（**本地化文本**）→ 指纹归一化时按白名单剔除。

### 4.5 编码

【实证】`cmd.exe` 内建输出走**控制台代码页**（zh-CN → **CP936**），与脚本文件编码**无关**。
→ `out-data` 的 base64 原始字节**必须按 CP936 解码**。（在 wine 预验证中看到 `pause` 提示的 GBK 字节序列，实证此点。）

**处置**：指纹**同时**存 ① base64 原文 ② 解码文本。
**绝不**只存解码结果 —— 解码是有损的，代码页判断错误时原文是唯一的救回途径。

### 4.6 快照策略（必需，非优化）

语料 **23.9%** 会改注册表/服务/用户账户（`poc-samples.md` §2.1）。
**没有快照回滚，第二个样本就被第一个污染。**

```bash
virsh --connect qemu:///system snapshot-revert win-behavior clean   # 每个样本前
```

**要求**：装完 Windows + VirtIO 驱动 + `qemu-ga` 后，**立即打 `clean` 快照**（见任务书 §三.3）。
每个样本执行前必须 revert，保证样本间**零串扰**。

## 5. 行为指纹 schema

```json
{
  "schema_version": 1,
  "script": {
    "name": "poc-01-stdout.bat",
    "sha256": "…",
    "source": "repo:research/behavior-tracking/samples/",
    "license": "AGPL-3.0"
  },
  "environment": {
    "guest_os": "Windows 10 IoT Enterprise LTSC 2021",
    "guest_agent_version": "…",
    "console_codepage": 936,
    "snapshot": "clean",
    "qemu": "11.1.1"
  },
  "execution": {
    "argv": ["cmd.exe", "/c", "poc-01-stdout.bat < nul"],
    "exit_code": 7,
    "signal": null,
    "duration_ms": 123,
    "out_truncated": false,
    "err_truncated": false
  },
  "stdout": { "b64": "…", "text_cp936": "…" },
  "stderr": { "b64": "", "text_cp936": "" },
  "filesystem": {
    "method": "manifest-diff-v1",
    "created": ["C:\\poc\\work\\", "C:\\poc\\work\\a.txt"],
    "modified": [],
    "deleted": [],
    "unchanged_count": 2,
    "blind_spots": ["reads", "transient-effects", "metadata-only-writes"]
  },
  "process": [],
  "network": [],
  "notes": []
}
```

**设计要点**：

| 决策 | 理由 |
| :--- | :--- |
| `stdout` 存 `b64` **与** `text_cp936` | 解码有损，原文必须保留（§4.5） |
| `execution.out_truncated` / `err_truncated` | 静默截断必须显式记录（§4.2） |
| `execution.signal` | Windows 未处理异常码 ≠ 退出码，捕获需分开 |
| `filesystem.blind_spots` **写进指纹** | **主动声明能力边界**，防止下游把"没看到"误读为"没发生" |
| `environment.console_codepage` | 编码解释依赖它，不复现则指纹不可比 |
| `process` / `network` 留空数组 | 本 session 不采集，**但保留字段占位**，避免未来 schema 破坏性变更 |
| `schema_version` | 指纹要长期存档，必须可演进 |

> **`blind_spots` 是最重要的一个字段。** 研究基础设施最大的风险不是采不到数据，
> 而是**采到了不完整的数据却以为完整**。把边界写进数据本身，是对抗这种误读的唯一可靠办法。

## 6. 能力边界（本 session 方案明确做不到什么）

| 做不到 | 原因 | 影响 |
| :--- | :--- | :--- |
| 观测**读**操作 | 净差分 | 无法区分"读了 a.txt"与"没碰 a.txt" |
| 观测**瞬时**副作用 | 净差分 | 建后即删完全隐形（**已实证**） |
| 观测 L1 API 调用 | 无 API hook | 无法回答"用了 `CreateFileW` 还是 `_open`" |
| 观测 L2 syscall | 无内核插桩；**TCG 插件在 KVM 下失效（实证）** | 无法拿到系统调用序列 |
| 观测注册表/服务变化 | 不在本 session 范围 | 23.9% 语料的关键行为会缺失 |
| 抗规避 | 无 | 若脚本检测沙箱并改变行为，指纹不可信（本场景为正常脚本，风险低） |

## 7. 下一 session（L1 / L2）的可选路线

按**性价比排序**（均为绕过 §3.1 TCG 墙的 guest 侧方案）：

| 优先级 | 路线 | 覆盖 | 成本 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **NTFS last-access + 对象访问审计**（`fsutil behavior set disablelastaccess 0`、`auditpol`） | L2（读操作） | **低** —— 配置 + 解析事件日志，**无需内核代码** | **直接补上 §4.3 最大盲区**，是当前方案最自然的延伸 |
| **2** | **注册表差分 / 进程差分** | L2 近似 | 低 | 复用 L3 的清单-差分框架，只换清单生成器 |
| **3** | **ETW（Windows 事件追踪）** | L1/L2 | 中 | 系统自带、无须注入；`Microsoft-Windows-Kernel-File` provider 可给文件 I/O |
| **4** | **CAPEv2 的 monitor DLL 思路**（guest 侧 NT API hook） | L1 | 高 | **架构上正确**（§3.2），但工程量大 |
| **5** | VMI（LibVMI/DRAKVUF） | L1+L2 | 最高 | 抗规避但 Windows 10 支持脆弱 |

> **建议**：下一 session 从**优先级 1** 开始。它用**纯配置**补上最大盲区，
> 且**复用本 session 已建立的清单-差分框架**，不引入新的架构风险。

## 8. 结论

| 问题 | 答案 |
| :--- | :--- |
| 三层模型是否成立？ | ✅ 成立，且**成本差异巨大** —— 必须先做 L3 |
| QEMU TCG 插件可用？ | ❌ **实测否决**（KVM 下静默失效，§3.1） |
| 任务书提到的 Crucible / Novgorod 框架？ | ❌ **未能证实**，不纳入设计（§3.3、§3.4） |
| Cuckoo / CAPEv2？ | ⚠️ 不整体引入；**借鉴其 guest 侧插桩思路**用于 L1（§3.2） |
| 最小 PoC 用什么？ | ✅ **QGA `guest-exec` + PowerShell 清单差分**（§4） |
| 最大风险？ | ⚠️ **静默失败**：KVM 插件空转、输出截断、净差分盲区 —— 三者都表现为「看起来正常」 |

> **本设计最重要的产出不是流程图，而是三个"沉默陷阱"的清单**（§3.1、§4.2、§4.3）。
> 研究基础设施的失败模式几乎总是"安静地给出不完整的数据"。
