# -*- coding: utf-8 -*-
"""监控轮次节奏指标：跨进程聚合（Redis）+ 进程内兜底，输出 Prometheus exposition。

**为什么需要**：采样节奏会被"多实例并发"放大。锁只保证互斥、不保证限速——
抢不到锁的实例照样按自己的 `interval` 起轮，于是聚合频率 = `interval ÷ 实例数`。
配置值看着完全正常（`MONITOR_INTERVAL_SNMP=60`），库里却按 ≈19 s 落一行。
旧路径只能事后查库才发现（见 `code_review/采样节奏真值核查-20260921.md`）。

本模块把两个信号变成**可抓取**指标，让"放大"当场可见：

- `ipip_monitor_rounds_per_minute` —— 实测轮次/分钟（明显高于配置值 ⇒ 有放大）
- `ipip_monitor_round_same_second_total` —— 同一秒内完成的额外轮次
- `ipip_monitor_round_skipped_total` —— 被**最小间隔闸门**拦下的轮次（限速器生效的
  直接证据；没有它，"限速在起作用"与"采集停摆了"读数一样低）
- 附带 `writers` / `min_gap_seconds` / `too_fast_total` 三个判据（与 DB 侧同源）

存储：与 `app/services/ai/metrics.py` 同一范式——权威数据在 Redis（多 worker /
celery / 多机共享），进程内有界容器仅作 Redis 不可用时的兜底。

Redis 结构（`loop` 为 snmp / bmc / zabbix / ping）：

    monitor:rounds:ts:<loop>       LIST   "<unix ts>|<pid>"，LPUSH + LTRIM 到 _KEEP 条，带 TTL
    monitor:rounds:total:<loop>    INCR   累计轮次（counter 语义，不设 TTL）
    monitor:rounds:skipped:<loop>  INCR   累计被闸门拦下的轮次（同上）

⚠️ 口径：**被拦的尝试不写 `ts` 列表**。它没有真的跑，若也进节奏序列，限速器会把
自己的拦截面当成节拍，反而把"轮次/分钟"读回放大值——那就把修复读成了故障。

降级约定：Redis 不可用只记日志告警，**不影响监控业务**。本模块是所有监控路径
之外的旁路逻辑，任何异常都不该冒泡到调用方。
"""
import threading
import time
from typing import Dict, List, Optional, Tuple

from app.utils.logging import get_logger

logger = get_logger(__name__)

_NS = "monitor:rounds"

_WINDOW_SECONDS = 300

_KEEP = 400

_TTL_SECONDS = 900

_MIN_LOOP_INTERVAL = 5

_mem: Dict[str, List[Tuple[float, str]]] = {}
_mem_lock = threading.Lock()


def _now() -> float:
    """当前 Unix 时间戳（测试可 monkeypatch 以获得确定性时钟）。"""
    return time.time()


def _pid() -> int:
    """当前进程号（测试可 monkeypatch 以模拟多 worker）。"""
    import os
    return os.getpid()


def _redis():
    """返回全局 Redis 单例，不可用（未配置 / 连接失败）时返回 None。"""
    try:
        from app.utils.redis_client import get_redis_client
        return get_redis_client()
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor.round_metrics.redis_unavailable %s", e)
        return None


def _ts_key(loop_name: str) -> str:
    return f"{_NS}:ts:{loop_name}"


def _total_key(loop_name: str) -> str:
    return f"{_NS}:total:{loop_name}"


def _skipped_key(loop_name: str) -> str:
    return f"{_NS}:skipped:{loop_name}"


def _mem_record(loop_name: str) -> None:
    """进程内兜底：记录一条时间戳并裁剪到 _KEEP。"""
    with _mem_lock:
        store = _mem.setdefault(loop_name, [])
        store.append((_now(), str(_pid())))
        if len(store) > _KEEP:
            del store[: len(store) - _KEEP]


def record_round(loop_name: str) -> bool:
    """记录一轮监控已完成（Redis 优先，失败回落进程内兜底）。

    Returns:
        是否成功写入 Redis。False 表示已回落到进程内视角。
    """
    name = (loop_name or "").strip() or "unknown"
    r = _redis()
    if r is None:
        _mem_record(name)
        return False
    try:
        ts_key = _ts_key(name)
        pipe = r.pipeline()
        pipe.lpush(ts_key, "%.3f|%s" % (_now(), _pid()))
        pipe.ltrim(ts_key, 0, _KEEP - 1)
        pipe.expire(ts_key, _TTL_SECONDS)
        pipe.incr(_total_key(name))
        pipe.execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor.round_metrics.redis_write_failed %s", e)
        _mem_record(name)
        return False


