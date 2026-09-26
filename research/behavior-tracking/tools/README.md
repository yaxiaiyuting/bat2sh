# 行为采集工具（L3 输出效果层）

> 研究基础设施，**不是 bat2sh 产品代码**。
> 设计依据：`../rollback-design.md` · `../network-policy.md`
> 实测结果：`../rollback-result.md` · `../network-policy-result.md` · `../batch-result.md`

## 这是什么

把 PoC 从「能采一次」变成「能反复采」：

- **覆盖层回滚** —— 每个样本前把 VM 恢复到逐字节相同的干净状态
- **样本间隔离** —— 用三重判据（J1/J2/J3）证明，而非仅凭差分
- **网络隔离 + 记录** —— 三档网络姿态；默认零出网，可选连接级记录（不记内容）
- **一条命令跑完** —— 回滚 → 网络姿态 → 等 agent → 传输 → 执行 → 采集 → 报告
- **批量执行** —— `batch.py` 跑完整清单，失败不阻塞，附批量级验证

## 文件

| 文件 | 职责 |
| :--- | :--- |
| `collect.py` | **CLI 入口**：单个样本的完整周期 |
| `batch.py` | **CLI 入口**：批量执行清单 + 批量级验证 |
| `verify.py` | **CLI 入口**：J1/J2/J3 隔离判据 |
| `vm.py` | VM 原语：域状态 / 回滚 / QGA 通道 / 清单与差分 / 环境检查 |
| `net.py` | 网络策略层：三档模式施加 + 采集窗口 + `network` 指纹 |
| `netsniff.py` | `AF_PACKET` 头部嗅探器（**唯一提权进程**，只读，需 `CAP_NET_RAW`） |
| `bat2sh-rec.network.xml` | `recording` 模式的承载网络（`forward mode='none'`，幂等 `net-define`） |
| `collect_linux.py` | **L 侧采集**：产物在 bwrap 沙箱执行，输出**与 W 同结构**的指纹（oracle 用） |
| `compare.py` | **W vs L 对比器**：归一化规则阶梯 + 三分类（一致 / 可归因 / 不可归因） |
| `classify_corpus.py` | 语料可对比性分类（A 纯文件操作 / B 部分 / C 不可对比），oracle 选样用 |

## 运行时 oracle（路 A：真机 W vs 产物 L）

与 `../../tools/oracle/golden_harness.py`（**wine** 作 W 侧）互补：本设施用**真机 Windows VM**
作 W 侧，权威顺序上高于 wine。设计见 `../oracle-design.md`，实测见 `../oracle-result.md`。

```bash
cd research/behavior-tracking

# W（真机，约 40–80 s/样本）
python3 tools/collect.py --sample tools/samples/copy.bat --guest-name v4.bat \
        --output results/oracle/W/v4.json --scope 'C:\poc\samples' --network isolated

# L（bwrap，< 2 s/样本）——产物**沿用 W 侧 guest 文件名（含 .bat）**，内容是 bash
python3 tools/collect_linux.py --script tools/samples/copy.bat --guest-name v4.bat \
        --output results/oracle/L/v4.json

# 对比
python3 tools/compare.py --w results/oracle/W/v4.json --l results/oracle/L/v4.json \
        --source tools/samples/copy.bat --report results/oracle/report/v4.json
```

**三条必读**：

1. **产物必须沿用 W 侧文件名**（含 `.bat`）。实测 `%~nx0` → `$(basename "$0")`、
   `for %%i in (*.bat)` → `for i in *.bat` ⇒ 脚本能观测自己的名字与目录内容。
2. **工作根目录名必须一致**（`--run-name`，默认 `samples` = `C:\poc\samples` 的 basename）。
   `for /r %%i in (.)` 会**为每个目录建同名文件，含工作根自己**。
3. **归一化规则不是可有可无的**：`compare.py` 先只加表示层规则（N1/N5/N6/N7），
   不够再加，**每加一条都写进 `normalization_applied` 并注明它掩盖了什么** ——
   这是对抗"假一致"的唯一办法，不要绕过。

`--neutralize-errexit` 是**诊断**开关（规则 N13）：中和 `set -euo pipefail` 后重跑，
用于把"级联后果（D5）"与"根因"用证据分开。重跑结果**不替换**正式 L 指纹。

## 快速开始

```bash
cd research/behavior-tracking

# 采集一个样本（默认 --network=isolated：完全断网）
python3 tools/collect.py --sample samples/copy.bat --output results/copy.json

# 批量采集（清单见 ../batch-samples.txt）
python3 tools/batch.py --samples batch-samples.txt --output results/batch

# 验证样本间隔离（至少两份指纹）
python3 tools/verify.py results/batch/s03.json results/batch/s04.json
```

