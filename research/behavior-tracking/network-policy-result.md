# 网络策略实测结果 —— 隔离 + 记录

> 时间：2026-09-26 · 状态：**T0/T1/T2/T3 全部通过**
> 设计：`network-policy.md`（§6 选定方案，§6.2 判据）
> 产物：`tools/netsniff.py`（新）、`tools/net.py`（新）、`tools/collect.py`（集成 `--network=`）

---

## 1. 结论摘要

| # | 判据 | 结果 | 硬证据 |
| :-- | :--- | :--- | :--- |
| **T0** | **正对照**：未隔离时确实能出网 | ✅ **通过** | `ping 8.8.8.8` 0% 丢失 / DNS 解析成功 / TCP `1.1.1.1:80` **connected**；宿主侧 327 帧、22 条 `established` |
| **T1** | 隔离生效 | ✅ **通过** | `ping` 100% 丢失 / DNS 无解析器 / TCP error；宿主侧 **`egress_frames=0`** |
| **T2** | 记录生效 | ✅ **通过** | 32 条连接，含 `icmp 8.8.8.8 refused` 与 `tcp 1.1.1.1:80 refused`；**无任何 off-subnet `established`** |
| **T3** | 回滚后隔离保持 | ✅ **通过** | 覆盖层重建后域 XML 仍 `link_state=down`、MAC 不变；重跑 T1 仍 `egress_frames=0` |

**一句话**：默认策略（A2 链路 down）在**宿主零防火墙改动**的前提下做到了可证明的零出网；记录策略（A4 + D1b）在**结构性无 NAT** 的前提下做到了"看得到尝试、出不去一个包"。

---

## 2. 环境与版本

| 项 | 值 |
| :--- | :--- |
| 仓库 | `/home/duanjb666/bat2sh`，HEAD `04f0dd4`（**锁定**，本轮未产生新 commit 前的基线） |
| 域 | `win-behavior` @ `qemu:///system` |
| Guest | `Microsoft Windows 11 专业版 Insider Preview`，`10.0.29599.1000`，BuildLabEx `29599.1000.amd64fre.rs_prerelease.260520-1434`（**构建于 2026-05-20**） |
| 授权 | `LicenseStatus=5`（通知模式，未激活），`GracePeriodRemaining=0`，`IsRetailOS=0` |
| 控制台代码页 | **936**（与 GBK 语料一致，`env-audit.md` 的结论在实测中成立） |
| 宿主 | `tcpdump`/`dumpcap`/`tshark` **均未安装**；`nft`/`iptables`/`ebtables`/`virt-xml` 可用；免密 sudo 可用 |
| 网络 | `default`（NAT，virbr0/192.168.122.0/24）；`bat2sh-rec`（**本次新建**，`forward mode='none'`，virbr-rec/192.168.200.0/24） |

### 2.1 Insider 时间炸弹（任务书 §六）

- 实测能取到的信息：`DisplayVersion=Dev`、`IsRetailOS=0`、构建时间戳 `260520-1434` ⇒ **构建于 2026-05-20**。
- Guest 当前时间 **2026-09-26**，系统**运行正常**，未观察到到期行为（未见"此版本已过期"提示、未见每小时重启）。
- **OS 没有暴露一个可直接读取的到期时刻**：`slmgr /xpr` 只报"通知模式"，`SoftwareLicensingProduct` 的 `GracePeriodRemaining=0` 指的是**激活宽限期**（已耗尽），**不是** Dev 通道的构建时间炸弹。
- **判定**：本期**未到期**，可继续。但**到期时间不可知**（只能给出"构建日 2026-05-20"这一上界线索）⇒ **下个 session 应换零售版**（与任务书要求一致）。
- 附带发现：`GracePeriodRemaining=0` + 通知模式意味着**任何依赖激活状态的样本行为都可能与真机有偏差**。当前未观察到影响，但记录在案。

---

## 3. T0 —— 正对照（`--network=nat`）

**为什么必须先做这个**：没有正对照，"ping 失败"这个观测**不可解释** —— 它可能是隔离生效，也可能是 ufw 挡了 DHCP（`vm-setup.md` §6.6 的真实坑）、网关没配、或网卡驱动没起来。**只有先证明"不隔离时能通"，"隔离时不通"才构成证据。**

```bash
python3 tools/collect.py --sample samples/net-probe.bat \
        --output results/t0-nat.json --network=nat
```

