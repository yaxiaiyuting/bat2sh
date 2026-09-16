# Session B1/B2 报告（B1 名称映射 + B2 输出契约 → v1.10.0a1 pre-release）

> 交付：`docs/session-b1b2-coldstart.md`（冷启动）、`docs/session-b1b2-review.md`（审阅与裁定）、
> `docs/session-b1b2-rounds.md`（逐 commit 指标）、`docs/releases/v1.10.0a1.md`（发布说明）、本文件。

| 项 | 内容 |
| :--- | :--- |
| **分支名** | `session-b1b2`（已 push；未合并 main） |
| **起点 HEAD** | `7048e6c0b59d75b5a28c856c6f8072f03197159a`（= v1.9.2 发布后 main） |
| **代码终点 HEAD**（B1/B2 实现完成） | `84d7e0a`（B2 首批契约消费） |
| **发布终点 HEAD**（= tag 目标，bump commit） | **`90af605`**（`chore: bump version to v1.10.0a1`） |
| **分支终点 HEAD**（Session B 起点） | 分支 `session-b1b2` 的 HEAD：**`90af605` + 其后追加的文档 commit**（`02c1bbb` docs、`v1.10.0a1-verification.md` 等，**无代码改动**）；Session B 以 `git rev-parse HEAD` 为准 |
| **tag** | `v1.10.0a1`（PEP 440 pre-release，annotated，打在 `90af605`） |
| **GitHub Release** | v1.10.0a1，**pre-release（`isPrerelease:true`；`Latest` 仍为 v1.9.2）** |
| **CI（tag 上）** | ✅ 3.12 / 3.13 / 3.14 **全绿**（PR #3 `pull_request` run `35127369625`，head = tag commit） |

---

## 一、完成了什么（逐条）

1. **冷启动自检**（`session-b1b2-coldstart.md`）：前置四项核对通过；记录 6 份必读文档 +
   只读代码锚点；用自己的话复述 B1/B2 与路线图假设；**前提核对**（前提 1/2/3/4/6 成立，
   前提 5 冲突 → 转裁定）。
2. **自我审阅与裁定**（`session-b1b2-review.md`）：范围/风险/最小复现/止损点/退路/替代方案/
   客观验收标准；**裁定 = 收窄后实现**（方案 E），并显式披露三处收窄。
3. **B1 名称映射子系统**（`mappings/windows_names.py`）：
   - 第三张结构化表（命令表 / 注册表键表 / **名称表**），`kind ∈ {env_var, path_root, service}`；
   - `NameMapping` schema + `validate_name_mappings()`（evidence 必填、置信度光谱、
     D 档不得硬凑、`form=none` 须注「无对应物」、`target_exists=no` 须注「目标物不存在」、
     `integrated=False` 须注 backlog、service 须指明 systemd unit、`(kind, win)` 去重、
     `path_root` 伪名机检）；
   - 降级策略：`form=none` → 诚实 TODO；`integrated=False` → 仅登记。
4. **B1 首批映射（C3 路径/环境）**：`ProgramFiles`（→ 诚实 TODO，修复静默
   `${ProgramFiles:-}` 空串）、`AllUsersProfile`（→ `/usr/share`，与既有 `PROGRAMDATA`
   一致）、`drive`/`unc`（**仅登记**，churn 实测 35 文件/6 strict → backlog）。
   集成 2 处（`_convert_simple_no_pipe` 行级 TODO、`env_repl` 映射值 + 警告）。
5. **B2 输出契约子系统**（`mappings/output_contracts.py`）：把
   `ToolMapping.output_contract` 从装饰性标记升级为结构化契约 + **交叉强制**
   （`output_contract=true` 必须有契约记录）；首批 5 条
   （`ipconfig`/`dxdiag`/`perfmon`/`ping`/`help`），每条带 `evidence`。
6. **B2 首批契约消费**：裸 `dxdiag`/`perfmon` 由「泛化 warn + 透传 → command not found」
   改为结构化诚实 TODO（只接管裸命令，`.exe` 与 `ipconfig`/`ping`/`help`/`for /f` 行为不变）。
7. **测试**：新增 62 条（30 框架 + 9 首批表 + 23 契约 + 9 集成 − 重复计数见 rounds 表），
   pytest **1262 → 1344**；每 commit 全量回归。
