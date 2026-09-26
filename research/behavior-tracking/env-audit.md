# 环境盘点：QEMU 行为采集路径

> 审计时间：2026-09-26 18:41 CST（18:50 修订，见文末修订记录）
> 主机：Arch Linux（内核 KVM 模块 `kvm_amd` 已加载）
> 方法：**只读诊断**（`--version` / `ls` / `pacman -Qq` / `virsh` 查询）。
> 本文件不修改 bat2sh 任何代码；仓库 HEAD 锁定在 `4c7076c`。

## 0. 前置确认结果

| # | 前置项 | 期望 | 实测 | 判定 |
| :-- | :--- | :--- | :--- | :--- |
| 1 | 工作区干净 | `git status` 无输出 | 无输出（仅 `.venv/`、打包产物等 `.gitignore` 内条目） | ✅ |
| 2 | HEAD = 最新 main tip | 与 `origin/main` 一致 | `4c7076c` == `origin/main` | ✅ |
| 3 | v2.9.0 维护模式 | tag 存在 | tag `v2.9.0` = `69e6fde`，HEAD 领先 13 个提交（全部 docs/chore） | ✅ |
| 4 | `docs/future-behavior-tracking.md` 已落盘 | 文件存在 | **不存在** | ❌ **偏离** |

> **⚠️ 偏离披露（#4）**：本 session 任务书称 `docs/future-behavior-tracking.md` 已落盘。
> 实测该文件在仓库工作树、全部本地/远程分支（9 个）、全部 git 历史（`git log --all`）、stash、reflog，
> 以及 `/home/duanjb666` 下 4 层目录中**均不存在**。
> 该文件被任务书定位为设计输入来源之一。**已暂停并向用户报告**（见 `poc-verdict.md`）。
> 本 session 产出**不依赖**该文件——所有设计结论均从任务书原文 + 已存在的先例研究
> `docs/research/b1-dynamic-tracing.md` 推导，并逐条标注来源。

## 1. 组件状态

| 组件 | 状态 | 版本 / 详情 |
| :--- | :--- | :--- |
| **QEMU** | ✅ 可用 | `QEMU emulator version 11.1.1`（包 `qemu-full`，含 `qemu-system-x86`、`qemu-img`、`qemu-ui-spice-core`） |
| **libvirt** | ✅ 可用 | `libvirt 12.7.0` / `virsh 12.7.0`；**systemd socket 激活**——`libvirtd.socket` active，`libvirtd.service` running（`--timeout 120` 空闲退出），实测 `virsh --connect qemu:///system` 正常返回 |
| **KVM** | ✅ 可用 | `/dev/kvm` 存在（`crw-rw-rw- root:kvm`）；CPU 支持 `svm`；模块 `kvm` + `kvm_amd` 已加载 |
| **Guest Agent** | ⚠️ Guest 端**缺失** | 宿主侧 `virsh qemu-agent-command` 能力就绪；Windows guest 所需 `virtio-win` 光盘**不存在**（详见 §3） |
| **Windows 镜像** | ❌ **无** | 全盘（`/home` 4 层 + `/var/lib/libvirt/images`）未找到任何 `*.iso` / `*.wim` / `*.esd`；仅有 Android AVD 的 `*.qcow2` |
| **磁盘空间** | ✅ 充足 | `/home` 可用 **731,883,212,800 B ≈ 681.6 GiB**（要求 ≥ 50 GB） |

## 2. 虚拟化栈明细

### 2.1 已安装且可用

| 包 / 工具 | 用途 | 备注 |
| :--- | :--- | :--- |
| `qemu-full` 11.1.1 | 模拟器全量 | 含 x86_64 + virtio 设备 |
| `libvirt` 12.7.0 | 虚拟机管理 | socket 激活，无需手动 start |
| `virt-install` | 建域 | `/usr/bin/virt-install` |
| `virt-manager` | GUI 管理 | 可作 Windows 安装的图形入口 |
| `virtiofsd` | 共享目录 | host↔guest 传脚本备选方案 |
| `edk2-ovmf` | UEFI 固件 | 可选；Win10 传统 BIOS 亦可 |
| `dnsmasq` | libvirt 默认网络 DHCP/DNS | `network=default` 依赖它 |
| `spice` / `spice-gtk` / `spicy` | SPICE 显示客户端 | `spicy` 可用于交互式安装 |
| `sed`/`virsh` 网络栈 | `default` 网络**已定义** | 见 §2.2 |

