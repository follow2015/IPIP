# -*- coding: utf-8 -*-
"""设备巡查 Prompt 模板：结论生成 + 风险路由判断。"""
from app.services.ai.prompts.registry import register_prompt

register_prompt(
    name="device_inspect_conclusion",
    system=(
        "你是资深网络运维工程师。根据设备信息与监控数据，给出巡查结论："
        "①整体健康度；②风险点（≤3条）；③建议处置动作（≤2条）。控制在120字内。"
    ),
    user_tpl="设备信息：{device_info}\n监控数据：{monitor_data}",
)

register_prompt(
    name="device_inspect_route",
    system="根据巡查结论判断是否需要创建工单。只回复 normal 或 risk，不要多余文字。",
    user_tpl="巡查结论：{conclusion}",
    allowed_outputs=["normal", "risk"],
)
