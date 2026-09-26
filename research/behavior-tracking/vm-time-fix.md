# 固定 VM 时间（行为采集设施）

> 时间：2026-09-26 · 轨道：research/behavior-tracking（**研究设施，未改 bat2sh 产品代码**）
> 起点 HEAD：`85cde68`（工作区干净；`pytest -q` 1588 passed）
> 域：`win-behavior`（`qemu:///system`）
> 交付：域 XML（`<clock offset='absolute' start='1780315200'>`）+ `tools/vm.py` 时间原语
> + `tools/collect.py` 每轮强制 + 本文件

---

## 1. 结论（先说结果）

| 问题 | 答案 | 依据 |
| :--- | :--- | :--- |
| 只改域 XML 能固定 guest 时间吗？ | ❌ **不能**（本镜像/本配置下） | 4 次冷启动实测：RTC 写 2026-06-01，guest 实际起来在 **2026-09-26 20:27~21:47**（§3.2/§3.4） |
| XML 改动白做了吗？ | ➖ 不是，但**不是保证** | `-rtc base=` 确实写进了 QEMU 命令行（`domxml-to-native` 实证）；未来日期被 guest **逐字采纳**（§3.3）⇒ 它是有效的"启动锚点"，只是会被 Windows 拒绝 |
| 时间真的固定住了吗？ | ✅ **固定住了** | 每轮开机后 `guest-set-time` + **读回验证**；残差 **≤ 0.23 s**，重复调用幂等（§3.5） |
| 真的样本跑在 T0 上吗？ | ✅ 是 | `s04` 端到端采集：`%DATE% %TIME% = 2026/06/01 周一 12:00:00.41`，`rc=0`，产物与历史批次一致（§3.6） |
| 固定时间影响 J1 判据吗？ | ❌ 不影响 | 清单只收 `FullName/Length/Hash`（**无 mtime**）；`s04` 的 `baseline_manifest_hash` 与历史批次**逐字符相同**（§5.6） |
| 任务书给的 XML 形式可用吗？ | ❌ **本机 schema 里不存在** | libvirt 12.7.0 的 `domaincommon.rng` 无 `offset='time'`/`<time>`；现代等价物是 `offset='absolute' start='<epoch>'`（§2.2） |

**一句话**：固定时间这件事，**最后靠的是"每轮显式设 + 读回验证"，不是 XML**。XML 只负责把 CMOS RTC 拨到 T0；而 **Windows 拒绝比"自己上次已知时间"早很多的 RTC 值**，于是它按镜像里存的时间起来 —— 那个值还会被**本设施自己的覆盖层回滚**改来改去（§3.4），所以既不是 T0、也不可复现。

---

## 2. 方案与取值

### 2.1 为什么需要一个固定时间

采集指纹里有三类东西**随真实日历漂移**，导致"同一脚本、不同 session 得到不同结果"：

1. **样本自己读时间**：`%date%`/`%time%`/`%DATE%`/`%TIME%`。语料里是真实存在的 ——
   `s07 查找最新的文件.bat` 的 `md %date%` 直接拿日期当路径（`batch-result.md` §4.3），
   `s12 每天自动创建文件夹.bat` 同类。
2. **文件/目录时间戳**：样本可能用 `dir /o-d`（按时间排序找最新）之类比较时间。
3. **"日历相关"的外部条件**：Insider 镜像有时间炸弹；某些样本按星期/月份走不同分支。

固定时间让这三类都变成**常量**，指纹因此跨 session 可比。

### 2.2 XML 的正确写法（任务书给的形式在本机不成立）

任务书 §2.1 给的是：

```xml
<clock offset='time' adjustment='set'>
  <time>2026-05-20T12:00:00</time>
</clock>
```

**本机 libvirt 12.7.0 的 schema 里没有这种写法**。证据（只读）：

```
$ python3 -c "…读 /usr/share/libvirt/schemas/domaincommon.rng 的 clock 定义…"
offset 取值：localtime | utc | timezone | variable | absolute
  · localtime/utc  : 可选 adjustment（timeDelta 或 reset）
  · timezone       : 可选 timezone
  · variable       : 可选 adjustment / basis
  · absolute       : **必填 start（unsignedLong，纪元秒）**     ← 唯一能"设定绝对时刻"的
```

`/usr/share/doc/libvirt/html/formatdomain.html` 对应原文：

> **absolute** — The guest clock will be always set to the value of the `start` attribute at startup of the domain.
> The `start` attribute takes an **epoch timestamp**. Since 8.4.0.

因此实际改为（**只改了这一行**，与备份逐行 diff 验证）：

