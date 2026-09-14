# 真实语料 fixtures（real-corpus）

## 来源

- 目录：`fleschutz/`（60 个 `.ps1`）
- 上游：`fleschutz/PowerShell`（`PowerShell-1.6` 快照，`scripts/` 目录）
- 许可：**CC0 1.0 Universal**（见同目录 `LICENSE`），可自由复制、修改、分发

## 选样规则（确定性）

1. 取 `scripts/*.ps1` 全量按文件名排序；
2. 取前 60 个（`sorted(...)[:60]`）；
3. 不做任何手工挑选或改写（保持上游原文，仅复制）。

## 用途与边界

- 用途：发布门槛中的"真实语料交叉验证"（`docs/testing-strategy.md`）：转换管线不得崩溃，
  且无论是否整体降级，产物必须是**语法合法的 bash**（never emit broken bash）。
- 不在测试中断言"转换质量"指标（如语义正确率）——PowerShell 侧为实验性支持，
  降级属于已知行为，质量数据以 `docs/real-corpus-report.md` 的诊断口径为准。
- 新增/替换语料时必须同步更新本说明与选样规则，并保持 ≥ 50 个独立脚本。
