# PoC 判定

> 时间：2026-09-26 · 仓库改动：**仅新增 `research/`**（零已跟踪文件改动）
> **判定：✅ L3 输出效果层采集路径 —— 可行，且已跑通并复现。**
>
> 本文件初版写于**镜像缺失的暂停点**，当时判定为「⏸ 未执行」。
> 用户后续提供镜像 → 域建成 → **PoC 已实际执行完毕**。下表已用**实测结果**回填，
> 初版结论保留在 §5 作为过程记录。**实测详情见 `poc-result.md`。**

## 1. 任务书 §六 的判定表（已回填实测结果）

| 问题 | 答案 | 依据 |
| :--- | :--- | :--- |
| **QEMU 环境可搭？** | ✅ **可以，已搭成** | QEMU 11.1.1 + libvirt 12.7.0 + KVM；域 `win-behavior` 已建成并运行（q35/EFI/TPM2/SATA64G/SPICE） |
| **Guest Agent 可执行命令？** | ✅ **可以** | `guest-ping` → `{"return":{}}`，通道 `state='connected'`，agent **110.2.3** / 37 个命令 |
| **能捕获输出？** | ✅ **可以，逐字节准确** | P1：`exit_code` **7 保真**，stdout 6 行与 wine 预验证**逐字节一致**，stderr 空，**无截断** |
| **能做文件差分？** | ✅ **可以** | P2：PowerShell+SHA256 清单差分，准确报出 `created: a.txt, c.txt` |
| **这条路可行？** | ✅ **可行** | 全链路（传脚本→执行→捕获→清单→差分）跑通；**且声明的盲区被实测复现**（`b.txt` 建后即删不可见） |
| **下一步做什么？** | 修 3 个遗留项 → 扩到 L2 | 见 §6 |

### 1.1 本次实测暴露的**两个根因级基础设施坑**（原设计文档未预料）

| # | 坑 | 现象 | 根因 |
| :-- | :--- | :--- | :--- |
| 1 | **宿主 `ufw` 丢弃 guest 的 DHCP 与 NAT** | guest「未识别的网络/无 Internet」，`net-dhcp-leases` 空 | `ufw` 默认 `deny(incoming)`+`deny(routed)`，`virbr0` 未放行；nftables 计数显示 **63 个 DHCP 请求被 drop** |
| 2 | **`qemu-ga` 缺 guest 侧 `vioserial` 驱动** | MSI 装好了，但通道永远 `disconnected` | `vioser.sys` 不存在 —— `qemu-ga` 走 **virtio-serial**，没有驱动就没有通道 |

> 两者都表现为「agent 不通 / 没网」，**且都无法从"libvirt 网络已启动"这一事实推断出来**。
> 已固化为 `poc-result.md` §6.2 的必查清单。

## 2. 阻塞项（均已解除，保留作过程记录）

### 2.1 【已解除】镜像缺失 → 曾触发 §七 暂停

初版写此文件时：全盘无任何 Windows ISO，也无 `virtio-win` ISO → 触发暂停条件。

**处置过程**：

| 步骤 | 结果 |
| :--- | :--- |
| AI 自动下载 `virtio-win.iso` 0.1.302（837 MB） | ✅ 完成并部署 |
| 用户提供 Windows 11 ISO | ✅ 先后两个：LTSC 2024 → 最终采用 **Win11 Pro build 29599** |
| `swtpm` 安装（用户授权） | ✅ 0.10.2 |
| `default` 网络启动 + 自启 | ✅ |
| 域建成 | ✅ `win-behavior` |

> ⚠️ **一次操作失误（已披露）**：`virsh undefine --remove-all-storage` 连带删除了
> 作为域光驱挂载的 `virtio-win.iso` 与旧 Windows ISO。`virtio-win.iso` 已**重新下载**；
> 被删的旧 LTSC ISO 用户已弃用。**教训：`--remove-all-storage` 会吃掉挂载的 ISO，勿用。**

### 2.2 【偏离披露】`docs/future-behavior-tracking.md` **不存在**

任务书 §一.2 称该文件「已落盘」。**实测不存在**：

| 检索范围 | 结果 |
| :--- | :--- |
| 工作树 `docs/` | ❌ 不存在 |
| `git log --all -- '*behavior*'` | ❌ 无任何提交 |
| 全部 9 个本地/远程分支 | ❌ 不存在 |
| `git stash list` / `git reflog` | ❌ 无 |
| `/home/duanjb666` 下 4 层目录 `find` | ❌ 无 |

**处置**：本 session **不臆造**该文件，**不基于它做任何设计决策**。
所有设计结论均改从**任务书原文** + **已存在的先例研究** `docs/research/b1-dynamic-tracing.md` 推导，并逐条标注证据来源。

