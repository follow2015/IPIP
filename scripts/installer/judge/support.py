"""系统支持矩阵 —— 哪些系统能装、哪些直接拒绝、拒绝时怎么指路。


"这个系统支不支持"是个**判据**，不是动作。项目的一贯纪律是：判据写成可测的
纯函数，动作交给执行层。散在 `ensure_*` 里的 if 分支没法测、没法统一改口径，
而且最容易出的事故是**沉默**：某个老系统上悄悄用错误的包名装了一半。

所以这里集中定义，并对每条拒绝给出**可执行的指路**（要么升级，要么自己装好
前置条件再来），而不是甩一句"不支持"。


- **supported**：有实测配方，装上就能用。
- **manual**：能跑，但需要用户自行准备 Python 3.14 与 MySQL 8.4
  （发行版源给不出合格版本，且我们不为它维护源码编译路径）。
  不拒绝安装，只是**不代劳**，并明确告诉用户缺什么、怎么装。
- **rejected**：系统太老，拒绝安装。原因通常不是"我们不想支持"，
  而是**基础组件在那些系统上凑不齐**（glibc / openssl 太老，
  编译 CPython 3.14 会失败；MySQL 8.4 官方也不再为它们出包）。


| 系统 | 为什么拒绝 |
|---|---|
| CentOS 7 | 已 EOL（2024-06）。glibc 2.17 / openssl 1.0.2，编译 CPython 3.14 会因缺 `OPENSSL_API_3` 失败；MySQL 8.4 官方源无 el7 包 |
| CentOS 8 / Rocky 8 | 已 EOL。MySQL 8.4 官方无 el8 包（只有 el9/el10） |
| Ubuntu 18.04 / 20.04 | 已过标准支持期；glibc 与 openssl 版本不足以构建 3.14 |
| Debian 10 / 11 | 同上（Debian 11 的 openssl 1.1.1 需额外处理） |

⚠️ 这些是**实测/查证过的硬限制**，不是保守估计。宁可明确拒绝并指路，
也不要装到一半失败 —— 后者留下的是个半安装状态，比没装更难收拾。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .facts import HostFacts

__all__ = [
    "SupportLevel",
    "SupportVerdict",
    "MATRIX",
    "REJECTED_MATRIX",
    "SUPPORTED_MATRIX",
    "judge_support",
    "MIN_RECOMMENDED",
]


class SupportLevel:
    SUPPORTED = "supported"
    MANUAL = "manual"
    REJECTED = "rejected"


MIN_RECOMMENDED = (
    "Ubuntu 24.04 LTS / Ubuntu 26.04",
    "Debian 12 / 13",
    "Rocky Linux 10 / AlmaLinux 10 / CentOS Stream 10",
)


@dataclass
class SupportVerdict:
    level: str
    reason: str = ""
    advice: list[str] = None  # type: ignore[assignment]
    extra_minutes: int = 0
    python_via_uv: bool = False

    def __post_init__(self) -> None:
        if self.advice is None:
            self.advice = []

    @property
    def ok(self) -> bool:
        return self.level != SupportLevel.REJECTED



def _load_matrix() -> dict[tuple[str, str], tuple[str, str, str]]:
    """从 supported-systems.conf 读支持矩阵。

    数据源统一在 ``scripts/installer/supported-systems.conf`` —— 那个文件
    **同时被 install.sh 的 bootstrap 用 shell 读**。两份实现读一份数据，
    是为了让"拒绝系统"这件事在**没有合格 Python 的机器上**也能完成：
    installer 全部 .py 都要 3.14 才能解析，而 CentOS 7 自带 2.7.5，
    用户看到的会是一段 pkgutil.py 内部 traceback，完全不知道撞上的是
    "系统不受支持"。

    格式：``发行版|版本前缀|级别|原因|怎么办``
    （见 conf 文件头注释；``\\n`` 是字面量两字符，此处还原成真换行）

    出错时**明确指出行号**（不是 ``raw!r``）—— 数据文件很容易被手改，
    没有行号的报错在几百行里找不出是哪一条。
    """
    out: dict[tuple[str, str], tuple[str, str, str]] = {}
    path = Path(__file__).resolve().parent.parent / "supported-systems.conf"
    if not path.is_file():
        raise ValueError(f"支持矩阵数据文件不存在：{path}")
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) != 5:
            raise ValueError(
                f"{path.name}:{lineno} 不是 5 段（用 | 分隔）"
                f"，实际 {len(parts)} 段：{line!r}"
            )
        distro, prefix, level, reason, advice = (x.strip() for x in parts)
        if level not in ("supported", "rejected", "manual"):
            raise ValueError(
                f"{path.name}:{lineno} 级别 {level!r} 无效"
                "（应为 supported / rejected / manual）"
            )
        out[(distro, prefix)] = (
            level,
            reason.replace("\\n", "\n"),
            advice.replace("\\n", "\n"),
        )
    if not out:
        raise ValueError(f"{path} 里一条配置都没有 —— 数据文件被清空了？")
    return out


_MATRIX_CACHE: dict[tuple[str, str], tuple[str, str, str]] | None = None


def _matrix() -> dict[tuple[str, str], tuple[str, str, str]]:
    """取支持矩阵（首次调用时读盘并缓存）。"""
    global _MATRIX_CACHE
    if _MATRIX_CACHE is None:
        _MATRIX_CACHE = _load_matrix()
    return _MATRIX_CACHE


class _MatrixView(dict):
    """``{(发行版, 版本前缀): (原因, 怎么办)}`` 的只读视图，按级别筛选。

    做成 dict 子类是为了让调用方（与既有测试）继续用 ``.items()`` /
    ``in`` / ``[]`` 的常规写法，同时把"读盘"推迟到第一次用到它。
    """

    __slots__ = ("_level",)

    def __init__(self, level: str) -> None:
        super().__init__()
        self._level = level

    def _data(self) -> dict:
        return {
            k: (reason, advice.split("\n") if advice else [])
            for k, (lvl, reason, advice) in _matrix().items()
            if lvl == self._level
        }

    def items(self):  # type: ignore[override]
        return self._data().items()

    def keys(self):  # type: ignore[override]
        return self._data().keys()

    def values(self):  # type: ignore[override]
        return self._data().values()

    def get(self, k, default=None):  # type: ignore[override]
        return self._data().get(k, default)

    def __getitem__(self, k):  # type: ignore[override]
        return self._data()[k]

    def __contains__(self, k) -> bool:  # type: ignore[override]
        return k in self._data()

    def __iter__(self):  # type: ignore[override]
        return iter(self._data())

    def __len__(self) -> int:  # type: ignore[override]
        return len(self._data())


class _AllMatrixView(_MatrixView):
    """``{(发行版, 版本前缀): (级别, 原因, 怎么办)}`` —— 含级别。"""

    def _data(self) -> dict:
        return dict(_matrix())


MATRIX = _AllMatrixView("")

REJECTED_MATRIX = _MatrixView(SupportLevel.REJECTED)

SUPPORTED_MATRIX = _MatrixView(SupportLevel.SUPPORTED)


def _version_matches(distro_version: str, prefix: str) -> bool:
    """VERSION_ID 与拒绝条目前缀是否匹配。

    用前缀而不是等值：Ubuntu 是 "24.04"，CentOS 是 "7"，Debian 是 "12"，
    形态不统一；而 "20.04.6" 这种补丁版也要能匹配 "20.04"。
    """
    if not prefix:
        return True                      # 空前缀 = 该发行版全系列
    v = (distro_version or "").strip()
    if not v:
        return False                     # 版本读不到时不猜，交给别处报错
    return v == prefix or v.startswith(prefix + ".")


def judge_support(f: HostFacts) -> SupportVerdict:
    """判定当前系统属于 supported / manual / rejected。

    ⚠️ 顺序有讲究，**三层都不能调换**：

    1. **非 systemd 环境最优先**。它是与发行版无关的硬约束（ADR-003 依赖
       systemd 托管进程），容器/WSL1 都落这里。若放到发行版查表之后，
       一个 ubuntu 24.04 的**容器**会因为命中 supported 而被放行 ——
       实测踩到：`test_no_systemd_is_rejected` 正是这么红的。

    2. 发行版查表：**先 rejected 再 supported**。反过来的话，将来若同一
       发行版同时出现在两张表里（加了新配方却忘了删旧的拒绝项），先判
       supported 会**放行一个我们已知装不上的系统**；先判 rejected 只是
       保守拒绝，用户可加 --force-unsupported 绕过。前者不可恢复。
    """
    if f.init_system != "systemd":
        reason = ("未检测到 systemd。本项目依赖 systemd 托管进程（ADR-003）。"
                  if f.init_system in ("unknown", "") else
                  "检测到 systemctl 二进制但 PID 1 不是 systemd（容器？）。"
                  "本项目依赖 systemd 托管进程（ADR-003）。")
        return SupportVerdict(
            SupportLevel.REJECTED,
            reason,
            [
                "在完整的 systemd 系统上部署（Debian/Ubuntu/Rocky 等）",
                "容器部署请用镜像方案，不要在容器内跑本安装器",
            ],
        )

    fam = _normalize(f)
    for table, level in ((REJECTED_MATRIX, SupportLevel.REJECTED),
                         (SUPPORTED_MATRIX, SupportLevel.SUPPORTED)):
        for (d, prefix), (reason, advice) in table.items():
            if d == fam and _version_matches(f.distro_version, prefix):
                extra, via_uv = _python_install_plan(f)
                if level == SupportLevel.SUPPORTED:
                    return SupportVerdict(level, extra_minutes=extra,
                                          python_via_uv=via_uv)
                return SupportVerdict(level, reason, list(advice),
                                      extra_minutes=extra, python_via_uv=via_uv)

    extra, via_uv = _python_install_plan(f)
    return SupportVerdict(
        SupportLevel.MANUAL,
        f"发行版 {f.distro} 未在支持矩阵中（未实测）。",
        [
            "推荐系统：" + "、".join(MIN_RECOMMENDED),
            "或自行装好 Python 3.14 与 MySQL 8.4 后加 --skip-syspkg 重跑",
        ],
        extra_minutes=extra,
        python_via_uv=via_uv,
    )


_PPA_PYTHON: tuple[tuple[str, str], ...] = (
    ("ubuntu", "22.04"),
    ("ubuntu", "24.04"),
    ("ubuntu", "26.04"),
)

_RHEL_FAMILIES = ("rocky", "centos", "rhel", "almalinux")

UV_PYTHON_MINUTES = 5


def _python_install_plan(f: HostFacts) -> tuple[int, bool]:
    """补 Python 3.14 的方式与耗时，返回 ``(额外分钟, 是否走 uv)``。

    ⚠️ 这是个**时间承诺**，必须有依据：

    - 已有 3.14 → 0 分钟；
    - Ubuntu 24.04+ 有 deadsnakes → 0（PPA 路径，1 分钟左右）；
    - **RHEL 系 el9 → uv**（python-build-standalone 自带 sqlite 3.53.1，
      规避 el9 系统 sqlite 3.34.1 导致的 AI 降级），分钟级；
    - 其余（含 el10：系统 sqlite 3.46.1 达标）→ 源码编译，十几分钟。
    """
    from ..judge.version import ge

    if f.python_version and ge(f.python_version, "3.14"):
        return 0, False                            # 已经有了，不用动

    fam = _normalize(f)
    for d, v in _PPA_PYTHON:
        if fam == d and _version_matches(f.distro_version, v):
            return 0, False                        # PPA 路径，1 分钟左右

    if fam in _RHEL_FAMILIES and f.distro_major == 9:
        return UV_PYTHON_MINUTES, True

    from ..act.python_build import estimate_build_minutes

    lo, hi = estimate_build_minutes()
    return hi, False                               # 源码编译，取上界


def _normalize(f: HostFacts) -> str:
    """归一化发行版名（与 syspkg._family 口径一致）。"""
    d = (f.distro or "").lower()
    like = (f.distro_id_like or "").lower()
    for fam in ("ubuntu", "debian", "rocky", "centos", "rhel", "almalinux"):
        if fam == d or fam in like:
            return fam
    if "rhel" in like or "fedora" in like:
        return "rhel"
    return d
