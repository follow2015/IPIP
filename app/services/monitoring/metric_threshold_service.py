# -*- coding: utf-8 -*-
"""指标阈值评估服务（MetricThresholdService）

根据指标模板的 metric_type 判定采集值是否触发告警，输出统一的告警判定结果。

metric_type 判定规则：
- gauge：与阈值 {warn, crit} 比较 → (severity, breached)
- counter：调用方先换算速率/差值后再按 gauge 判定（本服务不感知原始计数）
- state：与 {expected} 比较，不等即告警（如端口 expected=up，实际 down）
- event：出现即告警（如 RAID/硬盘故障事件）

告警层级：crit > warn。超出 crit 报 critical，超出 warn 报 warning。

阈值覆盖分层（预留）：
- 全局默认：模板.threshold
- 设备级覆盖：device_metric_overrides（本里程碑未建表，接口已预留）
"""
from typing import Optional, Tuple


class MetricThresholdService:

    def evaluate(self, metric_type: str, value, threshold: Optional[dict]) -> Tuple[str, bool]:
        if value is None:
            return "ok", False

        if metric_type == "event":
            if threshold and threshold.get("crit"):
                return "crit", True
            if threshold and threshold.get("warn"):
                return "warn", True
            return "warn", True

        if not threshold:
            return "ok", False

        if metric_type == "state":
            expected = threshold.get("expected")
            if expected is not None and str(value) != str(expected):
                return self._severity_for_state(threshold), True
            return "ok", False

        try:
            num = float(value)
        except (TypeError, ValueError):
            return "ok", False

        crit = threshold.get("crit")
        warn = threshold.get("warn")
        min_v = threshold.get("min")
        max_v = threshold.get("max")

        if max_v is not None and num > float(max_v):
            return "crit", True
        if min_v is not None and num < float(min_v):
            return "crit", True
        if crit is not None and num > float(crit):
            return "crit", True
        if warn is not None and num > float(warn):
            return "warn", True
        return "ok", False

    @staticmethod
    def _severity_for_state(threshold: dict) -> str:
        sev = threshold.get("severity")
        if isinstance(sev, str) and sev in ("crit", "warn"):
            return sev
        if threshold.get("crit"):
            return "crit"
        return "warn"
