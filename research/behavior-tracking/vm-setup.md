# VM 搭建记录（Win11 Enterprise LTSC 2024 → 实际为 Win11 Pro 29599）

> 时间：2026-09-26 · 状态：**✅ 域建成、Windows 装成、guest agent 连通、PoC 已跑通**
> **⚠️ 本文件相对任务书 §三 有多处实质偏离**，全部为执行中发现，逐条披露（见 §6、§8）。
>
> **最终采用的镜像并非本文件标题初版的 LTSC 2024** —— 用户中途更换为
> `29599.1000.260520-1434.RS_PRERELEASE_CLIENTPRO_OEMRET_X64FRE_ZH-CN.ISO`
> （**Windows 11 Pro，Insider 预发布版 build 29599**）。完整时间线见 §8。

## 0. 最终结果（TL;DR）

| 阶段 | 结果 |
| :--- | :--- |
| 域创建（`virt-install`） | ✅ q35 + EFI/Secure Boot + TPM 2.0 + SATA 64 GiB + SPICE |
| **免按键引导安装程序** | ✅ 通过**原位替换 El Torito EFI 镜像**为 `efisys_noprompt.bin`（见 §6.4） |
| Windows 安装 | ✅ **零按键**自动完成（无需人工按 "Press any key"） |
| 绕过 OOBE 强制联网/微软账户 | ✅ **`Ctrl+Shift+F3` 审核模式**（见 §6.5） |
| 网络（DHCP + NAT） | ✅ 需放行 `ufw`（**根因级坑**，见 §6.6） |
| `qemu-ga` 连通 | ✅ 需装 **`vioserial` 驱动**（**根因级坑**，见 §6.7） |
| **L3 PoC（P1/P2）** | ✅ **全部通过** —— 详见 `poc-result.md` |

**最终环境**：Win11 Pro build **29599**（`rs_prerelease`）· 审核模式 / Administrator ·
guest agent **110.2.3** · 控制台代码页 **CP936** · 磁盘占用 9.9 GiB

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

---

## 6.4 ✅ 免按键引导安装程序（关键技法，可复用）

**问题**：Windows 光盘的 `cdboot.efi` 显示 `Press any key to boot from CD or DVD......`，
**只等约 5 秒**；无人按键就回退到下一个引导设备（空硬盘）→ 失败。
`virsh send-key` 自动化**不可靠**：过早会被固件截住并**打开 Boot Manager**，
过晚 prompt 已超时（每次 `virsh` 调用有 0.2–0.4 s 往返延迟，覆盖不了该窗口）。

**解法**（本 ISO 自带）：

```
efi/microsoft/boot/efisys.bin           1474560 B   ← 会提示（El Torito 实际用的就是它）
efi/microsoft/boot/efisys_noprompt.bin  1474560 B   ← 不提示，同尺寸
```

1. 用 `xorriso -report_el_torito plain` 定位 El Torito EFI 镜像：**LBA 539**
2. `dd` 抽出该区域，SHA256 比对确认它**逐字节等于 `efisys.bin`**
3. **原位写回** `efisys_noprompt.bin`：

```bash
dd if=/mnt/iso/efi/microsoft/boot/efisys_noprompt.bin \
   of=win11.iso bs=2048 seek=539 conv=notrunc
```

4. 校验：抽出区域 SHA256 == `efisys_noprompt.bin`；`file` 仍报 `ISO 9660 ... (bootable)`

**结果**：Windows 安装程序**零按键自行启动并完成安装**。

> **注**：ISO 树内的 `efi/boot/bootx64.efi`（2.9 MB）**不是** El Torito 用的那个
> —— 它是 USB 引导用的 Windows Boot Manager（`bootmgfw`）。两者不要混淆。

## 6.5 ✅ 绕过 OOBE 强制联网 / 微软账户

该 Insider 镜像的 OOBE **强制联网且不提供本地账户**。逐一尝试：

| 尝试 | 结果 |
| :--- | :--- |
| 注入 `unattend.xml`（`HideOnlineAccountScreens`/`SkipMachineOOBE`）到 4 个标准位置 | ❌ 未生效（OOBE 已启动，不再读取） |
| `Shift+F10` 开命令行 | ❌ 该 build 的 OOBE 不响应 |
| 「设置为工作或学校」→「登录选项」 | ❌ 只给**安全密钥 / passkey** 页，无「改为域加入」 |
| **`Ctrl+Shift+F3`** | ✅ **审核模式**，直接得到 Administrator 桌面，**整个 OOBE 被跳过** |

```bash
virsh send-key win-behavior --holdtime 300 KEY_LEFTCTRL KEY_LEFTSHIFT KEY_F3
```