### 2.2 网络与显示

| 项 | 实测 | 影响 / 处置 |
| :--- | :--- | :--- |
| `qemu:///system` 的 `default` 网络 | **已定义（持久）**，状态 `不活跃`，`自动开始=否` | **一条命令即可**：`virsh --connect qemu:///system net-start default`（无需 `net-define`） |
| 地址冲突检查 | `192.168.122.0/24` **无占用**（路由表无该网段；本机无 docker/podman） | ✅ `net-start` 安全；`virbr0` 不会与现有网络冲突 |
| 现有网桥 | `cvd-ebr` / `cvd-wbr` 等 Android Cuttlefish 虚拟网络 | 与 libvirt 网段不重叠 ✅ |
| `virsh` 默认 URI | `qemu:///session` | 任务书命令显式用 `--connect qemu:///system`，**保持一致**（`default` 网络在 system URI 下） |
| `remote-viewer` / `virt-viewer` | 缺失 | **不阻塞**：有 `spicy`（SPICE）与 `virt-manager` |
| `swtpm` | 缺失 | **不阻塞**：仅 Windows 11 需 TPM 2.0 |

## 3. Guest Agent 澄清（重要）

任务书第一节把「`qemu-ga` 可用」列为宿主环境检查项。此处需澄清一个常见混淆：

- **`qemu-ga` 运行在 guest 内部，不在宿主。** 宿主侧只需 `virsh`（已具备，`virsh help qemu-agent-command` 正常）。
- **Windows guest 的 `qemu-ga` 由 `virtio-win` ISO 提供**（`guest-agent\qemu-ga-x86_64.msi`）。
- 宿主 `qemu-guest-agent 11.1.1-4`（`extra` 仓库可装）**不安装也不影响** PoC——它是给 Linux guest 用的。
- 真正的阻塞项是 **`virtio-win` ISO 缺失** → `guest-exec` 通路在 Windows guest 上**尚不可用**。

## 4. 需要用户下载的镜像（唯一硬阻塞）

Windows 安装需要交互式操作，**AI 不能自动安装 Windows**。用户需提供：

### 4.1 Windows 安装镜像（必需，二选一）

| 方案 | 版本 | 体积（约） | 评价 |
| :--- | :--- | :--- | :--- |
| **推荐** | Windows 10 IoT Enterprise LTSC 2021 | ~9.4 GB | 官方、无 Store/无预装、生命周期长、行为确定；适合作为长期采集基座 |
| 备选 | tiny10 / tiny11（社区精简版） | ~10.3 GB | 装得快，但**非官方**、组件被裁剪，可能缺失 PoC/未来需要的 `reg`、WMI、计划任务等 → **会污染行为基线**，不推荐作为研究真值基座 |

> **建议采用推荐方案。** 精简版裁剪掉的恰好可能是未来要观测的组件，作为「行为真值」基座不可靠。

### 4.2 `virtio-win` ISO（必需，随 4.1 一起下载）

- 来源：`https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso`
- 用途：① Windows 内安装 virtio 磁盘/网卡驱动；② 提供 **`qemu-ga`** 安装程序（PoC 的 `guest-exec` 通路依赖它）。
- 无此 ISO → §五 PoC 无法执行。

### 4.3 安装时的区域设置（决策项，非阻塞）

**建议 VM 安装时选「中文（简体）」区域。** 理由：`cmd.exe` 的内建输出走**控制台代码页**
（zh-CN → CP936），而语料主体正是 **GBK 中文批处理**（v1.4.1 统计 107/151 为 GBK）。