```xml
<clock offset='absolute' start='1780315200'>
  <timer name='rtc' tickpolicy='catchup'/>
  <timer name='pit' tickpolicy='delay'/>
  <timer name='hpet' present='no'/>
  <timer name='hypervclock' present='yes'/>
</clock>
```

### 2.3 T0 取值：**2026-06-01 12:00:00（guest 本地，Asia/Shanghai）**

| 项 | 值 | 理由 |
| :--- | :--- | :--- |
| guest 本地墙钟 | **2026-06-01 12:00:00**（周一） | `%date%` 形如 `2026/06/01 周一` |
| guest UTC 时刻 | **2026-06-01T04:00:00Z** | `guest-set-time` 收 UTC 纪元秒 = `1780286400` |
| RTC 字面量（XML `start`） | **1780315200**（= 2026-06-01T12:00:00Z） | Windows **把 RTC 当本地时间**读 ⇒ `start` 要填"目标本地墙钟的 UTC 字面量" |
| 构建时间 | 2026-05-20（`260520-1434`） | Insider 镜像构建于此前（`session-verdict.md` §五.2） |
| 已知可用上界 | 2026-09-26（guest 曾在此日期正常运行） | 同上 |

选 2026-06-01 而不是 2026-09-26 或更晚：**离构建时间只 12 天**，把"构建时间炸弹"的风险压到最小；同时 T0 必须是常量，不能跟着"今天是几号"走。

> ⚠️ **两个数字故意不同**（`1780286400` vs `1780315200`），不是笔误：前者是 UTC 时刻，后者是"RTC 里的本地墙钟"。两条路径落到**同一个 guest 墙钟**（§3.3 实测：`start` 的字面量就是 guest 显示的本地时间）。

### 2.4 选择"每轮显式设 + 验证"的理由

XML 是**声明式**的：它把 RTC 拨到 T0，但**无法保证 guest 接受**（§3.2 实证）。
采集器需要的是"**这一轮确实跑在 T0 上**"这个可验证的性质，因此：

- 在 `collect.py` 的循环里，**agent 就绪之后、任何行为观测之前**，显式设置并**读回**（`enforce_fixed_time()`）；
- 读回偏差超过容差（2 s）⇒ **硬失败**，拒绝在未知时钟下采集（不允许"静默跑在错误时间上"）；
- 结果写进指纹 `fixed_time`（证明"这轮确实跑在 T0"）。

这与 `check_env()` 的既有纪律一致：**能验证的才敢声称**。

---

## 3. 实测

### 3.1 仪器（先验证仪器，再谈结论）

| 仪器 | 用途 | 验证方式 |
| :--- | :--- | :--- |
| `virsh domxml-to-native qemu-argv` | **不开机**看 libvirt 到底把 clock 翻译成什么 | 见下（关键：确认改动真的落到 QEMU 命令行） |
| QGA `guest-get-time` | guest 时钟（UTC 纳秒 → 纪元秒），**与 guest 时区无关** | 与 host 同时刻读数配对；20 s 内重复测漂移 |
| QGA `guest-exec cmd /c date /t & time /t` | **样本视角**的本地墙钟（`%date%` 那一层） | 与 `guest-get-time` 交叉一致（§3.5） |
| `virsh dumpxml` | 域定义回读 | 与备份 diff，确认**只改了 clock 一行** |

生成的 QEMU 参数（改动前 / 改动后）：

```
改前（offset='localtime'）: -rtc base=localtime,driftfix=slew
改后（offset='absolute'） : -rtc base=2026-06-01T12:00:00,driftfix=slew
```

⇒ **XML 改动确实到达了 QEMU**。后面所有"guest 没按这个时间起来"都不是"配置没生效"，而是 **guest 主动拒绝**。

域定义 diff（`virsh define` 前后）：

```diff
-  <clock offset='localtime'>
+  <clock offset='absolute' start='1780315200'>
```

### 3.2 事实 1：**比"自己上次已知时间"早很多的 RTC 值被 Windows 拒绝**

四次冷启动，域 XML 的 `start` 都是 T0（`1780315200`），guest 起来后实测：

| # | host 时刻 | guest 时刻（本地） | 相对 T0 的偏移 | 说明 |
| ---: | :--- | :--- | ---: | :--- |
| 1 | 2026-09-26 22:03:58 | 2026-09-26 21:33:55 | **+1013925x s**（≈ +117.3 天） | 偏移**恒定**（20 s 内漂移 0.001 s） |
| 2 | 2026-09-26 22:11:00 | 2026-09-26 20:27:42 | +10139262.9 s | 覆盖层回滚后 |
| 3 | 2026-09-26 22:11:23 | 2026-09-26 20:27:59 | +10139279.7 s | 紧接着再启动一次 |
| 4 | 2026-09-26 22:1x | 2026-09-26 20:28:17 | +10139297.9 s | 端到端验证那次 |

