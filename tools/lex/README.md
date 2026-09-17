# tools/lex —— 词法层残余额账只读报告

> v1.10.0rc1（Session C-lex）落盘。把词法层 4 条残余（044/059/135/138，3 机制）
> 的台账固化为**可重跑的只读报告**。

## 用途

```bash
python3 tools/lex/lexical_report.py            # 台账校验 + 漂移检测 + 语料复现
python3 tools/lex/lexical_report.py --no-corpus
```

1. `validate_lexical_residuals()`：台账完整性（evidence 必填、置信度光谱、只读）；
2. **漂移检测**：把每条残余的 `trigger` 跑过转换器，确认仍复现「逸出」守卫
   （若某条已修，报 `DRIFT`，提示更新台账）；
3. **语料复现**（可选）：统计语料中触发守卫的文件，核对台账 `ids ⊆ 触发集合`。
   本工具**不跑沙箱**，故无法判定 `rc==0`；语料中额外触发者（031/047/077/143）
   含语法失败/rc≠0，是否 degraded 需沙箱确认。

**只读**：不写仓库、不改转换器、不跑沙箱。默认语料 `~/下载/非常批处理`；缺失时不判失败。

## 口径

- 守卫消息 = `core/batch.py:2695-2703` 的
  `循环变量 %%x 逸出 for 循环（块结构失同步）`；
- 台账见 `python/bat2sh/core/lexical_residuals.py`；
  根因与修复草案见 `docs/session-lex-design.md`。

## 与 v2.0 的关系

本工具**不改转换**：4 条残余因**无文件翻转收益**且落在**块栈核心 / A1 热路径**，
已在 `docs/session-lex-review.md` 裁定「退回设计文档」；LF-1 随 v2.0 解析层处理。
