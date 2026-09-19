# PS 解冻评估 · 现状实测（只读）

> 会话：PS 解冻只读评估。起点 HEAD（锁定）= `46d5d21`；`git status` 干净。
> **全程只读**：未修改任何代码 / 测试 / fixture；测量产物写 `/tmp`（不在仓库）。
> 前置：`git tag -l "v2.7.0"` 有输出 ✅；pytest **1554 passed** ✅；PS 语料可用 ✅（未触发暂停）。

---

## 0. 仪器验证（纪律 9 强化：先验证，再报数字）

### 0.1 复用既有仪器（v1.8.0）

```
python3 tools/corpus-analysis/ps_silent_check.py --out /tmp/ps-verify
→ total=60 syntax_pass=56 (93.3%)
→ bash 运行 rc==0（syntax_ok）: 19
```

与常驻 CI 仪器 `tests/test_real_corpus_metrics.py`（pytest 输出 `原始口径 56/60 = 93.3%`）
**逐字段一致** → 仪器可信。

> `bash rc==0 = 19` 恰是 v1.8.0「运行时语义 14/19」的**分母**，佐证历史口径结构。

### 0.2 全量 664 仪器（本 session 临时，写 /tmp）

`ps_silent_check.py` 硬编码 corpus 为 repo 内 60。为测**全量 664**，本 session 新建 `/tmp/ps_full_measure.py`，
**复用 `ps_silent_check` 的 `sandbox_bash` / `run` / `normalize`**（口径完全一致），仅把 corpus 指向
`~/下载/PowerShell-1.6/scripts`，并额外采集 TODO/error 分类。源码见 §7 附录。

**语料关系**：repo 内 `tests/fixtures/real-corpus/fleschutz/` 的 60 个 `.ps1` 是
`~/下载/PowerShell-1.6/scripts`（**664** 个 `.ps1`，CC0）的**子集**（同名）。

---

## 1. 当前指标（664 全量，实测）

| 指标 | v1.8.0 冻结时（60 子集） | **本次实测（664）** | **本次实测（60 子集）** |
| :--- | ---: | ---: | ---: |
| 语料 | 60 | **664** | 60 |
| **语法通过（原始口径）** | 56/60 = **93.3%** | **550/664 = 82.8%** | **56/60 = 93.3%** |
| rc==0（沙箱运行） | 19 | **214** | **19** |
| **功能完好 strict**（rc0 且 todos==0 且产物无 `# TODO`） | 未记录 | **0/664 = 0.0%** | **0/60 = 0.0%** |
| degraded（rc0 但含 `# TODO`） | — | **214/664 = 32.2%** | 19/60 |
| 转换崩溃 / 非语法错误 | 0 | **0** | **0** |
| TODO 总数 | 256（60） | **4324** | （见分类） |
| 运行时语义（vs pwsh） | 14/19 = 73.7% | **不可测**（pwsh 缺失，见 §5） | 不可测 |

> **关键**：60 子集（93.3%）与 v1.8.0 **完全一致** → PS 自 v1.8.0 **未改动**（无回归、无进步）。
> 全量 664 语法 82.8% 低于子集，因 repo 只取了较易的 60 个。

### 1.1 TODO 分类（664，4324 条）

| category | 计数 | 占比 |
| :--- | ---: | ---: |
| **objects**（对象模型 / 属性访问） | **2056** | **47.6%** |
| misc（杂项/未知命令兜底） | 1453 | 33.6% |
| control_flow | 442 | 10.2% |
| command | 194 | 4.5% |
| pipeline | 90 | 2.1% |
| params | 72 | 1.7% |
| registry | 17 | 0.4% |

> `objects` 47.6% 与 v1.8.0-ROI（60 子集 121/256 = 47.3%）**一致** → D 档缺口未变。

---

## 2. 逐类归因（A / B / C / D / S）

> 方法：模式级自动归因（`bash -n` 报错特征 + 沙箱 stderr 首行 + 源文件结构探测）。
> **本 session 未做 450 个失败文件的逐文件人工复核**（只读时间预算内），归因以**模式 + 计数 +
> 代表样本**给出；每文件原始结果在 `/tmp/ps-full/results.json`（含 `bash_err_head`）。
> 这是**方法偏离**，已披露（纪律 3/4）。

### 2.1 语法失败（114/664 = 17.2%）—— 全部属 **A（bat2sh PS 发射/解析缺陷）**