**RTC 里明明是 2026-06-01，guest 却起在 2026-09-26。** 且**同一份 XML、连续两次启动，guest 时钟差 16.8 s**（20:27:42 → 20:27:59）—— 不是常量、不可复现。

> **机制（不猜，只说确证的）**：Windows **没有**采纳该 RTC 值，而是回落到它自己保存的"上次已知时间"。
> 至于"为什么拒绝/回落到哪个值"的**内部判据未确证** —— 但回落的**来源**被 §3.4 定位到了。

### 3.3 事实 2：**未来的 RTC 值被逐字采纳**（判定这是"拒绝"而非"没生效"）

把 `start` 换成 **2026-10-01T12:00:00Z**（`1790856000`，比 host 当前时间晚 5 天）后冷启动：

| 项 | 值 |
| :--- | :--- |
| host | 2026-09-26 14:07:31Z |
| guest（`guest-get-time`） | 2026-10-01 04:00:23Z |
| guest（`date /t`，本地） | **2026/10/01 周四 12:00** |
| 生成参数 | `-rtc base=2026-10-01T12:00:00,driftfix=slew` |

⇒ RTC → guest 这条链**是通的**；`start` 的**字面量**就是 guest 显示的**本地**墙钟。
⇒ §3.2 的失败**只因为那个值在"过去"**。

### 3.4 事实 3：回落的锚点来自**镜像内部状态**，而覆盖层回滚会改它

把 §3.2 的四次读数与镜像文件对上：

| 观测 | 值 |
| :--- | :--- |
| 基础镜像 `win-behavior.base.qcow2` 写入时刻 | **2026-09-26 20:27:18** |
| 启动 #2 / #3 / #4 的 guest 时钟 | 20:27:42 / 20:27:59 / 20:28:17 |

三次都在"基础镜像写入时刻 + 24~59 s"附近，且**逐次递增**（每次 guest 运行期间它在镜像里更新自己的"上次已知时间"）。
启动 #1 的锚点（21:33:55）则对应**上一轮 session 结束时的镜像状态**（该 session 的文件时间戳是 21:35）。

**这解释了为什么"改 XML"这件事在本设施里格外不可靠**：

- 本设施**每个样本都从基础镜像拉一份覆盖层**（`rollback-design.md` §3），跑完丢弃；
- 于是 guest 的"上次已知时间"**每轮都被回滚**到基础镜像里的那个值；
- 结果：**开机时钟 = 镜像里的陈旧时间**，既不是 T0，也不是 host 当前时间，**而且和真实日历脱钩**（它只随"镜像 + 本轮已运行时长"走）。

> 换句话说：**靠 RTC 固定时间，等价于把时间固定在"上次做基础镜像的那一刻"** —— 这不是我们要的 T0，也会随基础镜像重建而变。

### 3.5 事实 4：`guest-set-time` 方向无关、可验证、幂等

| 调用 | action | before 偏移 | after 偏移 | ok |
| :--- | :--- | ---: | ---: | :--- |
| 第 1 次（`s04` 采集轮内） | `set` | +10139253.9 s | **+0.062 s** | ✅ |
| 第 1 次（专测） | `set` | +10139297.9 s | **+0.125 s** | ✅ |
| 立刻第 2 次 | `already` | +0.186 s | **+0.226 s** | ✅ |

同一时刻 `cmd` 视角（**样本能看到的那一层**）：

```
date /t        → 2026/06/01 周一
time /t        → 12:00
%DATE% %TIME%  → 2026/06/01 周一 12:00:00.41
```

时钟**速率**与 host 一致（20 s 窗口内偏移变化 0.001 s）⇒ 一轮 ~40 s 的采集期间漂移 < 0.1 s；同一轮内不同样本看到的时刻差 = 该轮耗时，这是**预期**，不是漂移。

### 3.6 端到端：真实样本跑在 T0 上

```
python3 tools/collect.py \
  --sample "$HOME/下载/非常批处理/生成指定内容的文本文件.bat" \
  --guest-name s04.bat --output results/timefix/s04.json --network isolated
```

