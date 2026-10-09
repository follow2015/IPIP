"""源码编译公共设施 —— 包管理器给不出合格版本时的唯一出路。

为什么需要这一层：

系统源里能拿到什么，取决于发行版维护者的选择，而不取决于项目基线。
两个具体事实（2026-10-03 实测）：

  · **Python 3.14**：Ubuntu 24.04 官方源止于 3.12；Debian 稳定版更老；
    Rocky/CentOS 的 AppStream 也到不了。旧路径是加 deadsnakes PPA ——
    那只对 Ubuntu 有效，且引入第三方源。而项目对 3.14 是 **DIE 级**
    依赖（``realtime_gateway`` 用了 3.14 才有的 ``asyncio.AsyncGenerator``），
    不能"降级继续"。
  · **「用镜像源」不等于「用编译」**：中科大 ``/python/`` 目录**确实**有
    3.14.8 的 tarball，但它只是**源码归档**，不是包管理源 —— 它给不出
    ``python3.14-venv`` 这种拆分包（Debian 系把 ensurepip 拆成了独立包，
    缺它建 venv 会报 "ensurepip is not available"）。所以即便从镜像拉，
    也依然是编译安装。别把「有镜像」误当成「有 deb 包」。

因此本模块只负责**怎么编译**，不关心"为什么" —— 后者归各调用方。

一条贯穿全模块的纪律：**编译失败必须能被看懂**。
configure/make 的输出以千行计，真因通常只在其中一处；所以每个阶段都要
给出可复现的单步命令，让人能脱离安装器手工重跑。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .shell import run, which

__all__ = [
    "SourceBuildError",
    "BuildJob",
    "cpu_count_for_make",
    "download_verified",
    "ensure_c_compiler",
    "extract",
    "fetch_first_available",
    "mirror_for",
]


class SourceBuildError(RuntimeError):
    """源码编译路径上的任何失败。"""



PYTHON_MIRRORS: tuple[tuple[str, str], ...] = (
    ("https://mirrors.tuna.tsinghua.edu.cn/python/{ver}/Python-{ver}.tar.xz", "清华镜像"),
    ("https://mirrors.bfsu.edu.cn/python/{ver}/Python-{ver}.tar.xz", "北外镜像"),
    ("https://mirrors.ustc.edu.cn/python/{ver}/Python-{ver}.tar.xz", "中科大镜像"),
    ("https://www.python.org/ftp/python/{ver}/Python-{ver}.tar.xz", "python.org 官方"),
)

USER_AGENT = "Wget/1.21"

DOWNLOAD_TIMEOUT = 300.0


def mirror_for(component: str) -> tuple[tuple[str, str], ...]:
    """取某组件的镜像候选列表。"""
    table = {"python": PYTHON_MIRRORS}
    try:
        return table[component]
    except KeyError:  # pragma: no cover - 目前只有 python
        raise SourceBuildError(f"未定义 {component} 的源码镜像列表") from None



def cpu_count_for_make(*, reserve: int = 1, cap: int = 8) -> str:
    """``make -j`` 的取值。

    两个约束来自实测：

    · **留一个核**：编译占满全部核心时，同一台机器上的心跳线程、sshd、
      监控 agent 都会被拖住，表现为"安装卡死"——而实际只是被打满了。
    · **上限 8**：与 uv 并发同一个教训，高并发在受限的云主机上反而更慢
      （内存压力导致 swap）。CPython 全量编译在 2 核机上约 10-20 分钟，
      在 8 核机上约 3-5 分钟，超过 8 核收益很小。
    """
    n = (os.cpu_count() or 2) - reserve
    n = max(1, min(n, cap))
    return str(n)



_TOOLCHAIN_APT: tuple[str, ...] = (
    "build-essential", "libssl-dev", "libffi-dev", "zlib1g-dev",
    "libbz2-dev", "libreadline-dev", "libsqlite3-dev", "liblzma-dev",
    "libncurses-dev", "uuid-dev", "tk-dev", "wget",
    "xz-utils", "bzip2", "gzip",
)

_TOOLCHAIN_APT_OPTIONAL: tuple[str, ...] = ("libgdbm-dev",)

_TOOLCHAIN_DNF: tuple[str, ...] = (
    "gcc", "gcc-c++", "make", "openssl-devel", "libffi-devel", "zlib-devel",
    "bzip2-devel", "readline-devel", "sqlite-devel", "xz-devel",
    "ncurses-devel", "libuuid-devel", "tk-devel", "wget",
    "xz", "bzip2", "gzip",
)

_TOOLCHAIN_DNF_OPTIONAL: tuple[str, ...] = ("gdbm-devel",)


def ensure_c_compiler(host, *, installer=None) -> None:
    """确保编译 CPython 必需的开发库齐备。

    :param host: :class:`~..judge.facts.HostFacts`
    :param installer: 可注入的安装回调 ``(packages, family) -> None``。
        默认走 ``act.syspkg`` —— 抽成回调是为了让测试不必真的装包。

    两条独立性判据，任一不满足就补装：

    1. ``_headers_ok()`` —— 能编译引用 openssl/ffi/zlib 的单文件；
    2. ``_extract_tools_ok()`` —— ``xz``/``gzip``/``bzip2`` 可执行文件在 PATH 里。

    第 2 条是真机加的（2026-10-03）：有 gcc、头文件也齐，但缺 ``/usr/bin/xz``，
    于是 ``tar -xf *.tar.xz`` 在**下载完成、22MB 已落盘之后**才失败。
    这与"缺 ssl 头文件"是同一类问题 —— 判据漏一项，就要多等五分钟才看到错。
    """
    if which("gcc") and which("make"):
        if _headers_ok() and _extract_tools_ok():
            return
        missing = []
        if not _headers_ok():
            missing.append("开发头文件")
        if not _extract_tools_ok():
            missing.append("解压工具")
        print(f"[build] gcc 在但{'与'.join(missing)}缺失，补齐编译依赖")
    else:
        print("[build] 缺 C 编译器，补齐编译工具链")

    if installer is not None:
        installer(host)
        return
    _default_install_toolchain(host)


_EXTRACT_TOOLS: tuple[str, ...] = ("xz", "gzip", "bzip2")


def _extract_tools_ok() -> bool:
    """解压工具可执行文件是否齐全。

    刻意用 ``which()`` 而不是"包装了没有"：包管理器只知道包装没装，
    而 ``xz-devel`` 装了**不代表** ``/usr/bin/xz`` 存在 —— 这正是真机上
    踩到的形态（``xz-devel`` 在、``xz`` 不在，两者是**不同的包**）。
    """
    return all(which(tool) for tool in _EXTRACT_TOOLS)


def _headers_ok() -> bool:
    """用一次真实编译探测头文件，而不是查包管理器。

    查 dpkg/rpm 知道"包装没装"，但不知道"头文件在不在 PATH 里"——
    交叉编译环境、手工解包的机器上两者会不一致。编译一次最直接。
    """
    src = '#include <openssl/ssl.h>\n#include <ffi.h>\n#include <zlib.h>\nint main(void){return 0;}\n'
    cc = which("cc") or which("gcc")
    if not cc:
        return False
    try:
        proc = subprocess.run(
            [cc, "-x", "c", "-", "-o", "/dev/null", "-lssl", "-lffi", "-lz"],
            input=src, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _default_install_toolchain(host) -> None:
    from ..act import syspkg

    if host.pkg_manager == "apt":
        syspkg.install_raw(list(_TOOLCHAIN_APT), host, label="编译工具链")
        _try_optional_packages(host, _TOOLCHAIN_APT_OPTIONAL)
    elif host.pkg_manager in ("dnf", "yum"):
        syspkg.install_raw(list(_TOOLCHAIN_DNF), host, label="编译工具链")
        _try_optional_packages(host, _TOOLCHAIN_DNF_OPTIONAL)
    else:
        raise SourceBuildError(
            f"未支持的包管理器 {host.pkg_manager or '（无）'}，无法自动补齐编译工具链。\n"
            "  请手工安装 gcc/make 以及 openssl、ffi、zlib 的开发头文件后重试。"
        )


def _try_optional_packages(host, packages: tuple[str, ...]) -> None:
    """尽力装上可选包；失败只提示，**不中止安装**。

    为什么要单独一组而不是并进必装列表：

    1. **一个包名不存在会拖垮整个 dnf/apt 事务**。实测 CentOS Stream 9 上
       ``dnf install gcc ... gdbm-devel`` 直接 ``Unable to find a match``，
       gcc 也没装上 —— 必装组里放一个可能不存在的包，等于给整条链路埋雷。
    2. **收益与代价不对等**。这些包只影响 CPython 的**可选模块**：
       缺 ``gdbm`` 头文件只是没有 ``dbm.gnu``（``dbm.ndbm``/``sqlite3`` 都不受影响），
       而缺 ``openssl`` 会让 pip 全线不可用。两者不该同生死。

    因此这里刻意用 ``install_raw`` 的"失败不抛"路径，把结果降级为提示。
    """
    from ..act import syspkg

    try:
        syspkg.install_raw(list(packages), host, label="编译工具链（可选模块）")
    except Exception as e:  # noqa: BLE001 —— 可选包失败绝不该让安装中止
        print(f"[build] 可选包 {', '.join(packages)} 未装上（不影响主流程）：{e}")
        print("[build]   影响面：CPython 会少编一个可选模块（如 dbm.gnu）；")
        print("[build]   ssl / sqlite3 / ctypes 等关键模块不受影响。")



@dataclass
class DownloadResult:
    path: Path
    url: str
    sha256: str
    from_cache: bool = False


def _sha256_of(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def fetch_first_available(
    candidates: tuple[tuple[str, str], ...],
    dest_dir: Path,
    *,
    cache_dir: Path | None = None,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """按顺序尝试候选 URL，返回第一个成功下载的文件。

    刻意**不并行探测**：源码包几十 MB，并行拉一遍等于把带宽用满还互相拖慢。
    顺序尝试的开销可忽略（失败的那个通常几秒内就 404）。
    """
    import urllib.error
    import urllib.request

    dest_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    for url, label in candidates:
        name = url.rsplit("/", 1)[-1]
        cached = (cache_dir / name) if cache_dir else None
        if cached and cached.exists() and cached.stat().st_size > 0:
            print(f"[build] 命中本地缓存：{cached}")
            return DownloadResult(cached, url, _sha256_of(cached), from_cache=True)

        target = dest_dir / name
        print(f"[build] 下载 {label}：{url}")
        started = time.monotonic()
        expected: str | None = None
        try:
            req = urllib.request.Request(  # noqa: S310 —— url 来自本模块内的镜像常量表，非用户输入
                url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 —— 同上
                expected = resp.headers.get("Content-Length")
                with target.open("wb") as out:
                    shutil.copyfileobj(resp, out, length=1 << 20)
        except (urllib.error.URLError, OSError) as exc:
            errors.append(f"{label}（{url}）：{exc}")
            target.unlink(missing_ok=True)
            continue

        got = target.stat().st_size
        if got == 0:
            errors.append(f"{label}：下载到 0 字节")
            target.unlink(missing_ok=True)
            continue
        if expected and got != int(expected):
            errors.append(f"{label}：不完整（{got}/{expected} 字节）")
            target.unlink(missing_ok=True)
            continue

        digest = _sha256_of(target)
        print(f"[build]   完成 {got / 1048576:.1f} MB，"
              f"耗时 {time.monotonic() - started:.1f}s，sha256={digest[:16]}…")
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(target, cache_dir / name)
            except OSError:
                pass    # 缓存是加速手段，失败不该拖垮安装
        return DownloadResult(target, url, digest)

    raise SourceBuildError("所有源码镜像都不可用：\n  " + "\n  ".join(errors))


def download_verified(
    url: str,
    dest_dir: Path,
    *,
    sha256: str = "",
    timeout: float = 600.0,
) -> DownloadResult:
    """下载单个 URL 并校验（给了 sha256 就严格比对）。

    ``sha256`` 留空时只记录不校验 —— 用于镜像不提供校验文件的场景。
    调用方**应当**尽量提供，因为源码编译的产物会以 root 装进 /usr/local，
    校验失败比下载失败严重得多。
    """
    res = fetch_first_available(((url, "指定的源"),), dest_dir, timeout=timeout)
    if sha256 and res.sha256.lower() != sha256.lower():
        raise SourceBuildError(
            f"sha256 校验失败：\n  期望 {sha256}\n  实际 {res.sha256}\n"
            f"  文件 {res.path}\n"
            "  这可能是镜像同步不完整，或内容被篡改。已中止。"
        )
    return res



_TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar.zst")

_SUFFIX_TOOL = {
    ".tar.gz": "gzip", ".tgz": "gzip",
    ".tar.xz": "xz",
    ".tar.bz2": "bzip2",
    ".tar.zst": "zstd",
}


def _ensure_extract_tool_for(archive: Path) -> None:
    """解压前确认对应程序可用，缺了就报一个说得清楚的错。"""
    for suffix, tool in _SUFFIX_TOOL.items():
        if not str(archive).endswith(suffix):
            continue
        if which(tool):
            return
        hint = {
            "xz": "Debian/Ubuntu: xz-utils ｜ RHEL/CentOS: xz",
            "bzip2": "Debian/Ubuntu: bzip2 ｜ RHEL/CentOS: bzip2",
            "gzip": "Debian/Ubuntu: gzip ｜ RHEL/CentOS: gzip",
            "zstd": "Debian/Ubuntu: zstd ｜ RHEL/CentOS: zstd",
        }.get(tool, tool)
        raise SourceBuildError(
            f"解压 {archive.name} 需要 `{tool}`，但它在 PATH 里找不到。\n"
            f"  装法：{hint}\n"
            "  [WARN] 注意 `-dev`/`-devel` 包只提供**编译用头文件**，"
            f"不提供 `{tool}` 可执行文件 —— 两者是不同的包。\n"
            f"  装好后重跑即可；已下载的 {archive.name} 会被缓存复用，不用重下。"
        )
    return


def extract(archive: Path, dest_dir: Path) -> Path:
    """解压 tarball，返回解出来的顶层目录。

    用 ``tar`` 而不是 Python 的 tarfile：源码包里可能有长路径、稀疏文件、
    或发行版特有的扩展属性，外部 tar 更稳，也更快。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not str(archive).endswith(_TAR_SUFFIXES):
        raise SourceBuildError(f"不认识的归档格式：{archive.name}")

    _ensure_extract_tool_for(archive)

    before = {p.name for p in dest_dir.iterdir()}
    run(["tar", "-xf", str(archive), "-C", str(dest_dir)], check=True,
        label=f"解压 {archive.name}")
    new = [p for p in dest_dir.iterdir() if p.name not in before and p.is_dir()]
    if len(new) != 1:
        raise SourceBuildError(
            f"解压 {archive.name} 后得到 {len(new)} 个顶层目录，无法判断源码树："
            f"{[p.name for p in new]}"
        )
    return new[0]



