# PoC 结果：L3 输出效果层采集

> 时间：2026-09-26 · 状态：**✅ 全部通过**
> 本文件是**真实 Windows guest 上的实测记录**，非推断。前置：`vm-setup.md`、`collection-design.md` §4。
> 采集实现：`/tmp/poc/{qa.py,drive.py,run_p2.py}`（仓库外临时产物，未入仓）。

## 1. 结论速览

| 环节 | 结果 |
| :--- | :--- |
| 传递脚本进 guest（`guest-file-*`） | ✅ 通过 |
| 执行并捕获 stdout / stderr / 退出码（`guest-exec`） | ✅ **逐字节符合预期** |
| 非零退出码保真 | ✅ **7 → 7** |
| 输出截断标志 | ✅ `out-truncated=false`, `err-truncated=false` |
| 控制台代码页识别 | ✅ **CP936**（程序化取得） |
| base64 → 文本解码正确性 | ✅ 中文 `版本` 正确还原 |
| 文件系统清单 + 差分（PowerShell + `Get-FileHash`） | ✅ 通过 |
| 净差分盲区（瞬时副作用） | ✅ **实测复现** —— 声明与行为一致 |
| **L3 采集路径** | ✅ **可行，且可复现** |

## 2. 运行环境（写入指纹的环境字段）

| 项 | 值 | 来源 |
| :--- | :--- | :--- |
| `pretty-name` | `Windows 10 Pro` | `guest-get-osinfo`（**Win11 的兼容性上报值**） |
| `version` | `Microsoft Windows 11` | 同上 |
| `kernel-release` | **29599** | 同上 |
| `machine` | `x86_64` | 同上 |
| **`console_codepage`** | **936** | guest 内 `chcp` |
| Guest Agent 版本 | **110.2.3**（37 个命令） | `guest-info` |
| QEMU / libvirt | 11.1.1 / 12.7.0 | 宿主 |
| Guest 磁盘占用 | 9.9 GiB（qcow2，sparse） | 宿主 |
| **快照名** | **无** —— 见 §6.3 | — |

> **⚠️ 环境状态披露**：guest 处于 **审核模式（Audit Mode）**，以 Administrator 自动登录。
> 这是绕过 OOBE 强制联网/微软账户的结果（见 §5.5）。**对 L3 采集无影响**（`cmd.exe` 行为一致），
> 但作为**长期行为真值基座**需要单独评估 —— 见 §7「遗留问题」。

## 3. P1 —— stdout / 特殊字符 / 退出码

**样本**：`research/behavior-tracking/samples/poc-01-stdout.bat`
**SHA256**：`77a1f5091bb846ea8c704fa9bc44d4ebb8354c63de1148126f96cdb670f9691a`

**执行**：`cmd.exe /c "C:\poc\samples\poc-01-stdout.bat < nul"`

| 字段 | 实测值 |
| :--- | :--- |
| `exit_code` | **7** |
| `signal` | `null` |
| `out_truncated` / `err_truncated` | `false` / `false` |
| `duration_ms` | 数十毫秒量级 |
| `stderr` | **空** |

**stdout（CP936 解码后，逐字节）**：

```
POC-01-START
plain line
tab<TAB>separated
caret & ampersand
percent % literal
POC-01-END
```

| 检查点 | 预期 | 实测 | 判定 |
| :--- | :--- | :--- | :--: |
| 6 行完整性、CRLF 保留 | 是 | 是 | ✅ |
| Tab 字面量 | 保留 | 保留 | ✅ |
| `^&` → 字面 `&` | `caret & ampersand` | 一致 | ✅ |
| `%%` → 字面 `%` | `percent % literal` | 一致 | ✅ |
| **退出码 7 保真** | 7 | **7** | ✅ |
| stderr 为空 | 空 | 空 | ✅ |

> **与 wine 预验证逐字节一致。** 这一点很关键：因为期望值在跑真机**之前**就已钉死
> （`poc-wine-prevalidation.md` §3），所以本次通过**证明的是采集通路正确**，
> 而不是「样本恰好输出成这样」。**预验证的投入在此兑现。**

## 4. P2 —— 文件系统差分

**样本**：`research/behavior-tracking/samples/poc-02-fileops.bat`
**SHA256**：`d464915b97a173c01b99a9927549d1e45566744fe469c0e75bbab201008c9e06`
**清单范围**：`C:\poc\samples\*`（样本用 `%~dp0work` 写在**自身目录**下）
**清单方法**：PowerShell `Get-ChildItem -Recurse -Force -File` + `Get-FileHash SHA256` → JSON

