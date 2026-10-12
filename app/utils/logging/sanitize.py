# -*- coding: utf-8 -*-
"""日志文本清洗 —— 日志注入面收口（评审 2026-10-10）。

用户可控字段（前端日志上报、CSP report 字段等）写入日志前必须过本函数：
换行与控制字符转义为可见形式（``\\n`` → 字面 ``\\n``），防止一条日志被拆成
多条伪造条目（grep / sort / uniq 的聚合口径被污染）；非打印控制字符（如
ANSI 转义序列）一并转义，防终端渲染劫持。

参数化日志（``logger.warning("...%s...", value)``）只防格式串注入，不防
**内容**换行 —— 两层配合使用，缺一不可。
"""
from __future__ import annotations

__all__ = ["sanitize_log_text", "DEFAULT_LOG_FIELD_MAX_LENGTH"]

DEFAULT_LOG_FIELD_MAX_LENGTH = 2000


def sanitize_log_text(
    value: object, max_length: int = DEFAULT_LOG_FIELD_MAX_LENGTH
) -> str:
    """把任意用户可控值单行化并限长，返回可安全写入单条日志的文本。

    非打印字符（含 ``\\r`` ``\\n`` ``\\t`` 与 ANSI ESC）统一转义为
    ``\\xNN`` 形式 —— 转义而不是删除：保留了"这里原本有个分隔"的信息，
    运维排查时看得出原始内容被篡改过。

    Args:
        value: 任意用户可控值（非字符串经 ``str()`` 归一）。
        max_length: 截断上限（字符数）。

    Returns:
        单行、有界长度的文本。
    """
    text = "".join(
        ch if ch.isprintable() else f"\\x{ord(ch):02x}"
        for ch in str(value)
    )
    return text[:max_length]
