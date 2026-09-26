# oracle 样本选取（第一批）

> 时间：2026-09-26 · 轨道：`research/behavior-tracking`（**研究设施，未改 bat2sh 产品代码**）
> 起点 HEAD：`0ec2ad3`（v2.10.0 tag 之后 5 个 commit 的 main tip；工作区干净）
> 依据：`oracle-design.md` §9（样本分类）/ §10（第一批建议）；用户已确认 V1–V5 全选
> 前置：`oracle-design.md` 硬闸门已通过（归一化规则、D-list、分类、样本范围四项均确认）

---

## 1. 选取标准

沿用 `poc-samples.md` §1（C1–C5）与 `batch-samples.md` §1（C1–C7），**新增两条 oracle 特有标准**：

| # | 标准 | 理由 |
| :-- | :--- | :--- |
| O1 | **属 A 类（纯文件操作）** | 只有 A 类的 W/L 差异**只能**解释为转换错误 —— B/C 类的差异无法归因（`oracle-design.md` §9） |
| O2 | **两侧初始状态可严格对称** | W 的 `C:\poc\samples` 与 L 的工作根必须逐项一致；否则会产出**采集设施引入的假差异** |
| C1–C7 | 无交互 / 行为明确 / 非破坏 / 许可干净 / 有界时间 / 名无空格 / basename 唯一 | 沿用既有标准 |

**额外偏好**：优先选**已有 W 指纹**或**许可干净可入仓**的样本，把本轮时间花在 L 设施与对比器上。

---

## 2. 选定样本（5 个）

| # | guest 名 | 原文件 | 来源 | 覆盖 | 许可 | `sha256`(前16) |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- |
| **V1** | `v1.bat` | `快速创建文件夹.bat` | 非常批处理 | **创建目录**（只 `md` ⇒ 仅 `created_dirs` 可见） | 无许可（只引用） | `C0B4C9AC78357D87` |
| **V2** | `v2.bat` | `生成指定内容的文本文件.bat` | 非常批处理 | **文本文件 + 中文内容**（N11 的首个真实用例） | 无许可（只引用） | `CEA637ECFA394C57` |
| **V3** | `v3.bat` | `samples/poc-02-fileops.bat` | **本仓库** | **写/读/复制/删除**全覆盖 | AGPL-3.0 | `D464915B97A173C0` |
| **V4** | `v4.bat` | `tools/samples/copy.bat` | **本仓库** | 创建+复制+读，含工作根**之外**的探针 | AGPL-3.0 | `7CF5462660E26772` |
| **V5** | `v5.cmd` | `以文件夹名为名建立文本文件.cmd` | 非常批处理 | **递归遍历 + 每目录建同名文件** | 无许可（只引用） | `A9485B7B8210F71A` |

### 2.1 覆盖矩阵

| 维度 | 覆盖 |
| :--- | :--- |
| 创建文件 | V2 V3 V4 V5 |
| 创建目录 | V1 V3 V4 |
| **复制** | V3 V4 |
| **删除** | V3 |
| 读取/输出（stdout） | V3 V4 |
| **中文内容落盘** | V2 |
| **递归目录遍历** | V5 |
| 工作根**之外**写入 | V4 |
| 编码 | GBK 4 个 / UTF-8 1 个 |
| 行尾 | CRLF 5 个 |

> **阴性对照**：V1（只建目录、stdout 恒空）与 V3/V4（有 stdout）构成一组。
> 若对比器只对 V1 报"不可归因"而对 V3/V4 报"一致"，说明规则对**空输出**处理有偏。

### 2.2 A 类第 4 个样本为何不进第一批

`卸载瑞星杀毒软件2008批处理版.bat`（A 类，`todo=0`）只 `del` 三个**并不存在**的
`模块\*.dll`，实际行为是 **no-op + 一行 stdout** —— 名为"卸载杀毒软件"，却
**测不到删除**。删除覆盖由 V3 承担（`del "%WORK%\b.txt"`，文件确实存在）。
该样本保留在 A 类清单中，供后续需要"**失败但静默**"的阴性用例时使用。

