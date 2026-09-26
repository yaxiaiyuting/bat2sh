# Session 判定 —— 网络策略 + 批量采集验证

> 时间：2026-09-26 · 轨道：research/behavior-tracking（**研究轨道，未改 bat2sh 产品代码**）
> 起点 HEAD：`04f0dd4`（工作区干净）
> 上一 session 的判定（覆盖层回滚 + 采集脚本入仓）见 **`04f0dd4` 的 `session-verdict.md`**（本文件按仓库惯例滚动覆盖）
> 交付：`network-policy.md` / `network-policy-result.md` / `batch-samples.md` / `batch-result.md` / 本文件
> 代码：`tools/netsniff.py`(新) `tools/net.py`(新) `tools/batch.py`(新) `tools/bat2sh-rec.network.xml`(新) `samples/net-probe.bat`(新)；`tools/collect.py` `tools/vm.py` `tools/verify.py`(改)

---

## 一、判定表

| 问题 | 答案 | 依据 |
| :--- | :--- | :--- |
| **网络策略可行？** | ✅ **可行** | 三档模式（`isolated`/`recording`/`nat`）已实现并集成到 `collect.py --network=`。默认 `isolated`，宿主**零防火墙改动**（只新增 1 条 DHCP-only 入站规则给 recording 桥）。设计见 `network-policy.md` §6 |
| **隔离有效？** | ✅ **有效，可证明** | T1/T3：guest 三个出网路径全失败，**宿主侧 `egress_frames=0`**。这是宿主视角的硬证据，不依赖样本自身逻辑。批量中 16/16 复现 |
| **记录有效？** | ✅ **有效** | T2：32 条连接级记录，`icmp 8.8.8.8 → refused`、`tcp 1.1.1.1:80 → refused`；**无任何 off-subnet `established`** ⇒ 零外部性。隐私为**构造性质**（每帧最多读 192 B，无读 payload 的代码路径） |
| **批量采集可行？** | ✅ **可行** | **16/16 完成**，零失败。J1（16 次起点哈希完全相同）+ J2（240 组有向比对零残留）+ base 完整性 16/16 |
| **时间可接受？** | ✅ **可接受，但不宽裕** | 中位数 **37.8 s**；排除 2 个超时样本后平均 **38.2 s**（< 60 s）。含超时平均 52.6 s。**16 s 花在 Windows 冷启动**，且 2 个样本因交互式模态框烧掉 240 s（占总墙钟 28%） |
| **下一步？** | → **补 L2 采集（注册表 + 进程），并把行尾检测加进指纹** | 见 §四 |

### 判定说明

**"可行"的边界要说清楚**：

- 网络策略的**默认姿态（isolated）已经可以无条件用于批量** —— 它 fail-closed，且对宿主零侵入。
- `recording` **可用但需要在 guest 内补一条默认路由**（`network-policy-result.md` §5.3）。这是对 guest 环境的主动修改，属**已披露的偏离**，不是纯观察。
- 批量的**隔离结论强度受 J3 限制**：16 个样本里只有 6 个产出物，只有它们的隔离结论构成证据。这是判据在**正确工作**，不是缺陷。

---

## 二、前置确认（任务书 §一）

| # | 项 | 结果 |
| :-- | :--- | :--- |
| 1 | 工作区干净，HEAD = 04f0dd4 | ✅ 干净，`04f0dd4` |
| 2 | `research/behavior-tracking/tools/` 存在 | ✅ 存在（`collect.py`/`vm.py`/`verify.py`） |
| 3 | VM `win-behavior` 存在（关闭状态） | ✅ 存在，关闭。⚠️ **裸 `virsh` 看不到它**（默认 URI 是 `qemu:///session`）—— 必须 `--connect qemu:///system` |
| 4 | 单样本采集可跑 | ✅ 通过（本轮又跑了 20+ 次） |

> ⚠️ **工作区路径与 session cwd 不一致**：session 工作目录是 `/home/duanjb666/deepseek`（**不是 git 仓库**），实际项目在 `/home/duanjb666/bat2sh`。任务书里的相对路径（`research/behavior-tracking/…`）都相对于后者。已按后者执行。

---

## 三、暂停条件检查（任务书 §四）

