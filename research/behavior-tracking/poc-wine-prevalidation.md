# PoC 样本本地预验证（Wine）—— 非权威，仅作交叉核对

> 时间：2026-09-26 · 方法：`wine 11.18` 隔离前缀（`~/.cache/bat2sh-wine-poc`，**仓库外**）
> **⚠️ 本文件的结果不是 PoC 结论。** `wine` 的 `cmd.exe` 是**重实现**，不是 Windows。
> 其唯一用途是：在 Windows VM 就绪**之前**，把「样本本身写错了」与「采集通路有问题」两个失败原因**解耦**。
> **行为真值必须来自真实 Windows guest**；`poc-result.md` 才是权威结果。

## 1. 为什么要做这一步

任务书 §七 要求「缺 Windows 镜像 → 暂停」。暂停期间若什么都不做，等 ISO 到位后一旦采集失败，
将无法区分是 **样本写错** 还是 **采集通路不通**。本地用 wine 先跑一遍，可以**预先钉死期望值**：

| 失败现象 | 无预验证 | **有预验证** |
| :--- | :--- | :--- |
| P1 输出缺行 | 样本问题？通路问题？ | 期望值已知 → **通路问题** |
| P1 退出码非 7 | 样本问题？`guest-exec` 吞码？ | 期望值已知 → **`guest-exec` 吞码** |
| P2 差分对不上 | 样本问题？差分方法问题？ | 期望值已知 → **差分方法问题** |

## 2. 环境

| 项 | 值 |
| :--- | :--- |
| Wine | `wine-11.18`（`/usr/bin/wine`，宿主已装） |
| 前缀 | `~/.cache/bat2sh-wine-poc`（**新建隔离前缀**，未触碰用户既有 `~/.wine`） |
| 环境变量 | `WINEPREFIX=<隔离前缀>`、`WINEDLLOVERRIDES="mscoree,mshtml="`、`WINEDEBUG=-all` |
| 调用方式 | `wine cmd /c "<script.bat>"`，stdin `</dev/null` |
| 前缀体积 | 376 MB（缓存目录，**未入仓**） |

## 3. P1 结果 —— ✅ 与预期**完全一致**

```
$ wine cmd /c "poc-01-stdout.bat"   # stdin = /dev/null
rc = 7

POC-01-START
plain line
tab<TAB>separated
caret & ampersand
percent % literal
POC-01-END
```

| 检查点 | 预期 | 实测 | 判定 |
| :--- | :--- | :--- | :--: |
| stdout 行数与内容 | 6 行，见上 | 逐字节一致（CRLF） | ✅ |
| Tab 字面量 | 保留 | `^I` 保留 | ✅ |
| `^&` → 字面 `&` | `caret & ampersand` | 一致 | ✅ |
| `%%` → 字面 `%` | `percent % literal` | 一致 | ✅ |
| **退出码** | **7** | **7** | ✅ |
| stderr | 空 | 空 | ✅ |

> **退出码 7 是本次预验证最有价值的一条**：它证明样本会**主动返回非零码**。
> 因此若真实 VM 上 `guest-exec-status` 报 `exitcode: 0`，即可**确定**是 `guest-exec` 的语义问题（如包装层吞码），而非样本问题。

## 4. P2 结果 —— ✅ 与预期**完全一致**，且**复现了净差分的盲区**

执行前：`./poc-01-stdout.bat`、`./poc-02-fileops.bat`
执行后：

```
rc = 0
stdout: "beta"

./poc-01-stdout.bat      （未变）
./poc-02-fileops.bat     （未变）
./work/                  （新增目录）
./work/a.txt             （新增，内容 "alpha"）
./work/c.txt             （新增，内容 "alpha"，复制自 a.txt）
```

| 检查点 | 预期 | 实测 | 判定 |
| :--- | :--- | :--- | :--: |
| 退出码 | 0 | 0 | ✅ |
| stdout | `beta` | `beta` | ✅ |
| `work/` 创建 | 是 | 是 | ✅ |
| `a.txt` 内容 | `alpha` | `alpha` | ✅ |
| `c.txt` 内容（复制） | `alpha` | `alpha` | ✅ |
| **`b.txt` 建后即删** | **净差分不可见** | **确实不可见** | ✅ **盲区已复现** |
| `a.txt` 被 `copy` 读取 | 净差分不可见 | 不可见 | ✅ **盲区已复现** |