### 4.1 执行结果

| 字段 | 实测值 |
| :--- | :--- |
| `exit_code` | **0** |
| `signal` | `null` |
| `out_truncated` / `err_truncated` | `false` / `false` |
| `stdout` | `beta`（`type b.txt` 的输出） |
| `stderr` | 空 |

### 4.2 差分结果

**执行前**（基线清单，2 项）：

```
C:\poc\samples\poc-01-stdout.bat
C:\poc\samples\poc-02-fileops.bat
```

**差分**：

| 类别 | 内容 |
| :--- | :--- |
| **created** | `C:\poc\samples\work\a.txt`、`C:\poc\samples\work\c.txt` |
| **modified** | （无） |
| **deleted** | （无） |
| **unchanged** | 2 |

**执行后实际目录内容**：`a.txt`、`c.txt`

**内容校验**：`a.txt` 与 `c.txt` 的 SHA256 **相同** → `copy /y` 复制正确。

### 4.3 ✅ 净差分盲区：**实测复现**

样本逻辑是 `echo beta>b.txt` → `copy a.txt c.txt` → `del b.txt`。因此：

| 真实发生的行为 | 净差分是否可见 | 实测 |
| :--- | :--- | :--- |
| `work\` 目录被创建 | ✅ | 目录本身未单列，但子文件出现 |
| `a.txt` 被**写入** | ✅ | created |
| `a.txt` 被 `copy` **读取** | ❌ **不可见** | **确认不可见** |
| `c.txt` 被创建 | ✅ | created |
| **`b.txt` 被创建后立即删除** | ❌ **完全不可见** | **确认不可见** |
| `b.txt` 被 `type` **读取** | ❌ 不可见 | 确认不可见（但内容出现在 stdout） |

> **这是本次 PoC 最有价值的发现之一**：`b.txt` 的「创建+删除」在快照对比中**彻底消失** ——
> 真实 Windows 上的行为与 `poc-samples.md` §5、`collection-design.md` §4.3 的**声明完全一致**。
> 即：**我们事先声明的能力边界是准确的**，没有把「看不到」误报成「没发生」。
> 指纹中 `filesystem.blind_spots` 字段如实记录了这一点。

## 5. 执行中发现的问题与处置（全部为实测）

### 5.1 🔴 `ufw` 丢弃 guest 的 DHCP 与 NAT（**根因级发现**）

**现象**：guest 显示「未识别的网络 / 无 Internet」，`net-dhcp-leases` 为空，OOBE 卡在网络页。

**根因**（nftables 计数为证）：

```
udp dport 67  counter packets 63 bytes 20930  jump ufw-skip-to-policy-input   ← 63 个 DHCP 请求被丢
chain input   { policy drop; }
chain forward { policy drop; }      # ufw 默认 deny(incoming) + deny(routed)
```

`ufw` 只放行了 KDE Connect，**libvirt 的 `virbr0` 完全没被放行**。

**处置**（两条定向规则，仅作用于 `virbr0`）：

```bash
sudo ufw allow in on virbr0 comment 'libvirt default bridge (guest DHCP/DNS)'
sudo ufw route allow in on virbr0 comment 'libvirt guest NAT forwarding'
```

**验证**：DHCP drop 计数**停止增长**；guest 获得 `192.168.122.36/24`；
NAT 计数器 `packets 68624 bytes 4475750 accept`（回程 193 MB）→ **真实外网连通**。

> **教训**：libvirt 的 `default` 网络"已启动"**不等于** guest 能上网。宿主防火墙是**独立的失败点**，
> 且其表现（"未识别的网络"）与网络配置错误**难以区分**。诊断必须看 **nftables 的 drop 计数**。

### 5.2 🔴 `qemu-ga` 需要 guest 侧 `vioserial` 驱动（**不是装上 MSI 就行**）

**现象**：`qemu-ga` MSI 安装成功（`C:\Program Files\Qemu-ga\` 有全套二进制），
但 `org.qemu.guest_agent.0` 通道始终 `state='disconnected'`。

**根因**：`C:\Windows\System32\drivers\vioser.sys` **不存在**。
`qemu-ga` 走 **virtio-serial**，没有该驱动则通道无法建立。

**处置**：安装 `virtio-win-gt-x64.msi`（virtio-win 光盘的驱动全家桶，含 `vioserial`）。
安装后**通道立即变为 `state='connected'`，`guest-ping` 返回 `{"return":{}}`**。

> **教训**：`state='disconnected'` 应首先怀疑**驱动**，而不是 agent 本身。
> 这条对任何"用 guest agent 做采集"的方案都成立，**值得写进下一 session 的前置检查**。

### 5.3 🟡 `cmd /c` 的首 token 引号剥离

**现象**：`cmd.exe /c '"C:\poc\samples\x.bat" < nul'` 报
`'"C:\poc\samples\x.bat"' 不是内部或外部命令`。

**根因**：`cmd /c` 对**以引号开头**的命令串有特殊剥离规则，导致整串（含引号）被当作程序名。

**处置**：路径无空格时**不加引号**（`cmd /c C:\poc\samples\x.bat < nul`）。
路径含空格时须用 `cmd /c ""C:\path with space\x.bat" < nul"` 的双引号形式（本 session 未实测）。

> 这是 `collection-design.md` §4.2「`arg` 是 argv、没有 shell」那条的**具体后果**：
> 重定向与引号语义**全部由 `cmd.exe` 的 `/c` 字符串层决定**，必须显式设计。

### 5.4 ✅ 编码链路端到端验证

`guest-exec-status` 返回 base64 原始字节，按 **CP936** 解码后中文正确还原
（`cmd /c ver` → `Microsoft Windows [版本 10.0.29599.1000]`）。
`chcp` 程序化取得 `936`。→ **`collection-design.md` §4.5「存 base64 原文 + 解码文本」的设计得到实证支持。**

### 5.5 🟡 绕过 OOBE 强制联网/微软账户

该镜像是 **Insider 预发布版（`rs_prerelease`, build 29599）**，OOBE **强制联网且不提供本地账户选项**：

| 尝试 | 结果 |
| :--- | :--- |
| 注入 `unattend.xml`（`HideOnlineAccountScreens` 等）到 4 个标准位置 | ❌ **未生效**（OOBE 已启动，未再读取） |
| `Shift+F10` 开命令行 | ❌ 该 build 的 OOBE 不响应 |
| 「设置为工作或学校」→「登录选项」 | ❌ 只给**安全密钥（passkey）**页，无「改为域加入」 |
| **`Ctrl+Shift+F3` → 审核模式** | ✅ **成功**，直接得到 Administrator 桌面，**整个 OOBE 被跳过** |

> **审核模式是本次的解法**，但**改变了环境语义**（见 §7）。

### 5.6 🟡 UEFI (pflash) 虚拟机不支持内部快照

```
错误：使用基于 pflash 固件的虚拟机的内部快照需要 QCOW2 nvram 格式
```

尝试把 NVRAM 转 qcow2 后，启动又失败：

```
错误：将 nvram 模板转换为其他目标格式不受支持
```

→ **放弃内部快照**，改用 **qcow2 backing-file 覆盖层**（见 §6.3）。

### 5.7 ✅ 无按键引导 Windows 安装程序

Windows 光盘的 `cdboot.efi` 会显示 `Press any key to boot from CD...` 并**只等约 5 秒**。
本 session 尝试 `virsh send-key` 自动化（定时突发 / 基于截图的反应式循环 / `--holdtime`）**均未命中时序窗口**。

**解法**：该 ISO 在 `efi/microsoft/boot/` 下**同时提供** `efisys.bin`（会提示）与
**`efisys_noprompt.bin`**（不提示），二者**均为 1,474,560 字节**。
而 El Torito 的 EFI 引导镜像（LBA 539）经 SHA256 比对**正是 `efisys.bin`**。
→ **把 `efisys_noprompt.bin` 原位写回 LBA 539**（`dd bs=2048 seek=539 conv=notrunc`），
即可**完全免按键**引导。

> 验证：补丁后 SHA256 与 `efisys_noprompt.bin` 一致，ISO 仍为有效 `ISO 9660 ... (bootable)`，
> **随后 Windows 安装程序在零按键下自行启动并完成安装**。

## 6. 复现清单

### 6.1 采集原语（可直接复用）

```bash
# 通道健康检查
virsh --connect qemu:///system qemu-agent-command win-behavior '{"execute":"guest-ping"}'

