"""Python 3.14 源码编译 —— 包管理器拿不到合格版本时的正解。


项目对 Python **3.14 是 DIE 级依赖**（``realtime_gateway`` 用 3.14 才有的
``asyncio.AsyncGenerator``），低于它的机器装完就是必然崩，不能"降级继续"。
但现实是：

| 发行版 | 官方源最高 | 结论 |
|---|---|---|
| Ubuntu 24.04 | 3.12 | 差两个小版本 |
| Debian 稳定 | 3.11 / 3.13（新） | 差 |
| Rocky / CentOS / RHEL | 3.12 上下 | 差 |

旧路径是加 deadsnakes PPA —— 那只对 Ubuntu 有效，且引入第三方源；
Rocky/CentOS 更连 PPA 都没有（那是 Debian 系的东西），
所以旧路径下这些发行版在 ``ensure_python`` 处直接就
``UnsupportedPlatform`` 死掉，**装都装不起来**。

源码编译天然跨发行版：只要 ``gcc``/``make`` + 几个开发库在，哪家都能编。
这正是用户 2026-10-03 的决策 —— "直接走编译安装的路径"，并且要求
一并把 Rocky/CentOS 打通。


中科大 ``/python/`` 目录**确实**有 3.14.8 的 tarball，实测可达。
但它只是**源码归档**，不是包管理源：它给不出 ``python3.14-venv``
这种拆分包（Debian 系把 ensurepip 拆成了独立包，缺它建 venv 报
"ensurepip is not available"）。所以「从中科大拉」和「自己编译」
并不冲突 —— 前者只是把源码包换了个更快的地方取。

这正是把镜像做成**有序候选列表**（中科大 → python.org）的原因：
镜像偶尔同步滞后（新版发布当天常见），官网必须留作回退。


``make altinstall`` + ``--prefix=/usr/local``：

- ``altinstall`` 只装 ``python3.14`` 而不动 ``python3`` 符号链接。
  **不能用 ``make install``** —— 那会覆盖系统 ``/usr/bin/python3``，
  直接搞坏发行版自带的工具（apt、dnf 自身都是 Python 写的）。
- ``/usr/local`` 是 ``--prefix`` 的默认值，且在主流发行版的
  PATH 中**先于** ``/usr/bin``，所以装完 ``python3.14`` 直接可用。
- ``--enable-optimizations``（PGO）能让运行时快 10-20%，代价是编译时间
  翻倍（多一轮带插桩的重新编译）。对**长期运行的服务**这个交换是划算的，
  所以默认开启；着急装机可以用 ``--no-optimize`` 关掉。

**为什么不开 ``--with-lto``（2026-10-03 去掉，实测依据）**：

GCC 的 full LTO 会在**链接阶段**把整个 ``libpython3.14.so`` 的 LTRANS 作业
串行重编。实测（10 核 / ``make -j9``）日志：

    lto-wrapper: warning: using serial compilation of 73 LTRANS jobs

73 个作业一个核一个核地过，`load average` 掉到 1.2 —— 也就是说这一段
``-jN`` 完全不起作用，白等。官方文档也写了 GCC 需要 ``ld.gold`` 或 ``lld``
才适合开 LTO，而这里没检查该前置条件。

**同一台机器的直接对比（都开 PGO）：**

| configure | make 耗时 |
|---|---|
| `--with-lto` | 16 分 25 秒 |
| 不含 LTO | **4 分 39 秒** |

也就是说 **LTO 单独吃掉约 12 分钟**，而它的增量收益远小于 PGO 的 10-20%。
所以**默认不开**；确实想要的可手工加。

**为什么必须处理 PGO 跑测失败（同上实测）**：

PGO 的 ``make`` 会先跑一遍 CPython 自带测试套件（43 文件 / 9595 用例）来
采集 profile。**任何一个用例失败，make 就断在 `profile-run-stamp`**，
留下的是插桩版二进制 —— 它连 ``--version`` 都跑不起来：

    symbol lookup error: undefined symbol: __gcov_indirect_call

实测在两种 configure 下**都**稳定失败（去掉 LTO 也一样），失败项固定是
``test_generators.SignalAndYieldFromTest.test_raise_and_yield_from`` ——
它用 ``_testcapi.raise_SIGINT_then_send_None`` 验证 SIGINT 在 ``yield from``
链条中的精确送达时机，而插桩改变了时序，于是拿到 `'FAILED' != 'PASSED'`。
这是**插桩的固有副作用，不是代码 bug**。

所以 `build_python` 里那条降级路径是**必经之路**，不是防御性编程：
不加它，这台机器 100% 装不上 Python 3.14。
"""

