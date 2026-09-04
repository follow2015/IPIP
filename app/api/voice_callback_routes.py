# -*- coding: utf-8 -*-
"""语音通知服务商回调端点（免登鉴权）。

签名校验 + IP 白名单 + 幂等 + 取消待重试 task。

⚠️ 阿里云 HTTP 批量推送的响应超时为 700ms，故同步路径只做 Redis 幂等 +
定位 + 单次 commit，revoke 一律异步化。
"""
import ipaddress
import os
from datetime import datetime, timezone

from flask import Blueprint, request, abort, jsonify, current_app
from sqlalchemy.orm.attributes import flag_modified

from app.services.channels.voice_providers.terminal_status import VOICE_RESULT_EVENTS
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Blueprint("voice_callback", __name__, url_prefix="/api/notification/voice")

_DEFAULT_PROVIDER_IP_WHITELIST = {
    "aliyun": [],
    "tencent": [],
}


def _get_voice_redis():
    """语音回调用 Redis 客户端；不可用时返回 None。

    项目无 `extensions.redis_client`，Redis 统一经 switch_events._get_redis。
    定义为模块级函数（而非函数内 import），便于测试 patch 与统一降级。
    """
    from app.services.switch_events import _get_redis

    try:
        return _get_redis()
    except Exception:
        logger.warning("语音回调 Redis 客户端获取失败", exc_info=True)
        return None


def _load_provider_ip_whitelist() -> dict:
    """从 app.config 或环境变量加载 IP 白名单，回退到默认值。"""
    configured = current_app.config.get("VOICE_PROVIDER_IP_WHITELIST")
    if configured:
        return {k: [ipaddress.ip_network(n) for n in v] for k, v in configured.items()}

    result = {}
    for provider, default_nets in _DEFAULT_PROVIDER_IP_WHITELIST.items():
        env_key = f"VOICE_{provider.upper()}_IP_WHITELIST"
        env_val = os.environ.get(env_key)
        nets_str = env_val.split(",") if env_val else default_nets
        result[provider] = [ipaddress.ip_network(n.strip()) for n in nets_str if n.strip()]
    return result


