# bat2sh 仓库可发现性优化方案

> 配套审计：`docs/discoverability-audit.md`（只读，含全部实测证据）。
> **本文件是方案，尚未执行。** 按任务书 §四硬闸门，等确认后再动手。

---

## 0. 执行摘要

| 动作 | 现状 | 目标 | 风险 |
| :--- | :--- | :--- | :---: |
| **Topics** | `[]` 空 | 10 个（全部实测有真实热度） | 极低 |
| **Description** | 纯中文 | 英文，前 120 字符含核心关键词 | 极低 |
| **homepage** | 未设置 | 指向 Release 页 | 极低 |
| **README 首屏** | 纯中文、无代码块 | 加英文 H1 + 摘要 + 3 行快速开始 + badges | 低 |
| **README 结构** | 828 行无 TOC | 加 11 节 TOC | 极低 |
| **用户行动** | — | Search Console / HN / V2EX / Reddit / 知乎（**AI 只备素材**） | — |

**预计效果**：让仓库首次出现在 `windows batch to bash` / `cmd to bash converter`
这类查询里 —— 目前是 **0 命中**（见审计 §3）。

---

## 1. GitHub Description

**GitHub 上限 350 字符**；搜索引擎与 GitHub 搜索主要吃**前 ~120 字符**。

### 1.1 方案 A（推荐，纯英文）

```
Batch/PowerShell to Bash converter — convert Windows .bat/.cmd/.ps1 scripts to Bash. GUI (PySide6) + CLI + Android APK. Flags untranslatable lines as TODO.
```

- 长度：**157 字符**（< 350）
- 前 120 字符：`Batch/PowerShell to Bash converter — convert Windows .bat/.cmd/.ps1 scripts to Bash. GUI (PySide6) + CLI + Android`
  已覆盖：`Batch`、`Bash`、**`converter`**、`Windows`、`.bat/.cmd/.ps1`、`GUI`、`CLI`、`Android`
- 全部为**事实**：转换范围、技术栈、形态、Android APK（v2.9.0 起随 Release 发布）、
  `# TODO: 手动检查:` 行为 —— 逐项可在仓库中验证
- **未使用**任何「强大 / 优雅 / 极致 / 最佳」类词（纪律 3）

### 1.2 方案 B（英文 + 中文尾注）

```
Batch/PowerShell to Bash converter — convert Windows .bat/.cmd/.ps1 to Bash. GUI (PySide6) + CLI + Android APK. 将 Windows 批处理/PowerShell 脚本转换为 Bash。
```

- 长度：**~170 字符**
- 保留中文检索词（`批处理` / `脚本转换`）
- 代价：尾部略拥挤，且中文占用的是**低价值字符位**（中文 GitHub 搜索量远低于英文）

### 1.3 推荐

**方案 A。** 理由：审计 §3 显示当前 4 个目标英文查询全部 0 命中，而中文检索量小得多；
README 正文仍是中文，中文用户不会因描述改英文而找不到项目。
若你希望兼顾，选方案 B —— 两者前 120 字符完全相同，英文侧收益一致。

---

## 2. GitHub Topics

**上限 20 个，本方案用 10 个。** 每个都经 `gh api search/repositories q=topic:<name>`
实测过真实使用量（数据见审计 §5）。

### 2.1 推荐清单

| # | Topic | 实测仓库数 | 理由 |
| ---: | :--- | ---: | :--- |
| 1 | `windows-batch` | 62 | **输入格式**，最精准的领域词 |
| 2 | `batch-file` | 543 | 同上，且比 `windows-batch` 热 8 倍 |
| 3 | `bash` | 34,537 | **输出目标**，本组最大流量入口 |
| 4 | `powershell` | 19,897 | 次要输入格式 |
| 5 | `converter` | 9,099 | 领域词（替代不可用的 `script-converter`） |
| 6 | `pyside6` | 4,232 | 技术栈（桌面 GUI） |
| 7 | `flet` | 760 | 技术栈（Android 版） |
| 8 | `android` | 154,166 | v2.9.0 新增能力，超大流量入口 |
| 9 | `cli-tool` | 6,256 | 形态 |
| 10 | `linux` | 87,027 | 目标平台 |

