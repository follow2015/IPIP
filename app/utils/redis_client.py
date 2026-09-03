# -*- coding: utf-8 -*-
"""Redis 客户端统一入口（V2 收敛）。

背景：switch_events（SSE 事件）、monitor_worker（监控锁/缓存）、
ai._runtime（AI 缓存/审计）三处各自实现「读 REDIS_URL → redis.from_url →
模块级单例」的连接逻辑，配置解析与连接参数各自漂移（monitor_worker 甚至
每次调用新建连接池）。本模块提供唯一公开入口，让所有调用方共享同一连接池。

使用约定：
- 调用方拿到的客户端可能为 None（Redis 未配置/暂不可用），必须自行降级；
  降级策略属于各业务域语义（事件静默丢弃 / 直查 DB / 无互斥），本模块不代管。
- monitor_worker._redis_client(app) 不走本入口：其 app.config["REDIS_URL"]
  是 property 描述符对象（from_object 拷贝配置类所致），拿不到 URL 字符串，
  维持 host/port fallback；连接复用由 dynamic_config 的 per-app 缓存兜住。
"""
import threading

from app.utils.logging import get_logger

logger = get_logger(__name__)

_client = None  # 全局共享单例
_init_lock = threading.Lock()  # 双检锁：防多线程并发初始化
_unavailable_logged = False  # REDIS_URL 未配置只记一次 ERROR，后续 DEBUG 防刷屏


def get_redis_client():
    """返回全局共享的 Redis 客户端单例（惰性 + 双检锁）。

    行为与原 switch_events._get_redis 一致：
    - REDIS_URL 未配置：返回 None（仅首次记 ERROR，之后 DEBUG 防刷屏）
    - 构造成功但 ping 失败：返回 None（不缓存失败，下次调用自动重试；
      每次重试记 warning，便于在 Redis 故障期间保持可观测）
    - 成功：返回带健康检查参数的共享客户端（decode_responses=True、
      socket 超时、keepalive、30s 健康检查）

    Returns:
        redis.Redis 或 None
    """
    global _client, _unavailable_logged
    if _client is not None:
        return _client
    with _init_lock:
        if _client is not None:
            return _client
        try:
            from config import get_config
            _config = get_config()
            config_instance = _config() if isinstance(_config, type) else _config
            redis_url = config_instance.REDIS_URL
        except Exception:  # noqa: BLE001
            redis_url = None
        if not redis_url:
            if not _unavailable_logged:
                logger.error("REDIS_URL 未配置，实时事件推送不可用（事件将被静默丢弃）")
                _unavailable_logged = True
            else:
                logger.debug("REDIS_URL 未配置，实时事件推送不可用")
            return None
        try:
            import redis as _redis_lib
            _client = _redis_lib.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                socket_keepalive=True,
            )
            _client.ping()
            logger.info("SSE Redis Pub/Sub 已启用: %s", redis_url)
            return _client
        except Exception as exc:  # noqa: BLE001
            logger.warning("REDIS_URL 已配置但连接失败，事件将被静默丢弃: %s", exc)
            return None
