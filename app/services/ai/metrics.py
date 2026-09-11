# -*- coding: utf-8 -*-
"""AI 运行指标：Redis 聚合存储 + 进程内兜底，输出 Prometheus exposition 文本。

为什么不再用进程内的 ``prometheus_client`` 指标对象：
部署形态是 ``gunicorn -w 4`` + ``celery worker``（见 ``ipip-deploy/scripts/start.sh``），
进程内内存态（含 prometheus_client 默认 registry）**无法跨进程汇总**，管理端看数
会随命中的 worker 漂移——典型表现就是"只有 HELP/TYPE、没有样本行"，且 celery 里
发生的 AI 调用永远不出现在 gunicorn 的输出中。故权威计数放 Redis（HINCRBY 原子
累加，天然覆盖 gunicorn / celery / 多机），进程内有界 dict 仅作 Redis 不可用时的兜底。

窗口：每个指标同时维护「累计 total」与「当日 day（TTL 30 天）」两份，
exposition 中用 ``window="total"|"day"`` 标签区分，指标名不重复。
"""
import os
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from app.utils.logging import get_logger
from app.utils.time_utils import utc_today

logger = get_logger(__name__)

_SERIES: Dict[str, Tuple[str, str, str, Tuple[str, ...]]] = {
    "calls": ("ai_llm_calls_total", "AI LLM 调用次数", "counter",
              ("scenario", "model")),
    "errors": ("ai_llm_errors_total", "AI LLM 调用失败次数", "counter",
               ("scenario", "model")),
    "aborted": ("ai_llm_aborted_total", "AI LLM 调用被客户端中断次数", "counter",
                ("scenario", "model")),
    "prompt_tokens": ("ai_llm_prompt_tokens_total", "AI 输入 token 消耗", "counter",
                      ("scenario", "model")),
    "completion_tokens": ("ai_llm_completion_tokens_total", "AI 输出 token 消耗", "counter",
                          ("scenario", "model")),
    "duration_sum": ("ai_llm_duration_seconds_sum", "AI 调用耗时累计（秒）", "counter",
                     ("scenario", "model")),
    "skill_runs": ("ai_skill_runs_total", "技能执行次数", "counter",
                   ("skill_name", "status")),
    "skill_duration_sum": ("ai_skill_duration_seconds_sum", "技能执行耗时累计（秒）", "counter",
                           ("skill_name",)),
    "skill_menu_calls": ("ai_skill_menu_calls_total", "AI 路由构造技能菜单次数", "counter",
                         ("mode", "fallback")),
    "skill_menu_size_sum": ("ai_skill_menu_size_sum", "AI 路由注入 prompt 的技能数累计", "counter",
                            ("mode",)),
}

_NS = "ai:metrics"
_DAY_TTL = 30 * 86400  # 当日窗口保留 30 天，便于回看近期趋势
_WINDOWS = ("total", "day")

_MEM_MAX_KEYS = 1000
_mem: Dict[str, "OrderedDict"] = {name: OrderedDict() for name in _SERIES}
_mem_lock = threading.Lock()


def _redis():
    """返回全局 Redis 单例，不可用（未配置 / 连接失败）时返回 None。"""
    try:
        from app.utils.redis_client import get_redis_client
        return get_redis_client()
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.metrics.redis_unavailable %s", e)
        return None


def _day_stamp() -> str:
    """当日窗口的日期戳（**UTC 日历日** YYYYMMDD）。

    统一用 ``utc_today()``：时序数据按 UTC 存储，若取服务器本地日，容器 TZ 不同
    时"今日"边界会随之偏移（UTC 容器相比 CST 差 8 小时），多 worker 之间也会
    落到不同的 day key。UTC 日界与库内时间口径一致，且完全不受进程 TZ 影响。
    """
    return utc_today().strftime("%Y%m%d")


def _key(name: str, window: str) -> str:
    """构造 Redis key：累计为 total，当日带日期戳。"""
    if window == "day":
        return f"{_NS}:day:{_day_stamp()}:{name}"
    return f"{_NS}:total:{name}"


def _mem_bump(name: str, values: Tuple[str, ...], delta: float) -> None:
    """进程内兜底计数：写入后置为最新，超限淘汰最久未更新的条目。"""
    with _mem_lock:
        store = _mem[name]
        store[values] = store.get(values, 0.0) + delta
        store.move_to_end(values)
        while len(store) > _MEM_MAX_KEYS:
            store.popitem(last=False)


def _norm_label(value: str) -> str:
    """规范化标签值：去掉 dim 分隔符与不可打印字符。

    dim 以 "|" 拼接，标签值若含 "|" 会让该样本在 _render 中因段数不符而被
    丢弃——模型名可来自配置（任意 OpenAI 兼容端点名），必须在写侧就约束住。
    """
    cleaned = "".join(ch if ch.isprintable() else "_" for ch in str(value or ""))
    return cleaned.replace("|", "_").strip() or "unknown"


