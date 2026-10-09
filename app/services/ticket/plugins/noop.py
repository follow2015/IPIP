# -*- coding: utf-8 -*-
"""示例插件 ``noop`` —— **照抄模板**，不是给人用的业务插件。

它的三个用途：

1. 新增平台时照着它改（这是它存在的**唯一**业务理由）；
2. 契约测试的样本：没有它，契约测试就"扫不到任何插件"，而"零命中"和"扫描器坏了"
   在输出上完全一样 —— 用一个真实存在的插件把门禁从"永不红"变成"会红"；
3. 演示三个能力各自的写法（建单 / 状态双向映射 / 不支持时返回什么）。

刻意**不是**"空适配器"：上传的 ITSM 参考文档建议"企微/飞书/钉钉各写一个空壳预留结构"，
那类空壳是负债不是资产 —— 它让"接了"看起来成立，一跑就 ``NotImplementedError``，
且没人维护。要预留的是**插座**（已由 ``plugin_base`` 提供），不是一堆假插件。
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.core.enums import QualityLevel
from app.services.ticket.kernel_status import TICKET_STATUSES, TicketStatus
from app.services.ticket.plugin_base import TicketPlugin
from app.services.ticket.plugin_capability import TicketCapability, implements

_KERNEL_TO_EXTERNAL: dict[str, str] = {s.value: s.value for s in TicketStatus}
_EXTERNAL_TO_KERNEL: dict[str, str] = {v: k for k, v in _KERNEL_TO_EXTERNAL.items()}


class NoopPlugin(TicketPlugin):
    """什么都不对接的插件：入站原样透传（按 READS 裁剪），出站做恒等形态的映射。"""

    code: ClassVar[str] = "noop"
    READS: ClassVar[frozenset[str]] = frozenset({"title", "content"})
    KERNEL_STATES: ClassVar[frozenset[str]] = TICKET_STATUSES

    def is_available(self) -> bool:
        """示例插件默认不可用：它不对接任何真实平台，装配进列表也不该真的被调用。"""
        return False

    @implements(TicketCapability.INBOUND_CREATE, QualityLevel.FULL)
    def to_kernel(self, payload: dict[str, Any]) -> dict[str, Any]:
        """把裁剪后的 payload 原样返回。

        真实插件在这里做**字段改名与补全**（如把企微的 ``event.title`` 映射成 ``title``、
        补默认值、把外部优先级映射成内核优先级）。这里什么都不做，是因为示例不该
        编造业务规则 —— 抄的人要自己填。
        """
        return dict(payload)

    @implements(TicketCapability.INBOUND_STATUS, QualityLevel.PARTIAL)
    def map_in(self, external_status: str) -> str | None:
        """外部状态 -> 内核状态；识别不了返回 ``None``（**不猜**，由模板转成 unmapped）。"""
        return _EXTERNAL_TO_KERNEL.get(external_status)

    @implements(TicketCapability.OUTBOUND_STATUS, QualityLevel.PARTIAL)
    def map_out(self, kernel_status: str) -> str:
        """内核状态 -> 外部状态。

        这里**故意不兜底**：未知的内核状态照原样返回。真实插件若要严格，应在此处抛错
        或返回插件自己的"未知"态 —— 但绝不能静默映射成一个看起来正常的状态，
        那会让外部侧显示"已完成"而内核其实还在处理中。
        """
        return _KERNEL_TO_EXTERNAL.get(kernel_status, kernel_status)


__all__ = ["NoopPlugin"]
