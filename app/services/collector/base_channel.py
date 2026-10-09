# -*- coding: utf-8 -*-
"""多通道采集 · 通道抽象层 ``BaseChannel``（T0.4）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` §3.4（精确定义）、决策 3（F6 + F10）。

要根治的缺陷（旧实现实测，不是推测）::

    class SnmpChannel(BaseChannel):
        capabilities = {CollectCapability.OPTICS: QualityLevel.PARTIAL}   # 谎称支持

        def _collect_optics(self, device_id, timeout=None):
            raise NotImplementedError                                     # 恒抛


两处失配**叠加**才致命：矩阵谎称 PARTIAL ⇒ Selector 每轮都选中它；``continue``
又把配对错误吞掉 ⇒ 既不报错也不补采。故障于是以"功能一直不可用"而非"报错"的
形态存在，发现时间是"永远发现不了"。

因此本层只有三件事，且治理点全部前移到**导入期**（总监裁决 3）：

1. ``capabilities`` 不是手写字典，而是 ``@implements`` 标注的实现方法**推导**出来的
   （``__init_subclass__`` 里写回类对象）—— 声明与实现不可能不一致，因为不一致的类
   根本构造不出来。
2. ``collect()`` 是**模板方法**（非抽象）：outcome 判定 / 预算 / 异常记录这些统一
   语义必须只有一份实现。子类各写一份就等于换地方复现 F10 的静默吞异常。
3. 派生 meta 三键仍然只由 ``CollectedFacts.refresh_meta()`` 写；本层只负责在返回前
   把 ``self.capabilities`` 作为质量矩阵喂给它。

依赖边界（ADR-004）：本模块**零**监控侧 import；deadline 用标准库自持
（``concurrent.futures``），理由见 ``docs/decisions/OPEN-DECISIONS.md`` OD-3。
"""
from __future__ import annotations

import inspect
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterable

from flask import current_app, has_app_context

from app.core.enums import CollectCapability, QualityLevel
from app.services.collector.capability import (
    DERIVED_CAPABILITIES_FLAG,
    HANDLERS_ATTR,
    ChannelContractError,
    as_capability,
    assert_handler_signature,
    assert_no_manual_capabilities,
    cap_value,
    collect_declarations,
    field_of,
    implements,
)
from app.services.collector.contract import (
    META_KEY_BUDGET_EXHAUSTED,
    META_KEY_CHANNEL,
    META_KEY_CHANNELS,
    META_KEY_COLLECTED_AT,
    META_KEY_ELAPSED_MS,
    META_KEY_ERRORS,
    META_KEY_FAILED,
    META_KEY_QUALITY,
    META_KEY_REQUESTED,
    META_KEY_SATISFIED,
    META_KEY_UNSUPPORTED,
    CapabilityOutcome,
    is_empty_value,
)
from app.services.collector.facts import CollectedFacts
from app.services.collector.metrics import COLLECTOR_METRICS
from app.utils.logging import get_logger

logger = get_logger(__name__)

ERROR_CODE_TIMEOUT = "timeout"
ERROR_CODE_BUDGET_EXHAUSTED = "budget_exhausted"

DEFAULT_BUDGET_SECONDS = 600.0


