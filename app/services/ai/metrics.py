# -*- coding: utf-8 -*-
"""AI Prometheus 指标。"""
from collections import OrderedDict

try:
    from prometheus_client import Counter, Histogram
    _tokens = Counter("ai_tokens_total", "AI token 消耗", ["scenario", "model"])
    _duration = Histogram("ai_call_duration_seconds", "AI 调用耗时", ["scenario", "model"])
    _errors = Counter("ai_errors_total", "AI 调用错误", ["scenario", "model"])
    _skill_runs = Counter("ai_skill_runs_total", "技能执行次数", ["skill_name", "status"])
    _skill_duration = Histogram("ai_skill_run_duration_seconds", "技能执行耗时", ["skill_name"])
    _HAS_PROM = True
except ImportError:  # pragma: no cover
    _HAS_PROM = False

_MEM_MAX_KEYS = 1000

_mem_tokens: "OrderedDict" = OrderedDict()
_mem_errors: "OrderedDict" = OrderedDict()
_mem_skill_runs: "OrderedDict" = OrderedDict()


def _mem_bump(store: "OrderedDict", key: tuple, delta: int) -> None:
    """内存兜底计数：写入后置为最新，超限淘汰最久未更新的条目（A10）。"""
    store[key] = store.get(key, 0) + delta
    store.move_to_end(key)
    while len(store) > _MEM_MAX_KEYS:
        store.popitem(last=False)


def record_call(scenario: str, model: str, user_id: int,
                tokens: int = 0, duration_seconds: float = 0.0,
                status: str = "ok") -> None:
    if _HAS_PROM:
        _tokens.labels(scenario=scenario, model=model).inc(tokens)
        _duration.labels(scenario=scenario, model=model).observe(duration_seconds)
        if status != "ok":
            _errors.labels(scenario=scenario, model=model).inc()
    else:
        _mem_bump(_mem_tokens, (scenario, model), tokens)
        if status != "ok":
            _mem_bump(_mem_errors, (scenario, model), 1)


def record_skill_run(skill_name: str, status: str = "ok",
                     duration_seconds: float = 0.0, tokens: int = 0) -> None:
    """记录一次技能执行（Tier 1 + Agentic 统一入口）。"""
    if _HAS_PROM:
        _skill_runs.labels(skill_name=skill_name, status=status).inc()
        _skill_duration.labels(skill_name=skill_name).observe(duration_seconds)
    else:
        _mem_bump(_mem_skill_runs, (skill_name, status), 1)


def get_metrics() -> dict:
    if _HAS_PROM:
        from prometheus_client import generate_latest
        return {"raw": generate_latest().decode("utf-8")}
    return {"ai_tokens_total": sum(_mem_tokens.values()),
            "ai_errors_total": sum(_mem_errors.values()),
            "ai_skill_runs_total": sum(_mem_skill_runs.values())}
