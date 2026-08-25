# -*- coding: utf-8 -*-
"""
网关环境变量配置

所有配置通过环境变量注入，与 Flask 主应用共享 REDIS_HOST / REDIS_PORT / JWT_SECRET_KEY。
REDIS_URL 优先从环境变量读取，未设置时从 REDIS_HOST / REDIS_PORT / REDIS_PASSWORD / REDIS_DB 组装，
与 Flask 主应用 config.py 的 REDIS_URL property 逻辑保持一致。
"""
import os

try:
    from dotenv import load_dotenv
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass


def _build_redis_url() -> str:
    explicit = os.environ.get("REDIS_URL")
    if explicit:
        return explicit

    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    db = os.environ.get("REDIS_DB", "0")
    password = os.environ.get("REDIS_PASSWORD", "")

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


REDIS_URL: str = _build_redis_url()

JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY", "")
JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")

KEEPALIVE_INTERVAL: int = int(os.environ.get("SSE_KEEPALIVE_INTERVAL", "25"))
CLIENT_QUEUE_SIZE: int = int(os.environ.get("SSE_CLIENT_QUEUE_SIZE", "64"))
MAX_IDLE_SECONDS: int = int(os.environ.get("SSE_MAX_IDLE_SECONDS", "300"))
MAX_CONNECTIONS: int = int(os.environ.get("SSE_MAX_CONNECTIONS", "500"))

RING_BUFFER_SIZE: int = int(os.environ.get("SSE_RING_BUFFER_SIZE", "200"))

GLOBAL_CHANNEL: str = "events:global"

LOG_LEVEL: str = os.environ.get("GATEWAY_LOG_LEVEL", "INFO")
LOG_DIR: str = os.environ.get("GATEWAY_LOG_DIR", "logs")
LOG_MAX_BYTES: int = 10 * 1024 * 1024
LOG_BACKUP_COUNT: int = 5