def record_skip(loop_name: str) -> bool:
    """记录一次「被最小间隔闸门拦下」的尝试（不写时间戳）。

    与 `record_round` 的关键区别：**不往节奏序列里写时间戳**。被拦的轮次没有
    真的跑，进了序列就等于让限速器把自己的拦截当成节拍 —— 修复后指标反而更像
    修复前（详见模块 docstring 的口径说明）。这里只累加计数。

    它是「闸门在工作」与「采集停摆」的分界证据：轮次/分钟偏低时，
    `skipped_total` 在涨 ⇒ 是限速生效（还有实例在争）；不涨 ⇒ 才要查采集是否死了。

    Returns:
        是否成功写入 Redis。失败只记日志，不抛异常（旁路逻辑）。
    """
    name = (loop_name or "").strip() or "unknown"
    r = _redis()
    if r is None:
        return False
    try:
        r.incr(_skipped_key(name))
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor.round_metrics.redis_skip_write_failed %s", e)
        return False


def _iter_loops(r) -> List[str]:
    """扫描出实际有轮次记录的 loop（不硬编码协议清单）。

    刻意**不**输出"从未有过轮次"的 loop：无样本的空壳样本会被读成
    "系统正常、节奏为零"，正是 `app/services/ai/metrics.py` 已经踩过的坑。
    """
    prefix = f"{_NS}:ts:"
    names = []
    try:
        for key in r.scan_iter(match=f"{prefix}*", count=100):
            k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            if k.startswith(prefix):
                names.append(k[len(prefix):])
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor.round_metrics.scan_failed %s", e)
    return sorted(set(names))


def _aggregate(entries, raw_total, now: float, raw_skipped=None) -> Dict[str, object]:
    """把时间戳列表聚合成节奏指标。

    速率口径用 **相邻间隔数 ÷ 跨度**（即 `(n-1)/span`）：n 个时刻之间只有 n-1 个
    间隔，用 `n/span` 会把"每 60 s 一轮"算成 1.2 轮/分钟。样本 < 2 时不做外推。
    """
    items: List[Tuple[float, str]] = []
    for e in entries or []:
        s = e.decode("utf-8") if isinstance(e, bytes) else str(e)
        ts_s, _, pid_s = s.partition("|")
        try:
            items.append((float(ts_s), pid_s or "?"))
        except (TypeError, ValueError):
            continue  # 历史脏条目，跳过而非让整个快照失败
    items.sort()

    win = [(ts, pid) for ts, pid in items if 0 <= now - ts <= _WINDOW_SECONDS]

    rounds_per_minute = 0.0
    min_gap = 0.0
    too_fast = 0
    if len(win) >= 2:
        span = max(win[-1][0] - win[0][0], 1.0)
        rounds_per_minute = (len(win) - 1) / span * 60.0
        gaps = [win[i + 1][0] - win[i][0] for i in range(len(win) - 1)]
        min_gap = min(gaps)
        too_fast = sum(1 for g in gaps if g < _MIN_LOOP_INTERVAL)

    buckets: Dict[int, int] = {}
    for ts, _ in win:
        buckets[int(ts)] = buckets.get(int(ts), 0) + 1
    same_second = sum(c - 1 for c in buckets.values() if c > 1)

    try:
        total = int(float(raw_total or 0))
    except (TypeError, ValueError):
        total = 0

    try:
        skipped = int(float(raw_skipped or 0))
    except (TypeError, ValueError):
        skipped = 0

    return {
        "rounds_total": total,
        "skipped_total": skipped,
        "rounds_per_minute": round(rounds_per_minute, 3),
        "writers": len({pid for _, pid in win}),
        "min_gap_seconds": round(min_gap, 3),
        "too_fast_total": too_fast,
        "same_second_total": same_second,
        "samples": len(win),
    }