| 观测 | 结果 |
| :--- | :--- |
| Guest IP | `192.168.122.36`，网关 `192.168.122.1` |
| `[1] ICMP 8.8.8.8` | **来自 8.8.8.8 的回复 … 0% 丢失**，平均 93 ms |
| `[2] DNS www.example.com` | **解析成功**（4 条 A/AAAA） |
| `[3] TCP 1.1.1.1:80` | **`tcp=connected`** |
| 宿主侧嗅探 | `egress_frames=327`，29 条连接，其中 **22 条 `established`** |
| `bytes_sent` / `bytes_recv` | 32913 / 97638 |

> ⚠️ **T0 本身产生了真实外部性**（一次 ICMP echo、一次 DNS 查询、一次 TCP 握手到公网）。这是正对照**不可避免的最小代价**，且只做了一次。记录在此以便追溯。

**结论**：测量装置对"能出网"这一状态**敏感**。后续的"不能出网"因此是**有效证据**而非环境故障。

---

## 4. T1 —— 隔离生效（`--network=isolated`，默认）

```bash
python3 tools/collect.py --sample samples/net-probe.bat \
        --output results/t1-isolated.json          # --network 默认即 isolated
```

| 观测 | 结果 |
| :--- | :--- |
| 姿态 | `default` / `link_state=**down**`（持久 XML，冷启动即生效） |
| `[1] ICMP 8.8.8.8` | **`PING：传输失败。常见故障。`** → 100% 丢失 |
| `[2] DNS www.example.com` | `*** 默认服务器不可用` / `No response from server`（解析器地址为 `127.0.0.1` ⇒ 无 DNS 配置） |
| `[3] TCP 1.1.1.1:80` | `tcp=error: 发生一个或多个错误。` |
| **宿主侧 `egress_frames`** | **0** ← **隔离的硬证据** |
| `bytes_sent` / `bytes_recv` | 0 / 0 |

### 4.1 为什么"0 帧"比"ping 失败"更强

`ping` 失败只是**样本视角的观测**；`egress_frames=0` 是**宿主视角的观测** —— 它说明 guest 的帧**根本没有进入宿主网桥**。这条判据不受样本自身逻辑、错误处理、超时设置的影响：**样本无论如何都发不出一个包**。

这正是选 A2 而非 A3（nwfilter）的理由：A2 的失败模式是"物理上发不出去"（fail-closed），A3 的失败模式是"规则没挂上就静默放行"（fail-open）。

### 4.2 一个必须写下来的语义边界

`isolated` 下 **`attempted = null`（未知），不是 `false`**。

链路 down ⇒ guest 的帧不进宿主 ⇒ 宿主**观测不到**样本是否尝试过联网。返回 `false` 会是一个**我们支持不了的断言**。指纹因此使用三态，并附 `attempted_basis` 说明依据：

```
attempted=None
attempted_basis="link-down：guest 的帧不进入宿主网桥，因此无法观测连接尝试（只能证明没有出网）"
```

> **代价**：`isolated` 模式丢失"意图"。要意图就必须用 `recording`。这是任务书 R5（观测损失）在默认模式下的具体体现，**如实记录而非掩盖**。

---

## 5. T2 —— 记录生效（`--network=recording`）

```bash
python3 tools/collect.py --sample samples/net-probe.bat \
        --output results/t2-recording.json --network=recording
```

| 观测 | 结果 |
| :--- | :--- |
| 承载 | `bat2sh-rec`（`<forward mode='none'/>` + `<dns enable='no'/>`），链路 up |
| Guest IP | `192.168.200.36`（DHCP 成功） |
| `[1] ICMP 8.8.8.8` | `来自 192.168.200.1 的回复: **无法连到端口**` ⇒ ICMP port unreachable |
| `[2] DNS` | `DNS request timed out`（查询发往 `192.168.200.1:53`，该地址**无监听**） |
| `[3] TCP 1.1.1.1:80` | `tcp=timeout` |
| 宿主侧嗅探 | `egress_frames=67`，**32 条连接** |
| 关键连接 | `icmp 8.8.8.8` → **`refused`**；`tcp 1.1.1.1:80` → **`refused`**；30 条 `udp 192.168.200.1:53` → `sent` |
| **出网检查** | **没有任何 off-subnet `established`** ⇒ 零外部性 ✅ |
| `bytes_recv` | **0** —— 除了 ICMP 错误，**没有任何对端数据回来**（诚实且有意义） |

