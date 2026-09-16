# bat2sh 项目总览

> 本文面向第一次接触本仓库的开发者，用真实仓库证据梳理项目定位、目录、架构、构建、
> 测试与发布流程。事实来源：`README.md`、`pyproject.toml`、`PKGBUILD`、`.SRCINFO`、
> `.github/workflows/test.yml`、`python/bat2sh/` 源码与 `docs/`。
> 当前版本为 **v1.8.1**（tag `v1.8.1`；打包同步 commit 见 §8 发布流程）。

### 指标口径（v1.8.0 起，务必区分）

| 口径 | 定义 | 用途 |
| --- | --- | --- |
| **原始转换口径（默认）** | `ConvertSettings(bash_check=False)` 的产物通过 `bash -n` 的比例 | **v1.8.0 起为发布口径**（门槛三档：≥93% 可发，<93% 暂停） |
| 降级口径 | 默认设置产物（语法失败时整体降级为注释）通过 `bash -n` 的比例 | 仅历史对照；**易造成「假信心」，勿单独引用** |

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
| 当前版本 | 1.8.1 | `pyproject.toml`、`python/bat2sh/__init__.py`、`PKGBUILD` |
| 语言 | Python >= 3.12 | `pyproject.toml` `requires-python = ">=3.12"` |
| GUI 框架 | PySide6 / Qt6（`PySide6>=6.5`） | `pyproject.toml` |
| 许可证 | AGPL-3.0-or-later | `pyproject.toml`、`PKGBUILD`、`LICENSE` |
| 目标系统 | CachyOS / Arch Linux（KDE/Wayland 优先） | `README.md` §3.1/§3.4 |
| 依赖分层 | 转换核心仅标准库；GUI 额外 PySide6 | `python/bat2sh/__init__.py` 文档串、`README.md` |
| 测试基线 | pytest **1167 passed** | `docs/releases/v1.8.0.md` §验证 |
| CI | GitHub Actions，Python 3.12 / 3.13 / 3.14 | `.github/workflows/test.yml` |
| 入口命令 | `bat2sh`（`bat2sh.__main__:main`） | `pyproject.toml` `[project.scripts]` |
| 已有 tag | v1.0.0 … v1.8.1（共 18 个） | `git tag` |

---

## 3. 目录结构

```text
bat2sh/
├── pyproject.toml               # setuptools 打包配置 + pytest 配置（version 1.8.1）
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
    │   ├── suggestions.py       # 复杂管道的参考改写建议（只生成注释）
    │   ├── recent.py            # 最近打开文件记录（XDG，JSON）
    │   └── api/                 # API 修复 TODO 子系统（见 §5.4）
    │       ├── config.py        # 配置加载/合并/校验/原子写
    │       ├── provider.py      # OpenAI 兼容 Provider（stdlib，流式 SSE）
    │       └── fixer.py         # TODO 标记扫描/替换（纯函数）
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

### 5.4 API 修复 TODO（`core/api/*`）

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
- 规模：`tests/` 下 78 个 `test_*.py`，v1.8.1 报告 **1167 passed**（v1.8.0 基线 1145，新增 22）。
- 主要测试类别（按文件名归组）：
  - 批处理转换：`test_batch*.py`（含 args/arithmetic/call/forf/goto/pipeline/robocopy 等）
  - PowerShell 转换：`test_powershell*.py`（含 advanced_function/block_stack/hashtable/try_dispatch）
  - 注册表映射：`test_registry_*.py`（batch/p0-p5/ps/writes）
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

---

## 8. 发布流程

0. **tag 前必跑 `./scripts/release-preflight.sh`**（v1.8.1 起）：
   在**空 `HOME` 的类 CI 环境**下跑 pytest，复现 CI「无外部语料/配置」条件，
   并要求工作区干净。**背景事故**：v1.8.1 有测试依赖仓库外的 `~/下载/非常批处理/`，
   本地全绿但 CI 红，tag 打完后才发现。该脚本用于杜绝此类「本地绿、tag 后红」。
1. **版本号两处同步**：`pyproject.toml` 的 `version` 与 `python/bat2sh/__init__.py` 的
   `__version__`（两者当前均为 `1.8.1`）。
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
