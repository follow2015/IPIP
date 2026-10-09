"""Python 虚拟环境与依赖安装。

这里承接旧脚本第 2 步，保留了三条用事故换来的规则：

1. **venv 可用性必须先校验，且独立于 g++ 检查**
   Debian/Ubuntu 把 venv 拆成独立包 ``python3.14-venv``（内含 ensurepip），
   最小安装默认不带 → ``ensurepip is not available``，Ubuntu 26.04 首次部署就卡在这。
   旧脚本曾因为"g++ 在就提前 return"而跳过 venv 校验，遇到过
   「g++ 在、venv 不在」的盒子一路走到第 2 步才炸。

2. **torch flavor 必须持久化，否则 GPU 会被静默降级成 CPU**
   状态文件两行：flavor（cpu|gpu）、cuda_multi_mirror（0|1）。
   不加这条，"下载新版本再执行一次安装"会因默认 cpu，把生产 GPU 环境的 torch 换掉。

3. **CUDA 版切回 CPU 时要清残留 nvidia-* 包**
   ⚠️ 旧脚本在这里有一条 **恒假** 判据：``set -o pipefail`` 下
   ``pip list | grep -qi "^nvidia-"`` 时，grep -q 命中即退出 → 上游 pip 收
   SIGPIPE(141) → 整条管道非 0 → 判定永远为假，残留包从来没被发现过。
   Python 里直接解析 stdout 列表，没有这个问题。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from ..judge.sources import select_pip_source
from ..judge.torch_source import select_cpu_index
from .shell import Result, run

__all__ = [
    "Venv",
    "ensure_venv",
    "install_requirements",
    "install_torch",
    "detect_nvidia_leftovers",
]

TORCH_CANDIDATES: list[str] = [
    "https://mirrors.nju.edu.cn/pytorch/whl/cpu",
    "https://download.pytorch.org/whl/cpu",
]

_WHL_VERSION_RE = re.compile(r"torch-(\d+\.\d+\.\d+)")


class Venv:
    """隔离环境的句柄。"""

    def __init__(self, root: Path, python_bin: str) -> None:
        self.root = root
        self.builder = python_bin
        self.py = str(root / "bin" / "python")

    @property
    def exists(self) -> bool:
        return Path(self.py).is_file()

    def create(self) -> Result:
        return run([self.builder, "-m", "venv", str(self.root)], check=True,
                   label="创建 venv", timeout=300)


def ensure_venv(root: Path, python_bin: str) -> Venv:
    """创建 venv；不可用时给出精确可执行的修复指令（而不是含糊的报错）。"""
    v = Venv(root, python_bin)
    if v.exists:
        print(f"[venv] 已有虚拟环境: {v.py}")
        return v

    probe_rc = run([python_bin, "-m", "venv", "--help"], check=False, echo=False)
    if not probe_rc.ok:
        short = ".".join(python_bin.split("python")[-1:]) or ""
        raise RuntimeError(
            f"{python_bin} 无法创建虚拟环境（ensurepip 不可用）。\n"
            "  Debian/Ubuntu 把 venv 拆成了独立包，必须单独安装：\n"
            f"    apt-get install -y python{short}-venv\n"
            "  RHEL 系：dnf install -y python3-virtualenv"
        )

    v.create()
    print(f"[venv] 已创建: {v.py}")
    return v


@lru_cache(maxsize=1)
def _choose_pip_args() -> tuple[str, ...]:
    """实测选源，返回要拼进 pip 的参数。

    全程都有兜底：选不出就用官方源继续，不让"选源"这件事本身成为安装失败点。

    用 ``lru_cache`` 而不是每次重测：一次完整安装里 ``upgrade_pip`` 与
    ``install_requirements`` 都会调它，重测等于把三个源各 12MB 的取样下载做两遍
    —— 这是纯粹的重复开销，用户感知到的就是"安装莫名慢了半分钟"。
    缓存还顺带保证前后两段用的是同一个源，不会前半程快后半程忽然掉速。
    """
    url, report = select_pip_source()
    print("[venv] pip 源实测:")
    for c in report:
        mark = "✓" if c.ok else "✗"
        print(f"    {mark} {c.name:6} {c.result.mib_s:>10}  {c.url}")
        if c.result.reason:
            print(f"        {c.result.reason[:72]}")
    if not url:
        return ()
    return ("-i", url)


def upgrade_pip(v: Venv) -> None:
    run([v.py, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools",
         *_choose_pip_args(), "--timeout", "30", "--retries", "3"],
        check=False, label="升级 pip")


UV_CONCURRENCY = "8"


def _index_url() -> str:
    """实测选出的源 URL（空串 = 交给工具默认值）。"""
    args = _choose_pip_args()
    return args[1] if len(args) == 2 else ""


def _ensure_uv(v: Venv) -> str | None:
    """在 venv 内装 uv，返回可执行文件路径；装不上返回 ``None``（调用方回退 pip）。

    为什么值得：uv 并发下载 + 复用缓存的安装，实测把 requirements 安装从
    ~1000s 压到 228s（4.4x），是全流程最大的单笔提速。

    为什么装在 venv 里而不要求宿主机预装：不引入新的外部前提。
    装不上就回退，**绝不因为加速器缺失而让安装失败** —— 加速器只能是
    "更快"，不能变成"能不能装"的新依赖。
    """
    uv = Path(v.py).parent / "uv"
    if uv.is_file():
        return str(uv)
    res = run([v.py, "-m", "pip", "install", "uv", *_choose_pip_args(),
               "--timeout", "30", "--retries", "3"],
              check=False, label="安装依赖加速器 uv", quiet_tail=20)
    if res.ok and uv.is_file():
        print(f"[venv] uv 就绪: {uv}（并发上限 {UV_CONCURRENCY}）")
        return str(uv)
    print("[venv] uv 不可用，回退 pip（会慢一些，但不影响结果）")
    return None


def _deps_satisfied(v: Venv) -> bool:
    """用 ``pip check`` 判定已装依赖的依赖图是否完整。

    为什么需要这道校验：lock 路径用 ``--no-deps`` 安装，uv 完全跳过依赖图
    求解，也就**不会发现 lock 漏了包**。lock 是生成物，可能过期（改了
    requirements.txt 却没重生成）。没有校验的话，漏装会一路潜伏到运行期，
    以"某个模块 import 不到"的形式炸在一个离真因很远的地方。

    ``pip check`` 是真实判据而非形式检查：它逐个核对已装包声明的依赖是否
    都在环境里且版本满足 —— 包括不在 lock 里的 torch（由 install_torch 先装）。
    """
    res = run([v.py, "-m", "pip", "check"], check=False, echo=False)
    if not res.ok:
        print("[venv] pip check 发现依赖缺口：\n    "
              + "\n    ".join((res.stdout or "").strip().splitlines()[:8]))
    return res.ok


def install_requirements(v: Venv, project_root: Path) -> None:
    req = project_root / "requirements.txt"
    if not req.is_file():
        raise FileNotFoundError(f"找不到依赖清单: {req}")

    uv = _ensure_uv(v)

    lock = project_root / "requirements.lock"
    if uv and lock.is_file():
        env = dict(os.environ, UV_CONCURRENT_DOWNLOADS=UV_CONCURRENCY,
                   UV_HTTP_TIMEOUT="60")
        args = [uv, "pip", "install", "--python", v.py, "--no-deps", "-r", str(lock)]
        if _index_url():
            args += ["--index-url", _index_url()]
        res = run(args, check=False, env=env,
                  label="安装 requirements.lock（跳过依赖求解）", quiet_tail=200)
        if res.ok and _deps_satisfied(v):
            return
        print("[venv] lock 路径未通过完整性校验，回退完整求解重来：\n    "
              + "\n    ".join(res.lines[-6:]))

    if uv:
        env = dict(os.environ, UV_CONCURRENT_DOWNLOADS=UV_CONCURRENCY,
                   UV_HTTP_TIMEOUT="60")
        args = [uv, "pip", "install", "--python", v.py, "-r", str(req)]
        if _index_url():
            args += ["--index-url", _index_url()]
        res = run(args, check=False, env=env,
                  label="安装 requirements.txt (uv)", quiet_tail=200)
        if res.ok:
            return
        print("[venv] uv 安装未成功，回退 pip 重来：\n    "
              + "\n    ".join(res.lines[-6:]))

    res = run([v.py, "-m", "pip", "install", "-r", str(req), *_choose_pip_args(),
               "--timeout", "60", "--retries", "5"],
              check=False, label="安装 requirements.txt", quiet_tail=200)
    if not res.ok:
        raise RuntimeError(
            "依赖安装失败。最常见的原因是缺编译工具链 —— chroma-hnswlib 在 PyPI 上\n"
            "  只有源码分发，必须本地编译；而 pip 的安装是**原子性**的，\n"
            "  一个包构建失败会导致整个 requirements 都不安装。\n"
            f"  可检查：{v.builder[:0] or ''}apt-get install -y build-essential python3-dev\n"
            f"  末行日志:\n    " + "\n    ".join(res.lines[-10:])
        )


def _installed_torch_version(v: Venv) -> str:
    res = run([v.py, "-c", "import importlib.metadata as m; print(m.version('torch'))"],
              check=False, echo=False)
    return res.stdout.strip() if res.ok else ""


def detect_nvidia_leftovers(v: Venv) -> list[str]:
    """列出残留的 nvidia-* 包（Python 版，避开 pipefail + grep -q 的 SIGPIPE 恒假）。

    旧脚本的判据是 ``pip list | grep -qi '^nvidia-'``，在 ``set -o pipefail`` 下
    grep -q 命中即退出导致上游收 SIGPIPE → 判据恒假 → 残留包从未被发现。
    """
    res = run([v.py, "-m", "pip", "list", "--format=json"], check=False, echo=False)
    if not res.ok:
        return []
    try:
        pkgs = json.loads(res.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [p["name"] for p in pkgs if p.get("name", "").lower().startswith("nvidia-")]


def _read_flavor_state(path: Path) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", ""
    flavor = lines[0].strip() if len(lines) > 0 else ""
    multi = lines[1].strip() if len(lines) > 1 else "0"
    return flavor, multi


def resolve_flavor(state_file: Path, explicit: str | None) -> tuple[str, str]:
    """决定本次用 cpu 还是 gpu。

    :param explicit: 用户显式指定时的取值；None 表示沿用上次记录。
    """
    if explicit:
        return explicit, "0"
    saved, multi = _read_flavor_state(state_file)
    if saved == "gpu":
        print("[venv] 沿用上次记录的 GPU 版 torch（如需改回 CPU 请显式指定 --cpu）")
        return "gpu", multi or "0"
    return "cpu", "0"


CUDA_MIRROR_POOL: tuple[str, ...] = (
    "https://mirrors.ustc.edu.cn/pypi/web",
    "https://pypi.org",
    "https://mirrors.cloud.tencent.com/pypi",
)
CUDA_OFFICIAL_MIRROR = "https://pypi.org"
CUDA_WHEEL_CACHE = Path(os.environ.get("PIP_WHEEL_CACHE")
                        or Path(tempfile.gettempdir()) / "ipip-wheels")
CUDA_SEGMENTS = 8
_CUDA_BIG_PREFIXES = ("nvidia_", "nvidia-", "triton-")


def _cuda_big_packages(v: Venv, report_path: Path) -> list[tuple[str, str]]:
    """pip --dry-run 解析 torch 的 CUDA 依赖，挑出超大 wheel。

    返回 ``[(包名, wheel 文件名)]``。只挑 nvidia-*/triton（2-3GB 的大头），
    torch 本体（554MB）与其余小包交给 pip 正常安装。

    ⚠️ 解析必须走**实测选出的镜像**（拼 `_choose_pip_args()`，评审 P1-7）：
    默认源直连 pypi.org，国内网络不可达时 rows=[]，加速开关会静默退化为
    最慢路径 —— 与"开关静默失效"同型的缺陷。
    """
    argv = [v.py, "-m", "pip", "install", "--dry-run", "--ignore-installed",
            "--report", str(report_path), *_choose_pip_args(), "torch"]
    res = run(argv, check=False, echo=False, quiet_tail=20)
    if not res.ok or not report_path.is_file():
        return []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows: list[tuple[str, str]] = []
    for item in report.get("install", []):
        url = (item.get("download_info") or {}).get("url", "")
        if not url.endswith(".whl"):
            continue
        fn = url.rsplit("/", 1)[-1].split("#")[0]
        if not fn.startswith(_CUDA_BIG_PREFIXES):
            continue
        rows.append((fn.split("-")[0].replace("_", "-").lower(), fn))
    return rows


def _wheel_url_on_mirror(mirror: str, pkg: str, fn: str) -> tuple[str, str]:
    """在镜像的 simple 索引页里定位 wheel，返回 ``(真实 URL, sha256)``。

    sha256 取自 simple 页 href 的 ``#sha256=<hex>`` fragment（PEP 503 标准），
    用于下载后的完整性校验（评审 P1-8）；拿不到返回空串（退化为大小校验）。

    href 有三种形态（旧 install.sh 实测归纳）：
      · 绝对 URL（pypi.org 的 simple 页直接给 https://...）
      · ``../../packages/...`` 相对路径（USTC web 布局）—— 按旧实现的
        ``${u#../../}`` 处理：拼到 mirror 根下。**不能用 urljoin**：
        它会把 ``../../`` 解析到 /pypi/packages，而 USTC 的文件实际在
        /pypi/web/packages 下。
      · 根相对/普通相对路径
    """
    import re as _re

    res = run(["curl", "-s", "-m", "20", f"{mirror}/simple/{pkg}/"],
              check=False, echo=False)
    if not res.ok:
        return "", ""
    m = _re.search(r'href="([^"]*' + _re.escape(fn) + r'[^"]*)"', res.stdout or "")
    if not m:
        return "", ""
    u = m.group(1)
    sha = ""
    if "#sha256=" in u:
        u, _, sha = u.partition("#sha256=")
    if u.startswith("http"):
        return u, sha
    if u.startswith("../"):
        return f"{mirror}/{u[6:]}", sha        # 剥掉 "../../"，见上
    return f"{mirror}/{u.lstrip('/')}", sha


def _content_length(url: str) -> int:
    """HEAD 拿文件大小；拿不到返回 0（调用方跳过该包）。"""
    import re as _re

    res = run(["curl", "-sIL", "-m", "20", url], check=False, echo=False)
    lengths = _re.findall(r"[Cc]ontent-[Ll]ength:\s*(\d+)", res.stdout or "")
    return int(lengths[-1]) if lengths else 0


def _download_segments(url: str, out: Path, total: int,
                       segments: int = CUDA_SEGMENTS,
                       sha256: str = "") -> bool:
    """curl Range 分段并行下载，拼装后校验完整性（sha256 优先，大小兜底）。

    ⚠️ 完整性校验是硬门槛（评审 P1-8）：镜像内容漂移、响应 200 而非 206
    （服务器忽略 Range）等情况，光对总大小查不出来 —— 由 sha256 兜住；
    半截文件绝不能被当成预取成功的包离线安装。

    用 curl 而不是 urllib：``--retry 10 --retry-all-errors`` 是旧实现
    实测打磨过的容错组合（瞬时网络抖动不能让整个预取失败）。
    """
    seg = (total + segments - 1) // segments
    jobs = []
    for i in range(segments):
        s = i * seg
        e = min(s + seg - 1, total - 1)
        if s <= e:
            jobs.append((i, s, e))

    def fetch(job: tuple[int, int, int]) -> bool:
        i, s, e = job
        res = run(["curl", "-sL", "--retry", "10", "--retry-all-errors",
                   "-r", f"{s}-{e}", "-o", f"{out}.part{i}", url],
                  check=False, echo=False)
        return res.ok

    with ThreadPoolExecutor(max_workers=segments) as pool:
        results = list(pool.map(fetch, jobs))
    if not all(results):
        for p in out.parent.glob(out.name + ".part*"):
            p.unlink(missing_ok=True)
        return False
    with open(out, "wb") as w:
        for i, _, _ in jobs:
            part = Path(f"{out}.part{i}")
            w.write(part.read_bytes())
            part.unlink()
    def _discard() -> bool:
        out.unlink(missing_ok=True)
        return False

    if sha256:
        import hashlib

        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        if digest.lower() != sha256.lower():
            print(f"[venv]   ✘ {out.name} sha256 不符（{digest[:12]}…），丢弃")
            return _discard()
        return True
    if out.stat().st_size != total:
        return _discard()
    return True


def _mirror_probe_seconds(base: str, *, timeout: float = 8.0) -> float | None:
    """探测一个镜像的索引页：返回耗时秒数，不可达返回 ``None``。

    带上 UA：裸 urllib 会被部分镜像 403（这在 sha256 探测上踩过一次）。
    """
    import time
    import urllib.request

    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/simple/torch/",
            headers={"User-Agent": "ipip-installer/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if resp.status != 200:
                return None
            resp.read(65536)              # 读一小段，避免只测到响应头
    except Exception:  # noqa: BLE001 —— 探测失败即淘汰该镜像
        return None
    return time.monotonic() - t0


def _pick_cuda_mirrors() -> tuple[str, ...]:
    """按**可达性与探测耗时**筛选并排序镜像池。

    ⚠️ 不能对整池 ``idx % len(pool)`` 硬分散（2026-10-04 评审反馈）：
    预取按包名轮流分配，国外机器上 2/3 的包会被分到国内镜像 —— 与 dnf
    第③步"整切 USTC"是同一类错误，只是这里伪装成了"分散加速"。

    与 pip/npm/torch 索引、dnf 切源保持同一条口径：**先探测再决策**。
    不可达的剔除，可达的按耗时升序（快的先分到包）；全部不可达退回官方源，
    不让"选源"变成安装失败点。
    """
    import time
    import urllib.request

    scored: list[tuple[float, str]] = []
    for base in CUDA_MIRROR_POOL:
        secs = _mirror_probe_seconds(base)
        if secs is None:
            continue
        scored.append((secs, base))

    if not scored:
        print("[venv] 镜像池全部不可达，预取退回官方源")
        return (CUDA_OFFICIAL_MIRROR,)
    scored.sort(key=lambda item: item[0])
    return tuple(base for _, base in scored)


def prefetch_cuda_multi_mirror(v: Venv) -> list[str]:
    """预取 CUDA/triton 大包，返回成功落盘的 wheel 路径列表。

    失败/空结果返回 ``[]``，调用方回退 pip 默认安装 —— 预取是加速器，
    **不能变成能不能装的新依赖**（与 ``_ensure_uv`` 同一条纪律）。
    """
    report = CUDA_WHEEL_CACHE / "cuda-report.json"
    CUDA_WHEEL_CACHE.mkdir(parents=True, exist_ok=True)
    print("[venv] --gpu-fast：解析 torch 的 CUDA 依赖（pip --dry-run，只解析不下载）...")
    rows = _cuda_big_packages(v, report)
    if not rows:
        print("[venv] 未解析到 CUDA/triton 大包，跳过预取")
        return []
    print(f"[venv] 待预取 {len(rows)} 个大包")
    mirrors = _pick_cuda_mirrors()
    print(f"[venv] 可用镜像 {len(mirrors)} 个（{', '.join(m.split('//')[-1] for m in mirrors)}），"
          f"按包名分散、每包 {CUDA_SEGMENTS} 连接")

    wheels: list[str] = []
    ok = fail = 0
    for idx, (pkg, fn) in enumerate(rows):
        out = CUDA_WHEEL_CACHE / fn
        mirror = mirrors[idx % len(mirrors)]
        url, sha = _wheel_url_on_mirror(mirror, pkg, fn)
        if out.is_file():
            if sha and _file_sha256(out) == sha.lower():
                print(f"[venv]   已缓存 {pkg}（sha256 ✓）")
                wheels.append(str(out))
                ok += 1
                continue
            if sha:
                print(f"[venv]   缓存的 {pkg} sha256 不符，重新下载")
                out.unlink(missing_ok=True)
            else:
                print(f"[venv]   已缓存 {pkg}（无 sha256 参照，跳过校验）")
                wheels.append(str(out))
                ok += 1
                continue
        total = _content_length(url) if url else 0
        if not url or total <= 0:
            print(f"[venv]   {pkg} 在 {mirror} 未找到或无法获取大小，跳过")
            fail += 1
            continue
        print(f"[venv]   预取 {pkg}（{total // (1024 * 1024)}MB，"
              f"源 {mirror.split('//')[-1]}）...")
        if _download_segments(url, out, total, sha256=sha):
            wheels.append(str(out))
            ok += 1
        else:
            print(f"[venv]   ✘ {pkg} 预取失败（大小/哈希不符），丢弃")
            fail += 1
    print(f"[venv] 预取结束：成功 {ok} 个，失败 {fail} 个")
    return wheels


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_torch(
    v: Venv,
    project_root: Path,
    flavor: str,
    *,
    cuda_multi_mirror: str = "0",
    force_upstream: bool = False,
    pip_fallback_index: str = "https://mirrors.ustc.edu.cn/pypi/simple/",
) -> None:
    """安装 CPU 或 GPU 版 torch。"""
    state_file = project_root / "instance" / ".install-flavor"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{flavor}\n{cuda_multi_mirror}\n", encoding="utf-8")
    print(f"[venv] torch flavor 已记录到 {state_file}: {flavor}")

    if flavor == "gpu":
        print("[venv] GPU(CUDA) 版：体积约 2.6-3.5GB，预计 30-60 分钟，"
              "无 NVIDIA GPU 的机器属纯浪费")
        if cuda_multi_mirror == "1":
            wheels = prefetch_cuda_multi_mirror(v)
            if wheels:
                run([v.py, "-m", "pip", "install", *wheels, "--no-deps",
                     "--timeout", "60", "--retries", "3"],
                    check=False, label="离线安装已预取的 CUDA 大包", quiet_tail=40)
        run([v.py, "-m", "pip", "install", "torch", "--timeout", "60", "--retries", "5"],
            check=True, label="安装 GPU 版 torch")
        return

    cur = _installed_torch_version(v)
    if "+cpu" in cur:
        print(f"[venv] 已安装 CPU 版 torch（{cur}），跳过")
        return
    if cur:
        print(f"[venv] 当前 torch={cur} 不是 CPU 版，将替换。")

    from ..judge.facts import collect

    facts = collect()
    candidates = TORCH_CANDIDATES
    if force_upstream:
        candidates = ["https://download.pytorch.org/whl/cpu"]
        print("[venv] --torch-upstream 指定：强制走官方源")

    chosen, report = select_cpu_index(
        candidates=candidates,
        cp_tag=facts.cp_tag or "cp314",
        arch_tag=facts.wheel_arch_tag or "manylinux_2_28_x86_64",
    )
    for url, r in report:
        mark = "✓" if r.ok else "✗"
        print(f"    {mark} {url:52} {r.mib_s:>10}")
        if r.reason:
            print(f"        {r.reason[:72]}")

    index = chosen or "https://download.pytorch.org/whl/cpu"
    print(f"[venv] torch 索引源: {index}")
    res = run([v.py, "-m", "pip", "install", "torch",
               "--index-url", index,
               "--extra-index-url", pip_fallback_index,
               "--force-reinstall", "--no-deps",
               "--timeout", "60", "--retries", "5"],
              check=False, label="安装 CPU 版 torch", quiet_tail=120)
    if not res.ok:
        raise RuntimeError(
            f"CPU 版 torch 安装失败（索引源 {index}）。可尝试：\n"
            f"  {v.py} -m pip install --force-reinstall torch --index-url {index}\n"
            f"  末行日志:\n    " + "\n    ".join(res.lines[-8:])
        )

    leftovers = detect_nvidia_leftovers(v)
    if leftovers:
        print(f"[venv] ⚠ 检测到残留 CUDA 依赖 {len(leftovers)} 个（对 CPU 版无用，白占数 GB）：")
        print(f"    {' '.join(leftovers[:8])}{' ...' if len(leftovers) > 8 else ''}")
        print(f"    清理：{v.py} -m pip uninstall -y " + " ".join(leftovers))

    newv = _installed_torch_version(v)
    print(f"[venv] torch 安装完成: {newv}")