### 5.1 三层独立的"出不去"

| 层 | 机制 | 实测证据 |
| :--- | :--- | :--- |
| 1 | libvirt 为 `forward mode='none'` 自动生成 `iif/oif "virbr-rec" reject` | `nft list chain ip libvirt_network guest_output` 可见 |
| 2 | ufw `deny (routed)`，且 `ALLOW FWD` **只对 virbr0** | `ufw status verbose` |
| 3 | **不存在 192.168.200.0/24 的 masquerade 规则** ⇒ 报文只能以 RFC1918 源地址离开，上游必丢 | `nft list ruleset \| grep 192.168.200` = **0 条** |

第 3 层是"结构性"的那一层：**不是"我们拦住了"，而是"根本没有任何一处配置把它路由出去"**。前两层同时失效也不会导致出网。

### 5.2 `refused` 与 `no-reply` 必须区分（一次真实的判据缺陷）

本工具第二版的实测输出里，被拒的 TCP 连接显示为 **`no-reply`**（"静默丢弃"），而真实语义是 **`refused`**（"有东西在应答"）。

**根因**：拒绝是通过 **ICMP port unreachable** 表达的，而 ICMP 错误报文本身**不回指**是哪个连接触发的；第二版把它记成了一条独立的 `icmp <网关>` 流，于是原始 TCP 流只剩一个 SYN ⇒ 被判成 `no-reply`。

**修复**：解析 ICMP 错误报文**内嵌的"被引用报文的头部"**（IP 头 + L4 前 4 字节），把结果归因回原始流。

> **隐私说明**：读的是**被引用报文的头部**（源/目的/协议/端口），**不是应用 payload**。这正是 RFC 792 里 ICMP 错误报文携带该信息的用途，也是防火墙做"哪个连接被拒"归因的标准做法。读取范围仍在 `MAX_FRAME_BYTES = 192` 之内。

**为什么这个区分重要**：`refused` 通常让样本立刻走 error 分支，`no-reply` 会让它挂到超时 —— **两者对样本后续行为的影响完全不同**，也会让采集周期差一个数量级（实测：Windows TCP 超时 ~21 s）。

### 5.3 `forward mode='none'` 的隐藏坑（本 session 最大的一个）

**第一版 `recording` 完全观测不到东西**：样本三个路径全失败，但宿主侧**只看到多播噪声**（IGMP/SSDP/DHCPv6），一条真实尝试都没有。

**根因不是 DHCP 失败**（`virbr-rec.status` 显示 guest 确实拿到了 `192.168.200.36`），而是 libvirt 在生成的 dnsmasq 配置里写了：

```
dhcp-option=3
```

在 dnsmasq 里，**"选项 3 不带值" = 不通告 option 3（默认网关）**。于是 guest **有 IP、没有默认路由**：

```
ping 8.8.8.8     → 立即 "传输失败。常见故障。"（一个报文都没发出）
TCP 1.1.1.1:80   → 立即 error
```

宿主侧看起来就像"样本没联网"—— **正是 `network-policy.md` §1 R5 描述的假阴性**，而且它伪装成了正常结果。

**修复**：在 guest 内补一条默认路由（`route.exe add 0.0.0.0 mask 0.0.0.0 192.168.200.1 if <idx> metric 1`），并把 DNS 指向 `192.168.200.1`（该地址无 `:53` 监听 ⇒ 查询被 refuse，**可见但不外泄**）。

**这削弱安全性了吗？没有。** 依据是 §5.1 的第 3 层：宿主对 `192.168.200.0/24` **没有任何 masquerade 规则**。补路由只是让 guest **敢发包**，报文照样出不去。安全性来自"没有 NAT"，不来自"guest 没有路由"。

> **方法论收获**：把"隔离"和"可观测"分开设计是对的，但**默认姿态的安全性可能顺带消灭了可观测性**。`forward mode='none'` 是一个"安全到看不见"的例子 —— 如果只测了"有没有出网"就收工，会得到一个**通过的安全测试 + 一个静默失效的记录功能**。

---

## 6. T3 —— 回滚后隔离保持

网络姿态写在**域 XML** 里，覆盖层回滚动的是**磁盘**。判据 3 要验证的正是这条正交性。

```bash
# 步骤 1–3（不重新施加姿态）
python3 /tmp/t3.py
```