### 2.2 任务书候选的修正（**重要**）

任务书建议的两项经实测**不满足**「用已有热度的 topic」这一要求：

| 任务书候选 | 实测 | 处置 |
| :--- | ---: | :--- |
| `batch-to-bash` | **0** | ❌ **剔除**（全 GitHub 无人使用＝自创词，对发现零帮助） |
| `script-converter` | **4** | ❌ **剔除**（几乎无人使用） |

替换为 `batch-file`（543）与 `converter`（9,099）—— 语义等价、热度高两个数量级。

其余 8 项（`windows-batch` / `bash` / `powershell` / `pyside6` / `cli-tool` / `android` /
`flet` / `linux`）**照采纳**。

### 2.3 明确不采纳（附理由）

| Topic | 实测 | 不采纳理由 |
| :--- | ---: | :--- |
| `shell-converter` | 0 | 自创 |
| `windows-script` | 11 | 过冷 |
| `cmd-script` | 7 | 过冷 |
| `code-converter` | 56 | 偏冷 |
| `transpiler` | 1,627 | 语义偏差：本项目是「尽力而为」静态翻译，非严格转译；用了会给错误预期 |
| `python` | 889,455 | 过宽，区分度低（`pyside6`/`flet` 已覆盖技术栈） |
| `batch` | 3,408 | 语义偏「批处理」泛化，已由 `windows-batch` + `batch-file` 覆盖 |

### 2.4 执行命令

```bash
gh repo edit --add-topic windows-batch,batch-file,bash,powershell,converter,pyside6,flet,android,cli-tool,linux
```

---

## 3. README 优化（**只改结构与首屏**）

### 3.1 改动边界（纪律 2）

| 改 | 不改 |
| :--- | :--- |
| H1 标题行 | §1 功能特性（逐字不动） |
| H1 下新增英文摘要 | §4 使用 / §6 转换规则 / §7 示例 |
| 新增 3 行快速开始代码块 | §8 无法完美转换的特性 |
| 新增 badges | §11 许可 |
| 新增 TOC | 任何事实性陈述、版本口径、许可证 |

### 3.2 改动预览（前 5 行 → 新的前 ~35 行）

**现状（`README.md:1-5`）**：

```markdown
# bat2sh — Windows 脚本转 Bash 转换器

将 Windows 批处理（`.bat`/`.cmd`）与 PowerShell（`.ps1`）脚本转换为 Linux Bash 脚本的
桌面工具 + 命令行工具。界面使用 **Python 3 + PySide6（Qt6）**，贴合 KDE Breeze 风格，
在 Wayland（KWin）下原生运行；核心转换引擎只依赖 Python 标准库。
```

**改为**：

```markdown
# bat2sh — Windows Batch / PowerShell → Bash Converter

[![CI](https://github.com/yaxiaiyuting/bat2sh/actions/workflows/test.yml/badge.svg)](https://github.com/yaxiaiyuting/bat2sh/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/yaxiaiyuting/bat2sh)](https://github.com/yaxiaiyuting/bat2sh/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)

**Convert Windows Batch (`.bat`/`.cmd`) and PowerShell (`.ps1`) scripts to Linux Bash.**
Desktop GUI (PySide6/Qt6) + CLI. An Android APK is also available. The conversion engine
depends only on the Python standard library.

将 Windows 批处理（`.bat`/`.cmd`）与 PowerShell（`.ps1`）脚本转换为 Linux Bash 脚本的
桌面工具 + 命令行工具。界面使用 **Python 3 + PySide6（Qt6）**，贴合 KDE Breeze 风格，
在 Wayland（KWin）下原生运行；核心转换引擎只依赖 Python 标准库。

```bash
makepkg -si                            # Arch / CachyOS
./install.sh                           # 免打包安装到 ~/.local
bat2sh --cli input.bat -o output.sh    # CLI 单文件转换
```

> 转换是"尽力而为"的静态翻译：……（**原文不动**）

---

## 目录

- [1. 功能特性](#1-功能特性)
- [2. 项目结构](#2-项目结构)
- [3. 安装](#3-安装)
- [4. 使用](#4-使用)
- [5. 编码处理](#5-编码处理)
- [6. 支持的转换规则](#6-支持的转换规则)
- [7. 示例](#7-示例)
- [8. 无法完美转换、需要人工干预的特性](#8-无法完美转换需要人工干预的特性)
- [9. 扩展转换规则](#9-扩展转换规则)
- [10. 开发与测试](#10-开发与测试)
- [11. 许可](#11-许可)

---
```

