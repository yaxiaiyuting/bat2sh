# 网络策略设计 —— 行为采集的隔离与记录

> 时间：2026-09-26 · 状态：**设计定稿，待实测验证**
> 前置：`rollback-result.md`（覆盖层回滚实测通过，commit `04f0dd4`）
> 轨道：research/behavior-tracking（**研究轨道，不改 bat2sh 产品代码**）
> 关联：`collection-design.md` §7（网络未采集）、`session-verdict.md`（L2 缺口）

---

## 1. 为什么网络需要一个**策略**，而不是一个开关

采集器目前把样本关在一台可回滚的 Windows VM 里（`rollback-result.md`）。回滚解决的是**磁盘状态**的外部性：样本改了 `C:\`，覆盖层一丢就干净。

网络是**唯一一个回滚管不到的作用面**：

| # | 风险 | 描述 | 回滚能否消除 |
| :-- | :--- | :--- | :--- |
| R1 | **外部性** | 样本改的是**对端**的状态 —— 往 FTP 传了文件、往论坛发了帖、给某个服务注册了账号。对端不在我们的 qcow2 里，**丢弃覆盖层不会撤销它**。 | ❌ **不能** |
| R2 | **污染** | 样本通过外部服务互相影响：样本 A 上传 `/a.txt` 到某 paste 服务，样本 B 读到它。J1/J2/J3 那套判据**看不见这条通路** —— 磁盘清单相同，但 B 的输入已经被 A 改过。 | ❌ **不能** |
| R3 | **隐私 / 数据外泄** | 样本可能把 guest 内的数据（主机名、用户名、路径、环境变量、样本正文）发到外部。这些数据出自我们的**测试环境**，但一旦发出即不可召回。 | ❌ **不能** |
| R4 | **可归因性** | 出网流量带的是**本机公网 IP**。样本若做恶意行为，来源会指向本机。 | ❌ **不能** |
| R5 | **观测损失**（反向风险） | 如果简单地"拔网线"，样本的网络行为就**完全不可见**了 —— 而网络行为恰恰是行为指纹里信息量最高的一类。 | — |

> **R1–R4 的共同结论**：网络风险**不能靠回滚兜底**，必须在**策略层**解决 —— 默认不允许，需要时按例外放行，且放行必须可记录。
>
> **R5 的反向约束**：策略不能只是"关掉网络"。必须同时提供一条**能看到尝试、但看不到外泄**的路径。

---

## 2. 只读诊断（先看现场，再定方案）

采集前对宿主网络栈做的**只读**观察（判据来自这些事实，不是猜的）：

| 观察项 | 实测值 | 对策略的意义 |
| :--- | :--- | :--- |
| `virsh list --all`（裸 `virsh`） | **看不到 `win-behavior`** | 默认 URI = `qemu:///session`。所有命令必须显式 `--connect qemu:///system`（`rollback-design.md` §2 已固化） |
| `virsh -c qemu:///system list --all` | `win-behavior` 关闭 | 域存在 |
| 域网卡数量 | **1** 个 | `type='network' source=default`，`model=e1000e`，MAC `52:54:00:c4:73:fd` |
| `virsh net-list` | `default` 活动，`<forward mode='nat'/>` | **默认网络是 NAT** ⇒ 直连就是全量出网 |
| `virsh snapshot-list win-behavior` | **空** | 回滚不是靠 libvirt 快照，是靠**覆盖层重建**（`rollback-design.md` §3） |
| `sysctl net.ipv4.ip_forward` | `1` | 宿主**会**转发。隔离不能指望"宿主不转发"这个默认值 |
| `iptables -S FORWARD` | `-P FORWARD DROP` | 转发**默认拒绝** —— 这是可利用的结构性事实 |
| `ufw status verbose` | `deny (routed)`，仅 `ALLOW FWD ... on virbr0` | **只有 `virbr0` 被放行转发**；任何**其他**网桥的转发流量都被 ufw 丢弃 |
| `nft list tables` | 无 `bat2sh*` 表 | 当前**没有**为采集而设的防火墙规则（干净起点） |
| `tcpdump` / `dumpcap` / `tshark` | **全部未安装** | ⚠️ **任务书 §1.1 的 D1 方案（tcpdump）不可用** —— 见 §5.4 |
| `virt-xml --network link_state=` | **支持**，dry-run 产生 `<link state="down"/>` | A2 方案可实现，且能写进**持久 XML** |

