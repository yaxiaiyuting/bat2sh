"""注册表只读键到 bash 的映射规则表（v1.6.0 阶段 B）。

依据 docs/research/b2-registry-mapping.md：仅覆盖有证据支持的字面量键 + 只读操作
（read/test/enumerate）。写类、``.reg`` 生成/导入、COM WScript.Shell、
.NET Microsoft.Win32.Registry、动态/变量键路径一律不在此映射，交由调用方发出
结构化 TODO。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .utils import dq

REBOOT_REQUIRED_PROBE = (
    "{ [ -e /var/run/reboot-required ] "
    "|| { command -v needs-restarting >/dev/null 2>&1 && ! needs-restarting -r >/dev/null 2>&1; }; }"
)

REBOOT_WARNING = (
    "重启检测已按 Linux 发行版探针近似（/var/run/reboot-required、needs-restarting），"
    "语义与 Windows Update 注册表标记不同，请核对"
)

OS_RELEASE_WARNING = (
    "系统版本已映射到 /etc/os-release（PRETTY_NAME/VERSION_ID），"
    "字段语义与 Windows 版本号不同，请核对"
)

_OS_RELEASE_PRETTY = '. /etc/os-release 2>/dev/null; printf \'%s\\n\' "${PRETTY_NAME:-$(uname -s)}"'
_OS_RELEASE_VERSION = '. /etc/os-release 2>/dev/null; printf \'%s\\n\' "${VERSION_ID:-$(uname -r)}"'

BIOS_WARNING = (
    "硬件信息已映射到 /sys/class/dmi/id/*，字段名与 Windows BIOS 键不同，请核对"
)

PACKAGE_WARNING = (
    "安装检测已映射到 Linux 包管理器查询（dpkg-query/rpm/pacman），"
    "Windows 显示名与发行版包名不同，请核对"
)

MIME_WARNING = (
    "文件关联已映射到 xdg-mime query default（输出 .desktop 名称），"
    "与 Windows 默认程序语义不同，请核对"
)

_MIME_KEY_RE = re.compile(
    r"(?i)^(?:HKCR|HKEY_CLASSES_ROOT|HKLM:\\SOFTWARE\\CLASSES):?\\(\.[^\\\s]+)$"
)


def _mime_default(ext: str) -> str:
    return (
        f"__f=$(mktemp --suffix={dq(ext)}) && "
        'xdg-mime query default "$(xdg-mime query filetype "$__f")"; rm -f "$__f"'
    )


def _package_query(app: str) -> str:
    quoted = dq(app)
    return (
        "if command -v dpkg-query >/dev/null 2>&1; then "
        f"dpkg-query -W {quoted} 2>/dev/null || echo 'not installed: {app}'; "
        "elif command -v rpm >/dev/null 2>&1; then "
        f"rpm -q {quoted} 2>/dev/null || echo 'not installed: {app}'; "
        "elif command -v pacman >/dev/null 2>&1; then "
        f"pacman -Q {quoted} 2>/dev/null || echo 'not installed: {app}'; "
        "else echo 'unknown package manager'; fi"
    )


def _package_list() -> str:
    return (
        "if command -v dpkg-query >/dev/null 2>&1; then dpkg-query -W; "
        "elif command -v rpm >/dev/null 2>&1; then rpm -qa; "
        "elif command -v pacman >/dev/null 2>&1; then pacman -Q; "
        "else echo 'unknown package manager'; fi"
    )

_BIOS_FIELDS = {
    "SYSTEMMANUFACTURER": "sys_vendor",
    "SYSTEMPRODUCTNAME": "product_name",
    "SYSTEMVERSION": "product_version",
    "SYSTEMFAMILY": "product_family",
    "BASEBOARDMANUFACTURER": "board_vendor",
    "BASEBOARDPRODUCT": "board_name",
    "BIOSVENDOR": "bios_vendor",
    "BIOSVERSION": "bios_version",
}


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
    if op == "enumerate":
        return _lookup_enumerate(normalized)
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
    if normalized.endswith("\\WINDOWS NT\\CURRENTVERSION"):
        if value == "PRODUCTNAME":
            return RegistryRead(_OS_RELEASE_PRETTY, OS_RELEASE_WARNING)
        if value in ("CURRENTVERSION", "CURRENTBUILDNUMBER"):
            return RegistryRead(_OS_RELEASE_VERSION, OS_RELEASE_WARNING)
    if normalized.endswith("\\HARDWARE\\DESCRIPTION\\SYSTEM\\BIOS"):
        field = _BIOS_FIELDS.get(value)
        if field is not None:
            return RegistryRead(
                f"cat /sys/class/dmi/id/{field} 2>/dev/null || true", BIOS_WARNING
            )
    if "\\CURRENTVERSION\\UNINSTALL" in normalized:
        match = re.search(r"(?i)\\Uninstall\\(.+)$", key)
        if match:
            return RegistryRead(_package_query(match.group(1)), PACKAGE_WARNING)
        if normalized.endswith("\\UNINSTALL"):
            return RegistryRead(_package_list(), PACKAGE_WARNING)
    mime = _MIME_KEY_RE.match(key)
    if mime:
        return RegistryRead(_mime_default(mime.group(1)), MIME_WARNING)
    return None


def _lookup_enumerate(normalized: str) -> RegistryRead | None:
    if normalized.endswith("\\CURRENTVERSION\\UNINSTALL"):
        return RegistryRead(_package_list(), PACKAGE_WARNING)
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