| 项 | 结果 | 与历史批次（`batch-result.md` s04）对比 |
| :--- | :--- | :--- |
| `exit_code` | 0 | 同 |
| `created` | `['C:\poc\samples\a.txt']` | 同 |
| `baseline_manifest_hash` | `sha256:72d287eb…e05df` | **逐字符相同** ⇒ J1 可比性未被破坏 |
| `fixed_time.ok` | `true`（`action=set`，残差 0.062 s） | 新增字段（schema v4） |
| `network` | `isolated=True, egress_frames=0` | 同 |
| `cycle_ms` | 47.9 s | 37.8 s 中位数（同量级；`env_check`/`baseline` 本轮偏慢） |

---

## 4. 落地实现

| 文件 | 改动 |
| :--- | :--- |
| 域 XML（`qemu:///system`） | `<clock offset='localtime'>` → `<clock offset='absolute' start='1780315200'>`（备份：`/tmp/win-behavior.xml.orig`，sha256 `434e669c…c89984`） |
| `tools/vm.py` | 新增常量 `FIXED_TIME_UTC_EPOCH` / `FIXED_TIME_RTC_START` / `FIXED_TIME_LOCAL` / `FIXED_TIME_TOLERANCE_S`；新增 `Qga.get_time()` / `Qga.set_time()` / `Qga.enforce_fixed_time()`（**失败即 `GuestError` 硬失败**） |
| `tools/collect.py` | 循环内新增 **3.5 固定时间**（agent 就绪 → 任何观测之前）；`fp["fixed_time"]`；`SCHEMA_VERSION` **3 → 4**（增量）；`HARNESS_VERSION` 1.1.0 → **1.2.0** |
| `tools/batch.py` | 批量汇总透传 `fixed_time_ok` / `fixed_time_offset_s`（v3 指纹如实留 `None`） |

`schema v4` 是**增量**变更：v3 的读取方不受影响；但**v3 指纹不能被声称"跑在固定时间上"**（缺 `fixed_time` 段）。

---

## 5. 时间固定**影响哪些行为**（任务书 §2.3 要求逐条记录）

### 5.1 直接影响（现在由 T0 决定，跨 session 稳定）

| 类别 | 例子 | 固定前 | 固定后 |
| :--- | :--- | :--- | :--- |
| `%date%` / `%DATE%` | `s07` 的 `md %date%`、`s12` 的按日期建目录 | 每天不同（且格式随区域设置） | 恒为 `2026/06/01 周一` |
| `%time%` / `%TIME%` | 日志前缀、按小时分支 | 每次运行不同 | 恒从 `12:00:00` 起（每轮 +轮内耗时） |
| 文件/目录 mtime | `dir /o-d` 找最新文件（`s07`）、`forfiles` 类 | 随真实日期 | 随 T0（**注意**：清单指纹不含 mtime，见 §5.6） |
| 星期/月份分支 | 按 `%date:~-2%` 之类判断 | 随真实日历 | 恒为周一 / 6 月 |

### 5.2 被**消除**的漂移源（固定时间的主要收益）

- **Insider 时间炸弹**：guest 日期不再向到期日推进 ⇒ "某天突然跑不动"的风险被冻结（代价：若 T0 本身落在炸弹窗口内，问题会**每次都出现**而不是"某天才出现" —— 反之亦然，属于把不确定变成确定）。
- **"上次已知时间"随机化**（§3.4）：固定前，开机时钟取决于基础镜像写入时刻与本轮已运行时长 ⇒ 同一脚本在不同 session 的 `%date%` 完全不同。

### 5.3 明确**不受影响**的东西

- **J1 基线清单哈希**：`Qga.manifest()` 只收 `FullName` / `Length` / `Hash`，**不含 mtime** ⇒ 固定时间不改变起点哈希（§3.6 实测同值）。
- **回滚与隔离判据 J2/J3**：与时间无关。
- **本机（宿主）时间**：只改 guest，宿主的构建/发布流程不受影响。

### 5.4 新引入的**偏差**（诚实记录，需要时可在结论里带上）

1. **guest 时间与真实世界不同步**（差约 4 个月）。任何"按真实时间判断"的行为都会变形：
   - `nat` 模式下访问 HTTPS：证书有效期判定会不同（`isolated`/`recording` 无真实出网，不受影响 —— 但**不要**用 `nat` 做时间敏感判定）。
   - 依赖"今天是星期几"的真实业务语义（如备份窗口）会指向 T0 的周一。
2. **同一轮内时间仍在走**：T0 是"轮起点"，不是"冻结时钟"。一轮 40 s ⇒ 轮内样本间有 ~40 s 差异。**跨轮可比，轮内不同时刻不可比** —— 指纹里用 `fixed_time.after_offset_s` 记残差，用 `timings` 记轮内进度。
3. **`start` 的两个常量**（`1780315200` vs `1780286400`）语义不同，改动其一必须同时改另一个（`vm.py` 注释已写明）。

