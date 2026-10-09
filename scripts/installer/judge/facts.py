"""宿主机事实采集 —— 安装器对「这台机器是什么」的唯一认知来源。

旧 install.sh 最大的结构性缺陷就是没有这一层：它只有零散的
``command -v apt-get`` 探测，没有「发行版 × 版本 × 架构」的模型。
所以补 MySQL/Redis/Node 安装 + 多发行版 + 多架构这件事，本质上要先有这层。

设计原则：

- **只读**。采集过程中不做任何修改系统的动作，方便反复调用与安全重试。
- **判定内外有别**。比如发现 `pnpm` 二进制**不等于** pnpm 可用
  （corepack 会留下"可执行但一跑就崩"的 shim），这类"会不会用"的问题
  留給具体动作层去做冒烟，facts 只回答"有没有"。
- **未知优于猜测**。版本解析不出来就返回空串，让调用方按自己的策略处理，
  不要猜一个"大概够了"。
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path

from .version import BASELINES, ge, gt

__all__ = ["HostFacts", "collect", "Issue", "check_baselines"]


@dataclass
class HostFacts:
    """一台机器的只读画像。"""

    distro: str = ""              # ubuntu | debian | centos | rocky | rhel | unknown
    distro_version: str = ""      # 24.04 / 12 / 9
    distro_id_like: str = ""
    arch: str = ""                # x86_64 | aarch64
    pkg_manager: str = ""         # apt | dnf | yum | ""
    init_system: str = ""         # systemd | other | ""
    is_root: bool = False
    python_bin: str = ""
    python_version: str = ""
    python_any_version: str = ""
    node_version: str = ""
    pnpm_version: str = ""
    mysql_client: str = ""
    mysql_version: str = ""
    redis_version: str = ""
    has_gpp: bool = False
    has_systemctl: bool = False
    has_rsync: bool = False
    has_sudo: bool = False
    raw: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def wheel_arch_tag(self) -> str:
        """PEP 600 风格平台标签。

        Linux x86_64 是 ``manylinux_2_28_x86_64`` —— **不是** ``linux_x86_64``。
        写成后者会全 404，而且这个错配历史上被误判成"镜像没有这个版本"。
        """
        return {
            "x86_64": "manylinux_2_28_x86_64",
            "aarch64": "manylinux_2_28_aarch64",
        }.get(self.arch, "")

    @property
    def cp_tag(self) -> str:
        """当前所选 Python 的 ABI 标签（``cp314``）。"""
        parts = self.python_version.split(".")
        if len(parts) >= 2 and parts[0] == "3" and parts[1].isdigit():
            return f"cp3{parts[1]}"
        return ""

    @property
    def distro_major(self) -> int:
        """发行版主版本号，供执行层按 EL 大版本分发配方。

        ``"9"`` / ``"9.4"`` → ``9``，``"10"`` → ``10``，解析不出返回 ``0``
        （``0`` 让调用方按"未知版本"保守处理，而不是抛异常）。
        """
        head = re.match(r"\d+", (self.distro_version or "").strip())
        return int(head.group()) if head else 0

    @property
    def python_display(self) -> str:
        """给人看的一行 Python 现状，**区分三种处境**。

        这三种如果都显示成空串，用户只能看到 ``Python`` 后面啥也没有，
        根本不知道是"没装"还是"装了但太老"：

        - ``3.14.0``                  —— 合格，直接用
        - ``3.9.10（低于基线）``      —— 有，但要升级/源码编译
        - ``未安装``                  —— 真的没有

        实测来源：CentOS Stream 9 自带 3.9.10，改造前显示为空，
        与"全新裸机"完全同形。
        """
        if self.python_version:
            return self.python_version
        if self.python_any_version:
            return f"{self.python_any_version}（低于基线）"
        return "未安装"


@dataclass
class Issue:
    """一条基线偏差。"""

    component: str
    current: str
    required: str
    fatal: bool
    note: str = ""

    def __str__(self) -> str:
        level = "FATAL" if self.fatal else "WARN "
        base = f"[{level}] {self.component}: 当前 {self.current or '缺失'} < 要求 {self.required}"
        return base + (f"\n        {self.note}" if self.note else "")


def _read_os_release() -> dict[str, str]:
    try:
        text = open("/etc/os-release", encoding="utf-8").read()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def _pick_pkg_manager() -> str:
    from shutil import which

    for mgr in ("apt-get", "dnf", "yum", "apk", "zypper"):
        if which(mgr):
            return {"apt-get": "apt"}.get(mgr, mgr)
    return ""


def _version_of(cmd: list[str], pattern: str, timeout: float = 5.0) -> str:
    """跑一次命令并正则取出版本号。任何失败都返回空串（不抛）。"""
    import subprocess

    from shutil import which

    if not which(cmd[0]):
        return ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(pattern, (proc.stdout or "") + (proc.stderr or ""))
    return m.group(1) if m else ""


def _pick_python(minimum: str) -> tuple[str, str, str]:
    """按 install.sh 的既定顺序挑第一个满足基线的解释器。

    顺序不能改成"有就用 python3"：要的是**满足 3.14 的那个**，不是第一个存在的。

    返回 ``(路径, 版本, 任意版本)`` —— 第三个是**不管满不满足基线**、
    机器上真实存在的那个版本。区分这两者是有意义的：
    CentOS Stream 9 自带 3.9.10，只报 ``python_version=""`` 会让它和
    "完全没装 Python" 的机器长得一样，而处置方式完全不同。
    """
    from shutil import which

    candidates = ["/usr/local/bin/python3.14",
                  "python3.14", "python3.13", "python3.12", "python3",
                  "python3.11", "python3.10"]
    any_version = ""
    for name in candidates:
        path = os.access(name, os.X_OK) if "/" in name else which(name)
        if not path:
            continue
        version = _version_of([name, "-c", "import sys;print('%d.%d.%d'%sys.version_info[:3])"], r"([\d.]+)")
        if version and (not any_version or gt(version, any_version)):
            any_version = version
        if ge(version, minimum):
            return path, version, any_version
    return "", "", any_version


def collect(min_python: str | None = None) -> HostFacts:
    """一次性采集本机全部事实。"""
    from shutil import which

    osr = _read_os_release()
    f = HostFacts(
        distro=(osr.get("ID") or "unknown").lower(),
        distro_version=osr.get("VERSION_ID") or "",
        distro_id_like=(osr.get("ID_LIKE") or "").lower(),
        arch=platform.machine(),
        pkg_manager=_pick_pkg_manager(),
        is_root=os.geteuid() == 0,
        has_systemctl=bool(which("systemctl")),
        has_rsync=bool(which("rsync")),
        has_sudo=bool(which("sudo")),
        has_gpp=bool(which("g++")),
        raw=osr,
    )
    f.init_system = (
        "systemd" if (f.has_systemctl and which("systemd-analyze")
                      and Path("/run/systemd/system").is_dir())
        else "systemd-unnormal" if f.has_systemctl
        else "unknown"
    )

    f.python_bin, f.python_version, f.python_any_version = _pick_python(
        min_python or BASELINES["python"]
    )

    if which("node"):
        f.node_version = _version_of(["node", "-v"], r"v?([\d.]+)")
    if which("pnpm"):
        f.pnpm_version = _version_of(["pnpm", "--version"], r"([\d.]+)")
    for client in ("mysql", "mysql8", "mariadb"):
        if which(client):
            f.mysql_client = client
            ver = _version_of([client, "--version"], r"([\d]+\.[\d]+\.[\d]+)")
            if _version_of([client, "--version"], r"(?i)(mariadb)"):
                f.mysql_version = ""
            else:
                f.mysql_version = ver
            break
    if which("redis-server"):
        f.redis_version = _version_of(["redis-server", "--version"], r"v=([\d.]+)")
    elif which("redis-cli"):
        f.redis_version = (_version_of(["redis-cli", "--version"], r"v=([\d.]+)")
                           or _version_of(["redis-cli", "--version"], r"([\d.]+)"))

    return f


def check_baselines(f: HostFacts) -> list[Issue]:
    """把事实相对基线做体检，返回偏差清单。

    分级口径照搬 install.sh：**已被实测证实会中断安装/运行的项才是 fatal**，
    仅仅"未在本机 dev 验证过"的项只 warn —— 否则会把大量能跑通的环境挡在门外。
    """
    issues: list[Issue] = []

    if not ge(f.python_version, BASELINES["python"]):
        issues.append(Issue(
            "python", f.python_version, BASELINES["python"], True,
            "realtime_gateway 的 asyncio.AsyncGenerator 需 3.14+，低于此版本启动即崩。",
        ))
    if not ge(f.node_version, BASELINES["node"]):
        issues.append(Issue(
            "node", f.node_version, BASELINES["node"], False,
            "前端构建才需要；低于基线会导致 rolldown 原生 binding 被 pnpm 静默跳过。",
        ))
    if f.mysql_client and not ge(f.mysql_version, BASELINES["mysql"]):
        issues.append(Issue(
            "mysql", f.mysql_version, BASELINES["mysql"], False,
            "8.0.x 实测可跑通部署，属「未验证组合」；注意 json/payroll 相关 SQL 行为差异。",
        ))
    if f.redis_version and not ge(f.redis_version, BASELINES["redis"]):
        issues.append(Issue(
            "redis", f.redis_version, BASELINES["redis"], False,
            "基础功能可用，属「未验证组合」。",
        ))
    return issues
