# bat2sh 项目总览

> 本文面向第一次接触本仓库的开发者，用真实仓库证据梳理项目定位、目录、架构、构建、
> 测试与发布流程。事实来源：`README.md`、`pyproject.toml`、`PKGBUILD`、`.SRCINFO`、
> `.github/workflows/test.yml`、`python/bat2sh/` 源码与 `docs/`。
> 当前版本为 **v2.4.0**（tag `v2.4.0`；**goto CFG 高级 · 硬做授权版**，minor）。
> ✅ **2.x 收尾成立（2026-09-18）**：三条件 (a)(b)(c) 全 ✓ → 冻结为**维护模式**；
> B5 / 注册表写 / 名称映射归**终态**；`goto CFG 高级` 的**可证安全子集**已于 **v2.4.0** 落地
> （冗余 goto → no-op；前向跳转不可达区间 → 注释化），其余 goto 形态维持终态（仅 T1 重评）——
> 见 **`docs/v2.3.0-2x-closure.md`**（收尾声明）与 **`docs/v2.4.0-report.md`**。
> **已排期方向（用户 2026-09-18 裁定）**：**块栈重构** —— 解锁 `backward_loop` / `in_block_goto` /
> 一般 `forward_skip` / 完整 goto CFG 状态的共同前置（沿用 `docs/v2.4.0-053-protection.md` 的回归防护 +
> `core/cfg.py`）。其余大方向 = **PS 解冻**（需求驱动，未触发）。
> v2.3.0 = 逐项实测 + 2.x 收尾；v2.2.0 = sc 结构化诚实 TODO；v2.1.0 = CFG 只读数据模型；v2.0.0 = 解析层/词法层硬化。
> 1.x 已于 v1.11.0 收尾为维护模式；`v1.9.1` 为未发布研究代号，见 `docs/v1.9.1-attribution.md`。
> ✅ **1.x 收尾成立（2026-09-17）**：路线图 §4 六标准（修订后）全 ✓ + 收尾三条件 (a)(b)(c) 全 ✓，
> 1.x 冻结为**维护模式**；2.x 范围与启动条件见 **`docs/v1.11.0-1x-closure-final.md`**（收尾声明）。

### 指标口径（v1.8.0 起，务必区分）

| 口径 | 定义 | 用途 |
| --- | --- | --- |
| **原始转换口径（默认）** | `ConvertSettings(bash_check=False)` 的产物通过 `bash -n` 的比例 | **v1.8.0 起为发布口径**（门槛三档：≥93% 可发，<93% 暂停） |
| 降级口径 | 默认设置产物（语法失败时整体降级为注释）通过 `bash -n` 的比例 | 仅历史对照；**易造成「假信心」，勿单独引用** |

#### rc==0 严格口径（**v1.9.0 起**，务必区分）

> **rc==0 = 脚本跑通 且 功能完好。含 `# TODO` 标记的产物不计入 rc==0，单列 `degraded`。**

理由：若 rc==0 只表示「能跑通」，它就退化成 `bash -n`，失去区分度。

| 指标 | 定义 | 分母 |
| --- | --- | --- |
| rc==0（原始） | 沙箱运行退出码为 0 | 语法通过数（147） |
| **rc==0（功能完好）** | 跑通 **且** 三产物不含 `# TODO` 标记、`ConvertReport.todo_count == 0` | 语法通过数 |
| **degraded** | 跑通但含 `# TODO`（功能缺失） | 语法通过数 |

- 判定取「产物含 `# TODO` 标记 **∪** 报告登记 TODO」的并集，与 `--fail-on-todo` 同源。
- v1.9.0 提供了**丢失检测**（`_check_silent_drop`，category `loss`）：源行未产出、无诊断、
  且非既定 noop 时告警，保证「不再有命令静默蒸发」。

- v1.7.0 曾宣称「语法通过率 100%」，实为**降级口径**；同口径下 PS 语料原始口径为 75.0%。
  已补 errata（`docs/releases/v1.7.0.md`）。
- 静默错误率：bat 语料用「模式扫描 + 最小复现」口径（归档 18.5%，**bat**）；
  PS 语料用「运行时行为对照」口径（v1.8.0 实测 14/19 = 73.7%，**PS，实验性**）。
  两者**不可互相套用**。

### 已知环境限制

- **PS 侧为实验性支持**（v1.3 起定位）：对象模型 / `.NET` 静态调用 / 注册表 / 远程会话等
  原理性缺失（D 档）在 bash 无等价物，产物定位为「高级草稿」。
- v1.8.0 的 ROI / 静默错误复检依赖 `bwrap` + 便携 pwsh 7.4.6（沙箱实跑）；
  CI 中无 pwsh 时相关测量跳过（工具见 `tools/corpus-analysis/ps_silent_check.py`）。

### 0.1 1.x 收尾声明（**已收尾** → 维护模式）+ 2.x 范围

> 完整论证、逐条归属与 2.x 启动条件见 **`docs/v1.11.0-1x-closure-final.md`**（收尾声明）；
> 六标准来源核查与标准 1 修订见 **`docs/v1.11.0-standards-revision.md`**。

- v1.10.0 合并三支，交付四个**只读子系统**（B1 名称映射 / B2 输出契约 / C4 控制流台账 / 词法层残余额账），**零转换改动**。
- v1.11.0 执行 **C2 收窄子集**（`for /r`→`find`、`for /f` 字符串形式、`net user /delete`→幂等 `userdel`、
  `attrib ±r`→`chmod`、3 条 hint 纠错）+ **C2 归属重判** + **标准 3 修订**。
- v1.11.0 基线（1.x 最终）：`151` 语料 / 语法 `147` / 功能完好（严格）`19` / degraded `83` / degraded TODO `886` /
  rc≠0 `45` / 崩溃·超时 `0` / pytest `1405` / wine `6/6`。**（v1.10.0 为 16/86/894/1371。）**
- **收尾判据**：三条件 (a) 剩余失败全部有归属（逐条 60 行）、(b) 无可修未修（可做 3 项已执行）、
  (c) degraded `83` = 修订标准 3；**六标准（修订后）全 ✓**——标准 1（原 `≥150/151` 估算）→ 原则性表述
  「语法失败全部有归属」（当前 4 例：1 B 类源畸形终态 + 3 解析层 2.x）；标准 3（原 `≤41` 估算）→ 实测 `≤83`。
- **1.x 结论**：**收尾成立**，冻结为**维护模式**（不再新增转换能力，仅缺陷修复与文档维护）。
- **2.x 范围**：goto 语义转换（CFG，15–25 人日）、PS 解冻、名称映射子系统扩展（`sc`/服务名/UNC）、
  解析层 3 例（括号配平 / 嵌套 `if` / 引号转义）、注册表写（29）、B2 解析级输出适配。
  **启动条件（需求驱动）**：T1 出现真实需求（非理论）｜T2 1.x 维护期发现回归｜T3 外部触发（如 PS 侧刚需）——
  **无触发则不启动**。
- 终态：`regsvr32`/COM、第三方 exe、L4 对象、B 类源畸形、`subst`/`debug`/`mshta`/`mstsc.exe`、
  `%date%` 子串、重定向未赋值变量、`chcp` 类 noop 审计（NEW-2，低优先）。

---

### 0.2 2.x 收尾声明（**已收尾** → 维护模式）+ 3.x 方向

> 完整论证见 **`docs/v2.3.0-2x-closure.md`**（收尾声明）；逐项实测见 `docs/v2.3.0-reality-check.md`。

