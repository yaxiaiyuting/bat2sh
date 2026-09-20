# bat2sh 仓库可发现性审计（只读）

> 会话：仓库可发现性优化。前置：v2.9.0 已发布。
> **本文件为只读审计**：未改动任何代码、README、GitHub 元数据。
> 所有数据均由 `gh` 实测取得，命令与原始输出见 §7。

---

## 0. 结论摘要

| # | 发现 | 严重度 |
| :--- | :--- | :---: |
| 1 | **GitHub Topics 为空**（`[]`）—— GitHub 主题页与 AI 工具的主要发现路径**完全缺失** | **P1** |
| 2 | **Description 是纯中文**，无任何英文关键词 —— 英文检索**零命中** | **P1** |
| 3 | **README 英文关键词全部为 0**（`batch to bash` / `Windows Batch` / `converter` 均 0 次） | **P1** |
| 4 | **README 完全未提 Android / APK / Flet**，而 v2.9.0 的核心交付正是 Android APK | **P2** |
| 5 | 仓库 **homepage 未设置** | P2 |
| 6 | GitHub 许可证识别为 **`Other` / `NOASSERTION`**（LICENSE 首行是自定义抬头） | P3 |
| 7 | README **828 行、11 个 H2、21 个 H3，无 TOC、无 badges** | P3 |
| 8 | `docs/PROJECT-OVERVIEW.md` **自身过期**（仍写「当前版本为 v2.8.1」、§8 仍写「四处版本号」） | 见 §6 |

**一句话**：项目在**自己的目标查询下搜不到** —— `cmd to bash converter` 这个查询全 GitHub
只有 **1 个仓库**，bat2sh 仍不在其中。主要缺口是 **Topics 为空** 与 **描述/README 无英文关键词**，
两者都是零成本的元数据修复。

---

## 1. 前置确认（任务书 §一）

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | 工作区干净，HEAD = v2.9.0 发布后 main tip | ✅ 分支 `main`，HEAD `0f06aa1`，工作区 0 项改动，未推送 0 |
| 2 | `gh` CLI 可用 | ✅ 已登录 `yaxiaiyuting`，scopes 含 `repo`（需带代理，见 §7） |
| 3 | 当前 README 与仓库 About 可读 | ✅ `README.md` 828 行 / 52,390 B |

补充：tag `v2.9.0` → `69e6fde`，HEAD `0f06aa1` 是 tag 之后的 hash-sync 提交
（发布流程第 6 步的预期结果，非偏差）。

---

## 2. 现状盘点

### 2.1 GitHub 仓库元数据（`gh repo view --json` 实测）

| 项 | 现状 | 问题 |
| :--- | :--- | :--- |
| **Description** | `将 Windows 批处理和 PowerShell 脚本转换为 Bash 的桌面工具` | **纯中文**；无 `batch to bash` / `converter` 等英文词；未提 CLI；未提 Android |
| **Topics** | **`[]`（空）** | **一个都没有** —— 主题页 / 相似仓库推荐 / AI 工具索引全部失效 |
| **homepage** | `""`（`gh api` 返回 `null`） | 未设置 |
| **license** | `key: other` / `spdx_id: **NOASSERTION**` / `url: null` | GitHub **无法断言**许可证，按「Other」展示 |
| stars / forks | 1 / 0 | — |
| primaryLanguage | Python | — |
| 创建时间 | 2026-09-13 | 仓库很新（7 天） |
| 默认分支 | `main` | — |

### 2.2 README 现状

| 项 | 现状 | 问题 |
| :--- | :--- | :--- |
| 规模 | 828 行 / 52 KB；**11 个 H2 + 21 个 H3** | 无 TOC，长文导航差 |
| H1 | `# bat2sh — Windows 脚本转 Bash 转换器` | **纯中文**，无英文关键词 |
| 首屏（前 13 行） | 5 行中文介绍 + 10 行「尽力而为」blockquote | **无安装/用法代码块**；**英文读者无法判断这是什么** |
| badges | **无** | 缺 CI / 版本 / 许可证可信度信号 |
| TOC | **无** | 828 行、11 节，靠滚动 |

### 2.3 README 关键词实测

在 `README.md` 中全文 grep 计数：

| 关键词 | 出现次数 |
| :--- | ---: |
| `batch to bash` | **0** |
| `Batch to Bash` | **0** |
| `Windows Batch` | **0** |
| `converter` | **0** |
| `Android` | **0** |
| `APK` | **0** |
| `convert` | 2 |
| `CLI` | 31 |

即：**四个最核心的英文检索词，一个都没有出现**。

---

## 3. 搜索可见性实测（本审计最硬的证据）

用 GitHub 搜索 API，取目标查询的**前 100 个命中**，检查 bat2sh 是否在其中：

