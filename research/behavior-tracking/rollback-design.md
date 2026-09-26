# 覆盖层回滚设计：样本间状态隔离

> 时间：2026-09-26 · 状态：**设计（本文不实现，实测见 `rollback-result.md`）**
> 前置：`poc-result.md` §6.3（覆盖层方案**已设计、未实测**）、`vm-setup.md` §6.6/§6.7
> 基线 HEAD：`e1f8fb4`

## 1. 结论速览

| 决策项 | 结论 |
| :--- | :--- |
| **选定方案** | **C —— 独立 overlay qcow2（`qemu-img create -b base`）** |
| 落选 A（内部快照） | **不是"兼容性差"，是实测不可能** —— pflash/raw NVRAM（`poc-result.md` §5.6） |
| 落选 B（外部快照） | 可行但 backing chain 需 `blockcommit` 回收，复杂度换不来收益 |
| 落选 D（全盘复制） | 本机 btrfs **reflink 可用**（实测），D 也快；但 C 更省（覆盖层 193 KiB vs 8 GiB 引用） |
| 回滚判据 | **回滚操作本身** `< 30s`（实测目标）；**完整周期**另计并单列（见 §4.1） |
| 隔离判据 | **不能用 diff**（diff 自归一化，见 §5.1）→ 改用 **baseline manifest hash + after 绝对清单** |
| 域 XML 改动 | **零** —— 覆盖层路径与原盘路径同名，libvirt 无感 |

## 2. 现状事实（本次实测采集，非推断）

| 项 | 实测值 | 采集方式 |
| :--- | :--- | :--- |
| 域 | `win-behavior`，**运行中**（id 10） | `virsh -c qemu:///system list --all` |
| **连接 URI** | **`qemu:///system`** —— 默认 URI 是 `qemu:///session`，**裸 `virsh` 看不到 VM** | `virsh uri` |
| 磁盘 | `/var/lib/libvirt/images/win-behavior.qcow2` | `domblklist` |
| 磁盘规格 | 虚拟 64 GiB，实际占用 **10.58 GB**（sparse），`compat=1.1`，cluster 64 KiB | `qemu-img info -U` |
| **backing file** | **无**（`<backingStore/>` 为空）→ 当前盘**就是**可作基线的原始盘 | `dumpxml` |
| 固件 | UEFI `pc-q35-11.1`，**secure-boot=yes**，`loader=OVMF_CODE.secboot.4m.fd`（pflash/raw） | `dumpxml` |
| NVRAM | `/var/lib/libvirt/qemu/nvram/win-behavior_VARS.fd`（540 KiB，独立于磁盘） | `ls` |
| 快照 / checkpoint | **均为空** | `snapshot-list`、`checkpoint-list` |
| 内存 / vCPU | 8192 MiB / 4 | `dominfo` |
| 宿主 FS | **btrfs**（`/dev/nvme0n1p2`），658 GiB 可用 | `df -T` |
| **btrfs reflink** | **可用**（实测 `cp --reflink=always` 877 MB ISO 瞬时完成） | 实测 |
| Guest Agent | `guest-ping` → `{"return":{}}` | `qemu-agent-command` |
| DHCP drop 计数 | `packets 64`，**8 秒内 delta=0（静止）** | `nft list ruleset` ×2 |
| DHCP 租约 | `192.168.122.36/24`，`DESKTOP-S7I08BC` | `net-dhcp-leases` |
| `sudo` | **免密可用**（`sudo -n true` 通过） | 实测 |

**guest 内 `C:\poc` 现状**（决定"干净基线"要清掉什么）：