from __future__ import annotations

import os
from pathlib import Path

from .shell import run, which
from .source_build import (
    BuildJob,
    SourceBuildError,
    cpu_count_for_make,
    download_verified,
    ensure_c_compiler,
    extract,
    fetch_first_available,
    mirror_for,
    prepare_autotools,
)

__all__ = ["ensure_python_from_source", "PYTHON_TARGET", "build_python"]

PYTHON_TARGET = "3.14.0"

WORK_ROOT = Path("/var/cache/ipip-build")

_AUTOTOOLS_TOUCH = ("configure.ac", "aclocal.m4", "configure")


def _prefix_python() -> str:
    return "/usr/local/bin/python3.14"


def build_python(
    version: str = PYTHON_TARGET,
    *,
    optimize: bool = True,
    jobs: str = "",
) -> Path:
    """下载并编译 Python，返回装好后的解释器路径。

    单独暴露出来是为了能脱离安装器手工重跑 —— 编译失败时，
    运维/L 需要能一条命令复现整个流程，而不是去读安装器源码猜它做了什么。
    """
    work = WORK_ROOT / f"python-{version}"
    work.mkdir(parents=True, exist_ok=True)

    print(f"[python-build] 目标 {version}，工作目录 {work}")
    if optimize:
        print("[python-build] 启用 PGO 优化（--enable-optimizations）："
              "运行时快 10-20%，编译时间约翻倍")

    archive = _fetch(version, work)
    src_root = work / "src"
    if not src_root.exists():
        tree = extract(archive, work)
        tree.rename(src_root)

    prepare_autotools(src_root, _AUTOTOOLS_TOUCH)

    configure = [
        "./configure",
        "--prefix=/usr/local",
        "--with-ensurepip=install",
    ]
    if optimize:
        configure.append("--enable-optimizations")

    nproc = jobs or BuildJob("python", version).resolved_jobs()
    lo, hi = estimate_build_minutes(optimize=optimize)

    run(configure, cwd=str(src_root), check=True, label="python-build: configure")

    make_argv = ["make", f"-j{nproc}"]
    make_env = dict(os.environ)
    make_env["PROFILE_TASK"] = "-m test --pgo --timeout=1200 -x test_generators"
    make_label = f"make -j{nproc}（预计 {lo}-{hi} 分钟，最慢的一步）"
    res = run(make_argv, cwd=str(src_root), check=False, env=make_env,
              label=f"python-build: {make_label}")

    if not res.ok and optimize:
        print()
        print("[python-build] [WARN] PGO 阶段失败（profile 跑测里有用例没过）。")
        print(f"[python-build]        原始退出码 {res.code}，日志见上方。")
        print("[python-build]        已知的那条时序敏感用例（test_generators）"
              "已通过 PROFILE_TASK 排除，")
        print("[python-build]        所以这次是本机/本工具链的新情况，"
              "值得回头看一眼日志。")
        print("[python-build]        正在降级：去掉 --enable-optimizations 重编一次。")
        print("[python-build]        代价是多等几分钟；好处是**不会因此装不上 Python**。")
        print("[python-build]        （PGO 只影响运行时快 10-20%，不影响功能）")
        print()
        _clean_for_rebuild(src_root)
        configure = [a for a in configure if a != "--enable-optimizations"]
        optimize = False
        run(configure, cwd=str(src_root), check=True,
            label="python-build: configure（降级，无 PGO）")
        lo, hi = estimate_build_minutes(optimize=False)
        res = run(["make", f"-j{nproc}"], cwd=str(src_root), check=False,
                  label=f"python-build: make -j{nproc}（降级重编，约 {lo}-{hi} 分钟）")

    if not res.ok:
        raise SourceBuildError(
            f"make 失败（退出码 {res.code}）。源码树保留在 {src_root}，"
            f"可进去手工重跑定位：cd {src_root} && make -j{nproc}"
        )

    run(["make", "altinstall"], cwd=str(src_root), check=True,
        label="python-build: make altinstall")

    exe = Path(_prefix_python())
    if not exe.exists():
        raise SourceBuildError(
            f"编译流程走完但找不到 {exe}。\n"
            f"  请手工核对：ls /usr/local/bin/python3.*\n"
            f"  源码树保留在 {src_root}，可进去手工 make altinstall 看报错。"
        )
    _verify_and_link(exe)
    return exe