- v2.0.0 解析层/词法层硬化（+2 语法通过）；v2.1.0 **CFG 只读数据模型**（`core/cfg.py`，零产物变化）；
  v2.2.0 `sc` **结构化诚实 TODO**（`# TODO[SC]`）；v2.3.0 **逐项实测 + 2.x 收尾**（零代码改动）；
  v2.4.0 **goto CFG 高级可证安全子集**（冗余 goto no-op + 前向跳转不可达区间注释化）。
- 2.x 基线（最终）：`151` 语料 / 语法 `149` / **功能完好 19** / degraded `85` / degraded TODO `897` /
  崩溃·超时 `0` / pytest `1448` / wine `6/6`。
- **2.x 翻转清单（5）**：`for /r`→`find`、`for /f` 字符串、`net user /delete`→`userdel`（v1.11.0）+
  降级管道行括号配平、`if exist %VAR:"=%`（v2.0.0）。
- **收尾判据**：三条件 (a) 剩余失败全有归属 ✓、(b) 无可修未修（实测）✓、(c) degraded `85` = 实测下界 ✓。
- **终态清单（2.x 收敛）**：goto（简单/回跳/块内/CFG 高级）、B5 括号跨行、注册表写、
  `sc` 服务名映射、B2 输出适配、L4 对象、第三方 exe。**`goto CFG 高级` 明确归终态（仅 T1 真实需求重评）。**
- **3.x 唯一大方向**：**PS 解冻**（PS 侧从实验性 → 完整语义）；启动条件 **T3（PS 刚需）**，**当前未触发**；
  解析层重写为条件性方向（仅 T1）。**无触发不启动**（沿用需求驱动 T1/T2/T3）。

---

## 1. 项目定位与目标

**一句话**：bat2sh 是把 Windows 批处理（`.bat`/`.cmd`）与 PowerShell（`.ps1`）脚本
"尽力而为"地静态翻译为 Linux Bash 脚本的桌面工具 + 命令行工具。

它要解决的核心问题：

1. **平台迁移成本**：Windows 运维/构建脚本无法在 CachyOS/Arch 上直接运行，手工逐行
   重写成本高且易错。
2. **批处理语义差异**：`%VAR%`、`call :label`、`for /f`、`errorlevel`、重定向与
   `&` 串联等 cmd 专有语义需要系统化改写，而非逐条查手册。
3. **PowerShell 对象模型差异**：对象管道、`try/catch`、哈希表、注册表 API 等在
   bash 中没有直接对应物，需要"可转换的转换、不可转换的显式标记"。
4. **不确定性的可审计性**：转换是近似翻译，必须用三层报告
   （**错误/警告/无法自动转换 TODO**）与 `# TODO` 注释把风险显式暴露，而不是静默产出
   可疑脚本。
5. **产物可执行性兜底**：生成脚本必须通过 `bash -n` 语法校验；失败时整体降级为注释，
   保证"绝不输出坏 bash"。

设计边界：只做静态翻译，不做数据流/类型分析，**不保证行为等价**；生成的 `.sh` 定位为
"高级草稿"，必须人工复核。

---

## 2. 关键事实表

| 项目 | 值 | 证据 |
| --- | --- | --- |
| 仓库 | https://github.com/yaxiaiyuting/bat2sh | `pyproject.toml`、`PKGBUILD`、`python/bat2sh/__init__.py` |
| 当前版本 | **2.4.0**（**goto CFG 高级 · 硬做授权版**；minor；见 `docs/v2.4.0-report.md`） | `pyproject.toml`、`python/bat2sh/__init__.py`、`PKGBUILD`（已同步 2.4.0） |
| 语言 | Python >= 3.12 | `pyproject.toml` `requires-python = ">=3.12"` |
| GUI 框架 | PySide6 / Qt6（`PySide6>=6.5`） | `pyproject.toml` |
| 许可证 | AGPL-3.0-or-later | `pyproject.toml`、`PKGBUILD`、`LICENSE` |
| 目标系统 | CachyOS / Arch Linux（KDE/Wayland 优先） | `README.md` §3.1/§3.4 |
| 依赖分层 | 转换核心仅标准库；GUI 额外 PySide6 | `python/bat2sh/__init__.py` 文档串、`README.md` |
| 测试基线 | pytest **1466 passed** | `docs/releases/v2.4.0.md` §5 |
| CI | GitHub Actions，Python 3.12 / 3.13 / 3.14 | `.github/workflows/test.yml` |
| 入口命令 | `bat2sh`（`bat2sh.__main__:main`） | `pyproject.toml` `[project.scripts]` |
| 已有 tag | v1.0.0 … v1.11.0，**v2.0.0**（解析层/词法层硬化），**v2.1.0**（CFG 只读数据模型），**v2.2.0**（sc 结构化诚实 TODO），**v2.3.0**（2.x 收尾），**v2.4.0**（goto CFG 高级）（`v1.10.0a1`/`b1`/`rc1` 为 pre-release；v1.9.1 未打 tag） | `git tag` |

---

## 3. 目录结构

```text
bat2sh/
├── pyproject.toml               # setuptools 打包配置 + pytest 配置（version 1.10.0）
├── PKGBUILD                     # Arch/CachyOS 打包脚本（makepkg -si）
├── .SRCINFO                     # PKGBUILD 的机读元数据（pkgver/sha256sums 同步）
├── bat2sh.desktop               # 桌面项（MIME 关联 x-bat / x-powershell）
├── bat2sh.install               # pacman 安装钩子（刷新 MIME/desktop 数据库）
├── install.sh                   # 免打包安装脚本（默认 ~/.local）
├── LICENSE                      # AGPL-3.0-or-later
├── README.md                    # 主文档（安装/使用/规则/限制，786 行）
├── data/mime/bat2sh.xml         # 自定义 MIME 类型定义
├── .github/workflows/test.yml   # CI：3.12/3.13/3.14 矩阵跑 pytest -q
├── scripts/
│   ├── bat2sh-dev               # 源码目录直接运行（设置 PYTHONPATH 后 python -m bat2sh）
│   └── bat2sh-launcher          # 安装版启动器（PYTHONPATH=/usr/lib/bat2sh）
├── examples/                    # 可运行示例（.bat/.ps1 及其 .sh 对照）
├── tests/                       # pytest 回归测试（70 个 test_*.py + fixtures/）
├── tools/corpus-analysis/       # 真实语料批量分析脚本与匿名化结果
├── docs/                        # 设计/研究报告与发布说明（见 §9）
└── python/bat2sh/
    ├── __init__.py              # 版本与应用元信息（APP_NAME/APP_ID/...）
    ├── __main__.py              # 统一入口：GUI 或 --cli
    ├── cli.py                   # 命令行模式（argparse + 退出码 + 流式输出）
    ├── data/bat2sh.svg          # 应用图标
    ├── core/                    # 转换引擎（不依赖 PySide6，仅标准库）
    │   ├── types.py             # SourceKind / ConvertReport / Diagnostic
    │   ├── engine.py            # 文件识别、转换编排、写出、备份、chmod
    │   ├── encoding.py          # 编码检测与读写（UTF-8/BOM/GBK/GB18030/Latin-1）
    │   ├── settings.py          # ConvertSettings + JSON 持久化
    │   ├── utils.py             # 引号/重定向切分/路径转换等工具
    │   ├── rules.py             # 全部转换规则表（字典，便于扩展）
    │   ├── batch.py             # 批处理转换器（3224 行）
    │   ├── powershell.py        # PowerShell 转换器（3531 行）
    │   ├── syntax.py            # bash -n 后置校验 + 整体降级
│   ├── registry_map.py      # 注册表只读键映射规则表
│   ├── control_flow.py      # C4 goto 控制流形态台账（v1.10.0b1；只读，不驱动转换）
│   ├── lexical_residuals.py # C(lex) 词法层残余额账（v1.10.0rc1；只读，不驱动转换）
│   ├── cfg.py                # CFG 只读数据模型（v2.1.0 P4：标签表 + goto→标签边；只读，不驱动转换）
│   ├── suggestions.py       # 复杂管道的参考改写建议（只生成注释）
    │   ├── recent.py            # 最近打开文件记录（XDG，JSON）
    │   └── api/                 # API 修复 TODO 子系统（见 §5.6）
    │       ├── config.py        # 配置加载/合并/校验/原子写
    │       ├── provider.py      # OpenAI 兼容 Provider（stdlib，流式 SSE）
    │       └── fixer.py         # TODO 标记扫描/替换（纯函数）
    ├── mappings/
    │   ├── windows_tools.py     # Windows 命令结构化映射表（37 条，evidence 必填 + 校验）
    │   ├── windows_names.py     # Windows **名称**映射表（B1：环境变量/路径根/服务名）
    │   └── output_contracts.py  # 输出契约子系统（B2：命令输出形态差异 + 交叉强制）
    └── gui/                     # 图形界面（PySide6）
        ├── app.py               # QApplication 入口
        ├── main_window.py       # 主窗口与业务编排（1108 行）
        ├── editor.py            # 带行号的代码编辑器
        ├── highlighter.py       # bat/ps1/bash 语法高亮 + TODO 高亮
        ├── dialogs.py           # 设置/差异/报告/关于/API 修复对话框
        └── theme.py             # 深色/浅色/跟随系统
```