8. **发布**：版本 bump → `1.10.0a1`（commit `90af605`）；`release-preflight.sh` 通过；
   tag `v1.10.0a1` 打在 bump commit；push 分支 + tag；**tag 上 CI 3.12/3.13/3.14 全绿**；
   GitHub **pre-release**（`Latest` 仍为 v1.9.2）；本机安装验证（`install.sh` → 启动器
   `--version` = 1.10.0a1 + 5 项实跑），见 `docs/releases/v1.10.0a1-verification.md`。
9. **CI 入口披露**：仓库 CI 仅触发 `push main` 与 `pull_request`（分支/tag push 不触发），
   故开了**草稿 PR #3**（`session-b1b2` → main，**未合并**）作为 CI 与审阅入口；
   PR head = tag commit `90af605`。若不需要可关闭，不影响 tag/release。

---

## 二、未完成什么（逐条 + 原因）

| 未完成项 | 原因 | 归属 |
| :--- | :--- | :--- |
| **B2 解析级输出适配**（如把 `for /f` 解析 `ipconfig` 输出真正译对，翻转 `085`） | 路线图 §1.B **1.x 红线**：不做解析级适配（v1.8.3 流程感知改法 26/151 churn + examples 漂移被否）；且 B2 风险 = **高** | 2.x |
| **B1 盘符 / UNC 的转换集成** | churn 实测 35 文件、其中 **6 个当前功能完好** → 诚实 TODO 化**净损 6 strict**，超出首批边界 | v1.9.4/v1.9.5 |
| **`sc→systemctl`（C7）与服务名→systemd unit** | 路线图 r2 已后移 v2.0（宿主 `135 系统优化.bat` 被 goto 阻塞，1.x 翻转 0）；任务书亦确认不含 | v2.0 |
| `%ProgramFiles(x86)%` 等无 corpus evidence 的别名 | **纪律 7**：缺 evidence 拒绝，不得硬凑（语料 0 次出现） | 待语料/文档 evidence |
| `if`/`for` **头部条件**中的 `%ProgramFiles%` → TODO | 改头部会触碰**块栈配平**（硬止损域）；语料中仅 5 行且全在已 rc≠0 的 `077` | 2.x（随解析层） |
| AUR 同步 | `pkgver=1.10.0a1` 会被 pacman 视为比 `1.10.0` 旧；**pre-release 不进 AUR 主分支**（任务书 §8.4） | 1.10.0 正式版 |
| `145 分母` 口径 | 任务书口径有误（v1.8.3 旧值）；本轮按真实分母 **147** 记录并披露 | — |

---

## 三、指标对比（v1.9.2 → 本分支）

口径：原始转换口径（`bash_check=False`）+ bwrap 沙箱；rc==0 严格口径（跑通 且 功能完好）。
**rc==0 分母 = 语法通过数 = 147**（非任务书的 145）。

| 指标 | v1.9.2 | session-b1b2 | 变化 | 判定 |
| :--- | ---: | ---: | ---: | :--- |
| pytest | 1262 | **1344** | **+82** | ✅ 只增不减 |
| 语料 | 151 | 151 | 0 | — |
| 语法通过 | 147/151 | **147/151** | 0 | ✅ 持平 |
| rc==0（原始） | 102 | **102** | 0 | ✅ 无回退 |
| rc≠0 | 45 | 45 | 0 | ✅ |
| **功能完好（严格）** | **16** | **16** | 0 | ✅ **无回退**（止损线 ≥16 未触发） |
| **degraded** | **86** | **86** | 0 | ✅ |
| degraded TODO 总数 | 894（文档记 895） | **894** | 0 | ✅ 一致（同一只仪器） |
| 崩溃 / 超时 | 0 / 0 | **0 / 0** | 0 | ✅ |
| examples tracked 对漂移 | 0 | **0**（3/3 对） | 0 | ✅ 零字节漂移 |
| `validate_mappings()` | `[]` | `[]` | 0 | ✅ |
| `validate_name_mappings()` | 不存在 | `[]` | 新增 | ✅ |
| `validate_contracts()` | 不存在 | `[]` | 新增 | ✅ |