| 条件 | 是否触发 |
| :--- | :--- |
| VM 不存在 | ❌ 未触发（存在） |
| 网络隔离无法实现 | ❌ 未触发（T1 实测有效） |
| 批量采集有样本污染 | ❌ 未触发（J1 哈希唯一 + J2 零残留） |
| 任何不确定 | ⚠️ **两处已判明的不确定，均已记录而非绕过**：见 §五 #1（recording 需改 guest 路由）与 #2（Insider 时间炸弹到期时刻不可知） |

**本 session 未暂停，全程跑完。**

---

## 四、下一步建议（按优先级）

| # | 建议 | 理由 | 成本 |
| :-- | :--- | :--- | :--- |
| **1** | **补 L2：注册表差分 + 进程采集** | 语料 **23.9%** 会改注册表/服务/账户，当前**完全不可见**（`batch-result.md` §3.2）。这是最大的能力缺口 | 中 |
| **2** | **指纹记录 `line_ending`** | 语料 **26.7%（55/206）是 LF-only**，cmd 会**解析错乱**（`batch-result.md` §4.1）。一个字段即可把"复杂脚本失败"与"行尾导致的解析崩溃"分开 | **极低**（读文件统计 `\r\n`） |
| **3** | 批量默认 `--timeout` 120 s → 45 s | 正常样本最慢 5 s；两个模态框超时白烧 240 s（占批次的 28%） | 极低 |
| **4** | 嗅探窗口支持"执行后延时" | `start` 类样本会派生后台进程，其网络行为落在窗口之外 | 低 |
| **5** | 每个样本跑 ≥2 次 | 当前单次运行**无法区分稳定行为与偶发行为**；`verify.py` 的重复性判据需要 ≥2 次 | 低（时间 ×2） |
| **6** | 换**零售版**镜像 | 消除 Insider 时间炸弹与"通知模式（未激活）"两个不确定源 | 中（需用户介入） |
| **7** | 若要采集真实语料的网络行为 | 逐样本 `--network=recording`；**不要**默认开 | 低 |

---

## 五、偏离与不确定（主动披露，纪律 #2）

### 1. `recording` 模式会修改 guest 的网络配置（**已披露的偏离**）

`forward mode='none'` 下 libvirt 写 `dhcp-option=3`（**不通告默认网关**），导致 guest 有 IP 却无默认路由 —— 样本连"尝试"都发不出，宿主侧只看到多播噪声，**与"样本没联网"不可区分**。

因此 `recording` 模式会在 guest 内执行 `route.exe add 0.0.0.0 …` 与 `netsh … set dnsservers`。**这是对被测环境的主动修改，不是纯观察。** 详细论证与三层安全性依据见 `network-policy-result.md` §5.3。

> 这批**批量采集全部用 `isolated`**，因此**不受此偏离影响**。

### 2. Insider 时间炸弹：本期未到期，但**到期时刻不可知**

- 可确证：`DisplayVersion=Dev`、`IsRetailOS=0`、构建时间戳 `260520-1434` ⇒ **构建于 2026-05-20**；guest 当前时间 2026-09-26，运行正常。
- **不可确证**：OS **没有**暴露可直接读取的到期时刻。`slmgr /xpr` 只报"通知模式"；`GracePeriodRemaining=0` 指的是**激活宽限期**（已耗尽），**不是** Dev 通道的构建时间炸弹。
- 附带风险：`LicenseStatus=5`（未激活）意味着**依赖激活状态的样本行为可能与真机有偏差**。本轮未观察到影响。

### 3. 任务书 §1.1 的四选一 → 实际新增了第五个候选（A4）

原四个候选（A1 无网卡 / A2 断链路 / A3 nwfilter / D1 tcpdump）**没有任何一个能同时满足"零外部性"和"可记录"**。A4（`forward mode='none'` 专用网络）是为 `recording` 新增的承载方案。
另：**D1 的 tcpdump 在本宿主上未安装**，改用纯 Python `AF_PACKET`（D1b），顺带得到更强的隐私保证（构造上读不到 payload）。

### 4. `network.attempted` 用三态而非布尔

