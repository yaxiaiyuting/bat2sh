# bat2sh 仓库可发现性优化 —— 执行报告

> 会话：仓库可发现性优化（执行）。前置：`docs/discoverability-audit.md` +
> `docs/discoverability-plan.md`（用户已确认五项决策）。
> 基线 HEAD = `0f06aa1`（v2.9.0 发布后 main tip）。

---

## 0. 结论摘要

| # | 项目 | 状态 |
| :--- | :--- | :--- |
| 1 | GitHub Description（方案 B） | ✅ 已生效 |
| 2 | GitHub Topics（10 个） | ✅ 已生效 |
| 3 | GitHub homepage | ✅ 已生效 |
| 4 | README 首屏 + TOC | ✅ 已改（独立 commit） |
| 5 | PROJECT-OVERVIEW 更新至 v2.9.0 | ✅ 已改（独立 commit） |
| 6 | **LICENSE 修正** | ⏸ **暂停报告** —— 实际缺陷**不是**任务书预设的「仅首行有自定义抬头」，而是**一段 85 行的重复残片**；按 §五「LICENSE 修正不确定 → 暂停报告」未改动。诊断与修法见 §4 |
| 7 | 搜索可见性复测 | ✅ **4 个目标查询全部 0 → 1 命中** |

**一句话**：元数据（description / topics / homepage）改动**立即生效** ——
优化前 bat2sh 在 4 个目标英文查询下**全部 0 命中**，优化后**全部命中**。
README 与 PROJECT-OVERVIEW 已同步；**LICENSE 因实际情况与预设不符而暂停**。

---

## 1. 前置确认

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | 工作区干净，HEAD = v2.9.0 发布后 main tip | ✅ `main` @ `0f06aa1`；仅两个审计/方案文档未跟踪 |
| 2 | `gh` CLI 可用 | ✅ 已登录 `yaxiaiyuting`（需带代理） |
| 3 | 审计文档存在 | ✅ `docs/discoverability-audit.md`（11,775 B）、`discoverability-plan.md`（17,933 B） |

---

## 2. 已执行：GitHub 元数据

命令（一次提交三项）：

```bash
gh repo edit \
  --description "Batch/PowerShell to Bash converter — convert Windows .bat/.cmd/.ps1 to Bash. GUI (PySide6) + CLI + Android APK. 批处理/PowerShell 转 Bash 工具。" \
  --homepage "https://github.com/yaxiaiyuting/bat2sh/releases/latest" \
  --add-topic windows-batch,batch-file,bash,powershell,converter,pyside6,flet,android,cli-tool,linux
```

**执行后核对**（`gh api repos/yaxiaiyuting/bat2sh`）：

```json
{"description":"Batch/PowerShell to Bash converter — convert Windows .bat/.cmd/.ps1 to Bash. GUI (PySide6) + CLI + Android APK. 批处理/PowerShell 转 Bash 工具。",
 "homepage":"https://github.com/yaxiaiyuting/bat2sh/releases/latest",
 "topics":["android","bash","batch-file","cli-tool","converter","flet","linux","powershell","pyside6","windows-batch"]}
```

| 项 | 执行前 | 执行后 |
| :--- | :--- | :--- |
| description | `将 Windows 批处理和 PowerShell 脚本转换为 Bash 的桌面工具` | 英文（137 字符，11 个关键词全在前 120 字符内）+ 中文尾注 |
| homepage | `null` | `/releases/latest` |
| topics | `[]`（**0 个**） | **10 个** |
| license | `NOASSERTION` | `NOASSERTION`（**未处理，见 §4**） |

**Description 字符核对**（执行前实测）：

```
总字符数: 137          （GitHub 上限 350）
前 120 字符含: Batch ✅ Bash ✅ converter ✅ Windows ✅ .bat ✅ .cmd ✅
               .ps1 ✅ GUI ✅ PySide6 ✅ CLI ✅ Android ✅
```

---

## 3. 已执行：README + PROJECT-OVERVIEW

### 3.1 README.md

`git diff --stat`：**32 insertions(+), 1 deletion(-)**

