# -*- coding: utf-8 -*-
"""诊断类 capability：device.live_inspection + ssh.diagnostic_show。

设计文档第三节：
- device.live_inspection：厂商无关命名，内部按 device.brand 路由，从 DeviceMetricLatest 取指标。
- ssh.diagnostic_show：通过 SSH 执行预定义只读诊断命令，按厂商分组的命令白名单。

两者都是只读能力，allowed_capabilities 只注册只读，结构上无法调用写操作。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.ai.capabilities.registry import register_capability
from app.services.ai.command_safety import (
    get_diagnostic_command,
    is_diagnostic_command_allowed,
    resolve_command_family,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)



_CHECK_METRIC_KEYS = {
    "cpu": ["cpu_usage", "zabbix_cpu_usage"],
    "memory": ["memory", "memory_usage", "zabbix_memory_usage"],
    "interface": ["interface", "interface_status"],
    "temperature": ["temperature", "temp"],
}

_UNSUPPORTED_CHECK_HINTS: Dict[str, Dict[str, str]] = {
    "session": {
        "h3c": "请人工执行 display session statistics",
        "huawei": "请人工执行 display session statistics",
        "cisco": "该设备无自动采集的会话指标，Cisco ASA 请人工执行 show conn count",
    },
    "syn_half_open": {
        "h3c": "请人工执行 display session relation 查看半连接",
        "huawei": "请人工执行 display session statistics 查看半连接",
        "cisco": "请人工执行 show tcp brief all 查看 TCP 连接状态",
    },
}
_UNKNOWN_FAMILY_HINT = "该设备厂商未登记命令族，无法给出对应的人工排查命令"


def _parse_metric_value(raw: str) -> float | None:
    """把 DeviceMetricLatest.value（字符串快照）解析为数值。

    设备回显可能是 "86%" / "72.3" / "0.86" 等，取首个数值片段。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"-?\d+\.?\d*", s)
    if m is None:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _build_metric_result(
    metric_key: str, value: float, unit: str = "%",
    anomaly: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """构建单项指标结果（含基线偏离）。

    设计文档第四节：诊断结论中的"基线偏离"必须是计算出来的事实，不能是 LLM
    凭经验估的数字。基线缺失时返回 null + insufficient_samples，绝不臆造。

    Args:
        metric_key: 命中的 metric_key。
        value: 解析后的指标值。
        unit: 单位（百分比类为 "%"）。
        anomaly: BaselineService.detect_anomaly 的结果；None 表示未做基线检测。
    """
    if anomaly is None:
        return {
            "value": value, "unit": unit, "metric_key": metric_key,
            "baseline": None, "deviation_pct": None,
            "baseline_status": "insufficient_samples",
        }
    baseline = anomaly.get("baseline") or {}
    return {
        "value": value,
        "unit": unit,
        "metric_key": metric_key,
        "baseline": baseline.get("mean"),
        "deviation_pct": anomaly.get("deviation_pct"),
        "baseline_status": baseline.get("baseline_status", "insufficient_samples"),
        "anomaly_reason": anomaly.get("reason"),
    }


@register_capability("device.live_inspection")
def live_inspection(args: Dict[str, Any]) -> Dict[str, Any]:
    """设备实时巡检：从 DeviceMetricLatest 批量取多项指标。

    设计文档第三节：厂商无关命名，一次调用传多个 checks，非并行执行。
    字段名不匹配时返回 supported:false，不静默 None。
    session/syn_half_open 无自动采集通道 → supported:false + hint，可再调 ssh.diagnostic_show。

    Args:
        args: {"device_id": int, "checks": ["cpu", "memory", "interface", ...]}

    Returns:
        {"device_id": ..., "brand": ..., "checks": {check_name: result|{supported:false,hint}}}
    """
    from app.services.ai.service_factory import get_device_service
    from app.models.device_metric_latest import DeviceMetricLatest
    from app.persistence.device_metric_latest_repository import DeviceMetricLatestRepository
    from extensions import db

    device_id = args.get("device_id")
    if not isinstance(device_id, int):
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            return {"supported": False, "hint": "device_id 必填且为整数"}

    checks = args.get("checks") or ["cpu", "memory", "interface"]
    if not isinstance(checks, list):
        checks = [checks]

    device = get_device_service().get_device_by_id(device_id)
    if not device:
        return {"supported": False, "hint": f"设备 {device_id} 不存在"}

    brand_family = resolve_command_family(device.get("brand"))

    from app.services.ai.baseline_service import BaselineService
    baseline_svc = BaselineService()

    repo = DeviceMetricLatestRepository(db.session)
    all_metrics = repo.find_by_device(device_id)
    metric_map: Dict[str, DeviceMetricLatest] = {}
    for m in all_metrics:
        metric_map[m.metric_key] = m

    results: Dict[str, Any] = {}
    for check in checks:
        if check in _UNSUPPORTED_CHECK_HINTS:
            hints = _UNSUPPORTED_CHECK_HINTS[check]
            results[check] = {
                "supported": False,
                "hint": hints.get(brand_family, _UNKNOWN_FAMILY_HINT)
                if brand_family else _UNKNOWN_FAMILY_HINT,
            }
            continue

        candidate_keys = _CHECK_METRIC_KEYS.get(check)
        if not candidate_keys:
            results[check] = {"supported": False, "hint": f"未知 check 项：{check}"}
            continue

        matched = None
        for mk in candidate_keys:
            if mk in metric_map:
                matched = metric_map[mk]
                break

        if matched is None:
            results[check] = {
                "supported": False,
                "hint": f"未采集到 {check} 指标（候选 metric_key: {candidate_keys}）",
            }
            continue

        value = _parse_metric_value(matched.value)
        if value is None:
            results[check] = {
                "supported": False,
                "hint": f"指标 {matched.metric_key} 值无法解析：{matched.value!r}",
            }
            continue

        unit = "%" if check in ("cpu", "memory") else ""
        try:
            anomaly = baseline_svc.detect_anomaly(device_id, matched.metric_key, value)
        except Exception as e:  # noqa: BLE001 - 基线查询失败降级为无基线，不阻断巡检
            logger.warning("baseline detect failed device=%s metric=%s: %s",
                           device_id, matched.metric_key, e)
            anomaly = None
        results[check] = _build_metric_result(matched.metric_key, value, unit, anomaly)

    return {"device_id": device_id, "brand": brand_family, "checks": results}



_KEY_LINE_PATTERN = re.compile(
    r"error|down|fail|crc|drop|discard|collision|flapping|err-disable|%",
    re.IGNORECASE,
)
_MAX_DIAGNOSTIC_OUTPUT_CHARS = 4000


def _truncate_with_key_lines(text: str, limit: int = _MAX_DIAGNOSTIC_OUTPUT_CHARS) -> Dict[str, Any]:
    """截断前先按关键词提取命中行优先保留，再填充其余内容。

    设计文档第三节：朴素的"保留前 N 行"会恰好切掉故障特征所在的行。
    """
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return {"text": text, "truncated": False, "total_lines": None, "kept_lines": None}

    lines = text.split("\n")
    total_lines = len(lines)
    key_lines = [ln for ln in lines if _KEY_LINE_PATTERN.search(ln)]
    other_lines = [ln for ln in lines if not _KEY_LINE_PATTERN.search(ln)]

    kept: List[str] = []
    used = 0
    for ln in key_lines:
        if used + len(ln) + 1 > limit:
            break
        kept.append(ln)
        used += len(ln) + 1
    for ln in other_lines:
        if used + len(ln) + 1 > limit:
            break
        kept.append(ln)
        used += len(ln) + 1

    return {
        "text": "\n".join(kept),
        "truncated": True,
        "total_lines": total_lines,
        "kept_lines": len(kept),
    }


@register_capability("ssh.diagnostic_show")
def diagnostic_show(args: Dict[str, Any]) -> Dict[str, Any]:
    """通过 SSH 执行预定义只读诊断命令。

    设计文档第三节四项强制约束：
    1. 输出截断：单条上限 4000 字符，截断前先提取关键行。
    2. 超时显式传参：timeout=30（不用 SSHManager 默认 120s）。
    3. 独立熔断器：SSH 通道单独走熔断（get_circuit_breaker("ssh")）。
    4. 独立短超时锁：诊断走独立只读锁（mode="read", timeout=5）。

    Args:
        args: {"device_id": int, "command_key": str}

    Returns:
        {"device_id": ..., "command_key": ..., "output": {...}} 或 {"supported": False, ...}
    """
    from app.services.ai.service_factory import get_device_service
    from app.persistence.switch_repo import SwitchRepository
    from app.services.device_op_lock import device_op_lock, DeviceOperationConflict
    from app.services.ai.circuit_breaker import get_circuit_breaker, AICircuitOpenError
    from app.infra import SSHManager

    device_id = args.get("device_id")
    try:
        device_id = int(device_id)
    except (TypeError, ValueError):
        return {"supported": False, "hint": "device_id 必填且为整数"}

    from app.services.ai.capabilities.device_scope import check_device_access
    allowed, reason = check_device_access(device_id, fail_closed=True)
    if not allowed:
        return {"supported": False, "hint": reason}

    command_key = args.get("command_key")
    if not command_key or not isinstance(command_key, str):
        return {"supported": False, "hint": "command_key 必填且为预定义键"}

    device = get_device_service().get_device_by_id(device_id)
    if not device:
        return {"supported": False, "hint": f"设备 {device_id} 不存在"}

    brand_family = resolve_command_family(device.get("brand"))
    if brand_family is None:
        return {
            "supported": False,
            "hint": f"设备 {device_id} 的厂商（{device.get('brand')}）未登记命令族，"
                    f"无法匹配诊断白名单",
        }

    if not is_diagnostic_command_allowed(brand_family, command_key):
        return {
            "supported": False,
            "hint": f"命令 {command_key} 不在厂商 {brand_family} 的诊断白名单中",
        }

    command = get_diagnostic_command(brand_family, command_key)

    switch = SwitchRepository().find_by_device_id(device_id)
    if not switch:
        return {"supported": False, "hint": f"设备 {device_id} 无 SSH 凭据"}

    try:
        with device_op_lock.acquire(device_id, timeout=5, mode="read"):
            try:
                raw_output = get_circuit_breaker("ssh").call(
                    lambda: SSHManager().send_show_command(switch, command, timeout=30)
                )
            except AICircuitOpenError:
                return {"supported": False, "hint": "SSH 通道熔断开启，设备可能不可达"}
            except Exception as e:  # noqa: BLE001 - 统一降级为 supported:false
                logger.warning("ssh.diagnostic_show device=%s cmd=%s failed: %s",
                               device_id, command_key, e)
                return {"supported": False, "hint": f"SSH 执行失败：{type(e).__name__}"}
    except DeviceOperationConflict:
        return {"supported": False, "hint": f"设备 {device_id} 当前有操作正在执行（只读锁未获取）"}

    truncated = _truncate_with_key_lines(raw_output)
    return {
        "device_id": device_id,
        "command_key": command_key,
        "command": command,  # 返回实际执行的命令供审计（白名单内，安全）
        "output": truncated,
    }