> 仓库根目录还包含 `src/`、`pkg/`、`deploy/` 与 `bat2sh-*.tar.gz` / `*.pkg.tar.zst`，
> 均为 makepkg 构建产物，不属于源码结构。

---

## 4. 模块架构与数据流

### 4.1 入口分派

`python/bat2sh/__main__.py` 是唯一入口：若参数中出现 `--cli` 或任何 CLI 专用选项，
走 `cli.main`；否则启动 `gui.app.run_gui`。无参数或仅给定脚本路径时启动 GUI。

```text
python -m bat2sh
   │
   ├── --cli / CLI 选项 ──► core/engine.convert_file()
   │                          │
   │                          ├─ detect_kind()            （按扩展名判 .bat/.cmd/.ps1）
   │                          ├─ encoding.read_source()   （编码检测）
   │                          ├─ convert_text()
   │                          │     ├─ BatchConverter       core/batch.py
   │                          │     └─ PowerShellConverter  core/powershell.py
   │                          │            └─ rules.py / utils.py 规则与工具
   │                          ├─ syntax.bash_syntax_error()（bash -n 校验 → 失败则整体降级）
   │                          └─ write_output()            （备份 → 写 UTF-8/LF → chmod +x）
   │
   └── 无 CLI 选项 ──────► gui/app.py → gui/main_window.py
                              │  （复用 core/engine 的同一套转换 API）
                              └─ editor / highlighter / dialogs / theme
```

### 4.2 转换管线

两条路径（CLI / GUI）在 `core/engine` 处汇合，共用同一转换与校验逻辑：

```text
core/engine.convert_text()
        │
        ▼
core/batch.py 或 core/powershell.py     ← 读取 core/rules.py 规则表
        │                                  （BATCH_SIMPLE_MAP / *_HANDLER_MAP / TODO 表）
        ▼
生成完整 bash 脚本文本
        │
        ▼
core/syntax.py  bash -n  ✅ 通过 ──► 返回 (脚本, ConvertReport)
        │                ❌ 失败 ──► degraded_script() 整体注释 + 记入 errors 层
        ▼
ConvertReport（errors / warnings / todos 三层）
        │
        ▼
CLI：--report / --report-json / 退出码    GUI：报告对话框 / 差异预览 / 状态栏计数
```

### 4.3 `core/api` 子系统（v1.4 引入，v1.5 流式，v1.7 并行）

```text
core/api/config.py    优先级合并：CLI > 环境变量 > ~/.config/bat2sh/api.json（原子写 0600）
core/api/provider.py  OpenAI 兼容（urllib，stream:true SSE）；空闲超时语义；注入式 Transport
core/api/fixer.py     M1/M3/M4 三类 TODO 标记扫描 + 发送边界构造 + diff 应用（纯函数）
core/api/parallel.py  多选并行编排：可收缩限流器 + 429 退避降并发 + 从后往前合并（bash -n 可注入）
```

---

## 5. 核心子系统说明

### 5.1 转换引擎

- `core/batch.py`（批处理）与 `core/powershell.py`（PowerShell）各自实现 `convert()`
  与大量 `cmd_*` 处理方法；两者都返回脚本文本并通过 `self.report` 暴露诊断。
- `core/rules.py` 集中所有规则表：简单命令映射、需要特判的参数命令到 `cmd_*` 方法的
  分派表、TODO 命令表、环境/自动变量映射。扩展规则通常只改此表或新增处理方法。
- `mappings/windows_tools.py` 是 Windows 命令结构化映射表（v1.8.1 起）：
  `evidence` 必填且须指向真实语料（纪律 7），`validate_mappings()` 在测试中守护；
  派发顺序上它位于 `BATCH_HANDLER_MAP` 之后（部分条目仅作文档，见 v1.9.0 rounds B-3）。
- **丢失检测（v1.9.0）**：`_check_silent_drop` 保证任何源行都落为代码/注释/诊断，不得静默蒸发；
  `cmd_todo_hint` 必须返回 `# TODO` 字符串（返回 `None` 会被派发分支整行丢弃）。
- **`%VAR%` 块内冻结（v1.9.2）**：块内用户 `%VAR%` 的**解析时冻结**语义经
  「占位符 + marker + `_compose` 合成期解析」实现（`_a1_*` 私有方法），
  仅对「同最外层块内被赋值」的变量在块头前发射 `__bat2sh_snap_<v>="${v}"`。
- **backlog（2.x）**：`call` 会**重新解析**目标文本并再次展开 `%VAR%`，与「块解析时冻结」
  是不同机制 → 本版不建模，记入路线图 2.x 组；顶层独立 `( … )` group 块冻结亦为 backlog。
- 报告类型定义在 `core/types.py`：`SourceKind`、`Diagnostic`、`ConvertReport`。

### 5.2 语法兜底（`core/syntax.py`）

- `bash_syntax_error(script)`：把生成脚本写入临时文件并执行 `bash -n`，环境无 bash 时
  返回 `None`（不阻断）；错误信息中的临时路径替换为 `<生成脚本>`。
- 失败时：`record_syntax_error()` 把错误记入报告 `errors` 层（`category="syntax"`），
  `degraded_script()` 把原脚本**整体降级为注释**，确保产物仍能通过 `bash -n`，
  绝不输出坏 bash。

### 5.3 注册表映射（`core/registry_map.py`）

- v1.6.0 阶段 B 成果。只覆盖**有证据支持的字面量键路径 + 只读操作**（read/test/enumerate），
  映射为 Linux 等价探针，例如：重启检测 → `/var/run/reboot-required` + `needs-restarting`；
  系统版本 → `/etc/os-release`；硬件信息 → `/sys/class/dmi/id/*`；安装检测 → 包管理器查询；
  文件关联 → `xdg-mime`。所有映射均为语义近似并产生 `registry` 类警告。
- **写类**（`reg add/delete/import`、`Set/New/Remove-ItemProperty`、注册表路径上的
  `New/Remove-Item`、COM `WScript.Shell`、`.NET Microsoft.Win32.Registry`）一律输出
  **结构化 TODO**，供 `--fix-todos` / API 处理：
  `# TODO[REG] op=write key="…" value="…": 手动检查: <原命令>`。
- 拒绝发明：服务名 → systemd unit、`.reg` 生成/导入、PSProvider、动态/变量键路径。
  依据与计数见 `docs/research/b2-registry-mapping.md`。

