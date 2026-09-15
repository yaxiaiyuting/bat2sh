"""注册表只读键到 bash 的映射规则表（v1.6.0 阶段 B）。

依据 docs/research/b2-registry-mapping.md：仅覆盖有证据支持的字面量键 + 只读操作
（read/test/enumerate）。写类、``.reg`` 生成/导入、COM WScript.Shell、
.NET Microsoft.Win32.Registry、动态/变量键路径一律不在此映射，交由调用方发出
结构化 TODO。
"""

from __future__ import annotations

from dataclasses import dataclass

REBOOT_REQUIRED_PROBE = (
    "{ [ -e /var/run/reboot-required ] "
    "|| { command -v needs-restarting >/dev/null 2>&1 && ! needs-restarting -r >/dev/null 2>&1; }; }"
)

REBOOT_WARNING = (
    "重启检测已按 Linux 发行版探针近似（/var/run/reboot-required、needs-restarting），"
    "语义与 Windows Update 注册表标记不同，请核对"
)


@dataclass(frozen=True)
class RegistryRead:
    """一条注册表只读映射：``bash`` 为可直接嵌入的 bash 片段。"""

    bash: str
    warning: str
    is_test: bool = False


def normalize_key(key: str) -> str:
    return key.replace("/", "\\").rstrip("\\").upper()


def _raw(key: str) -> str:
    return key.replace("/", "\\").rstrip("\\")


def lookup(key: str, value: str = "", op: str = "read") -> RegistryRead | None:
    """按 (键路径, 值名, 操作) 查表；无匹配返回 None（调用方发结构化 TODO）。"""
    normalized = normalize_key(key)
    name = value.strip().upper()
    if op == "test":
        return _lookup_test(normalized, name)
    if op == "read":
        return _lookup_read(_raw(key), normalized, name)
    return None


def _lookup_test(key: str, value: str) -> RegistryRead | None:
    if key.endswith("\\WINDOWSUPDATE\\AUTO UPDATE\\REBOOTREQUIRED"):
        return RegistryRead(REBOOT_REQUIRED_PROBE, REBOOT_WARNING, is_test=True)
    if key.endswith("\\COMPONENT BASED SERVICING\\REBOOTPENDING"):
        return RegistryRead(REBOOT_REQUIRED_PROBE, REBOOT_WARNING, is_test=True)
    if key.endswith("\\CONTROL\\SESSION MANAGER") and value in ("", "PENDINGFILERENAMEOPERATIONS"):
        return RegistryRead(REBOOT_REQUIRED_PROBE, REBOOT_WARNING, is_test=True)
    return None


def _lookup_read(key: str, normalized: str, value: str) -> RegistryRead | None:
    return None


def hint_for(key: str, op: str = "read") -> str:
    """针对已知用途给出更具体的 TODO 提示（无对应物等价映射时的引导）。"""
    k = normalize_key(key)
    if "\\SYSTEM\\CURRENTCONTROLSET\\SERVICES\\" in k:
        return (
            "服务配置读取：Windows 服务名在 Linux 无对应 systemd unit，"
            "请改用 systemctl is-active/is-enabled/show 人工核对（无证据做名称映射）"
        )
    return ""
