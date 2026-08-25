# -*- coding: utf-8 -*-
"""
API 请求验证工具

提取路由中重复的参数解析和校验逻辑。
"""
import ipaddress


from app.api.base import APIResponse, ErrorCode


def parse_ip_room(data: dict) -> tuple:
    """解析并校验 ip_address + room_id 参数。

    Args:
        data: 请求体字典

    Returns:
        tuple: (ip_address, room_id) 或错误响应元组。
               调用方需用 isinstance 检查第一个元素是否为 Response。
    """
    ip_address = data.get("ip_address")
    room_id = data.get("room_id")

    if not ip_address or room_id is None:
        return APIResponse.error(
            "缺少 ip_address 或 room_id",
            ErrorCode.VALIDATION_ERROR, 400,
        )

    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return APIResponse.error(
            f"无效的 IP 地址格式: {ip_address}",
            ErrorCode.VALIDATION_ERROR, 400,
        )

    return ip_address, room_id