> ⚠️ **语义代价**：审核模式是 OEM 预装态（Administrator 自动登录），
> **不等于最终用户状态**。对 L3 采集无影响（`cmd.exe` 行为一致），
> 但作为**长期行为真值基座需单独评估**（见 `poc-result.md` §7 遗留 #2）。

## 6.6 🔴 `ufw` 丢弃 guest 的 DHCP 与 NAT（根因级）

**现象**：guest 显示「未识别的网络 / 无 Internet」，`net-dhcp-leases` 为空，OOBE 卡住。

**根因**：宿主 `ufw` 处于 active，默认 `deny (incoming)` + `deny (routed)`，且**只放行了 KDE Connect**。
libvirt 的 `virbr0` 完全没被放行。nftables 计数为铁证：

```
udp dport 67  counter packets 63 bytes 20930  jump ufw-skip-to-policy-input   ← 63 个 DHCP 被丢
```

**处置**（定向、仅作用于 `virbr0`）：

```bash
sudo ufw allow in on virbr0 comment 'libvirt default bridge (guest DHCP/DNS)'
sudo ufw route allow in on virbr0 comment 'libvirt guest NAT forwarding'
```

**验证**：drop 计数停止增长 → guest 获得 `192.168.122.36/24` →
NAT 计数器 `packets 68624 bytes 4475750 accept`（回程 193 MB）。

> **"libvirt default 网络已启动" ≠ "guest 能上网"。** 宿主防火墙是独立失败点，
> 且症状（"未识别的网络"）与网络配置错误难以区分。**诊断必须看 nftables 的 drop 计数。**

## 6.7 🔴 `qemu-ga` 需要 guest 侧 `vioserial` 驱动（根因级）

**现象**：`qemu-ga` MSI 安装成功（`C:\Program Files\Qemu-ga\` 有全套二进制），
但 `org.qemu.guest_agent.0` 通道**始终** `state='disconnected'`。

**根因**：`C:\Windows\System32\drivers\vioser.sys` **不存在**。
`qemu-ga` 走 **virtio-serial**，没有该驱动则通道无法建立。

**处置**：安装 virtio-win 光盘的驱动全家桶：

```bash
msiexec /i C:\poc\virtio-win-gt-x64.msi /qn /norestart
```

安装后**通道立即 `state='connected'`，`guest-ping` 返回 `{"return":{}}`**。

> **`state='disconnected'` 应首先怀疑驱动，而不是 agent 本身。**
> 这条对任何「用 guest agent 做采集」的方案都成立。

## 6.8 离线预置法（规避中文输入法干扰）

guest 内中文输入法（微软拼音）会吞掉 `send-key` 打的字母（变成候选词）。
本 session 用**离线预置 + 自删除启动脚本**绕开打字：

```bash
# 1) 关机；qemu-nbd 挂 qcow2；ntfs-3g 挂 Windows 分区
sudo qemu-nbd --connect=/dev/nbd0 --discard=unmap win-behavior.qcow2
sudo mount -t ntfs-3g -o rw /dev/nbd0p3 /mnt/win

# 2) 投安装包到 C:\poc\
# 3) 投自删除启动脚本到
#    /mnt/win/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/zz-install.bat
#    （注意是 Startup 不是 StartUp；另有本地化符号链接「程序」）

# 4) 卸载、断连、启动 —— 审核模式自动登录，脚本随即静默安装并自删
sudo umount /mnt/win && sudo qemu-nbd --disconnect /dev/nbd0
```

---

## 8. 镜像更换时间线（如实记录）

| 顺序 | 镜像 | 结果 |
| :--- | :--- | :--- |
| 1 | 任务书建议：Win10 IoT LTSC 2021 | 用户未提供 |
| 2 | 用户实际下载：`zh-cn_windows_11_enterprise_ltsc_2024`（5.29 GB） | 已建成域，但卡在 `Press any key` 引导提示；后用户更换 |
| 3 | **用户更换：`29599.1000.260520-1434.RS_PRERELEASE_CLIENTPRO_OEMRET_X64FRE_ZH-CN.ISO`（5.91 GB）** | ✅ **最终采用** —— 该 ISO 自带 `efisys_noprompt.bin`，据此实现免按键引导 |

**镜像性质披露**：`RS_PRERELEASE` = **Windows Insider 预发布版**，
`CLIENTPRO` = Pro 版，build `29599.1000`（编译于 2026-05-20）。

> ⚠️ Insider 构建**含时间炸弹**，且**不是零售行为基线**。
> 作为**长期行为真值基座不可接受**；本次仅用于**验证采集通路可行性**（该目的已达成）。
> 建议后续换 **LTSC / 零售版**重新建立基线（`poc-verdict.md` §6.1 遗留项 2）。
