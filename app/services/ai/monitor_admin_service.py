# -*- coding: utf-8 -*-
"""AI 监控管理服务：熔断器状态 + 运行指标。

v3（方案 §6.2）：熔断器状态已改为 Redis 存储，本模块不再读进程内 `_BREAKERS`
字典与私有字段（否则运维端点会静默显示空状态、手动重置失效）。

以模块引用（`circuit_breaker.X`）而非 `from ... import X` 调用：后者会把函数
对象绑定到本模块命名空间，测试 patch `circuit_breaker._get_redis` 时不会生效。
"""
from typing import Any, Dict, List

from app.services.ai import circuit_breaker as cb
from app.services.ai import metrics as ai_metrics


def get_circuit_status() -> List[Dict[str, Any]]:
    """获取所有 provider 的熔断器状态。

    v3：不再依赖进程内 `_BREAKERS` 快照——它只反映**本进程**用过的 provider，
    多进程下会漏报。改为按 Redis 索引 + 已知常量逐个读快照。

    每次构造新的 CircuitBreaker 而非复用 `get_circuit_breaker()` 单例：单例在
    构造时就绑定了当时的存储后端，若彼时 Redis 不可用则永久停留在降级模式，
    即使 Redis 随后恢复也读不到共享状态。运维端点调用频率极低，构造开销可忽略。
    """
    r = cb._get_redis()
    return [cb.CircuitBreaker(name).snapshot() for name in cb.known_providers(r)]


def reset_circuit(provider: str) -> None:
    """重置指定 provider 熔断器（清零失败计数）。

    v3：状态在 Redis，故不再校验「provider 是否存在于 _BREAKERS」——该字典只
    反映本进程，用它做前置校验会让运维在 A 机器上无法重置 B 机器触发的熔断。
    """
    cb.CircuitBreaker(provider).reset()


def get_metrics_summary() -> Dict[str, Any]:
    """获取 AI 运行指标摘要。"""
    return ai_metrics.get_metrics()
