# 行为采集工具（L3 输出效果层）

> 研究基础设施，**不是 bat2sh 产品代码**。
> 设计依据：`../rollback-design.md` · 实测结果：`../rollback-result.md`

## 这是什么

把 PoC 从「能采一次」变成「能反复采」：

- **覆盖层回滚** —— 每个样本前把 VM 恢复到逐字节相同的干净状态
- **样本间隔离** —— 用三重判据（J1/J2/J3）证明，而非仅凭差分
- **一条命令跑完** —— 回滚 → 等 agent → 传输 → 执行 → 采集 → 报告

## 快速开始

```bash
cd research/behavior-tracking/tools

# 采集一个样本
python3 collect.py --sample samples/copy.bat --output results/copy.json

# 验证样本间隔离（至少两份指纹）
python3 verify.py results/copy.json results/other.json results/copy-rerun.json
```

`--sample` 的相对路径依次在 **cwd → `tools/` → `tools/samples/` → `../samples/`** 中查找，
所以下面两条都成立：

```bash
cd research/behavior-tracking/tools && python3 collect.py --sample samples/copy.bat ...
cd research/behavior-tracking       && python3 tools/collect.py --sample samples/copy.bat ...
```

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
