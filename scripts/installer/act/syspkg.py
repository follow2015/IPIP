"""系统依赖安装 —— 补全 install.sh 从来就没打算管的那部分。

旧脚本的心智模型是「假设机器已经准备好了」：node 找不到直接 die、redis 找不到
直接 die、mysql server 缺失则一路走到第 5 步才炸，全程只给用户一串安装 URL。
这是它最大的结构性缺口。

这里用**表驱动矩阵**组织配方，原因很实际：要覆盖的是

    distro(ubuntu/debian/centos/rocky) × distro_ver × arch × 组件(python/node/mysql/redis)

这个叉乘在 bash 里会退化成一坨 case + if 的地狱（旧脚本缺 chronic 发行版识别
正是同一件事的另一面）。

一条纪律：**未实测的发行版直接报错**，不猜包名。猜错的代价远大于明确地失败 ——
`apt-get install mysql-server` 在错误的源上只会报 `Unable to locate package`，
这个报错指向包名，会让人去怀疑"这个发行版是不是没有这个包"。


原先的结论是「官方 apt 源只有 8.0，达不到基线 8.4，属未验证组合」。
**这个结论是错的**，根源是只查了一个镜像：

| 镜像 | apt 路径 | 有 8.4 吗 |
|---|---|---|
| 中科大 `/mysql-repo/apt/ubuntu/dists/noble/` | — | ✗ 只有 8.0 |
| 清华 `/mysql/apt/ubuntu/dists/noble/` | — | ✓ `mysql-8.4-lts/` |
| 清华 `/mysql/yum/` | — | ✓ `mysql-8.4-community-el9-x86_64/` |

实测（真机，2026-10-03）：从清华源可直装
``mysql-community-server 8.4.11-1ubuntu24.04``，**不需要任何编译**。
教训与知识库一致：**单点采样得出的"没有"，只是"我没找到"**。

走官方 MySQL 源而非编译，省掉 10-25 分钟编译时间，也省掉一整套
编译失败风险。代价只是多一个第三方 apt 源。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..act.shell import run, which
from ..judge.facts import HostFacts

__all__ = [
    "Recipe",
    "matrix",
    "ensure_python",
    "ensure_node",
    "ensure_redis",
    "ensure_mysql_server",
    "ensure_build_toolchain",
    "install_raw",
    "UnsupportedPlatform",
]


class UnsupportedPlatform(RuntimeError):
    """当前发行版没有经过实测的配方。"""


@dataclass
class Recipe:
    """某个组件在某个发行版上的安装配方。"""

    packages: list[str]
    prepare: list[list[str]] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    note: str = ""



_DEBIAN_BUILD = Recipe(
    packages=["build-essential", "cmake", "pkg-config"],
    note="chroma-hnswlib 在 PyPI 上只有 sdist，必须本地编译；"
         "而 pip 安装是原子性的 —— 一个包构建失败会导致整个 requirements 都不安装。",
)

_EPEL_PREPARE = [
    ["dnf", "install", "-y", "epel-release"],
]

_CRB_PREPARE = [
    ["bash", "-c",
     "dnf config-manager --set-enabled crb 2>/dev/null || "
     "dnf config-manager set-enabled crb 2>/dev/null || "
     "dnf config-manager --set-enabled powertools 2>/dev/null || true"],
]

_RHEL_BUILD = Recipe(
    packages=["gcc-c++", "cmake", "pkgconfig", "libuuid-devel"],
    prepare=[*_CRB_PREPARE],
    note="chroma-hnswlib 只有 sdist，必须本地编译。"
         "（gcc-c++ 在 appstream、cmake/libuuid-devel 在 CRB，均不需要 EPEL）",
)



MYSQL_GPG_KEY = "https://repo.mysql.com/RPM-GPG-KEY-mysql-2025"

MYSQL_OFFICIAL_APT = "https://repo.mysql.com/apt"
MYSQL_OFFICIAL_YUM = "https://repo.mysql.com/yum"

MYSQL_MIRROR = "https://mirrors.tuna.tsinghua.edu.cn/mysql"




def _mysql_apt_prepare(family: str) -> list[list[str]]:
    """生成 MySQL 官方 apt 源的准备步骤。

    ``family`` 只影响日志文案；真正的代号从机器上读 —— 见上文坑 ②。

    ⚠️ 这里**不再**直接 ``apt-get install curl``：见上方那条注释。
       包装好了不代表命令可用，而命令可用时又根本不需要装。
    """
    return [
        _ensure_curl_cmd_apt(extra=("gnupg",)),
        ["bash", "-c",
         f"curl -fsSL {MYSQL_GPG_KEY} "
         f"| gpg --dearmor -o /usr/share/keyrings/mysql.gpg"
         f" && chmod 644 /usr/share/keyrings/mysql.gpg"],
        ["bash", "-c",
         '. /etc/os-release; code="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"; '
         '[ -n "$code" ] || { echo "无法从 /etc/os-release 确定发行版代号" >&2; exit 1; }; '
         'base="' + MYSQL_MIRROR + '"; '
         f'curl -fsSL -o /dev/null "$base/apt/{family}/dists/$code/Release" '
         f'|| base="{MYSQL_OFFICIAL_APT}"; '
         'echo "deb [signed-by=/usr/share/keyrings/mysql.gpg] '
         '$base/apt/' + family + ' $code mysql-8.4-lts mysql-tools" '
         '> /etc/apt/sources.list.d/mysql.list'
         ],
        ["apt-get", "update"],
    ]


def _ensure_curl_cmd_apt(*, extra: tuple[str, ...] = ()) -> list[str]:
    """apt 侧"确保 curl 可用"的一步 —— 已可用就跳过安装。

    抽成独立函数是为了让它**可被单测**：配方里内联的 bash 片段没法断言。
    ``extra`` 是顺带需要的别的包（如导 key 用的 gnupg）—— 它们与 curl 没有
    包冲突问题，但同样"已有就别再装"。

    写成多行 bash 而不是一条长命令：拼接出来的单行版本一旦出错，
    报错会指向整行，根本看不出是哪一段。这里每步一行的形式，
    日志里能直接看出走的是哪条分支。
    """
    lines = [
        'if command -v curl >/dev/null 2>&1; then',
        '  echo "[syspkg] curl 已可用，跳过安装"',
        'else',
        f'  apt-get install -y ca-certificates curl {" ".join(extra)}'.rstrip(),
        'fi',
    ]
    for pkg, cmd in (("gnupg", "gpg"),):
        if pkg in extra:
            lines += [
                f'command -v {cmd} >/dev/null 2>&1 || apt-get install -y {pkg}',
            ]
    return ["bash", "-c", "\n".join(lines)]


def _ensure_curl_cmd_dnf() -> list[str]:
    """dnf 侧"确保 curl 可用"的一步。

    关键：**先判命令在不在**。CentOS Stream 9 预装 curl-minimal 已提供
    /usr/bin/curl，此时再 ``dnf install curl`` 必然冲突失败（见 ensure_curl 注释）。
    """
    return ["bash", "-c",
            'command -v curl >/dev/null 2>&1 && { echo "[syspkg] curl 已可用，跳过安装"; exit 0; }; '
            'dnf install -y ca-certificates || true; '
            'dnf install -y curl || dnf install -y --allowerasing curl']


def _mysql_yum_prepare(el: int) -> list[list[str]]:
    """生成 MySQL 官方 yum/dnf 源的准备步骤。``el`` 是 EL 主版本号。

    [WARN] ``$basearch`` 必须**原样写进** repo 文件，交给 dnf 自己展开。
    这里有个 heredoc 的坑，2026-10-03 在 CentOS Stream 9 真机上踩到：

        写 repo 用的是 `cat > xxx.repo <<EOF`（**不加引号**）⇒ shell 会把
        heredoc 体里的 ``$basearch`` **当普通变量展开成空串**，而 dnf 拿到的
        就是 ``.../mysql-8.4-community-el9-/`` —— 少了一段路径。后果是
        `dnf makecache` 报 404：

            Status code: 404 for .../mysql-8.4-community-el9-/repodata/repomd.xml
            Error: Failed to download metadata for repo 'mysql-8.4-community'

        而 ``$base``（清华 / 官方二选一）**必须**由 shell 展开，所以不能简单
        改成 ``<<'EOF'`` 把整个 heredoc 都保护起来。

    解法：把 ``$basearch`` 转义成 ``$basearch`` 让 shell 不碰它 ——
    用反斜杠转义 ``\\$basearch``，shell 展开后落进文件的就是字面量
    ``$basearch``，再由 dnf 展开。
    """
    return [
        _ensure_curl_cmd_dnf(),
        ["bash", "-c",
         'base="' + MYSQL_MIRROR + '"; '
         f'curl -fsSL -o /dev/null "$base/yum/mysql-8.4-community-el{el}-x86_64/" '
         f'|| base="{MYSQL_OFFICIAL_YUM}"; '
         'cat > /etc/yum.repos.d/mysql-community.repo <<EOF\n'
         '[mysql-8.4-community]\n'
         'name=MySQL 8.4 Community Server\n'
         f'baseurl=$base/yum/mysql-8.4-community-el{el}-\\$basearch/\n'
         'enabled=1\n'
         'gpgcheck=1\n'
         f'gpgkey={MYSQL_GPG_KEY}\n'
         'EOF'
         ],
        ["bash", "-c",
         'grep -q "\\$basearch" /etc/yum.repos.d/mysql-community.repo || { '
         'echo "生成的 repo 文件里 $basearch 被展开了（应为字面量）" >&2; '
         'cat /etc/yum.repos.d/mysql-community.repo >&2; exit 1; }'],
        ["dnf", "clean", "all"],
        ["dnf", "makecache"],
    ]

matrix: dict[str, dict[str, Recipe]] = {
    "python": {
        "ubuntu": Recipe(
            packages=["python3.14", "python3.14-venv", "python3.14-dev"],
            prepare=[
                ["apt-get", "install", "-y", "software-properties-common"],
                ["add-apt-repository", "-y", "ppa:deadsnakes/ppa"],
                ["apt-get", "update"],
            ],
            note="deadsnakes PPA 提供 python3.14（Ubuntu 24.04 官方源止于 3.12）。",
        ),
        "debian": Recipe(
            packages=["python3", "python3-venv", "python3-dev"],
            note="⚠️ Debian 官方源通常到不了 3.14 —— 若版本不足请改用 uv。"
                 "本条为未实测路径。",
        ),
    },
    "node": {
        "ubuntu": Recipe(
            packages=["nodejs"],
            prepare=[
                _ensure_curl_cmd_apt(extra=("gnupg",)),
                ["bash", "-c",
                 "curl -fsSL https://deb.nodesource.com/setup_26.x | bash -"],
            ],
            note="Node 基线 26.7 来自本机 dev；低于该版本的 Node 会让 pnpm "
                 "静默跳过 rolldown 原生 binding，到构建阶段才炸。",
        ),
        "debian": Recipe(
            packages=["nodejs"],
            prepare=[
                _ensure_curl_cmd_apt(extra=("gnupg",)),
                ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_26.x | bash -"],
            ],
        ),
        "rocky": Recipe(
            packages=["nodejs"],
            prepare=[
                _ensure_curl_cmd_dnf(),
                ["bash", "-c", "curl -fsSL https://rpm.nodesource.com/setup_26.x | bash -"],
            ],
        ),
        "centos": Recipe(
            packages=["nodejs"],
            prepare=[
                _ensure_curl_cmd_dnf(),
                ["bash", "-c", "curl -fsSL https://rpm.nodesource.com/setup_26.x | bash -"],
            ],
        ),
        "rhel": Recipe(
            packages=["nodejs"],
            prepare=[
                _ensure_curl_cmd_dnf(),
                ["bash", "-c", "curl -fsSL https://rpm.nodesource.com/setup_26.x | bash -"],
            ],
        ),
    },
    "redis": {
        "ubuntu": Recipe(packages=["redis-server"], services=["redis-server"]),
        "debian": Recipe(packages=["redis-server"], services=["redis-server"]),
        "rocky": Recipe(packages=["redis"], services=["redis"],
                        prepare=_EPEL_PREPARE),
        "centos": Recipe(packages=["redis"], services=["redis"],
                         prepare=_EPEL_PREPARE),
        "rhel": Recipe(packages=["redis"], services=["redis"],
                       note="⚠️ redis 在 EPEL，而 RHEL 的 dnf 源里没有 epel-release。"
                            "需自行安装 EPEL rpm 后重试："
                            "https://docs.fedoraproject.org/en-US/epel/"),
    },
    "mysql": {
        "ubuntu": Recipe(
            packages=["mysql-community-server"],
            services=["mysql"],
            prepare=_mysql_apt_prepare("ubuntu"),
            note="从 MySQL 官方源（清华镜像）安装 8.4 LTS。"
                 "不用发行版的 mysql-server 是因为那个只有 8.0。",
        ),
        "debian": Recipe(
            packages=["mysql-community-server"],
            services=["mysql"],
            prepare=_mysql_apt_prepare("debian"),
            note="从 MySQL 官方源（清华镜像）安装 8.4 LTS —— 未实测路径。",
        ),
        "rocky": Recipe(
            packages=["mysql-community-server"],
            services=["mysqld"],
            prepare=_mysql_yum_prepare(9),
        ),
        "centos": Recipe(
            packages=["mysql-community-server"],
            services=["mysqld"],
            prepare=_mysql_yum_prepare(9),
        ),
        "rhel": Recipe(
            packages=["mysql-community-server"],
            services=["mysqld"],
            prepare=_mysql_yum_prepare(9),
        ),
    },
    "build": {
        "ubuntu": _DEBIAN_BUILD,
        "debian": _DEBIAN_BUILD,
        "rocky": _RHEL_BUILD,
        "centos": _RHEL_BUILD,
        "rhel": _RHEL_BUILD,
    },
}


_RHEL_FAMILIES = ("rocky", "centos", "rhel", "almalinux")


def _el_major(f: HostFacts) -> int:
    """EL 主版本号；非 RHEL 系返回 0（调用方据此走非 RHEL 配方）。

    el9（Rocky/CentOS/Alma/RHEL 9）与 el10 的 MySQL/Redis/Python 配方
    完全不同：el9 的 MySQL 走社区源、Redis 在 EPEL；el10 的 MySQL 直给
    appstream 的 ``mysql8.4-server``、Redis 无包改用 ``valkey``。
    区分依据是 ``distro_major``（来自 VERSION_ID 主版本号）。
    """
    if _family(f) in _RHEL_FAMILIES:
        return f.distro_major
    return 0


def _family(f: HostFacts) -> str:
    """归一化发行版族 —— **委托 judge.support._normalize，保持单一实现**。

    ⚠️ 曾有两份归一化各自为政（评审 P0-4/P1-9）：Oracle Linux（ID=ol）
    被 _normalize 判 supported、_family 却返回 "ol" 导致全线
    UnsupportedPlatform；almalinux 缺席族表时"判 supported 但装不了"。
    修这类问题只能改一处 —— 归一化在 judge 层，矩阵键的别名在下方
    ``_MATRIX_ALIAS`` 处理。
    """
    if f.distro in matrix.get("redis", {}) and f.distro != "debian":
        return f.distro
    from ..judge.support import _normalize

    return _normalize(f)


_MATRIX_ALIAS = {"almalinux": "centos"}


def _apt_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    return env


_APT_LOCKS: tuple[str, ...] = (
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/lib/apt/lists/lock",
    "/var/cache/apt/archives/lock",
)

APT_LOCK_WAIT = 900.0


def _apt_lock_busy() -> str:
    """返回当前被别的进程占用的锁文件路径；无人占用返回空串。

    判据是**真的去抢一次锁**（非阻塞），不是看文件存在与否 ——
    这些锁文件在被创建过之后会一直存在，靠 stat 判断会得到恒真的假信号。

    ⚠️ 必须 flock 与 lockf **都试**：Linux 上这两种锁机制互不干扰 ——
    flock 是 BSD 风格（按 open file description），lockf/POSIX 记录锁是
    另一套（按进程）。dpkg/apt 用的是 **lockf**。只查 flock 的话，
    即使 dpkg 正占着锁也会探测"成功"，判据恒假 —— 实测第一轮就是这么
    漏掉的：加了等锁逻辑，安装照样在 4 秒后被 apt 拒绝。
    """
    import fcntl

    for path in _APT_LOCKS:
        try:
            f = open(path, "a")
        except OSError:
            continue
        acquired = []
        free = True
        for lock in (fcntl.flock, fcntl.lockf):
            try:
                lock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired.append(lock)
            except OSError:
                free = False
                break
        for lock in acquired:
            try:
                lock(f, fcntl.LOCK_UN)
            except OSError:
                pass
        f.close()
        if not free:
            return path
    return ""


def _wait_for_apt_lock(timeout: float = APT_LOCK_WAIT) -> None:
    """apt/dpkg 锁被占用时等待释放，而不是让安装当场失败。

    ⚠️ 真实新机场景（2026-10-02 实测：Ubuntu 24.04 云主机刚重置）：
    云镜像首次启动会在后台跑 ``unattended-upgrades``，持续数分钟到十几分钟。
    这期间任何 apt-get 都立刻失败：

        E: Could not get lock /var/lib/dpkg/lock-frontend.
           It is held by process 2305 (unattended-upgr)

    旧脚本和修复前的 installer 都会在这一步直接退出 —— 用户什么都没做错，
    只是"来早了"。等一会儿即可，这比报错退出有用得多。

    超时后不阻塞：仍继续尝试，让 apt 自己给出真因（保留原始错误信息）。
    """
    import time

    busy = _apt_lock_busy()
    if not busy:
        return
    print(f"[syspkg] apt/dpkg 锁被占用（{busy}），等待释放，"
          f"最多 {timeout / 60:.0f} 分钟")
    print("         云主机首次启动时通常是 unattended-upgrades 在后台跑 apt；"
          "不是安装器的问题，等它跑完即可")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(15)
        if not _apt_lock_busy():
            print("[syspkg] apt/dpkg 锁已释放，继续")
            return
    print(f"[syspkg] ⚠ 等了 {timeout / 60:.0f} 分钟锁仍未释放，"
          "继续尝试（若失败，apt 会给出真因）")


def _apt(argv: list[str], *, label: str, check: bool = True,
         echo: bool = True) -> object:
    """跑 apt 命令；必要时先等锁（见 :func:`_wait_for_apt_lock`）。"""
    _wait_for_apt_lock()
    return run(argv, check=check, echo=echo, env=_apt_env(), label=label)


def _install(component: str, f: HostFacts, *, yes: bool = True,
            recipe: Recipe | None = None) -> Recipe:
    """按矩阵执行 apt/dnf 安装，返回所用配方。

    :param recipe: 显式配方。用于按 EL 大版本覆盖矩阵默认项（如 el10 的
        MySQL/Redis 与 el9 不同）—— 传了就直接用，不再查矩阵。
    """
    if recipe is None:
        fam = _family(f)
        table = matrix.get(component, {})
        recipe = table.get(fam) or table.get(_MATRIX_ALIAS.get(fam, fam))
    if not recipe:
        fam = _family(f)
        raise UnsupportedPlatform(
            f"没有适用于 {component} 的 {fam or f.distro} 配方。"
            f"已实测的发行版：{', '.join(sorted(matrix.get(component, {})))}。"
            "宁刀 blades 明确失败也不猜包名 —— 猜错的报错会指向包名，"
            "把人误导到『这个发行版没有这个包』上去。"
        )

    _run_recipe(component, recipe, f, yes=yes)
    return recipe


def _run_recipe(component: str, recipe: Recipe, f: HostFacts, *, yes: bool = True) -> None:
    """执行一条配方的 prepare + install + enable。"""
    pm = f.pkg_manager
    if pm == "apt":
        if yes:
            _apt(["apt-get", "update"], label="更新 apt 索引", check=False, echo=False)
        for argv in recipe.prepare:
            _apt(argv, label=f"{component} 准备")
        _apt(["apt-get", "install", "-y", *recipe.packages], label=f"安装 {component}")
    elif pm in ("dnf", "yum"):
        for argv in recipe.prepare:
            run(argv, check=True, label=f"{component} 准备")
        run([pm, "install", "-y", *recipe.packages], check=True, label=f"安装 {component}")
    else:
        raise UnsupportedPlatform(f"未找到受支持的包管理器（当前：{pm or '无'}）")

    for svc in recipe.services:
        if which("systemctl"):
            run(["systemctl", "enable", "--now", svc], check=False, echo=True,
                label=f"启用 {svc}")
    if recipe.note:
        print(f"  · {recipe.note}")


def install_raw(packages: list[str], f: HostFacts, *, label: str = "") -> None:
    """直接安装一组包名，不走配方矩阵。

    给「编译工具链」这类**与发行版族无关、包名两边不同**的场景用：
    调用方已经把 apt / dnf 的包名分别列好了，这里只负责执行。

    ⚠️ 与 `_install` 的区别：不做配方查找，因此**不会**在未知发行版上抛
    UnsupportedPlatform。判断"这个发行版支不支持"是调用方的事。
    """
    name = label or "安装依赖包"
    recipe = Recipe(packages=list(packages))
    print(f"[syspkg] {name}: {' '.join(packages)}")
    _run_recipe(name, recipe, f, yes=True)



def ensure_python(f: HostFacts, minimum: str) -> None:
    """Python 低于基线就补。

    路径选择（2026-10-04 改造）：

    1. **Ubuntu** → deadsnakes PPA。有现成 deb 就别编译，1 分钟 vs 15 分钟。
    2. **RHEL 系 el9** → **uv 装 python-build-standalone**。el9 系统 sqlite
       锁在 3.34.1（< chromadb 要求的 3.35.0），源码编译的 CPython 链的是
       系统 sqlite，会让 AI/RAG 功能降级。python-build-standalone **自带**
       sqlite 3.53.1，且是官方预编译、下载即用，比源码编译更快也更稳。
       uv 拉不到（网络受限）时回退源码编译，并显式 WARN 这一降级。
    3. **其它发行版（Debian / el10 / 其它）** → 源码编译。el10 系统 sqlite
       3.46.1 已达标，源码编译无 AI 问题；Debian 12 系统 sqlite 3.40.1 同样达标。

    ⚠️ 「中科大 /python/ 有源码包」≠「有 deb 包」：那只是源码归档，
       给不出 ``python3.14-venv`` 这类拆分包。
    """
    from ..judge.version import ge

    if f.python_version and ge(f.python_version, minimum):
        return

    print(f"[syspkg] Python {f.python_display} < {minimum}，开始补齐")

    if f.pkg_manager == "apt" and _family(f) == "ubuntu":
        try:
            _install("python", f)
            return
        except (UnsupportedPlatform, Exception) as exc:  # noqa: BLE001
            print(f"[syspkg] deadsnakes 路径失败（{exc}），改用源码编译")

    if _family(f) in _RHEL_FAMILIES and _el_major(f) == 9:
        try:
            ensure_python_via_uv(f, minimum)
            return
        except (UnsupportedPlatform, Exception) as exc:  # noqa: BLE001
            print(f"[syspkg] uv 安装 Python 失败（{exc}），回退源码编译；"
                  "⚠ el9 系统 sqlite 3.34.1 < 3.35.0，AI/RAG 功能将降级运行")

    _ensure_python_by_source(f)


def _ensure_python_by_source(f: HostFacts) -> None:
    """源码编译 Python —— 跨发行版的通用出路。"""
    from ..judge.version import BASELINES
    from .python_build import ensure_python_from_source

    ensure_python_from_source(f, BASELINES["python"])


UV_PYTHON_INSTALL_DIR = "/usr/local/lib/uv-python"


def _ensure_uv_bin() -> str:
    """拿到可用的 ``uv`` 二进制；裸机没有就引导一个。

    顺序（从快到稳）：

    1. 已在 PATH → 直接用。
    2. 系统 python3 的 pip 能装 → 装到用户目录并定位。
    3. 官方独立安装脚本（写到 ``/usr/local/bin``，避开 home 的 ProtectHome
       问题），脚本本身从 astral 官方源拉静态二进制。

    任何一步拿到即用，不强制走某一条；都失败则由调用方回退源码编译。
    """
    found = which("uv")
    if found:
        return found

    for py in ("python3", "python3.9", "python3.11"):
        if not which(py):
            continue
        run([py, "-m", "pip", "install", "uv"], check=False,
            echo=False, label="pip 安装 uv")
        located = which("uv")
        if not located:
            home = Path.home()
            candidate = home / ".local" / "bin" / "uv"
            located = str(candidate) if candidate.is_file() else ""
        if located:
            return located
        break

    run(["bash", "-c",
         "curl -LsSf https://astral.sh/uv/install.sh "
         "| UV_INSTALL_DIR=/usr/local/bin sh"],
        check=True, label="安装 uv（官方脚本）")
    return "/usr/local/bin/uv"


def _find_uv_python() -> str:
    """定位刚装好的 uv Python 解释器。

    python-build-standalone 的布局是
    ``<UV_PYTHON_INSTALL_DIR>/cpython-3.14.x-<triple>/bin/python3.14``。
    用 glob 而非固定路径，避免被小版本号（3.14.0 vs 3.14.2）卡死。

    ⚠️ 排序必须按**解析出的版本号数值**而不是字典序：字典序下
    ``"cpython-3.14.10-..." < "cpython-3.14.2-..."``，patch≥10 的最新版
    反而排前面，``hits[-1]`` 会选到旧版；gnu/musl 变体共存时 g<m，
    glibc 主机还可能选中 musl 构建。故同版本内显式偏好 gnu。
    """
    import glob
    import re as _re

    pattern = str(Path(UV_PYTHON_INSTALL_DIR) / "cpython-3.14.*" / "bin" / "python3.14")
    hits = glob.glob(pattern)
    if not hits:
        raise RuntimeError(
            f"uv 已安装 Python 3.14 但找不到解释器（期望 {pattern}）。"
        )

    def _key(p: str) -> tuple:
        m = _re.search(r"cpython-3\.14\.(\d+)", p)
        patch = int(m.group(1)) if m else -1
        return (patch, "gnu" in p)      # 同 patch 内偏好 gnu 变体

    return max(hits, key=_key)


def _verify_uv_sqlite(exe: str) -> None:
    """校验 uv Python 自带的 sqlite 满足 chromadb（>= 3.35.0）。

    不满足就抛错，逼回源码编译路径 —— 否则会静默装上一个
    链着系统低版本 sqlite 的解释器，到 RAG 导入时才崩，离真因极远。
    """
    from ..judge.version import ge

    res = run([exe, "-c", "import sqlite3;print(sqlite3.sqlite_version)"],
              check=False, echo=False)
    ver = res.stdout.strip()
    if not res.ok or not ver:
        raise RuntimeError("uv Python 的 sqlite 版本探测失败")
    if not ge(ver, "3.35.0"):
        raise RuntimeError(
            f"uv Python 自带 sqlite {ver} < 3.35.0，不满足 chromadb，"
            "回退源码编译"
        )
    print(f"[syspkg] ✓ uv Python 自带 sqlite {ver}（>= 3.35.0，AI/RAG 不受影响）")


def ensure_python_via_uv(f: HostFacts, minimum: str) -> str:
    """用 uv 装 python-build-standalone 作为宿主 Python。

    返回解释器路径并写入 ``f.python_bin``。这是 el9 的**首选**路径：
    python-build-standalone 自带高版本 sqlite（3.53.1），避开 el9 系统
    sqlite 3.34.1 导致 AI 降级的坑；且是官方预编译，比源码编译更快。

    装完后把解释器软链到 ``/usr/local/bin/python3.14``，与源码编译的
    ``_prefix_python()`` 一致，保证 ``collect()`` 的 ``_pick_python`` 能在
    补齐后重新发现它，后续 venv 用它创建、systemd 单元直接 exec venv 内的副本。
    """
    from ..judge.version import ge

    if f.python_version and ge(f.python_version, minimum):
        return f.python_bin

    uv = _ensure_uv_bin()
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=UV_PYTHON_INSTALL_DIR)
    run([uv, "python", "install", "3.14"], check=True, env=env,
        label="uv 安装 Python 3.14（python-build-standalone）")

    exe = _find_uv_python()
    _verify_uv_sqlite(exe)

    run(["bash", "-c", f"ln -sf {exe} /usr/local/bin/python3.14"],
        check=True, echo=True, label="软链 uv Python 到 /usr/local/bin/python3.14")

    f.python_bin = "/usr/local/bin/python3.14"
    return f.python_bin


def ensure_node(f: HostFacts, minimum: str) -> None:
    from ..judge.version import ge

    if f.node_version and ge(f.node_version, minimum):
        return
    print(f"[syspkg] Node {f.node_version or '缺失'} < {minimum}，尝试安装 Node 26")
    _install("node", f)


def _epel_prepare(f: HostFacts) -> list[list[str]]:
    """EPEL 引导，**按发行版分流**（2026-10-04 测试机实测教训）。

    CentOS Stream 9 的自身仓库（含 extras-common）里**没有** epel-release 包
    —— `dnf install epel-release` 直接 No match。它必须直装 fedora 的
    `epel-release-latest-<el>.noarch.rpm`；Rocky/Alma 的仓库里才有该包。
    """
    el = _el_or_fail(f) or 9
    if _family(f) == "centos":
        return [["bash", "-c",
                 f"dnf install -y https://dl.fedoraproject.org/pub/epel/"
                 f"epel-release-latest-{el}.noarch.rpm"]]
    return [["dnf", "install", "-y", "epel-release"]]


def ensure_redis(f: HostFacts) -> None:
    """Redis 缺失就装并起服。

    旧脚本只 warn（"必须另行安装并启动"）但流程继续 —— 到 Celery broker
    连不上时才暴露，那时已经是"安装成功"之后很久了。
    """
    if which("redis-server"):
        return
    print("[syspkg] Redis 缺失（缓存与 Celery broker 必需），尝试安装并起服")
    _install_redis(f)


def _el_or_fail(f: HostFacts) -> int:
    """取 EL 主版本；RHEL 系但版本解析不出时**响亮失败**而非静默落回 el9。

    VERSION_ID 缺失/非数字的 el10 定制镜像上，``_el_major==0`` 会让
    ``>=10`` 判定不命中，静默走 el9 配方（EPEL 无 redis、el9 MySQL
    社区源）—— 与「未实测的发行版直接报错，不猜包名」纪律相悖
    （评审 P1-2）。
    """
    if _family(f) not in _RHEL_FAMILIES:
        return 0
    el = _el_major(f)
    if el == 0:
        raise UnsupportedPlatform(
            f"{f.distro} {f.distro_version} 是 RHEL 系，但无法从 os-release "
            "解析出 EL 主版本号（VERSION_ID 缺失或非数字）。"
            "为避免误用 el9/el10 配方，已中止；请修复 VERSION_ID 或"
            "自行备好 MySQL/Redis 后加 --skip-syspkg 重跑。"
        )
    return el


def _install_redis(f: HostFacts) -> None:
    """按 EL 大版本选 Redis 配方。

    - el10：官方源与 EPEL 都没有 ``redis-server``，用 ``valkey``（Redis 协议兼容，
       对外声明 redis_version 7.2.4）。装后软链成 ``redis-server``/``redis-cli``，
       保证后续 ``which("redis-server")`` 与客户端能力协商成立；服务名 ``valkey``。
    - el9 及其它 RHEL：走矩阵里的 EPEL ``redis``。
    """
    if _family(f) in _RHEL_FAMILIES:
        if _el_or_fail(f) < 10:
            _install("redis", f, recipe=Recipe(
                packages=["redis"], services=["redis"],
                prepare=_epel_prepare(f),
            ))
            return
        _install("redis", f, recipe=Recipe(
            packages=["valkey"],
            services=["valkey"],
            note="el10 官方源与 EPEL 均无 redis-server，用 valkey（Redis 协议兼容）替代",
        ))
        vs = which("valkey-server")
        vc = which("valkey-cli")
        if not (vs and vc):
            print("[syspkg] ⚠ 找不到 valkey-server/valkey-cli，跳过软链；"
                  "请手工确认二进制位置并软链为 redis-server/redis-cli")
            return
        run(["bash", "-c",
             f"ln -sf {vs} /usr/local/bin/redis-server && "
             f"ln -sf {vc} /usr/local/bin/redis-cli"],
            check=False, echo=True, label="valkey 软链为 redis-server")
        return
    _install("redis", f)


def ensure_mysql_server(f: HostFacts, *, on_upgrade: str = "ask") -> None:
    """MySQL 服务端缺失或**版本低于基线**时补齐。

    ⚠️ 判据在 2026-10-03 从「有没有装」改成了「版本够不够」。旧判据是
    ``which("mysqld")``，后果是：**装过 8.0 的机器永远不会升到 8.4**，
    基线形同虚设（升级路径被静默跳过，而日志里看不出任何异常）。

    :param on_upgrade: 已有低版本时怎么办。
        ``"ask"``（默认）→ 交互提示，由用户决定；
        ``"yes"`` → 直接升；``"no"`` → 保持不动只警告；
        非交互环境下 ``"ask"`` 等同 ``"no"``（不擅自改数据库）。
    """
    from ..judge.version import BASELINES, ge

    has_server = bool(which("mysqld")
                      or Path("/usr/libexec/mysqld").exists())
    if has_server and ge(f.mysql_version, BASELINES["mysql"]):
        return                              # 已是 8.4+，什么都不做

    if has_server:
        _handle_mysql_upgrade(f, on_upgrade)
        return

    print("[syspkg] MySQL 服务端缺失（DB 初始化依赖），尝试安装并起服")
    _install_mysql(f)


def _install_mysql(f: HostFacts) -> None:
    """按 EL 大版本选 MySQL 配方。

    - el10：appstream 直给 ``mysql8.4-server``（8.4.11），**无需** MySQL 社区源
      与 GPG key（那是 el9 的路径）。服务名仍是 ``mysqld``。
    - el9 及其它 RHEL：走矩阵里的社区源路径（``mysql-community-server``）。

    ⚠️ 新装与**升级**两条路径都必须经这里（评审 P0-1）：升级路径曾直接
    ``_install("mysql", f)`` 查矩阵，el10 机器上会误写 el9 社区源。
    """
    if _family(f) in _RHEL_FAMILIES:
        if _el_or_fail(f) < 10:
            _install("mysql", f)
            return
        _install("mysql", f, recipe=Recipe(
            packages=["mysql8.4-server"],
            services=["mysqld"],
            note="el10 的 MySQL 8.4 直给在 appstream（mysql8.4-server），"
                 "不用 el9 的 MySQL 社区源",
        ))
        return
    _install("mysql", f)


MYSQL_UPGRADE_RISKS: tuple[str, ...] = (
    "apt/dnf 会移除发行版自带的 mysql-server-8.0 等包，替换为 mysql-community-server",
    "数据目录就地升级，**不可回滚** —— 请先做备份（mysqldump 或快照）",
    "MySQL 8.4 对外键引用列类型的一致性要求比 8.0 严格（error 3780），"
    "存量库中未适配的 FK 会在后续建表时报错",
    "8.4 默认禁用 mysql_native_password；使用该认证的旧账号需迁移到 caching_sha2_password",
    "升级过程中服务会重启，期间应用不可用",
)


def _handle_mysql_upgrade(f: HostFacts, mode: str) -> None:
    """已有低版本 MySQL 时的处置。"""
    from ..judge.version import BASELINES

    cur = f.mysql_version or "未知"
    print(f"\n[syspkg] ⚠ 检测到 MySQL {cur}，低于项目基线 {BASELINES['mysql']}")
    print("[syspkg] 升级前请确认以下风险：")
    for i, risk in enumerate(MYSQL_UPGRADE_RISKS, 1):
        print(f"           {i}. {risk}")

    if mode == "no":
        print(f"[syspkg] 按配置保持 MySQL {cur} 不变（--mysql-upgrade=no）")
        return

    if mode == "ask":
        if not _is_interactive():
            print("[syspkg] 当前为非交互环境，不擅自升级数据库。")
            print("[syspkg]   确认要升级请显式指定：--mysql-upgrade=yes")
            return
        if not _confirm("是否现在升级到 MySQL 8.4？"):
            print(f"[syspkg] 已跳过升级，继续使用 MySQL {cur}")
            return

    print(f"[syspkg] 开始将 MySQL {cur} 升级到 {BASELINES['mysql']}")
    _install_mysql(f)


def _is_interactive() -> bool:
    """判断能否安全地提问。

    ⚠️ 不能只看 stdin.isatty()：CI 里 stdin 常是管道，但那是**非交互**，
    应该走安全默认；而某些编排系统会给一个假 tty。
    这里用 stdin.isatty() —— 它保守，误判只会导致"该问的没问、按不动处理"，
    而按不动处理是安全的那个方向。
    """
    import sys

    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _confirm(prompt: str) -> bool:
    """问一个 y/N 问题。默认 No —— 数据库升级不该是"回车即同意"。"""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def ensure_build_toolchain(f: HostFacts) -> None:
    """补齐 C++ 工具链与 venv 可用性。

    ⚠️ 顺序要点（旧脚本踩过）：**venv 校验必须在 g++ 的早期返回之前做**。
    否则遇到「g++ 在、venv 不在」的盒子会直接跳过整段补齐，到创建 venv 才炸。
    """
    if f.has_gpp:
        return
    print("[syspkg] g++ 缺失，补全编译工具链")
    _install("build", f)