| 路径 | 大小 | 性质 | 基线处置 |
| :--- | ---: | :--- | :--- |
| `qemu-ga-x86_64.msi` | 11.9 MB | 环境安装物 | **保留**（环境溯源证据） |
| `virtio-win-gt-x64.msi` | 4.9 MB | 环境安装物 | **保留** |
| `ga-install.log` / `ga.log` / `gt.log` / `INSTALL-LOG.txt` | 0.5 MB | 环境安装物 | **保留** |
| `run\` | 空目录 | PoC 遗留 | **清掉** |
| `samples\poc-01-stdout.bat`、`samples\poc-02-fileops.bat` | 537 B | PoC 样本 | **清掉**（改为每次运行上传） |
| **`samples\work\a.txt`、`work\c.txt`** | 14 B | **PoC 样本副作用** | **清掉**（否则污染基线） |

> 最后一个是被忽视的：`poc-result.md` §6.3 说"基线重置用的是 guest 内 `rmdir` 清理"，
> 但磁盘上 `work\a.txt` 与 `work\c.txt` **仍在**。若直接以当前盘作基线，
> 这两个文件会被**永久固化进"干净状态"** —— 之后每次 A 样本的差分里它们都变成 `unchanged`，
> 而隔离测试会因此**假通过**。**基线自净是本设计的第一步，不是可选项。**

## 3. 方案选型

### 3.1 评估矩阵

| 方案 | 机制 | 回滚操作 | 域 XML | UEFI 兼容 | 失败模式 | 判定 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 内部快照** | `snapshot-create-as` | `snapshot-revert`（快） | 不改 | ❌ **实测不可能** | 需 QCOW2 格式 NVRAM；转格式后 "将 nvram 模板转换为其他目标格式不受支持" | **否决（硬约束）** |
| **B. 外部快照** | `snapshot-create-as --disk-only` | 建新层 + `blockcommit` 回收 | 不改 | ✅ | chain 增长；`blockcommit` 需 VM 运行/耗时；中断留脏链 | 可行但过重 |
| **C. 独立 overlay** | `qemu-img create -b base -F qcow2 ovl` | **`rm ovl && create ovl`** | **不改**（同名） | ✅ | 需 VM **关机**才能换文件；覆盖层误删=非破坏性（base 只读） | ✅ **选定** |
| **D. 全盘复制** | `cp --reflink=always base ovl` | `rm ovl && cp --reflink` | 不改 | ✅ | 依赖 FS reflink；非 reflink FS 上退化 10.5 GB 拷贝 | 备选 |

### 3.2 为什么是 C

1. **A 的死因是硬的，不是软的。** `poc-result.md` §5.6 已经撞过：pflash 固件的域不支持内部快照，
   且把 NVRAM 转 qcow2 后启动直接失败。这条**不是"兼容性差"，是此环境下的不可能** ——
   设计文档不应把它列为"简单但兼容性差"的可选项。
2. **B 的收益是"不用关机"，而 C 恰好不需要这个收益。** 见 §5.2：覆盖层让关机路径与确定性**解耦**，
   所以"必须关机"这个 C 的缺点在本场景里**不构成代价**。B 换来的能力用不上，却要付出 chain 管理复杂度。
3. **C 的失败模式最安全。** base 以**只读**方式被 qcow2 打开，任何写入只落覆盖层。
   最坏情况（覆盖层损坏/误删）→ 重建覆盖层即可，**基线不可能被破坏**。
   D 若拷到一半失败，会留下一个看似完整的半成品盘 —— 更危险。
4. **C 的回滚操作是 O(1)。** 创建覆盖层只写元数据：实测 193 KiB 文件（`qemu-img create` 200 ms 量级）。

> **D 作为备选保留**：本机 btrfs reflink 实测可用，D 也很快，且不需要 base/ovl 分离的理解成本。
> 若将来迁到非 btrfs 宿主，D 会退化，**C 不会** —— 所以主选 C。

### 3.3 选定架构

```
/var/lib/libvirt/images/
├── win-behavior.base.qcow2     ← 只读基线（干净 Windows + virtio + qemu-ga + C:\poc 环境）
└── win-behavior.qcow2          ← 覆盖层（每次回滚重建；域 XML 指向的仍是这个路径）
```

域 XML **一个字都不改** —— 这是方案 C 相对 B/D 的关键工程优势：
`<source file='.../win-behavior.qcow2'/>` 保持不变，libvirt 视角下什么都没发生过。

## 4. 关键约束与逐条设计

### 4.1 约束 1：回滚速度 < 30s

**必须区分两个量，否则结论会被偷换：**

| 指标 | 定义 | 目标 | 说明 |
| :--- | :--- | :--- | :--- |
| **`revert_op_ms`** | `rm ovl` + `qemu-img create -b base` 的**纯回滚操作** | **< 30s（硬判据）** | 这正是任务书"回滚"的字面含义 |
| `cycle_ms` | 上一个样本采集完 → 下一个样本 **agent 就绪** | 另计，**如实单列** | 含关机 + 回滚 + 冷启动 + agent 上线；**这才是批量吞吐的真实成本** |

**本设计的态度**：硬判据按 `revert_op_ms` 判定，但 `cycle_ms` **必须一并实测并写进结果**，
绝不用"回滚只要 0.2 秒"去掩盖"整轮要 60 秒"。两者都报，读者自行判断。

> `cycle_ms` 的优化路径（**本 session 不实现，仅记录**）：
> `virsh save` 保存"干净且 agent 在线"的 RAM 态 → 回滚后 `virsh restore` 免冷启动。
> 8 GiB RAM 的 save/restore 是否真比 Windows 冷启动快，**需实测**，不做无根据的断言。

### 4.2 约束 2：Guest Agent 存活

回滚 = 换磁盘 + 重启，所以"存活"的准确含义是**自动恢复**，而非"不中断"。

| 环节 | 设计 | 依据 |
| :--- | :--- | :--- |
| agent 自启 | `qemu-ga` 是 Windows **自启动服务**，随基线固化 | 基线一次性装好 |
| 通道驱动 | `vioser.sys` 随基线固化（**`vm-setup.md` §6.7 的根因坑**） | 基线内已装 virtio-win-gt |
| 等待策略 | **轮询 `guest-ping` 直到成功**，超时上限 + 明确报错 | 不假设固定等待时间 |
| 通道 `state` | 同时检查 `dumpxml` 的 `state='connected'` | `poc-result.md` §6.2 #4 |

**关键设计决定：`wait_for_agent()` 必须轮询 `guest-ping`，而不是 `sleep N`。**
固定 sleep 在慢启动时会假失败，在快启动时白等。轮询把"启动多久"这个不确定性**吸收掉**。

### 4.3 约束 3：快照点（干净状态的唯一定义）

**基线 = 以下全部满足的那个时刻**，一次性建立，此后永不修改：

1. Windows 已安装并完成 OOBE 绕过（审核模式，`poc-result.md` §5.5）
2. `virtio-win-gt-x64` 已装 → `vioser.sys` 存在（§6.7 坑）
3. `qemu-ga` 已装且 `guest-ping` 通过（§6.6 坑的前提）
4. `C:\poc\` 环境物保留、**样本与样本副作用已清除**（§2 表）
5. **guest 优雅关机后**（`virsh shutdown`，非 `destroy`）再冻结 —— 让 NTFS 干净

> 第 5 条只在**建基线这一次**重要。理由见 §5.2。

### 4.4 约束 4：样本间隔离

隔离的目标：**样本 A 的副作用（文件/注册表/服务/进程/网络）不得影响样本 B 的采集结果。**

| 作用域 | 覆盖层能否隔离 | 说明 |
| :--- | :--- | :--- |
| 文件系统 | ✅ 完整 | 整个 C: 盘在覆盖层里 |
| 注册表 | ✅ 完整 | 注册表 hive 是磁盘文件 |
| 服务 / 驱动配置 | ✅ 完整 | 同上 |
| 计划任务 / WMI 仓库 | ✅ 完整 | 同上 |
| 进程 / 内存残留 | ✅ 完整（冷启动清空） | **这是冷启动方案相对 RAM 快照的隐藏优势** |
| 网络侧状态（外部主机看到的） | ❌ **不隔离** | 见下 |
| 宿主机受影响的资源 | ❌ **不隔离** | 见下 |

**必须如实声明的两个隔离边界（覆盖层管不到）：**

1. **网络外部性**：若样本对外发包（扫描、下载、C2），**目标侧的状态变了就回不来**。
   覆盖层只回滚 guest 自己。→ 批量采集前必须明确网络策略（断网 / 黑洞 / 真实网络）并写进指纹。
2. **宿主机侧效应**：样本若攻击宿主（virtio 逃逸类），覆盖层无能为力。
   本 PoC 的研究目的是**行为观察**而非**安全沙箱**，此边界必须写进文档，不能默认"回滚=安全"。

## 5. 两个设计上的关键修正

### 5.1 ⚠️ 陷阱：**清单差分无法证明隔离**（diff 自归一化）

朴素判据是"B 的差分不含 A 创建的文件"。**这个判据是无效的**，原因：

差分是**相对 before 清单**算的。若回滚**失败**（A 的 `a.txt` 残留）：

| | before 清单 | after 清单 | `created` |
| :--- | :--- | :--- | :--- |
| 回滚**成功** | 无 `a.txt` | 无 `a.txt` | `[]` |
| 回滚**失败** | **有 `a.txt`** | **有 `a.txt`** | `[]` ← **一模一样！** |

残留文件在两次运行里都落在 `unchanged`（哈希相同），**差分里根本看不见**。
→ **用差分判隔离，会得到系统性假通过。**

**修正后的判据（三重，缺一不可）：**

| # | 判据 | 为什么它有效 |
| :--- | :--- | :--- |
| **J1** | **`baseline_manifest_hash` 在 A、B 两次运行中完全相同** | 直接证明"两次运行的起点是同一状态"。这是**最强**的一条 —— 起点相同，则结果的差只能来自样本 |
| **J2** | B 的 **after 绝对清单**中不含 A 独有产物 | 不看 diff，看绝对状态。绕开自归一化 |
| **J3** | A 跑完后、回滚前，**确认 A 的产物确实存在过** | 否则"B 里没有 A 的产物"可能只是因为 **A 压根没成功** —— 假通过的另一个方向 |

> **J3 是被忽略的反向陷阱**：如果 A 因为路径错/权限错而没写成功，
> "B 不含 A 的产物"会平凡成立，隔离测试**看起来通过但什么都没验证**。
> A 必须先被证明**有效**，隔离结论才有意义。这就是 `poc-result.md` 里
> "预验证的投入在此兑现"的同一条方法论。

因此指纹结构必须升级，**记录绝对清单而非仅记录差分**：

```jsonc
"filesystem": {
  "scope": "C:\\poc",
  "baseline_manifest_hash": "sha256:...",   // ← J1
  "before_count": 12,
  "after_count": 14,
  "created": [...], "modified": [...], "deleted": [...],
  "after_manifest": { "path": {"Hash": "...", "Length": 7}, ... },  // ← J2
  "known_artifacts": [...],                 // 采集器自己放进去的东西（见 §7.3）
  "blind_spots": ["reads","transient-effects","metadata-only-writes"]
}
```

### 5.2 ✅ 发现：覆盖层让**关机路径与确定性解耦**

朴素推理会说："回滚必须优雅关机，否则 NTFS 脏位会导致下次启动 chkdsk，引入不确定性。"

**在方案 C 下这个推理不成立**，因为：

```
写入只落覆盖层 → base 永远只读 → base 的 NTFS 永远干净
→ 每次启动都从同一份干净 base 开始 → 与上一次怎么关机无关
```

**推论（重要，直接影响实现选择）：**

- 可以用 **`virsh destroy`（硬断电）** 回滚，**不必等 Windows 优雅关机**。
  脏状态落在**即将被丢弃的覆盖层**里，**不会**进入下一次运行。
- 于是 `cycle_ms` 省掉整个 Windows 关机时间 —— 这是方案 C 的**额外**收益，
  在设计阶段不易看出（B/D 同样受益，但 C 的 O(1) 回滚让它最显著）。
- **但有一条前提**：优雅关机只在**建基线那一次**必要，用来保证 **base 自身**干净。

> **待实测验证**：`destroy` 是否真的不污染 base（比对 base 的 mtime/size/inode），
> 以及残留的 qcow2 dirty-flag 是否影响下次启动。**未验证前不得当作已确立结论。**

## 6. 与采集流程的集成

### 6.1 目标循环

```
for sample in samples:
    revert_to_clean()      # 1. 丢弃覆盖层，从 base 重建       → 判据 revert_op_ms < 30s
    start_vm()             # 2. 冷启动
    wait_for_agent()       # 3. 轮询 guest-ping 直到通（非 sleep）
    collect(sample)        # 4. 基线清单 → 上传 → 执行 → 采集 → 事后清单
    save_result()          # 5. 存档指纹（含 baseline_manifest_hash 与 after_manifest）
    stop_vm()              # 6. 进入下一轮
