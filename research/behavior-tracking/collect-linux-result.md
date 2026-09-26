# Linux 侧采集设施（`tools/collect_linux.py`）验证结果

> 时间：2026-09-26 · 轨道：`research/behavior-tracking`（**研究设施，未改 bat2sh 产品代码**）
> 起点 HEAD：`0ec2ad3` · 设计依据：`oracle-design.md` §7
> 验证样本：**Windows 侧 PoC 的 2 个**（`tools/samples/copy.bat`、`tools/samples/other.bat`）
> 结论：✅ **结构一致（对比契约 22/22 字段对齐）；设施可用；且立刻抓到真实差异**

---

## 1. 目标与判据

任务书 §3.3 要求：用 Windows 侧的**同一批样本**，采集 W 与 L，验证**结构一致**。

| # | 判据 | 结果 |
| :-- | :--- | :--- |
| 1 | `collect_linux.py` 可独立运行 | ✅ 一条命令完成：转换 → 沙箱 → 执行 → 采集 → 指纹 |
| 2 | 输出与 W **同结构** | ✅ **对比契约 22/22 字段同名同型**（§3） |
| 3 | 路径归一化在输出时完成 | ✅ 清单键为**工作根相对路径**；`<WORK>` 映射由 `compare.py` 施加 |
| 4 | 采集渠道覆盖 W 的同一组 | ✅ rc / stdout / stderr / 文件+目录差分 / 文件内容哈希 |
| 5 | 能区分"样本没行为"与"采集器没看见" | ✅ `blind_spots` 显式声明，且与 W 同组 + 2 项 Linux 特有 |

---

## 2. 运行结果（PoC 2 样本）

```bash
python3 tools/collect_linux.py --script tools/samples/copy.bat  --guest-name copy.bat  --output results/oracle/L/copy.json
python3 tools/collect_linux.py --script tools/samples/other.bat --guest-name other.bat --output results/oracle/L/poc-other.json
```

| 项 | `copy.bat` | `other.bat` |
| :--- | :--- | :--- |
| guest 名（沿用原名） | `copy.bat` | `other.bat` |
| exit_code | **1** | **1** |
| stdout | `''` | `''` |
| stderr | `cat: '…/samples/work\c.txt': No such file or directory` | `cat: '…/samples/work\b-marker.txt': No such file or directory` |
| created | `C:/iso-probe/from-a.txt`, `work/a.txt`, `work/c.txt` | `C:/iso-probe/from-b.txt`, `payload/b-data.txt`, `work/b-marker.txt` |
| created_dirs | `C:`, `C:/iso-probe`, `work` | `C:`, `C:/iso-probe`, `payload`, `work` |
| 网络 | `bwrap-unshare-all`，无出网路径 | 同 |

> **两个样本都立刻报出差异** —— 这正是设施可用的第一批证据（详见 `oracle-result.md`）。

---

## 3. 结构一致性（核心判据）

### 3.1 对比契约逐字段核对（5 对指纹 × 22 字段）

"对比契约" = `compare.py` **实际读取**的字段（不是"两个 JSON 长得像不像"）。
核对方法：对每一对 W/L，检查该字段**两侧都存在且类型相同**。

| 字段 | v1 | v2 | v3 | v4 | v5 |
| :--- | :-: | :-: | :-: | :-: | :-: |
| `schema_version` | OK | OK | OK | OK | OK |
| `harness.git_head` | OK | OK | OK | OK | OK |
| `script.name` / `sha256` / `size` / `guest_name` | OK | OK | OK | OK | OK |
| `execution.exit_code` / `argv` / `timeout` | OK | OK | OK | OK | OK |
| `stdout.text` / `stderr.text` | OK | OK | OK | OK | OK |
| `filesystem.scope` | OK | OK | OK | OK | OK |
| `filesystem.created` / `modified` / `deleted` | OK | OK | OK | OK | OK |
| `filesystem.created_dirs` / `deleted_dirs` | OK | OK | OK | OK | OK |
| `filesystem.known_artifacts` | OK | OK | OK | OK | OK |
| `filesystem.after_manifest` / `baseline_manifest` | OK | OK | OK | OK | OK |
| `filesystem.blind_spots` | OK | OK | OK | OK | OK |
| `execution_workdir` | OK | OK | OK | OK | OK |

