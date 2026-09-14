# 管道模式挖掘报告（v1.3 阶段 2 · 只读诊断）

> 语料：examples/ 与手头真实脚本 · 方法：真实管道行提取 → 归一化 → 频次统计 → 对照当前转换器行为
> 本轮不改任何代码、不建库；本文仅为候选清单与建议。

## 1. 语料规模报告

| 文件 | 行数 | 真管道行 |
|---|---|---|
| examples/stress_test.bat | 572 | 16 |
| 下载/deepseek_bat_20260913_895203.bat | 572 | 16 |
| examples/deepseek_bat_20260913_faa286.bat | 581 | 4 |
| examples/backup.ps1 | 28 | 1 |
| examples/deploy.bat | 23 | 0 |
| examples/hello.bat | 13 | 0 |
| examples/cleanup.ps1 | 21 | 0 |
| **合计** | **1817** | **37** |

- 去重后唯一管道行：**21 条**；`stress_test.bat` 与 `895203.bat` 为**近重复孪生**（大部分 `[2]` 频次来自两文件重复，而非真实复用）
- 剔除误报（`^|` 转义字面量、`||` 逻辑或、引号内 `|`）后统计
- **结论先行：语料偏小**（有效独立脚本 ≈ 4 个、唯一形态 21 条、绝大多数是 torture-test 构造，缺少真实生产脚本的多样性）。足以支撑"第一批段级映射"，不足以支撑完整模式库设计（详见第 6 节）

## 2. 模式频次表（21 条唯一形态）

| # | 归一化模式 | 次数 | 当前处理 | 建议档位 |
|---|---|---|---|---|
| 1 | `ipconfig \| findstr /i STR` | 2 | AUTO（WARN：输出格式差异） | B（改进命令映射） |
| 2 | `netstat -an \| findstr STR \| findstr STR >nul && echo … \|\| echo …` | 2 | TODO（多级+重定向） | B（含 idiom） |
| 3 | `sc query X 2>nul \| findstr STR` | 2 | TODO（sc 未知命令） | B |
| 4 | `tasklist /fi STR 2>nul \| findstr /i STR` | 2 | TODO | B/C |
| 5 | `echo … & echo … & echo … \| findstr STR` | 2 | TODO（`&` 优先级歧义） | D（保持 TODO） |
| 6 | `dir nonexistent_file 2>&1 \| findstr /i STR` | 2 | TODO（2>&1 + 管道） | B（放开 2>&1） |
| 7 | `certutil -hashfile FILE MD5 2>nul \| findstr /v STR` | 2 | TODO | A（直译 md5sum） |
| 8 | `sort FILE \| more +N` | 2 | WARN（语义存疑） | 反例（待澄清） |
| 9 | `systeminfo \| findstr /i STR 2>nul` | 2 | TODO | B/C |
| 10 | `driverquery \| findstr /i STR \| findstr /i STR 2>nul \| findstr /n STR \| findstr STR` | 2 | TODO | 反例主体 + 段级 idiom |
| 11 | `tasklist /svc \| findstr /i STR \| findstr /n STR \| findstr STR` | 2 | TODO | 段级 idiom + B |
| 12 | `net user 2>nul \| findstr /v STR \| findstr /n STR \| findstr STR` | 2 | TODO | 段级 idiom + C |
| 13 | `net start 2>nul \| findstr /n STR \| findstr STR` | 2 | TODO | 段级 idiom + C |
| 14 | `whoami /all 2>nul \| findstr /i STR \| findstr /n STR \| findstr STR` | 2 | TODO | 段级 idiom + B |
| 15 | `echo hello \| findstr STR > FILE` | 2 | TODO（管道+重定向） | A（放开组合） |
| 16 | `echo 错误合并: … 2>&1 \| findstr /i STR`（echo 文本管道） | 2 | TODO | B（同 #15 的组合放开） |
| 17 | `echo a b c d e \| findstr STR ×5` | 1 | TODO | 反例（>4 级收益低） |
| 18 | `dir 2>&1 \| findstr /i STR > FILE` | 1 | TODO | B（同 #6/#15） |
| 19 | `%CMD% \| findstr STR` | 1 | AUTO + WARN（未知命令） | D（动态命令保持） |
| 20 | `type FILE \| sort \| more` | 1 | TODO | B（`sort F \| less`） |
| 21 | `New-Item … \| Out-Null`（PS） | 1 | PS 侧管道 | B（PS：`mkdir -p` 丢弃输出） |

