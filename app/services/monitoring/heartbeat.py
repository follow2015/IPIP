# -*- coding: utf-8 -*-
"""进程心跳（T2.2 · 自监控闭环的信号来源之一）。

每个被 systemd 托管的常驻进程周期性写 Redis：

    ipip:heartbeat:<service>  →  "<unix 时间戳>"   EX <ttl>

判活语义三态，和 systemd 互补：
- systemd 只看「进程在不在」——`kill -9` 后拉起它负责；
- 心跳看「进程还转不转」——卡死在死循环/GC/死锁时进程仍在但不再写心跳，
  这一层只有心跳能抓到。

降级约定：Redis 不可用只记日志告警，**不影响业务**。heartbeat 是所有业务
路径之外的旁路逻辑，任何异常都不该冒泡到调用方。

配置（可在 app.config 或环境变量设置）：
    HEARTBEAT_ENABLED          总开关（testing 默认 False）
    HEARTBEAT_INTERVAL_SECONDS 写入周期，默认 20s
    HEARTBEAT_TTL_SECONDS      key 有效期，默认 90s；代码强制 ≥ 3×周期，
                               否则一轮网络抖动就会误判进程死亡。
"""
import os
import sys
import threading
import time

from app.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_PREFIX = "ipip:heartbeat:"


def environment() -> str:
    """当前环境隔离段（development / testing / production 或自定义前缀）。

    单独暴露给 watchdog 等消费方复用同一套隔离语义。此前 watchdog 用
    `namespace().split(":")[-2]` 反推环境段，遇到自定义 `HEARTBEAT_KEY_PREFIX`
    （切分后段数 <4）会静默落到 "production" —— 开发环境的告警冷却因此与生产
    共用，排查时表现为"冷却时间早过了却没发通知"。

    ⚠️ 刻意**不读** Flask 的 `config["ENV"]`（也不经 `_conf`）：该键由
    `FLASK_ENV` 派生，语义是"调试模式"而非部署环境名。线上实测（2026-09-11）：
    `.env` 里 `FLASK_ENV=development` 时，**请求上下文内**读到 development，
    而心跳**写入方**是无 app 上下文的守护线程（回落 `os.getenv("ENV")`）→ 同一
    进程写出 `production` 段、读回 `development` 段，健康端点的
    `services_heartbeat` 因此把**全部**服务误判为 `alive=false`（判定型信号
    永久失真）。故环境段只认显式声明，且**在有无 app 上下文下取值恒定一致**：
    `HEARTBEAT_ENV` → `ENV` 环境变量 → "production"。
    """
    custom = _conf("HEARTBEAT_KEY_PREFIX", None)
    if custom:
        return str(custom).rstrip(":")
    explicit = os.getenv("HEARTBEAT_ENV") or os.getenv("ENV")
    return (explicit or "production").strip().lower() or "production"


def namespace() -> str:
    """当前心跳命名空间（含结尾冒号）。"""
    custom = _conf("HEARTBEAT_KEY_PREFIX", None)
    if custom:
        return f"{environment()}:"
    return f"ipip:heartbeat:{environment()}:"

SERVICES = ("web", "monitor", "gateway", "celery-ai", "celery-voice")

_DEFAULT_INTERVAL = 20
_DEFAULT_TTL = 90  # ≥ 3 × interval

_started_threads = set()  # 防止热重载 / 多 worker 重复启动同一 service 的心跳线程


def _conf(name: str, default):
    """优先取 current_app.config，无 app context（独立脚本/测试）回落环境变量。"""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            value = current_app.config.get(name)
            if value is not None:
                return value
    except Exception:  # noqa: BLE001  配置读取失败不阻断心跳
        pass
    return os.getenv(name, default)


def enabled() -> bool:
    value = _conf("HEARTBEAT_ENABLED", "true")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def interval_seconds() -> int:
    try:
        return max(1, int(_conf("HEARTBEAT_INTERVAL_SECONDS", _DEFAULT_INTERVAL)))
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL


def resolve_ttl(interval: int = None) -> int:
    """实际使用的 TTL：用户值 < 3×周期 时抬到 3×周期（防止微小抖动误判死亡）。"""
    seconds = int(interval if interval is not None else interval_seconds())
    try:
        configured = int(_conf("HEARTBEAT_TTL_SECONDS", _DEFAULT_TTL))
    except (TypeError, ValueError):
        configured = _DEFAULT_TTL
    return max(configured, seconds * 3)


def heartbeat_key(service: str) -> str:
    return f"{namespace()}{service}"


def in_app_service_name(config) -> "str | None":
    """判定「应用内自动心跳」该以什么身份写入；返回 None 表示本进程不受监控。

    单独抽成函数（而非内联在 create_app 里）是因为这条规则很容易被"顺手补个
    默认值"改坏，且改坏后症状极隐蔽：心跳 key 一直有人续期、监控看起来一切
    正常，只是**再也报不出故障**。必须有测试钉住。

    规则：**只认显式声明的身份**，不提供 "web" 之类回落。
    create_app() 的调用方远不止 web 服务 —— CLI（flask db-upgrade）、运维脚本、
    以及 heartbeat_watchdog 自身都会建 app。若回落成 "web"，这些短命进程就会
    冒充 web 写心跳；watchdog 每 60s 跑一次而 TTL 只有 90s，等于持续给已经死掉的
    gunicorn 续命，第二层「活着但卡死」检测对 web 永久失效。
    """
    if not config.get("HEARTBEAT_ENABLED", False):
        return None
    name = config.get("HEARTBEAT_SERVICE_NAME")
    return str(name) if name else None


def get_redis_client():
    """委托统一入口（共享连接池）；未配置/连不上返回 None，由调用方降级。"""
    from app.utils.redis_client import get_redis_client as _get

    return _get()


def write_heartbeat(service: str, client=None, now: float = None) -> bool:
    """写一次心跳。Redis 不可用或异常时返回 False，不抛异常。"""
    if not service:
        return False
    return write_key(heartbeat_key(service), client=client, now=now)


def write_key(key: str, client=None, now: float = None) -> bool:
    """按既定 key 写一次心跳。

    与 write_heartbeat 分开的原因：key 依赖 app context（ENV 段），而心跳线程
    运行在 app context 之外，每次重算会与主线程的 ENV 判断漂移，导致 key 与
    watchdog 读取的不一致。故长期运行的线程在启动时快照 key，此处按 key 写。
    """
    redis_client = client if client is not None else get_redis_client()
    if redis_client is None:
        logger.warning("Redis 不可用，心跳未写入 %s（仅告警，不阻断业务）", key)
        return False
    stamp = f"{(time.time() if now is None else now):.3f}"
    try:
        redis_client.set(key, stamp, ex=resolve_ttl())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("心跳写入失败 %s: %s", key, exc)
        return False


def read_heartbeats(services=SERVICES, client=None, now: float = None):
    """批量读取心跳。

    Args:
        services: 需要判定的服务名
        client: 注入的 Redis 客户端（测试用 fakeredis）
        now: 注入当前时间（测试用）

    Returns:
        {service: {"checked": bool, "alive": bool, "heartbeat_ts": float|None,
                   "age_seconds": float|None}}
        `checked=False` 表示「没能读到」（Redis 不可用），**不等于进程死亡**；
        调用方必须据此跳过未读到的服务，否则 Redis 一抖就全局误告警。
    """
    redis_client = client if client is not None else get_redis_client()
    result = {
        name: {"checked": False, "alive": False, "heartbeat_ts": None, "age_seconds": None}
        for name in services
    }
    if redis_client is None:
        return result

    moment = time.time() if now is None else now
    try:
        values = redis_client.mget([heartbeat_key(name) for name in services])
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取心跳失败: %s", exc)
        return result

    for name, raw in zip(services, values):
        if raw is None:
            result[name]["checked"] = True  # 读到了：key 不在 → 心跳已过期
            continue
        try:
            stamp = float(raw)
        except (TypeError, ValueError):
            result[name]["checked"] = True
            continue
        result[name].update(
            {
                "checked": True,
                "alive": True,
                "heartbeat_ts": stamp,
                "age_seconds": round(max(0.0, moment - stamp), 1),
            }
        )
    return result