> **两条最有价值的结构性事实**：
> 1. `FORWARD` 策略是 **DROP**，且 ufw 只对 `virbr0` 开口 —— 所以**换一个网桥就天然出不去**，不需要新增任何防火墙规则。
> 2. `link_state` 能进**持久 XML**（不是运行时开关）⇒ 域**从第一帧起**就没有链路，不存在"启动过程中短暂有网"的竞态窗口。

---

## 3. 默认策略 + 例外机制

**默认拒绝，例外按需，且例外必留痕。**

| 类别 | 网络 | 依据 |
| :--- | :--- | :--- |
| **本地样本**（绝大多数） | **完全隔离**（`isolated`） | 不需要网络。给不需要的能力＝纯增风险 |
| **网络样本**（少数） | **按需**（`recording` / `nat`） | 显式选择，且 `nat` 需自担外部性 |

三档模式（即 `collect.py --network=` 的取值）：

| 模式 | 语义 | 外部性 | 可观测性 | 用途 |
| :--- | :--- | :--- | :--- | :--- |
| **`isolated`**（默认） | vNIC 链路 **down**，持久 XML | **零** —— 报文根本发不出去 | 弱：只能证明"没出网" + 样本侧的失败文本 | 批量采集、样本普查 |
| **`recording`** | 链路 **up**，但接在**无转发**的专用网络上；宿主侧按**头部**记录 | **结构性为零**（无 NAT、无路由、无 DNS 上联） | 强：连接尝试的 dst/proto/result | 网络行为的定向采集 |
| **`nat`** | 接 `default`（NAT），全量出网 | ⚠️ **存在** —— R1/R2/R3/R4 全部成立 | 强 | **仅**在明确需要真实网络时显式开启 |

> `nat` 不是"另一个隔离级别"，而是**显式放弃隔离**。它必须在指纹里留下不可忽略的标记（`network.isolated=false` + `notes` 警告），否则事后无法区分"这个样本没联网"和"这个样本联了网但我们没拦住"。

---

## 4. 网络行为记录

### 4.1 记录什么

**无论哪种模式，`network` 字段必须存在且可解释**（缺字段 ≠ 没联网）：

```json
{
  "network": {
    "mode": "isolated",
    "isolated": true,
    "isolation_method": "nic-link-down",
    "attempted": false,
    "connections": [],
    "bytes_sent": 0,
    "bytes_recv": 0,
    "capture": {"iface": "virbr0", "frames_seen": 0, "duration_ms": 31842},
    "notes": []
  }
}
```

`connections[]` 每项只含**连接元数据**：

```json
{"dst": "192.168.1.1:21", "proto": "tcp", "result": "refused", "first_seen_ms": 1204, "bytes_sent": 0}
```

| 字段 | 取值 | 说明 |
| :--- | :--- | :--- |
| `dst` | `ip:port` | 目的地址（IPv6 用 `[addr]:port`） |
| `proto` | `tcp` / `udp` / `icmp` / `other` | 传输层 |
| `result` | `refused` / `established` / `no-reply` / `unreachable` / `sent` | 见 §4.2 |
| `first_seen_ms` | int | 相对采集开始的毫秒偏移（用于对齐样本执行窗口） |

### 4.2 `result` 的判定规则

| result | 判据（宿主侧观察） |
| :--- | :--- |
| `established` | 收到对端 `SYN-ACK`（TCP）—— 或 UDP 收到对端回包 |
| `refused` | 收到 `RST`，或 ICMP type 3 code 3（port unreachable） |
| `unreachable` | ICMP type 3 code 0/1/9/10（net/host/prohibited） |
| `no-reply` | 只有出向 `SYN`，窗口内无任何回包（=被静默丢弃） |
| `sent` | UDP/ICMP 单向发出，无回包（UDP 无握手，不能判"拒绝"） |

> `refused` 与 `no-reply` 的区别**有价值**：前者说明"有东西在应答"（可能暴露中间设备），后者说明"被静默丢弃"。二者对样本的后续行为影响也不同（`refused` 通常让样本立刻走 error 分支，`no-reply` 会让它挂到超时）。

### 4.3 **不记录内容**（隐私 / 安全）

**硬约束**：

- 只解析 **L2/L3/L4 头部**，**永不**读取或落盘 payload。
- **不落 pcap**。pcap 会把 payload 一起写进文件 —— 那等于把样本可能外泄的数据**抄送到宿主磁盘**，与 R3 的目标相反。
- DNS 查询**只记 `dst`（如 `192.168.122.1:53`）**，不记查询的域名 —— 域名本身就是敏感信息。
- 因此记录产物是**结构性免疫**于内容泄露的：解析器里根本没有读 payload 的代码路径。