### 5.4 名称映射（`mappings/windows_names.py`，B1 / v1.10.0a1）

- 与命令表、注册表键表并列的**第三张结构化表**：同一个东西在另一边的**名字**
  （环境变量 / 路径根 / 服务名）。`NameMapping` 含 `kind`、`form`、`confidence`、
  `target_exists`、`evidence`、`integrated`、`notes`；`validate_name_mappings()` 在测试中守护。
- **降级策略**：无依据的 Linux 名 → **行级诚实 TODO**（`form=none`），绝不硬凑（纪律 7）；
  `integrated=False` = 仅登记不驱动转换（`notes` 必须写明 backlog）。
- 集成点（`core/batch.py` 两处）：`_convert_simple_no_pipe` 的 `unmappable_env_names_in`
  预扫（整行 TODO，与 `_expand_vars` 同序先掩 `%%`）、`env_repl` 的映射值 + 警告。
- **首批**：`%ProgramFiles%`（→ 诚实 TODO）、`%AllUsersProfile%`（→ `/usr/share`）、
  盘符/UNC（仅登记）。**不含** `sc→systemctl`（C7/v2.0）。
- **已知限制**：`if`/`for` **头部条件**中的 Windows 专有 env_var 不转为 TODO
  （改头部会触碰块栈配平）；`%ProgramFiles(x86)%` 等无 corpus evidence 的别名未登记。

### 5.5 输出契约（`mappings/output_contracts.py`，B2 / v1.10.0a1）

- **问题**：命令翻译对了但**输出形态**不同（`ipconfig→ip addr`）；`ToolMapping.output_contract`
  此前只是「`notes` 含『输出格式』」的装饰性标记。
- **本版**升级为结构化契约 `OutputContract(command, linux_command, shape, keywords,
  evidence, integrated, notes)`，并**交叉强制**：`output_contract=true` 的命令必须有契约记录。
- **1.x 红线**：**不做解析级输出适配**（路线图 §1.B；v1.8.3 流程感知改法 26/151 churn 被否）；
  本版只做「登记 + 校验 + 诚实化」。
- **首批**：`ipconfig`（`shape=differs`，中文关键词与 `_FINDSTR_CJK_MAP` 由测试锁定）、
  `dxdiag`/`perfmon`（`shape=none`）、`ping`/`help`（仅登记）。
- **消费**：裸 `dxdiag`/`perfmon`（无 `.exe`）由静默透传改为结构化诚实 TODO；
  `.exe` 形态与 `ipconfig`/`ping`/`help`/`for /f` 行为不变。

### 5.6 API 修复 TODO（`core/api/*`）

- **触发方式**：CLI `--fix-todos`（需交互终端，与 `--run` 互斥）或 GUI"API 修复 TODO"。
  实验性、默认不触发。
- **配置**：优先级 CLI > 环境变量 > `~/.config/bat2sh/api.json`；不内置服务商默认，
  `base_url`/`model` 缺失即报错（退出码 6）。
- **流式 SSE**：`provider.py` 用标准库 `urllib` 请求 `{base_url}/chat/completions`，
  统一 `stream: true`；超时是**两次数据到达之间的空闲超时**，长思考模型不再触发读超时。
- **隐私逐条确认**：每次发送前在终端原样展示将离开本机的完整内容，逐条确认；
  不提供"全部同意"，`--yes`/`--force` 不可绕过，非 TTY 直接拒绝。
- **应用门槛**：建议必须通过整脚本 `bash -n` 校验 + unified diff 确认后才应用；
  失败保留原 TODO；全部结束一次性写盘，中断则丢弃。

### 5.7 goto 控制流形态台账（`core/control_flow.py`，C4 / v1.10.0b1）

- **问题**：cmd 的 `goto` 是**任意跳转**（前跳/回跳/跳出/跳入控制块/动态目标），bash 无对应物；
  静态翻译必须先做**控制流图（CFG）**分析。路线图把 C4 评为 1.x 单点最大（~250 TODO）、
  **风险最高**，明确归 **v2.0**（`docs/v1.x-roadmap-research.md` §1.C4/F1）。
- **本版定位**：**不做任何语义转换**（`integrated=False`），把 goto 形态固化为与
  「命令表 / 名称表 / 输出契约表」并列的**第四张表**（`ControlFlowPattern`，7 主形态 + 1 辅形态），
  带 `evidence`（纪律 7）、置信度光谱（A–D）、`plan`（v2.0 转换方案）与 `convertible` 标记。
- **接口**：`classify_goto()`（纯函数、互斥分类）、`summarize_goto_lines()`（`echo`/`rem`
  与 CJK 标签感知）、`validate_control_flow_patterns()`（测试守护）、
  `tools/c4/control_flow_report.py`（只读报告，复现计数）。
- **实测（151 语料）**：goto 语句 1583；转换器口径 goto TODO **1359**/39 文件（v2.4.0 后，较 1364 −5）。
- **已实现形态（v2.4.0）**：`goto :eof`（→ `exit 0`/`return`）、`redundant_goto`（目标紧随其后 → 等价 no-op）、
  `forward_skip` 的**可证安全子集**（无条件顶层 goto + 区间内无标签样行 → 区间不可达 → 逐行注释，含 CJK 标签意识）。
- **未实现形态（诚实 TODO，仅 T1 重评）**：`backward_loop` / `in_block_goto` / `missing_label` /
  `dynamic_target` / `label_in_block`；一般 `forward_skip`（条件/含标签区间/多入口）。
  原因：须重构块栈发射 / `_label_line`（053 域）+ 状态机（15–25 人日），实测翻转 0（纪律 1）。
- **测试**：`tests/test_control_flow_taxonomy.py`（16 条）+ `tests/test_batch_goto_dispositions.py`（8 条，逐形态归属）
  + `tests/test_batch_goto_forward_skip.py`（9 条，可达性边界/运行时语义）。
  设计与分阶段方案见 `docs/session-c4-design.md`；v2.4.0 实现与防护见 `docs/v2.4.0-report.md`、`docs/v2.4.0-053-protection.md`。

### 5.8 词法层残余额账（`core/lexical_residuals.py`，C(lex) / v1.10.0rc1）

- **问题**：053 块栈失同步（v1.9.0）与 A1 `%VAR%` 冻结（v1.9.2）修复后，语料仍有
  **4 个 degraded 文件**触发转换器的「循环变量逸出（块结构失同步）」守卫。
- **本版定位**：**不做任何转换改动**（`integrated=False`），把它固化为与
  「命令表 / 名称表 / 输出契约表 / 控制流表」并列的**第五张只读表**（`LexicalResidual`）。
- **实测证伪任务书标签（4 条 / 3 机制）**：
  - `LF-1`（044 `备份文件/备份服务.bat`、135 `系统优化.bat`）：`_convert_for` 头部正则
    `\((.*)\)` **贪婪**，外层 `for` 的 `in (…)` 被切到内层 `for` 的 `)` → 真失同步（for 头核心）；
  - `LF-2`（059 `打开快捷方式指向的目录.bat`）：leak 守卫**误报**——引号内 / nested-`cmd`
    字符串里的字面 `%%X`（cmd 语义 = 字面 `%X`，wine 实测）；
  - `LF-3`（138 `获取U盘盘符和可用容量.bat`）：`_protect_arith_modulo` **不识别** `%VAR:~n,m%`
    子串式，其收尾 `%` 与后随 `%` 配成取模 → 伪 `%%m` → 守卫误报。
- **为何不实现**：三条机制**均无文件翻转收益**（044/059/135/138 修掉任一条 LF 项仍有其他 TODO），
  且分别落在 **块栈核心**（LF-1）与 **A1 变量展开热路径**（LF-2）→ 纪律 1/10 止损，
  修复草案与 churn 界见 `docs/session-lex-design.md`。