**段级签名频次**（管道各段命令 + 开关，去引号后统计）：
`findstr` 26（其中 `/i` 19、`/n` 10、`/v` 4）· `echo` 9 · `net` 4 · `dir` 3 · `sort` 3 · `more` 3 · 其余命令各 1–2。
→ **findstr 家族占绝对主导，是本批次最有价值的目标**；`/n "^"` + `^[1-5]:` 的"取前 N 行"idiom 出现 5 次（#10–14）。

## 3. 建议第一批入库清单（16 条）

> 档位：A 确定 / B 惯用法 / C 语义接近 / D 无法可靠。模板中的 `X` 为上游管道输入。

### 已实现、建议固化为文档与测试基线（4 条）

| # | 归一化模式 | 建议模板 | 语义说明 + 差异警告 | 档位 |
|---|---|---|---|---|
| 1 | `findstr /i STR` | `grep -i STR` | 大小写不敏感匹配；正则方言差异保留警告 | A |
| 2 | `findstr /v STR` | `grep -v STR` | 反选；同上 | A |
| 3 | `findstr /c:"STR"`（无 /r） | `grep -F "STR"` | 字面量匹配 | A |
| 4 | `findstr /r …` | `grep -E …` | 扩展正则（已修复 /r 优先于 /c:） | A |

### 段级/结构映射（6 条）

| # | 归一化模式 | 建议模板 | 语义说明 + 差异警告 | 档位 |
|---|---|---|---|---|
| 5 | `findstr /n "^"` | `grep -n ""` | 给所有行编号（`^` 全行正则的惯用法） | B |
| 6 | `X \| findstr /n "^" \| findstr "^[1-N]:"` | `X \| head -n N` | **"取前 N 行"惯用法**（N≤9 时可靠；≥10 的前缀正则写法需另处理） | B |
| 7 | `X \| findstr A \| findstr B`（纯过滤链 ≤3 段） | `X \| grep A \| grep B` | 放宽"两段以上即 TODO"到"全程纯 findstr/grep 过滤链可自动"；输出格式差异警告保留 | B |
| 8 | `X 2>&1 \| findstr PAT` | `X 2>&1 \| grep PAT` | 允许 `2>&1` 参与的两段管道（当前一律 TODO） | B |
| 9 | `X \| findstr PAT > FILE` | `X \| grep PAT > FILE` | 允许"管道 + 末尾重定向"组合（当前一律 TODO） | A |
| 10 | `X \| findstr PAT \|\| true` 后缀策略 | 维持并文档化 | 过滤语义：未匹配不终止（已实现，防回归） | A |

### 命令级 idiom（6 条，替换整条管道）

| # | 归一化模式 | 建议模板 | 语义说明 + 差异警告 | 档位 |
|---|---|---|---|---|
| 11 | `certutil -hashfile FILE MD5 \| findstr /v STR` | `md5sum FILE` | **直译**：过滤链只是去掉 CertUtil 头，md5sum 无需过滤；输出格式不同 | A |
| 12 | `netstat -an \| findstr "LISTENING"` | `ss -ltn` | 监听端口查询；列名/状态词不同（LISTENING↔LISTEN） | B |
| 13 | `sc query X \| findstr "STATE"` | `systemctl is-active X` | 服务状态；输出词汇完全不同（STATE: 4 RUNNING ↔ active） | B |
| 14 | `tasklist \| findstr /i NAME` / `tasklist /fi …` | `pgrep -a NAME`（`/fi` → `pgrep -f`） | 进程查询；`/fi` 过滤语法无对应，需改写 | B/C |
| 15 | `ipconfig \| findstr "IPv4…"` | `ip -brief addr` | 取 IP；字段名/结构不同（当前 `ip addr \| grep` 可保留但建议换 `-brief`） | B |
| 16 | `whoami /all \| findstr …` | `id` | 当前用户与组；字段结构完全不同 | B |

