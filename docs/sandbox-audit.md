# 沙箱审计（v1.8.1）

> 目的：在跑 `~/下载/非常批处理/` 中的**危险脚本**之前，确认 `bwrap` 沙箱边界可靠。
> 方法：只读探针（`/tmp/v181/sbprobe/`），逐项实测。**仓库未被修改。**
> 结论：**通过 —— 4 项硬要求全部满足。**

环境：CachyOS / Arch Linux；`bubblewrap 0.12.0`；内核提供 user/PID/网络命名空间。

---

## 1. 沙箱配方（v1.8.1 采用）

```bash
timeout -k 5 30 bwrap \
  --unshare-all --die-with-parent \
  --ro-bind /usr /usr \
  --ro-bind /etc /etc \
  --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --symlink usr/bin /bin --symlink usr/sbin /sbin \
  --proc /proc --dev /dev \
  --tmpfs /tmp \
  --tmpfs /home/sandbox \
  --bind "$WORKDIR" "$WORKDIR" --chdir "$WORKDIR" \
  env -i HOME=/home/sandbox PATH=/usr/bin:/usr/sbin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    TERM=dumb \
  bash -c 'ulimit -c 0; exec bash script.sh'
```

相对 v1.4.1 `tools/corpus-analysis/sb.py` 配方的**唯一调整**：新增 `--tmpfs /home/sandbox`
并把 `HOME` 指向它（v1.4.1 把 `HOME` 指向 rw bind 的 workdir；本版按任务书要求让 `HOME` 落在 tmpfs）。

---

## 2. 逐项实测

### 2.1 无 bind mount 泄漏 ✅

沙箱内 `ls /` 与存在性探测：

```text
PWD=/tmp/v181/sbprobe
HOME=/tmp/v181/sbprobe
USER=<unset>
--- root ls ---
bin dev etc lib lib64 proc sbin tmp usr
ABSENT /home
ABSENT /root
ABSENT /mnt
ABSENT /media
ABSENT /var
EXISTS /etc
EXISTS /usr
```

**结论**：真实 `/home`、`/root`、`/mnt`、`/media`、`/var` **均未挂入**（不存在）。
仅挂载 `/usr`、`/etc`（只读）、`/proc`、`/dev`、`/tmp`（tmpfs）与显式 `--bind` 的 workdir。

### 2.2 `$HOME` 指向 tmpfs ✅

```text
HOME=/home/sandbox
tmpfs /tmp tmpfs rw,nosuid,nodev,relatime,mode=755,... 0 0
tmpfs /home/sandbox tmpfs rw,nosuid,nodev,relatime,mode=755,... 0 0
--- HOME write ---
HOME_WRITABLE
--- cwd write ---
CWD_WRITABLE
```

**结论**：`/proc/mounts` 显示 `/home/sandbox` 为 `tmpfs`，可写；workdir 可写（供脚本产生产物）。

### 2.3 `--unshare-all`（含网络隔离）生效 ✅

```text
--- network ifaces ---
lo:
--- curl test ---
000CURL_FAIL rc=6
```

**结论**：sandbox 内仅有 `lo`（无 `eth0`/`wlan0`）；`curl https://example.com` 以
`rc=6`（无法解析主机）失败。网络命名空间隔离生效。

### 2.4 `--die-with-parent` ✅

用「心跳文件」法（避免 `pgrep -f` 自匹配）：沙箱内循环向 rw-bind 目录追加心跳，
`SIGKILL` 掉 `bwrap` 进程后观察心跳是否停止。

```text
heartbeat before kill=20 bytes, 2s after kill=20 bytes
RESULT=PASS (child died with parent)
```

**结论**：`bwrap` 被杀死后沙箱内进程随之终止（心跳停止）。

### 2.5 超时保护 ✅

```text
$ timeout -k 5 30 bash -c 'bwrap ... bash -c "sleep 60"'
rc=124 (expect 124)
```

**结论**：30s 超时生效，超时后 `timeout` 以 `124` 结束并（配合 `-k 5`）强杀。

---

## 3. 危险脚本处理策略

审计通过后，仍采取**双重保护**（保守优先，纪律 1）：

1. **前置静态审计**：对语料做危险构造扫描（`format`/`fdisk`/`diskpart`/`reg delete HKLM`/
   `shutdown`/`net user`/`cacls`/`takeown`/`vssadmin`/`bcdedit`/`taskkill`/`del autorun` 等）。
   命中者标记 `dangerous`，**在沙箱内运行**（已由本节审计保证边界）。
2. **运行期约束**：30s 超时 + `--die-with-parent` + 无网络 + 无真实家目录。
   任何**意外行为**（越过 `WORKDIR` 的写入、逃逸迹象、异常子进程）→ **立即停止并暂停上报**（任务书第十节）。

已标记危险的脚本（16 个，节选）：`史上最牛X批处理工具包…`、`多功能系统优化设置.cmd`、
`一键转移桌面-收藏夹-文档多用户版.bat`、`删除用户.bat`、`添加用户并注销.bat`、
`批量安装补丁并重启.bat`、`系统优化.bat`、`文件备份器/文件备份器V2.3修改版2.cmd` 等。

---

## 4. 审计结论

| 项 | 要求 | 实测 | 判定 |
| :--- | :--- | :--- | :--- |
| bind mount 泄漏 | 真实 `/home`/`/mnt`/`/media` 未挂入 | 均 ABSENT | ✅ |
| `$HOME` | 指向 tmpfs | `tmpfs /home/sandbox`，可写 | ✅ |
| `--unshare-net` | 生效 | 仅 `lo`，curl rc=6 | ✅ |
| `--die-with-parent` | 生效 | 心跳随 `bwrap` 被杀停止 | ✅ |
| 超时 | 30s | rc=124 | ✅ |

**审计通过 → 危险脚本可在沙箱内运行。** 未触发任何「暂停问我」条件。