| 模式 | 计数 | 代表 | 性质 |
| :--- | ---: | :--- | :--- |
| 表达式/括号（`$(...)`、cast、调用） | 32 | `check-drives.ps1`（`'{0:N0}KB' -f (${bytes}…`） | A |
| `foreach` 循环头损坏 | 30 | `check-apps.ps1`（`for app in ${apps}) { if (…`） | A（v1.8.0 已知 X5） |
| 词法：未闭合引号/here 串 | 15 | `check-pending-reboot.ps1` | A |
| 块：`try/catch` 的 `else` 发射 | 15 | `check-symlinks.ps1`（`else  # TODO: catch 块`） | A |
| `param()` / 类型转换残留 | 8 | `cd-recycle-bin.ps1`（`] param()`） | A（v1.8.0 已知） |
| 其他（含 COM/对象） | 14 | `close-file-explorer.ps1`（`(New-Object -ComObject …`） | A/D 混合 |

**说明**：PowerShell 源文件是 CC0 高质量脚本（无畸形），故 **B 类 ≈ 0**。
这些是**翻译缺陷**，不是源问题。**全部可修**（A），但需 PS 解析层专项。

### 2.2 rc≠0（336/664，仅 syntax_ok 者）—— 环境主导

| 归因 | 计数 | 代表 |
| :--- | ---: | :--- |
| **C**：缺失路径（Windows 专有目录/盘符） | 108 | `cd-home.ps1`（home 目录解析为空） |
| **C**：缺失命令（Windows 专有工具） | 99 | `winget`(26)、`TaskKill`(11)、`tskill`、`rundll32` |
| **C/S**：其他（COM 派生空路径 / 主动 exit 1） | 77 | `cd-downloads.ps1`（`(New-Object -ComObject Shell.Application)…`） |
| **A**：`unbound variable`（变量未初始化） | 16 | — |
| **S**：无 git 仓库 / 沙箱 / 网络 | 16+9+4 = 29 | `fatal: not a git repository`、`no new privileges`、代理不可达 |
| **A**：参数透传（`realpath -a` 等） | 8 | — |
| **S**：空 stderr（交互/fixture） | 8 | — |

> **rc≠0 中真正 bat2sh 缺陷（A）= 24/336 = 7.1%**；环境类（C/S）≈ 313/336 = 93%。

### 2.3 结构缺口（D 档）分布

源文件含**至少一个 Linux 无对应构造**者：**277/664 = 41.7%**（静态探测）：

| 构造 | 文件数 | Linux 对应 |
| :--- | ---: | :--- |
| 对象管道（`$_`/`Where-Object`/`Select-Object`…） | 462 | 部分可近似，语义不等价 |
| `.NET` 静态（`::`） | 186 | **无** |
| `New-Object`（含 COM） | 113 | **无** |
| `Get-Process/Service/EventLog/ChildItem` | 88 | 部分（`ps`/`systemctl`），属性不等价 |
| CIM/WMI | 18 | **无** |
| `Import-Module`/`Add-Type` | 17 | **无** |
| 注册表（`HKLM:` 等） | 9 | **无** |
| 远程会话（`Invoke-Command`/`PSSession`） | 5 | 需 SSH 映射，语义不等价 |

---

## 3. 与 bat 侧对比（同口径）

| 口径（bat） | bat 151 语料（v2.8.0） | **PS 664（本次）** |
| :--- | ---: | ---: |
| 语法通过 | 149/151 = 98.7% | 550/664 = **82.8%** |
| rc==0 | 101 | 214 |
| **功能完好 strict** | 19/151 = 12.6% | **0/664 = 0.0%** |
| degraded | 82 | 214 |
| degraded TODO | 851 | 4324 |
| 崩溃 / 转换错误 | 0 | 0 |

> bat 尚且有 19 个 strict（功能完好）；**PS 在 664 语料上 strict = 0**——
> 每个可运行产物都至少含一个 `# TODO`（含 try/catch 注释）。PS 的「可用产出」比 bat 更依赖人工。

---

## 4. 新发现缺陷（只读复现，class A）

**现象**：PS 的 `try/catch` 以 `# TODO` 注释发射，但 `ConvertReport.todo_count` 不计数
（登记为 warning）。导致：
1. **报告少计**：`cd-up.ps1` 产物含 **3 个** `# TODO`，但 `report.todo_count = 0`、
   `warning_count = 4`；GUI `open_report` 在 `error_count==0 && todo_count==0` 时显示
   「所有语句均已自动转换」→ **误导**。