> 这不是"我们承诺不存内容"，而是"**工具在构造上取不到内容**"。前者是纪律，后者是可验证的性质（见 `network-policy-result.md` 的代码审计项）。

---

## 5. 隔离实现候选评估

### 5.1 A1 —— 移除网卡（`virt-xml --remove-device --network all`）

| 维度 | 评价 |
| :--- | :--- |
| 隔离强度 | **最强**：guest 连适配器都没有 |
| 宿主扰动 | 中：需改域 XML，且**回滚恢复时要重建整个 `<interface>`**（MAC、model、address 都要还原） |
| 真实性 | **低**：多数样本会先枚举适配器；"没有任何网卡"与"网线没插"走**不同的代码分支**，会引入**策略自身造成的指纹偏差** |
| 可记录性 | 无（没有链路可抓） |

**否决**：破坏样本行为真实性，且恢复面比 A2 大。隔离强度上的收益（相对 A2）在本威胁模型下是**边际的** —— A2 已经让报文发不出去。

### 5.2 A2 —— 断开链路（`link_state='down'`）✅ **选为默认**

| 维度 | 评价 |
| :--- | :--- |
| 隔离强度 | **强**：QEMU 侧 vNIC 链路 down ⇒ guest 的帧**根本不会进入宿主**，无"防火墙规则写错就漏"的问题 |
| 宿主扰动 | **最小**：只给 `<interface>` 加一个 `<link state="down"/>` 子元素 |
| 可逆性 | **极易**：删掉该元素即恢复 |
| 持久性 | 可写进**持久 XML** ⇒ **开机的第一帧起**就无链路，无竞态窗口 |
| 真实性 | **高**：适配器仍在，Windows 显示"网络电缆被拔出" —— 这是真实存在的环境状态 |
| 对回滚的正交性 | 域 XML ≠ 磁盘 ⇒ **覆盖层回滚不会碰到它**（判据 3 要验证的正是这条） |

**两种施加方式**（都要实现，用途不同）：

| 方式 | 命令 | 持久 | 用途 |
| :--- | :--- | :--- | :--- |
| **持久**（默认路径） | `virt-xml --edit --network link_state=down` | ✅ 写进 XML | 采集的默认姿态；域从冷启动起就隔离 |
| **运行时** | `virsh domif-setlink <dom> <mac> down` | ❌ 仅本次运行 | 不重启切换；用于对照实验 |

**已知语义边界（必须写进文档，否则会被误用）**：

- 链路 down **不等于**"样本没尝试联网"。样本仍会调 `connect()`，只是拿到 `WSAENETUNREACH`。**"尝试了"与"出网了"是两件事**，指纹必须能区分（§4.1 的 `attempted` 与 `bytes_sent` 就是为此）。
- Windows 在链路 down 时可能**主动改写网络位置感知（NLA）状态**并写入注册表 —— 这是**环境自身**的副作用，不是样本的。当前采集器**不观测注册表**（`session-verdict.md` 已知缺口），所以暂不影响指纹；但它意味着 **A2 模式下不能把"注册表有变化"归因给样本**。记为遗留风险。

### 5.3 A3 —— libvirt nwfilter

| 维度 | 评价 |
| :--- | :--- |
| 隔离强度 | 中：依赖 ebtables/iptables 规则**被正确挂到该 vNIC 上**。规则没挂上 ⇒ **静默失效**（表现为"样本能上网"，而不是报错） |
| 宿主扰动 | 中：`virsh nwfilter-define` + 域 XML `<filterref>` |
| 与 ufw 的关系 | 宿主同时跑 ufw（iptables-nft）。两套东西都往 `filter` 表插规则，**顺序与优先级不在我们控制内** |
| 可观测性 | 可加 `log` 规则，但日志走内核 log（有速率限制），解析脆弱 |

**否决为默认**：失败模式是"静默失效"（fail-open），而 A2 的失败模式是"物理上发不出去"（fail-closed）。**默认策略必须是 fail-closed 的。**

### 5.4 D1 —— 宿主侧抓包

| 子方案 | 状态 | 说明 |
| :--- | :--- | :--- |
| **D1a `tcpdump`** | ❌ **不可用** | 实测**未安装**（`dumpcap`/`tshark` 同样缺失）。安装需联网取包 + root，**扩大了宿主的供应链面**，与"降低风险"的初衷相悖 |
| **D1b 纯 Python `AF_PACKET`** | ✅ **选为记录方案** | 标准库 `socket`，无需安装任何东西；且因为**自己写解析器**，可以做到"**只解析头部、结构上读不到 payload**"（§4.3） |

**D1b 的取舍**：