> **这是对 `poc-samples.md` §5 的实证**：净差分**只能看到最终状态**。
> `b.txt` 的「创建 + 删除」在快照对比中**完全消失**，`copy` 对 `a.txt` 的**读**也无痕迹。
> 在真实 VM 上这两条**预期同样不可见** —— 若届时「看见了」，反而说明差分方法有 bug（如残留临时文件）。

## 5. 交互处理（`< nul`）—— ✅ 已验证

用带 `pause` 的探针脚本（`pause-test.bat`，退出码 5）测试三种 stdin 处置：

| 方案 | stdin | 结果 | `pause` 是否阻塞 |
| :--- | :--- | :--- | :--- |
| **A（推荐）** | `/dev/null`（等价 `< nul`） | rc=5，`BEFORE-PAUSE` → 提示 → `AFTER-PAUSE` | **否，立即返回** ✅ |
| **B（推荐）** | 命令行内联 `cmd /c "s.bat < nul"` | rc=5，同上 | **否，立即返回** ✅ |
| C | `/dev/zero` | rc=5，同上 | 否（`/dev/zero` 不是 EOF，wine 把 NUL 字节当按键；**不能证伪**） |

**结论**：`poc-samples.md` §4 的 **S1 方案（`< nul`）成立**，可解锁语料中 **53.7% 的交互式脚本**。
真实 Windows 上 `pause` 在 stdin EOF 时同样立即返回——**但这一点仍须在 VM 上复核**（wine ≠ Windows）。

## 6. 附带发现：输出编码 = 控制台代码页（GBK）

`pause` 的提示文本在 `cat -A` 下显示为 `M-GM-kM-0M-4M-HM-NM-RM-bM-<M-|M-<M-LM-PM-x...`，
即 **GBK/CP936 字节序列**（`请按任意键继续. . .`）——不是 UTF-8。

这**实证了 `poc-samples.md` §6 的编码判断**：
- `cmd.exe` 的内建输出走**控制台代码页**（zh-CN → CP936），与脚本文件自身的编码**无关**。
- 因此 `guest-exec` 返回的 **base64 原始字节必须按 CP936 解码**，否则指纹里全是乱码。
- 佐证：本机 wine 继承了宿主的 zh-CN 区域设置，故自动选择 CP936。

> 真实 VM 上该结论**取决于安装时的区域/语言选择**。若装 en-US，代码页将是 CP437/CP850，
> 此时**中文夹具会乱码**。→ **建议 VM 安装时选中文（简体）区域**，与语料主体（GBK 中文批处理）一致。
> 这一点**已回写至 `poc-verdict.md` 的「下一步」**作为建域时的决策项。

## 7. 局限与合规声明

| 项 | 说明 |
| :--- | :--- |
| **非权威** | Wine 的 `cmd.exe` 是重实现。**`call`/`goto`/`%~dp0`/`delayedexpansion`/代码页 等行为可能与真实 Windows 不同。** 本文件不构成 PoC 通过依据。 |
| 未覆盖 | 未测 GBK 脚本正文、注册表、`wmic`、`reg`、服务、UAC、权限 —— 这些正是 wine 最不可信、也最需要真实 Windows 的部分 |
| 仓库影响 | **零**。样本来自 `research/`，运行在 `~/.cache/` 隔离前缀，`git status` 仅显示新增 `research/`（见 `poc-verdict.md`） |
| 临时产物 | `~/.cache/bat2sh-wine-poc/`（376 MB，仓库外）、`/tmp/p{1,2}.{out,err}`、`/tmp/pa,pb,pc.out` |
| 副作用 | 未触碰用户既有 `~/.wine` 前缀 |

---

**结论：样本语法与预期行为已在 wine 上钉死。这不能替代真实 Windows 验证，但把等 ISO 期间的不确定性从「样本对不对」收敛为「通路通不通」一个问题。**