# 传文件：guest-file-open(mode=wb) → guest-file-write(buf-b64) → guest-file-close
# 执行：  guest-exec {path:"cmd.exe", arg:["/c","<脚本路径无引号> < nul"], capture-output:true} → pid
# 取回：  guest-exec-status {pid} → exited/exitcode/signal/out-data/err-data/{out,err}-truncated
# 清单：  powershell -NoProfile -Command "Get-ChildItem <范围> -Recurse -Force -File |
#           Select FullName,Length,LastWriteTime,@{n='Hash';e={(Get-FileHash $_.FullName -Algorithm SHA256).Hash}} |
#           ConvertTo-Json -Compress"
```

### 6.2 必查清单（本次踩过的坑，建议固化为前置检查）

| # | 检查 | 期望 |
| :-- | :--- | :--- |
| 1 | `sudo nft list ruleset \| grep 'udp dport 67'` 的 drop 计数是否增长 | 不增长 |
| 2 | `virsh net-dhcp-leases default` | 有 guest 租约 |
| 3 | `qemu-agent-command guest-ping` | `{"return":{}}` |
| 4 | `dumpxml` 中 agent 通道 `state` | `connected`（**否则查 `vioser.sys`**） |
| 5 | `{out,err}-truncated` | 均为 `false` |
| 6 | `chcp` | 记录进指纹 |

### 6.3 回滚机制（替代内部快照）

因 UEFI 限制改用 **qcow2 backing-file 覆盖层**，且**无需改域 XML**：

```bash
# 一次性：把当前"干净"盘作为基线，域仍指向 win-behavior.qcow2
virsh shutdown win-behavior
mv /var/lib/libvirt/images/win-behavior.qcow2 /var/lib/libvirt/images/win-behavior.base.qcow2
qemu-img create -f qcow2 -b win-behavior.base.qcow2 -F qcow2 \
     /var/lib/libvirt/images/win-behavior.qcow2