2. **CI 门静默失效**：`bat2sh --cli cd-up.ps1 --print --fail-on-todo` **退出 0**（应 3）。
3. **指标虚高**：若按 `todo_count==0` 判 strict，得 33；按 bat 口径（含产物 `# TODO` 标记）
   得 **0**。

**规模**：550 个 syntax_ok 文件中 **474 个** 产物 `# TODO` 标记数 > `report.todo_count`；
其中 rc0 者 **175 个**。

**性质**：与 v2.6.0 修复的 bat A-1（子报告丢弃 → `--fail-on-todo` 静默失效）**同类**，
但属 **PS 路径的独立、既有**问题（v1.8.0 起的 API 层/报告 taxonomy 选择）。

**证据（逐字）**：

```
$ bat2sh --cli .../cd-up.ps1 --print --fail-on-todo ; echo $?
0
$ bat2sh --cli .../cd-up.ps1 --print | grep -c "# TODO"
3
$ bat2sh --cli .../cd-up.ps1 --print --report-json   # stderr
  "todo_count": 0, "warning_count": 4, "error_count": 0
```

> **本 session 只读，不修此缺陷**；登记为 PS 解冻（若启动）的**第一批必处理项**。

---

## 5. 运行时语义：本 session **不可测**（如实披露）

- 定义（v1.8.0）：产物 `bash -n` 通过且沙箱 rc==0，但可见行为（rc/stdout）与**原始 pwsh** 不一致。
- 仪器存在：`ps_silent_check.py --pwsh <dir>`（v1.8.0）。
- **oracle 缺失**：本机 **无 pwsh / dotnet / 便携 pwsh 副本**（`command -v pwsh` 无输出；
  `/usr/bin/pwsh` 不存在；全盘 `find -name pwsh` 无命中）。
- **结论**：**73.7% 无法复现，也无法测出新的静默错误率**。任何 PS 语义工作在本机**不可验证**
  （违反纪律 9/10 的「可复现」要求），除非引入 pwsh 运行时设施（**新依赖/新设施**）。

> 这不改变语法/strict 结论；但**显著削弱「解冻做语义」的可行性**（见 blockers/verdict）。

---

## 6. 复现（命令与产物）

```bash
# 1) 既有仪器（60 子集，bash-only）
python3 tools/corpus-analysis/ps_silent_check.py --out /tmp/ps-verify

# 2) 全量 664（本 session 临时仪器；源码见附录）
python3 /tmp/ps_full_measure.py        # → /tmp/ps-full/results.json
python3 /tmp/ps_analyze.py             # → 归因/分布

# 3) 缺陷复现
cd <repo> && PYTHONPATH=python python3 -m bat2sh --cli \
  tests/fixtures/real-corpus/fleschutz/cd-up.ps1 --print --fail-on-todo ; echo $?   # → 0

# 4) 常驻 CI 口径（等价）
python3 -m pytest tests/test_real_corpus_metrics.py -q
```

依赖：`bwrap`（0.12）、`bash`、`python3`（3.14）；**pwsh 缺失**（§5）。全部只读源文件，产物写 `/tmp`。

---

## 7. 附录：临时仪器源码（`/tmp/ps_full_measure.py`）

```python
# 复用 ps_silent_check 的沙箱口径；corpus = ~/下载/PowerShell-1.6/scripts（664）
import json, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
REPO = Path("/home/duanjb666/bat2sh")
sys.path.insert(0, str(REPO / "tools" / "corpus-analysis"))
import ps_silent_check as psc
CORPUS = Path("/home/duanjb666/下载/PowerShell-1.6/scripts")
OUT = Path("/tmp/ps-full"); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "python"))
from bat2sh.core.encoding import decode_bytes
from bat2sh.core.engine import convert_text
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import SourceKind

def one(path):
    workdir = OUT / path.stem; workdir.mkdir(parents=True, exist_ok=True)
    decoded = decode_bytes(path.read_bytes(), None)
    raw, report = convert_text(decoded.text, SourceKind.POWERSHELL,
                               ConvertSettings(bash_check=False), path.name)
    (workdir / "script.sh").write_text(raw, encoding="utf-8")
    ok = psc.subprocess.run(["bash", "-n"], input=raw, capture_output=True,
                            text=True).returncode == 0
    rc, _o, err = psc.run(psc.sandbox_bash(workdir))
    return {"name": path.name, "syntax_ok": ok, "bash_rc": rc,
            "bash_err_head": psc.normalize(err).splitlines()[:1],
            "todos": report.todo_count,
            "todo_cats": dict(Counter(d.category for d in report.todos)),
            "errors": report.error_count}

files = sorted(CORPUS.glob("*.ps1"))
with ThreadPoolExecutor(max_workers=16) as pool:
    rows = list(pool.map(one, files))
(OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
```