### 3.1 为什么「rc==0 提升、degraded 下降」没有发生（重要披露）

任务书 §七的验收写「**rc==0 提升、degraded 下降**」。**本 session 未能实现，且判断其在本 scope 内不可达**：

1. **路线图 §3.4 已预判翻转 0**：`path` 设施 16 TODO / 4 文件 / **0 单设施翻转**；
   `sc` 0 翻转；B1/B2 都不是「文件翻转批」（§3.1 明记「sc/errorlevel/path = TODO 多但文件翻转 0」）。
2. **命中文件已被阻塞**：`ipconfig` 命中 `085`（degraded，其唯一 TODO 正是需要解析级适配的那条）、
   `dxdiag/perfmon` 命中 `031`（syntax-fail）与 `135`/`系统优化.bat`（439 TODO、被 goto 阻塞）。
3. **B1/B2 的正确做法是「诚实化」而非「翻转」**：把**静默错**（`${ProgramFiles:-}` 空串、
   裸 `dxdiag` 透传 → command not found）改成**诚实 TODO**；这在文件级指标上**中性**，
   在 honesty 上是净改进。若把盘符/UNC 也诚实 TODO 化，反而会让 **strict 16 → 10**（§review §2.2）。

→ 已按 `session-b1b2-review.md` §6 把验收**重述为可测标准**（strict/rc==0 不回退、
degraded 变化可解释、崩溃 0、examples 零漂移、映射有 evidence、新子系统单测覆盖）。
**已在本报告的审阅建议中提示用户裁定是否接受该重述。**

---

## 四、自我审阅结论

| 项 | 结论 |
| :--- | :--- |
| 裁定 | **收窄后实现**（方案 E；非「退回设计文档」） |
| 收窄 1 | B2 不做解析级输出适配（1.x 红线）→ 只做契约框架 + 登记 + 交叉强制 + 裸命令诚实化 |
| 收窄 2 | B1 不集成盘符/UNC（净损 6 strict）→ 仅登记 + backlog |
| 收窄 3 | B1 env_var 只新增未在 `BATCH_ENV_MAP` 的名字（不遮蔽既有映射，零输出漂移） |
| 是否退回设计文档 | **否**（收窄后风险可控、止损清晰、有退路；且 B1 本就是路线图 1.x 项目） |
| B1/B2 是否一起做 | **一起做**（独立、共享校验范式、可独立回滚） |

## 五、止损点

| 闸门 | 是否触发 |
| :--- | :--- |
| strict（功能完好）由 16 下降 | **未触发**（16 全程保持） |
| degraded TODO 总数 > +20 | **未触发**（0 变化） |
| pytest 出现失败 | **未触发**（1262→1344，0 failed） |
| examples tracked 对漂移 | **未触发**（3/3 零字节） |
| 改动模块 > 5 | **未触发**（2 个新模块 + 3 个既有文件：`batch.py`、`mappings/__init__.py`、测试） |
| 触及块栈核心 | **未触发**（未改块栈/词法层） |
| 映射缺 evidence | **未触发**（4 名称 + 5 契约全部有 evidence） |
| HEAD 并发变化 | **未触发**（HEAD 只被本 session 自己的 commit 推进，无他人写入） |
| tag 后 CI 红 | **未触发**（3.12/3.13/3.14 全绿；未 force-push） |

---

## 六、合并到 main 时可能冲突的区域（给 Session B 参考）

`session-b1b2` 与 main 的差异集中在 **3 个文件 + 1 个新目录**。Session B（C4 goto/控制流）
必然大改 `core/batch.py`，故给出**精确锚点**：