| 改动 | 内容 |
| :--- | :--- |
| H1 | `# bat2sh — Windows 脚本转 Bash 转换器` → `# bat2sh — Windows Batch / PowerShell → Bash Converter`（**唯一被删的 1 行**） |
| badges | 新增 4 个：CI（`test.yml`）/ Release / License AGPL-3.0 / Python 3.12+ |
| 英文摘要 | 新增 3 行（GUI 用 PySide6、有 CLI、有 Android APK、核心仅标准库） |
| 快速开始 | 新增 3 行代码块：`makepkg -si` / `./install.sh` / `bat2sh --cli input.bat -o output.sh`（**全部取自 README 现有内容**） |
| TOC | 新增 11 节目录 |

**未改动**：原中文段落、`> 转换是"尽力而为"…` 引用块、§1 功能特性、§4 使用、
§6 转换规则、§7 示例、§11 许可 —— 逐字保留。

**锚点校验**（脚本比对 TOC 链接与实际 H2 标题）：

```
H2 标题数: 12（含新增的「目录」）  TOC 条目数: 11
  ✅ 1-功能特性        ✅ 2-项目结构      ✅ 3-安装          ✅ 4-使用
  ✅ 5-编码处理        ✅ 6-支持的转换规则  ✅ 7-示例          ✅ 8-无法完美转换需要人工干预的特性
  ✅ 9-扩展转换规则     ✅ 10-开发与测试     ✅ 11-许可
锚点校验: 全部匹配
```

代码围栏配对：38 个（偶数）✅。

### 3.2 docs/PROJECT-OVERVIEW.md

`git diff --stat`：**52 insertions(+), 15 deletions(-)**

| 位置 | 改动 |
| :--- | :--- |
| 版头 | 新增 **v2.9.0** 段（Android API 修复含并行、core 零改动、pytest 1571、首个 Android 二进制产物）；v2.8.1 降为历史条目 |
| §0.2 2.x 收尾 | **新增「收尾之后的维护期发布」事实补充**（v2.5.0–v2.9.0）—— 原文只到 v2.4.0，读者会误以为 2.x 停在收尾点；并把「2.x 基线（最终）」澄清为「**v2.3.0 时点**，非最新」 |
| §2 关键事实表 | 当前版本 2.8.1 → **2.9.0**；测试基线 1561 → **1571 passed / 17 skipped**；tag 37 → **38**（补 v2.9.0）；**新增 Android 行** |
| §3 目录结构 | version 2.8.1 → 2.9.0；README 行数 824 → **859**（原文档本就落后 4 行）；**新增 `packaging/` 子树** |
| §4.3 core/api | 新增 **Android 复用**说明（XDG 注入 / Termux 语法闸门 / 队列批量刷新，core 零改动） |
| §5.6 API 修复 TODO | 新增 **Android 侧**行为（AlertDialog 隐私确认、方案 B 面板、单条重试） |
| §8 发布流程 | 「四处」→ **「五处」**（2 处）；版本清单补 `packaging/android/pyproject.toml`；发布说明范围 v1.8.1 → v2.9.0；**新增第 6 步「发布二进制资产」**（sdist/deb/rpm/Arch + **APK 构建顺序陷阱** + digest 核对） |

**残留检查**：`四处` = **0** 次；`五处` = 3 次；`v2.9.0` = 16 次；`Android` = 13 次。
残留的 `2.8.1` 提及均为历史叙述（版本历史、tag 列表、D-1 事故记录）。
关键事实表 14 行**列数全部为 3** ✅。

---

## 4. ⏸ 暂停：LICENSE 未改动（附完整诊断）

### 4.1 为什么暂停

任务书 §3.3 预设的情形是：

> 若标准 AGPL-3.0 文本完整，仅首行有自定义抬头 → **只改首行**

**实际情形与预设不符**（见 4.2）。按任务书 §五「**LICENSE 修正不确定 → 暂停报告**」
与纪律 4「法律文件谨慎」，**本次未改动 `LICENSE` 一个字节**。

### 4.2 诊断（有权威比对证据）