**可选补充（视优先级）**：`systeminfo \| findstr "OS…"` → `uname -a` + `cat /etc/os-release`（C）；`net start \| …` → `systemctl list-units --type=service --state=running`（C）；`net user \| …` → `getent passwd`（C）；`type F \| sort \| more` → `sort F | less`（B）。

## 4. 反例清单（看着像但不应入库）

| 模式 | 原因 |
|---|---|
| `echo … & echo … & echo … \| findstr STR` | cmd 中管道优先级高于 `&`：实际只有最后一段参与管道；语义易误读，保持 TODO |
| `sort FILE \| more +N` | `+N` 语义待澄清（cmd 文档"从第 N 行开始显示" vs 现转换器注释"跳过首行"不一致）；入库前需单独确权 |
| `driverquery \| … \| findstr ^[1-5]:`（整链） | Windows 专有数据源（驱动列表），`lsmod` 语义不同；只应拆出段级 idiom（#6），不整链入库 |
| `systeminfo \| findstr "OS 名称 OS Name …"` | 输出格式与区域设置强耦合，字符串过滤不可可靠迁移（可用 uname，但已非"迁移"） |
| `wmic … \| findstr …` | 命令无 Linux 对应物（既有 TODO 处理正确） |
| `%CMD% \| findstr STR` | 上游命令为动态变量，静态不可知；保持"未知命令 + 警告" |
| `findstr STR` 单独出现（非管道） | 与管道话题无关；且裸 grep 兜底已由独立机制处理 |
| `^\|` / `\|\|` 行 | 转义字面量与逻辑或，归一化误报（已剔除） |
| >4 段纯 findstr 链 | 真实脚本罕见，维护成本 > 收益；建议 3 段封顶 |

## 5. 覆盖率估算

- **段级**：findstr 段（26/37 行的组成部分，含 `/i /n /v /c: /r`）→ 第一批 1–6 条覆盖 ≈ **100%** 的 findstr 语义映射
- **行级**：37 条真管道行中
  - 直接可自动（结构类 #5–10 + 命令类 #11–16 中确凿项）：约 **19/37 ≈ 51%**
  - 可自动但带格式差异警告（B/C 档命令 idiom）：约 **11/37 ≈ 30%**
  - 保持 TODO 的合理项（反例、动态、超长链）：约 **7/37 ≈ 19%**
  - → 第一批入库后，**约 81% 的管道行**可得到"自动或带警告的自动"处理；剩余缺口集中在 Windows 专有数据源
- **注**：以上比例受孪生文件重复影响，独立视角（21 唯一形态）下同口径约为 75–80%

## 6. 语料充分性与建议

**语料偏小，建议分两步走：**

1. **本批（立即可做）**：只入库段级映射（#5–10）与 A 档直译（#11、#15）；B/C 档命令 idiom 以"带警告的自动 + 参考模板"形式提供，不追求语义等价
2. **等语料积累再做**：当前 21 条唯一形态、且来自 4 个 torture-test 脚本，**不足以支撑模式库的抽象设计**（缺真实业务脚本中的：日志过滤、CSV/表格加工、服务巡检、批处理重定向组合等）。建议：
   - 继续收集真实 .bat/.cmd（目标：≥10 个独立脚本、≥50 条唯一管道行）
   - 届时再做第二轮挖掘，重点补全：多级过滤链上限、引号/转义在管道中的边界、`for /f` 内管道（当前整行 TODO）
   - 不建议在语料 <10 脚本时扩大 C 档（语义接近）的自动转换面

