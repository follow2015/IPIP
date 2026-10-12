"""安装器侧的 HTTP 出口 —— **唯一**允许构造 / 打开 URL 的地方。

为什么要有这一层
----------------
``urllib.request.urlopen`` 与 ``Request`` 默认接受**任意** scheme，包含
``file://`` 和自定义 scheme（``S310`` 的实质关切）。安装器里的 URL 全部来自
模块级常量表（``PIP_SOURCES`` / 镜像池 / 候选源），按理不该出现 ``file://``；
但"按理"挡不住一次手误或一次常量改动把本地路径当 URL 传进来 —— 那时
``urlopen`` 会**成功**并静默读走本机文件，而后续报错（校验和不对 / 解析失败）
**指不到这一行**，排查方向会整个跑偏（本仓 installer 的历史事故几乎都是
"报错点离真因很远"这一种）。

所以这里把 scheme 收成 ``http`` / ``https`` 白名单，非白名单直接抛
``ValueError``。

为什么是"集中校验"而不是"10 处各写一条 noqa"
--------------------------------------------
``S310`` 曾在本仓有 10 条存量，散落在 ``act/`` 与 ``judge/`` 下。逐条加
``# noqa: S310`` 同样能清零，但代价是门禁在这 10 行上**永久失明**，且理由要
重复写 10 遍（分散的 noqa 没人会逐条复查理由）。收敛到这里之后只剩 2 条
noqa，理由只需读一次，而真正生效的拦截是白名单本身 —— 它有牙：传
``file:///etc/passwd`` 会当场抛错。

[WARN] 这不是安全边界。它拦的是"把本地路径当 URL 用"这类手误，**不防
SSRF** —— 源表由安装器自带、不接外部输入，若将来出现外部可控的 URL，需要
的是出网目标白名单，不是这里这一层。
"""

from __future__ import annotations

import urllib.request
from typing import Any, Final
from urllib.parse import urlsplit

__all__ = ["build_request", "open_request", "open_url", "ALLOWED_SCHEMES"]

ALLOWED_SCHEMES: Final = ("http", "https")


def _check_scheme(url: str) -> None:
    """非 http/https 直接抛错 —— 宁可中止安装，也不要静默读本地文件。"""
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"安装器只允许 {ALLOWED_SCHEMES} 的 URL，收到 scheme={scheme!r}：{url!r}"
        )


def build_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
) -> urllib.request.Request:
    """构造 :class:`urllib.request.Request`（带 scheme 白名单校验）。"""
    _check_scheme(url)
    return urllib.request.Request(url, headers=headers or {}, method=method)  # noqa: S310 —— scheme 已由白名单收紧


def open_request(
    req: urllib.request.Request,
    *,
    timeout: float,
) -> Any:
    """打开一个 :class:`Request`（带 scheme 白名单校验）。

    返回可上下文管理的响应对象（``with ... as resp``）。

    需要自定义请求头（Range / UA）时先用 :func:`build_request` 构造再交给这里。
    """
    _check_scheme(str(req.full_url))
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 —— scheme 已由白名单收紧


def open_url(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    method: str = "GET",
) -> Any:
    """一步到位：构造 + 打开。无自定义头需求时用这个。"""
    return open_request(build_request(url, headers=headers, method=method), timeout=timeout)