def _clean_for_rebuild(src_root: Path) -> None:
    """清掉上一次构建的半成品。

    必须清干净：PGO 的 ``make`` 会在插桩状态下产出 ``.o`` 与 gcov 数据
    （``.gcda``/``.gcno``），不清会让新的 configure 复用这些目标文件，
    结果**仍然链出插桩二进制**，重编等于白编。
    """
    run(["make", "clean"], cwd=str(src_root), check=False,
        label="python-build: 清理半成品（降级重编前）")
    patterns = ("*.o", "*.a", "*.so", "*.gcda", "*.gcno", "*.gcov")
    for pat in patterns:
        for p in src_root.rglob(pat):
            try:
                p.unlink()
            except OSError:
                pass


def _fetch(version: str, work: Path) -> Path:
    """按候选顺序取源码包，尽可能做校验。

    ⚠️ 校验策略是"能取到就校，取不到就记录摘要并**明确说明跳过了**"。
    实测（2026-10-03）：
      · python.org 只给 ``.crt`` / ``.sig`` / ``.sigstore`` / ``.spdx.json``，
        **没有** ``.sha256``；
      · 清华与中科大都不提供该文件（均 404）。
    所以不能假设有校验文件 —— 那会让每次安装都白跑一轮请求。
    但也**不能静默跳过**：静默跳过会让人以为校验过了，比不校验更糟。
    """
    candidates = tuple(
        (tpl.format(ver=version), label) for tpl, label in mirror_for("python")
    )
    archive = fetch_first_available(
        candidates, work / "download", cache_dir=WORK_ROOT / "cache",
    )
    expected = _remote_sha256(archive.url)
    if expected and expected != archive.sha256:
        raise SourceBuildError(
            f"sha256 校验失败：\n  期望 {expected}\n  实际 {archive.sha256}\n"
            f"  文件 {archive.path}\n  来源 {archive.url}\n已中止。"
        )
    if not expected:
        print(f"[build] ⚠ 该源未提供 .sha256 校验文件，已记录摘要备查："
              f"{archive.sha256}")
        print(f"[build]   如需严格校验，可用 gpg 验证 sigstore 签名："
              f"{archive.url}.sigstore")
    else:
        print(f"[build] ✓ sha256 校验通过")
    return archive.path


def _remote_sha256(url: str) -> str:
    """尝试取 ``<url>.sha256`` 并解析出摘要。取不到返回空串。"""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url + ".sha256", timeout=20) as resp:
            text = resp.read(4096).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return ""
    for token in text.replace("*", " ").split():
        token = token.strip().lower()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            return token
    return ""


def _sqlite_ok(ver: str) -> bool:
    """sqlite 引擎版本是否达到 chromadb 门槛（>= 3.35.0）。"""
    from ..judge.version import ge

    return ge(ver, "3.35.0")


def _verify_and_link(exe: Path) -> None:
    """冒烟 + 把解释器登记到系统路径。

    ⚠️ 判据是**真跑一次** ``import ssl``，不是看二进制存在：
    缺 openssl 头文件时 CPython 依然会"编译成功"并装上，
    直到真正用 ssl 才炸 —— 而 pip 全线依赖 ssl。
    这与 pnpm 的 corepack shim 是同一类问题（可执行 ≠ 可用）。
    """
    probe = [str(exe), "-c",
             "import sys,ssl,zlib,ctypes,sqlite3;"
             "print('%d.%d.%d' % sys.version_info[:3])"]
    res = run(probe, check=False, echo=False)
    if not res.ok:
        raise SourceBuildError(
            f"{exe} 装上了但关键模块导入失败：\n{res.stdout[-2000:]}\n"
            "  最常见原因是编译时缺 openssl / libffi / zlib 头文件。\n"
            "  请补齐后删掉源码树重编：rm -rf " + str(WORK_ROOT / "python-*")
        )
    version = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "?"
    print(f"[python-build] ✓ 冒烟通过：{exe} → {version}（ssl/zlib/ctypes/sqlite3 均可导入）")

    sq = run([str(exe), "-c", "import sqlite3;print(sqlite3.sqlite_version)"],
             check=False, echo=False)
    sqlite_ver = sq.stdout.strip() if sq.ok else ""
    if sqlite_ver and not _sqlite_ok(sqlite_ver):
        print(f"[python-build] ⚠ 该解释器的 sqlite 为 {sqlite_ver} < 3.35.0"
              "（chromadb 要求），AI/RAG 功能将降级")
        print("[python-build]   出路：改用 uv 安装的 Python（自带 sqlite 3.53.1），"
              "或换 el10 / Debian 12+ 等系统 sqlite 达标的发行版")

    if not which("python3.14"):
        print(f"[python-build] ⚠ python3.14 不在 PATH 中，请确认 /usr/local/bin 在 PATH 内，"
              f"或使用绝对路径 {exe}")