### 3.3 逐项说明

| # | 改动 | 依据 |
| :--- | :--- | :--- |
| 1 | H1 由纯中文改为 `Windows Batch / PowerShell → Bash Converter` | 审计 §2.3：`Windows Batch` / `converter` 当前**出现 0 次** |
| 2 | 新增 4 个 badges（CI / Release / License / Python） | 增加可信度；且 License badge 可在 GitHub 判 `NOASSERTION` 时仍显式传达 AGPL-3.0 |
| 3 | 新增 3 行英文摘要 | 让英文读者 3 秒判断这是什么；句子均为**事实**（GUI 用 PySide6、有 CLI、有 Android APK、核心仅标准库） |
| 4 | 保留原中文段落（原文照抄） | 纪律 2：不改事实内容 |
| 5 | 新增快速开始代码块（3 条**真实**命令） | 命令全部取自 README 现有内容（§3.1 `makepkg -si`、§3.2 `./install.sh`、§4 `bat2sh --cli ... -o ...`），**未发明** |
| 6 | 新增 TOC（11 节） | 828 行、11 个 H2 无导航 |

**关于 badge 的真实性核对**：

| Badge | 依据 |
| :--- | :--- |
| CI | `.github/workflows/test.yml` 确实存在（`name: 测试`） |
| Release | 仓库有 Release（v2.9.0） |
| License | `LICENSE` 为 AGPL-3.0 全文；`pyproject.toml` 声明 `AGPL-3.0-or-later` |
| Python 3.12+ | `pyproject.toml` 的 `requires-python = ">=3.12"`；README §10 写 CI 跑 3.12/3.13/3.14 |

---

## 4. 仓库 homepage

**现状**：`homepage: null`（未设置）。

**建议**：指向 Release 页

```
https://github.com/yaxiaiyuting/bat2sh/releases/latest
```

**理由**：项目没有文档站；Release 页是访客**唯一能直接拿到可下载产物**的地方
（sdist / .deb / .rpm / Arch 包 / **Android APK**）。`/releases/latest` 会自动跟随最新版。

**备选**：若你更希望访客先看 README，可留空 —— 但那样 homepage 就浪费了一个
可被搜索引擎与 AI 工具抓取的显式链接位。

---

## 5. 用户行动清单（**AI 不能代做**）

以下动作需要你的账号 / 身份，我只准备素材，**不代发**。

| # | 动作 | 具体做法 | AI 能帮什么 |
| ---: | :--- | :--- | :--- |
| 1 | **Google Search Console** | 添加 `https://github.com/yaxiaiyuting/bat2sh` → 请求编入索引 | 无（需你的 Google 账号） |
| 2 | **Hacker News** | Show HN 帖，**周二上午或周六**（美东） | ✅ 草稿见 §6 |
| 3 | **V2EX** | `/go/share` 或 `/go/programming` | ✅ 草稿见 §6.2 |
| 4 | **Reddit** | r/commandline、r/bash、r/linux（**注意各版自荐规则**） | ✅ 草稿见 §6.3 |
| 5 | **知乎** | 回答「bat 转 bash」「批处理转 shell」类问题 | ✅ 要点见 §6.4 |

> ⚠️ **发帖纪律建议**：先在 1–2 个社区试水，观察反馈再扩展。
> 同一内容在多个社区同时刷会被视为 spam。HN 尤其反感自荐刷屏。

---

## 6. 发帖素材草稿（**仅草稿，未发布**）

### 6.1 Show HN（英文）

**标题**（HN 要求以 `Show HN:` 开头）：