def _write(items: List[Tuple[str, Tuple[str, ...], float]]) -> bool:
    """把增量累加进 Redis 的累计与当日两个窗口。

    Args:
        items: [(系列名, 标签值元组, 增量)]。

    Returns:
        是否写入成功。False 表示 Redis 不可用，调用方需回落到进程内兜底。
    """
    r = _redis()
    if r is None:
        return False
    try:
        pipe = r.pipeline()
        expired = set()
        for name, values, delta in items:
            dim = "|".join(_norm_label(v) for v in values)
            for window in _WINDOWS:
                key = _key(name, window)
                pipe.hincrbyfloat(key, dim, delta)
                if window == "day" and key not in expired:
                    pipe.expire(key, _DAY_TTL)
                    expired.add(key)
        pipe.execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.metrics.redis_write_failed %s", e)
        return False


def _decode(raw) -> Dict[str, float]:
    """把 hgetall 的结果（bytes 或 str）统一解码成 {dim: float}。

    decode_responses=False 的客户端返回 bytes 键值，而 ``float(b"1.5")`` 直接抛
    TypeError——必须键与值一并解码。否则所有样本会被**静默丢弃**，表现为
    "指标全空却无任何报错"，正是本次要根治的同类故障。
    """
    out: Dict[str, float] = {}
    for k, v in (raw or {}).items():
        dim = k.decode("utf-8") if isinstance(k, bytes) else str(k)
        val = v.decode("utf-8") if isinstance(v, bytes) else v
        try:
            out[dim] = float(val)
        except (TypeError, ValueError):
            logger.warning("ai.metrics.decode_failed dim=%s", dim)
    return out


def _read() -> Optional[Dict[str, Dict[str, Dict[str, float]]]]:
    """读取全部窗口与系列。

    Returns:
        {window: {name: {dim: value}}}；Redis 不可用或读取失败返回 None
        （调用方据此回落到进程内兜底）。
    """
    r = _redis()
    if r is None:
        return None
    keys = [(w, n, _key(n, w)) for w in _WINDOWS for n in _SERIES]
    try:
        pipe = r.pipeline()
        for _, _, key in keys:
            pipe.hgetall(key)
        raw_list = pipe.execute()
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.metrics.redis_read_failed %s", e)
        return None

    rows: Dict[str, Dict[str, Dict[str, float]]] = {w: {} for w in _WINDOWS}
    for (window, name, _), raw in zip(keys, raw_list):
        rows[window][name] = _decode(raw)
    return rows


def _mem_rows() -> Dict[str, Dict[str, Dict[str, float]]]:
    """兜底路径：进程内数据伪装成 total 窗口（无当日维度，仅本进程可见）。"""
    rows: Dict[str, Dict[str, Dict[str, float]]] = {w: {} for w in _WINDOWS}
    for name, store in _mem.items():
        rows["total"][name] = {"|".join(v): float(val) for v, val in store.items()}
    return rows


def record_llm_call(scenario: str, model: str, prompt_tokens: int = 0,
                    completion_tokens: int = 0, duration_seconds: float = 0.0,
                    status: str = "ok") -> None:
    """记录一次 LLM 调用（跨进程聚合，Redis 优先、进程内兜底）。

    Args:
        scenario: 业务场景（rag / nlq / alert / inspection / skill.xxx / agentic.xxx）。
        model: 模型名。
        prompt_tokens: 输入 token（取自 resp.usage.prompt_tokens）。
        completion_tokens: 输出 token（取自 resp.usage.completion_tokens）。
        duration_seconds: 调用耗时（秒）。
        status: "ok" / "error" / "aborted"。error 累加错误计数；aborted 表示
            客户端断连（SSE 取消 / 关页面），单独计数、不计为错误。
    """
    s = scenario or "unknown"
    m = model or "unknown"
    items: List[Tuple[str, Tuple[str, ...], float]] = [
        ("calls", (s, m), 1.0),
        ("prompt_tokens", (s, m), float(prompt_tokens or 0)),
        ("completion_tokens", (s, m), float(completion_tokens or 0)),
        ("duration_sum", (s, m), float(duration_seconds or 0.0)),
    ]
    if status == "aborted":
        items.append(("aborted", (s, m), 1.0))
    elif status != "ok":
        items.append(("errors", (s, m), 1.0))

    if not _write(items):
        for name, values, delta in items:
            _mem_bump(name, values, delta)


def record_skill_run(skill_name: str, status: str = "ok",
                     duration_seconds: float = 0.0) -> None:
    """记录一次技能执行（Tier 1 + Agentic 统一入口，跨进程聚合）。

    Args:
        skill_name: 技能名（agentic 路径带 "agentic." 前缀）。
        status: "ok" / "error"。
        duration_seconds: 执行耗时（秒）。
    """
    items: List[Tuple[str, Tuple[str, ...], float]] = [
        ("skill_runs", (skill_name or "unknown", status or "unknown"), 1.0),
        ("skill_duration_sum", (skill_name or "unknown",), float(duration_seconds or 0.0)),
    ]
    if not _write(items):
        for name, values, delta in items:
            _mem_bump(name, values, delta)