### 2.3 两侧初始状态对称性（O2 的落地）

| 维度 | W | L | 对齐方式 |
| :--- | :--- | :--- | :--- |
| 工作根 | `C:\poc\samples` | `<沙箱>/samples` | `collect_linux.py --run-name samples`（**目录名也必须一致** —— 见 §2.4） |
| 初始内容 | 仅上传的样本 | 仅转换产物 | 两者都登记进 `filesystem.known_artifacts`，并在内容比较中排除 |
| 产物文件名 | `v1.bat` … `v5.cmd` | **同名**（内容是 bash） | `collect_linux.py --guest-name`；理由见 `oracle-design.md` §3.2.1 |
| stdin | `< nul` | `< /dev/null` | 固定 |
| 网络 | `--network isolated` | `bwrap --unshare-all` | 结构性零出网 |
| 时间 | 固定 `2026-06-01 12:00:00` | 宿主实时（`clock_fixed=false`） | 本批 5 个样本**都不读时间** ⇒ 不影响 |

### 2.4 为什么工作根**目录名**也要一致

V5 用 `for /r %%i in (.)` **为每个目录**（含工作根自己）建一个同名 `.txt`。
W 的工作根叫 `samples` ⇒ 产出 `samples.txt`；若 L 的工作根叫 `run`，就会产出 `run.txt`
—— 那将是**采集设施引入的假差异**，会把一个真实的转换缺陷淹没在噪声里。
故 `collect_linux.py` 的 `--run-name` 默认 `samples`。

---

## 3. 采集与对比方法

每个样本三步：

```bash
cd research/behavior-tracking

# 1. W = 真机 cmd.exe
python3 tools/collect.py --sample <SRC> --output results/oracle/W/<v>.json \
        --guest-name <v.bat> --scope 'C:\poc\samples' --network isolated

# 2. L = 产物在 bwrap 沙箱
python3 tools/collect_linux.py --script <SRC> --guest-name <v.bat> \
        --output results/oracle/L/<v>.json

# 3. 归一化 → 三分类
python3 tools/compare.py --w results/oracle/W/<v>.json --l results/oracle/L/<v>.json \
        --source <SRC> --report results/oracle/report/<v>.json
```

**W 侧 scope 用 `C:\poc\samples`（非默认的 `C:\poc`）**，使 W 的清单范围与 L 的工作根**严格 1:1**，
排除 `C:\poc\*.msi` 等采集器自身文件造成的噪声。

### 3.1 N13 诊断重跑（仅对"不可归因"样本）

`set -euo pipefail` 会让 L 在首条失败命令处**提前中止**，而 cmd 会继续执行（已知差异 D5）。
为了把 D5 与真缺陷分开，对不可归因样本额外跑一次：

```bash
python3 tools/collect_linux.py --script <SRC> --guest-name <v.bat> \
        --neutralize-errexit --output results/oracle/L/<v>-noerrexit.json
python3 tools/compare.py --w results/oracle/W/<v>.json --l results/oracle/L/<v>-noerrexit.json --source <SRC>
```

⚠️ 重跑结果**不替换**正式 L 指纹，只作**归因证据**（`oracle-design.md` §5 N13）。

---

## 4. 产出清单

| 文件 | 内容 |
| :--- | :--- |
| `results/oracle/W/v1..v5.json` | W 侧指纹（真机） |
| `results/oracle/W/poc-other.json` | W 侧指纹（`other.bat`，Phase 2 结构验证用） |
| `results/oracle/L/v1..v5.json` | L 侧指纹（bwrap） |
| `results/oracle/L/v3-noerrexit.json`、`v4-noerrexit.json` | N13 诊断重跑 |
| `results/oracle/L/poc-other.json` | L 侧指纹（Phase 2 结构验证用） |
| `results/oracle/report/v1..v5.json` | 对比报告（含归一化留痕） |
| `oracle-result.md` | 对比结论 |
| `oracle-verdict.md` | 判定 |