`--sample` 的相对路径依次在 **cwd → `tools/` → `tools/samples/` → `../samples/`** 中查找，
所以下面两条都成立：

```bash
cd research/behavior-tracking/tools && python3 collect.py --sample samples/copy.bat ...
cd research/behavior-tracking       && python3 tools/collect.py --sample samples/copy.bat ...
```

## 网络姿态（`--network=`）

| 模式 | 语义 | 外部性 | 何时用 |
| :--- | :--- | :--- | :--- |
| `isolated`（**默认**） | vNIC 链路 down（持久 XML） | **零** | 批量、样本普查 |
| `recording` | 接 `bat2sh-rec`（无 NAT / 无转发 / 无 DNS 上联），宿主侧按**头部**记录 | **结构性零** | 需要连接级 dst/proto/result 时 |
| `nat` | 接 `default`（NAT），全量出网 | ⚠️ **真实存在，不可撤回** | 仅在明确需要真实网络时 |

指纹的 `network` 段含 `mode` / `isolated` / `attempted` / `connections[]` / `bytes_sent` /
`bytes_recv` / `egress_frames` / `capture`。

> **不记录 payload**：每帧最多读 192 B，解析器里没有读 payload 的代码路径
> （`capture.payload_read=false` 是**构造性质**，不是承诺）。
> `isolated` 下 `attempted=null`（宿主观测不到意图，如实返回未知而非 `false`）。

## 两个必须知道的参数

| 参数 | 为什么需要 |
| :--- | :--- |
| `--workdir`（默认 `C:\poc\samples`） | `guest-exec` 继承 qemu-ga 的 cwd = **`C:\Windows\System32`**。语料几乎全用**相对路径**，不设 workdir 时它们的写入**落在清单范围之外**、完全不可见 |
| `--guest-name` | QGA 的 `guest-exec` 会给参数里的 `"` 加**反斜杠转义**，`cmd.exe` 不认 `\"` ⇒ **含空格/中文的路径根本跑不了**。用它将语料名换成安全 ASCII 名，原名仍记入指纹 |

> 含空格的路径会被**硬拒绝**（而不是静默跑出 `rc=1`，看起来像"样本执行失败"）。

## 指纹 schema

`SCHEMA_VERSION = 4`。⚠️ **v2 → v3 是破坏性变更**：`network` 由**列表**（v2 恒为 `[]` 占位符）
改为**对象**。旧 `[]` **不代表"没有网络行为"**，两种 schema 混用会被误读。

> **v3 → v4**（本文档此前误写为 3，v2.10.0 oracle session 更正）：新增两个**顶层**字段
> `fixed_time`（固定时钟的执行证据：`target_utc` / `after_offset_s` / `ok` …）与
> `execution_workdir`。二者均为**增量**，不改动既有字段语义。
> `collect_linux.py` 亦输出 `schema_version: 4`，但其 `fixed_time` **不存在**
> （L 侧无法固定时钟，改用 `environment.clock_fixed: false` 显式声明）。

## 前置条件（缺一不可）

| # | 条件 | 检查方式 |
| :-- | :--- | :--- |
| 1 | 域 `win-behavior` 存在 | `virsh -c qemu:///system list --all` |
| 2 | 用户可用 `virsh`（在 `libvirt` 组） | 非 root 即可，**但 URI 必须显式 `qemu:///system`** |
| 3 | 免密 `sudo`（镜像文件为 root 所有） | `sudo -n true` |
| 4 | `ufw` 放行 `virbr0` | `collect.py` 的 `check_env` 会硬报错 |
| 5 | 基线 + 覆盖层已建立 | `--establish-baseline`（一次性） |

> ⚠️ **URI 坑**：`virsh` 默认 URI 是 `qemu:///session`，看不到 `system` 上的域。
> 本工具默认 `--connect qemu:///system`，无需每次手写。

## 一次性：建立基线

基线 = **干净 Windows + virtio 驱动 + qemu-ga + `C:\poc` 环境物**，
且**不含任何样本或其副作用**。建立前请先让 guest 优雅关机（保证 NTFS 干净）。

```bash
virsh -c qemu:///system shutdown win-behavior     # 优雅关机（建基线时必要）
python3 collect.py --establish-baseline
```

它做三件事：把 `win-behavior.qcow2` 改名为 `win-behavior.base.qcow2` →
`qemu-img create -b base` 生成同名覆盖层 → 启动并等 agent 就绪。
**域 XML 不动**（覆盖层与原盘同名）。

## 文件