| 步骤 | 结果 |
| :--- | :--- |
| [1] 施加 `isolated` | `{"mac":"52:54:00:c4:73:fd","network":"default","link_state":"down"}` |
| [2] **覆盖层回滚**（`revert_op_ms=78`） | 丢弃 overlay，从 base 重建 |
| [3] 回滚后读域 XML（**未重新施加**） | `{"mac":"52:54:00:c4:73:fd","network":"default","link_state":"down"}` |
| — | **POSTURE SURVIVED ROLLBACK: YES** ✅（network / link_state / MAC 三项全同） |
| [4] base 完整性 | `unchanged=True` —— 基线全程未被写入 |

```bash
# 步骤 4：行为复核
python3 tools/collect.py --sample samples/net-probe.bat \
        --output results/t3-isolated-after-rollback.json --network=isolated
```

| 观测 | 结果 |
| :--- | :--- |
| `ping` | `传输失败。常见故障。` 100% 丢失 |
| `egress_frames` | **0** |
| `isolated` | `true`，`method=nic-link-down` |

**结论**：回滚**不会**削弱隔离。域 XML ≠ 磁盘，二者正交 —— 这正是选 A2（域定义）而不是"在 guest 里配防火墙"的关键好处：guest 内的任何网络配置都会被回滚掉，而**姿态本身不在 guest 里**。

---

## 7. 实现与集成

### 7.1 新增/修改的文件

| 文件 | 状态 | 说明 |
| :--- | :--- | :--- |
| `tools/netsniff.py` | **新增** | `AF_PACKET` 头部嗅探器（唯一的提权进程，只读） |
| `tools/net.py` | **新增** | 网络策略层：三档模式施加 + 采集窗口 + 指纹产出 |
| `tools/bat2sh-rec.network.xml` | **新增** | `recording` 承载网络定义（可入仓，幂等 `net-define`） |
| `tools/collect.py` | 修改 | 新增 `--network` / `--capture-window`；`SCHEMA_VERSION` **2 → 3** |
| `tools/vm.py` | 修改 | `check_env(..., dhcp_relevant=)` |
| `samples/net-probe.bat` | **新增** | 网络探针样本（驱动 T0–T3） |

### 7.2 三档模式

```bash
python3 tools/collect.py --sample X.bat --output r.json                    # 默认 = isolated
python3 tools/collect.py --sample X.bat --output r.json --network=isolated
python3 tools/collect.py --sample X.bat --output r.json --network=recording
python3 tools/collect.py --sample X.bat --output r.json --network=nat      # ⚠️ 放弃隔离
```

| 模式 | 链路 | 承载 | 外部性 | 可观测性 |
| :--- | :--- | :--- | :--- | :--- |
| `isolated`（默认） | **down** | `default`（不参与） | **零** | 只能证明"没出网" |
| `recording` | up | `bat2sh-rec`（无转发/无 NAT/无 DNS 上联） | **结构性零** | 连接级 dst/proto/result |
| `nat` | up | `default`（NAT） | ⚠️ **真实存在** | 完整 |

### 7.3 `SCHEMA_VERSION` 2 → 3（破坏性变更）

`network` 字段由 **列表**（旧版恒为 `[]` 占位符）改为**对象**：

```json
{
  "network": {
    "mode": "isolated", "isolated": true, "isolation_method": "nic-link-down",
    "network_name": "default", "link_state": "down", "iface": "virbr0",
    "attempted": null,
    "attempted_basis": "link-down：guest 的帧不进入宿主网桥…",
    "connections": [{"dst":"1.1.1.1:80","proto":"tcp","result":"refused",
                     "first_seen_ms":12597,"bytes_sent":96,"bytes_recv":0}],
    "bytes_sent": 0, "bytes_recv": 0,
    "egress_frames": 0,
    "capture": {"method":"af_packet-header-only","max_frame_bytes":192,
                "payload_read": false, "frames_guest":0, "...": "..."},
    "setup": {"requested":{}, "before":{}, "after":{}, "bridge":"virbr0"},
    "notes": []
  }
}
```

> **必须升版本的 reason**：旧版 `"network": []` 是**占位符**，不是"没有网络行为"。同时存在两种 schema 时，`[]` 会被误读成"样本没联网"——**一个安静的、方向性错误的结论**。

### 7.4 环境检查按模式调整

`isolated` 下 DHCP 检查**恒真**（链路 down ⇒ 不会有 DHCP ⇒ 丢弃计数必然静止）。这不是"检查通过"，而是"**该检查在本模式下没有鉴别力**"。指纹如实标注：

