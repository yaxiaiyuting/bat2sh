# Session C(lex) 报告（词法层残余 → v1.10.0rc1 pre-release）

> 交付：`docs/session-lex-coldstart.md`（冷启动）、`docs/session-lex-review.md`（审阅与裁定）、
> `docs/session-lex-design.md`（设计/台账/修复草案）、`docs/releases/v1.10.0rc1.md`（发布说明）、
> 本文件；代码 `core/lexical_residuals.py` + `tools/lex/` + 测试。

| 项 | 内容 |
| :--- | :--- |
| **分支名** | `session-lex`（基于 `session-c4`；**已 push**；**未合并 main**） |
| **起点 HEAD** | `68dfbdd325bb93e0c5d7c9222a3d62fb6c2079fb`（= `session-c4` 终点） |
| **代码终点 HEAD** | `bb97f08`（词法层残余额账子系统 + 只读报告） |
| **发布终点 HEAD**（= tag 目标，bump commit） | **`20b1585f58f6daa533270e2f7403101a76a67df9`**（`20b1585`，`chore: bump version to v1.10.0rc1`） |
| **分支终点 HEAD** | `session-lex` 分支 HEAD（bump commit + 其后仅文档 commit；以 `git rev-parse HEAD` 为准） |
| **tag** | `v1.10.0rc1`（PEP 440 pre-release，annotated，打在 `20b1585`） |
| **GitHub Release** | v1.10.0rc1，**pre-release**（`isPrerelease:true`；`Latest` 仍为 v1.9.2） |
| **CI（tag 上）** | ✅ 3.12 / 3.13 / 3.14 **全绿**（`push` run `35225646708`，head = tag commit `20b1585`）；分支 run `35225642925` 亦绿 |
| **本机安装验证** | ✅ 6 项（见 `docs/releases/v1.10.0rc1-verification.md`） |

---

## 一、完成了什么（逐条）

1. **冷启动自检**（`session-lex-coldstart.md`）：前置四项全部通过（含本会话独立复跑
   `pytest -q` = **1360 passed**）；记录 10 份必读文档 + 只读代码锚点；用自己的话复述
   词法层残余与 4 条形态；**前提核对**（两处偏差已披露）；记录回滚点 `68dfbdd`。
2. **自我审阅与裁定**（`session-lex-review.md`）：范围/风险/最小复现/止损/退路/替代方案/客观验收；
   **裁定 = 退回设计文档**（产出词法层残余额账，**零转换改动**）。
3. **只读诊断（实现前完成，纪律 2/9）**：
   - 4 条残余的**真实机制**：044/135 = `_convert_for:2092` 头正则贪婪切分；
     059 = leak 守卫引号/nested-`cmd` 盲区；138 = `_protect_arith_modulo:131` 子串盲区。
   - **wine 语义锚定**：`echo %%m`→`%m`、`echo "for /l %%i …"`→字面 `%i`、
     `for %%i in (a b) do echo [%%i]`→`[a] [b]`。
   - **形态矩阵**：LF-1 触发条件精确为「for 体内联括号组中再出现 `for … do`」。
   - **churn 上界**：LF-1 ≤10 行/4 文件；LF-3 2 行/2 文件；LF-2 真实 leak 文件 8 个（degraded 4）。
4. **词法层残余额账子系统**（`core/lexical_residuals.py`）：第五张只读表（4 条 / 3 机制），
   每条带 `root_cause`（file:line）、`trigger`（最小复现）、`fix_sketch`、`risk`、
   `confidence`、`evidence`、`integrated=False`；`validate_lexical_residuals()`（纪律 7）；
   `classify_percent_token()`（cmd `%%X` 语义参考实现）。
5. **只读报告工具**（`tools/lex/lexical_report.py` + 本目录无 README 依赖）：台账校验 +
   trigger 漂移检测 + 语料复现（台账 ids ⊆ 触发集合；额外 031/047/077/143 已披露）。
6. **测试**：`tests/test_lexical_residuals.py` **11 条**（断言台账语义与 cmd 语义，
   **不编码转换器当前行为**）；pytest **1360 → 1371**。
7. **发布**：bump → `1.10.0rc1`；`release-preflight.sh`；tag 打在 bump commit；
   push 分支 + tag；tag 上 CI；GitHub **pre-release**；本机安装验证。**不进 AUR**。
8. **文档**：coldstart / review / design / report / release notes / PROJECT-OVERVIEW 更新。

---

## 二、未完成什么（逐条 + 原因）

