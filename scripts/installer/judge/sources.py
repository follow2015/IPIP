"""pip 与 npm 的源择优。

三个源都遵循同一条判据：**实测真实吞吐**，而不是"能不能访问"或"能不能装完"。

为什么不能用弱判据（这三件事都真实发生过）：

- **首页响应时间**：官方 pytorch CDN 首页只有几十 KB/s，wheel 真实下载却可达数 MB/s。
  首页慢 ≠ 下载慢。
- **能不能装完**：``debug`` 这种几十 KB 的小包，即使源被限到 12–47 KiB/s 也能在
  120s 窗口内装完并返回成功。旧 install.sh 因此选中慢源，把整段前端构建拖成瓶颈。
- **HTTP 200**：错误页也是 200（见 judge/download.py 的实测数据）。

关于「是不是国内」这个请求：

这里**不做地理判定来直接决策**。理由是当前 installer 自己就在强调的那条纪律 ——
弱信号不该直接当结论用：时区可以改、CDN anycast 让地域与网络质量脱钩、海外 CN2
可能比国内普通线路更快直连。地理信息只用来**缩小候选集**（决定要不要把国内镜像
放进候选），最终由实测吞吐拍板。
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin

from .download import ProbeResult, probe

__all__ = [
    "SourceChoice",
    "PIP_SOURCES",
    "NPM_SOURCES",
    "pypi_sdist_url",
    "npm_tarball_url",
    "select_pip_source",
    "select_npm_source",
]


@dataclass
class SourceChoice:
    """一个源的探测结论。"""

    name: str
    url: str
    result: ProbeResult

    @property
    def ok(self) -> bool:
        return self.result.ok


PIP_SOURCES: dict[str, str] = {
    "官方": "https://pypi.org/simple",
    "中科大": "https://mirrors.ustc.edu.cn/pypi/web/simple",
    "阿里云": "https://mirrors.aliyun.com/pypi/simple",
}

NPM_SOURCES: dict[str, str] = {
    "官方": "https://registry.npmjs.org",
    "淘宝": "https://registry.npmmirror.com",
}


def _get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ipip-installer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def pypi_sdist_url(simple_index: str, package: str, timeout: float = 15.0) -> tuple[str | None, str]:
    """从 simple index 取一个真实可下载的分发包 URL。

    返回 ``(url, reason)``。**不吞掉失败原因** —— 曾经这里 ``except: return None``，
    结果三个源全解析失败时只看到"全都 0 kB/s"，看不出是在解析阶段就断了
    （真机上那次是 TLS 握手被内网代理切断）。失败原因必须能传到日志里。
    """
    url = simple_index.rstrip("/") + "/" + package + "/"
    req = urllib.request.Request(url, headers={"User-Agent": "ipip-installer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, f"索引不可达: {type(e).__name__}: {str(e)[:70]}"

    links = re.findall(r'href="([^"]+)"', html)
    prefer = [u for u in links if ".whl" in u] or [u for u in links if ".tar.gz" in u]
    if not prefer:
        return None, f"索引里没有可下载的分发包（共 {len(links)} 条链接）"
    chosen = sorted(prefer)[-1]          # 取字典序靠后（通常版本号更高）
    target = chosen.split("#", 1)[0]
    return urljoin(url, target), ""


def npm_tarball_url(registry: str, package: str, timeout: float = 15.0) -> tuple[str | None, str]:
    """取某个 npm 包最新版的 tarball 地址，返回 ``(url, reason)``。"""
    try:
        data = _get_json(registry.rstrip("/") + "/" + package + "/latest", timeout)
    except Exception as e:
        return None, f"registry 不可达: {type(e).__name__}: {str(e)[:70]}"
    tarball = data.get("dist", {}).get("tarball")
    return (tarball, "") if tarball else (None, "latest 元数据里没有 dist.tarball")


def _pick(
    sources: dict[str, str],
    resolve_fn,
    *,
    sample_bytes: int,
    timeout: float,
    bias_domestic: float,
) -> tuple[str | None, list[SourceChoice]]:
    """通用的「取样本 → 测吞吐 → 择优」。

    :param bias_domestic: 国内镜像需要**超过官方这么多倍**才当选。
        打平或略快时仍选官方 —— 这是一个有意的偏置：国内镜像在 CI/CD 里通常
        还需要回源同步，偶发抖动概率更高，而观察到的慢网络下差距往往不是一点半点。
    """
    report: list[SourceChoice] = []
    best_name: str | None = None
    best_kbps = 0

    official_name = "官方"
    official_kbps = 0

    for name, url in sources.items():
        sample, why = resolve_fn(url)
        if not sample:
            report.append(SourceChoice(name, url, ProbeResult(url, False, reason=why)))
            continue
        result = probe(sample, sample_bytes=sample_bytes, timeout=timeout,
                       min_meaningful=1024)
        report.append(SourceChoice(name, url, result))
        kbps = result.kbps
        if name == official_name:
            official_kbps = kbps
        if result.ok and kbps > best_kbps:
            best_kbps = kbps
            best_name = name

    if best_name is None:
        return None, report

    if official_kbps > 0 and best_name != official_name:
        if official_kbps >= best_kbps * bias_domestic:
            return official_name, report
    return best_name, report


def select_pip_source(
    *,
    package: str = "numpy",
    sample_bytes: int = 8 * 1024 * 1024,
    timeout: float = 25.0,
) -> tuple[str, list[SourceChoice]]:
    """选 pip 源，永远有兜底（官方）。返回 ``(源的 URL, 全部报告)``。"""
    name, report = _pick(
        PIP_SOURCES,
        lambda u: pypi_sdist_url(u, package),
        sample_bytes=sample_bytes,
        timeout=timeout,
        bias_domestic=1.3,
    )
    if name and any(c.name == name and c.ok for c in report):
        return PIP_SOURCES[name], report
    return PIP_SOURCES["官方"], report


def select_npm_source(
    *,
    package: str = "debug",
    sample_bytes: int = 4 * 1024 * 1024,
    timeout: float = 20.0,
) -> tuple[str, list[SourceChoice]]:
    """选 npm registry。永远有兜底（官方），不会返回 None。"""
    name, report = _pick(
        NPM_SOURCES,
        lambda u: npm_tarball_url(u, package),
        sample_bytes=sample_bytes,
        timeout=timeout,
        bias_domestic=1.5,
    )
    if name is None:
        return NPM_SOURCES["官方"], report
    return NPM_SOURCES[name], report