```
[ok  ] DHCP 未被丢弃: **本模式下无鉴别力**：链路 down ⇒ 不会有 DHCP ⇒ 计数必然静止（恒真，不构成证据）
```

不加这一条，会得到一份**"8 项检查全部通过"的假安全感**。

---

## 8. 隐私审计（§4.3 的"构造性质"落地了吗）

设计承诺：**不记录内容**，且这是**构造性质**而非纪律。逐条核对：

| 承诺 | 实现 | 可验证性 |
| :--- | :--- | :--- |
| 不读 payload | `s.recvfrom(MAX_FRAME_BYTES)`，`MAX_FRAME_BYTES = 192` | 单帧读入内存**上限 192 B**（Ethernet 14 + IPv4 最大头 60 + TCP 最大头 60 = 134，余量 58）；**payload 从不进入本进程** |
| 不落 pcap | 输出是 JSON（连接元数据），无 `write` 到 pcap | `grep -c pcap` 无写入路径 |
| DNS 只记 `dst` | 流表键为 `(proto, ip, port, ip, port)`；查询名从未被解析 | 见上：192 B 上限甚至覆盖不到 QNAME 之后的部分 |
| 产物可复核 | 指纹带 `payload_read: false` + `max_frame_bytes: 192` + `frames_at_max_len` | 本次 T0 实测 **96 帧达到 192 B 上限** ⇒ 这些帧**确实有 payload 未被读取** |

**唯一的例外必须写明**：ICMP 错误报文里**内嵌的原始 IP/L4 头部**会被解析（§5.2）。这是**头部**不是应用 payload，但仍属于"读进内存的字节"。它同样受 192 B 上限约束（14+20+8+60+4 = 106 < 192）。

> **未做代码级形式化验证**：以上是**代码审计 + 实测计数**，不是证明。`frames_at_max_len` 是"有 payload 我们没读"的**间接证据**，不是"我们从没读过 payload"的证明。

---

## 9. 实测踩到的坑（全部已修复，附根因）

| # | 坑 | 症状 | 根因 | 修复 |
| :-- | :--- | :--- | :--- | :--- |
| 1 | **`tcpdump` 未安装** | 任务书 §1.1 的 D1 方案不可用 | 宿主无 tcpdump/dumpcap/tshark | 改 `AF_PACKET` 纯 Python（**顺带得到更强的隐私保证**） |
| 2 | **嗅探启动竞态** | 整个 ping 未被记录，`connections` 为空 | 调用方 `sleep N` 后开跑，嗅探器尚未 bind | `netsniff --ready-file` 就绪握手；**必须等文件出现再执行样本** |
| 3 | **`forward mode='none'` 不通告网关** | recording 模式**完全观测不到**真实尝试 | libvirt 写 `dhcp-option=3`（=不通告默认网关）⇒ guest 有 IP 无路由 | guest 内补默认路由（安全性由"无 NAT 规则"保证） |
| 4 | **`Get-NetAdapter` 14 s** | `guest_egress` 耗时 **17 s** | CIM 冷启动 + 该类查询本身极慢 | 改原生 `route.exe`/`netsh`，**完全不用 PowerShell** ⇒ **2.0 s** |
| 5 | **`netsh` DNS 校验 12.5 s** | 同上 | netsh 会去"验证"这个**故意不可达**的 DNS 服务器并超时 | `validate=no` |
| 6 | **`$ErrorActionPreference='Stop'`** | 采集被挡在 exit=1 | 原生命令往 stderr 写东西被 PS 当成 `NativeCommandError` 终止脚本 | 去掉该设置，显式检查 `$LASTEXITCODE` |
| 7 | **f-string 里 `$gw` 不被插值** | `route add` 打印用法、rc=1 | Python f-string 只替换 `{...}`，`$gw` 原样传给 PS 且未定义 ⇒ 展开为空 | 补 `$gw='...'` 定义 |
| 8 | **`virsh net-info` 的 locale** | 活动网络被判为"未活动" | 中文输出用**全角冒号** `：`，且字段名是 **`活跃`**（不是 `活动`） | 改用**网桥接口是否存在**做主判据（与语言无关） |
| 9 | **`bytes_recv` 恒为 0** | 顶层汇总为 0，但流内有回包 | 按 `flow.direction` 过滤求和，而一条流两个方向都有字节 | 按**方向字节**求和 |
| 10 | **ICMP 错误未归因** | 被拒的 TCP 显示成 `no-reply` | ICMP 错误不回指原流 | 解析内嵌原始头（§5.2） |

