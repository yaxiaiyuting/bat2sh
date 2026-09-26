# VM 搭建记录（Win11 Enterprise LTSC 2024）

> 时间：2026-09-26 · 状态：**✅ 域已创建并运行，停在「等待用户按任意键启动安装程序」**
> **⚠️ 本文件相对任务书 §三 有多处实质偏离**，全部为执行中发现，逐条披露（见 §6）。

## 1. 最终实际配置（已生效，非计划）

| 项 | 值 | 来源 |
| :--- | :--- | :--- |
| 域名称 | `win-behavior` | — |
| 状态 | **运行中**（Id 3） | `virsh list` |
| 机器类型 | `q35` | os-variant win11 |
| 固件 | **EFI + Secure Boot**（`OVMF_CODE.secboot.4m.fd`）+ `smm=on` | `--boot uefi,firmware.feature0...` |
| TPM | **`tpm-crb` emulator v2.0**（`swtpm` 0.10.2） | `--tpm` |
| vCPU / 内存 | 4 / 8192 MB | — |
| 系统盘 | **SATA**，64 GiB qcow2 sparse（`win-behavior.qcow2`） | 见 §6.2 |
| 光驱 1（`sdb`） | **`win11-ltsc2024.iso`**（可引导 → Boot Manager 里的 `QM00003`） | — |
| 光驱 2（`sdc`） | **`virtio-win.iso`**（0.1.302 → Boot Manager 里的 `QM00005`） | — |
| 网络 | `default` 网络，**`e1000e`** | 见 §6.3 |
| 显示 | **SPICE `127.0.0.1:5900`**，qxl | `virsh domdisplay` |
| Guest Agent 通道 | `org.qemu.guest_agent.0`，状态 **`disconnected`**（预期：guest 未装 agent） | `dumpxml` |
| CPU 模式 | `host-passthrough` | — |

**镜像**（已就位，均为有效 ISO 9660，`libvirt-qemu` 可读）：

| 文件 | 大小 | 标识 |
| :--- | ---: | :--- |
| `/var/lib/libvirt/images/win11-ltsc2024.iso` | 5,287,520,256 B | `CES_X64FREV_ZH-CN_DV9`（**bootable**） |
| `/var/lib/libvirt/images/virtio-win.iso` | 877,373,440 B | `virtio-win-0.1.302` |

## 2. 🔴 当前阻塞：需要人工按一次键

**域已运行，但 Windows 安装程序未启动。** 卡在 UEFI 引导环节：

```
BdsDxe: No bootable option or device was found.
BdsDxe: Press any key to enter the Boot Manager Menu.
```

**原因**：Windows 安装光盘的 `cdboot.efi` 会显示

```
Press any key to boot from CD or DVD......
```

并**只等约 5 秒**；无人按键就回退到下一个引导设备（空硬盘 → 失败）。

> **本 session 尝试了自动化按键**（`virsh send-key`，含定时突发、基于截图的反应式循环、`--holdtime`），
> **均未能命中该窗口** —— 按键要么过早（被固件拦截并**打开 Boot Manager**），要么过晚（prompt 已超时）。
> 而 DOWN/ENTER 在 Boot Manager 内**是生效的**（光标确实移动过），所以不是 `send-key` 不通，
> 而是**时序窗口 + 命令往返延迟**（每次 `virsh` 调用 ≈0.2–0.4 s）无法可靠覆盖。

**这正是任务书 §三 预判的「Windows 安装需要交互，AI 不能自动装 Windows」** → **移交用户。**

### 2.1 用户操作（约 2 分钟）

**方式 A（推荐，图形）**：

```bash
virt-manager      # 已安装；双击 win-behavior 打开控制台
```

**方式 B（命令行 SPICE）**：

```bash
spicy -h 127.0.0.1 -p 5900
```

**在控制台里**：

1. 当前应停在 **Boot Manager**（`Please select boot device:`）
2. 用 **↓** 选中 **`UEFI QEMU DVD-ROM QM00003`** ← 这是 Windows 11 光盘（`sdb`）
   - ⚠️ **不要**选 `QM00005`，那是 `virtio-win` 驱动盘（不可引导）
3. 按 **ENTER**
4. 看到 **`Press any key to boot from CD or DVD......`** 时，**立刻按任意键**（空格即可）
5. 之后进入正常的 Windows 11 安装界面，走完即可

> 若第 1 步不在 Boot Manager，重启域即可：`sudo virsh --connect qemu:///system reboot win-behavior`

### 2.2 ⚠️ 若 Windows 11 报「此电脑无法运行 Windows 11」

**根因（已定位）**：本机 libvirt 固件能力为

```
<enum name='enrolledKeys'><value>no</value></enum>     ← 只支持 no
```

即 **没有预置微软签名密钥的 NVRAM 模板**（Arch 的 `edk2-ovmf` 只提供空的 `OVMF_VARS.4m.fd`）。
因此 Secure Boot **处于 Setup Mode**（有能力、未启用校验），Windows 11 可能据此拒绝。

**绕过（两分钟，标准做法）**：在安装界面按 **Shift+F10** 打开命令行 → `regedit` → 定位

```
HKEY_LOCAL_MACHINE\SYSTEM\Setup
```

新建项 **`LabConfig`**，在其下新建 3 个 DWORD = `1`：

| 名称 | 值 |
| :--- | :--- |
| `BypassTPMCheck` | 1 |
| `BypassSecureBootCheck` | 1 |
| `BypassRAMCheck` | 1 |

关闭 regedit 与命令行，回到安装界面点「上一步」再「下一步」即可继续。

