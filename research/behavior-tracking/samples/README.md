# PoC 样本（输出效果层最小验证）

本目录是 `research/behavior-tracking/poc-samples.md` 选定样本的实体。

## 文件

| 文件 | 用途 | 预期 stdout | 预期退出码 | 文件系统副作用 |
| :--- | :--- | :--- | ---: | :--- |
| `poc-01-stdout.bat` | 验证 stdout / 特殊字符 / 退出码捕获 | 见下 | **7** | 无 |
| `poc-02-fileops.bat` | 验证文件系统差分 | `beta` | 0 | 建 `work/`、写 `a.txt`/`b.txt`/`c.txt`、删 `b.txt` |

### `poc-01-stdout.bat` 预期 stdout

```
POC-01-START
plain line
tab	separated
caret & ampersand
percent % literal
POC-01-END
```

覆盖点：多行完整性、Tab 字面量、`^&` 转义为字面 `&`、`%%` 转义为字面 `%`、**非零退出码 7**。

### `poc-02-fileops.bat` 预期差分

执行前该目录只有本 README 与两个 `.bat`。执行后新增：

```
work/            （新目录）
work/a.txt       （内容 "alpha"）
work/c.txt       （内容 "alpha"，由 a.txt 复制）
```

`work/b.txt` **建后即删** → **净差分看不到**（这是净差分的已知边界，见 `poc-samples.md` §5）。

## 编码与格式约定

- **纯 ASCII**、**CRLF** 行尾 —— 刻意排除编码变量，使「通路是否通」与「代码页是否正确」两个问题解耦。
- 真实语料的 GBK 问题是**独立一轮**的实验（`poc-samples.md` §6）。

## 许可

这两个文件由本项目自行编写（bat2sh，AGPL-3.0），**可入仓**。
外部无许可语料（`~/下载/bat-master/` 等）**只引用不入仓**，见 `poc-samples.md` §3 P3。

## 尚未执行

⏸ **本目录尚未在任何 Windows 上运行过。** 阻塞项：缺 Windows 10 ISO 与 `virtio-win` ISO，见 `env-audit.md` §4。
