# -*- coding: utf-8 -*-
"""多通道采集 · 进程内指标注册表（T0.11，V2 落地）。

要解决的缺陷（评审 §20.5 V2）：§14 验收要求"通道命中率、质量分布、熔断次数"
可观测，但代码只有 ``meta`` 里的单批次数据，没有任何跨批次的汇总出口 ——
指标数据每次随 facts 被消费后即蒸发，"命中率"这类需要分母的口径根本无从谈起。

三项指标的口径（唯一真源就是本模块，消费端不得自行再从 meta 拼装）::

    通道命中率   hit_rate = satisfied / delegated（delegated=0 时为 None，
                不给 0 —— "从未委派"与"委派了全失败"是两件事，压成一个数
                会把后者伪装成前者）
    耗时         elapsed_ms 的**计数与总和**（不存分位数：进程内没有
                无界明细的预算，P95 属于外部监控体系的职责）
    质量分布     per-capability 落在 full/partial/none 的批次数（FAILED
                在 refresh_meta 里已降档 none，此处如实累计）

刻意**不做**的三件事：

1. **不依赖 Flask / DB / Redis**（ADR-004 的依赖边界：通道层零监控侧 import；
   本模块在 collector 包内、只用标准库）。代价是进程重启清零 —— 但可观测
   数据的第一消费方是日志与排障，跨进程聚合是既有监控体系的事（V2 建议
   "汇总后写入既有监控体系"，本模块就是那个"汇总"的唯一数据源）。
2. **不记 per-device 明细**。设备维度属于审计，不属于指标；无界 dict 会随
   设备数线性膨胀且永不回收。
3. **不让指标故障反噬采集**。所有 ``record_*`` 的调用方都必须套
   ``try/except``（``base_channel`` / ``selector`` 已照此接线）—— 指标挂了
   顶多丢一条计数，采集挂了是事故。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.services.collector.contract import CapabilityOutcome

_QUALITY_BUCKETS = ("full", "partial", "none")


class CollectorMetrics:
    """线程安全的进程内指标累加器。

    一把锁护全部计数：指标写入频率是"每次采集一批各一条"，远够用；拆多把锁
    只会让 snapshot 的一致性变复杂（各锁下读到的不是同一时刻的世界）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset_unlocked()

    def record_channel_collect(
        self,
        channel: str,
        delegated: int,
        outcomes: dict[str, str],
        quality: dict[str, str],
        elapsed_ms: int,
    ) -> None:
        """记一次通道采集批次（``BaseChannel.collect`` 收尾各调一次）。

        Args:
            channel: 通道 code（``"cli"`` / ``"snmp"``）。
            delegated: 本批次委派给该通道的能力数（``meta["channels"]`` 的长度
                —— 只数真正留名的，UNSUPPORTED 不算委派）。
            outcomes: ``{cap_key: outcome_value}``，只统计 SATISFIED/EMPTY/FAILED。
            quality: ``{cap_key: quality_value}``（refresh_meta 派生后的终值）。
            elapsed_ms: 本批次耗时（``meta["elapsed_ms"]``）。
        """
        with self._lock:
            stat = self._channels.setdefault(
                channel,
                {"collects": 0, "delegated": 0, "satisfied": 0,
                 "empty": 0, "failed": 0, "elapsed_ms_total": 0},
            )
            stat["collects"] += 1
            stat["delegated"] += delegated
            stat["elapsed_ms_total"] += int(elapsed_ms)
            for outcome in outcomes.values():
                if outcome == CapabilityOutcome.SATISFIED.value:
                    stat["satisfied"] += 1
                elif outcome == CapabilityOutcome.EMPTY.value:
                    stat["empty"] += 1
                elif outcome == CapabilityOutcome.FAILED.value:
                    stat["failed"] += 1
            for cap, level in quality.items():
                bucket = level if level in _QUALITY_BUCKETS else "none"
                self._quality.setdefault(cap, dict.fromkeys(_QUALITY_BUCKETS, 0))
                self._quality[cap][bucket] += 1
            if outcomes:
                self._collect_batches += 1

    def record_circuit_trip(self, channel: str) -> None:
        """记一次熔断触发（连续失败**恰好**达到阈值的那一刻，不是每一笔失败）。"""
        with self._lock:
            self._circuit_trips[channel] = self._circuit_trips.get(channel, 0) + 1

    def record_budget_exhausted(self, channel: str | None = None) -> None:
        """记一次整设备预算耗尽（``meta["budget_exhausted"]`` 为真的批次）。"""
        key = channel or "unknown"
        with self._lock:
            self._budget_exhausted[key] = self._budget_exhausted.get(key, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        """导出三项指标的当前累计值（深拷贝，调用方改不动内部状态）。

        形状（G3 全周期看板与 V2 消费端以本形状为契约）::

            {
              "generated_at": "...ISO8601...",
              "collect_batches": 3,
              "channels": {
                "cli": {"collects": 3, "delegated": 8, "satisfied": 6,
                         "empty": 1, "failed": 1, "elapsed_ms_total": 900,
                         "hit_rate": 0.75},
              },
              "quality": {"ports": {"full": 2, "partial": 0, "none": 1}},
              "circuit_trips": {"cli": 1},
              "budget_exhausted": {"cli": 1},
            }
        """
        with self._lock:
            channels: dict[str, dict[str, Any]] = {}
            for code, stat in self._channels.items():
                out = dict(stat)
                out["hit_rate"] = (
                    round(stat["satisfied"] / stat["delegated"], 4)
                    if stat["delegated"] > 0 else None
                )
                channels[code] = out
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "collect_batches": self._collect_batches,
                "channels": {k: dict(v) for k, v in channels.items()},
                "quality": {cap: dict(levels) for cap, levels in self._quality.items()},
                "circuit_trips": dict(self._circuit_trips),
                "budget_exhausted": dict(self._budget_exhausted),
            }

    def reset(self) -> None:
        """清零。**只给测试用**：生产进程的指标生命周期 = 进程生命周期。"""
        with self._lock:
            self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self._channels: dict[str, dict[str, int]] = {}
        self._quality: dict[str, dict[str, int]] = {}
        self._circuit_trips: dict[str, int] = {}
        self._budget_exhausted: dict[str, int] = {}
        self._collect_batches = 0


COLLECTOR_METRICS = CollectorMetrics()


__all__ = ["COLLECTOR_METRICS", "CollectorMetrics"]