## 7. 第二轮扩充诊断（2026-09-14 · AI 生成语料）

> 新增语料：`~/下载/deepseek_bat_20260914_*.bat` ×10 + `deepseek_powershell_20260914_*.ps1` ×10（均为 AI 生成）。
> 方法与第一轮对齐；统计脚本 `/tmp/opencode/pipeline_mine3.py`、`pipeline_probe.py`、`pipeline_handling.py`（只读，未入库）。
> 转换行为实测基于 HEAD `b91df72`。**本节为追加，不覆盖第 1–6 节；对第一轮结论的修订见 7.7。**

### 7.1 语料规模

| 子集 | 文件 | 行数 | 管道实例 | 有管道的文件 |
|---|---|---|---|---|
| .bat 20260914（新） | 10 | 677 | 9（直接 5 + 命令上下文 4） | 3/10 |
| .ps1 20260914（新） | 10 | 395 | 18（逻辑行） | 8/10 |

- .bat 新语料是"语法演示片段"集合：`FOR /L`、字符串定义、日期格式化、ping 扫段、服务巡检、菜单工具等，10 个文件里 7 个零管道
- .ps1 新语料同样是特性演示：哈希表遍历、动态命令、Here-String、目录树、重试包装、日志统计、系统报告（含后台作业）
- 误报剔除示例：`echo Header: %%a ^| %%b ^| %%c`（735127）是转义竖线字面量，非管道（本轮脚本已正确排除）

### 7.2 新旧对比（.bat / .ps1 分开统计）

#### .bat — 直接行管道（第一轮同口径）

| 指标 | 第一轮（旧） | 第二轮（新） | 合并 |
|---|---|---|---|
| 独立源文件 | 5 | 10 | 15 |
| 管道行实例 | 36 | 5 | 41 |
| **唯一形态数** | **20** | **5** | **25** |
| 频次 ≥2 形态数 | 16 | 0 | 16 |
| 真新 / 变体 / 重复（vs 原清单） | — | 2 / 3 / 0 | — |

- 第一轮 16 条高频几乎全部来自 `stress_test` 与 `895203` 孪生重复；新语料**没有任何一条达到频次 2**（10 个文件彼此独立、无复用）

#### .bat — 命令上下文管道（`for /f ('... ^| ...')`；第一轮未统计，本次补录）

| 指标 | 旧语料（补算） | 新语料 | 合并 |
|---|---|---|---|
| 管道实例 | 24 | 4 | 28 |
| **唯一形态数** | **13** | **4** | **17** |
| 频次 ≥2 形态数 | 11（孪生重复） | 0 | 11 |
| 真新 / 变体 / 重复 | — | 1 / 1 / 2 | — |

- 第一轮口径遗漏了这一大类（第一轮脚本把单引号内命令整体剔除）。**补录后，命令上下文管道是与直接行同量级的需求面**，且目前 24+4 条**全部 TODO/被注释**，是当前最大单一缺口

#### .ps1

| 指标 | 第一轮 | 第二轮 | 合并 |
|---|---|---|---|
| 独立源文件 | 2 | 10 | 12 |
| 管道逻辑行 | 1 | 18 | 19 |
| **唯一形态数** | **1** | **16**（链级 15） | **17** |
| 频次 ≥2 形态数 | 0 | 2（链级 3） | 2 |
| 真新 | — | 16 | — |

#### 总览（仅合计，不混表）

- 同第一轮口径（bat 直接 + ps）：唯一形态 **21 → 42**
- 含命令上下文补录：**34 → 59**（bat 25 + bat 上下文 17 + ps 17）
- 新增 25 条模式中：**真新 19、重复 2、变体 4**；其中 **23/25 频次 = 1**
- 频次 ≥2：bat 16 条全部来自第一轮（torture 孪生）；ps 2 条全部来自第二轮（跨文件复用）

### 7.3 新增模式清单（原 21 条之外）

#### .bat（9 条：直接 5 + 命令上下文 4）