| 未完成项 | 原因 | 归属 |
| :--- | :--- | :--- |
| **LF-1（044/135）for 头切分修复** | 改的是**所有 `for` 行入口正则**（块栈核心，053 同域）；且无文件翻转（净收益 0）→ 纪律 1/10 | v2.0 解析层 |
| **LF-2（059）守卫 quote-aware** | 触 **A1 热路径**（`_expand_vars`）与 Session A 锚点；守卫为**载荷性兜底**，误收窄 → 静默错 | 待守卫重构 |
| **LF-3（138）子串识别** | 138 源行本身退化（wine `set /a` 报错、值不变），「修成什么」语义不明；收益 0 | backlog |
| 撞库式模板 | 形态数十种，C4 已判不可行 | 不采用 |
| 文件翻转 | 4 条均无单设施翻转；诚实报告不硬凑（纪律 13） | v2.0 |
| AUR 同步 | pre-release `pkgver=1.10.0rc1` 被 pacman 视为比 `1.10.0` 旧 | 1.10.0 正式版 |

---

## 三、指标对比（v1.10.0b1 → 本分支）

口径：原始转换口径（`bash_check=False`）+ bwrap 沙箱；rc==0 严格口径；分母 = 语法通过数 = **147**。
仪器：`/tmp/lex/measure.py`（复制自 `/tmp/c4/measure.py`，只改输出目录），
**本会话独立复跑并与 `/tmp/c4/measure.json` 逐项一致**（纪律 9）。

| 指标 | v1.10.0b1 | **session-lex** | 变化 | 判定 |
| :--- | ---: | ---: | ---: | :--- |
| pytest | 1360 | **1371** | **+11** | ✅ 只增不减 |
| 语料 | 151 | 151 | 0 | — |
| 语法通过 | 147/151 | **147/151** | 0 | ✅ 持平 |
| rc==0（原始） | 102 | **102** | 0 | ✅ 持平 |
| **功能完好（严格）** | **16** | **16** | 0 | ✅ **无回退** |
| **degraded** | **86** | **86** | 0 | ✅ 持平 |
| degraded TODO 总数 | 894 | **894** | 0 | ✅ 持平 |
| 崩溃 / 超时 | 0 / 0 | **0 / 0** | 0 | ✅ |
| **转换产物逐字节 diff** | — | **0 文件** | — | ✅ **零转换改动** |
| examples tracked 对漂移 | 0 | **0**（3/3） | 0 | ✅ 零字节 |
| `validate_lexical_residuals()` | 不存在 | **`[]`** | 新增 | ✅ |
| `tools/lex` 复现 | 不存在 | **8/8** | 新增 | ✅ |

### 3.1 为什么「rc==0 提升、degraded 下降」没有发生（重要披露）

任务书 §七验收写「rc==0 提升、degraded 下降」。**本 session 未实现，且判断其在本 scope 内不可达**：

1. **4 条残余均非「单设施阻塞」**：044（7 TODO）、135（443 TODO）、059（2 TODO）、138（7 TODO），
   修掉任一条的 LF 项都**不会翻转文件**（仍有其他 TODO）。
2. **路线图 §3.4 已预判**：1.x 天花板是「小设施单点翻转」，词法层残余属「TODO 少、翻转 0」。
3. **正确做法是「固化为可校验台账 + 修复草案」**：若强行改核心，违反纪律 1 并制造静默错风险。

→ 已按 `session-lex-review.md` §8 把验收**重述为可测标准**（产物零漂移、指标不劣化、
崩溃 0、examples 零漂移、台账有 evidence、新子系统单测覆盖），并全部满足。
**审阅者需裁定是否接受该重述。**

---

## 四、wine harness 通过率对比

| 版本 | wine 黄金对照 |
| :--- | :--- |
| v1.10.0b1 | 6/6 MATCH |
| **session-lex** | **6/6 MATCH**（不下降） |

`pytest tests/test_oracle_wine.py -q` = **8 passed**（61.50s）。

---

## 五、是否触及 053 / A1 已修路径

**否（零转换改动）。**

- 未改 `_prepass` / `_label_line` / `_convert_for` / `_emit_for_f` / `_convert_if` /
  `_pop_block` / `_close_block_line` / `_Block`（053 已修块栈核心）；
- 未改 `_expand_vars` / `env_repl` / `_a1_*` / `_guard_unset_variable_refs`
  （A1 `%VAR%` 冻结热路径）；
- 新增 `core/lexical_residuals.py` 为**纯只读模块**（不 import `batch.py`、不被转换器调用）。

**证据**：151 语料产物与 `/tmp/c4` 基线 **逐字节 0 diff**（bash / rc / todo 三类全 0）；
examples 3/3 零漂移；wine 6/6。

> LF-1/LF-2 的**修复草案本身**会触及上述路径，故本版**刻意不实现**（见 review 裁定）。

---

## 六、合并到 main 时可能冲突的区域