任务书给的 JSON 里是 `"attempted": true`。实现为 `true`/`false`/`null`：`isolated` 下宿主**观测不到**意图，返回 `false` 会是**支持不了的断言**。改为 `null` + `attempted_basis` 说明依据。

### 5. `SCHEMA_VERSION` 2 → 3（破坏性）

`network` 由列表（旧版恒为 `[]` 占位符）改为对象。旧 `[]` **不代表"没有网络行为"**，混用会被误读。

---

## 六、本 session 最有价值的四条发现

1. **"隔离"与"可观测"必须分开设计，而且要分别验证。**
   `forward mode='none'` 是一个"**安全到看不见**"的例子：它顺带消灭了默认网关，于是记录功能**静默失效**，而症状（`connections` 为空）看起来就像"样本没联网"。**如果只测了"有没有出网"就收工，会得到一份通过的安全测试 + 一个坏掉的记录功能。**

2. **正对照（T0）不可省。**
   没有"不隔离时确实能通"，"隔离时不通"就**不可解释** —— 它可能是 ufw 挡了 DHCP、网关没配、或网卡没起。这是对 PoC 方法论的一个补强：J1/J2/J3 判"起点相同"，网络判决额外需要"**能力在未被限制时确实存在**"。

3. **`egress_frames=0` 比 `ping 失败` 强得多。**
   前者是宿主视角的观测（帧根本没进网桥），不依赖样本自身的逻辑、错误处理或超时设置。**判据要尽量落在被测对象之外。**

4. **语料有 26.7% 是 LF-only，cmd.exe 会解析错乱。**
   这是**归因问题**而非采集缺陷：指纹正确记下了 `rc=255` + 乱码 stderr，根因由 A/B 对照实验（只把 LF 换成 CRLF，`rc` 从 255 变 0、输出完整）**决定性证明**。这些脚本在真机上同样跑不对。

> 另外三条"会产生**看起来正常但错误**的数据"的坑（嗅探启动竞态、`guest-exec` 的 cwd 是 System32、清单只收文件），全部在批量执行**之前**被发现并修复 —— 若留到跑完再看，会得到"16/16 通过但指纹大面积空白"的报告，而空白会被误读成"这些样本没有行为"。

---

## 七、交付物清单

| 文件 | 状态 |
| :--- | :--- |
| `research/behavior-tracking/network-policy.md` | ✅ 设计（威胁模型 / 候选评估 / 选定方案 / 判据） |
| `research/behavior-tracking/network-policy-result.md` | ✅ 实测（T0–T3 + 10 个实测坑 + 隐私审计 + 偏离披露） |
| `research/behavior-tracking/batch-samples.md` | ✅ 选样（16 个，覆盖矩阵，执行前修复的 3 个缺陷） |
| `research/behavior-tracking/batch-samples.txt` | ✅ 机器可读清单（TSV + SHA256） |
| `research/behavior-tracking/batch-result.md` | ✅ 结果分析（指纹总表 + 3 个根因发现 + 时间分析） |
| `research/behavior-tracking/session-verdict.md` | ✅ 本文件 |
| `tools/netsniff.py` | ✅ 新增：`AF_PACKET` 头部嗅探（唯一提权进程，只读） |
| `tools/net.py` | ✅ 新增：网络策略层（三档模式 + 采集窗口 + 指纹） |
| `tools/batch.py` | ✅ 新增：批量执行器（失败不阻塞 + 进度 + 批量级验证） |
| `tools/bat2sh-rec.network.xml` | ✅ 新增：recording 承载网络（幂等 `net-define`） |
| `tools/collect.py` | ✅ 修改：`--network` / `--workdir` / `--guest-name`；`SCHEMA_VERSION=3`；目录行为 |
| `tools/vm.py` | ✅ 修改：`dirs()`；`check_env(dhcp_relevant=)` |
| `tools/verify.py` | ✅ 修改：J3 计入目录产物 |
| `samples/net-probe.bat` | ✅ 新增：网络探针样本（T0–T3 的驱动） |
| `results/` | ✅ 原始指纹（T0–T3 + 批量 16 个 + A/B 对照） |

**未改任何 bat2sh 产品代码**（`python/`、`src/`、`tests/` 均未触碰）。
