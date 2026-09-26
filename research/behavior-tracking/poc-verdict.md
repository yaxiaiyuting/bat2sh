# PoC 判定

> 时间：2026-09-26 · HEAD：`4c7076c`（锁定未变）· 仓库改动：**仅新增 `research/`**
> **判定：⏸ 暂停 —— PoC 未执行。阻塞项为镜像缺失（任务书 §七 明列的暂停条件）。**

## 1. 任务书 §六 的判定表

| 问题 | 答案 | 依据 |
| :--- | :--- | :--- |
| **QEMU 环境可搭？** | ✅ **可以** | QEMU 11.1.1 + libvirt 12.7.0 + KVM 全部就绪；磁盘 681.6 GiB；`virt-install`/`virtiofsd`/`dnsmasq`/`spice` 齐备（`env-audit.md`） |
| **Guest Agent 可执行命令？** | ⏸ **待验证** | 宿主侧 `virsh qemu-agent-command` 已就绪；**guest 侧 `qemu-ga` 需 `virtio-win` ISO 才能安装** → 未安装，通路未跑通 |
| **能捕获输出？** | ⏸ **待验证**（设计已定，未执行） | 语义已从本机 QEMU 官方文档逐条核实（`collection-design.md` §4.2）；**未在 Windows 上实测** |
| **能做文件差分？** | ⏸ **待验证**（并已发现关键约束） | **QGA 无目录列举命令** → 须在 guest 内生成清单（`collection-design.md` §4.3）；未实测 |
| **这条路可行？** | 🟡 **部分可行，但一个主要候选被否决** | 见 §3、§4 |
| **下一步做什么？** | **用户提供两件 ISO** → 建域 → 跑通 L3 → 再评估 | 见 §6 |

## 2. 两个阻塞项

### 2.1 【预期内】Windows 镜像缺失 → 触发 §七 暂停

| 缺什么 | 状态 |
| :--- | :--- |
| Windows 10 IoT Enterprise LTSC 2021 ISO（~9.4 GB） | ❌ 全盘未找到任何 `*.iso` |
| `virtio-win` ISO（提供 virtio 驱动 + guest 侧 `qemu-ga`） | ❌ 未找到 |

→ **这是任务书 §七 明列的暂停条件。PoC 无法执行，需用户下载。**

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

## 5. ⏸ 未完成（因阻塞而未执行）

| 任务书步骤 | 状态 | 原因 |
| :--- | :--- | :--- |
| §三 搭建最小 VM | ⏸ 未开始 | 缺 ISO；且 **Windows 安装需用户交互**（§八.6） |
| §五.2 采集流程执行 | ⏸ 未开始 | 依赖 VM |
| **`poc-result.md`** | ⏸ **未创建** | **不伪造结果**。待 VM 就绪、真实采集完成后写入 |
| §六 判定 | ✅ 已写（本文件） | 判定为「宿主可行、PoC 阻塞」 |

> **`poc-result.md` 故意不存在。** 任务书把它列为交付物，但它是**实测结果**文件；
> 在 PoC 未运行的情况下写入任何内容都是伪造。**这是刻意的偏离，已在此披露。**

## 6. 下一步（按顺序）

### 6.1 用户操作（阻塞中）

1. **下载 Windows 10 IoT Enterprise LTSC 2021 ISO**（~9.4 GB）→ 放 `/var/lib/libvirt/images/`
2. **下载 `virtio-win` ISO** → 同上
   - `https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso`
3. **告知本 session「ISO 已就位」** → 恢复执行

### 6.2 AI 自动执行（ISO 就位后，无需用户）

4. `virsh net-start default`（已确认无地址冲突）
5. `virt-install` 建域（**注意：安装时选中文简体区域** —— 与 GBK 语料主体一致，见 `env-audit.md` §4.3）
6. 等待用户完成 Windows 安装（**唯一需用户交互的步骤**）
7. 装 VirtIO 驱动 + `qemu-ga` → **打 `clean` 快照**
8. 执行 L3 PoC（P1/P2，流程见 `collection-design.md` §4.1）→ 写 `poc-result.md`
9. 回填 `poc-verdict.md` 的 Q2–Q4 与最终可行性判定

### 6.3 若 PoC 通过，下一 session 优先项

**NTFS last-access + 对象访问审计**（`collection-design.md` §7 优先级 1）——
用**纯配置**补上「读操作不可见」这一最大盲区，复用已建立的清单-差分框架。

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
