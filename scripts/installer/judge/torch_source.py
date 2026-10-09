"""pytorch wheel 索引解析与 CPU 源择优。

这里每一行几乎都对应一次真机误判，按踩坑顺序排列：

1. **不能照抄索引页的 href**
   南大索引 1219 条 href 里有 703 条把下载地址写成 `download-r2.pytorch.org` 的绝对 URL。
   照抄的话约 58% 概率绕回官方 CDN，选了镜像却享受不到镜像的速度。
   → 只取 href 的 **basename**，再用 `base_url + filename` 自拼。

2. **wheel 的下载地址是扁平的**
   `<index>/<filename>`，不带包名层。嵌套的 `<index>/<pkg>/<filename>` 在官方会 403、
   在南大会 404。详见 ``docs/ops/install-behavior-baseline.md`` 4.2。

3. **Linux x86_64 的 wheel 标签是 ``manylinux_2_28_x86_64``**
   写成 ``linux_x86_64`` 会全 404 —— 而且历史上有过把"标签写错"误判成"镜像缺版本"。

4. **"错误页"也可能是 HTTP 200**
   清华 / 中科大 / 阿里云对不存在的 pytorch 索引返回 152B / 192B / 2316B 的错误页，
   状态码同样是 200。所以可用性判定交给 :func:`available`（按响应体大小判定），
   而不是看状态码。

这些规则全部来自实测，改动前建议先读上述文档第 4 节。
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from .download import ProbeResult, available, probe

__all__ = [
    "wheel_filenames",
    "match_wheels",
    "highest_wheel",
    "flat_wheel_url",
    "select_cpu_index",
]

_HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def wheel_filenames(index_url: str, *, package: str = "torch", timeout: float = 25.0) -> list[str]:
    """从 PEP 503 simple index 页提取 wheel **文件名**（带 URL 编码的原始形态）。

    返回原始形态（含 ``%2B``）而不是解码后的字符串，因为要直接拼回 URL：
    解码后再拼会把 ``+`` 变成空格语义，导致 404。
    """
    import urllib.request

    url = index_url.rstrip("/") + "/" + package + "/"
    req = urllib.request.Request(url, headers={"User-Agent": "ipip-installer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", "ignore")

    names: list[str] = []
    for href in _HREF_RE.findall(html):
        raw = href.split("#", 1)[0]          # 去掉 #sha256=...
        name = raw.rsplit("/", 1)[-1]        # 只取 basename —— 见模块文档第 1 条
        if name.endswith(".whl"):
            names.append(name)
    return names


def match_wheels(names: list[str], *, cp_tag: str, arch_tag: str) -> list[str]:
    """筛出匹配「Python ABI × 平台」的 CPU wheel。

    ``arch_tag`` 形如 ``manylinux_2_28_x86_64`` / ``manylinux_2_28_aarch64``。
    注意平台标签不可写成 ``linux_x86_64``（见模块文档第 3 条）。
    """
    pattern = re.compile(
        rf"^torch-(\d+)\.(\d+)\.(\d+)(%2B|\+)cpu-{cp_tag}-{cp_tag}-(?:t-)?{arch_tag}\.whl$"
    )
    out: list[str] = []
    for n in names:
        if pattern.match(n):
            out.append(n)
    return sorted(set(out), key=_version_key)


def _version_key(name: str) -> tuple[int, int, int]:
    """wheel 文件名 → 可比较的版本三元组。"""
    m = re.match(r"^torch-(\d+)\.(\d+)\.(\d+)", name)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)  # type: ignore[return-value]


def highest_wheel(names: list[str], *, cp_tag: str, arch_tag: str) -> str | None:
    """该 ABI+平台下可用的最高版本 wheel 文件名；没有则 None。"""
    matched = match_wheels(names, cp_tag=cp_tag, arch_tag=arch_tag)
    return matched[-1] if matched else None


def flat_wheel_url(index_url: str, filename: str) -> str:
    """拼出**扁平**形态的 wheel 下载地址（见模块文档第 2 条）。"""
    return index_url.rstrip("/") + "/" + filename


def select_cpu_index(
    *,
    candidates: list[str],
    cp_tag: str,
    arch_tag: str,
    min_kbps: int = 500,
    sample_bytes: int = 12 * 1024 * 1024,
    timeout: float = 25.0,
) -> tuple[str | None, list[tuple[str, ProbeResult]]]:
    """在候选源里选出「确有资源且最快」的那个。

    返回 ``(选中的 index_url, [(源, 探测结果), ...])``；全部不可用时为 ``(None, 报告)``。

    双重判据，缺一不可：
      - **能不能下载到**：目标 wheel 是否真实存在（靠 :func:`probe` 的响应体判定）
      - **有多快**：真实吞吐是否达标 ``min_kbps``

    只盯速度会选出"很快地返回错误页"的源；只看能不能下会选中最慢但可用的源。
    """
    report: list[tuple[str, ProbeResult]] = []
    best_url: str | None = None
    best_kbps = 0

    for index in candidates:
        ping = probe(index.rstrip("/") + "/torch/", sample_bytes=4096, timeout=timeout)
        if not ping.ok:
            report.append((index, ping))
            continue

        try:
            names = wheel_filenames(index, timeout=timeout)
        except Exception as e:  # 索引拉取失败不能中断整体择优
            report.append((index, ProbeResult(index, False, reason=f"索引拉取失败: {e}")))
            continue

        wheel = highest_wheel(names, cp_tag=cp_tag, arch_tag=arch_tag)
        if not wheel:
            report.append(
                (index, ProbeResult(index, False, reason=f"无 {cp_tag}/{arch_tag} 的 CPU wheel"))
            )
            continue

        result = probe(flat_wheel_url(index, wheel), sample_bytes=sample_bytes, timeout=timeout)
        result = ProbeResult(
            result.url, result.ok, result.status, result.bytes_read, result.elapsed,
            (result.reason or unquote(wheel)),
        )
        report.append((index, result))
        if result.ok and result.kbps >= min_kbps and result.kbps > best_kbps:
            best_kbps = result.kbps
            best_url = index

    return best_url, report