### 5.5 精度与容差

- 设置残差：**0.062 ~ 0.226 s**（QGA 往返 + Windows 时钟粒度）。
- 速率：与 host 同步（20 s 内 0.001 s）。
- 硬失败阈值：**2 s**（`FIXED_TIME_TOLERANCE_S`）。超过即拒绝采集，而不是带着未知偏移继续。

### 5.6 与既有结论的兼容性

- `batch-result.md` 的 16 个样本采集于**固定时间生效之前**（schema v3），其 `%date%` 相关行为对应 **2026-09-26**。新采集（v4）对应 **2026-06-01**：
  - 对**不依赖时间**的样本（绝大多数）：指纹应逐字段一致；
  - 对 `s07` 这类**依赖时间格式**的样本：失败**类别**相同（`md` 仍把 `/` 当开关），但 stderr 里的日期字面量会不同 ⇒ 跨版本对比时要看"类别"而不是"字面量"。

---

## 6. 未做与限制（明确披露）

| # | 项 | 说明 |
| :-- | :--- | :--- |
| 1 | Windows 拒绝"过去 RTC"的**内部判据**未确证 | 只确证了现象（§3.2/§3.3）与回落锚点的来源（§3.4）。**没有**去猜注册表键名或内核逻辑 |
| 2 | **基础镜像内的"上次已知时间"未重置** | 它仍是 2026-09-26 20:27 左右。理论上"从基础镜像启动一次 → 设 T0 → 重建基线"可让 RTC 锚点也被接受；**本轮未做**（每轮 QGA 已足够，且改基线是更重的动作） |
| 3 | T0 未与"真实当前时间"做偏移补偿 | 采集期间 guest 比真实世界慢约 4 个月；见 §5.4 |
| 4 | 未改 guest 的 Windows Time 服务 / 时区 | `w32time` 本来就是**未启动**（实测 `0x80070426`）且 guest 无网络 ⇒ 没有其他时间源干扰。时区为 `China Standard Time`，与 T0 的表述绑定 |
| 5 | 未做"时间固定后重跑 16 样本"的全量批次 | 本轮只做了 1 个真实样本的端到端（§3.6）。全量重跑（v4 指纹）留给下一次批量采集 |
| 6 | `nat` 模式下的时间敏感行为未评估 | §5.4 已列为限制 |

---

## 7. 可复跑

```bash
# 1) 看域定义与 QEMU 参数（不开机）
virsh -c qemu:///system dumpxml win-behavior | sed -n '/<clock/,/<\/clock>/p'
virsh -c qemu:///system domxml-to-native qemu-argv /tmp/win-behavior.timefix.xml | tr ' ' '\n' | grep -A1 '^\-rtc$'

# 2) 改 clock（幂等）
virsh -c qemu:///system dumpxml win-behavior > /tmp/vm.xml
#    把 <clock offset='…'> 改成 <clock offset='absolute' start='1780315200'>
virsh -c qemu:///system define /tmp/vm.xml

# 3) 开机 → 手测固定时间（等价于 collect.py 的 3.5 步）
python3 - <<'PY'
import sys; sys.path.insert(0, 'tools')
from vm import Vm, Qga
Vm().start(); Vm().wait_for_agent()
print(Qga().enforce_fixed_time())     # 期望 ok=True，after_offset_s ≈ 0
PY

# 4) 完整一轮（含固定时间 + 指纹）
python3 tools/collect.py --sample <样本> --guest-name sXX.bat \
        --output results/timefix/sXX.json --network isolated
```

---

## 8. 交付物清单

| 文件 | 状态 |
| :--- | :--- |
| 域 XML（`qemu:///system` 内，`<clock offset='absolute' start='1780315200'>`） | ✅ 已定义并回读验证 |
| `research/behavior-tracking/vm-time-fix.md` | ✅ 本文件 |
| `tools/vm.py`（时间常量 + `get_time`/`set_time`/`enforce_fixed_time`） | ✅ |
| `tools/collect.py`（循环内固定时间 + `fp["fixed_time"]` + schema v4） | ✅ |
| `tools/batch.py`（汇总透传 `fixed_time_*`） | ✅ |
| `results/timefix/s04.json`（端到端证据） | ✅ |

**未改任何 bat2sh 产品代码**（本轮改动全部在 `research/behavior-tracking/tools/` 与域 XML）。