def build_heartbeat_view(services=SERVICES, client=None, now: float = None) -> dict:
    """生成对外展示/消费的心跳视图（健康检查端点与 watchdog 共用）。

    Returns:
        {"redis_available": bool, "stale_after_seconds": int,
         "services": {name: {"checked","alive","stale","age_seconds",
                             "heartbeat_at(str|None)"}}}
        `stale` 表示「有心跳但已明显滞后」（>3 倍周期）——进程没死但很可能
        卡在长任务/GC，是故障的前兆，值得先于彻底失联就告警。
    """
    statuses = read_heartbeats(services, client=client, now=now)
    interval = interval_seconds()
    stale_after = max(interval * 3, 60)

    services_view = {}
    for name, state in statuses.items():
        age = state["age_seconds"]
        services_view[name] = {
            "checked": state["checked"],
            "alive": state["alive"],
            "stale": bool(age is not None and age > stale_after),
            "age_seconds": age,
            "heartbeat_at": _iso(state["heartbeat_ts"]),
        }
    return {
        "redis_available": bool(statuses) and all(s["checked"] for s in statuses.values()),
        "stale_after_seconds": stale_after,
        "services": services_view,
    }


def _iso(stamp):
    if stamp is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def start_heartbeat_thread(service: str, client=None, interval: int = None):
    """启动 daemon 心跳线程并返回 Thread；未启用或已启动过返回 None。

    幂等：同一 service 重复调用不会起第二个线程（Flask `--reload` 与
    gunicorn 多 worker 场景下都可能重复触发）。
    """
    if not service or not enabled():
        return None
    if service in _started_threads:
        return None
    seconds = int(interval if interval is not None else interval_seconds())
    _started_threads.add(service)
    key = heartbeat_key(service)  # 启动时快照：线程内无 app context，见 write_key

    def _loop():
        while True:
            write_key(key, client=client)
            time.sleep(seconds)

    thread = threading.Thread(target=_loop, name=f"heartbeat-{service}", daemon=True)
    thread.start()
    logger.info(
        "心跳已启动: service=%s interval=%ss ttl=%ss", service, seconds, resolve_ttl(seconds)
    )
    return thread


def resolve_celery_service_name(argv=None) -> str:
    """Celery worker 的服务名：与 deploy/systemd 的 ipip-celery-{ai,voice} 对齐。

    优先 `IPIP_SERVICE_NAME`；未设置时从命令行队列推导
    （`-Q ai` → `celery-ai`，`-Q ai,voice` → 取第一个）。

    推导不出来时返回 None（调用方据此不起心跳），**不回落到 "celery"**：
    SERVICES 里没有这个名字，写进去就是一个**没人判定的 key** —— 表面上
    "worker 有心跳"，实际上它失联永远不会被发现，比没有心跳更糟（虚假安全感）。
    """
    env_name = os.getenv("IPIP_SERVICE_NAME")
    if env_name:
        return env_name
    args = sys.argv if argv is None else argv
    for index, arg in enumerate(args):
        if arg in ("-Q", "--queues") and index + 1 < len(args):
            queue = args[index + 1].split(",")[0].strip()
            if queue:
                return f"celery-{queue}"
        if arg.startswith("--queues="):
            queue = arg.split("=", 1)[1].split(",")[0].strip()
            if queue:
                return f"celery-{queue}"
    logger.error(
        "无法推导 celery 服务名（命令行无 -Q/--queues，且未设 IPIP_SERVICE_NAME）；"
        "本次不写心跳，请检查 ipip-celery-*.service 的启动参数"
    )
    return None
