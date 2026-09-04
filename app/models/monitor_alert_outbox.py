# -*- coding: utf-8 -*-
"""监控告警发件箱（outbox 模式）

解耦「状态落库」与「告警投递」：``apply_result`` 在状态 upsert 的【同一事务】内
写入待发行，由独立进程内发件轮询器（``MonitorOutboxSender``）读取并调用
``notification_service.notify`` 投递，成功后标记 ``sent``。以此消除原
「upsert 未提交即先 notify」的一致性窗口：

- 状态更新与待发告警现在原子提交，不会「告警已发但状态回滚」或反之；
- 发件轮询器提供「至少一次投递」：崩溃重放时 notify 的 ``idempotency_key``
  幂等去重，不会产生重复通知。
"""
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text

from app.models.base import BaseModel, LONGTEXT
from extensions import db

import json


class MonitorAlertOutbox(BaseModel):
    """监控告警发件箱（outbox）"""

    __tablename__ = "monitor_alert_outbox"
    __table_args__ = (
        Index("ix_mao_status", "status"),
        Index("ix_mao_dedup_key", "dedup_key"),
        Index("ix_mao_created_at", "created_at"),
        Index("ix_mao_acknowledged_at", "acknowledged_at"),
        Index("ix_mao_incident", "incident_id"),
        {"comment": "监控告警发件箱（outbox 模式，解耦状态落库与告警投递）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联设备ID（设备被删除后置空，历史告警行本身保留）",
    )
    alert_type = db.Column(
        db.String(40),
        nullable=False,
        comment="device_unreachable / device_recovered",
    )
    severity = db.Column(
        db.String(20),
        nullable=False,
        comment="info / warning / critical",
    )
    dedup_key = db.Column(
        db.String(191),
        nullable=False,
        comment="= notify idempotency_key，去重/幂等",
    )
    payload_json = db.Column(
        LONGTEXT,
        nullable=False,
        comment=(
            "notify 参数字典的 JSON：type/severity/title/content/payload/"
            "source_module/target_type/target_id/channels/idempotency_key/allow_broadcast"
        ),
    )
    status = db.Column(
        db.String(16),
        nullable=False,
        server_default="pending",
        comment="pending / sent / failed",
    )
    attempts = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="投递尝试次数",
    )
    last_error = db.Column(
        db.Text,
        nullable=True,
        comment="最近一次投递失败信息",
    )
    next_retry_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="下次允许重试时间（指数退避；NULL 表示立即可重试）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="入箱时间",
    )
    sent_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="投递成功时间",
    )
    acknowledged_by = db.Column(
        db.String(64),
        nullable=True,
        comment="确认人用户名（G9 人工确认/认领）",
    )
    acknowledged_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="确认时间（G9；同时供 G4.2 升级扫描判断未确认告警）",
    )
    ack_note = db.Column(
        db.Text,
        nullable=True,
        comment="确认备注（G9）",
    )
    closed_by = db.Column(
        db.String(64),
        nullable=True,
        comment="关闭人用户名（P2-16 manual_close）",
    )
    closed_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="手动关闭时间（P2-16；IS NOT NULL 表示已关闭，不再计入活跃告警）",
    )
    close_reason = db.Column(
        db.Text,
        nullable=True,
        comment="关闭原因（P2-16）",
    )
    incident_id = db.Column(
        db.BigInteger,
        nullable=True,
        comment="归属事件ID（事件聚合；NULL 表示未聚合或聚合失败）",
    )
    reason_code = db.Column(
        db.String(40),
        nullable=True,
        comment="归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        """序列化（不回显敏感字段）"""
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "dedup_key": self.dedup_key,
            "payload": json.loads(self.payload_json) if self.payload_json else None,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "ack_note": self.ack_note,
            "closed_by": self.closed_by,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "close_reason": self.close_reason,
            "incident_id": self.incident_id,
            "reason_code": self.reason_code,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
