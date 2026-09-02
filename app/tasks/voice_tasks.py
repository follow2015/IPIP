# -*- coding: utf-8 -*-
"""语音呼叫 Celery task。

与 AI task 共用 ContextTask 基类，但用独立 queue "voice" 隔离
（由独立 -Q voice worker 消费，否则本 task 无人消费）。
"""
import time
from datetime import datetime, timezone

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery
from app.utils.logging import get_logger
from app.services.channels.voice_providers.errors import (
    TransientVoiceError,
    PermanentVoiceError,
)

logger = get_logger(__name__)


def _get_voice_redis():
    """语音 task 用 Redis 客户端；不可用时返回 None。

    项目无 `extensions.redis_client`，Redis 统一经 switch_events._get_redis
    （与 AI 模块 task_state/task_idempotency/circuit_breaker 同一惯例）。
    定义为模块级函数，便于测试 patch。
    """
    from app.services.switch_events import _get_redis

    try:
        return _get_redis()
    except Exception:
        logger.warning("语音 task Redis 客户端获取失败", exc_info=True)
        return None


@celery.task(bind=True, queue="voice",
             autoretry_for=(TransientVoiceError, SoftTimeLimitExceeded),
             retry_backoff=60, retry_backoff_max=300,
             retry_jitter=True, max_retries=1,
             soft_time_limit=45)
def send_voice_call(self, receipt_id: int) -> dict:
    """发起语音呼叫并等待回调确认窗口。

    流程：
    1. 幂等短路（回调已写终态，含 answered）
    2. 校验被叫号码（无号码为永久错误，不重试）
    3. 被叫号码流控预算校验
    4. 调 provider.make_call 发起呼叫
    5. Redis 反向索引 call_id → receipt_id
    6. 短轮询 channel_status 等待回调
    7. 超时抛 TransientVoiceError 触发重试

    ⚠️ soft_time_limit(45s) 必须大于轮询窗口。call_timeout 硬上限 30
    （= 45 - make_call 余量），否则轮询循环先撞软超时。
    SoftTimeLimitExceeded 已在 autoretry_for 中，防撞限时任务死亡且状态卡在 calling。
    """
    from app.models.notification import NotificationReceipt
    from app.models.user import User
    from app.services.channels.voice import get_voice_config_from_db
    from app.services.channels.voice_providers import get_voice_provider
    from extensions import db
    from sqlalchemy.orm.attributes import flag_modified

    receipt = NotificationReceipt.query.get(receipt_id)
    if not receipt:
        return {"skipped": "receipt_not_found"}

    status = dict(receipt.channel_status or {})

    if status.get("voice") in ("acked", "answered", "delivered", "no_answer",
                               "failed:cancelled"):
        return {"skipped": f"already_{status['voice']}"}

    callee_user = User.query.get(receipt.user_id)
    if not callee_user or not callee_user.contact_phone:
        status["voice"] = "failed:permanent:no_phone"
        receipt.channel_status = status
        flag_modified(receipt, "channel_status")
        db.session.commit()
        return {"status": "permanent_error", "error": "user has no contact_phone"}

    config = get_voice_config_from_db()
    provider_name = config.get("provider", "aliyun")
    provider = get_voice_provider(provider_name)
    redis_client = _get_voice_redis()

    if not _check_and_consume_budget(redis_client, callee_user.contact_phone, config):
        status["voice"] = "failed:throttled:budget_exhausted"
        receipt.channel_status = status
        flag_modified(receipt, "channel_status")
        db.session.commit()
        logger.error("被叫语音呼叫预算已满，本次放弃: receipt_id=%s", receipt_id)
        return {"status": "budget_exhausted"}

    status["voice"] = "calling"
    _t0 = time.perf_counter()
    try:
        call_id = provider.make_call(
            callee=callee_user.contact_phone,
            receipt_id=receipt_id,
            config=config,
            template_vars=_build_template_vars(receipt),
        )
        _duration_ms = int((time.perf_counter() - _t0) * 1000)
        logger.info("语音呼叫已发起: receipt_id=%s call_id=%s provider=%s duration_ms=%d",
                    receipt_id, call_id, provider_name, _duration_ms)
    except PermanentVoiceError as exc:
        status["voice"] = f"failed:permanent:{type(exc).__name__}"
        receipt.channel_status = status
        flag_modified(receipt, "channel_status")
        db.session.commit()
        logger.error("语音呼叫永久失败 receipt_id=%s duration_ms=%d: %s",
                     receipt_id, int((time.perf_counter() - _t0) * 1000), exc)
        return {"status": "permanent_error", "error": str(exc)}
    except TransientVoiceError as exc:
        logger.warning("语音呼叫瞬态失败 receipt_id=%s duration_ms=%d: %s",
                       receipt_id, int((time.perf_counter() - _t0) * 1000), exc)
        raise  # 交由 Celery autoretry
    except Exception as exc:
        status["voice"] = f"failed:{type(exc).__name__}"
        receipt.channel_status = status
        flag_modified(receipt, "channel_status")
        db.session.commit()
        logger.error("语音呼叫未知失败 receipt_id=%s duration_ms=%d: %s",
                     receipt_id, int((time.perf_counter() - _t0) * 1000), exc)
        raise TransientVoiceError(f"make_call failed: {exc}") from exc

    status["voice_call_id"] = call_id
    receipt.channel_status = status
    flag_modified(receipt, "channel_status")
    db.session.commit()

    if redis_client:
        redis_client.setex(f"voice:call:{call_id}", 600, str(receipt_id))

    call_timeout = min(int(config.get("call_timeout", 30)), 30)
    poll_interval = 5
    poll_count = call_timeout // poll_interval

    for _ in range(poll_count):
        time.sleep(poll_interval)
        db.session.expire(receipt)  # 强制重读
        status_now = dict(receipt.channel_status or {})
        current = status_now.get("voice")
        if current in ("acked", "answered", "delivered"):
            return {"result": current, "call_id": call_id}
        if current == "no_answer" or (current or "").startswith("failed:"):
            if status_now.get("voice_retryable"):
                raise TransientVoiceError(f"call ended: {current}")
            logger.info("语音呼叫终态不重试: receipt_id=%s status=%s", receipt_id, current)
            return {"result": current, "call_id": call_id, "retried": False}

    raise TransientVoiceError("callback_timeout")


