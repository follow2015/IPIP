# -*- coding: utf-8 -*-
"""
ASGI 应用入口 — Starlette 路由 + 启停生命周期

启动方式（单进程，不加 --workers）：
    uvicorn realtime_gateway.main:app

路由：
    GET /sse/switch/{device_id}   交换机级 SSE 事件流（含断线重放）
    GET /sse/global               全局 SSE 事件流
    GET /healthz                  健康检查

鉴权：
    浏览器 EventSource 不支持自定义 Header，token 通过 ?token= 传递。
    同时兼容 Authorization: Bearer 请求头。
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from . import auth
from . import config
from . import redis_bus
from . import sse

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    root = logging.getLogger("realtime_gateway")
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        config.LOG_DIR,
    )
    os.makedirs(log_dir, exist_ok=True)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "gateway.log"),
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


_setup_logging()


class SSEAuthMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/healthz":
            await self.app(scope, receive, send)
            return

        token = auth.extract_token_from_request(scope)
        if not token:
            response = JSONResponse(
                {"error": "缺少认证令牌"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        payload = auth.verify_token(token)
        if not payload:
            response = JSONResponse(
                {"error": "无效或已过期的令牌"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        scope["state"] = {"user_id": payload["user_id"]}
        await self.app(scope, receive, send)


class _ConnectionCounter:

    def __init__(self, limit: int):
        self._limit = limit
        self._current = 0

    def acquire(self) -> bool:
        if self._current >= self._limit:
            return False
        self._current += 1
        return True

    def release(self) -> None:
        if self._current > 0:
            self._current -= 1

    @property
    def current(self) -> int:
        return self._current

    @property
    def limit(self) -> int:
        return self._limit


_connection_counter = _ConnectionCounter(config.MAX_CONNECTIONS)


async def _wrap_stream_with_counter(stream_gen, counter=None):
    if counter is None:
        counter = _connection_counter
    try:
        async for chunk in stream_gen:
            yield chunk
    finally:
        counter.release()


async def switch_events(request: Request) -> StreamingResponse:
    if not _connection_counter.acquire():
        logger.warning(
            "SSE 连接超限拒绝 device 路由 current=%d limit=%d",
            _connection_counter.current,
            _connection_counter.limit,
        )
        return JSONResponse(
            {
                "error": "too_many_connections",
                "current": _connection_counter.current,
                "limit": _connection_counter.limit,
            },
            status_code=503,
        )

    device_id = request.path_params["device_id"]
    since_seq = int(request.query_params.get("since_seq", "0"))

    return StreamingResponse(
        _wrap_stream_with_counter(sse.device_event_stream(device_id, since_seq)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def global_events(request: Request) -> StreamingResponse:
    if not _connection_counter.acquire():
        logger.warning(
            "SSE 连接超限拒绝 global 路由 current=%d limit=%d",
            _connection_counter.current,
            _connection_counter.limit,
        )
        return JSONResponse(
            {
                "error": "too_many_connections",
                "current": _connection_counter.current,
                "limit": _connection_counter.limit,
            },
            status_code=503,
        )

    user_id = request.scope.get("state", {}).get("user_id")
    return StreamingResponse(
        _wrap_stream_with_counter(sse.global_event_stream(user_id=user_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@asynccontextmanager
async def lifespan(app):
    logger.info("ASGI 推送网关启动中...")
    subscriber_task = None
    try:
        await redis_bus.get_redis()
        subscriber_task = asyncio.create_task(redis_bus.start_subscriber())
        logger.info("ASGI 推送网关已启动（Redis 已连接）")
    except Exception as exc:
        logger.warning(
            "网关 Redis 连接失败: %s，以降级模式启动（SSE 推送不可用）",
            exc,
        )
        logger.info("ASGI 推送网关已启动（降级模式）")

    yield

    logger.info("ASGI 推送网关正在关闭...")
    if subscriber_task:
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass
    logger.info("ASGI 推送网关已关闭")


routes = [
    Route("/sse/switch/{device_id:int}", switch_events),
    Route("/sse/global", global_events),
    Route("/healthz", healthz),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[Middleware(SSEAuthMiddleware)],
)