@dataclass
class BuildJob:
    """一次源码编译的完整配方。"""

    name: str
    version: str
    steps: list[tuple[list[str], str]] = field(default_factory=list)
    jobs: str = ""
    touch_before_configure: tuple[str, ...] = ()

    def resolved_jobs(self) -> str:
        return self.jobs or cpu_count_for_make()


def prepare_autotools(tree: Path, files: tuple[str, ...]) -> None:
    """把 configure 相关文件的时间戳推新，阻止 maintainer 规则重跑 autoconf。

    ⚠️ 这是一条必须记住的 CPython 编译陷阱：

    CPython 的 tarball 里 ``configure`` 比 ``configure.ac`` 旧一点点，
    于是 ``make`` 认为 configure 需要重新生成，就去调 ``autoconf``。
    而新系统（Ubuntu 24.04 自带 autoconf 2.72）与 CPython 3.14 的
    ``configure.ac`` 不兼容，会直接报：

        configure.ac:64: error: possibly undefined macro: AS_...
        autoreconf: ... failed with exit status: 1

    这个报错指向 configure.ac 和 automake，与"我在编译 Python"这件事
    看起来毫无关系 —— 实测第一次编译就卡在这里，排查了半小时。

    解法就是 ``touch`` 那几个文件，让 make 认为它们比 configure 新。
    """
    now = time.time()
    for name in files:
        p = tree / name
        if p.exists():
            os.utime(p, (now, now))
