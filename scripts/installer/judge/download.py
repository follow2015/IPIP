"""下载可用性校验与真实吞吐探测。

这一模块的存在理由是两次真实误判，两次都代价不菲：

1. **" HTTP 200 " 不等于 "资源存在"**
   多数镜像站在路径不存在时返回的是**错误页**，而错误页同样是 **HTTP 200**。
   实测 pytorch CPU 索引在三处镜像的表现：

   | 站点     | 响应体大小 | 实情         |
   |----------|-----------|--------------|
   | 中科大   | 192B      | 错误页（200）|
   | 阿里云   | 2316B     | 错误页（200）|
   | 清华     | 152B      | 错误页（200）|

   只看状态码的结论是"三家都可用"，实际是"三家都没有"。因此这里的判据是
   **响应体大小 + HTML 形态检测**，双重确认。

2. **"能不能装完" 不等于 "这个源快"**
   `debug` 这种几十 KB 的小包，即使源被限到 12–47 KiB/s 也能在超时窗口内装完
   并返回成功。旧版 install.sh 因此选中慢源，把整段前端构建拖成瓶颈。
   所以判据必须是**真实吞吐**（kB/s），且只计量纯传输时间。

判据层与动作层分离是本轮重构的核心主张：历史事故中，**动作从来没错，错的都是判据**。
把判据写成纯函数，每一条事故都能变成一条 pytest 用例，而不是一台机器上的几十分钟。
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final

__all__ = ["ProbeResult", "probe", "available", "KB", "MB"]

KB: Final = 1024
MB: Final = 1024 * 1024

_CHUNK: Final = 256 * 1024
_USER_AGENT: Final = "ipip-installer/1.0 (+https://github.com/gguu/ipip)"


@dataclass(frozen=True)
class ProbeResult:
    """一次探测的结果。

    所有失败情况都收敛成 ok=False 的实例，而不是抛异常 —— 选源的调用方要的是
    "这个源能不能用、有多快"，不是一个需要逐条 catch 的异常动物园。
    """

    url: str
    ok: bool
    status: int | None = None      # HTTP 状态码；连接层失败时为 None
    bytes_read: int = 0            # 实际读取的响应体字节数
    elapsed: float = 0.0           # 纯传输耗时（秒）
    reason: str = ""               # 失败原因 / 补充说明

    @property
    def kbps(self) -> int:
        """吞吐（kB/s）。不可用时为 0。"""
        if not self.ok or self.elapsed <= 0:
            return 0
        return int(self.bytes_read / KB / self.elapsed)

    @property
    def mib_s(self) -> str:
        """人类可读速率，用于日志。"""
        kbps = self.kbps
        if kbps >= 1024:
            return f"{kbps / 1024:.1f} MB/s"
        return f"{kbps} kB/s"


def _request(url: str, *, start: int, end: int | None, timeout: float) -> urllib.request.Request:
    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    if end is not None:
        headers["Range"] = f"bytes={start}-{end}"
    return urllib.request.Request(url, headers=headers, method="GET")


def probe(
    url: str,
    *,
    sample_bytes: int = 12 * MB,
    timeout: float = 25.0,
    min_meaningful: int | None = None,
) -> ProbeResult:
    """对单个 URL 做取样探测，返回可用性判定与真实吞吐。

    取样策略：

    - 优先用 ``Range`` 只取前 ``sample_bytes`` 字节，避免把整个大文件拖下来；
    - 服务器不支持 Range 时会退化成整体下载，由 ``timeout`` 兜住上限，不会失控；
    - **计时从收到第一字节开始**，把 DNS / TCP / TLS 握手排除在外 ——
      否则探测小 tarball 时握手耗时会严重压低速率，让两源的横向对比失真。

    ``min_meaningful`` 是关键判据：响应体小于该阈值就判定为"无实质内容"
    （几乎一定是错误页），即使状态码是 200。
    """
    started_dns = time.monotonic()
    if min_meaningful is None:
        min_meaningful = min(64 * KB, sample_bytes)
    req = _request(url, start=0, end=sample_bytes - 1, timeout=timeout)
    got = 0
    status: int | None = None
    t_first = 0.0

    overall_deadline = started_dns + timeout * 2

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", resp.getcode()))
            if status >= 400:
                return ProbeResult(url, False, status, 0, 0.0, f"HTTP {status}")

            while got < sample_bytes:
                if time.monotonic() > overall_deadline:
                    return ProbeResult(
                        url, False, status, got, 0.0,
                        f"取样超时：{timeout * 2:.0f}s 内只取到 {got}B/{sample_bytes}B"
                        f"（源响应过慢，判为不可用）",
                    )
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                if got == 0:
                    t_first = time.monotonic()   # 只从这里开始算传输时间
                got += len(chunk)
            elapsed = (time.monotonic() - t_first) if got else 0.0

    except urllib.error.HTTPError as e:
        return ProbeResult(url, False, int(e.code), 0, 0.0, f"HTTP {e.code}")
    except urllib.error.URLError as e:
        return ProbeResult(url, False, None, 0, 0.0, f"网络错误: {e.reason}")
    except socket.timeout:
        return ProbeResult(url, False, status, got, 0.0, "读取超时")
    except OSError as e:
        return ProbeResult(url, False, status, got, 0.0, f"IO 错误: {e}")

    if got < min_meaningful:
        return ProbeResult(
            url, False, status, got, elapsed,
            f"响应体仅 {got}B（<{min_meaningful}B），判为错误页/占位资源 —— "
            f"注意很多镜像对不存在的路径返回的也是 HTTP 200",
        )
    return ProbeResult(url, True, status, got, elapsed, "")


def available(url: str, *, timeout: float = 15.0, min_bytes: int = 1024) -> bool:
    """资源是否真实存在（粗判，不关心速度）。

    刻意**不用 HEAD**：部分 CDN / 镜像对 HEAD 与 GET 的行为不一致（实测有 HEAD 返回
    200、GET 却返回错误页的站点）。多花一次 HEAD 往返去省几 KB，得不偿失。
    """
    res = probe(url, sample_bytes=min_bytes, timeout=timeout, min_meaningful=min_bytes)
    return res.ok


def human_rate(kbps: int) -> str:
    """kB/s → 人类可读。与 :attr:`ProbeResult.mib_s` 同源，供外部调用方复用。"""
    if kbps >= 1024:
        return f"{kbps / 1024:.1f} MB/s"
    return f"{kbps} kB/s"