_BENCH_MINUTES_PGO = {          # (下限, 上限)，按键是 make 并发度
    1: (28, 45),
    2: (18, 30),
    4: (12, 20),
    8: (5, 9),                  # 实测点：10 核机留一核给心跳，make -j8/-j9 同档
}


def estimate_build_minutes(*, optimize: bool = True) -> tuple[int, int]:
    """估算编译耗时区间（分钟）。

    基准来自上表的实测值，取**不超过本机并发度的最大实测点**（不做线性外推 ——
    CPython 的编译时间对核数不线性，外推会越推越偏）。

    并发度只有一条来源：`cpu_count_for_make()`，它已截断在 8，而表的最大键也是 8。
    所以 `n` 必然落在表的闭区间内，查表必定命中 —— 这里**刻意不写 default 兜底**：
    兜底会把"截断失效"这类缺陷悄悄吞掉，让它表现成"估算很合理"。
    """
    n = int(cpu_count_for_make())
    keys = sorted(_BENCH_MINUTES_PGO)
    floor_key = max(k for k in keys if k <= n)      # n >= 1，必命中
    lo, hi = _BENCH_MINUTES_PGO[floor_key]

    if not optimize:
        lo, hi = max(1, int(lo * 0.55)), max(2, int(hi * 0.55))
    return lo, hi


def _announce_build_cost(version: str, *, optimize: bool = True) -> None:
    """开编之前把代价说清楚：要多久、为什么这么久、中途看到什么算正常。"""
    lo, hi = estimate_build_minutes(optimize=optimize)
    n = cpu_count_for_make()
    print()
    print(f"[python-build] 即将从源码编译 Python {version}")
    print(f"               ┌ 预计耗时 {lo}-{hi} 分钟（本机 {os_cpu_count()} 核，"
          f"用 make -j{n} 编译；再多的核也压不下来了）")
    if optimize:
        print("               ├ 已启用 PGO 优化：编译会跑两遍（第二遍带插桩重编），")
        print("               │  换取运行时快 10-20%。想快可加 --no-optimize 关掉")
    print("               ├ 中途长时间没有输出是**正常的**（make 不打印进度条），")
    print("               │  安装器会持续发心跳。**请勿中断** —— 中断会留下半安装状态")
    print("               ├ 编译前置的 -dev 包（libssl-dev 等）**必须在开编前装好**：")
    print("               │  缺了它们不会报错，而是『编译成功但模块缺失』（实测缺 openssl")
    print("               │  头文件时 ssl 静默消失，pip 全线不可用），等于白等一场")
    print("               ├ 源码包 22MB，从国内镜像通常几十秒；卡在下载说明镜像有问题，")
    print("               │  会自动切换到下一个源，无需人工干预")
    print(f"               └ 源码树保留在 {WORK_ROOT}/python-{version}/，"
          f"失败时可进去手工重跑")
    print()


def os_cpu_count() -> int:
    """单独包一层是为了让测试能不打桩 os 模块就改到核数。"""
    import os

    return os.cpu_count() or 2


def ensure_python_from_source(host, minimum: str, *, optimize: bool = True) -> str:
    """安装器入口：基线不满足时从源码编译。

    返回装好后的解释器路径；若当前环境已满足基线则返回现有路径（不做任何事）。
    """
    from ..judge.version import ge

    if host.python_version and ge(host.python_version, minimum):
        return host.python_bin

    print(f"[syspkg] Python {host.python_version or '缺失'} < {minimum}，"
          f"改走源码编译（发行版源给不出该版本）")
    _announce_build_cost(PYTHON_TARGET, optimize=optimize)
    ensure_c_compiler(host)
    exe = build_python(optimize=optimize)
    return str(exe)