- **接口**：`validate_lexical_residuals()`（纪律 7 evidence 必填）、
  `classify_percent_token()` / `expected_percent_expansion()`（cmd `%%X` 语义参考实现）、
  `summarize_residuals()`；`tools/lex/lexical_report.py`（只读，台账校验 + trigger 漂移检测 + 语料复现）。
- **测试**：`tests/test_lexical_residuals.py`（11 条，断言台账语义与 cmd 语义，不编码转换器现况）。

### 5.9 CFG 只读数据模型（`core/cfg.py`，P4 / v2.1.0）

- **问题**：C4 台账（§5.7）给出了 goto 的**形态分布**，但 goto 语义转换还需要**位置与边**：
  目标标签在何处、方向（前跳/回跳）、是否块内、被几处跳入、被跳过的区间。这是 v2.2
  goto 高级形态（回跳→循环 / 块内 goto）的**前置基础设施**（`session-c4-design.md` §2 Phase 1）。
- **定位**：**纯只读**（`integrated=False`）——**不 import `core.batch`、不被转换器调用**；
  在「命令表 / 名称表 / 输出契约表 / 控制流表 / 词法层表」之外的**第六张只读表**（但为**数据模型**而非台账）。
- **数据结构**：`LabelPosition`（标签 → 行号/下标/块内/入边计数）、`GotoEdge`
  （源、目标、目标类型、方向、块内、条件、冗余、C4 形态键）、`Cfg`（标签表 + 边集）。
- **接口**：`logical_lines()`（与 `batch._logical_lines` 同口径）、`build_cfg()` /
  `build_cfg_from_text()`、`summarize_cfg()`、`validate_cfg()`（每条 goto 必须落入 C4 互斥主形态；
  方向/目标/冗余/入边自洽）、`tools/cfg/cfg_report.py`（只读报告）。
- **实测（151 语料）**：标签位置 **781**；goto 边 **1583**；形态分布 **7/7 与 C4 台账一致**；
  逐文件 `validate_cfg` **0 问题**。
- **为何 P5 未落地**：`redundant_goto` / 顶层 `forward_skip` 经实测**翻转 0**（路线图估算 ≈3–4 为估算错）；
  可证安全子集零产物/零指标影响，`forward_skip` 另需块结构发射（053 同域）→ 归 v2.2.0；
  **v2.2.0 复测仍为 0 → 维持不做**（见 `docs/v2.2.0-reality-check.md` §2.C）。v2.1.0 为**零转换改动**。
- **测试**：`tests/test_cfg.py`（24 条，断言 CFG 语义，不依赖外部语料）。

### 5.10 `sc` 结构化诚实 TODO（`cmd_sc` / v2.2.0，**实测优先**）

- **背景**：v2.2.0 采用**实测优先协议（纪律 18）**——roadmap 提议的 goto 高级 / P5 / 注册表写
  **全部实测翻转 0**（见 `docs/v2.2.0-reality-check.md`）；唯一可做项 = `sc` 诚实 TODO 结构化。
- **实现**：`core/batch.py` 的 `cmd_sc` 解析 `sc <action> [service] [params]`，输出
  `# TODO[SC] op=… service="…" params="…": 手动检查: <原命令>`；category=`service`。
- **纪律 7（零映射）**：**只解析、不映射**——绝不把 Windows 服务名（`AeLookupSvc`/`Alerter`…
  94 个，几无 Linux 同名 unit）硬凑为 `systemctl enable …`。
- **回退**：未知/畸形形态（`sc`、`sc /?`）→ 回退通用诚实 TODO（不崩、不丢行）。
- **兼容**：`# TODO[SC]` 与既有 `# TODO[REG]` 同等可被 `core/api/fixer.py` 扫描（`--fix-todos`）。
- **实测 churn**：仅 `系统优化.bat` 1 文件 / 169 行（纯 tag 插入，原命令逐字未变）；指标全部持平。
- **测试**：`tests/test_batch_sc.py`（12 条，不依赖外部语料）。

---

## 6. 构建 / 安装 / 运行

### 6.1 Arch / CachyOS：PKGBUILD

```bash
makepkg -si
```

`PKGBUILD` 依赖 `python`、`pyside6`、`hicolor-icon-theme`、`shared-mime-info`、
`desktop-file-utils`；`source` 指向 GitHub Release tag tarball，并用固定 `sha256sums`。
`.SRCINFO` 与之保持同步（`pkgver` / `source` / `sha256sums` 三处一致）。

### 6.2 免打包安装

```bash
./install.sh                            # 默认安装到 ~/.local
sudo PREFIX=/usr/local ./install.sh     # 系统级安装
```

### 6.3 pip / 源码运行

```bash
pip install .                # 通过 pyproject.toml 安装（含 PySide6 依赖）
pip install -e .[test]       # 含测试依赖
./scripts/bat2sh-dev                # 源码目录运行 GUI
./scripts/bat2sh-dev --cli a.bat    # 源码目录运行 CLI
```

安装版启动器为 `scripts/bat2sh-launcher`，设置 `PYTHONPATH=/usr/lib/bat2sh` 后执行
`python -m bat2sh`。

### 6.4 常用 CLI 形式

```bash
bat2sh --cli input.bat -o output.sh         # 单文件输出
bat2sh --cli a.bat b.ps1 --outdir build/    # 多文件到目录
bat2sh --cli a.bat --print                  # 只打印，不写盘
bat2sh --cli a.bat --diff                   # unified diff
bat2sh --cli a.bat --dry-run                # 只显示将写出的文件
bat2sh --cli a.bat --report --fail-on-todo  # CI 卡点（有错误/TODO 退出码 3）
bat2sh --cli a.bat --run --yes              # 转换后执行（含 TODO 拒绝，退出码 4）
bat2sh --cli a.bat --fix-todos              # 交互式 API 修复 TODO
```

退出码：`0` 成功；`2` 读写/转换错误；`3` `--fail-on-todo` 命中；`4` `--run` 被 TODO 防护
拒绝；`5` 执行超时/无法启动 bash；`6` `--fix-todos` 配置缺失或非法。
完整参数表见 `README.md` §4.2。

---

## 7. 测试策略

- 框架：**pytest**（`pyproject.toml` 配置 `testpaths=["tests"]`、`pythonpath=["python"]`、
  `-p no:cacheprovider`）。运行方式：`pip install -e .[test] && pytest`。
- 规模：`tests/` 下 104 个 `test_*.py`，v1.10.0 报告 **1371 passed**（v1.9.2 基线 1262）。
- 主要测试类别（按文件名归组）：
  - 批处理转换：`test_batch*.py`（含 args/arithmetic/call/forf/goto/pipeline/robocopy 等）
  - PowerShell 转换：`test_powershell*.py`（含 advanced_function/block_stack/hashtable/try_dispatch）
  - 注册表映射：`test_registry_*.py`（batch/p0-p5/ps/writes）
  - 映射表：`test_mappings_windows_tools.py`（命令）、`test_mappings_windows_names.py`（B1 名称）、
    `test_mappings_output_contracts.py`（B2 契约）、`test_batch_windows_names.py` /
    `test_batch_output_contracts.py`（B1/B2 集成）
  - API 修复：`test_api_config.py`、`test_api_fixer.py`、`test_api_provider.py`、`test_api_parallel.py`
  - CLI：`test_cli*.py`（colors/run/stdout/fix_todos）
  - GUI：`test_gui_*.py`（api_test/fix/run/startup/pure/logging）
  - 端到端与冒烟：`test_examples*.py`、`test_real_corpus.py`、`test_stress_no_crash.py`
  - 基础设施：`test_encoding.py`、`test_packaging.py`、`test_report_*.py`、`test_presets.py`
