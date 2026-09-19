# bat2sh 流水线报告 —— PS 评估收尾 + v2.8.1（报告诚实性修复）已发布

> **用户醒来第一读物。** 本 session 目标：PS 只读评估收尾（提交 4 份文档）+ 修 A 类缺陷 + 发 v2.8.1。
> **结论**：**v2.8.1 已完整交付并发布**；**PS 判定：继续冻结**；项目进入**维护模式**。
> 起点 HEAD = `46d5d21`；终点 HEAD = 以 `git rev-parse HEAD` 为准（发布回填后）。
> 前一版流水线见 `docs/pipeline-report.md` 历史（v2.8.0 段见 `docs/v2.8.0-report.md`）。

---

## 0. TL;DR

| 交付 | 状态 | 证据 |
| :--- | :--- | :--- |
| PS 解冻评估（4 文档） | ✅ commit `a919050` | `docs/ps-assessment-*.md` |
| **判定** | ✅ **继续冻结** | `ps-assessment-verdict.md` |
| A 类缺陷修复 | ✅ commit `c0d7fb3` | PS `# TODO` 计入 `todo_count` |
| 发布 | ✅ tag `v2.8.1` @ `e628e39` | CI 全绿 / Release Latest |
| 项目状态 | ✅ **维护模式** | 等 T1′–T4′ 触发 |

---

## 1. 前置确认

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | 起点 HEAD = `46d5d21` | ✅ |
| 2 | `git status` 干净（4 份评估 doc untracked） | ✅ |
| 3 | pytest | ✅ **1554 passed** |
| 4 | PS 语料可用（664 + 60） | ✅ |
| 5 | **pwsh 运行时 oracle** | ❌ 缺失（语义不可测，已披露） |

---

## 2. PS 解冻评估（commit `a919050`）

**判定：继续冻结。** 要点：

- **PS strict = 0/664**（rc0 且无 `# TODO`）：即便修好全部语法，语义等价仍不可达。
- **硬 D 构造 277/664 = 41.7%**；`objects` TODO **47.6%**（对象模型/.NET/CIM/注册表/远程）。
- 语法 550/664 = 82.8%（114 个 A 类发射缺陷）；rc==0 214；崩溃 0。
- 无真实需求（T1/T2/T3 未触发）；**pwsh oracle 缺失** → 语义工作不可验证。
- 重启触发收紧为 **T1′–T4′**（见 verdict）。

交付：`ps-assessment-history.md`、`ps-assessment-reality.md`（含 /tmp 数据摘要附录）、
`ps-assessment-blockers.md`、**`ps-assessment-verdict.md`（核心）**。

---

## 3. A 类缺陷修复（commit `c0d7fb3`）

**问题**：PS `try/catch`、`finally`、复杂哈希表、`elseif` 解析失败、未闭合 here-string 的
自定义 `# TODO` 标记**只登记 warning**，不计入 `todo_count` → `--fail-on-todo` **静默退出 0**。

**修复**：新增 `_register_todo`（`_todo` 复用），在 **7 处**自定义标记点登记 todo。

| 指标（全量 664，排除脚本头） | 修复前 | 修复后 |
| :--- | ---: | ---: |
| defect（markers>0 且 todos==0） | 8 | **0** |
| markers > todos | 262 | 10（多标记同属一个 todo） |

**回归测试**：`test_powershell.py` 5 条 invariant（参数化）+ `test_cli.py` 2 条门回归；
更新 3 条既有断言（原断言 `todo_count==0` 即缺陷本身）。

**边界**：PS 路径独立，**未触 053/A1 与 bat 转换逻辑**；**不是「PS 解冻」**，只修报告诚实性。

---

## 4. 发布 v2.8.1

| 步骤 | 结果 |
| :--- | :--- |
| preflight | ✅ 1544 passed / 17 skipped |
| bump | **`e628e39`** `chore: bump version to v2.8.1` |
| tag | **`v2.8.1`**（annotated） |
| CI | ✅ tag `35429963246` / main `35429961583` / pkg `35430069124` 全 success |
| PKGBUILD | **`0d06a4c`**，sha256 `cf6a3e29…1c64`（二次一致），.SRCINFO 重生成 |
| Release | ✅ **v2.8.1（Latest）** https://github.com/yaxiaiyuting/bat2sh/releases/tag/v2.8.1 |
| AUR | **不进** |
| 本机验证 | ✅ 真实 `pacman -U`：`bat2sh 2.8.1`；PS 门 exit 3；bat 门回归 OK（`docs/releases/v2.8.1-verification.md`） |

---

## 5. 验收

| 项 | 结果 |
| :--- | :--- |
| pytest | ✅ **1561 passed**（+7） |
| 全量 664 defect | ✅ **8 → 0** |
| PS 语法口径 | ✅ 56/60 = 93.3%（未回退） |
| 151 bat 语料 | ✅ 151/149/101/19/82/851/崩溃 0 |
| 053/A1 | ✅ 未触 |
| 无新依赖 | ✅ |

---

## 6. 偏离与如实披露（纪律 3/4）

| # | 项 | 说明 |
| :--- | :--- | :--- |
| 1 | 任务书 §2.1「语法 75.0%」 | 实为 v1.8.0 **修复前**；修复后 93.3%（reality §0 已校正） |
| 2 | 664 全量归因 | **模式级自动归因**（非 450 文件逐条人工）；原始结果 `/tmp/ps-full/results.json`，摘要入 reality 附录 B |
| 3 | 头行口径修正 | 初次「474/550」把脚本头 `# 带有 # TODO 标记` 计入；改用 `measure.py::count_markers` 口径后为 262（修复前）/10（修复后）；defect 8→0 |
| 4 | 运行时语义 73.7% | **不可复现**（pwsh 缺失） |
| 5 | 3 条既有测试断言更新 | 原 `todo_count==0` 即缺陷本身；改为语义正确的计数并加 invariant |
| 6 | 本 session 未开专用分支 | 直接在 `main` 提交（docs + fix + bump），符合 patch 发布 |

---

## 7. 后续（**维护模式**）

1. **等 T1′–T4′ 触发**（`ps-assessment-verdict.md` §4）：
   - T1′ 真实 PS 迁移需求；T2′ PS 回归；T3′ 外部刚需 **且 pwsh oracle 就绪**；T4′ 具名读类映射。
2. **若触发**的候选范围（P0 报告诚实性 → P1 A 类发射缺陷 → P2 pwsh 设施 → P3 对象读类）
   见 verdict §5，**本 session 不激活**。
3. **backlog（跨版本）**：P-1 CJK 变量名展开 / P-2 延迟展开 `!`（`docs/v2.6.0-report.md`）。

---

> **v2.8.1 已发布，项目进入维护模式。** 本文件为流水线终报告。
