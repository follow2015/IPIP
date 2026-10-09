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
    浏览器 EventSource 不支持自定义 Header，凭据通过 URL 传递。
    优先使用一次性 ticket（?ticket=，由 Flask POST /api/sse/ticket 签发，短效且单用），
    回退兼容长期 access token（?token= / Authorization: Bearer 头，仅限 type=access）。
    两条路径都会查询 Flask 侧撤销集合（P0#4），故已登出/已撤销的令牌无法建连。
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

from . import ai_task_stream
from . import auth
from . import config
from . import redis_bus
from . import single_replica_guard
from . import sse

logger = logging.getLogger(__name__)

_replica_state: dict | None = None



def _setup_logging() -> None:
    """配置网关日志：控制台 + RotatingFileHandler

    在模块导入后、应用启动前调用。
    uvicorn 自身的日志不受影响（由 uvicorn --log-level 控制）。
    """
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
    """SSE 端点鉴权：从请求中提取并校验 JWT token"""

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

        ticket = auth.extract_ticket(scope)
        if ticket:
            payload = await auth.verify_sse_ticket(ticket)
        else:
            token = auth.extract_token_from_request(scope)
            payload = await auth.verify_token(token) if token else None

        if not payload:
            response = JSONResponse(
                {"error": "无效或已过期的令牌"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        scope["state"] = {
            "user_id": payload["user_id"],
            "dev": payload.get("dev"),
        }
        await self.app(scope, receive, send)



class _ConnectionCounter:
    """全局 SSE 连接计数，超限拒绝新连接。

    ⚠️ M13 前提：**本计数只在单副本下代表网关上限**。uvicorn 加 `--workers N`
    就有 N 个互不可见的计数器，实际上限 = MAX_CONNECTIONS × N，且不会报错。
    扩容前必须先把计数换成跨进程实现（Redis + TTL 兜底），否则上限形同虚设。
    启动自检见 `single_replica_guard`，结果暴露在 /healthz 的 sse.single_replica。

    Args:
        limit: 配额上限。
        name: 配额名（用于 503 响应与日志里说明"被哪个配额挡住"）。
    """

    def __init__(self, limit: int, name: str = ""):
        self._limit = limit
        self._current = 0
        self.name = name

    def acquire(self) -> bool:
        """尝试占用一个连接槽。返回 True 表示允许，False 表示超限。"""
        if self._current >= self._limit:
            return False
        self._current += 1
        return True

    def release(self) -> None:
        """释放一个连接槽。"""
        if self._current > 0:
            self._current -= 1

    @property
    def current(self) -> int:
        return self._current

    @property
    def limit(self) -> int:
        return self._limit


class _MultiCounter:
    """组合配额：一条连接同时受多个计数器约束（O4）。

    AI 进度流既占全局配额（总量不失控），也占 AI 专用配额（不挤占普通事件流）。
    任一配额不足即拒绝，且**回滚已占到的** —— 否则被 AI 配额挡下的连接会白白
    吃掉一个全局槽，几次之后普通流就被"没建成功的 AI 流"挤没了。

    `last_blocked` 记录挡住本次请求的那个计数器，供 503 响应说明拒绝原因：
    运维看到 503 时要能立刻分辨"是整体满了"还是"AI 配额满了"。
    """

    def __init__(self, counters):
        self._counters = list(counters)
        self.last_blocked = None

    def acquire(self) -> bool:
        self.last_blocked = None
        taken = []
        for counter in self._counters:
            if not counter.acquire():
                self.last_blocked = counter
                for held in taken:
                    held.release()
                return False
            taken.append(counter)
        return True

    def release(self) -> None:
        for counter in self._counters:
            counter.release()

    @property
    def current(self) -> int:
        return max((c.current for c in self._counters), default=0)

    @property
    def limit(self) -> int:
        return min((c.limit for c in self._counters), default=0)


_connection_counter = _ConnectionCounter(config.MAX_CONNECTIONS, name="global")
_ai_stream_counter = _ConnectionCounter(
    config.AI_STREAM_MAX_CONNECTIONS, name="ai_task"
)
_ai_stream_slots = _MultiCounter([_connection_counter, _ai_stream_counter])


async def _wrap_stream_with_counter(stream_gen, counter=None):
    """包裹 SSE 生成器，连接结束时释放计数槽。

    counter 默认使用模块级 _connection_counter；测试可传入自定义实例。
    """
    if counter is None:
        counter = _connection_counter
    try:
        async for chunk in stream_gen:
            yield chunk
    finally:
        counter.release()


def _parse_since_seq(request: Request) -> int | None:
    """解析断线重放游标 `since_seq`（设备流与全局流共用）。

    来源优先级：
    1. 查询参数 `since_seq` —— 前端显式重连时携带（如 DeviceEventBus）。
    2. 请求头 `Last-Event-ID` —— **浏览器 EventSource 自动重连**时由浏览器
       带回（值取自我们上一条 `id:` 行）。这是 M1 闭环的关键：EventSource
       自动重连会**复用建连时的固定 URL**，查询参数里的游标不会更新；只有
       `Last-Event-ID` 会随每条新事件刷新，因此断线重放必须靠它兜底。

    语义（s12）：
    - 两者都没有 = 首次连接 → 返回 None，**不重放历史**（页面刷新不再白白收到
      最多 200 条陈旧事件）；断线重连的连接会带上游标，走既有重放路径。
    - 携带但非法（客户端误传/攻击）→ 回退 0（从头重放）而非 500（s1 修复）。
    - 显式传 0 = 从 ring 头全量补发。
    """
    raw_seq = request.query_params.get("since_seq")
    if raw_seq is None:
        raw_seq = request.headers.get("last-event-id")
    if raw_seq is None:
        return None
    try:
        return int(raw_seq)
    except (TypeError, ValueError):
        return 0


async def switch_events(request: Request) -> StreamingResponse:
    """SSE 交换机级事件流"""
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

    state = request.scope.get("state", {})
    bound_device = state.get("dev")
    if bound_device is None or str(bound_device) != str(device_id):
        _connection_counter.release()
        logger.warning(
            "SSE 设备流鉴权失败 user_id=%s bound=%s requested=%s",
            state.get("user_id"), bound_device, device_id,
        )
        return JSONResponse(
            {"error": "forbidden_device", "device_id": device_id},
            status_code=403,
        )

    since_seq = _parse_since_seq(request)

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
    """SSE 全局事件流"""
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
        _wrap_stream_with_counter(
            sse.global_event_stream(
                user_id=user_id, since_seq=_parse_since_seq(request),
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def ai_task_events(request: Request) -> StreamingResponse:
    """SSE AI 任务进度流（P0-7：自 Flask sync worker 迁入网关）。

    归属校验在流内进行（任务状态缺失 / user_id 不符 → SSE error 帧后结束），
    与 Flask 版行为对齐；`ai:admin` 跨用户排障仍走 Flask 端点。

    O4：本路由单条连接最长可占 3600s（STREAM_TIMEOUT），故除全局配额外另受
    AI 专用配额约束 —— 否则几十个长任务就能把 500 个槽全占住，交换机事件流
    一个都建不上（而它才是"必须实时"的那条）。
    """
    if not _ai_stream_slots.acquire():
        blocked = _ai_stream_slots.last_blocked
        logger.warning(
            "SSE 连接超限拒绝 ai-task 路由 quota=%s current=%d limit=%d",
            blocked.name, blocked.current, blocked.limit,
        )
        return JSONResponse(
            {
                "error": "too_many_connections",
                "quota": blocked.name,
                "current": blocked.current,
                "limit": blocked.limit,
            },
            status_code=503,
        )

    task_id = request.path_params["task_id"]
    user_id = request.scope.get("state", {}).get("user_id")
    return StreamingResponse(
        _wrap_stream_with_counter(
            ai_task_stream.ai_task_event_stream(task_id, user_id),
            counter=_ai_stream_slots,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def healthz(request: Request) -> JSONResponse:
    """健康检查。

    附带 SSE 连接计数与副本前提：只回 `{"status":"ok"}` 时，"上限 500" 到底
    是整个网关的上限还是本进程的上限，排查时只能去读源码才知道（M13）。
    """
    payload = {
        "status": "ok",
        "sse": {
            "connections": _connection_counter.current,
            "limit": _connection_counter.limit,
            "ai_stream": {
                "connections": _ai_stream_counter.current,
                "limit": _ai_stream_counter.limit,
            },
            "single_replica": _replica_state,
        },
    }
    return JSONResponse(payload)



@asynccontextmanager
async def lifespan(app):
    """应用启动：初始化 Redis 连接并启动订阅

    Redis 不可用时网关仍以降级模式启动：SSE 端点不报错但推不出事件。
    S1 修复：无论 Redis 是否可用都启动订阅任务——start_subscriber 内部是
    while 重试循环，Redis 恢复后由其自行建连订阅，无需重启进程（这是本函数
    docstring 一直承诺的行为，修复前降级分支不建任务，承诺落空）。
    """
    logger.info("ASGI 推送网关启动中...")
    degraded = False

    global _replica_state
    _replica_state = {
        "ok": single_replica_guard.check_single_replica(),
        "workers": single_replica_guard.detect_worker_count(),
    }
    try:
        await redis_bus.get_redis()
    except Exception as exc:  # noqa: BLE001 -- 网关 Redis 连接失败降级：以降级模式启动，订阅任务持续重试
        degraded = True
        logger.warning(
            "网关 Redis 连接失败: %s，以降级模式启动（SSE 推送暂不可用，订阅任务持续重试）",
            exc,
        )

    subscriber_task = asyncio.create_task(redis_bus.start_subscriber())

    if os.getenv("HEARTBEAT_ENABLED", "true").strip().lower() not in ("false", "0", "no"):
        try:
            from app.services.monitoring.heartbeat import start_heartbeat_thread

            start_heartbeat_thread(os.getenv("HEARTBEAT_SERVICE_NAME") or "gateway")
        except Exception as exc:  # noqa: BLE001 -- 网关心跳线程启动失败忽略（已标注 pragma no cover）
            logger.warning("网关心跳线程启动失败（已忽略）: %s", exc)

    logger.info(
        "ASGI 推送网关已启动（%s）",
        "降级模式" if degraded else "Redis 已连接",
    )

    yield

    logger.info("ASGI 推送网关正在关闭...")
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    await redis_bus.close_redis()
    logger.info("ASGI 推送网关已关闭")



routes = [
    Route("/sse/switch/{device_id:int}", switch_events),
    Route("/sse/global", global_events),
    Route("/sse/ai-task/{task_id}", ai_task_events),
    Route("/healthz", healthz),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[Middleware(SSEAuthMiddleware)],
)
