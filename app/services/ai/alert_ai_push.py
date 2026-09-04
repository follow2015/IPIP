# -*- coding: utf-8 -*-
"""告警 AI 解读主动推送：复用既有 SSE 通道广播 alert_with_ai 事件。"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from flask import current_app

from app.services.ai.alert_interpreter import AlertInterpreter
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ALERT_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-alert")


def broadcast_sse(event_type: str, payload: dict) -> None:
    """复用既有 FlaskAPI SSE 推送通道。

    对接 app/services/monitoring/alert_ingress.py:publish_monitor_alert_event
    （告警场景既有入口，封装 target_user_ids 隔离 + best-effort 语义）。
    """
    try:
        from app.services.monitoring.alert_ingress import publish_monitor_alert_event
        from app.services.monitoring.data_scope_service import get_users_with_device_access
    except ImportError:
        logger.info("ai.sse.broadcast type=%s payload_keys=%s", event_type, list(payload.keys()))
        return

    if event_type == "alert_with_ai":
        alert = payload.get("alert", {})
        device_id = alert.get("device_id")
        target_user_ids = get_users_with_device_access(device_id) if device_id else None
        publish_monitor_alert_event(
            device_id=device_id,
            alert_type="ai_interpretation",
            severity=alert.get("severity", "info"),
            idempotency_key=f"ai_interp_{alert.get('id')}",
            outbox_id=alert.get("id"),
            payload=payload,
            target_user_ids=target_user_ids,
        )
    else:
        from app.services.switch_events import emit_global_event
        emit_global_event(event_type, payload)


def _interpret_and_broadcast(alert: Dict) -> None:
    app = current_app._get_current_object()
    with app.app_context():
        try:
            interpretation = AlertInterpreter().interpret(alert)
            broadcast_sse("alert_with_ai", {"alert": alert, "interpretation": interpretation})
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.alert_push.failed %s", e)


def push_alert_with_ai(alert_payload: Dict) -> None:
    """在告警触发链路中调用：异步解读 + SSE 广播。

    应在 notification_service 发送严重告警通知时调用本函数。
    I6 修复：用有界线程池替代无限制起线程，避免告警风暴下线程耗尽。
    """
    if alert_payload.get("severity") not in ("crit", "high"):
        return  # 仅严重告警触发 AI 解读
    try:
        _ALERT_POOL.submit(_interpret_and_broadcast, alert_payload)
    except RuntimeError:
        thread = threading.Thread(target=_interpret_and_broadcast, args=(alert_payload,), daemon=True)
        thread.start()