```

### 6.2 状态机（每步失败都必须"明确报错，不静默"）

| 状态 | 进入条件 | 失败检测 | 失败动作 |
| :--- | :--- | :--- | :--- |
| `PREFLIGHT` | 启动 | 任一项环境检查不过 | **中止**，报出具体项 |
| `REVERTING` | VM 已停机 | `qemu-img create` 非零退出 | **中止**，保留现场 |
| `BOOTING` | 覆盖层就绪 | `virsh start` 失败 | **中止**，报 libvirt 原文 |
| `WAITING_AGENT` | 域 running | `guest-ping` 超时 | **中止**；提示查 `vioser.sys`（§6.7 坑） |
| `UPLOADING` | agent 通 | `guest-file-write` 报错 | **中止** |
| `EXECUTING` | 上传完成 | 执行超时 | 记录 `timeout=true` 并**继续采集**（超时本身是行为） |
| `COLLECTING` | 执行返回 | 清单 JSON 解析失败 | 记录 `__parse_error__`，**不静默吞掉** |
| `ARCHIVED` | 指纹落盘 | 写失败 | **中止** |

> **`EXECUTING` 超时与别处不同**：样本跑不完**是一种要记录的行为**（比如死循环），
> 不是基础设施故障。所以它是"记录并继续"，而非"中止"。这个区分必须显式写进代码。

### 6.3 每轮必查清单（把 `vm-setup.md` 的两个根因坑固化成代码）

来自 `poc-result.md` §6.2 + `vm-setup.md` §6.6/§6.7：

| # | 检查 | 期望 | 失败含义 |
| :-- | :--- | :--- | :--- |
| 1 | `virsh -c qemu:///system` 可达 | 列出域 | **URI 错**（默认 `session` 看不到 VM —— 本次实测的第一坑） |
| 2 | `ufw` 放行 `virbr0`（in + route） | 两条规则在 | guest 无 DHCP/NAT（§6.6） |
| 3 | `nft` 的 `udp dport 67` drop 计数**两次采样不增长** | delta = 0 | 仍在丢 DHCP（§6.6） |
| 4 | base 镜像存在且**无 backing file** | 是 | 基线被误当覆盖层，回滚会递归 |
| 5 | 覆盖层路径 == 域 XML 的 disk source | 相同 | 回滚错文件 |
| 6 | `guest-ping` | `{"return":{}}` | 通道不通 → 查 `vioser.sys`（§6.7） |
| 7 | `dumpxml` 中 agent 通道 `state` | `connected` | 同上 |
| 8 | `chcp` | 记入指纹 | 编码解释错误（§5.4） |
| 9 | `{out,err}-truncated` | 均 `false` | 输出被截断，指纹不完整 |