本分支与 `session-c4` 的差异集中在 **3 个新文件 + 1 个新目录 + 文档 + 版本行**，
**未触碰 `batch.py`、`rules.py`、`mappings/`** → 与 Session A 的 4 处 `batch.py` 锚点**无冲突**：

| 文件 | 位置 | 内容 | 冲突风险 |
| :--- | :--- | :--- | :--- |
| `python/bat2sh/core/lexical_residuals.py` | 新文件 | 词法层残余台账 | 无（新文件） |
| `tools/lex/lexical_report.py` | 新目录 | 只读报告 | 无 |
| `tests/test_lexical_residuals.py` | 新文件 | 11 条测试 | 无 |
| `pyproject.toml` / `python/bat2sh/__init__.py` | `version` 行 | `1.10.0b1 → 1.10.0rc1` | 低（每位 bump 都撞，按惯例后合并者改） |
| `docs/PROJECT-OVERVIEW.md` | 版本/测试数/§5.8/§9 | 词法层残余说明 | 低（文档，逐段合并） |
| `python/bat2sh/core/batch.py` | **未改动** | — | **无冲突**（Session A 锚点 `:14` / `:1097-1114` / `:2630-2643` / `:2772-2782` 不受影响） |

---

## 七、v1.10.0 正式版合并建议（三分支顺序）

三个分支为**累积关系**（`main → session-b1b2 → session-c4 → session-lex`），建议：

```text
1) git checkout main
2) git merge --no-ff session-b1b2   # v1.10.0a1：B1 名称映射 + B2 输出契约
3) git merge --no-ff session-c4     # v1.10.0b1：C4 goto 控制流台账
4) git merge --no-ff session-lex    # v1.10.0rc1：词法层残余额账
5) bump → 1.10.0 正式版 + 同步 PKGBUILD/.SRCINFO + tag v1.10.0 + CI + GitHub Release + AUR
```

- 每个 merge 后跑 `pytest` + 151 语料 + examples 零漂移 + wine 6/6（发布门槛）。
- 冲突热点：`pyproject.toml`/`__init__.py` 的 `version` 行、`.github/workflows/test.yml`
  （C4 改过 `on:`）、`docs/PROJECT-OVERVIEW.md`（文档逐段）。三者均**低风险**。
- `batch.py` 在三个分支中**均未被改动**（B1/B2 的 4 处锚点是**新增代码**，C4/lex 未动），
  故累积合并**不应产生 `batch.py` 文本冲突**。

---

## 八、自我审阅结论 / 止损点

| 项 | 结论 |
| :--- | :--- |
| 裁定 | **退回设计文档**（产出词法层残余额账 + 修复草案；**不实现转换改动**） |
| 是否触及 053/A1 | 否（零转换改动） |
| 退路 | HEAD 回滚点 `68dfbdd` |
| 本版性质 | 研究固化型 rc（与 v1.10.0b1 同范式） |

| 闸门（任务书 §十） | 是否触发 |
| :--- | :--- |
| 触及 053 / A1 已修路径且无清晰方案 | **是 → 停**（LF-2 双红线；LF-1 属同域核心）→ 不实现，写报告 |
| 改动 > 5 模块 | **未触发**（0 转换模块；新增只读模块 + 工具 + 测试） |
| pytest 失败 | **未触发**（1360→1371，0 failed） |
| 转换产物字节变化 | **未触发**（0 文件） |
| strict 由 16 下降 / degraded 增加 | **未触发**（=16 / =86 / =894） |
| wine harness 下降 | **未触发**（6/6） |
| examples 漂移 | **未触发**（3/3 零字节） |
| HEAD 并发变化 | **未触发**（仅本会话 commit 推进） |
| tag 后 CI 红 | **未触发**（`35225646708` 3.12/3.13/3.14 全绿；未 force-push） |

---

## 九、给审阅者的建议

| # | 建议 | 理由 |
| :--- | :--- | :--- |
| 1 | **接受「退回设计文档」裁定** | 4 条中 ≥2 条无「低风险且指标为正」方案；LF-2 触 A1 热路径，LF-1 触 for 头核心 |
| 2 | **接受验收标准重述** | 任务书「rc==0 提升、degraded 下降」与路线图 ROI 口径冲突且不可达（§3.1） |
| 3 | **确认任务书 059/138 文件名更正** | 仪器编号 059=`打开快捷方式指向的目录.bat`、138=`获取U盘盘符和可用容量.bat` |
| 4 | **认可 v1.10.0rc1 作为 rc** | 零转换改动的 rc；三分支合并后转正 |
| 5 | **LF-1 排入 v2.0**（随 CFG/解析层） | 修复草案已备（design §3.1），本版不动核心 |