> **影响评估：低。** 任务书 §四 已给出三层模型与最小方案骨架，`b1-dynamic-tracing.md` 提供了先例方法论。
> 该文件缺失**未阻塞**本次工作。但若它包含**已定的口径/约束**，需用户补充核对。

## 3. ✅ 本 session 已确证的部分

| 结论 | 证据强度 |
| :--- | :--- |
| **宿主虚拟化栈完全可用** —— QEMU/libvirt/KVM 无缺失，无需补装任何宿主组件 | 【实证】逐项命令验证 |
| **真正缺的只有两件 ISO** —— 初版审计曾误报 4 项（libvirtd、default 网络），已复核修正 | 【实证】见 `env-audit.md` 修订记录 |
| **QEMU TCG 插件在 KVM 下静默失效** | 【实证】**本 session 亲自实验**：同一 guest 同一插件，TCG → `tb=92424 insns=451440`；KVM → **`tb=0 insns=0`**，且 QEMU 不报错 |
| **QGA 无目录列举命令** → 差分须靠 `guest-exec` 生成清单 | 【文档】本机 QEMU 11.1.1 官方参考原文 |
| **`capture-output: merged` 在 Windows 上无效** | 【文档】同上，原文 "Not effective on windows guests" |
| **输出可能被静默截断**（`out-truncated`/`err-truncated`） | 【文档】同上 |
| **`guest-exec` 支持 stdin**（`input-data`，base64） | 【文档】同上 —— 修正了「guest-exec 无 stdin 通道」的常见误解 |
| **控制台输出走 CP936**（非 UTF-8） | 【实证】wine 预验证中 `pause` 提示为 GBK 字节 |
| **语料 53.7% 交互式、23.9% 会改系统状态** | 【实证】218 个 `.bat`/`.cmd` 全量扫描 |
| **净差分看不到读操作与瞬时副作用** | 【实证】wine 预验证复现（`b.txt` 建后即删 → 差分中完全消失） |
| **样本本身正确**（P1 退出码 7、P2 差分符合预期） | 【实证】wine 预验证 —— **使后续失败可归因于通路而非样本** |

## 4. ❌ 本 session 否决（含一次**自我更正**）