| # | 归一化模式（原样） | 来源 | 真新/重复/变体 | AI 味 | 现状（b91df72 实测） |
|---|---|---|---|---|---|
| 1 | `ipconfig /all \| findstr /i STR` | 6375a0:54 | 变体（#1） | 低 | 自动+警告；**多词 OR 语义错**（grep 按字面短语，永不匹配） |
| 2 | `nslookup google.com 2>nul \| findstr /v STR` | 6375a0:60 | 真新 | 高 | TODO（管道+重定向） |
| 3 | `systeminfo \| findstr /b /c:…×4` | 6375a0:73 | 变体（#9） | 中 | 自动+警告；**/b 被忽略、仅保留最后 1 个 /c:（丢 3 个模式）** |
| 4 | `tasklist /fi STR 2>nul \| findstr /i STR >nul` | ad2b59:42 | 变体（#4） | 低 | TODO（含参考建议） |
| 5 | `tasklist /fi STR /fo csv \| findstr /v STR` | ad2b59:45 | 真新（/fo csv） | 中 | 位于 TODO 的 if 块内，被注释 |
| 6 | `sc query "%VAR%" ^\| findstr "STATE"`（for /f 内） | ad2b59:16 | 重复（旧上下文同类） | 低 | TODO 块内注释 |
| 7 | `systeminfo ^\| findstr /b /c:"OS Name"`（for /f 内） | ad2b59:53 | 重复 | 中 | TODO |
| 8 | `wmic … /value ^\| findstr "="`（for /f 内） | ad2b59:59 | 变体（旧 wmic Caption 同类） | 高 | TODO |
| 9 | `ping … ^\| findstr "time="`（for /f 内） | a36f6f:23 | 真新 | 低（真实惯用法） | TODO 块内被注释 |

#### .ps1（16 条唯一形态 · 行级归一化；链级 15）

| # | 链（归一化） | 频次 | AI 味 | 现状（b91df72 实测） |
|---|---|---|---|---|
| 1 | `N..N \| ForEach-Object {` | 2 | 高（合成范围） | TODO |
| 2 | `$VAR \| Format-Table -AutoSize` | 2 | 中高（装饰性显示） | TODO |
| 3 | `$VAR \| ConvertTo-Json -Depth N \| Out-File STR` | 1 | 高（序列化演示） | TODO |
| 4 | `$VAR = Get-Content -Raw \| ConvertFrom-Json` | 1 | 高（序列化演示） | **半自动：静默丢 ConvertFrom-Json（退化为 cat）** |
| 5 | `$VAR \| Select-Object -First N \| ForEach-Object { Write-Host }` | 1 | 中 | TODO |
| 6 | `Get-ChildItem \| Sort-Object {…}, Name` | 1 | 中 | TODO |
| 7 | `Group-Object \| Select-Object \| Sort-Object` | 1 | 中（统计惯用） | **半自动坏行**（`levelStats="${…} \| Group-Object …"`） |
| 8 | `$VAR \| ForEach-Object {`（含赋值形态 ×1） | 2 | 中 | TODO |
| 9 | `$VAR \| Out-File STR` | 1 | 中 | 半自动（上游变量已是坏行） |
| 10 | `Sort-Object \| Select-Object -First $VAR \| Format-Table` | 1 | 中 | TODO |
| 11 | `@(STR…) \| Get-SystemReport … -Verbose` | 1 | 高（自定义函数演示） | TODO |
| 12 | `Get-Process \| Where-Object \| Sort-Object \| Select-Object` | 1 | 中（真实惯用） | **半自动坏行**（`topProcesses=$(ps aux \|)` 语法错误） |
| 13 | `$VAR \| Wait-Job -Timeout N \| Out-Null` | 1 | 高（作业演示） | TODO |
| 14 | `Get-ChildItem \| Where-Object \| ForEach-Object` | 1 | 中（真实惯用） | TODO |
| 15 | `$VAR \| Export-Csv -NoTypeInformation` | 1 | 中 | TODO |