| 查询 | 该查询全站仓库数 | bat2sh 是否在前 100 |
| :--- | ---: | :---: |
| `windows batch to bash` | 74 | ❌ **否（0）** |
| `convert bat to sh` | 19 | ❌ **否（0）** |
| `batch to bash converter` | 22 | ❌ **否（0）** |
| `cmd to bash converter` | **1** | ❌ **否（0）** |
| `bat2sh`（仅按名字） | 3 | ✅ 是（1） |

**关键观察**：`cmd to bash converter` 全站只有 **1 个仓库**，这是一个**几乎无人占据**的利基，
而 bat2sh **仍然搜不到** —— 因为它的描述、README、Topics 里都没有这些词。
换句话说：**问题不在竞争，而在元数据**。

> 说明：GitHub 搜索对仓库的排序同时依赖 name / description / **topics** / README 内容。
> 当前三者（除 name 外）都没有目标关键词，因此不出现在任何目标查询里。

---

## 4. 目标关键词

### 4.1 用户可能怎么搜

| 语言 | 查询 |
| :--- | :--- |
| 英文 | `windows batch to bash`、`convert bat to sh`、`batch script converter`、`cmd to bash`、`bat to sh converter` |
| 中文 | `bat 转 sh`、`批处理转 bash`、`Windows 脚本转换`、`cmd 转 shell` |

### 4.2 AI 工具 / 聚合器怎么找

| 路径 | 依赖 | 当前状态 |
| :--- | :--- | :--- |
| GitHub Topics 页 | `repositoryTopics` | ❌ **空** |
| GitHub 搜索 | description + topics + README | ⚠️ 描述纯中文、README 无英文词 |
| 相似仓库推荐 | topics | ❌ 空 |
| 通用搜索引擎 | README 正文 + 描述 | ⚠️ 无英文内容可索引 |
| Release 页 | homepage 指向 | ⚠️ homepage 未设置 |

---

## 5. Topic 候选热度实测

任务书给了一份候选表。我**逐个用 GitHub 搜索实测了每个 topic 的真实使用量**
（`topic:<name>` 命中的仓库总数），结果有两项需要修正：

| 任务书候选 | 实测仓库数 | 判定 |
| :--- | ---: | :--- |
| `windows-batch` | 62 | ✅ 可用（精准，虽小众但真实存在） |
| **`batch-to-bash`** | **0** | ❌ **无人使用（自创词）** |
| `bash` | 34,537 | ✅ 高热度 |
| **`script-converter`** | **4** | ❌ **几乎无人使用** |
| `powershell` | 19,897 | ✅ 高热度 |
| `pyside6` | 4,232 | ✅ 可用 |
| `cli-tool` | 6,256 | ✅ 可用 |
| `android` | 154,166 | ✅ 高热度 |
| `flet` | 760 | ✅ 可用 |
| `linux` | 87,027 | ✅ 高热度 |

**补充实测**（为替换上面两个不可用的 topic）：

| 候选 | 实测仓库数 | 判定 |
| :--- | ---: | :--- |
| `batch-file` | 543 | ✅ **比 `windows-batch` 更热，且同样精准** |
| `batch` | 3,408 | ✅ 可用（但语义偏「批处理」，略宽） |
| `bash-script` | 9,398 | ✅ 可用 |
| `shell` | 27,856 | ✅ 可用（较宽） |
| `converter` | 9,099 | ✅ **`script-converter` 的正确替代** |
| `windows` | 72,395 | ✅ 可用（很宽） |
| `python` | 889,455 | ✅ 极热（但太宽，区分度低） |
| `qt` / `qt6` | 10,819 / 3,053 | ✅ 可用 |
| `desktop-app` | 22,170 | ✅ 可用 |
| `gui` | 25,049 | ✅ 可用 |
| `termux` | 4,361 | ✅ 可用（Android 运行时相关） |
| `transpiler` | 1,627 | ⚠️ 语义偏差（本项目是「尽力而为」翻译，非严格转译） |
| `windows-script` | 11 | ❌ 过冷 |
| `cmd-script` | 7 | ❌ 过冷 |
| `code-converter` | 56 | ⚠️ 偏冷 |

> **纪律（任务书 §3.2 要求「用 GitHub 上已有热度的 topic，不是自创」）**：
> `batch-to-bash`（0）与 `script-converter`（4）**不满足**该要求，故不采纳；
> 由 `batch-file`（543）与 `converter`（9,099）替代。

---

## 6. 事实冲突检查（任务书 §七的暂停条件）

逐项核对 README 与 `docs/PROJECT-OVERVIEW.md`：