`LICENSE` 760 行，实际结构是**三段**而非两段：

| 行范围 | 内容 | 判定 |
| :--- | :--- | :--- |
| 1–15 | 应用声明（标题 + 版权 + AGPL 标准 notice 块） | ✅ 正常 |
| **16–100** | **AGPL-3.0 开头的重复残片**（header + Preamble + TERMS AND CONDITIONS + `0. Definitions` 截断在 "as well."） | ❌ **多余残片（85 行）** |
| 101–760 | 完整 AGPL-3.0 正文 | ✅ 正常 |

**权威比对**（拉取 FSF 官方 `https://www.gnu.org/licenses/agpl-3.0.txt`，661 行）：

```
=== LICENSE 101-760（660 行）vs 官方正文 2-661（660 行）===
  ✅ 逐字节完全一致 —— 真文本是完整的官方 AGPL-3.0

=== 第 100 行尾部 ===
  LICENSE[100] 尾部: 's well.                    GNU AFFERO GENERAL PUBLIC LICENSE'
  官方首行          : '                    GNU AFFERO GENERAL PUBLIC LICENSE'
  → 真文本首行被拼接在一个残片行之后 ✅
```

即：**第 100 行 = 残片结尾 + 真文本首行**，两段在同一条线上粘连。

### 4.3 影响

- **法律层面**：许可证条款**完整且未被篡改**（逐字节等于官方文本），应用声明也在。
  所以这不是「许可证无效」，而是「文件里多了一段重复残片」。
- **实际层面**：GitHub 无法断言许可证 →
  `license: {key: "other", spdx_id: "NOASSERTION", url: null}`，
  页面按 **Other** 展示 → **按许可证筛选的开发者找不到本项目**。

### 4.4 建议修法（**待你授权，未执行**）

最小、不触碰任何条款的修法：

1. **删除第 16–99 行**（84 行残片）；
2. **第 100 行改为官方首行**（去掉 `public, and in some countries other activities as well.` 前缀）；
3. 第 101–760 行**原样保留**；第 1–15 行**原样保留**。

结果：676 行 = 15 行应用声明 + 661 行官方 AGPL-3.0，**与官方文本逐字节一致**。
预期 GitHub 随即识别为 **AGPL-3.0**。

**需要你注意的副作用**：`LICENSE` 已随 **v2.9.0 及全部历史 Release 的 tarball** 发布；
现在改动会造成「同一许可证在不同版本间文件内容不同」。这不影响授权效力
（条款未变），但如果你介意版本间差异，另一种选择是**下一个版本再改**。

**请指示**：立即修 / 下个版本再修 / 不修。

---

## 5. 搜索可见性复测（基线记录）

### 5.1 优化前 vs 优化后

用同一条查询语句、同样取前 100 命中：

| 查询 | 优化前命中 | 优化前总数 | **优化后命中** | **优化后总数** |
| :--- | :---: | ---: | :---: | ---: |
| `windows batch to bash` | ❌ 0 | 74 | ✅ **1** | 75 |
| `convert bat to sh` | ❌ 0 | 19 | ✅ **1** | 20 |
| `batch to bash converter` | ❌ 0 | 22 | ✅ **1** | 23 |
| `cmd to bash converter` | ❌ 0 | **1** | ✅ **1** | 2 |

Topic 检索（`topic:<name> bat2sh`）同样已命中：`windows-batch` / `batch-file` / `converter` 各 1。

### 5.2 诚实解读

- ✅ **改进是真实的**：四个目标查询从「完全搜不到」变成「能搜到」，这是 0 → 1 的质变。
- ⚠️ **不要过度解读**：这些查询的结果集本身很小（2–75 个仓库），
  总数恰好各 +1，与「bat2sh 因关键词匹配被新纳入索引」一致；
  「命中」只表示出现在前 100，**不代表排名靠前**。
- ℹ️ **本次复测是「立即」复测**（优化后数分钟内），GitHub 搜索索引**已生效** ——
  这与我在方案 §8 中「很可能仍是 0 命中」的预期**相反**，属**偏乐观的偏离**，如实记录。
