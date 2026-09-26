# VM 搭建方案（Win11 Enterprise LTSC 2024）

> 时间：2026-09-26 · 状态：**准备中（ISO 下载中）**
> **⚠️ 本文件相对任务书 §三 有实质偏离**：任务书示例是 `win10` + 25 GB 磁盘 + 无 TPM；
> 实际交付的镜像是 **Windows 11 Enterprise LTSC 2024**，因此命令已改写。偏离已披露（见 §4）。

## 1. 镜像决策

| 项 | 值 |
| :--- | :--- |
| 任务书建议 | Windows 10 IoT Enterprise LTSC 2021 |
| **实际采用** | **Windows 11 Enterprise LTSC 2024（zh-cn）** |
| 来源 | `zh-cn_windows_11_enterprise_ltsc_2024_x64_dvd_cff9cd2d.iso`（qbittorrent，~4.92 GiB） |
| 决策人 | 用户（本 session 显式确认） |

**采用 Win11 的理由**：支持周期至 **2034**（Win10 LTSC 2021 为 2027-01），更适合作为长期行为真值基座。
**代价**：需要 TPM 2.0 + Secure Boot + 更大磁盘（见 §2）。

## 2. 相对任务书 §三 的必要变更

| 项 | 任务书示例 | **Win11 实际需要** | 原因 |
| :--- | :--- | :--- | :--- |
| `--os-variant` | `win10` | **`win11`** | 驱动/设备模型差异 |
| `--disk size` | `25` | **`64`** | Win11 官方最低 64 GB；25 GB 装不下 |
| TPM 2.0 | 无 | **`--tpm backend.type=emulator,backend.version=2.0`** | Win11 硬性要求 → 依赖 **`swtpm`** |
| 固件 | 默认 BIOS | **UEFI + Secure Boot**（`edk2-ovmf`） | Win11 硬性要求 |
| `--features` | 无 | **`smm=on`** | Secure Boot 必需 |
| 内存 | `4096` | **`8192`** | 安装期更稳（宿主 30 GiB，可用 14 GiB，充裕） |
| vCPU | `4` | `4`（保持） | 宿主 16 核 |

## 3. 已完成的准备

| 步骤 | 状态 | 证据 |
| :--- | :--- | :--- |
| `libvirtd` 可用 | ✅ | socket 激活（`env-audit.md` §2.1） |
| **`default` 网络启动 + 自启** | ✅ **已执行** | `net-list`：`default 活动 是 是` |
| **`swtpm` 安装** | ✅ **已执行**（用户授权） | `swtpm 0.10.2`，`/usr/bin/swtpm` 存在 |
| `edk2-ovmf`（Secure Boot 固件） | ✅ 已有 | 包已安装 |
| ISO 下载 | ⏳ 进行中 | qbittorrent，ETA ≈ 12 min |
| **`virtio-win` ISO** | ❌ **仍缺** | **PoC 硬依赖**，见 §5.1 |

### 3.1 ⚠️ ISO 权限陷阱（必须处理）

```
drwx------  /home/duanjb666          ← 700，libvirt-qemu 无法穿越
drwxr-xr-x  /home/duanjb666/下载     ← 751
```

`qemu:///system` 的域以 **`libvirt-qemu`** 用户运行（`/etc/libvirt/qemu.conf` 默认值）。
**它无法读取 `~/下载/` 下的 ISO** —— 域会因「Permission denied」启动失败。

**处置**：下载完成后把 ISO **移动到** `/var/lib/libvirt/images/` 并放开读取权限：

```bash
sudo mv /home/duanjb666/下载/zh-cn_windows_11_enterprise_ltsc_2024_x64_dvd_cff9cd2d.iso \
        /var/lib/libvirt/images/win11-ltsc2024.iso
sudo chmod 644 /var/lib/libvirt/images/win11-ltsc2024.iso
```

（用 `mv` 而非 `cp`，避免多占 ~5 GB。）

## 4. 待执行的建域命令

```bash
sudo virt-install \
  --connect qemu:///system \
  --name win-behavior \
  --memory 8192 \
  --vcpus 4 \
  --os-variant win11 \
  --cdrom /var/lib/libvirt/images/win11-ltsc2024.iso \
  --disk size=64,format=qcow2,bus=virtio,path=/var/lib/libvirt/images/win-behavior.qcow2 \
  --network network=default,model=virtio \
  --graphics spice,listen=127.0.0.1 \
  --video qxl \
  --tpm backend.type=emulator,backend.version=2.0,model=tpm-crb \
  --boot uefi,firmware.feature0.name=secure-boot,firmware.feature0.enabled=yes \
  --features smm=on \
  --channel unix,target_type=virtio,name=org.qemu.guest_agent.0 \
  --noautoconsole
```