### 6.4 为什么"环境检查"必须是**硬失败**

§6.6（ufw 丢 DHCP）与 §6.7（缺 `vioser`）的共同特征是：
**症状看起来像"样本行为异常"，实际是基础设施坏了**。

- 网络不通 → 样本的网络行为**静默地**变成空集 → 指纹里 `network: []` → **被读成"该样本不联网"**
- agent 不通 → 采集直接失败（这个至少显式）

**第 1 种是真正危险的**：它产生**看起来完全正常的错误数据**。
→ 所以环境检查**必须在采集前跑、必须硬失败**，绝不允许"降级继续"。

## 7. 采集脚本入仓设计

### 7.1 布局

```
research/behavior-tracking/tools/
├── collect.py       # CLI 入口：回滚 → 等 agent → 传输 → 执行 → 采集 → 报告
├── vm.py            # VM 原语：启停/回滚/agent 通信/文件传输
├── samples/         # 样本 bat（含隔离测试用的 B 样本）
└── README.md        # 用法 + 前置条件 + 故障诊断
```

### 7.2 参数化与可独立运行

| 要求 | 设计 |
| :--- | :--- |
| 不依赖 `/tmp` | 全部路径来自 CLI 参数 + 相对仓库根解析 |
| 样本路径参数化 | `--sample` |
| 输出路径参数化 | `--output` |
| 不做全局状态 | `DOMAIN`/`CONN` 作为参数，默认 `win-behavior` / `qemu:///system` |
| 失败可诊断 | 每步失败抛带**上下文原文**的异常（libvirt/qemu-img 的 stderr 不吞） |