- **离线原则**：测试不访问真实网络；`core/api/provider.py` 提供注入式 `Transport` 协议，
  用假实现覆盖请求/流式/错误分类。GUI 测试走 `QT_QPA_PLATFORM=offscreen` 等无显示路径。
- **XDG 隔离**：`tests/conftest.py` 提供 `autouse` fixture `_isolate_user_dirs`，
  把 `XDG_CONFIG_HOME` / `XDG_STATE_HOME` 指向临时目录，防止测试误写用户真实配置
  （事故背景见 conftest 注释，2026-09-15）。
- 另有 `bash_check` / `bash_run` 两个 session fixture 做脚本语法校验与执行验证。
- 三层语料思路见 `docs/testing-strategy.md`。

### 7.1 运行时语义双 oracle（黄金对照，v1.9.2 新增）

> **定位**：与「沙箱运行」「三层语料」「发布门槛」并列的**基础设施**，用于抓
> **运行时语义缺陷**——这类缺陷既非语法错误，也未必带 `# TODO`（例：v1.9.2 修复的
> A1 `%VAR%` 冻结语义丢失：产物无 TODO、`bash -n` 通过、但行为错；TODO 扫描抓不到）。

- **工具**：`tools/oracle/golden_harness.py`（用例 `tools/oracle/cases/g01..g06.bat`）。
- **方法**：wine `cmd.exe` 执行源 `.bat` vs `bat2sh` 产物经 `bash` 执行，**规范化后逐例比对**。
- **oracle 权威顺序**：**真机 cmd / 官方文档 > wine**；wine 是重实现，仅作初筛，
  不一致时不得直接判 bat2sh 有错。ChenPi11/cmd **不可作 oracle**（053 构造上输出错误）。
- **已知 wine 不可信**：X5（`echo 1.0.1>out.txt` wine 不吞位，真实 cmd 把紧邻 `>` 的数字
  当文件句柄）、A8（findstr 多词位置参数：wine 自相矛盾）→ 需真机，harness 中标注不断言。
- **CI/无 wine**：自动 **skip 而非 fail**（`tests/test_oracle_wine.py` 与 CLI 均跳过）。
- 背景与用例故事见 `tools/oracle/README.md`。

---

## 8. 发布流程

0. **tag 前必跑 `./scripts/release-preflight.sh`**（v1.8.1 起）：
   在**空 `HOME` 的类 CI 环境**下跑 pytest，复现 CI「无外部语料/配置」条件，
   并要求工作区干净。**背景事故**：v1.8.1 有测试依赖仓库外的 `~/下载/非常批处理/`，
   本地全绿但 CI 红，tag 打完后才发现。该脚本用于杜绝此类「本地绿、tag 后红」。
1. **版本号两处同步**：`pyproject.toml` 的 `version` 与 `python/bat2sh/__init__.py` 的
   `__version__`（两者当前均为 `1.10.0` 正式版）。
   **pre-release 纪律**：alpha/beta/rc 同样是发布——tag 打在 bump commit、CI 全绿、release notes 完整；
   且 pre-release **不同步** `PKGBUILD`/`.SRCINFO`（`v1.10.0a1/b1/rc1` 均停留 1.9.2）。
   **v1.10.0 起为正式版**：`PKGBUILD`/`.SRCINFO` 已同步 `1.10.0` + tag tarball `sha256`。
2. **PKGBUILD 同步**：更新 `pkgver`；tag 生成后同步 `sha256sums`（可用 `updpkgsums`），
   并更新 `.SRCINFO` 使其与 `PKGBUILD` 一致。v1.6.0 的提交序列即为
   `030ab72 chore: bump version to v1.6.0` → `1f68d42 chore(pkg): sync PKGBUILD hashes`
   → `11cd50e docs: v1.6.0 release note`；v1.7.0 为 `7864015 chore: bump version to v1.7.0`
   → `f18d625 chore(pkg): sync PKGBUILD hashes for v1.7.0`；
   v1.8.0 为 `81a50a3 chore: bump version to v1.8.0` → `0f6494b chore(pkg): sync PKGBUILD hashes for v1.8.0`。
3. **打 tag**：tag 打在版本 bump commit 上（`v1.6.0` → `030ab72`，`v1.7.0` → `7864015`，
   `v1.8.0` → `81a50a3`）。
4. **发布说明**：在 `docs/releases/` 下新增 `<版本>.md`（现有 v1.3.0 … v1.8.1），
   记录 New features / Fixes / 验证（pytest 数、CI 结果、`bat2sh --version` 输出）。
5. **CI 门槛**：GitHub Actions 在 Python 3.12 / 3.13 / 3.14 上运行 `pytest -q`，
   全绿方可发布。

### 8.1 会话并发写入防护（r2 新增，会话级纪律）

> 背景：2026-09-16 的 1.x 路线图研究会话中，**另一个并发会话**在研究会话进行期间提交了
> 同一交付物（`docs/v1.x-roadmap-research.md`），HEAD 由 `db28fd8` 变为 `03e4d54`，
> 使「会话开始时记录的基线」失效。AI 侧当时的处置为「只读 + 主动报告」，未覆盖他人产出；
> 但工作流应**预防**此类事件。

**纪律（每次涉及仓库写入的会话必须遵守）**：

```text
1. 会话开始时记录 HEAD = X（写入任务记录/会话摘要）。
2. 每次写操作（edit / write / git commit）前，校验 `git rev-parse HEAD` 是否仍 = X。
3. 若 HEAD ≠ X → 立即暂停，报告「检测到并发写入」，附旧/新 HEAD 与差异，等裁定。
4. 不得为追上变化而放弃校验，也不得静默覆盖他人已提交的交付物。
```

配套建议：长研究会话可在开始时把 HEAD 落盘到 `/tmp/<session>/head.lock`，
并在每次 commit 前后各校验一次（参考 `docs/v1.x-roadmap-research.md` §7 纪律 7）。

---

## 9. 文档索引（`docs/`）