| 安装区域 | 控制台代码页 | GBK 语料 | UTF-8 夹具 |
| :--- | :--- | :--- | :--- |
| **中文（简体）** | CP936 | ✅ 正常 | ⚠️ 乱码 |
| en-US | CP437/850 | ❌ 乱码 | ✅ 正常 |

两种语料**不可能同时正确**——编码必须作为一个**显式受控变量**记录在指纹里。
选 zh-CN 是因为语料主体是 GBK。此结论已在 wine 预验证中实证（见 `poc-wine-prevalidation.md` §6）。

### 4.4 下载后放置建议

```
/var/lib/libvirt/images/win10-ltsc.iso
/var/lib/libvirt/images/virtio-win.iso
```

（路径可自定，建域命令使用实际路径。）

## 5. 判定

| 问题 | 答案 |
| :--- | :--- |
| QEMU 环境可搭？ | ✅ **可以** —— QEMU 11.1.1 + libvirt 12.7.0 + KVM 全部就绪，磁盘 681 GiB 充足 |
| KVM 加速可用？ | ✅ 是（`/dev/kvm` + `kvm_amd` 已加载，CPU `svm`） |
| 宿主栈需要补装什么？ | **无**（`qemu-full` 全量已装；`swtpm`/`virt-viewer` 非必需） |
| Guest Agent 可执行命令？ | ⏸ **待验证** —— 宿主能力就绪，guest 侧 agent 需 `virtio-win` ISO 才能安装 |
| 缺什么才能继续？ | **仅两件镜像**：① Windows 10 LTSC ISO ② `virtio-win` ISO |
| **是否暂停？** | 🛑 **是** —— 触发任务书 §七「Windows 镜像缺失 → 暂停，等用户下载」 |

## 6. 待执行的准备工作（无需用户，副作用明确）

以下步骤**尚未执行**（遵循「只读诊断先行」）。均**可逆**且已确认无冲突：

```bash
# 1. 启动 libvirt 默认 NAT 网络（已定义，仅需启动；无 192.168.122.0/24 冲突）
sudo virsh --connect qemu:///system net-start default
sudo virsh --connect qemu:///system net-autostart default   # 可选：开机自启

# 2. 校验
virsh --connect qemu:///system net-list --all    # default 应变为 active
virsh --connect qemu:///system version           # 已验证可用

# 3. 安装目录准备
sudo mkdir -p /var/lib/libvirt/images
```

> **备选**：若不愿动系统网络配置，`virt-install` 可用 `--network user`（QEMU 用户态 NAT），
> 零系统配置即可让 guest 出网。代价是宿主无法主动连入 guest——本 PoC 方向为 host→guest（`guest-exec`
> 走 virtio-serial，不经网络），**故 `--network user` 对 PoC 完全够用**，可作为无副作用首选。

---

## 修订记录

**18:50 修订**：初版审计有两处误判，经复核修正：

| 初版结论 | 修正后 | 原因 |
| :--- | :--- | :--- |
| ~~`libvirtd` 未运行，需 `systemctl start libvirtd`~~ | **可用**，socket 激活 | `systemctl is-active libvirtd` 报 inactive 具有误导性：`libvirtd.socket` 为 active，实测 `virsh --connect qemu:///system` 正常返回（`运行管理程序: QEMU 11.1.1`） |
| ~~`default` 网络未定义，需 `net-define`~~ | **已定义**，仅需 `net-start` | 初版只查了默认 URI `qemu:///session`（该 URI 下确实无网络）；`qemu:///system` 下 `default` 为持久网络，状态 `不活跃` |
| ~~`net-define /usr/share/libvirt/networks/default.xml`~~ | 路径错误，勿用 | Arch 上该路径不存在；实际 XML 在 `/etc/libvirt/qemu/networks/default.xml`（root-only），且已定义无需重定义 |

修正后**硬阻塞从 4 项收敛为 1 项：仅缺两件 ISO**。宿主虚拟化栈本身完全健康。

---

**审计结论：宿主虚拟化栈健康可用，唯一硬阻塞是镜像缺失。等用户提供 ISO 后即可进入 §三 建域。**