def record_skill_menu(mode: str, size: int, total: int = 0) -> None:
    """记录一次 /ask 路由的菜单构造结果（Phase D：L3 运行期指标）。

    Args:
        mode: 路由模式（full / domain / recall / domain+recall）。
        size: 实际注入 prompt 的技能数。
        total: 裁剪前的技能总数；size >= total 视为回退全量（fallback=full）。
    """
    m = mode or "unknown"
    fallback = "full" if total and size >= total else "filtered"
    items: List[Tuple[str, Tuple[str, ...], float]] = [
        ("skill_menu_calls", (m, fallback), 1.0),
        ("skill_menu_size_sum", (m,), float(size or 0)),
    ]
    if not _write(items):
        for name, values, delta in items:
            _mem_bump(name, values, delta)


def _escape(value: str) -> str:
    """转义 Prometheus 标签值中的反斜杠、双引号与换行。"""
    return (value.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n"))


def _num(value: float) -> str:
    """数值格式化：整数不带小数点，小数用定点表示（不用科学计数法）。

    Prometheus 能解析 `1e+09`，但 duration_sum 长期累加后全变成科学计数法，
    可读性差，部分第三方解析器也更挑剔。
    """
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def _render(rows: Dict[str, Dict[str, Dict[str, float]]]) -> str:
    """把聚合结果渲染为 Prometheus exposition 文本。

    同名指标的 HELP/TYPE 只输出一次，两个窗口的样本用 window 标签区分。
    """
    lines: List[str] = []
    for name, (metric, help_text, type_text, labels) in _SERIES.items():
        samples: List[str] = []
        for window in _WINDOWS:
            for dim, value in rows.get(window, {}).get(name, {}).items():
                parts = dim.split("|")
                if len(parts) != len(labels):
                    continue  # 历史脏数据，跳过而非渲染成畸形标签
                pairs = ",".join(f'{k}="{_escape(v)}"' for k, v in zip(labels, parts))
                samples.append(f'{metric}{{{pairs},window="{window}"}} {_num(value)}')
        if not samples:
            continue  # 无样本则不输出空壳 HELP/TYPE（这正是旧实现误导运维的根源）
        lines.append(f"# HELP {metric} {help_text}")
        lines.append(f"# TYPE {metric} {type_text}")
        lines.extend(samples)
    return "\n".join(lines) + "\n" if lines else ""


def _system_text() -> str:
    """附加 prometheus_client 默认采集器（python_gc / process / python_info）。

    这些是进程级指标，天然只反映本进程，与 AI 聚合计数区分开即可。
    prometheus_client 缺失时返回空串。
    """
    try:
        from prometheus_client import generate_latest
        return generate_latest().decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _sum_of(series: Dict[str, Dict[str, float]], name: str) -> int:
    """求某窗口内某系列的全量合计（跨 scenario / model 汇总）。"""
    return int(sum(series.get(name, {}).values()))


def _flatten(rows: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, int]:
    """生成前端卡片可直接展示的扁平字段（累计 + 当日）。"""
    total = rows.get("total", {})
    day = rows.get("day", {})

    def s(series: Dict[str, Dict[str, float]], name: str) -> int:
        return _sum_of(series, name)

    prompt_all, completion_all = s(total, "prompt_tokens"), s(total, "completion_tokens")
    prompt_day, completion_day = s(day, "prompt_tokens"), s(day, "completion_tokens")
    return {
        "ai_calls_total": s(total, "calls"),
        "ai_errors_total": s(total, "errors"),
        "ai_prompt_tokens_total": prompt_all,
        "ai_completion_tokens_total": completion_all,
        "ai_tokens_total": prompt_all + completion_all,  # 兼容旧契约
        "ai_skill_runs_total": s(total, "skill_runs"),
        "ai_calls_today": s(day, "calls"),
        "ai_errors_today": s(day, "errors"),
        "ai_prompt_tokens_today": prompt_day,
        "ai_completion_tokens_today": completion_day,
        "ai_tokens_today": prompt_day + completion_day,
        "ai_skill_runs_today": s(day, "skill_runs"),
    }


def get_metrics() -> Dict[str, object]:
    """返回 AI 运行指标（exposition 文本 + 扁平字段 + 数据来源）。

    Returns:
        raw: Prometheus exposition 格式文本（AI 聚合计数 + 本进程系统指标）。
        metrics_source: "redis" 表示全进程聚合；"local" 表示 Redis 不可用，
            仅为本进程兜底数据（会随命中的 worker 变化，不可作为全局依据）。
        pid: 处理本次请求的进程号（便于确认多 worker 情形）。
        其余 ai_* 字段为扁平计数，供前端卡片直接展示。
    """
    rows = _read()
    if rows is None:
        source = "error" if _redis() is not None else "local"
        rows = _mem_rows()
    else:
        source = "redis"

    result: Dict[str, object] = {
        "raw": _render(rows) + _system_text(),
        "metrics_source": source,
        "pid": os.getpid(),
    }
    result.update(_flatten(rows))
    return result
