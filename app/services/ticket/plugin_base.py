# -*- coding: utf-8 -*-
"""工单插件 · 插座基类 ``TicketPlugin``（同构于 ``collector/base_channel.py``）。

一句话：**插件可以依赖内核，内核绝不依赖插件。** 这条反向依赖一旦开口，工单内核就
会被某个平台的字段形状反向塑形，最终变成"给钉钉写的一套逻辑 + 一堆 if"。

本基类只管三件事：

1. **契约**：``code`` 必须有、能力矩阵必须派生、``READS`` 必须声明（``INBOUND_CREATE``）；
2. **模板方法**：内核永远调模板方法（``build_draft`` / ``to_kernel_status`` / …），
   不直接调插件的 handler —— 过滤器、UNSUPPORTED 语义、结果形态都由模板统一；
3. **不支持 ≠ 错误**：未实现的能力返回 ``ok=False, reason="unsupported"``，不抛异常。
   照采集侧「防火墙 MAC 不算失败」的同款语义：某个平台不支持状态回写，
   不该让整条建单链路炸掉。

刻意**不**做的事：不在基类里读配置 / Redis / 数据库。插件的"能不能用"由
``is_available()`` 回答，而**熔断是编排层的状态**（跨进程、跨插件共用），
塞进基类会让每个插件都依赖 Redis、单测必须起 Redis —— 与采集侧把熔断放在
``selector`` 而不是 ``BaseChannel`` 同一个理由。
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from app.core.enums import QualityLevel
from app.services.ticket.plugin_capability import (
    DERIVED_CAPABILITIES_FLAG,
    HANDLERS_ATTR,
    PluginContractError,
    TicketCapability,
    assert_handler_signature,
    assert_no_manual_capabilities,
    collect_declarations,
)

UNSUPPORTED = "unsupported"
UNKNOWN_KERNEL_STATUS = "unknown_kernel_status"


@dataclass(frozen=True)
class PluginResult:
    """插件调用的统一结果形态。

    ``ok=False`` 时内核必须先看 ``reason``：``unsupported`` 是**能力缺失**（正常，应降级），
    其它值是**真的失败了**（要记日志、要能重试）。把两者混为一谈是工单侧最容易犯的错 ——
    "平台不支持回写"被当成故障告警刷屏，几次之后运维就会把所有插件告警都忽略掉。
    """

    ok: bool
    data: Any = None
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class TicketPlugin(ABC):
    """所有工单插件的抽象基类。

    ``capabilities`` 是**派生属性**：由 ``@implements`` 标注的实现方法在类定义期推导
    并写回类对象。矩阵取值域因此只有 ``FULL`` / ``PARTIAL`` —— ``NONE`` 由"不实现"表达。
    """

    code: ClassVar[str] = ""
    capabilities: ClassVar[dict[TicketCapability, QualityLevel]] = {}
    READS: ClassVar[frozenset[str]] = frozenset()
    KERNEL_STATES: ClassVar[frozenset[str]] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        if not cls.code:
            raise PluginContractError(f"{cls.__name__} 未声明 code")

        assert_no_manual_capabilities(cls, exempt=(TicketPlugin,))
        declared = collect_declarations(cls)
        setattr(cls, DERIVED_CAPABILITIES_FLAG, True)
        cls.capabilities = {cap: quality for cap, (quality, _name) in declared.items()}
        setattr(cls, HANDLERS_ATTR, {cap: name for cap, (_quality, name) in declared.items()})
        for cap, (_quality, name) in declared.items():
            assert_handler_signature(cls.__name__, cap, getattr(cls, name))

        if TicketCapability.INBOUND_CREATE in cls.capabilities and not cls.READS:
            raise PluginContractError(
                f"{cls.__name__} 实现了 INBOUND_CREATE 却未声明 READS —— "
                "必须显式列出从外部 payload 读取的字段名（禁 **kwargs 透传）。"
            )

        if {TicketCapability.INBOUND_STATUS, TicketCapability.OUTBOUND_STATUS} & set(
            cls.capabilities
        ) and not cls.KERNEL_STATES:
            raise PluginContractError(
                f"{cls.__name__} 实现了状态映射却未声明 KERNEL_STATES —— "
                "必须列出本插件认知的内核状态取值域，否则无法校验映射的双向覆盖。"
            )

    @abstractmethod
    def is_available(self) -> bool:
        """该插件当前是否可用（开关打开 + 凭据齐备 + 未被熔断）。

        必须是**纯判断**：不发网络请求、不改状态。真正的网络动作只在能力方法里发生，
        否则"装配时扫一遍可用性"就会变成一次对外部平台的批量探测。
        """

    def _handler(self, cap: TicketCapability):
        name = getattr(type(self), HANDLERS_ATTR, {}).get(cap)
        if name is None:
            return None
        return getattr(self, name)

    @staticmethod
    def _unsupported(cap: TicketCapability) -> PluginResult:
        return PluginResult(ok=False, reason=UNSUPPORTED, meta={"capability": cap.value})

    def resolve_identity(self, external_id: str) -> PluginResult:
        """外部身份 -> 内部 ``user_id``；未识别返回 ``ok=False, data=None``。"""
        handler = self._handler(TicketCapability.IDENTITY)
        if handler is None:
            return self._unsupported(TicketCapability.IDENTITY)
        return PluginResult(ok=True, data=handler(external_id))

    def build_draft(self, payload: Mapping[str, Any]) -> PluginResult:
        """外部 payload -> 内核工单草稿。

        **字段过滤在模板里做，不在插件里做**：先按 ``READS`` 白名单裁掉未声明字段，
        再把裁剪后的 payload 交给插件的 handler。这样"只能读声明过的字段"是机制保证，
        而不是靠每个插件作者自觉 —— U3 落到这里才算钉住。

        被丢弃的键放进 ``meta["dropped_keys"]``：插件想用某个字段却忘了声明时，
        这是唯一能自证"我以为我传了"的线索（否则它只会拿到一个静默变小的 dict）。
        """
        if TicketCapability.INBOUND_CREATE not in type(self).capabilities:
            return self._unsupported(TicketCapability.INBOUND_CREATE)
        handler = self._handler(TicketCapability.INBOUND_CREATE)
        declared = set(self.READS)
        filtered = {k: v for k, v in payload.items() if k in declared}
        dropped = sorted(str(k) for k in payload.keys() if k not in declared)
        return PluginResult(ok=True, data=handler(filtered), meta={"dropped_keys": dropped})

    def to_kernel_status(self, external_status: str) -> PluginResult:
        """外部状态 -> 内核状态；无法映射时返回 ``ok=False``（**不得**猜一个默认值）。"""
        handler = self._handler(TicketCapability.INBOUND_STATUS)
        if handler is None:
            return self._unsupported(TicketCapability.INBOUND_STATUS)
        mapped = handler(external_status)
        if mapped is None:
            return PluginResult(ok=False, reason="unmapped", meta={"external_status": external_status})
        if mapped not in type(self).KERNEL_STATES:
            return PluginResult(
                ok=False,
                reason=UNKNOWN_KERNEL_STATUS,
                meta={"external_status": external_status, "mapped": mapped},
            )
        return PluginResult(ok=True, data=mapped)

    def from_kernel_status(self, kernel_status: str) -> PluginResult:
        """内核状态 -> 外部展示状态。"""
        handler = self._handler(TicketCapability.OUTBOUND_STATUS)
        if handler is None:
            return self._unsupported(TicketCapability.OUTBOUND_STATUS)
        return PluginResult(ok=True, data=handler(kernel_status))

    def pull(self, since: Any = None) -> PluginResult:
        """主动拉取外部工单（双向同步）。"""
        handler = self._handler(TicketCapability.PULL_SYNC)
        if handler is None:
            return self._unsupported(TicketCapability.PULL_SYNC)
        return PluginResult(ok=True, data=handler(since))


__all__ = ["PluginResult", "TicketPlugin", "UNKNOWN_KERNEL_STATUS", "UNSUPPORTED"]