# 每个样本前回滚：删覆盖层重建（秒级，基线不动）
virsh shutdown win-behavior
rm /var/lib/libvirt/images/win-behavior.qcow2
qemu-img create -f qcow2 -b win-behavior.base.qcow2 -F qcow2 \
     /var/lib/libvirt/images/win-behavior.qcow2
virsh start win-behavior
```

> **⚠️ 本节为设计，尚未执行验证。** 本次 P2 之前的"基线重置"用的是
> **guest 内 `rmdir` 清理**（见 `run_p2.py`），不是覆盖层。
> 覆盖层的实际验证**留到下一 session 的第一件事**。

## 7. 遗留问题（如实列出）

| # | 问题 | 影响 | 建议 |
| :-- | :--- | :--- | :--- |
| 1 | **镜像为 Insider 预发布版**（`rs_prerelease` 29599） | 含**时间炸弹**（会过期）；非零售行为基线 | 长期采集应换 **LTSC/零售版**；本 PoC 结论不受影响 |
| 2 | **guest 处于审核模式** | 非标准最终用户状态 | 若作为长期基座，应评估是否需要正常 OOBE 后的状态 |
| 3 | 覆盖层回滚机制**未实测** | 样本间隔离尚无硬保证 | 下一 session 首要验证项 |
| 4 | 注册表 / 进程 / 网络**未采集** | 23.9% 语料的改系统行为不可见 | 属 L2，见 `collection-design.md` §7 |
| 5 | 读操作 / 瞬时副作用**不可见** | 已在 §4.3 实证 | 下一 session 优先级 1（NTFS last-access + `auditpol`） |
| 6 | `input-data`（stdin）方案**未测** | 目前依赖 `< nul` | 下一 session 对比验证（设计文档 §4.4 S2） |
| 7 | 采集脚本在 `/tmp/poc/`**未入仓** | 不可复现 | 决定是否入仓（属研究基础设施，非 bat2sh 产品代码） |

## 8. 判定

| 问题 | 答案 |
| :--- | :--- |
| 传递脚本可行？ | ✅ `guest-file-*` |
| 执行并捕获输出可行？ | ✅ **退出码 7 保真、stdout 逐字节正确、无截断** |
| 文件系统差分可行？ | ✅ PowerShell + SHA256 清单，差分准确 |
| 声明的盲区是否属实？ | ✅ **实测复现**（`b.txt` 建后即删完全不可见） |
| 编码处理是否正确？ | ✅ CP936 端到端验证，中文正确还原 |
| **L3 这条路可行？** | ✅ **可行，且可复现** |
| 最大的意外收获？ | **两个根因级基础设施坑**：ufw 丢 DHCP/NAT、qemu-ga 缺 `vioserial` 驱动 —— 两者都会表现为"agent 不通/没网"，且都不在原始设计文档的预料内 |