| 检查项 | 结果 |
| :--- | :--- |
| README 是否声明版本号 | ❌ **未声明** —— 因此与 OVERVIEW 无**直接**版本冲突 |
| README 功能描述 vs OVERVIEW | ✅ 一致（三栏 GUI / CLI / 编码检测 / 分层报告 / API 修复 TODO 等均对得上） |
| README 许可证章节 | ✅ `AGPL-3.0-or-later`，与 `LICENSE` 文件、`pyproject.toml` 一致 |

**结论：未发现 README ↔ PROJECT-OVERVIEW 的**直接事实冲突**。**

但发现**两处过期**，如实列出（**本 session 不擅自修改**，见 §8 范围说明）：

| # | 位置 | 过期内容 | 应为 |
| :--- | :--- | :--- | :--- |
| 1 | `docs/PROJECT-OVERVIEW.md:6` | 「当前版本为 **v2.8.1**」 | v2.9.0 |
| 2 | `docs/PROJECT-OVERVIEW.md:543,545` | 「校验**四处**版本号一致」（D-1 门） | **五处**（v2.9.0 起纳入 `packaging/android/pyproject.toml`） |

另：`docs/PROJECT-OVERVIEW.md:153,162` 的关键事实表（当前版本 / tag 列表）同样停在 v2.8.1。

**这不是任务书 §七 意义上的「README 与 OVERVIEW 冲突」，故不构成暂停触发条件；
但既然是审计发现，如实报告，交由你决定是否另行处理。**

---

## 7. 复现命令与原始输出

```bash
cd /home/duanjb666/bat2sh
source /tmp/flet-termux-poc/env.sh
export https_proxy=http://127.0.0.1:10808 http_proxy=http://127.0.0.1:10808   # gh 需要代理

# 元数据
gh repo view --json name,description,homepageUrl,repositoryTopics,licenseInfo,stargazerCount
gh api repos/yaxiaiyuting/bat2sh --jq '{license: .license, topics: .topics, homepage: .homepage}'

# 搜索可见性
gh api -X GET search/repositories -f q="cmd to bash converter" -f per_page=100 \
  --jq '.items[].full_name'
gh api -X GET search/repositories -f q="cmd to bash converter" -f per_page=1 --jq '.total_count'

# topic 热度
for t in windows-batch batch-to-bash converter batch-file flet; do
  gh api -X GET search/repositories -f q="topic:$t" -f per_page=1 --jq '.total_count'
done

# README 关键词
for kw in "batch to bash" "Windows Batch" converter Android APK; do
  printf "%-18s %s\n" "$kw" "$(grep -ci "$kw" README.md)"
done
```

**原始输出（关键片段）**：

```
$ gh api repos/yaxiaiyuting/bat2sh --jq '{license, topics, homepage}'
{"description":"将 Windows 批处理和 PowerShell 脚本转换为 Bash 的桌面工具",
 "homepage":null,
 "license":{"key":"other","name":"Other","spdx_id":"NOASSERTION","url":null},
 "topics":[]}

$ 搜索可见性
  windows batch to bash      命中 bat2sh: 0  (该查询共 74 个仓库)
  convert bat to sh          命中 bat2sh: 0  (该查询共 19 个仓库)
  batch to bash converter    命中 bat2sh: 0  (该查询共 22 个仓库)
  cmd to bash converter      命中 bat2sh: 0  (该查询共 1 个仓库)
  bat2sh                     命中 bat2sh: 1  (该查询共 3 个仓库)
```

---

## 8. 审计边界说明（纪律 5：主动披露）

| # | 项 | 说明 |
| :--- | :--- | :--- |
| 1 | 本审计**未改动任何文件** | 未改 README、未改 GitHub 元数据、未改代码 |
| 2 | **`docs/PROJECT-OVERVIEW.md` 的过期不在本 session 交付物内** | 任务书 §九只列了 audit / plan / README / 元数据；故只报告、不修改 |
| 3 | **许可证 `NOASSERTION` 未列入执行方案** | 修它需要改 `LICENSE` 文件首行 —— 属「事实内容」，且涉及法律文件，需你明确授权；本 session 只报告。详见 plan §3.6 |
| 4 | 搜索可见性用 GitHub 搜索 API 实测 | 反映 GitHub 内部检索；**不等于** Google 收录情况（Google 需 Search Console，见 plan §用户行动清单） |
| 5 | topic 热度是**查询时刻**的快照 | 数字会随时间变化；结论（0 与 4 属自创/近空）稳健，具体数值不稳健 |
| 6 | 未测试 Google / Bing / AI 工具的实际收录 | 无凭据访问这些平台；仅从可索引内容（README / description / topics）推断 |

---

## 9. 下一步

优化方案见 **`docs/discoverability-plan.md`**（含 Description / Topics / README 改动点 /
homepage 建议 / 用户行动清单 / Show HN 草稿）。
按任务书 §四硬闸门，**方案提交后暂停，等确认再执行。**