**结论：22 × 5 = 110 项全部对齐，零缺口。**

### 3.2 有意**不同**的字段（不是缺陷，是两侧物理差异的如实记录）

| 字段组 | W 独有 | L 独有 | 为什么不同 |
| :--- | :--- | :--- | :--- |
| 虚拟化层 | `fixed_time.*`、`rollback.base*`、`rollback.agent_ready_ms`、`rollback.overlay`、`network.capture.*` | `rollback.run_dir`、`timings.convert`、`environment.clock_fixed` | W 跑在 qcow2 覆盖层 + QGA 上；L 跑在 bwrap + tmpdir 上 |
| 环境描述 | `guest_version`、`guest_agent_version`、`guest_agent_commands` | `environment.locale`、`environment.timezone` | 平台事实不同 |
| 清单键形态 | `C:\poc\samples\work\a.txt`（绝对） | `work/a.txt`（工作根相对） | 由 `compare.py` 的 N5/N6 归一 |
| **内容哈希** | 1 个（`Hash`） | **3 个**（`Hash` + `hash_lf_to_crlf` + `hash_cp936_crlf`） | L 侧为 N10/N11 额外计算；W 侧无需改动（**这是"不改 W 工具就能做内容对比"的关键设计**） |

---

## 4. 实现中发现并修掉的两个设施缺陷

**仪器先验证**：以下两条如果留到 Phase 3 才发现，会把**假差异**写进结论。

| # | 缺陷 | 后果 | 修复 |
| :-- | :--- | :--- | :--- |
| 1 | bwrap 未补 `/bin`、`/lib` 符号链接 | Arch 上 `/bin` 是符号链接 ⇒ `bwrap: execvp /bin/echo: No such file or directory` | 显式 `--symlink usr/bin /bin`（+ `sbin`/`lib`/`lib64`） |
| 2 | 工作根目录名默认 `run` | V5 用 `for /r` **为每个目录建同名文件**（含工作根）⇒ W 出 `samples.txt`、L 出 `run.txt`，**设施制造的假差异** | `--run-name`，默认 `samples`（= W 侧 `C:\poc\samples` 的 basename） |

另修一处**对比器**缺陷（Phase 3 前）：

| # | 缺陷 | 后果 | 修复 |
| :-- | :--- | :--- | :--- |
| 3 | L 的 stderr 含**每次运行都不同**的沙箱绝对路径 | 任何含路径的错误信息都会**恒定假报不一致** | N5 也作用于**文本**通道（把 `rollback.run_dir` 替换为 `<WORK>`） |

---

## 5. 能力边界（写进指纹，防止误读）

L 指纹的 `filesystem.blind_spots` 与 W **同组**，外加 Linux 特有项：

```
reads, transient-effects, metadata-only-writes,
registry-not-collected, process-not-collected, network-not-collected
```

| 看不见 | 原因 |
| :--- | :--- |
| 读操作 | 净差分 |
| 瞬时副作用（建后即删） | 净差分 |
| 仅元数据写入 | 清单只收 size + hash |
| 注册表 / 进程 / 网络 | 不在 L3 范围 |

> ⚠️ **两侧盲区相同** ⇒ 共同盲区里的缺陷对 oracle **完全隐形**。
> 这是本设施的**根本限制**（`oracle-design.md` §12）：它把"静默错误"缩小到
> "**可观测通道上的**静默错误"，而不是消除它。

---

## 6. 结论

| 问题 | 答案 |
| :--- | :--- |
| `collect_linux.py` 可用？ | ✅ 一条命令跑完，5 个样本全部成功产出指纹 |
| 与 W **同结构**？ | ✅ **对比契约 110/110 项对齐**（22 字段 × 5 对） |
| 路径归一化在输出时完成？ | ✅ 清单键为工作根相对路径；映射由对比器统一施加 |
| 能否独立运行？ | ✅ 仅依赖 `bwrap` 与 `bat2sh`，两者缺失时**硬失败**（exit 1），不静默降级 |
| 验证中抓到东西了吗？ | ✅ **2/2 样本立即报出真实差异**，并暴露了 3 个设施/对比器缺陷（已在 Phase 3 前修复） |