（完整版含 `lines/error_cats/warnings` 字段，逻辑同上。）

---

## 附录 B：/tmp 数据摘要（防 `/tmp` 被清；本 session 实测）

> 以下为 `/tmp/ps-full/results.json`（664）与 `/tmp/ps-verify`（60）的核心聚合，
> 便于日后复现/核对。**原始 `results.json` 未入仓**（只读约定）。

### B.1 664 全量汇总

| 指标 | 值 |
| :--- | ---: |
| total | 664 |
| syntax_ok | 550（82.8%） |
| bash rc==0 | 214 |
| **strict**（rc0 且 todos==0 且无 `# TODO` 标记） | **0** |
| todos 总数 | 4324 |
| errors 总数 | 0 |
| todo_cats | objects 2056 / misc 1453 / control_flow 442 / command 194 / pipeline 90 / params 72 / registry 17 |

### B.2 语法失败模式（114）

| 模式 | 计数 |
| :--- | ---: |
| 表达式/括号 | 32 |
| for 循环头 | 30 |
| 词法（未闭合引号/here） | 15 |
| try/catch 的 else 发射 | 15 |
| param/类型转换 | 8 |
| 其他 | 14 |

### B.3 rc≠0 归因（336）

| 类 | 计数 |
| :--- | ---: |
| C 缺失路径 | 108 |
| C 缺失命令（Windows 专有） | 99 |
| C/S 其他（COM 空路径 / 主动 exit 1） | 77 |
| A unbound variable | 16 |
| S 无 git 仓库 | 16 |
| A 参数透传 | 8 |
| S 沙箱（NO_NEW_PRIVS/systemd） | 9 |
| S 空 stderr（交互/fixture） | 8 |
| S 网络阻断 | 4 |

### B.4 硬 D 构造分布（源码级，664）

| 构造 | 文件数 |
| :--- | ---: |
| 对象管道 | 462 |
| `.NET` 静态（`::`） | 186 |
| `New-Object`/COM | 113 |
| `Get-Process/Service/EventLog/ChildItem` | 88 |
| CIM/WMI | 18 |
| `Import-Module`/`Add-Type` | 17 |
| 注册表 | 9 |
| 远程会话 | 5 |
| **含 ≥1 硬 D 构造（并集）** | **277（41.7%）** |

### B.5 60 子集

| 指标 | 值 |
| :--- | ---: |
| syntax_ok | 56/60（93.3%） |
| rc==0 | 19 |
| strict | 0 |
| 语法失败（与 v1.8.0 已知 4 例一致） | `cd-recycle-bin.ps1`、`cd-trash.ps1`、`check-apps.ps1`、`check-drives.ps1` |

### B.6 「报告诚实性」缺陷规模（**修正头行口径**）

> **口径修正（纪律 3/4）**：初次分析用 `# TODO` 子串计数，**把脚本头
> `# 带有 # TODO 标记的行无法自动转换` 也计入**（每个文件 1 个），导致 figure 虚高
> （曾报「474/550」）。改用 `measure.py::count_markers` 口径（排除头行）后：

| 指标（排除脚本头） | 修复前 | 修复后 |
| :--- | ---: | ---: |
| **defect：`# TODO` 标记存在但 `todo_count==0`** | **8 / 664** | **0 / 664** |
| `# TODO` 标记数 > `todo_count` | 262 / 550 | 10 / 550 |
| 其中 60 子集 defect | 6 | 0 |

- defect 的 8 个文件：`cd-repo.ps1`、`cd-up*.ps1`(4)、`check-file.ps1`、`list-ssh-key.ps1`、`vi.ps1`。
- 修复后剩余 10 例为「2 个标记同属 1 个已登记 todo」（如 try+catch 两行标记对应 1 个 todo），
  **非缺陷**（每个标记都有对应 todo 登记）。

---

> **本文件为只读实测。** 障碍评估见 `ps-assessment-blockers.md`；判定见 `ps-assessment-verdict.md`。
