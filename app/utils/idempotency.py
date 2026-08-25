# -*- coding: utf-8 -*-
"""
幂等性公共组件

提供两种幂等保护机制：
1. idempotent 装饰器 — 基于 X-Idempotency-Key 请求头的 Redis 幂等键保护
   适用于：batch-import、config-change 等写操作
2. redis_lock 装饰器 — 基于 Redis SETNX 的分布式重入锁
   适用于：异步扫描、配置备份等同一资源不可并发执行的操作

使用方式：
    # 方式1：幂等键（客户端传 X-Idempotency-Key 头）
    @idempotent(prefix="import", ttl=86400)
    def batch_import():
        ...

    # 方式2：分布式锁（按资源ID加锁）
    @redis_lock(prefix="config_backup", key_param="device_id", ttl=300)
    def backup_config(device_id):
        ...
"""
import hashlib
import json
import uuid
from functools import wraps
from typing import Any, Callable, Optional, Tuple

from flask import g, request

from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_redis_client():
    try:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            return cache_manager.primary_storage.redis_client
    except Exception:
        pass
    try:
        from app.services.network_scanner_service import ScanOrchestrator
        client = ScanOrchestrator._get_redis_client()
        if client:
            return client
    except Exception:
        pass
    return None


class IdempotencyError(Exception):

    def __init__(self, message: str, code: str = "IDEMPOTENCY_CONFLICT"):
        self.message = message
        self.code = code
        super().__init__(self.message)


def idempotent(prefix: str = "idem", ttl: int = 86400,
               key_func: Optional[Callable] = None):

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            idempotency_key = None
            if key_func:
                idempotency_key = key_func(*args, **kwargs)
            else:
                idempotency_key = request.headers.get("X-Idempotency-Key")

            if not idempotency_key:
                return f(*args, **kwargs)

            redis_client = _get_redis_client()
            if not redis_client:
                logger.warning("Redis 不可用，跳过幂等性检查")
                return f(*args, **kwargs)

            current_user = getattr(g, "current_user", None)
            user_id = "anon"
            if current_user is not None:
                user_id = current_user.get("user_id", "anon") if isinstance(current_user, dict) else "anon"
            redis_key = f"ipm:idem:{prefix}:{user_id}:{idempotency_key}"

            placeholder_set = redis_client.set(redis_key, "pending", nx=True, ex=ttl)
            if not placeholder_set:
                cached = redis_client.get(redis_key)
                if cached is not None and cached != "pending":
                    try:
                        cached_response = json.loads(cached)
                        logger.info(f"幂等键命中: key={redis_key}")
                        from flask import jsonify
                        return jsonify(cached_response["body"]), cached_response["status_code"]
                    except (json.JSONDecodeError, KeyError):
                        redis_client.delete(redis_key)
                elif cached == "pending":
                    logger.warning(f"幂等键冲突（并发请求）: key={redis_key}")
                    from app.api.base import APIResponse
                    return APIResponse.error(
                        "相同操作正在执行中，请稍后再试",
                        error_code="IDEMPOTENCY_CONFLICT",
                        status_code=409,
                    )
                else:
                    redis_client.delete(redis_key)

            result = f(*args, **kwargs)

            try:
                if isinstance(result, tuple) and len(result) == 2:
                    body, status_code = result
                    if 200 <= status_code < 300:
                        body_data = body.get_json() if hasattr(body, "get_json") else {}
                        cache_value = json.dumps(
                            {"body": body_data, "status_code": status_code},
                            ensure_ascii=False,
                        )
                        redis_client.setex(redis_key, ttl, cache_value)
                        logger.debug(f"幂等键已缓存: key={redis_key}, ttl={ttl}")
                elif isinstance(result, tuple) and len(result) == 3:
                    body, status_code, headers = result
                    if 200 <= status_code < 300:
                        body_data = body.get_json() if hasattr(body, "get_json") else {}
                        cache_value = json.dumps(
                            {"body": body_data, "status_code": status_code},
                            ensure_ascii=False,
                        )
                        redis_client.setex(redis_key, ttl, cache_value)
            except Exception as e:
                logger.warning(f"缓存幂等响应失败: key={redis_key}, error={e}")

            return result

        return decorated_function

    return decorator


def redis_lock(prefix: str, key_param: Optional[str] = None,
               key_func: Optional[Callable] = None, ttl: int = 300,
               error_message: str = "操作正在执行中，请稍后再试"):

    _RELEASE_LOCK_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            lock_key_value = None
            if key_func:
                lock_key_value = key_func(*args, **kwargs)
            elif key_param:
                lock_key_value = kwargs.get(key_param)
                if lock_key_value is None:
                    lock_key_value = request.view_args.get(key_param) if request.view_args else None

            if not lock_key_value:
                logger.warning(f"无法构造锁键: prefix={prefix}, key_param={key_param}")
                return f(*args, **kwargs)

            redis_client = _get_redis_client()
            if not redis_client:
                logger.warning("Redis 不可用，跳过分布式锁检查")
                return f(*args, **kwargs)

            lock_key = f"ipm:lock:{prefix}:{lock_key_value}"

            lock_token = str(uuid.uuid4())

            acquired = redis_client.set(lock_key, lock_token, nx=True, ex=ttl)
            if not acquired:
                logger.info(f"分布式锁获取失败: key={lock_key}")
                from app.api.base import APIResponse
                return APIResponse.error(
                    error_message,
                    error_code="RESOURCE_LOCKED",
                    status_code=409,
                )

            try:
                result = f(*args, **kwargs)
                return result
            finally:
                try:
                    redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
                    logger.debug(f"分布式锁已释放: key={lock_key}")
                except Exception as e:
                    logger.warning(f"释放分布式锁失败: key={lock_key}, error={e}")

        return decorated_function

    return decorator