| 文件 | 一句话说明 |
| --- | --- |
| `docs/PROJECT-OVERVIEW.md` | 本文：项目总览与新人地图 |
| `docs/api-fix-design.md` | v1.4 API 修复 TODO 的设计诊断稿（只读，含配置/发送边界/接口契约） |
| `docs/pipeline-patterns.md` | v1.3 管道模式挖掘报告：真实管道行频次统计与候选清单 |
| `docs/real-corpus-report.md` | v1.3 真实语料覆盖率体检报告（37 脚本，归一化描述） |
| `docs/testing-strategy.md` | 测试策略与发布门槛（三层语料） |
| `docs/v1.7.0-design.md` | v1.7.0（C 阶段）TODO 多选并行修复的实现契约（并发/429/合并/配置/GUI） |
| `docs/v1.8.0-roi.md` | v1.8.0 ROI 评估与主体裁定（B1 不做；asyncio 不按表执行；选选项 3） |
| `docs/v1.8.0-design.md` | v1.8.0 实现契约（D1–D7 发射缺陷 + 廉价取消 + 口径定义 + 遗留项 1 关闭） |
| `docs/releases/v1.8.0.md` | v1.8.0 发布说明（含「口径说明」「已知限制」「PS 状态」三小节） |
| `docs/releases/v1.8.0-verification.md` | v1.8.0 本机安装验证日志（版本 + 取消实跑 + 门槛数据） |
| `docs/sandbox-audit.md` | v1.8.1 沙箱审计（bind 泄漏 / HOME tmpfs / unshare-net / die-with-parent / 超时） |
| `docs/v1.8.1-design.md` | v1.8.1 设计：bat 静默错误基准 + 结构化映射表 schema/校验 + Round 0 基线 |
| `docs/v1.8.1-rounds.md` | v1.8.1 多轮循环记录（5 轮，指标对比与 backlog） |
| `docs/releases/v1.8.1.md` | v1.8.1 发布说明（版本理由 / 修复 / 新增映射 / 未修原因 / 静默与环境占比） |
| `docs/v1.8.2-artifact-classification.md` | v1.8.2 转换 artifact 逐条分类（A/B/C/S）+ Batch 2b 词法层评估 + 2c/3 结果 + 验收快照 |
| `docs/releases/v1.8.2.md` | v1.8.2 发布说明（A/B/C/S 分类 / A-1..A-6 修复 / 映射扩展 13 条 / tag 上 CI 复核） |
| `docs/releases/v1.8.2-verification.md` | v1.8.2 本机安装验证日志（版本 + 八项修复实跑 + 门槛数据 + CI 时序） |
| `docs/v1.8.3-attribution.md` | v1.8.3 阶段一：46 条 rc≠0 逐条归因 + 仪器验证 + v1.8.2 数据更正 |
| `docs/v1.8.3-design.md` | v1.8.3 设计：6 条攻坚评估 + §5 退回条目（085/053/062②）检查 |
| `docs/v1.8.3-rounds.md` | v1.8.3 逐 commit 指标（含两处过度触发收窄记录） |
| `docs/releases/v1.8.3.md` | v1.8.3 发布说明（4 修复 / 3 退回 / 2 降级 / 145 分母指标） |
| `docs/releases/v1.8.3-verification.md` | v1.8.3 本机安装验证日志（版本 + 5 项实跑 + 145 分母门槛 + CI 时序） |
| `docs/v1.9.0-design.md` | v1.9.0 设计：新口径基线 + 053 块栈只读评估 + 映射扩展评估 + §0.2 反证核验 |
| `docs/v1.9.0-rounds.md` | v1.9.0 逐优先级指标 + 053 三条 rc 判定 + B-1/B-2/B-3 判定与理由 |
| `docs/releases/v1.9.0.md` | v1.9.0 发布说明（口径说明 / 4 修复 / 映射 10 条 / 已知限制 / 退回条目） |
| `docs/releases/v1.9.0-verification.md` | v1.9.0 本机安装验证日志（版本 + 实跑 + 严格口径门槛 + CI 时序） |
| `docs/v1.9.1-attribution.md` | v1.9.1（未发布代号）86 条 degraded 归因与 L1–L5 分层（只读） |
| `docs/v1.x-roadmap-research.md` | 1.x 全量可行性研究 + 路线图（r2：文件翻转口径 + 1.x 理论下界） |
| `docs/v1.9.2-design.md` | v1.9.2 设计：A1 `%VAR%` 冻结 S2 方案 + churn 计量 + 风险处理 |
| `docs/v1.9.2-rounds.md` | v1.9.2 逐 commit 指标（A1 / C1 / B3 / B4 + 语义默认变更披露） |
| `docs/session-b1b2-coldstart.md` | Session B1/B2 冷启动自检（前置核对 / 前提核对 / 仪器修复 / 口径更正） |
| `docs/session-b1b2-review.md` | Session B1/B2 自我审阅与裁定（范围/风险/churn/止损/退路/客观验收；裁定=收窄后实现） |
| `docs/session-b1b2-rounds.md` | Session B1/B2 逐 commit 指标（B1/B2 框架与首批 + churn 实测） |
| `docs/session-b1b2-report.md` | Session B1/B2 报告（交付/未完成/指标对比/冲突区域/Session B 起点） |
| `docs/session-c4-coldstart.md` | Session C4 冷启动自检（前置核对 / 前提核对 / goto 形态实测） |
| `docs/session-c4-review.md` | Session C4 自我审阅与裁定（范围/风险/止损/退路/客观验收；裁定=收窄后实现） |
| `docs/session-c4-design.md` | C4 goto 控制流设计契约（形态分布 + v2.0 分阶段 CFG 方案 + 闸门） |
| `docs/session-c4-report.md` | Session C4 报告（交付/未完成/指标对比/wine/冲突区域/Session C 起点） |
| `docs/session-lex-coldstart.md` | Session C(lex) 冷启动自检（前置核对 / 前提核对 / 4 条残余实测机制） |
| `docs/session-lex-review.md` | Session C(lex) 自我审阅与裁定（范围/风险/止损/退路/验收；裁定=退回设计文档） |
| `docs/session-lex-design.md` | C(lex) 词法层残余额账 + LF-1/2/3 修复草案（v1.10.0rc1） |
| `docs/session-lex-report.md` | Session C(lex) 报告（交付/未完成/指标对比/wine/合并建议） |
| `docs/releases/v1.10.0rc1.md` | v1.10.0rc1 pre-release 发布说明（词法层残余台账 / 已知限制 / 后续计划） |
| `docs/releases/v1.10.0rc1-verification.md` | v1.10.0rc1 本机安装验证日志（版本 + 6 项实跑 + tag 上 CI 时序 + 指标快照） |
| `docs/releases/v1.10.0a1.md` | v1.10.0a1 pre-release 发布说明（B1/B2 子系统 / 口径更正 / 已知限制 / 后续计划） |
| `docs/releases/v1.10.0a1-verification.md` | v1.10.0a1 本机安装验证日志（版本 + 5 项实跑 + tag 上 CI 时序 + tarball sha256） |
| `docs/releases/v1.10.0b1.md` | v1.10.0b1 pre-release 发布说明（C4 控制流台账 / CI 修正 / 已知限制 / 后续计划） |
| `docs/releases/v1.10.0b1-verification.md` | v1.10.0b1 本机安装验证日志（版本 + 实跑 + tag 上 CI 时序 + tarball sha256） |
| `docs/v1.10.0-merge-plan.md` | v1.10.0 三分支合并计划（累积拓扑 / 冲突预判=0 / 合并顺序 / 验证清单） |
| `docs/v1.10.0-1x-closure.md` | **1.x 收尾判定（未达成）** + 剩余项清点 + 2.x 范围与可证伪启动条件（v1.10.0 核心交付） |
| `docs/v1.10.0-report.md` | v1.10.0 发布报告（合并 / 全量验证 / tag / CI / AUR / 收尾结论） |
| `docs/v1.11.0-coldstart.md` | v1.11.0 冷启动自检（前提核对：46/36/≤41 三项不可复现） |
| `docs/v1.11.0-review.md` | v1.11.0 自我审阅与裁定（三类设施范围/风险/最小复现/止损/退路） |
| `docs/v1.11.0-instrument-verify.md` | v1.11.0 仪器验证（三轮复跑逐字段一致）+ 前提再核 |
| `docs/v1.11.0-reclassification.md` | **C2 归属重判**（registry 29/29→2.x；other 17 单设施逐条；可做 3+1） |
| `docs/v1.11.0-standard-3-revision.md` | 路线图 §4 标准 3 修订（≤41 → ≤83 实测）+ 纪律 9 强化 |
| `docs/v1.11.0-1x-closure-final.md` | **1.x 收尾声明**（六标准修订后全 ✓ + 三条件全 ✓ → 收尾成立）+ 2.x 范围与需求驱动启动条件 |
| `docs/v1.11.0-standards-revision.md` | **六标准来源核查**（2 条估算 / 4 条仪器）+ 标准 1 修订（原则性表述）+ 纪律 9 强化 |
| `docs/v1.11.0-report.md` | v1.11.0 发布报告（交付/归属重判/标准修订/指标/收尾判定） |
| `docs/v2.0.0-coldstart.md` / `v2.0.0-review.md` / `v2.0.0-breaking-changes.md` / `v2.0.0-report.md` | v2.0.0 解析层/词法层硬化（coldstart / 审阅裁定 / 破坏性声明 / 报告） |
| `docs/v2.1.0-coldstart.md` | v2.1.0 冷启动自检（前置核对 / 仪器复现 / 证伪「翻转 ≈3–4」/ 偏离披露） |
| `docs/v2.1.0-review.md` | v2.1.0 自我审阅与裁定（范围/风险/最小复现/止损/退路；裁定 = 只交 P4，P5/B5 归 v2.2.0） |
| `docs/v2.1.0-breaking-changes.md` | v2.1.0 破坏性变更声明（实测：无破坏性变更） |
| `docs/v2.1.0-report.md` | v2.1.0 发布报告（交付/未完成/指标/053-A1/下一版起点） |
| `docs/releases/v2.0.0.md` | v2.0.0 发布说明（解析层/词法层硬化；2.x 定位声明） |
| `docs/releases/v2.1.0.md` | v2.1.0 发布说明（CFG 只读数据模型；P5 显式归 v2.2.0；无障碍声明） |
| `docs/releases/v2.1.0-verification.md` | v2.1.0 本机安装验证日志（版本 + 实跑 + tag 上 CI 时序） |
| `docs/v2.2.0-coldstart.md` | v2.2.0 冷启动自检（前置核对 / 仪器复现 / 实测优先协议 / 前提核对） |
| `docs/v2.2.0-reality-check.md` | **v2.2.0 逐项实测（核心产出）**：goto 高级/P5/sc/注册表写/B5 全部翻转 0 + 裁定 + 六次估算错误统计 |
| `docs/v2.2.0-review.md` | v2.2.0 自我审阅与裁定（范围/风险/止损/退路/原则性验收；裁定 = sc 结构化诚实 TODO） |
| `docs/v2.2.0-report.md` | v2.2.0 发布报告（逐项实测/翻转 0/指标/053-A1/下一版起点） |
| `docs/releases/v2.2.0.md` | v2.2.0 发布说明（实测优先协议 / 逐项实测 / 六次估算错误 / sc 诚实 TODO 结构化） |
| `docs/v2.3.0-coldstart.md` | v2.3.0 冷启动自检（前置 / 仪器复现 / 2.x 结构性事实 / 前提核对） |
| `docs/v2.3.0-reality-check.md` | **v2.3.0 逐项实测（核心产出）**：goto 回跳/块内/CFG 高级/B5/注册表写全部翻转 0 + 裁定 |
| `docs/v2.3.0-review.md` | v2.3.0 自我审阅与裁定（情形 B：全 0 → 触发 2.x 收尾评估） |
| **`docs/v2.3.0-2x-closure.md`** | **2.x 收尾声明**（三条件全 ✓ + goto CFG 高级归属 + 3.x 范围 + PS 解冻评估） |
| `docs/v2.3.0-report.md` | v2.3.0 报告（逐项实测 / 2.x 收尾判定 / goto CFG 高级归属 / 下一版起点） |
| `docs/releases/v2.3.0.md` | v2.3.0 发布说明（实测优先 / 2.x 收尾声明 / goto CFG 高级归属 / PS 解冻评估） |
| `docs/v2.4.0-coldstart.md` | v2.4.0 冷启动自检（前置五条 / 仪器复现 / goto CFG 高级复述 / 053·A1 代码锚点 / 前提核对） |
| **`docs/v2.4.0-053-protection.md`** | **053/A1 回归防护设计**（测试清单 + 修复代码路径 + 四道检测 + 覆盖文件逐文件 diff + 回滚锚点） |
| `docs/v2.4.0-review.md` | v2.4.0 自我审阅与裁定（范围/目标/风险/止损/退路/替代/原则性验收；裁定=进入实现） |
| `docs/v2.4.0-breaking-changes.md` | v2.4.0 破坏性变更声明（允许/禁止 + 实测产物变化 + 近失静默错披露） |
| `docs/v2.4.0-report.md` | v2.4.0 报告（goto 7+1 归属 / 053·A1 回归 / 实测指标 / 近失静默错 / 2.x 状态） |
| `docs/releases/v2.4.0.md` | v2.4.0 发布说明（goto CFG 高级硬做授权 / 形态覆盖 / 防护 / 指标 / 已知限制） |
| `docs/2.x-roadmap-research.md` | 2.x 路线图研究（goto/CFG、名称映射、版本序列 v2.0/v2.1/v2.2） |
| `docs/releases/v1.11.0.md` | v1.11.0 发布说明（C2 收窄执行 / 归属重判 / 标准 3 修订 / 已知限制） |
| `docs/releases/v1.10.0.md` | v1.10.0 正式版发布说明（1.x 功能冻结 / 四个并行子系统 / 诚实披露） |
| `docs/releases/v1.10.0-verification.md` | v1.10.0 本机安装验证日志（版本 + 实跑 + tag 上 CI 时序 + tarball sha256） |
| `docs/releases/v1.3.0.md` | v1.3.0 发布说明（errors 层、findstr 中文模式、for/f 两段管道） |
| `docs/releases/v1.4.0.md` | v1.4.0 发布说明（API 修复 TODO，CLI + GUI） |
| `docs/releases/v1.4.1.md` | v1.4.1 发布说明（GUI"测试连接"按钮） |
| `docs/releases/v1.4.2.md` | v1.4.2 发布说明（for/f 包装引号等修复） |
| `docs/releases/v1.5.0.md` | v1.5.0 发布说明（API 修复支持流式 SSE） |
| `docs/releases/v1.6.0.md` | v1.6.0 发布说明（PS 块结构加固 + 注册表智能映射） |
| `docs/releases/v1.7.0.md` | v1.7.0 发布说明（TODO 多选并行修复 + `[REG]` 语义明确） |
| `docs/releases/v1.7.0-verification.md` | v1.7.0 本机安装验证日志（版本 + 并行修复实跑 + 门槛数据） |
| `docs/research/b1-dynamic-tracing.md` | B1 研究：PS 动态追踪可行性（结论：值得做，作为静态转换的补充） |
| `docs/research/b2-registry-mapping.md` | B2 研究：注册表映射可行性（读可做、写一律拒绝） |
| `docs/research/b3-ps-block-structure.md` | B3 研究：PS 块结构 4 缺陷修复评估 |