> **说明**：`--boot uefi,...secure-boot` 需要 `edk2-ovmf` 的 secboot 固件（已装）。
> 同时 `--cdrom` 与 `--disk bus=virtio` 共存时，Windows 安装程序**默认看不到 virtio 磁盘** ——
> 需在安装界面手动「加载驱动程序」并从 `virtio-win` 光盘加载（见 §5.2）。

### 4.1 图形访问（用户交互安装）

```bash
virt-manager            # GUI（已安装）
# 或
spicy -h 127.0.0.1 -p <port>    # spicy 已安装
```
（`remote-viewer` / `virt-viewer` 未安装，但**不影响** —— 有 `virt-manager` 与 `spicy`。）

## 5. 用户需完成的交互步骤

### 5.1 【阻塞】下载 `virtio-win` ISO

```
https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso
```

约 700 MB。提供：① virtio 磁盘/网卡驱动 ② **guest 侧 `qemu-ga` 安装程序**（PoC 的 `guest-exec` 通路依赖它）。

放 `/var/lib/libvirt/images/virtio-win.iso` 并 `chmod 644`。

### 5.2 Windows 安装（用户操作，AI 不能自动化）

1. 走完 OOBE；**区域/语言选「中文（简体）」**（与 GBK 语料主体一致，见 `env-audit.md` §4.3）
2. **安装 virtio 驱动**：磁盘选择界面若看不到磁盘 → 「加载驱动程序」→ 浏览 `virtio-win` 光盘 → `viostor\w11\amd64`
3. 装完系统后，从同一光盘安装 **`guest-agent\qemu-ga-x86_64.msi`**
4. **建议**：装完立即关机，由 AI 打 `clean` 快照（见 §6）

### 5.3 验证 Guest Agent 通路

```bash
virsh --connect qemu:///system qemu-agent-command win-behavior '{"execute":"guest-ping"}'
virsh --connect qemu:///system qemu-agent-command win-behavior '{"execute":"guest-get-osinfo"}'
```

## 6. 快照（必需，非可选）

语料 **23.9% 会修改系统状态**（注册表/服务/用户），**没有快照回滚，第二个样本就被第一个污染**。

```bash
sudo virsh --connect qemu:///system snapshot-create-as win-behavior clean \
     --description "Windows 装完 + virtio 驱动 + qemu-ga，干净基线"
```

此后**每个样本执行前**：

```bash
sudo virsh --connect qemu:///system snapshot-revert win-behavior clean
```

## 7. 环境记录（写入指纹必需）

域建好、系统装完后，须采集并记录进 `poc-result.md`：

| 项 | 获取方式 |
| :--- | :--- |
| `guest_os` | `guest-get-osinfo`（pretty-name / version / kernel-release） |
| `guest_agent_version` | `guest-info` |
| `console_codepage` | guest 内 `chcp` |
| `qemu` / `libvirt` 版本 | `qemu-system-x86_64 --version` / `virsh version` |
| 快照名 | `clean` |

> **`console_codepage` 是解释 stdout 的前提**，不记录则指纹不可比（`collection-design.md` §4.5）。

## 8. 本文件的偏离汇总（对照任务书 §三）

| # | 任务书 | 本方案 | 性质 |
| :-- | :--- | :--- | :--- |
| 1 | `win10` 镜像 | **`win11` LTSC 2024** | **用户决策**，已确认 |
| 2 | `--disk size=25` | `--disk size=64` | Win11 硬性要求 |
| 3 | 无 TPM | 加 `--tpm` emulator 2.0 + `swtpm` | Win11 硬性要求 |
| 4 | 无固件指定 | UEFI + Secure Boot + `smm=on` | Win11 硬性要求 |
| 5 | `--memory 4096` | `--memory 8192` | 安装期稳定性 |
| 6 | 未提 ISO 权限 | 加 §3.1 权限处置 | **实测发现**：`libvirt-qemu` 读不到 `~` |
| 7 | 未提 `default` 网络 | 已 `net-start` + 自启 | 任务书命令依赖它但环境未就绪 |
| 8 | 未提 virtio-win | §5.1 列为**阻塞项** | `qemu-ga` 的来源 |

> **未执行项**：§4 的 `virt-install` **尚未运行** —— 等 ISO 下载完成 + `virtio-win` 就位。
