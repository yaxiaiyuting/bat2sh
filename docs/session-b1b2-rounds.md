# bat2sh session B1/B2 多轮循环记录（逐 commit 指标）

> 口径：**原始转换口径**（`ConvertSettings(bash_check=False)`）+ bwrap 沙箱；
> `rc==0` 严格口径 = 跑通 **且** 产物不含真实 `# TODO` 标记（`report.todo_count == 0`
> 且无 marker 行，**排除固定脚本头**）。
> 语料：`~/下载/非常批处理/`（151 个 `.bat`/`.cmd`）。
> 仪器：`/tmp/b1b2/measure.py`（本 session 修好 marker 头行缺陷后，已逐项复现 v1.9.2 基线）。
> **rc==0 分母 = 语法通过数 = 147**（任务书所写「145 分母」为 v1.8.3 旧值，见冷启动 §5.2）。

---

## 指标总览（逐 commit）

| 序 | commit | 内容 | pytest | 语法 | rc==0 | **功能完好** | **degraded** | degraded TODO | 崩溃 | examples |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 0 | — | **v1.9.2 基线**（起点 `7048e6c`） | 1262 | 147/151 | 102 | **16** | **86** | 894 | 0 | ✅ |
| 1 | `51f52d2` | 文档：冷启动自检 + 审阅裁定 | 1262 | 147/151 | 102 | 16 | 86 | 894 | 0 | ✅ |
| 2 | `28973aa` | B1 名称映射**框架**（空表 + 校验器） | **1292** | 147/151 | 102 | 16 | 86 | 894 | 0 | ✅ |
| 3 | `9cdfd5d` | B1 **首批映射** + env_repl 集成 | **1312** | 147/151 | 102 | 16 | 86 | 894 | 0 | ✅ |
| 4 | `34add7e` | B2 输出契约**框架** + 交叉强制 | **1335** | 147/151 | 102 | 16 | 86 | 894 | 0 | ✅ |
| 5 | `84d7e0a` | B2 **首批契约消费**（裸 dxdiag/perfmon） | **1344** | 147/151 | 102 | 16 | 86 | 894 | 0 | ✅ |

> **核心结论**：全部 headline 指标**零变化、零回归**。这与路线图 §3.4 的预期一致：
> `path` 设施 16 TODO / 4 文件 / **0 单设施翻转**；`ipconfig`/`dxdiag`/`perfmon` 命中的
> 文件已被 `goto`/终态/语法失败阻塞 → **B1/B2 是可预期翻转 0 的设施建设**，
> 其价值在**子系统与诚实化**，不在文件翻转（详见 `docs/session-b1b2-report.md`）。
>
> `degraded TODO` 总数 894：`031` +1（syntax-fail，不计入）、`077` +2（rc≠0，不计入），
> 故 degraded 集合内总数不变。

---

## Commit 2（`28973aa`）B1 框架

**范围**：新增 `python/bat2sh/mappings/windows_names.py` + `mappings/__init__.py` 导出
+ `tests/test_mappings_windows_names.py`（30 条）。`WINDOWS_NAMES` 为空表（框架提交）。

**schema**：`NameMapping(win, kind, linux, form, confidence, target_exists, evidence,
integrated, notes)`；`kind ∈ {env_var, path_root, service}`；`path_root` 的 `win` 限定为
`drive`/`unc` 子类伪名（可机检）。

**降级策略**：查不到 → `None`；`form=none` → 调用方降级为诚实 TODO；
`integrated=False` → 仅登记不驱动转换（`notes` 必须写明 `backlog`）。

## Commit 3（`9cdfd5d`）B1 首批映射 + 集成

| 条目 | kind | 处置 | evidence |
| :--- | :--- | :--- | :--- |
| `ProgramFiles` | env_var | `form=none` → 行级诚实 TODO（原为静默 `${ProgramFiles:-}` 空串） | `corpus/史上最牛X…bat:9933` |
| `AllUsersProfile` | env_var | → `/usr/share`（与 `BATCH_ENV_MAP["PROGRAMDATA"]` 一致） | `corpus/快速清理垃圾文件安装修改版/快速清理垃圾文件.bat:15` |
| `drive`（盘符） | path_root | **仅登记**（`integrated=False`） | `corpus/注册表/导出注册表的键值2.bat:1` |
| `unc`（共享） | path_root | **仅登记**（`integrated=False`） | `corpus/注册表/设注册表某个键的键值为变量2.bat:3` |

**集成 2 处（均在 `core/batch.py`）**：