---

## 10. 相关工具

- `tools/corpus-analysis/`：对真实 Windows 脚本做"转换 → 静态分析 → bwrap 沙箱运行 →
  结果关联"的批量体检（`analyze.py` / `sb.py` / `results-anonymized.json`），
  不含任何无许可语料原文。说明见该目录 `README.md`。
- `tools/corpus-analysis/measure.py`：**可复现语料测量仪器**（v1.11.0 固化，纪律 9 强化）
  —— 原始转换口径 + rc==0 严格口径，输出 `measure.json`（summary + 逐文件 rc/todo）。
  用法：`python3 tools/corpus-analysis/measure.py --corpus <DIR> --out <DIR>`。
- `tools/oracle/`：wine-cmd **黄金行为对照** harness（§7.1），抓运行时语义缺陷；
  用例 `cases/g01..g06.bat`，无 wine 时 skip。说明见该目录 `README.md`。
- `tools/c4/`：**goto 控制流只读报告**（§5.7），复现形态台账计数并给转换器口径统计；
  只读、不跑沙箱，语料缺失时退出码 2。说明见该目录 `README.md`。
- `tools/lex/`：**词法层残余额账只读报告**（§5.8），台账校验 + trigger 漂移检测 + 语料复现；
  只读、不跑沙箱、不改转换器。
- `tools/cfg/`：**CFG 只读数据模型报告**（§5.9），构建标签表 + goto 边并与 C4 台账交叉核对；
  只读、不跑沙箱、不改转换器。语料缺失时退出码 2。说明见该目录 `README.md`。