- .ps1 段级频次（剥离赋值前缀）：`ForEach-Object` 6、`Select-Object` 4、`Sort-Object` 4、`Format-Table` 3、`Out-File`/`Where-Object`/`Get-ChildItem` 各 2
- 链签名频次 ≥2：`N..N \| ForEach-Object`、`$VAR \| ForEach-Object`、`$VAR \| Format-Table`（各 2）

### 7.4 "AI 味"判据与标注

**判据**（可用文件本身复核，不依赖单文件直觉）：

1. **主题 = 语言特性演示**：注释标题即 `:: FOR /L - 数值范围循环`、`# Here-String 多行字符串`、`# 格式化运算符 -f`、`# 动态命令构建与调用`——脚本存在目的是"展示语法"，不是完成某任务
2. **合成数据**：`1..10 \| ForEach-Object`、`1..3 \| ForEach-Object`、`@("Server01","Server02","Server03")`、固定阈值 `50MB`、玩具日志
3. **教程式组合**：`nslookup google.com \| findstr /v "#"`（教材 DNS 检查范例）
4. **装饰性输出**：`Format-Table -AutoSize` 单独成行、`===` 分隔线、全量 `-ForegroundColor`、`echo Header: %%a ^| %%b`（用转义竖线画表格）
5. **模板脚手架**：菜单 `choice`+`goto` 循环、`Initialize→Process→Cleanup→Summary` 四段式、时间戳日志流水线

**标注结果**：
- **高 AI 味（不建议作为频次证据）**：.bat 清单 #2 nslookup、#8 wmic；PS `N..N\|ForEach-Object`、`ConvertTo-Json`/`ConvertFrom-Json` 往返、`Wait-Job\|Out-Null`、`@(Server01…) \| 自定义函数`；以及全部菜单/四段式脚手架
- **真实惯用法（AI 从真实语料习得，可作"惯用法存在性"证据，但频次由第一轮为准）**：`ipconfig \| findstr`、`tasklist /fi \| findstr`、`ping \| findstr "time="`、`sc query \| findstr "STATE"`、PS `Get-ChildItem \| Where-Object \| ForEach-Object`、`Get-Process \| Where-Object \| Sort-Object \| Select-Object`、`Group-Object` 统计、`Export-Csv`
- **勿混淆**："AI 语料高频" ≠ "真实脚本高频"：新语料中频次≥2 的仅 3 条链，且 bat 侧新模式的实例频次全部 = 1；AI 生成集中复现的是**教材级 idiom**，对"哪些模式值得入库"只能提供广度（缺口发现），不能提供权重

### 7.5 转换行为实测：新发现（只读诊断）

1. **P0 · PowerShell 路径没有 `bash -n` 后置校验**（`powershell.py` 全文 0 处 `bash_check`；守卫只存在于 `BatchConverter`）：
   - 新 .ps1 语料 **9/10 个文件**转换产物 `bash -n` 失败，且 `error_count=0`、无降级、无告警——CLI/GUI 会照常写出坏脚本
   - 失败样例：`topProcesses=$(ps aux |)`（语法错误）、`levelStats="${parsedEntries} | Group-Object -Property Level |"`（字面泄漏）、条件块结构错位
2. **P0 · PS 管道"半自动"产出坏行而非诚实 TODO**：18 条管道逻辑行中，起始行被标 TODO 的 12 条、未标 6 条；对 6 条逐一复核：**3 条产出语法/语义坏的 bash**（`topProcesses=$(ps aux |)`、`levelStats="${parsedEntries} | Group-Object -Property Level |"`、`sanitized="${logLines} | ForEach-Object {"`）、**1 条静默丢段**（`Get-Content -Raw | ConvertFrom-Json` → `cat`）、2 条实为段行 TODO 或坏产物的后续行。即：**新语料中没有一条 PS 管道链被正确完整转换**
3. **P1 · findstr 多词 OR 语义**：`findstr "A B C"` 在 cmd 是 OR 多模式，转换后成为单条 grep 字面短语、永不匹配。老语料 2 实例（中文+英文）+ 新语料 1 实例（`"IPv4 Subnet Gateway DNS"`）——全部处于"自动转换成功"状态，属最危险的"看起来对、实际错"象限
4. **P1 · findstr `/b` + 多个 `/c:`**：新发现——`/b` 忽略告警，但多个 `/c:` 仅保留最后一个，**其余模式被静默丢弃**（6375a0:73 丢 3/4）
5. **bat 侧防线有效**：新 .bat 10/10 产出通过 `bash -n`、无降级、无坏行（`_bash_syntax_error` 守卫 + TODO 纪律生效）；问题集中在 PS 路径