class BaseChannel(ABC):
    """所有采集通道的抽象基类。

    ``capabilities`` 是**派生属性**：由 ``@implements`` 标注的实现方法在类定义期推导
    并写回类对象（见 ``__init_subclass__``）。矩阵取值域因此只有 ``FULL`` / ``PARTIAL``
    —— ``NONE`` 由"不实现"表达。``collect()`` 对"矩阵缺失或为 NONE"一律产出
    ``UNSUPPORTED``，这正是 AC-9（防火墙 MAC 不算失败）在运行期的落地形态。
    """

    code: ClassVar[str] = ""                                    # "cli" / "snmp"
    capabilities: ClassVar[dict[CollectCapability, QualityLevel]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        if not cls.code:
            raise ChannelContractError(f"{cls.__name__} 未声明 code")

        assert_no_manual_capabilities(cls, exempt=(BaseChannel,))
        declared = collect_declarations(cls)
        setattr(cls, DERIVED_CAPABILITIES_FLAG, True)
        cls.capabilities = {cap: quality for cap, (quality, _name) in declared.items()}
        setattr(cls, HANDLERS_ATTR, {cap: name for cap, (_quality, name) in declared.items()})
        for cap, (_quality, name) in declared.items():
            assert_handler_signature(cls.__name__, cap, getattr(cls, name))

    @abstractmethod
    def is_available(self, device_id: int) -> bool:
        """该通道对此设备是否可用（凭据齐备 + 开关打开 + 未被熔断）。"""

    @abstractmethod
    def health_probe(self, device_id: int) -> bool:
        """轻量健康检查（供 ChannelSelector 熔断判定）。"""

    def collect(
        self,
        device_id: int,
        capabilities: Iterable[CollectCapability | str],
        timeout: int | None = None,
    ) -> CollectedFacts:
        """按能力逐项采集，单项失败只降级该 capability，不抛异常。

        单项四态语义：成功且非空 -> ``SATISFIED``；成功但确实为空 -> ``EMPTY``；
        未实现 / 矩阵 NONE -> ``UNSUPPORTED``；抛异常或超预算 -> ``FAILED``。前三者都是
        **确定答案**（不再补采），只有 FAILED 进 ``meta["errors"]`` 并触发补采。

        ``meta["channels"][cap] = self.code`` 随每个确有能力产出（见 ``_collect_one``）：
        这是混合采集里 per-capability 溯源的唯一写入点（B1 / AC-30）。
        """
        requested = sorted({as_capability(c) for c in capabilities}, key=cap_value)
        for cap in requested:
            field_of(cap)

        app_obj = current_app._get_current_object() if has_app_context() else None

        facts = CollectedFacts()
        started = time.monotonic()
        budget = float(timeout) if timeout is not None else DEFAULT_BUDGET_SECONDS
        deadline = started + budget

        facts.meta[META_KEY_CHANNEL] = self.code
        facts.meta[META_KEY_REQUESTED] = [cap_value(c) for c in requested]
        facts.meta[META_KEY_COLLECTED_AT] = datetime.now(timezone.utc).isoformat()
        facts.meta[META_KEY_ERRORS] = {}
        facts.meta[META_KEY_CHANNELS] = {}
        facts.meta[META_KEY_BUDGET_EXHAUSTED] = False

        handlers: dict[CollectCapability, str] = getattr(self, HANDLERS_ATTR, {})

        self._begin_collect(device_id)
        try:
            executor = ThreadPoolExecutor(
                max_workers=max(1, len(requested)),
                thread_name_prefix=f"collect-{self.code}",
            )
            try:
                for cap in requested:
                    self._collect_one(
                        facts, executor, handlers, cap, device_id, deadline, app_obj
                    )
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        finally:
            facts.meta[META_KEY_ELAPSED_MS] = round((time.monotonic() - started) * 1000)
            self._end_collect(device_id)

        facts.refresh_meta(self.capabilities)
        self._report(facts, device_id)
        return facts

    def _report(self, facts: CollectedFacts, device_id: int) -> None:
        """批次收尾的统一观测点：§10.3 结构化日志 + V2 指标累加。

        指标故障**不得**反噬采集（metrics 模块纪律）：这里整体套 try/except，
        观测挂了最多丢一条日志/计数，绝不改变 collect() 的返回。
        """
        try:
            meta = facts.meta
            quality = meta.get(META_KEY_QUALITY) or {}
            elapsed = meta.get(META_KEY_ELAPSED_MS) or 0
            logger.info(
                "channel=%s device_id=%s requested=%s satisfied=%s empty=%s "
                "failed=%s unsupported=%s elapsed_ms=%s",
                self.code, device_id,
                meta.get(META_KEY_REQUESTED), meta.get(META_KEY_SATISFIED),
                [k for k, v in facts.outcomes.items() if v is CapabilityOutcome.EMPTY],
                meta.get(META_KEY_FAILED), meta.get(META_KEY_UNSUPPORTED),
                elapsed,
            )
            COLLECTOR_METRICS.record_channel_collect(
                channel=self.code,
                delegated=len(meta.get(META_KEY_CHANNELS) or {}),
                outcomes={k: (v.value if hasattr(v, "value") else str(v))
                          for k, v in facts.outcomes.items()},
                quality=dict(quality),
                elapsed_ms=int(elapsed),
            )
            if meta.get(META_KEY_BUDGET_EXHAUSTED):
                COLLECTOR_METRICS.record_budget_exhausted(self.code)
        except Exception:  # 观测失败只留痕，不上抛
            logger.warning("采集指标记录失败（忽略）channel=%s device_id=%s",
                           self.code, device_id, exc_info=True)

    def _begin_collect(self, device_id: int) -> None:  # noqa: B027 -- 有意默认 no-op 而非抽象方法（见 docstring）：逼不需要批次概念的通道实现只会加样板
        """单次采集开始。需要批次级资源的通道（如 walk 结果复用）覆写它。

        刻意做成**空实现**而不是抽象方法：绝大多数通道不需要批次概念，逼它们
        实现一遍只会让新通道的样板代码变多。
        """

    def _end_collect(self, device_id: int) -> None:  # noqa: B027 -- 同上：默认 no-op 钩子
        """单次采集结束（成功 / 超时 / 异常均会调用）。默认 no-op。"""

    def _collect_one(
        self,
        facts: CollectedFacts,
        executor: ThreadPoolExecutor,
        handlers: dict[CollectCapability, str],
        cap: CollectCapability,
        device_id: int,
        deadline: float | None,
        app_obj: Any | None,
    ) -> None:
        """采集单项能力，把结果四态写进 ``facts.outcomes``。"""
        key = cap_value(cap)
        handler_name = handlers.get(cap)
        quality = type(self).capabilities.get(cap)
        if handler_name is None or quality is None or quality is QualityLevel.NONE:
            facts.outcomes[key] = CapabilityOutcome.UNSUPPORTED
            return

        facts.meta.setdefault(META_KEY_CHANNELS, {})[key] = self.code

        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            facts.outcomes[key] = CapabilityOutcome.FAILED
            facts.meta[META_KEY_BUDGET_EXHAUSTED] = True
            self._record_error(
                facts, key, ERROR_CODE_BUDGET_EXHAUSTED,
                f"整设备时间预算已耗尽，{cap.value} 未开始采集",
            )
            return

        future = executor.submit(
            self._run_in_app_context,
            app_obj,
            getattr(self, handler_name),
            device_id,
            remaining,
        )
        code: str | None = None
        try:
            error = future.exception(timeout=remaining)
        except TimeoutError:
            error = TimeoutError(f"{cap.value} 采集超过剩余预算 {remaining:.3f}s")
            code = ERROR_CODE_TIMEOUT
            future.cancel()

        if error is not None:
            logger.error(
                "通道 %s 采集能力 %s 失败（device_id=%s）",
                self.code, cap.value, device_id, exc_info=error,
            )
            facts.outcomes[key] = CapabilityOutcome.FAILED
            self._record_error(
                facts, key, code or type(error).__name__, str(error) or type(error).__name__,
            )
            return

        value: Any = future.result()
        setattr(facts, field_of(cap), value)
        facts.outcomes[key] = (
            CapabilityOutcome.EMPTY if is_empty_value(value) else CapabilityOutcome.SATISFIED
        )

    @staticmethod
    def _run_in_app_context(app_obj: Any, handler: Any, device_id: int, timeout: Any):
        """worker 线程入口：在需要的线程里重建 app context（T0.9）。

        - 调用线程有 app context → worker push **全新** context（理由见 collect()）；
        - 调用线程没有 → worker 也**不凭空造**：handler 内部对 context 的依赖
          （如凭据 provider）必须自己明确报错 —— 无中生有地包一层空 context 会
          把『取不到 DB』伪装成『配置了空库』，复活 F1 的静默失效形态。
        """
        if app_obj is None:
            return handler(device_id, timeout=timeout)
        with app_obj.app_context():
            return handler(device_id, timeout=timeout)

    @staticmethod
    def _record_error(facts: CollectedFacts, key: str, code: str, message: str) -> None:
        """``meta["errors"][cap]`` 的唯一写入点（形状 ``{"code", "message"}``）。"""
        facts.meta.setdefault(META_KEY_ERRORS, {})[key] = {"code": code, "message": message}


__all__ = [
    "ERROR_CODE_BUDGET_EXHAUSTED",
    "ERROR_CODE_TIMEOUT",
    "BaseChannel",
    "ChannelContractError",
    "implements",
]
