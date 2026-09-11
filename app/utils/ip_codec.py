# -*- coding: utf-8 -*-
"""
IP 地址编解码 —— 全仓唯一的 IPv4 整数换算实现（P1-3 工具收敛）

收敛背景：`socket.inet_aton`/`ip_to_int` 原先散落在 ip_model、switch_credentials、
switch_route、ip_route_service 四处（≈20 个调用点），IPv6 纳管时无处统一改造，
故收口到本模块；旧导入名全部保留为**瘦封装/再导出**，调用方零改动。

双栈接口约定（IPv6 纳管评估见 docs/IPv6改造-数据模型评估.md）：
- ``ip_to_int`` 仅 IPv4（32 位整数，等价 MySQL INET_ATON）。IPv6 输入返回 None
  —— 现有 INTEGER(unsigned) 列装不下 128 位，这是**列类型约束**而非接口缺陷；
  纳管后应改走 ``ip_to_bytes``/``bytes_to_ip``（4/16 字节，VARBINARY(16) 友好）。
- 保留 ``inet_aton`` 的**宽松解析**语义（如 "127.1" → 127.0.0.1、八进制段），
  与 MySQL INET_ATON 及既有落库数据保持一致；换用 ipaddress 严格解析会改变
  行为，必须随纳管迁移一并评估。
"""
import socket
import struct

import ipaddress

__all__ = ["ip_to_int", "int_to_ip", "ip_to_bytes", "bytes_to_ip"]


def ip_to_int(ip_address: str) -> int | None:
    """IPv4 地址 → 无符号 32 位整数（等价 MySQL INET_ATON）。

    Args:
        ip_address: IPv4 地址字符串（保持 inet_aton 宽松解析语义）。

    Returns:
        int: 整数表示；无效地址（含 IPv6）返回 None。

    Note:
        非 str 入参（None 等）会抛 TypeError —— 与既有各实现行为一致，
        由调用方负责判空（现状亦如此）。
    """
    try:
        return struct.unpack("!I", socket.inet_aton(ip_address))[0]
    except (OSError, struct.error):
        return None


def int_to_ip(value: int) -> str | None:
    """无符号 32 位整数 → IPv4 点分十进制（等价 MySQL INET_NTOA）。

    超出 32 位范围或非整数返回 None。
    """
    if not isinstance(value, int) or isinstance(value, bool) or not (0 <= value <= 0xFFFFFFFF):
        return None
    return socket.inet_ntoa(struct.pack("!I", value))


def ip_to_bytes(ip_address: str) -> bytes | None:
    """IP 地址 → 网络序字节串（双栈友好）。

    IPv4 → 4 字节；IPv6 → 16 字节（含压缩形式与 IPv4-mapped 展开）。
    无效地址返回 None。供 VARBINARY(16) 列（IPv6 纳管的目标列型）使用。
    """
    try:
        addr = ipaddress.ip_address(str(ip_address).strip())
    except ValueError:
        return None
    return addr.packed


def bytes_to_ip(raw: bytes) -> str | None:
    """网络序字节串 → IP 地址字符串（ip_to_bytes 的逆操作）。

    4 字节按 IPv4 解析；5-15 字节非法返回 None；16 字节按 IPv6 解析。
    """
    if not isinstance(raw, (bytes, bytearray)):
        return None
    raw = bytes(raw)
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None