1. `_convert_simple_no_pipe`：Windows 专有 `env_var`（`form=none`）→ 行级诚实 TODO。
   与 `_expand_vars` **同序先掩 `%%` 再扫**（`%%ProgramFiles%%` 不被误判）；
   脚本自赋值的同名变量走 `_assigned_by_upper`，按用户变量处理。
2. `env_repl`：未在 `BATCH_ENV_MAP` 中的映射型 `env_var` → Linux 值 + 警告（不遮蔽既有映射）。

**churn 实测（决定「盘符/UNC 不集成」）**：

| 模式 | 命中文件 | 命中次数 | 其中当前功能完好 | 结论 |
| :--- | ---: | ---: | ---: | :--- |
| `X:/`（盘符） | 35 | 385 | **6** | ❌ 诚实 TODO 化净损 6 strict → backlog |
| `\\host\share`（UNC） | 4 | 19 | 1 | ❌ 至少 −1 strict → backlog |
| `${ProgramFiles:-}`（静默空串） | 2 | 5 | **0** | ✅ 可集成 |

**151 语料产物逐文件 diff（vs v1.9.2）**：仅 **3 个文件**变化，全部预期：

| 文件 | 变化 | rc | 说明 |
| :--- | :--- | :--- | :--- |
| `031 史上最牛X…bat` | `${ProgramFiles:-}` → TODO | syntax-fail | 不计入 rc/degraded |
| `058 快速清理垃圾文件.bat` | `%ALLUSERSPROFILE%` → `/usr/share` | 0（degraded） | mapping 生效，TODO 数不变 |
| `077 文件备份器V2.3修改版2.cmd` | 3 处 → TODO（+2 TODO） | 1 | 本非 rc==0，文件级指标不变 |

**已知限制（主动披露）**：`if`/`for` **头部条件**中的 `%ProgramFiles%` 不转为 TODO——
改头部会触碰块栈配平（属硬止损域）。语料中此类仅 **5 行**、全部在 `077`（已 rc≠0）
→ **零指标影响**；已用测试 `test_if_header_condition_is_a_documented_limitation` 锁定该限制。

## Commit 4（`34add7e`）B2 框架

**范围**：`python/bat2sh/mappings/output_contracts.py` + 导出 + `tests/test_mappings_output_contracts.py`（23 条）。

**升级点**：`ToolMapping.output_contract` 从「`notes` 含『输出格式』四字」的**装饰性标记**
升级为**结构化可执行契约** `OutputContract(command, linux_command, shape, keywords,
evidence, integrated, notes)`，并加**交叉强制**：`output_contract=true` 的命令**必须**有契约记录
（当前 `ping` / `help`，已补登记）。

**首批契约 5 条**：`ipconfig`（`shape=differs`，中文关键词与既有 `_FINDSTR_CJK_MAP` 由测试锁定）、
`dxdiag`/`perfmon`（`shape=none`，可消费）、`ping`/`help`（仅登记，backlog）。

**1.x 红线**：不做解析级输出适配（路线图 §1.B）；适配留 2.x。
`085 显示自己的IP.bat`（唯一可能翻转的 ipconfig 解析文件）**本版不翻转**。

## Commit 5（`84d7e0a`）B2 首批契约消费

**集成 1 处**（`core/batch.py` 派发链 `elif`）：契约 `shape=none` 且 `integrated` → 结构化诚实 TODO。
裸 `dxdiag` / `perfmon` 由「泛化 warn + 原样透传 → command not found」转为诚实 TODO。
**只接管裸命令**：`dxdiag.exe`/`perfmon.exe` 仍走既有 exe 分支（消息不变）；
`ipconfig`/`ping`/`help`/`for /f` 英文标签/中文映射全部不变（有测试锁定）。

---

## 六问之外的两项专项验证

| 项 | 结果 |
| :--- | :--- |
| 仪器先验证（纪律 9） | 冷启动期修复 marker 头行缺陷；修复后逐项复现 v1.9.2：147/102/16/86 ✅ |
| 不发明映射（纪律 7） | 新增 4 条名称映射 + 5 条契约，**每条** `evidence` 指向真实语料行；`validate_name_mappings()==[]`、`validate_contracts()==[]` |
| 既有映射零改动 | `windows_tools.py` 未改；`BATCH_ENV_MAP` 未改（新表只登记未映射的名字，测试守护不遮蔽） |
| 块栈/词法层 | **未触碰**（止损未触发） |
| examples | tracked 对 3/3 零字节漂移（未刷新） |
| release-preflight | 通过（类 CI 空 HOME：1334 passed / 10 skipped） |