> 坑 3、2、10 是**会产生"看起来正常但错误"的数据**的那一类 —— 它们不报错，只是**悄悄给出错误结论**。这与 `rollback-result.md` §6.4 的教训同源。

---

## 10. 残余风险与未验证项（明确披露）

| # | 项 | 状态 |
| :-- | :--- | :--- |
| 1 | `isolated` 下**看不到联网意图** | **已知限制**。`attempted=null`。改进方向：读 guest 内 TCP 失败计数器（`netstat -s`）作为"意图"的佐证 —— **本 session 未做** |
| 2 | A2 让 Windows 自行改写 NLA（网络位置感知）注册表状态 | 未观测（当前不采集注册表）。**上 L2 注册表差分时必须重新评估** |
| 3 | `nat` 模式外部性**不可撤回** | 设计如此；指纹强制 `isolated=false` + 显式 note |
| 4 | 自研解析器覆盖有限（VLAN 只跳一层、IPv6 扩展头/分片/隧道归 `unparsed`） | 计数如实上报，**不猜测**。本 session 实测 `frames_unparsed=0`（T2） |
| 5 | `recording` 需要 guest 内补默认路由 | 这是**对 guest 环境的主动修改**（偏离"纯观察"）。已在 §5.3 说明必要性；若样本对路由表敏感，会引入偏差 |
| 6 | `bat2sh-rec` 是**新增宿主对象**（网络 + 1 条 ufw 规则） | 幂等创建；ufw 规则**只开 udp/67**，未使用 `allow in on virbr-rec`（那会暴露宿主所有 0.0.0.0 服务） |
| 7 | Insider 构建的时间炸弹 | 见 §2.1，本期未到期，**到期时刻不可知** |
| 8 | **未做**：真实语料样本上的网络行为验证 | 属 Phase 2（批量）；批量默认 `isolated`，故**批量不会产生网络行为数据** |
| 9 | 嗅探需 `CAP_NET_RAW` | 提权面限制在 `netsniff.py` 单个只读脚本；`collect.py`/`vm.py` 主体不提权 |

---

## 11. 偏离披露（纪律 #2）

| # | 计划 | 实际 | 理由 |
| :-- | :--- | :--- | :--- |
| 1 | 任务书 §1.1 列了 **D1 tcpdump** | 改用 **D1b 纯 Python `AF_PACKET`** | tcpdump 未安装；且自研解析器能做到"结构上读不到 payload"，**比 pcap 更符合 §4.3 的隐私要求** |
| 2 | 任务书 §1.1 的 A1/A2/A3/D1 四选一 | **A2 作默认 + A4（新增）作 recording 承载** | 原四选项里没有任何一个能同时满足"零外部性"和"可记录"。A4 是**新增的第五个候选**，见 `network-policy.md` §5.5 |
| 3 | 任务书给出的 `network` JSON 里 `"attempted": true` | 实现为**三态**（`true`/`false`/`null`） | `isolated` 下无法观测意图，返回 `false` 是**支持不了的断言**。如实返回 `null` + `attempted_basis` |
| 4 | 任务书 §1.1 "不记录内容，只记录行为" | 额外解析了 **ICMP 内嵌的原始头** | 不解析就无法区分 `refused` 与 `no-reply`（§5.2）。读的是**头部**，受同一 192 B 上限约束，已单列披露 |
| 5 | 计划"网络姿态在回滚前施加" | 维持，并**额外**在 `recording` 下修改 guest 路由表 | §5.3 的 `dhcp-option=3` 坑使否则该模式无观测能力 |
| 6 | 未计划新增 ufw 规则 | 新增 1 条 `67/udp on virbr-rec` | DHCP 是宿主**入站**；**刻意不用** `allow in on virbr-rec`（那会开整个网桥） |

---

## 12. 下一步

1. **Phase 2 批量采集**（`batch-samples.md` / `tools/batch.py` / `batch-result.md`）—— 默认 `isolated`，因此批量产物**不含**网络行为。
2. 若要采集真实语料的网络行为，需**逐样本显式** `--network=recording`（默认不给，符合"默认拒绝"）。
3. 上 L2 注册表差分时，**重新评估** §10 第 2 项（NLA 副作用）。
4. 下个 session 换**零售版**镜像，消除 §2.1 的不确定性。