### 7.3 采集器自身产物的归属（诚实性设计）

上传样本这个动作**本身**会写文件（`C:\poc\samples\<name>.bat`），它在采集范围内。
朴素做法是把它混进 `created` —— 那会污染行为指纹。

**设计**：`known_artifacts` 显式列出采集器自己写入的路径，并从 `created` 中分离：

```jsonc
"filesystem": {
  "created": [ /* 行为产物，不含采集器自身写入 */ ],
  "known_artifacts": [ {"path": "C:\\poc\\samples\\x.bat", "reason": "harness upload"} ],
  "after_manifest": { /* 原始全量，什么都不隐藏 */ }
}
```

**原则**：分离是为了**可读**，不是为了**隐藏**。`after_manifest` 保留全量原始数据，
任何人可复核。这与 `collection-design.md` §4.5「存 base64 原文 + 解码文本」是同一条原则。

## 8. 失败模式与对策

| 失败 | 症状 | 对策 |
| :--- | :--- | :--- |
| 回滚后 VM 起不来 | `virsh start` 报错 | 检查 base 完整性；覆盖层 `qemu-img info`；回退到 D 方案 |
| 回滚后 agent 不通 | `guest-ping` 超时 | 查通道 `state`；查 `vioser.sys`；延长轮询上限 |
| **base 被写入** | base mtime/size 变化 | **立即中止**（隔离前提已破）→ 检查 qcow2 是否以 rw 打开 base |
| 覆盖层权限错 | libvirt 起不来 | 覆盖层 owner 设为 `libvirt-qemu`，mode 600，与 base 一致 |
| 磁盘耗尽 | 覆盖层增长到 64 GiB | 每次回滚删除覆盖层 → 稳态不增长；监控 `/var/lib/libvirt/images` |
| Guest 内 chkdsk | 启动变慢/自动修复 | §5.2 预测可避免；**待实测确认** |