### 7.6 覆盖率估算（新语料口径）

| 子集 | 行数 | 干净自动 | 假自动（语义错） | TODO/注释 | 坏行 |
|---|---|---|---|---|---|
| .bat 管道 9 行 | 9 | 0 | 2（#1、#3） | 7 | 0 |
| .ps1 管道 18 行 | 18 | 0 | 0 | 13（含段行标注 1） | 3 坏行 + 1 静默丢段 + 1 坏产物后续行 |

- 修复 P0 后：.ps1 的 18 行应全部收敛为"安全输出或诚实 TODO"（坏行 3 + 丢段 1 清零），可靠性提升不体现在自动化率
- 修复 P1 后：.bat 的 2 条"假自动"（多词 OR / 多 `/c:`）变为正确输出或诚实 TODO
- 入库 P2（`for /f` 内两段管道直译）后：.bat 9 条中约 4 条可转为可自动类（`ping`/`sc query`/`systeminfo` 上游可迁移），`wmic`/`nslookup` 保持 TODO
- 口径说明：新语料实例频次多为 1，**百分比覆盖率在本轮说服力弱于第一轮**（第一轮至少来自孪生 torture 的重复），建议以"缺口类型是否收敛"而非百分比评估

### 7.7 结论（对第一轮结论的修订）

1. **语料量：21 → 42（同口径）/ 34 → 59（含命令上下文补录），但仍不足以支撑按频次驱动的完整模式库**。新增量来自 AI 教程片段：主题分散、实例频次全为 1、bat 侧零跨文件复用。**AI 语料应定位为"鲁棒性探针 + 惯用法发现"，不能当真实频次证据**。
2. **够做的是"定向修复 + 少量段级模板"**，建议排序：
   - **P0（先于一切）**：PS 转换路径补 `bash -n` 后置校验/安全降级；将管道半转换（含坏行 3 类）一律降级为诚实 TODO。理由：本轮 9/10 文件触发，是"产出坏脚本"的底线问题，与模式库无关
   - **P1**：findstr 正确性修复——多词 OR 语义（3 实例，全部"假自动"）+ 多 `/c:` 合并 + `/b` 处理。理由：属最危险象限且修复成本低
   - **P2**：`for /f` 命令上下文内的两段管道直译（`'CMD ^| FILTER'` → 复用现有段级管道能力 + 进程替换）。理由：17 条唯一形态同构（命令|过滤），是当前最大单一缺口，且样板极窄
3. **明确暂缓**：PS 管道链模板（`Format-Table`/`ForEach-Object` 脚本块/序列化链/`Wait-Job`）、`nslookup`、`wmic` 上游、bat 单例（`/fo csv` 等）——待 P0 落地 + 真实 PS 语料积累后再评估
4. **语料目标不变**：真实脚本 ≥10 个独立源；本轮 AI 语料可作为回归 fixture（尤其"必须不产出坏行"的负样本）

---

*统计脚本：`/tmp/pipeline_mine2.py`（第一轮）与 `/tmp/opencode/pipeline_mine3.py`、`pipeline_probe.py`、`pipeline_handling.py`（第二轮）（均只读，未入库）。第一轮行为对照基于 HEAD `c7c1c85`；第二轮（第 7 节）基于 HEAD `b91df72`。*