| 文件 | 职责 |
| :--- | :--- |
| `collect.py` | CLI 入口：回滚 → 等 agent → 传输 → 执行 → 采集 → 报告 |
| `vm.py` | VM 原语：域状态/启停/**回滚**/QGA 通信/文件传输/清单与差分/`check_env` |
| `verify.py` | 隔离验证：J1（起点同一性）/ J2（无跨样本污染）/ J3（样本有效性）+ 重复性 |
| `samples/copy.bat` | 样本 A：`create → copy → read`，含 `C:\poc` **之外**的探针 |
| `samples/other.bat` | 样本 B：隔离探针，产物与 A 完全不同 |
| `results/` | 指纹输出。**入仓**（24 KB）：隔离结论的原始证据，便于他人直接复跑 `verify.py` 复核 |

## 指纹结构（schema v2）

```jsonc
{
  "schema_version": 2,
  "harness": { "git_head": "...", "invocation": [...] },
  "script":  { "name", "sha256", "size", "guest_path" },
  "environment": { "guest_os", "console_codepage", "guest_agent_version", ... },
  "rollback": {
    "method": "overlay-qcow2",
    "revert_op_ms": 77,          // ← 纯回滚操作（硬判据 < 30s）
    "stop_ms", "agent_ready_ms", "cycle_ms",
    "base_intact": { "unchanged": true, "before": {...}, "after": {...} }
  },
  "execution": { "argv", "exit_code", "signal", "duration_ms", "timeout",
                 "out_truncated", "err_truncated" },
  "stdout": { "b64", "text" },   // 原文 + 解码文本（CP936）
  "stderr": { "b64", "text" },
  "filesystem": {
    "scope": ["C:\\poc", "C:\\iso-probe"],
    "baseline_manifest_hash": "sha256:...",   // ← J1
    "baseline_manifest": { ... },             // 全量存档，使 J1 差异可复核
    "created": [...],                         // 行为产物（已剔除采集器自身写入）
    "modified": [...], "deleted": [...],
    "known_artifacts": [ { "path", "reason": "harness upload" } ],
    "after_manifest": { ... },                // ← J2：绝对状态
    "blind_spots": ["reads","transient-effects","metadata-only-writes"]
  },
  "timings": { "revert": 165, "agent_wait": 16522, ... }
}
```

## 为什么隔离要用 J1/J2/J3 而不是"看差分"

**清单差分是自归一化的，无法证明隔离。** 若回滚失败、A 的 `a.txt` 残留：

| | before | after | `created` |
| :--- | :--- | :--- | :--- |
| 回滚成功 | 无 `a.txt` | 无 `a.txt` | `[]` |
| 回滚**失败** | **有** `a.txt` | **有** `a.txt` | `[]` ← **一样** |

残留文件在两次运行里哈希相同 → 落进 `unchanged` → **差分里看不见**。
所以必须用：

- **J1** 所有运行的 `baseline_manifest_hash` 完全相同 ← 最强：起点相同，结果之差只能来自样本
- **J2** Y 的 `after_manifest`（绝对状态）不含"X 创建且 Y 未创建"的路径
- **J3** 每次运行 `created` 非空 ← 防空转：样本没生效时，J2 会**平凡成立**

## 常见故障

| 症状 | 根因 | 处置 |
| :--- | :--- | :--- |
| `check_env` 报 ufw 未放行 | 宿主防火墙丢 DHCP/NAT | `sudo ufw allow in on virbr0` + `sudo ufw route allow in on virbr0` |
| `guest-ping` 超时 | 缺 `vioser.sys`（**不是 agent 没装**） | guest 内装 `virtio-win-gt-x64.msi` |
| 域查不到 | URI 是 `session` | 显式 `--connect qemu:///system` |
| `qemu-img info` 报 write lock | 域正在运行 | 加 `-U`（工具已内置） |
| 首次清单异常慢 | 清单范围含**不存在**的路径（PowerShell 病理，~30-40s） | 已修：`manifest()` 先 `Test-Path` 过滤 |
| 回滚报"基线不存在" | 未建基线 | `python3 collect.py --establish-baseline` |

## 已知边界（**不是 bug，是设计边界**）

- **网络外部性不隔离**：样本对外发包改变了对端状态 → 覆盖层回滚不了。批量采集前须定网络策略
- **宿主机侧效应不隔离**：本工具是**行为观察**设施，**不是安全沙箱**
- **读操作 / 瞬时副作用不可见**：见 `blind_spots`（`../poc-result.md` §4.3 已实证）
- **注册表 / 进程 / 网络未采集**：属 L2，见 `../collection-design.md` §7