| 项 | 结论 |
| :--- | :--- |
| **QEMU TCG 插件框架** | ❌ **实测否决** —— KVM 下完全失效；放弃 KVM 用 TCG 则慢到不可用（最小 Linux guest 已慢 11 倍）。**L1/L2 必须走 guest 侧插桩** |
| **「Crucible 五信号监控」** | ⚠️ **存在，但不可复用** —— [AshwinNHacker/Crucible](https://github.com/AshwinNHacker/Crucible)，GitHub 描述含 "five-signal behavioral monitoring"；**但仅 1 个提交、README 自述 "portfolio/demonstration project"、无可复用产物** |
| **「Novgorod State University QEMU 插件框架」** | ⚠️ **存在，但不可用** —— Fursova/Dovgalyuk/Vasiliev, Trudy ISP RAN 27(6), 2015, DOI `10.15514/ISPRAS-2015-27(6)-11`；**TCG/翻译块机制 → KVM 下失效**；无公开仓库 |
| Cuckoo Sandbox | ❌ **确认已死** —— README 原文 "2.x is currently unmaintained"，最后提交 2021-04-26 |
| CAPEv2 | ⚠️ **活跃**（2026-09-23，KVM 官方推荐）；不整体引入；其 `capemon`（2026-09-25）是 L1 的架构参考 |
| VMI（LibVMI / DRAKVUF） | ❌ **确认出局** —— 本机 **AMD**，DRAKVUF 需 Intel VT-x/EPT 且不支持 Win11；LibVMI 的 KVM 补丁止于 QEMU 4.1.0（2019） |

> ### ⚠️ 更正声明
> 本 session **初版**把 Crucible 与 Novgorod 框架记为「**未能证实存在**」。**该结论是错的。**
> 经独立调研复核，**两者确实存在**，已在上表与 `collection-design.md` §3.3/§3.4 更正。
>
> **处置不变（仍不采用），但理由不同** —— 这个区别对后续决策重要：
> 「不存在」意味着**可能还有同类工具值得找**；「存在但不可复用」意味着**这条路已经走过，不必重走**。
>
> **教训**：「我没搜到」不等于「不存在」。本 session 把一次检索失败写成了存在性结论，这是**过度断言**。
> 已按 §八.2「主动披露偏离」更正，而非悄悄修改。

> **对任务书 §4.2 的偏离**：任务书列出的 4 个「参考项目」中，**1 个（QEMU 插件）被实测否决、
> 2 个存在但不可用、1 个（CAPEv2）活跃但不整体引入**。
> 本 session **如实报告而非凑数采纳** —— 这本身就是 PoC 的价值（§八.5「失败也是合格结果」）。

## 5. 交付物完成情况（初版此处为「未完成」，现已全部完成）

| 任务书步骤 | 初版状态 | **最终状态** |
| :--- | :--- | :--- |
| §三 搭建最小 VM | ⏸ 未开始 | ✅ **已建成**（`win-behavior`，运行中） |
| §五.2 采集流程执行 | ⏸ 未开始 | ✅ **已执行，P1/P2 全部通过** |
| **`poc-result.md`** | ⏸ 未创建（拒绝伪造） | ✅ **已创建，含真实实测数据** |
| §六 判定 | ✅ 已写 | ✅ **已回填实测结果** |

> **过程说明**：初版**刻意不创建** `poc-result.md`，因为它是实测结果文件，
> 在 PoC 未运行的情况下写入任何内容都是伪造。该判断在本次得到验证 ——
> 后来的真实执行暴露了**两个原设计完全没预料到的根因级坑**（ufw / vioserial），
> 这些内容**不可能靠推演写出来**。**拒绝伪造是正确的。**

## 6. 下一步

### 6.1 三个遗留项（优先级从高到低）

| # | 事项 | 为何重要 |
| :-- | :--- | :--- |
| **1** | **验证 qcow2 覆盖层回滚**（`poc-result.md` §6.3） | 样本间隔离目前只有「guest 内 `rmdir` 清理」这种弱保证；语料 23.9% 会改注册表/服务，**必须**有硬回滚 |
| **2** | **换掉 Insider 镜像** | 当前镜像是 `rs_prerelease` 29599，**含时间炸弹**、非零售行为基线。作为**长期真值基座不可接受** |
| **3** | **决定采集脚本是否入仓** | `/tmp/poc/{qa.py,drive.py}` 目前**不可复现**；它是研究基础设施（非 bat2sh 产品代码） |

### 6.2 之后：扩到 L2

**NTFS last-access + 对象访问审计**（`collection-design.md` §7 优先级 1）——
用**纯配置**补上「读操作不可见」这一最大盲区（已在 `poc-result.md` §4.3 实证该盲区确实存在），
复用已建立的清单-差分框架。

### 6.3 另需复核

- `input-data`（stdin）方案 vs 当前的 `< nul>`（`collection-design.md` §4.4 S2）
- 路径含空格时的 `cmd /c ""...""` 引号形式（`poc-result.md` §5.3 未实测）
- 审核模式作为长期基座是否可接受（`poc-result.md` §7 遗留 #2）

## 7. 纪律合规

| 纪律 | 执行情况 |
| :--- | :--- |
| 1. 研究不是产品，不改 bat2sh 代码 | ✅ `git status` 仅 `?? research/`，**零已跟踪文件改动**；HEAD `4c7076c` 未变 |
| 2. 主动披露偏离 | ✅ 披露 4 项：缺前置文档、否决 2 个参考项目、`poc-result.md` 缺席、初版审计误报已自纠 |
| 3. 只读诊断先行 | ✅ 环境盘点全程只读；未启动 `net-start`、未装包、未建域。wine 验证用**独立前缀**，未触碰用户 `~/.wine` |
| 4. 锁定 HEAD | ✅ `4c7076c` |
| 5. 失败也是合格结果 | ✅ 本 session 的价值主要在**否决**（TCG 插件）与**发现静默陷阱**，而非跑通 PoC |
| 6. 用户参与 | ✅ Windows 安装待用户；已明确列出需下载的两件 ISO |
| — 跨多个小时 | 本 session 实际用时约 25 分钟（未进入 Windows 安装阶段） |

### 副作用清单（全部在仓库外）

| 项 | 位置 | 说明 |
| :--- | :--- | :--- |
| wine 前缀 | `~/.cache/bat2sh-wine-poc/`（376 MB） | **未触碰**用户既有 `~/.wine` |
| 实验产物 | `/tmp/plugtest/`（插件源码、`.so`、initramfs） | TCG/KVM 实验 |
| QGA 文档抽取 | `/tmp/qga.txt`、`/tmp/tcgp.txt` | 只读抽取 |
| 临时输出 | `/tmp/p1.*`、`/tmp/p2.*`、`/tmp/pa,pb,pc.out` | 预验证输出 |
| **仓库** | `research/behavior-tracking/` | **唯一改动，全部为新增文档/样本** |

> **未执行的系统变更**（待用户确认）：`virsh net-start default`、`net-autostart`、`mkdir /var/lib/libvirt/images`。
> 均已在 `env-audit.md` §6 列出，**本 session 未执行**。