| 优点 | 代价 |
| :--- | :--- |
| 零新增依赖 / 零供应链面 | 需要 `CAP_NET_RAW`（⇒ 以 `sudo -n` 跑一个**独立小进程**，而不是把整个采集器提权） |
| 只解析头部 ⇒ 隐私 by construction | 自研解析器有 bug 风险（覆盖不到的分片/隧道会被归入 `other`，**不猜测**） |
| 与 `nat`/`recording` 模式解耦 | 需要按 `dst MAC` 过滤以排除宿主自身与其他 VM 的流量 |

> **权限最小化**：提权的只有 `netsniff.py` 这一个 ~200 行的只读脚本；`collect.py` / `vm.py` 主体仍以普通用户运行。抓包进程通过一个临时 JSONL 文件回传结果。

### 5.5 A4 —— 无转发的专用网络（`recording` 模式的承载）

`default` 是 **NAT**。若 `recording` 模式直接挂在 `default` 上，链路一 up 就是**全量出网**（R1–R4 全部成立）。所以在"可记录"与"无外部性"之间需要一个承载：

```
<network>
  <name>bat2sh-rec</name>
  <forward mode='none'/>          ← 没有 NAT，没有转发。出网在**结构上**不可能
  <bridge name='virbr-rec'/>
  <ip address='192.168.200.1' netmask='255.255.255.0'>
    <dhcp><range start='192.168.200.2' end='192.168.200.254'/></dhcp>
  </ip>
  <dns enable='no'/>              ← 关掉 dnsmasq 的上联转发 ⇒ DNS 也不能外泄
</network>
```

**为什么这是"结构性"而不是"规则性"的**：

| 通路 | 为什么出不去 |
| :--- | :--- |
| guest → 互联网 | `forward mode='none'` ⇒ libvirt **不建** NAT/转发规则；且 ufw 的 `ALLOW FWD` **只对 `virbr0`**，`virbr-rec` 落进 `FORWARD DROP` 默认策略 |
| guest → DNS 外泄 | `<dns enable='no'/>` ⇒ dnsmasq **不做递归/转发**。查域名只能拿到"无应答" |
| guest → 宿主其他服务 | 只剩宿主在 `192.168.200.1` 上的入站（DHCP），以及 ufw 输入策略允许的范围 |

> **双层保险**：第 1 层是 libvirt 不配置转发（结构性），第 2 层是 ufw 的 `deny (routed)` 默认策略。**任一层单独成立即可阻断**，两层同时失效才可能出网。

**代价 / 开口**：DHCP 是宿主**入站**，被 ufw 的 `deny (incoming)` 挡住 ⇒ 需要一条 `ufw allow in on virbr-rec`。这是本方案**唯一**的宿主防火墙改动，且**只开 DHCP/DNS 入站，不开转发**。

**`refused` vs `no-reply` 的取舍**：`forward mode='none'` 下宿主对 guest 的出向报文是 **DROP**（ufw 策略）⇒ 样本会看到 **超时**（`no-reply`），而不是 `refused`。TCP 超时在 Windows 上默认 ~21s（3 次 SYN 重传），会让**网络样本的采集周期显著变长**。

> 若实测确认超时不可接受，追加第 3 层：一条**按 `virbr-rec` 限定**的 nftables `reject` 规则，让宿主立刻回 RST/ICMP ⇒ `result=refused`、样本立即走 error 分支。这**只影响速度，不影响安全性**（安全性已由前两层保证）。

---

## 6. 选定方案

| 角色 | 方案 | 一句话理由 |
| :--- | :--- | :--- |
| **默认隔离** | **A2** —— `link_state='down'`（持久 XML） | 宿主零改动、fail-closed、开机即无链路、与覆盖层回滚正交 |
| **记录方案** | **D1b** —— 纯 Python `AF_PACKET` 头部嗅探 | `tcpdump` 不可用；且只有自研解析器才能**结构上**保证不碰 payload |
| **记录承载** | **A4** —— `bat2sh-rec`（`forward mode='none'` + `dns enable='no'`） | 让"可记录"不必以"可出网"为代价 |
| 显式放弃隔离 | `default` NAT（`--network=nat`） | 少数样本确需真实网络时必须显式选择并留痕 |

### 6.1 组合矩阵

| 模式 | 链路 | 承载网络 | 记录 | 外部性 | fail 模式 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `isolated`（默认） | **down** | `default`（不参与） | 宿主侧零帧证明 | **无** | fail-closed |
| `recording` | up | `bat2sh-rec` | 头部嗅探 + 结构化 `connections[]` | **结构性无** | fail-closed（无 NAT） |
| `nat` | up | `default`（NAT） | 头部嗅探（若启用） | ⚠️ **有** | fail-open（**故意**） |

