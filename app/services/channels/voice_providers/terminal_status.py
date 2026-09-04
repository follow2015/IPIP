# -*- coding: utf-8 -*-
"""语音渠道「终态」唯一权威定义（n10）。

此前终态口径分散硬编码在三处（voice_tasks / voice_callback_routes /
providers.errors），`failed:cancelled` 与 `failed:permanent:*` 易漏同步——
漏一处的表现是「已取消/已终态的呼叫被再次外呼」或「回调终态被中间态覆盖」，
均属用户可感知的缺陷。本模块为唯一定义源，其他位置一律 import 使用。
"""

VOICE_CONCLUDED_STATUSES = frozenset({
    "acked",            # 接听并按键确认
    "answered",         # 接听未按键（已触达）
    "delivered",        # 听完播报
    "no_answer",        # 未接听（人为不接，不得骚扰重试）
    "failed:cancelled", # 呼叫被取消（重试任务已 revoke，但排队中的任务需此判断兜底）
})

VOICE_RESULT_EVENTS: tuple[str, ...] = ("acked", "delivered", "answered", "no_answer")

VOICE_FAILED_PREFIX = "failed:"


def is_call_concluded(status: str | None) -> bool:
    """判断渠道状态是否意味着「呼叫已结束，不得重新外呼」。"""
    return status in VOICE_CONCLUDED_STATUSES


def is_failed_status(status: str | None) -> bool:
    """判断渠道状态是否为失败态（failed:* 前缀）。"""
    return bool(status) and status.startswith(VOICE_FAILED_PREFIX)