```
Show HN: bat2sh – Convert Windows Batch and PowerShell scripts to Bash
```

**正文**：

```
I wrote bat2sh because I kept having to port .bat files to Linux by hand.

It's a rule-based static translator, not an emulator. It converts .bat/.cmd and .ps1
into Bash and marks every line it cannot translate honestly with
"# TODO: 手动检查: <original>" instead of guessing. The report separates errors,
warnings and TODOs, so you can see how much of the script was actually converted.

What it does:
- GUI (PySide6/Qt6) and a CLI (bat2sh --cli in.bat -o out.sh)
- Handles common cases: variables, if/else, for loops, labels/goto via a small
  dispatch state machine, errorlevel, and a decent chunk of the Windows tool
  mappings (findstr, tasklist, xcopy, ...)
- Optional API-assisted TODO fixing: sends the untranslated lines to an
  OpenAI-compatible endpoint (local Ollama/LM Studio works) and applies the
  suggestions only after `bash -n` passes and you confirm the diff
- Android APK (Flet + embedded Termux runtime) attached to the release

What it does NOT do:
- No Wine, no cmd.exe under the hood, no runtime emulation
- Registry, WMI, COM and .NET object model have no Bash equivalent; those become TODOs
- PowerShell support is explicitly experimental

Rough scale: ~1571 tests, and on a 151-file batch corpus the generated scripts pass
`bash -n`. There's an honest metric in the docs about how many files convert cleanly.

License is AGPL-3.0. Feedback welcome, especially on cases where it produces
confidently wrong output - that's the failure mode I care most about.

https://github.com/yaxiaiyuting/bat2sh
```

> **说明**：以上数字（1571 tests / 151 语料 / AGPL-3.0）均可从仓库验证。
> **未使用**「blazing fast」「powerful」类词。主动写明「不做什么」是 HN 的通行做法，
> 也符合本仓库一贯的诚实口径（`# TODO` 与降级机制）。

### 6.2 V2EX（中文）

**标题**：

```
[分享] bat2sh —— 把 Windows 批处理/PowerShell 转成 Bash 的工具（含 Android 版）
```

**正文要点**（自行展开）：

- 起因：手头 .bat 要迁到 Linux，手工改写太烦
- 是什么：规则式静态翻译，**不是**模拟器；转不了的语句如实打 `# TODO: 手动检查:`
- 形态：桌面 GUI（PySide6/Qt6）+ CLI；v2.9.0 起另附 Android APK
- 可选 AI 修复：把未转换行发到你自己的 OpenAI 兼容端点（本地 Ollama 也行），
  逐条过 `bash -n` 且确认 diff 后才写盘
- 不做什么：不跑 Wine、不做注册表/WMI/COM 等价转换、PowerShell 仍属实验性
- 地址：https://github.com/yaxiaiyuting/bat2sh

### 6.3 Reddit（英文，注意各版规则）

- **r/commandline**：偏工具本身，适合贴 CLI 用法与转换示例对照
- **r/bash**：偏技术，建议以「如何诚实处理无法转换的语句」为切入点，而非纯推广
- **r/linux**：自荐限制较严，**先读版规**，必要时改用评论回复相关提问

标题参考：`bat2sh: converts .bat/.cmd/.ps1 to bash, and tells you what it couldn't convert`

### 6.4 知乎（中文）

建议**回答既有问题**而非发文章（更符合平台调性）：

- 「怎么把 bat 脚本转成 linux 的 sh？」
- 「Windows 批处理如何迁移到 Linux？」
- 「有没有 bat 转 bash 的工具？」

回答要点：说明「自动转换的天花板在哪」（注册表/WMI/COM 无对应物）、
为什么要显式 `# TODO` 而不是猜、以及如何人工复核。

---

## 7. 需要你单独决定的两项（**本方案不含**）

### 7.1 许可证被 GitHub 判为 `NOASSERTION`

**现状**：`LICENSE` 首行是自定义抬头（`bat2sh - Convert Windows batch/PowerShell scripts to Bash`），
GitHub 无法断言许可证 → `spdx_id: NOASSERTION`、`url: null`，
页面按 **Other** 展示（审计 §2.1）。