### 6.2 待实测验证的判据

| # | 判据 | 通过条件 |
| :--- | :--- | :--- |
| **T0** | **正对照** —— 未隔离时确实能出网 | `nat` 下 guest `ping 8.8.8.8` **成功** |
| **T1** | 隔离生效 | `isolated` 下 guest `ping 8.8.8.8` **失败**，且宿主侧**零帧** |
| **T2** | 记录生效 | `recording` 下产生 `connections[]`，含 `dst`/`proto`/`result`，且**宿主侧确认无出网** |
| **T3** | 回滚后隔离保持 | 覆盖层回滚后重跑 T1，结论不变 |

> **为什么 T0 是必需的**：没有正对照，"`ping` 失败"这个观测就**不可解释** —— 它可能是隔离生效，也可能是 ufw 挡了 DHCP（`vm-setup.md` §6.6 的真实坑）、网关没配、或网卡驱动没起。**只有先证明"不隔离时能通"，"隔离时不通"才构成证据。** 这是本 session 对 PoC 方法论的一个补强：`rollback-result.md` 的 J1/J2/J3 判的是"起点相同"，网络判决额外需要"**能力在未被限制时确实存在**"。

### 6.3 残余风险（明确披露）

| # | 残余风险 | 严重度 | 缓解 |
| :--- | :--- | :--- | :--- |
| 1 | `isolated` 下**看不到**样本的联网*意图*（只看到"没出网"） | 中 | 需要意图时用 `recording`；样本的 stderr/exit code 仍会暴露失败分支 |
| 2 | A2 让 Windows 自行改写 NLA 注册表状态 | 低 | 当前不观测注册表；**上 L2 注册表差分时必须重新评估** |
| 3 | `nat` 模式的外部性**不可撤回** | **高** | 非默认；指纹强制标记 `isolated=false`；建议仅用于确有必要的样本 |
| 4 | `AF_PACKET` 自研解析器覆盖面有限（VLAN/隧道/分片） | 低 | 不认识的帧归入 `other` 并计数，**不猜测、不丢弃** |
| 5 | 嗅探需要 `CAP_NET_RAW` | 低 | 提权面限制在独立只读脚本 `netsniff.py` |
| 6 | `bat2sh-rec` 网络是**新的宿主对象**，需随环境一起清理 | 低 | 幂等创建；`--network=nat/isolated` 时域 XML 切回 `default` |
| 7 | Insider 预发布镜像自带**时间炸弹** | 中 | 见 `session-verdict.md`；本期未见到期，下期换零售版 |

---

## 7. 与采集器的集成（`--network=`）

```bash
# 默认：完全隔离
python3 collect.py --sample samples/copy.bat --output results/copy.json

# 等价的显式写法
python3 collect.py --sample samples/copy.bat --output results/copy.json --network=isolated

# 记录模式：可看到连接尝试，但出不去
python3 collect.py --sample samples/net-probe.bat --output results/net.json --network=recording

# 显式放弃隔离（⚠️ 外部性）
python3 collect.py --sample samples/net-probe.bat --output results/net.json --network=nat
```

**集成要点**：

1. **默认必须是 `isolated`** —— 不给参数就是最安全的姿态（安全默认值原则）。
2. 模式在**回滚之前**施加（链路状态属于域 XML / 域定义，必须在冷启动前定好）。
3. `network` 字段从 `[]`（当前的占位列表）**改为对象** ⇒ `SCHEMA_VERSION` **2 → 3**（破坏性变更，必须显式升版本，否则旧指纹会被误读）。
4. 嗅探进程**随样本执行窗口启停**，窗口外不监听（减少无关流量进入指纹）。
5. 环境检查要**按模式**调整：`isolated` 下 DHCP 检查会**恒真**（链路 down ⇒ 没有 DHCP ⇒ 丢弃计数必然静止），必须标注为"该模式下无鉴别力"，否则会得到一份"看起来通过了检查"的假安全感。

---

## 8. 下一步

1. 实现 `tools/netsniff.py`（AF_PACKET 头部嗅探）与 `tools/net.py`（策略施加 + 模式管理）。
2. 建 `bat2sh-rec` 网络并验证 DHCP（含唯一的 ufw 开口）。
3. 跑 T0 / T1 / T2 / T3，结果写入 `network-policy-result.md`。
4. 集成 `--network=` 到 `collect.py`（含 `SCHEMA_VERSION` 升版）。
5. 进入批量采集验证（`batch-samples.md` / `batch.py`）。
