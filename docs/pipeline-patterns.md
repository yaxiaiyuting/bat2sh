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

---

*统计脚本：`/tmp/pipeline_mine2.py`（只读，未入库）。行为对照基于当前 HEAD `c7c1c85` 的转换器实测。*
