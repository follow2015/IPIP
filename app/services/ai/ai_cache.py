# -*- coding: utf-8 -*-
"""AI 响应缓存，避免重复 prompt 烧 token。"""
import hashlib
import json
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)


class AIResponseCache:
    """基于 Redis 的 AI 响应缓存（可选，无 redis 时静默降级）。"""

    PREFIX = "ai:resp:"

    def __init__(self, redis_client=None):
        self.redis = redis_client

    @staticmethod
    def make_key(user_id: int, *parts) -> str:
        """构造缓存 key（**必须**包含 user_id 维度）。

        B5 修复：原实现仅对 prompt 内容哈希，不含用户维度。若某能力返回用户
        私有数据（如"我的设备列表"、按权限过滤的资源），A 用户的缓存结果会被
        B 用户命中，构成**跨用户数据泄露**。故将 user_id 设为首个必填位置参数，
        使调用方在签名层面无法遗漏（而非依赖约定）。

        Args:
            user_id: 用户 ID，用于隔离不同用户的缓存空间。
            *parts: 参与哈希的其余内容（场景标识、prompt、参数等）。

        Returns:
            缓存 key。
        """
        raw = json.dumps([user_id, *parts], sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"{AIResponseCache.PREFIX}{digest}"

    def get(self, key: str) -> Optional[str]:
        if not self.redis:
            return None
        try:
            val = self.redis.get(key)
            return val.decode("utf-8") if isinstance(val, bytes) else val
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.cache.get_failed %s", e)
            return None

    def set(self, key: str, value: str, ttl: int = 600) -> None:
        if not self.redis:
            return
        try:
            self.redis.setex(key, ttl, value)
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.cache.set_failed %s", e)