- ⏳ **仍未验证**：Google / Bing / AI 工具的实际收录。那取决于外部爬虫，
  需数天至数周，且 Google 侧需你用 Search Console 主动提交（见方案 §5）。

### 5.3 建议复测时点

**3–7 天后**再跑一次同样命令，并观察 GitHub 流量页（Insights → Traffic）的
referrer 变化。届时若 `windows batch to bash` 仍只有 1 命中，说明仅靠元数据已到上限，
增量要靠外部社区（方案 §5 / §6 的素材已备好）。

---

## 6. 本次未做（如实披露）

| # | 项 | 原因 |
| :--- | :--- | :--- |
| 1 | **LICENSE 修正** | 实际缺陷与任务书预设不符（85 行残片，而非仅首行抬头）→ 按 §五暂停。见 §4 |
| 2 | **「纪律 1–22」清单写入 PROJECT-OVERVIEW** | 任务书 §3.4 要求「若未含」。**全仓库不存在权威的纪律 1–22 完整清单** —— 各文档只按编号内联引用（最高见「纪律 22」）。**无权威来源即不可编造**（纪律 2/4），故未添加。若需要，请提供清单来源或另行立 session 从各版本报告反推 |
| 3 | Google Search Console / HN / V2EX / Reddit / 知乎 | 需你的账号；素材已在方案 §5–6 备好，**AI 不代发** |
| 4 | 仓库 Settings 中其它开关（social preview 图、Discussions 等） | 任务书未列，未擅自改 |

---

## 7. 偏离与边界披露（纪律 5）

| # | 项 | 说明 |
| :--- | :--- | :--- |
| 1 | **复测结果优于预期** | 方案 §8 写「立即复测很可能仍 0 命中」，实测**立即全部命中**。属偏乐观偏离，已在 §5.2 如实记录并提醒不要过度解读 |
| 2 | **LICENSE 未改** | 任务书决策表写「LICENSE + PROJECT-OVERVIEW 一并处理」，但同一任务书的暂停条件要求「修正不确定 → 暂停」。**两者冲突时取更保守的一条**，并在 §4 给出可直接执行的修法 |
| 3 | **未编造纪律清单** | 见 §6.2。宁可少写，不可杜撰 |
| 4 | **README 实际新增了英文段落** | 方案 §9 已披露：中文 H1 无法承载英文检索词，故新增 3 行英文摘要；均为事实陈述，原有中文一字未删 |
| 5 | **PROJECT-OVERVIEW 顺带修正了 2 处方案未列的过期** | README 行数（824→859，原已落后）与发布说明范围（v1.8.1→v2.9.0）；均为纯事实订正 |
| 6 | **未验证 Google/Bing/AI 工具收录** | 无凭据，只能从可索引内容推断 |

---

## 8. 交付物与 commit

| 文件 | 状态 |
| :--- | :--- |
| `README.md` | 改（32+/1-） |
| `docs/PROJECT-OVERVIEW.md` | 改（52+/15-） |
| `docs/discoverability-audit.md` | 新增（前序 session） |
| `docs/discoverability-plan.md` | 新增（前序 session） |
| `docs/discoverability-report.md` | 新增（本文件） |
| `LICENSE` | **未改**（暂停，见 §4） |
| GitHub 元数据 | description / homepage / topics 已更新 |

commit 计划：

1. `docs: 可发现性审计 + 方案`（两个前序文档）
2. `docs(readme): 首屏英文化 + badges + 快速开始 + TOC`
3. `docs(overview): 更新至 v2.9.0 + Android + 五处版本门`
4. `docs: 可发现性执行报告`

---

## 9. 下一步（需你决定）

| # | 事项 | 说明 |
| :--- | :--- | :--- |
| 1 | **LICENSE 是否修** | 修法已给出（§4.4），可直接执行；或推迟到下个版本 |
| 2 | **是否补充「纪律 1–22」** | 需要权威来源（§6.2） |
| 3 | **外部社区投放** | 素材见方案 §5–6，**由你发布** |
| 4 | **3–7 天后复测** | 命令见 §5.1 |
