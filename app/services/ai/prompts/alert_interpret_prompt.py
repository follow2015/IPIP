# -*- coding: utf-8 -*-
"""告警解读 Prompt 模板。"""
from app.services.ai.prompt_guard import sanitize_user_input

SYSTEM = (
    "你是一名资深网络运维助手。请将下面结构化告警转换为一段中文口语化解读，"
    "包含：①发生现象；②可能原因；③建议处置步骤（≤3条）。控制在150字内，使用专业但易懂的措辞。"
)

USER_TPL = (
    "告警类型：{alert_type}\n设备：{device_name}\n指标：{metric}\n"
    "当前值：{value}{unit}\n严重级别：{severity}\n"
)


def build_user_prompt(alert: dict) -> str:
    """构造用户 prompt，所有用户可控输入经 sanitize_user_input 过滤注入。"""
    return USER_TPL.format(
        alert_type=sanitize_user_input(str(alert.get("alert_type", "unknown"))),
        device_name=sanitize_user_input(str(alert.get("device_name", "未知设备"))),
        metric=sanitize_user_input(str(alert.get("metric", "-"))),
        value=sanitize_user_input(str(alert.get("value", "-"))),
        unit=sanitize_user_input(str(alert.get("unit", ""))),
        severity=sanitize_user_input(str(alert.get("severity", "unknown"))),
    )


from app.services.ai.prompts.registry import register_prompt  # noqa: E402

register_prompt(
    name="alert_interpret",
    system=SYSTEM,
    user_tpl=USER_TPL,
)