def _read(r) -> Dict[str, Dict[str, object]]:
    """从 Redis 读出全部 loop 的聚合结果（跨进程视角）。"""
    loops = _iter_loops(r)
    if not loops:
        return {}
    now = _now()
    pipe = r.pipeline()
    for name in loops:
        pipe.lrange(_ts_key(name), 0, _KEEP - 1)
        pipe.get(_total_key(name))
        pipe.get(_skipped_key(name))
    res = pipe.execute()

    out: Dict[str, Dict[str, object]] = {}
    for i, name in enumerate(loops):
        out[name] = _aggregate(
            res[3 * i], res[3 * i + 1], now, res[3 * i + 2]
        )
    return out


def _mem_rows() -> Dict[str, Dict[str, object]]:
    """兜底路径：进程内数据（只反映本进程，不代表全局）。"""
    now = _now()
    with _mem_lock:
        snapshot = {name: list(store) for name, store in _mem.items()}
    return {name: _aggregate(store, len(store), now) for name, store in snapshot.items()}


_SERIES = (
    ("ipip_monitor_rounds_total", "监控轮次累计数（跨进程聚合）", "counter", "rounds_total", False),
    ("ipip_monitor_round_skipped_total",
     "累计被最小间隔闸门拦下的轮次（在涨 ⇒ 限速器生效且仍有实例在争配额）",
     "counter", "skipped_total", False),
    ("ipip_monitor_round_samples", "近 5 分钟窗口内的轮次样本数", "gauge", "samples", False),
    ("ipip_monitor_rounds_per_minute",
     "近 5 分钟实测轮次/分钟（明显高于配置值 ⇒ 存在多写者放大）", "gauge", "rounds_per_minute", True),
    ("ipip_monitor_round_writers",
     "近 5 分钟完成轮次的不同进程数（>1 ⇒ 同一 loop 有多实例并发）", "gauge", "writers", True),
    ("ipip_monitor_round_min_gap_seconds",
     "近 5 分钟相邻轮次最小间隔（小于最小循环周期 ⇒ 单循环不可能）", "gauge", "min_gap_seconds", True),
    ("ipip_monitor_round_too_fast_total",
     "近 5 分钟相邻间隔小于最小循环周期的次数", "gauge", "too_fast_total", True),
    ("ipip_monitor_round_same_second_total",
     "近 5 分钟同一秒内完成的额外轮次（DB 侧表现为同秒两份快照）", "gauge", "same_second_total", True),
)


def _num(value) -> str:
    """数值格式化：整数不带小数点，小数用定点表示（避免科学计数法）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "0"
    if f.is_integer():
        return str(int(f))
    return f"{f:.6f}".rstrip("0").rstrip(".") or "0"


def _render(rows: Dict[str, Dict[str, object]]) -> str:
    """渲染 Prometheus exposition 文本；无任何样本时返回空串。"""
    if not rows:
        return ""
    lines: List[str] = []
    for metric, help_text, type_text, field, needs_two in _SERIES:
        samples = []
        for loop_name in sorted(rows):
            row = rows[loop_name]
            if needs_two and int(row.get("samples") or 0) < 2:
                continue  # 样本不足，不做外推（避免 1 条读成 60 轮/分钟）
            samples.append(f'{metric}{{loop="{loop_name}"}} {_num(row.get(field))}')
        if not samples:
            continue
        lines.append(f"# HELP {metric} {help_text}")
        lines.append(f"# TYPE {metric} {type_text}")
        lines.extend(samples)
    return "\n".join(lines) + "\n" if lines else ""


def snapshot() -> Dict[str, object]:
    """返回监控轮次指标（exposition 文本 + 结构化字段 + 数据来源）。

    Returns:
        raw: Prometheus exposition 文本（无样本时为空串）。
        metrics_source: "redis" 表示跨进程聚合；"local" 表示 Redis 不可用，
            仅本进程数据（不可作全局依据）；"error" 表示 Redis 可达但读取失败。
        pid: 处理本次调用的进程号。
        loops: {loop: {rounds_total, skipped_total, rounds_per_minute, writers,
                       min_gap_seconds, too_fast_total, same_second_total, samples}}
    """
    r = _redis()
    rows: Optional[Dict[str, Dict[str, object]]] = None
    if r is not None:
        try:
            rows = _read(r)
        except Exception as e:  # noqa: BLE001
            logger.warning("monitor.round_metrics.redis_read_failed %s", e)
            rows = None

    if rows is None:
        source = "error" if r is not None else "local"
        rows = _mem_rows()
    else:
        source = "redis"

    return {
        "raw": _render(rows),
        "metrics_source": source,
        "pid": _pid(),
        "loops": rows,
    }