| 文件 | 位置（本分支行号） | 内容 | 冲突风险 |
| :--- | :--- | :--- | :--- |
| `python/bat2sh/core/batch.py` | `:14` | import 行：`from ..mappings import output_contracts, windows_names, windows_tools` | 低（Session B 若也改 imports 可能有文本冲突） |
| `python/bat2sh/core/batch.py` | `:1097-1114`（`env_repl` 内） | 新增 `windows_names.env_mapping_for` 分支（在 `BATCH_ENV_MAP` 之后、user-var 兜底之前） | **低–中**（`env_repl` 是 A1/C1 热点） |
| `python/bat2sh/core/batch.py` | `:2630-2643`（`_convert_simple_no_pipe` 内） | `unmappable_env_names_in` 行级诚实 TODO 预扫 | **中**（该函数是 A-2/A-3 词法层热点） |
| `python/bat2sh/core/batch.py` | `:2772-2782`（派发链） | `elif contract ... shape == "none"` → 诚实 TODO（在 `windows_tools.mapping_for` 之后、`BATCH_TODO_COMMANDS` 之前） | 低 |
| `python/bat2sh/core/batch.py` | 未改动但相关 | `_convert_goto`（诚实 TODO）、`_convert_if`/`_convert_for`、`_Block` | **Session B 主战场**；本分支**未触碰**，无冲突，但 import/行号会漂移 |
| `python/bat2sh/mappings/__init__.py` | 全文 | 新增 `windows_names` / `output_contracts` 导出 | 低 |
| `python/bat2sh/mappings/windows_names.py` | 新文件 | B1 名称表 | 无（新文件） |
| `python/bat2sh/mappings/output_contracts.py` | 新文件 | B2 契约表 | 无（新文件） |
| `tests/test_mappings_windows_names.py` / `test_mappings_output_contracts.py` / `test_batch_windows_names.py` / `test_batch_output_contracts.py` | 新文件 | 62 条新测试 | 无 |
| `python/bat2sh/mappings/windows_tools.py` | **未改动** | — | 无 |
| `python/bat2sh/core/rules.py` | **未改动** | — | 无（Session B 会改 `BATCH_HANDLER_MAP`） |

**建议**：Session B 从 `session-b1b2` 终点 HEAD 开 `session-c4`（**累积模式**），
先 `git merge origin/main` 或直接以本分支为基线；合并 main 时优先处理 `batch.py` 的
**import 行**与上述 3 个 anchor 的文本冲突（`git rerere` 或手工均可在 5 分钟内解决）。

---

## 七、给审阅者的建议

| # | 建议 | 理由 |
| :--- | :--- | :--- |
| 1 | **接受「收窄后实现」的裁定** | B2 的 1.x 原计划是「只做诚实 TODO/警告」（路线图 §1.B）；本版严格照此执行，并额外交付了契约框架 |
| 2 | **接受验收标准的重述** | 任务书「rc==0 提升、degraded 下降」与路线图 ROI 口径冲突且不可达（§三.1）；重述后的标准全部满足 |
| 3 | **确认 v1.10.0a1 的版本号** | 路线图 §3.1 对 A1 修复提出 v1.10.0 命名待裁定；本 session 的 B1/B2 是**新子系统**（触及映射层而非核心变量展开），按 semver 更宜作为 1.10.0 的 alpha |
| 4 | **确认 `ProgramFiles` 的诚实 TODO 方向** | 与「不发明映射」一致；若坚持要映射（如 `/usr`），需提供文档 evidence 并接受「看似对、实际错」风险 |
| 5 | **下一版（Session B / C4）的建议顺序** | C4（goto/控制流）是单点最大收益（~250 TODO、16 文件阻塞）也是最高风险；建议先做**只读** CFG/回归量化，再分阶段闸门 |
| 6 | 是否继续 B（C4）/ 调整 / 重做 | **建议继续 C4（Session B）**；B1 的盘符/UNC 集成与 B2 的解析级适配随后续版本评估 |
| 7 | **是否需要 `bat2sh-pre` AUR 包** | 本 session 跳过 AUR（§二）；若需要预发布包需另立 `bat2sh-pre` |

---

## 八、Session B 的起点

| 项 | 值 |
| :--- | :--- |
| **Session B 起点 HEAD** | `session-b1b2` 分支 HEAD（= 发布终点 `90af605` + 其后**仅文档** commit；以 `git rev-parse HEAD` 为准） |
| 建议分支名 | `session-c4`（从本 session 终点 HEAD 累积开分支） |
| 发布基线（可直接引用） | tag `v1.10.0a1` / commit `90af605`（CI 全绿） |
| 本 session 的输入 | 本报告 §六「可能冲突区域」+ §七「建议」 |
| 前置设施已就位 | `validate_name_mappings()` / `validate_contracts()`；B3/B4 wine 黄金对照（6/6）；A1 冻结语义 |
