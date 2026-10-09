# -*- coding: utf-8 -*-
"""多通道采集 · 通道选择器 ``ChannelSelector``（T0.4 的后半块）。

``BaseChannel`` 规定了"通道长什么样、单项怎么采"，本模块规定"**由谁、按什么顺序、
在多少时间内**去采"—— 三个职责：

1. **选择**：按优先级挑通道（默认 ``cli,snmp,netconf,restconf,gnmi``，CLI 优先是
   为了 G6「现有行为零变更」，见设计文档 §19.2）；
2. **按能力混合降级（O2=A）**：降级**不是全有全无**。同一台设备上 ``PORTS`` 走 SNMP、
   ``MAC`` 回落 CLI 是允许且被期待的形态 —— 因此选择的最小单位是**能力**而非设备；
3. **整设备 deadline**：预算由选择器统一持有，剩余预算动态分配给后续每一轮，
   耗尽即停止补采（而不是让每个通道各按自己的 timeout 各跑各的）。

刻意**不**做的两件事（都是"看起来该做、做了更糟"）：

- **不在选择路径上发 ``health_probe``**。设计文档把它列为熔断判据输入，但
  ``CliChannel.health_probe`` 的成本是一次完整 SSH 握手 —— 而"选择"会被每个能力
  调用一次。采集结果本身是比探测更诚实的信号：某通道刚把能力采崩了，比它现在
  能否握手更值得作为熔断依据。``probe()`` 单独暴露，供 T-G1 接入点按需调用。
- **不在通道里读 Redis 做熔断**。熔断是"编排层"的状态（跨进程、跨通道共用），
  塞进 ``BaseChannel`` 会让每个通道都依赖 Redis，也让单通道单测必须起 Redis。
  这里由选择器持有，``is_available()`` 保持纯"凭据/开关"语义。

熔断阈值口径：设计文档 §19.2 写默认 5（``SCAN_CHANNEL_CIRCUIT_THRESHOLD``），
而正文另一处出现过 3。本实现取 **5**（开关的默认值）并做成构造参数 —— T0.8 把
开关登记进 ``MonitorDynamicConfig`` 后由它注入，届时口径唯一化。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Iterable, Sequence

from app.core.enums import CollectCapability, QualityLevel
from app.services.collector.base_channel import BaseChannel
from app.services.collector.capability import as_capability, cap_value
from app.services.collector.circuit_breaker import (
    CIRCUIT_KEY_TEMPLATE,
    DEFAULT_CIRCUIT_THRESHOLD,
    DEFAULT_CIRCUIT_TTL,
    CircuitStore,
    MemoryCircuitStore,
    RedisCircuitStore,
)
from app.services.collector.contract import (
    META_KEY_BUDGET_EXHAUSTED,
    META_KEY_CHANNELS,
    META_KEY_COLLECTED_AT,
    META_KEY_DEGRADED_FROM,
    META_KEY_ELAPSED_MS,
    META_KEY_ERRORS,
    META_KEY_REQUESTED,
    CapabilityOutcome,
)
from app.services.collector.facts import CollectedFacts
from app.services.collector.metrics import COLLECTOR_METRICS
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _needs_attempt(facts: CollectedFacts, cap: CollectCapability | str) -> bool:
    """该能力是否还需要再试一次（决定要不要进下一轮补采）。

    三种不重试的情形：已得到确定答案（``SATISFIED`` / ``EMPTY``）、明确不支持
    （``UNSUPPORTED`` —— 换通道也只会再拿一次 UNSUPPORTED，属 AC-9 的确定答案）、
    候选用尽。除此之外（还没采过 / ``FAILED``）都要试。
    """
    outcome = facts.outcomes.get(cap_value(cap))
    if outcome is None:
        return True
    if outcome is CapabilityOutcome.UNSUPPORTED:
        return False
    return not facts.is_satisfied(cap)

DEFAULT_BUDGET_SECONDS = 60.0

ROLE_SKIP_CAPABILITIES: dict[str, frozenset[CollectCapability]] = {
    "firewall": frozenset({CollectCapability.MAC}),
    "l2_switch": frozenset({CollectCapability.ROUTES}),
}


class ChannelSelector:
    """通道选择器：选择 / 按能力混合降级 / 熔断 / 整设备 deadline。"""

    def __init__(
        self,
        channels: Sequence[BaseChannel],
        *,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
        circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
        circuit_store: CircuitStore | None = None,
        circuit_ttl: float | None = None,
        role_resolver: Callable[[int], str | None] | None = None,
    ) -> None:
        if not channels:
            raise ValueError("ChannelSelector 至少需要一个通道")
        codes = [ch.code for ch in channels]
        if len(set(codes)) != len(codes):
            raise ValueError(f"通道 code 重复：{codes}")
        self._channels = list(channels)
        self._budget = float(budget_seconds)
        self._threshold = int(circuit_threshold)
        self._store: CircuitStore = circuit_store or MemoryCircuitStore()
        self._circuit_ttl = (
            float(circuit_ttl) if circuit_ttl is not None
            else float(getattr(self._store, "ttl", 0.0) or DEFAULT_CIRCUIT_TTL)
        )
        self._opened_at: dict[tuple[str, int], float] = {}
        self._half_open_used: set[tuple[str, int]] = set()
        self._role_resolver = role_resolver

    def _role_skips(self, device_id: int) -> frozenset[CollectCapability]:
        """该设备角色下**不适用**的能力集合（解析器缺失或未知角色时为空集）。"""
        if self._role_resolver is None:
            return frozenset()
        try:
            role = self._role_resolver(device_id)
        except Exception as exc:  # noqa: BLE001 —— 角色解析失败不得让采集中断
            logger.warning("角色解析失败 device_id=%s: %s（本轮不做角色过滤）", device_id, exc)
            return frozenset()
        if not role:
            return frozenset()
        return ROLE_SKIP_CAPABILITIES.get(role, frozenset())

    @property
    def channels(self) -> list[BaseChannel]:
        """按优先级排列的通道（CLI 优先）。"""
        return list(self._channels)

    def _usable(self, channel: BaseChannel, device_id: int) -> bool:
        """凭据齐备 + 未被熔断（含半开探测）。

        ``is_available`` 抛出的异常**不吞**：无 app context 之类的错误必须明确
        报错（T0.9 验收口径），把它降级成"该通道不可用"会让真正的问题伪装成
        "没有可用通道"，排查方向整个偏掉。

        熔断恢复语义（评审 I-6）：计数达阈值即**打开**；窗口（``circuit_ttl``）
        内一律跳过；窗口过后**允许恰好一次探测**（半开）——
          · 探测成功 → 计数清零、关闭熔断（真恢复）；
          · 探测失败 → 立刻重新打开（计数回阈值，需要再等一个窗口）。
        原实现是"窗口过期即整量恢复"，等于恢复与首次进入无从区分；
        ``circuit_ttl`` 也必须与 store 的窗口同源，否则半开永远等不到。
        """
        if not channel.is_available(device_id):
            return False
        if self._threshold <= 0:
            return True

        key = (channel.code, device_id)
        fails = self._store.failures(channel.code, device_id)
        if fails < self._threshold:
            self._opened_at.pop(key, None)
            self._half_open_used.discard(key)
            return True

        now = time.monotonic()
        opened = self._opened_at.setdefault(key, now)
        if now - opened < self._circuit_ttl:
            logger.info(
                "通道 %s 对 device_id=%s 已熔断（%d 次失败，窗口剩余 %.0fs），本轮跳过",
                channel.code, device_id, fails, self._circuit_ttl - (now - opened),
            )
            return False
        if key in self._half_open_used:
            return False
        self._half_open_used.add(key)
        logger.info(
            "通道 %s 对 device_id=%s 进入半开：放行一次探测（device_id 可自证恢复）",
            channel.code, device_id,
        )
        return True

    def select_channel(
        self,
        device_id: int,
        required_capabilities: Iterable[CollectCapability | str],
    ) -> BaseChannel | None:
        """设备级入口：挑一个能覆盖**全部**所需能力的首选通道。

        返回值给"整设备走单一通道"的调用方（G6 灰度回退到纯 CLI 时用得上）；
        正常路径请用 :meth:`collect` —— 它按能力分派，允许混合。
        """
        required = [as_capability(c) for c in required_capabilities]
        skips = self._role_skips(device_id)
        required = [cap for cap in required if cap not in skips]
        for channel in self._channels:
            if not self._usable(channel, device_id):
                continue
            matrix = channel.capabilities
            if all(matrix.get(cap) not in (None, QualityLevel.NONE) for cap in required):
                return channel
        return None

    def plan(
        self,
        device_id: int,
        capabilities: Iterable[CollectCapability | str],
    ) -> dict[CollectCapability, list[BaseChannel]]:
        """能力级分派（O2=A 的落地）：``{cap: [候选通道，按优先级]}``。

        某个能力的候选为空，意味着"没有任何通道支持它" —— :meth:`collect` 会把它
        标为 ``UNSUPPORTED``（确定答案，不补采、不记 error，AC-9）。
        """
        caps = sorted({as_capability(c) for c in capabilities}, key=cap_value)
        usable = [ch for ch in self._channels if self._usable(ch, device_id)]
        skips = self._role_skips(device_id)
        plan: dict[CollectCapability, list[BaseChannel]] = {}
        for cap in caps:
            if cap in skips:
                plan[cap] = []
                continue
            plan[cap] = [
                ch for ch in usable
                if ch.capabilities.get(cap) not in (None, QualityLevel.NONE)
            ]
        return plan

    def collect(
        self,
        device_id: int,
        capabilities: Iterable[CollectCapability | str],
        timeout: float | None = None,
    ) -> CollectedFacts:
        """按能力分派采集，失败能力回落下一通道，全程共享**一个**整设备预算。

        Args:
            device_id: 设备 ID。
            capabilities: 需要的采集能力。
            timeout: 覆盖默认整设备预算（秒）。**不是**单能力超时 —— 预算被所有
                轮次共享，剩余多少就给下一轮多少。

        Returns:
            CollectedFacts: 合并后的结果；``meta["channels"]`` 记录每个能力的
            实际来源通道，``meta["degraded_from"]`` 记录被降级的原通道。
        """
        requested = sorted({as_capability(c) for c in capabilities}, key=cap_value)
        if not requested:
            raise ValueError("capabilities 不能为空——空请求与'什么都没采到'必须可区分")

        plans = self.plan(device_id, requested)
        facts = CollectedFacts()
        facts.meta[META_KEY_REQUESTED] = [cap_value(c) for c in requested]
        facts.meta[META_KEY_COLLECTED_AT] = datetime.now(timezone.utc).isoformat()
        facts.meta[META_KEY_ERRORS] = {}
        facts.meta[META_KEY_CHANNELS] = {}
        facts.meta[META_KEY_BUDGET_EXHAUSTED] = False

        for cap, candidates in plans.items():
            if not candidates:
                facts.outcomes[cap_value(cap)] = CapabilityOutcome.UNSUPPORTED

        started = time.monotonic()
        deadline = started + (float(timeout) if timeout else self._budget)
        tried: dict[str, list[str]] = {cap_value(cap): [] for cap in requested}
        depth = 0
        max_depth = max((len(c) for c in plans.values()), default=0)

        while depth < max_depth:
            pending = [cap for cap in requested if _needs_attempt(facts, cap)]
            if not pending:
                break

            buckets: dict[str, tuple[BaseChannel, list[CollectCapability]]] = {}
            for cap in pending:
                candidates = plans.get(cap) or []
                if depth >= len(candidates):
                    continue  # 候选用尽：保持已有的 FAILED，不再尝试
                channel = candidates[depth]
                entry = buckets.setdefault(channel.code, (channel, []))
                entry[1].append(cap)

            if not buckets:
                break

            for _code, (channel, caps) in buckets.items():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._exhaust_budget(facts, caps)
                    continue
                sub = channel.collect(device_id, caps, timeout=remaining)
                facts = self._absorb(
                    facts, sub, channel, caps, device_id, tried, degraded_from=depth > 0,
                )

            if facts.meta.get(META_KEY_BUDGET_EXHAUSTED):
                break
            depth += 1

        facts.meta[META_KEY_ELAPSED_MS] = round((time.monotonic() - started) * 1000)
        facts.refresh_meta()
        return facts

    def _exhaust_budget(self, facts: CollectedFacts, caps: list[CollectCapability]) -> None:
        """预算耗尽：尚未开始的能力标 FAILED + ``budget_exhausted``（AC-13）。

        区别于单能力自身超时（``timeout``）：后者**不**置 ``budget_exhausted``
        （规格 §3.3），两者成因不同，下游据此分辨"被我们的预算掐断"还是"设备慢"。
        """
        facts.meta[META_KEY_BUDGET_EXHAUSTED] = True
        for cap in caps:
            key = cap_value(cap)
            facts.outcomes[key] = CapabilityOutcome.FAILED
            facts.meta.setdefault(META_KEY_ERRORS, {})[key] = {
                "code": "budget_exhausted",
                "message": "整设备时间预算已耗尽，未开始采集",
            }

    def _absorb(
        self,
        facts: CollectedFacts,
        sub: CollectedFacts,
        channel: BaseChannel,
        caps: list[CollectCapability],
        device_id: int,
        tried: dict[str, list[str]],
        *,
        degraded_from: bool,
    ) -> CollectedFacts:
        """把一次子采集的结果合回总账，返回**新**的总账（不改入参）。

        - ``degraded_from``：本轮是补采（depth>0）时把**上一次**用的通道记为降级
          来源。``merge_meta`` 对 ``degraded_from`` 取"早到的那一侧"，所以必须写在
          self 侧（合并前的 ``facts``）才不会被后续合并抹掉。
        - 熔断计数：只有"一项都没采到"才累加（D3 修订），采到任一项即清零 ——
          部分成功说明通道还活着，按失败计数会把可用通道熔断掉。
        """
        if degraded_from:
            degraded = facts.meta.setdefault(META_KEY_DEGRADED_FROM, {})
            for cap in caps:
                previous = tried.get(cap_value(cap)) or []
                if previous:
                    degraded.setdefault(cap_value(cap), previous[-1])

        for cap in caps:
            tried.setdefault(cap_value(cap), []).append(channel.code)

        got_any = any(not sub.needs_fallback(cap) for cap in caps)
        cb_key = (channel.code, device_id)
        if got_any:
            self._store.record_success(channel.code, device_id)
            self._opened_at.pop(cb_key, None)
            self._half_open_used.discard(cb_key)
        else:
            count = self._store.record_failure(channel.code, device_id)
            if cb_key in self._half_open_used:
                self._half_open_used.discard(cb_key)
                while count < self._threshold:
                    count = self._store.record_failure(channel.code, device_id)
                self._opened_at[cb_key] = time.monotonic()
            elif count >= self._threshold:
                self._opened_at.setdefault(cb_key, time.monotonic())
            logger.warning(
                "通道 %s 对 device_id=%s 本轮一项未采到（连续失败 %d/%d）",
                channel.code, device_id, count, self._threshold,
            )
            if self._threshold > 0 and count == self._threshold:
                COLLECTOR_METRICS.record_circuit_trip(channel.code)

        return facts.merge(sub)

    def probe(self, device_id: int) -> dict[str, bool]:
        """显式健康检查（**不在**选择路径上调用）。

        ``{channel_code: 是否健康}``。成本是每通道一次握手，只在 T-G1 接入点
        需要"先探再采"的场合用。
        """
        result: dict[str, bool] = {}
        for channel in self._channels:
            try:
                result[channel.code] = bool(channel.health_probe(device_id))
            except Exception as exc:  # noqa: BLE001 -- 通道健康检查异常视为不可用：探测失败不得阻断选路
                logger.warning("健康检查异常 channel=%s device_id=%s: %s",
                               channel.code, device_id, exc)
                result[channel.code] = False
        return result


__all__ = [
    "CIRCUIT_KEY_TEMPLATE",
    "DEFAULT_BUDGET_SECONDS",
    "DEFAULT_CIRCUIT_THRESHOLD",
    "DEFAULT_CIRCUIT_TTL",
    "ChannelSelector",
    "CircuitStore",
    "MemoryCircuitStore",
    "RedisCircuitStore",
]
