# -*- coding: utf-8 -*-
"""
运维告警桥接

将 CacheMonitor、RateLimitMonitor 和审计事件转换为统一通知。
- CacheMonitor: 通过 add_alert_callback() 回调机制桥接
- RateLimitMonitor: 通过后台线程轮询 get_alerts() 桥接（在 notification_delivery_worker.py 中调用）
- 审计事件: 通过 bridge_audit_event() 桥接，按 critical/warning/info 分级触发通知
"""
from app.utils.logging import get_logger
from app.core.enums import ChannelType, NotificationTypeCode, SeverityLevel

from app.services.notification_service import notification_service

logger = get_logger(__name__)

SEVERITY_MAP = {
    "low": SeverityLevel.INFO,
    "medium": SeverityLevel.WARNING,
    "high": SeverityLevel.CRITICAL,
    "critical": SeverityLevel.CRITICAL,
}

AUDIT_SEVERITY_CHANNELS = {
    SeverityLevel.CRITICAL: (ChannelType.INBOX, ChannelType.EMAIL, ChannelType.WECHAT_WORK),
    SeverityLevel.WARNING: (ChannelType.INBOX, ChannelType.EMAIL),
    SeverityLevel.INFO: (ChannelType.INBOX,),
}

NOTIFIABLE_RESOURCES = {
    "device",
    "user",
    "switch",
    "rbac",
    "webhook_config",
    "mail_setting",
}


def bridge_cache_alert(alert) -> None:
    """CacheMonitor.add_alert_callback() 的回调函数

    Args:
        alert: CacheAlert 实例（来自 app.utils.cache.monitoring）
    """
    try:
        notification_service.notify(
            type=f"cache_{alert.alert_type}",  # cache_performance / cache_error / cache_capacity
            severity=SEVERITY_MAP.get(alert.severity, SeverityLevel.WARNING),
            title=f"缓存告警: {alert.message}",
            content=alert.message,
            payload=alert.metrics,
            source_module="cache_monitor",
            target_type="role",
            target_id="admin",
            channels=(ChannelType.INBOX, ChannelType.EMAIL, ChannelType.WECHAT_WORK),
            ack_required=alert.severity in ("high", "critical"),
        )
    except Exception:
        logger.exception("缓存告警桥接失败（已忽略）")


def bridge_rate_limit_alert(alert_data: dict) -> None:
    """RateLimitMonitor 告警桥接

    由 notification_delivery_worker._poll_rate_limit_alerts() 调用。

    Args:
        alert_data: 限流告警数据
            - key: 限制键
            - endpoint: 端点
            - blocked_count: 被阻止次数
            - severity: 严重程度
    """
    try:
        notification_service.notify(
            type=NotificationTypeCode.RATE_LIMIT_EXCEEDED,
            severity=SEVERITY_MAP.get(alert_data.get("severity", "medium"), SeverityLevel.WARNING),
            title=f"频率限制告警: {alert_data.get('key', 'unknown')}",
            content=f"端点 {alert_data.get('endpoint', 'unknown')} 在统计窗口内被阻止 {alert_data.get('blocked_count', 0)} 次",
            payload=alert_data,
            source_module="rate_limiting",
            target_type="role",
            target_id="admin",
            channels=(ChannelType.INBOX, ChannelType.EMAIL),
        )
    except Exception:
        logger.exception("限流告警桥接失败（已忽略）")


def register_ops_alert_callbacks() -> None:
    """注册所有运维告警回调（在 create_app 中调用）"""
    from app.utils.cache.monitoring import cache_monitor
    cache_monitor.add_alert_callback(bridge_cache_alert)
    logger.info("运维告警回调已注册")


def bridge_audit_event(audit_log, severity: str = SeverityLevel.INFO) -> None:
    """审计事件 → 通知桥接

    根据审计事件的严重程度和操作类型，决定是否发送通知以及通过哪些渠道。

    分级规则:
    - critical: inbox + email + 企微（穿透免打扰）
    - warning: inbox + email
    - info: inbox only（遵守免打扰）
    - delete 操作自动升级为 warning
    - rbac/webhook_config/mail_setting 的任何操作自动升级为 warning（安全敏感）
    - info 级别的 create/update 不通知（避免通知风暴）

    Args:
        audit_log: AuditLog 实例
        severity: 严重程度 info/warning/critical（SeverityLevel 值）
    """
    try:
        if audit_log.resource not in NOTIFIABLE_RESOURCES:
            return

        if audit_log.action == "delete" and severity == SeverityLevel.INFO:
            severity = SeverityLevel.WARNING

        if audit_log.resource in ("rbac", "webhook_config", "mail_setting") and severity == SeverityLevel.INFO:
            severity = SeverityLevel.WARNING

        if severity == SeverityLevel.INFO and audit_log.action in ("create", "update"):
            return

        channels = AUDIT_SEVERITY_CHANNELS.get(severity, (ChannelType.INBOX,))

        action_text = {
            "create": "创建",
            "update": "更新",
            "delete": "删除",
        }.get(audit_log.action, audit_log.action)

        resource_text = {
            "device": "设备",
            "user": "用户",
            "switch": "交换机",
            "rbac": "RBAC权限",
            "webhook_config": "Webhook配置",
            "mail_setting": "邮件配置",
        }.get(audit_log.resource, audit_log.resource)

        title = f"审计通知: {resource_text}{action_text}"
        if audit_log.resource_id:
            title += f" #{audit_log.resource_id}"

        notification_service.notify(
            type=f"audit_{audit_log.resource}_{audit_log.action}",
            severity=SEVERITY_MAP.get(severity, severity),
            title=title,
            content=f"操作人ID: {audit_log.user_id or '未知'} | 资源: {audit_log.resource}#{audit_log.resource_id or '?'} | 操作: {audit_log.action}",
            payload=audit_log.detail or {},
            source_module="audit",
            target_type="role",
            target_id="admin",
            channels=channels,
            idempotency_key=f"audit_log_{audit_log.id}",
            ack_required=severity == SeverityLevel.CRITICAL,
        )
    except Exception:
        logger.exception("审计通知桥接失败（已忽略）")