**影响**：① 按许可证筛选的开发者不会找到本项目；② 「Other」在观感上不如具名许可证可信。

**为何不列入执行方案**：修它要**改 `LICENSE` 文件本体**（法律文件），
属「事实内容」，超出「只改元数据 + 文档」的授权范围，且应由你决定。

**若你授权**，可选的两种最小改法（均不改许可证条款，仅改抬头）：

| 方案 | 做法 | 风险 |
| :--- | :--- | :--- |
| **A** | 删掉自定义首行，让文件以标准 `GNU AFFERO GENERAL PUBLIC LICENSE` 开头，版权行下移 | 低 —— 但 `LICENSE` 已在 v2.9.0 tarball 里，改动会造成版本间差异 |
| **B** | 保持不动，仅在 README 加 License badge（**已含在 §3.2 的改动里**） | 无 —— 但 GitHub 侧仍显示 Other |

**我的建议**：先做 B（已在方案内），A 留到下一个版本随其他改动一起做。

### 7.2 `docs/PROJECT-OVERVIEW.md` 过期

审计 §6 发现两处停在 v2.8.1（当前版本号、D-1 门的「四处」）。
**不在本 session 交付物清单内**，故本方案不含。
如需一并修，请告知 —— 那是纯文档订正，成本很低。

---

## 8. 执行计划（确认后）

顺序与影响面：

| # | 动作 | 产物 | 影响面 |
| ---: | :--- | :--- | :--- |
| 1 | `gh repo edit --description "..."` | GitHub Description | 全站可见 |
| 2 | `gh repo edit --add-topic ...` | GitHub Topics | 全站可见 |
| 3 | `gh repo edit --homepage ...` | 仓库 homepage | 全站可见 |
| 4 | 改 `README.md`（仅首屏 + 结构） | 1 个 commit | 仓库 |
| 5 | commit `docs/discoverability-audit.md` + `discoverability-plan.md` + README | 1–2 个 commit | 仓库 |
| 6 | `git push origin main` | 推送 | 公开 |

**验证方式**（执行后立即复测，形成闭环）：

```bash
# 元数据生效
gh repo view --json description,homepageUrl,repositoryTopics

# 搜索可见性复测（应与审计 §3 的「0 命中」形成对照）
for q in "windows batch to bash" "cmd to bash converter" "batch to bash converter"; do
  echo "$q -> $(gh api -X GET search/repositories -f q="$q" -f per_page=100 \
      --jq '.items[].full_name' | grep -c yaxiaiyuting/bat2sh)"
done
```

> **诚实预期**：GitHub 搜索索引**不是即时**的，topics/description 生效通常需数小时至数天；
> README 内容被搜索引擎收录更慢（数天至数周）。**执行后立刻复测仍可能是 0 命中**，
> 这属正常，不代表方案失败。建议 3–7 天后复测。

---

## 9. 偏离与边界披露（纪律 5）

| # | 项 | 说明 |
| :--- | :--- | :--- |
| 1 | **修正了任务书 §3.2 的两个 topic** | `batch-to-bash`(0) 与 `script-converter`(4) 经实测不满足「已有热度」要求，已替换并给出理由（§2.2） |
| 2 | **Description 建议为纯英文** | 任务书 §3.1 的示例本身即英文；审计显示英文侧当前 0 命中。中文版本作为方案 B 保留 |
| 3 | **README 会新增英文段落** | 任务书要求「加关键词」，而中文 H1 无法承载英文检索词；新增段落均为事实陈述，未改任何原有内容 |
| 4 | **许可证 `NOASSERTION` 只报告不修** | 涉及法律文件，超出授权；已在 §7.1 单列并给出建议 |
| 5 | **`PROJECT-OVERVIEW.md` 过期只报告不修** | 不在交付物清单内；见 §7.2 |
| 6 | **未验证 Google/Bing/AI 工具的实际收录** | 无凭据；只能从可索引内容推断。Search Console 需你操作 |
| 7 | 「预计效果」是**推断**，非实测 | 元数据改动生效需时间，本次无法当场证伪；已给出 3–7 天复测建议 |