## 9. 未决项（明确标注，交给实测）

| # | 未决项 | 实测计划 |
| :-- | :--- | :--- |
| 1 | 方案 C 全流程**是否真的可行** | `rollback-result.md` §3 |
| 2 | `revert_op_ms` 实际值 | 计时 |
| 3 | `cycle_ms` 实际值（吞吐真实成本） | 计时 |
| 4 | **base 是否保持只读** | 比对 base 的 size/mtime/inode |
| 5 | `destroy`（硬断电）是否可替代优雅关机 | 对比两种停机方式后的启动表现 |
| 6 | 隔离判据 J1/J2/J3 是否全部成立 | A→回滚→B 实测 |
| 7 | `virsh save`/`restore` 能否缩短 `cycle_ms` | **本 session 不做**，仅记录 |
| 8 | 网络外部性策略（断网/黑洞/真实） | **本 session 不做**，属后续 |

## 10. 与既有文档的关系

| 文档 | 关系 |
| :--- | :--- |
| `poc-result.md` §6.3 | 本文**细化了它设计但未验证的方案**；并纠正了它"基线重置用 rmdir"的遗留污染（§2） |
| `poc-result.md` §7 遗留 #3 | "覆盖层回滚机制未实测" → **本文的实测部分即为此项** |
| `vm-setup.md` §6.6/§6.7 | 两个根因坑 → §6.3 固化为 `check_env()` 的硬检查 |
| `collection-design.md` §4 | 采集原语不变；本文只加**状态隔离**维度，不改采集语义 |
| `poc-samples.md` | 样本设计不变；本文新增隔离测试用 B 样本 |