@celery.task(queue="voice")
def cancel_voice_retry_task(task_id: str) -> dict:
    """取消待重试的语音 task（异步执行，不占用回调 700ms 响应窗口）。"""
    try:
        celery.control.revoke(task_id, terminate=False)
        return {"revoked": task_id}
    except Exception as exc:
        logger.warning("取消语音重试 task 失败 task_id=%s: %s", task_id, exc)
        return {"revoked": None, "error": str(exc)}


def _build_template_vars(receipt) -> dict:
    """构造语音模板变量（告警标题/级别）。字段缺失时返回空 dict。

    注意：Notification 模型没有 level 字段，级别取 severity。
    """
    try:
        notif = receipt.notification
        return {
            "title": (getattr(notif, "title", "") or "")[:30],
            "level": getattr(notif, "severity", "") or "",
        }
    except Exception:  # 取不到变量不应阻断呼叫（模板无变量时本就不需要）
        return {}


_VOICE_BUDGET_WINDOWS: dict[str, list[tuple[int, int]]] = {
    "aliyun": [(60, 1), (3600, 4), (86400, 18)],
    "tencent": [(30, 1), (600, 1), (86400, 2)],
}

_VOICE_NIGHT_BUDGET: dict[str, int | None] = {
    "aliyun": None,
    "tencent": 1,
}


def _night_window_id(now_ts: int) -> str | None:
    """返回当前时刻所属的夜间窗口 ID（22:00-次日 08:00），白天返回 None。

    22:00 之后启动的夜间窗口归属当天；08:00 之前仍属于**前一天** 22:00 启动的窗口。

    时区必须用应用时区（APP_TIMEZONE，默认 Asia/Shanghai）：腾讯云夜间限呼
    按北京时间执行，若 worker 跑在 UTC 容器，窗口会整体错位 8 小时——
    北京夜间反而无限流（超厂商限制烧预算），北京白天被误限 1 条/天。
    与 notification_service._in_quiet_hours 同一惯例。
    """
    import datetime as _dt

    try:
        from config import get_config
        tz_name = getattr(get_config(), "APP_TIMEZONE", "Asia/Shanghai")
    except Exception:
        tz_name = "Asia/Shanghai"

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        from datetime import timedelta, timezone
        tz = timezone(timedelta(hours=8))

    now = _dt.datetime.fromtimestamp(now_ts, tz=tz)
    if now.hour >= 22:
        return now.strftime("%Y%m%d")
    if now.hour < 8:
        return (now - _dt.timedelta(days=1)).strftime("%Y%m%d")
    return None


def _check_and_consume_budget(redis_client, phone: str, config: dict) -> bool:
    """被叫号码呼叫预算，按 provider 分档（全局单一预算在腾讯云侧必然超限）。

    窗口按「固定分片」近似（而非严格滑动窗口），告警低频场景下足够。
    Redis 不可用时放行（不做无谓阻断，由厂商侧流控兜底）。
    """
    if not redis_client:
        return True

    provider = (config.get("provider") or "aliyun").strip().lower()
    windows = list(_VOICE_BUDGET_WINDOWS.get(provider, _VOICE_BUDGET_WINDOWS["aliyun"]))

    if provider == "aliyun":
        overrides = {}
        if config.get("voice_budget_hour"):
            overrides[3600] = int(config["voice_budget_hour"])
        if config.get("voice_budget_day"):
            overrides[86400] = int(config["voice_budget_day"])
        if overrides:
            windows = [(span, overrides.get(span, budget)) for span, budget in windows]
    elif config.get("voice_budget_hour") or config.get("voice_budget_day"):
        logger.warning(
            "voice_budget_hour/day 仅对 aliyun 生效，当前 provider=%s 将忽略该覆盖"
            "（腾讯云夜间 1 条为厂商硬限制，不可调）", provider,
        )

    now = int(time.time())

    checks: list[tuple[str, int, int]] = [
        (f"voice:budget:{provider}:{span}:{phone}:{now // span}", budget, span * 2)
        for span, budget in windows
    ]

    night_budget = _VOICE_NIGHT_BUDGET.get(provider)
    if night_budget is not None:
        night_id = _night_window_id(now)
        if night_id:
            checks.append(
                (f"voice:budget:{provider}:night:{phone}:{night_id}", night_budget, 14 * 3600)
            )

    try:
        pipe = redis_client.pipeline()
        for key, _budget, ttl in checks:
            pipe.incr(key)
            pipe.expire(key, ttl)
        results = pipe.execute()
        for idx, (_key, budget, _ttl) in enumerate(checks):
            if results[idx * 2] > budget:
                return False
        return True
    except Exception:
        logger.warning("语音预算 Redis 不可用，放行本次呼叫", exc_info=True)
        return True