def _is_provider_ip(ip_str: str, provider: str) -> bool:
    """检查请求 IP 是否在服务商白名单内。

    白名单为空时**放行**（默认关闭 IP 校验）——空列表若按"不在名单内"处理会
    100% 拒收，与本意相反。安全由 call_id 幂等 + out_id/callid 关联 +
    Redis 反向索引三道防线保证。
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        whitelist = _load_provider_ip_whitelist()
        nets = whitelist.get(provider, [])
        if not nets:
            return True  # 未配置 = 不启用 IP 校验
        return any(ip in net for net in nets)
    except ValueError:
        return False


def _has_any_callback_protection(config: dict) -> bool:
    """是否至少配置了一道回调防线（IP 白名单或 callback_token）。

    fail-closed 判定依据：config 中显式设置了非空白名单（任一 provider）、
    或 callback_token 非空，视为有防线；否则视为裸奔。
    verify_mode=off 是显式逃生门，不走本检查（见调用处）。
    """
    if (config.get("callback_token") or "").strip():
        return True
    whitelist = _load_provider_ip_whitelist()
    return any(nets for nets in whitelist.values())


def warn_if_callback_protection_missing(app) -> None:
    """n4：启动期检测「语音已启用但回调无任何防线」并告警。

    默认配置（无 IP 白名单、无 callback_token）下 fail-closed 会 100% 拒真回调：
    语音终态永不落库 → task 必然超时重试直到预算耗尽（电话照打但状态永不更新）。
    该状态必须在启动时被运维看到，而不是等第一通电话打完、回调被拒后才从
    请求日志里排查。应用创建（create_app）时调用本函数。
    """
    try:
        with app.app_context():
            from app.models.voice_setting import VoiceSetting

            config = VoiceSetting.get_raw_batch(VoiceSetting.ALLOWED_KEYS)
            if (config.get("enabled") or "false").lower() != "true":
                return  # 语音未启用，不会有回调，无需告警
            if _has_any_callback_protection(config):
                return
        logger.warning(
            "语音通知已启用，但回调未配置任何防线（IP 白名单 / callback_token）。"
            "当前 fail-closed 策略将拒绝全部回调：语音终态无法写入、任务将超时重试"
            "直至预算耗尽。请配置 VOICE_*_IP_WHITELIST 或 callback_token"
            "（确认风险后可显式将 callback_verify_mode 置 off）。"
        )
    except Exception:  # noqa: BLE001 - 启动期检测失败绝不阻断应用创建
        logger.warning("语音回调防线启动检测失败（跳过）", exc_info=True)


def _load_trusted_proxies() -> list:
    """加载可信代理网段（n7：X-Forwarded-For 信任边界）。

    默认空 = 不信任任何代理，回调 IP 一律取 remote_addr（直连对端）。
    经 nginx 反代部署时配置 VOICE_TRUSTED_PROXIES（如 127.0.0.1/32 或
    反代所在内网段），此时才采信代理追加的 XFF。
    """
    from flask import current_app

    configured = current_app.config.get("VOICE_TRUSTED_PROXIES")
    if configured:
        return [ipaddress.ip_network(n) for n in configured]
    env_val = os.environ.get("VOICE_TRUSTED_PROXIES", "")
    return [ipaddress.ip_network(n.strip()) for n in env_val.split(",") if n.strip()]


def _get_client_ip(req) -> str:
    """获取真实客户端 IP（n7：不可盲信 X-Forwarded-For）。

    修复前取 XFF 最左侧（最早跳）——该值由请求方自行携带，可任意伪造，
    攻击者带 X-Forwarded-For: <白名单IP> 即冒充服务商绕过 IP 白名单。

    信任边界：
    - 直连对端（remote_addr）落在可信代理网段内 → 取 XFF 最右侧（由可信
      代理追加，客户端无法伪造；单层代理下即代理看到的直连 IP）；
    - 否则一律以 remote_addr 为准，XFF 仅作日志参考。
    """
    peer = req.remote_addr or ""
    try:
        peer_ip = ipaddress.ip_address(peer)
        trusted = any(peer_ip in net for net in _load_trusted_proxies())
    except ValueError:
        trusted = False

    xff = req.headers.get("X-Forwarded-For", "")
    if trusted and xff:
        return xff.split(",")[-1].strip()
    return peer


_TERMINAL_EVENTS = VOICE_RESULT_EVENTS


@router.route("/callback", methods=["POST"])
def voice_callback():
    """服务商语音回调。"""
    from app.models.notification import NotificationReceipt
    from app.services.channels.voice import get_voice_config_from_db
    from app.services.channels.voice_providers import get_voice_provider
    from extensions import db

    raw_body = request.get_data()
    config = get_voice_config_from_db()
    provider_name = config.get("provider", "aliyun")
    provider = get_voice_provider(provider_name)
    response_body, response_status = provider.callback_response()

    verify_mode = config.get("callback_verify_mode", "ip_only")
    if verify_mode != "off" and not _has_any_callback_protection(config):
        logger.error(
            "语音回调拒绝处理：未配置任何防线（IP 白名单 / callback_token）。"
            "请配置 VOICE_%s_IP_WHITELIST 或在语音配置页设置 callback_token；"
            "确认风险后可显式将 callback_verify_mode 设为 off",
            provider_name.upper(),
        )
        abort(403)

    if verify_mode == "signature_and_ip":
        if not provider.verify_callback_signature(raw_body, dict(request.headers), config):
            logger.warning("语音回调签名校验失败: ip=%s", request.remote_addr)
            abort(403)

    if verify_mode in ("ip_only", "signature_and_ip"):
        client_ip = _get_client_ip(request)
        if not _is_provider_ip(client_ip, provider_name):
            logger.warning("语音回调 IP 不在白名单: ip=%s provider=%s",
                           client_ip, provider_name)
            abort(403)

    redis_client = _get_voice_redis()
    if not redis_client:
        logger.error("Redis 不可用，语音回调无法幂等去重，拒绝处理")
        abort(503)

    try:
        events = provider.parse_callback(raw_body, dict(request.headers))
    except Exception:
        logger.exception("语音回调解析失败: provider=%s", provider_name)
        return jsonify(dict(response_body, parse_error=True)), response_status

    if not events:
        return jsonify(dict(response_body, ignored=True)), response_status

    handled = []
    for parsed in events:
        call_id = parsed.get("call_id") or ""
        event = parsed["event"]
        receipt_id = parsed.get("receipt_id")
        if not call_id:
            continue

        if not receipt_id:
            receipt_id_str = redis_client.get(f"voice:call:{call_id}")
            if receipt_id_str:
                try:
                    receipt_id = int(receipt_id_str)
                except (TypeError, ValueError):
                    receipt_id = None
        if not receipt_id:
            logger.warning("语音回调无法定位 receipt: call_id=%s", call_id)
            continue

        receipt = db.session.get(
            NotificationReceipt, receipt_id, with_for_update=True
        )
        if not receipt:
            continue

        if not redis_client.set(f"voice:cb:{call_id}:{event}", "1", nx=True, ex=3600):
            logger.debug("语音回调重复，已处理: call_id=%s event=%s", call_id, event)
            db.session.rollback()  # I-3：该分支无未决写入，立即释放行锁
            continue

        status = dict(receipt.channel_status or {})
        current = status.get("voice")
        if current in _TERMINAL_EVENTS and event != "acked":
            logger.debug("语音终态已存在，忽略新事件: call_id=%s current=%s new=%s",
                         call_id, current, event)
            db.session.rollback()  # I-3：立即释放行锁（腾讯云双回调并发时避免排队）
            continue

        is_ack = event == "acked" or bool(parsed.get("key_press"))
        if is_ack:
            status["voice"] = "acked"
            receipt.acked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            status["voice"] = event
        status["voice_retryable"] = bool(parsed.get("retryable"))
        if parsed.get("key_press"):
            status["voice_key_press"] = parsed["key_press"]
        receipt.channel_status = status
        flag_modified(receipt, "channel_status")

        db.session.commit()  # 行锁随 commit 释放

        task_id = status.get("voice_task_id")
        if task_id:
            from app.tasks.voice_tasks import cancel_voice_retry_task
            cancel_voice_retry_task.apply_async(args=[task_id], countdown=1)

        handled.append({"call_id": call_id, "event": event, "receipt_id": receipt_id})

    logger.info("语音回调处理完成: provider=%s handled=%s", provider_name, handled)
    return jsonify(dict(response_body, handled=len(handled))), response_status