> TPM 2.0 **本身是真实存在的**（swtpm emulator）。此绕过只是让安装程序跳过**校验**，
> **不影响后续行为采集** —— PoC 只关心 `cmd.exe` 的文件/输出行为，与 Secure Boot 状态无关。
> 但**必须记录**在指纹的 `environment` 中（SB 状态会影响少数脚本的探测行为）。

## 3. 安装完成后（用户操作）

1. **区域/语言选「中文（简体）」** —— 与 GBK 语料主体一致（见 `env-audit.md` §4.3）
2. 装 **virtio 驱动**：`virtio-win` 光盘（`sdc`）内
   - `guest-agent\qemu-ga-x86_64.msi` ← **PoC 的硬依赖，必装**
   - 网卡/串口等其余驱动可选（系统盘是 SATA，**无需** viostor）
3. 关机，然后由 AI 打快照

## 4. 快照（必需，非可选）

语料 **23.9% 会修改系统状态**，没有快照回滚，第二个样本就被第一个污染。

```bash
sudo virsh --connect qemu:///system snapshot-create-as win-behavior clean \
     --description "Win11 装完 + qemu-ga，干净基线"
```

此后**每个样本执行前**：

```bash
sudo virsh --connect qemu:///system snapshot-revert win-behavior clean
```

## 5. Guest Agent 通路验证（快照后立即做）

```bash
sudo virsh --connect qemu:///system qemu-agent-command win-behavior '{"execute":"guest-ping"}'
sudo virsh --connect qemu:///system qemu-agent-command win-behavior '{"execute":"guest-get-osinfo"}'
```

`dumpxml` 中 `<target type='virtio' name='org.qemu.guest_agent.0' state='disconnected'/>`
的 `state` 应从 `disconnected` 变为 `connected`。

## 6. 偏离汇总（对照任务书 §三）

| # | 任务书 | 实际 | 性质 |
| :-- | :--- | :--- | :--- |
| 1 | `win10` 镜像 | **`win11` LTSC 2024** | **用户决策**，已确认 |
| 2 | `--disk size=25,bus=virtio` | **`size=64,bus=sata`** | 64 因 Win11 硬性要求；**SATA 是主动选择**，见 §6.2 |
| 3 | 无 TPM | `--tpm` emulator 2.0 + **装 `swtpm`** | Win11 硬性要求（用户已授权装包） |
| 4 | 无固件指定 | EFI + Secure Boot + `smm=on` | Win11 硬性要求 |
| 5 | `--memory 4096` | `--memory 8192` | 安装期稳定性 |
| 6 | 未提 ISO 权限 | `~/` 是 700，**`libvirt-qemu` 读不到** → 移到 `/var/lib/libvirt/images/` | **执行中发现** |
| 7 | 未提 `default` 网络 | **已 `net-start` + `net-autostart`** | 任务书命令依赖它但环境未就绪 |
| 8 | 未提 virtio-win | 由 AI **自动下载并部署**（0.1.302） | 原为阻塞项，已消除 |
| 9 | 未提 Boot Manager | **需人工按键**（§2） | **执行中发现**，机械自动化不可靠 |
| 10 | 未提 enrolled-keys | Secure Boot **Setup Mode**，可能需 LabConfig 绕过（§2.2） | **执行中发现**，本机固件能力限制 |

### 6.1 ⚠️ 一次失败与自纠：`enrolled-keys`

首次 `virt-install` **失败**：

```
ERROR    操作失败: 找不到与当前配置兼容的"efi"固件
```

原因：我请求了 `firmware.feature1.name=enrolled-keys,enabled=yes`，
但 `virsh domcapabilities` 显示本机 **`enrolledKeys` 只支持 `no`**（Arch 不提供预置密钥的 VARS 模板）→ 无固件可匹配。
**去掉该 feature 后成功。**

> **教训**：`virt-install --dry-run --print-xml` **不会**校验固件兼容性 ——
> 带 `enrolled-keys` 的 dry-run **顺利通过**，真实执行却失败。
> **dry-run 通过不等于配置可用**，凡涉及固件/设备能力，须查 `domcapabilities`。

### 6.2 为什么系统盘用 SATA 而非 virtio

任务书示例用 `bus=virtio`。改为 **SATA** 的理由：

| | virtio | **SATA（选用）** |
| :--- | :--- | :--- |
| Windows 安装时 | **看不到磁盘**，须手动「加载驱动程序」→ `viostor\w11\amd64` | **开箱即见**，零额外步骤 |
| 失败风险 | 找不到驱动 → 安装无法继续 | 无 |
| 性能 | 更高 | 对「跑小 .bat」**完全足够** |

PoC 的执行对象是**复制几个小文件**，磁盘吞吐不是瓶颈。
**用一次安装失败的风险换取用不上的性能，不划算** → 选 SATA。
（`virtio-win` 光盘仍挂载，用于装 **`qemu-ga`** —— 它走 virtio-serial，**与磁盘无关**。）

### 6.3 网卡用 `e1000e`

Windows 自带 Intel 网卡驱动，**装完即有网**，无需先装 virtio 驱动。
PoC 本身不需要网络（`guest-exec` 走 virtio-serial），此处仅为可用性便利。

## 7. 环境记录（快照后采集，写入指纹）

| 项 | 获取方式 |
| :--- | :--- |
| `guest_os` | `guest-get-osinfo` |
| `guest_agent_version` | `guest-info` |
| `console_codepage` | guest 内 `chcp` |
| Secure Boot 实际状态 | guest 内 `Confirm-SecureBootUEFI`（PS）或 msinfo32 |
| `qemu` / `libvirt` | `11.1.1` / `12.7.0` |
| 快照名 | `clean` |

> **`console_codepage` 是解释 stdout 的前提**，不记录则指纹不可比（`collection-design.md` §4.5）。
