# tools/oracle —— wine cmd 黄金行为对照 harness

> v1.9.2（B3）落盘。把「bat → bash 转换的运行时语义」从人工判断变为**可回归**。

## 用途

用 wine 的 `cmd.exe` 执行源 `.bat`，与 `bat2sh` 产物经 `bash` 执行的结果**规范化后逐例比对**，
用于抓**运行时语义缺陷**——这类缺陷既不是语法错误，也未必带 `# TODO`
（例：v1.9.2 修复的 A1 `%VAR%` 冻结语义丢失，产物无 TODO、`bash -n` 通过、但行为错）。

## oracle 权威顺序（重要）

```
真机 cmd / 官方文档  >  wine  >  （不可用）ChenPi11/cmd
```

- **wine 是重实现，只作初筛**（R5）。wine 与 bat2sh 不一致时，**不得**直接判 bat2sh 有错。
- **ChenPi11/cmd 不能作 oracle**：其在 053 构造上输出错误结果（见
  `docs/research/chenpi11-cmd-reference.md` §2.3）。

### wine 不可信的两处（本 harness 不以 wine 断言）

| 探针 | 现象 | 处置 |
| :--- | :--- | :--- |
| **X5** `echo 1.0.1>out.txt` | wine 不吞位（落盘 `1.0.1`）；真实 cmd 把紧邻 `>` 的数字当**文件句柄** | 需真机；结论依据 `utils.py:228` 设计意图 + cmd 文档 |
| **A8** `findstr a b file.txt` | wine findstr **自相矛盾**（`a b file` 有输出、`alpha gamma file` 无输出） | 需真机/官方文档，**不得用 wine 定切分** |

见 `UNRELIABLE_PROBES`（`golden_harness.py`）。

## 用例（`cases/`）

| 用例 | 构造 | 说明 |
| :--- | :--- | :--- |
| g01 | 053 同构（`for`+嵌套 `if/else(`，两分支） | 块结构 |
| g02 | 053 同构（else 体命中） | 块结构 |
| g03 | 多行 `if/else` | 块结构 |
| g04 | `!v!` 延迟展开 | 执行时取值（不得变化） |
| **g05** | **`%v%` 立即展开** | **A1：解析时冻结**（v1.9.2 前为 DIFF） |
| g06 | 114 自引用 `!str1!%%i` | 延迟展开自引用 |

> **g05 故事**：v1.9.2 前 wine `i=1 i=1` vs bat2sh `i=2 i=2`（A1 缺陷）；
> A1 修复后 6/6 MATCH。该用例即「6 例中唯一不匹配」的归因（= bat2sh 缺陷，非 wine 局限）。

## 用法

```bash
python3 tools/oracle/golden_harness.py     # 无 wine 时 SKIP（exit 0）
pytest tests/test_oracle_wine.py -q        # 无 wine 时 skip
```

无 wine / 无 bash 时跳过而非失败，与 CI 语料策略一致。
`wine_available()` 还要求当前 `HOME` 下存在默认 wine prefix 的 `cmd.exe`
（这样 `release-preflight.sh` 的空 `HOME` 环境会正确 skip，而非误失败）。
