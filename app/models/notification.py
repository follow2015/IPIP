# -*- coding: utf-8 -*-
"""
通知模型

定义统一消息通知的数据模型：
- Notification：通知主体（一条通知发给多人时只存一条）
- NotificationReceipt：投递回执（每用户一条，记录已读状态）
"""
from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class Notification(BaseModel):
    """通知主体模型"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notification_type", "type"),
        Index("idx_notification_severity", "severity"),
        Index("idx_notification_target", "target_type", "target_id"),
        Index("idx_notification_source", "source_module"),
        Index("idx_notification_created", "created_at"),
        {"comment": "统一消息通知表"},
    )

    type = db.Column(db.String(100), nullable=False, comment="通知类型")

    severity = db.Column(
        db.String(20), nullable=False, server_default="info", comment="严重程度"
    )

    title = db.Column(db.String(255), nullable=False, comment="通知标题")
    content = db.Column(db.Text, nullable=True, comment="通知正文")

    payload = db.Column(db.JSON, nullable=True, comment="业务载荷")

    source_module = db.Column(db.String(50), nullable=True, comment="来源模块")

    target_type = db.Column(
        db.String(20), nullable=False, comment="目标类型(user/role/broadcast)"
    )
    target_id = db.Column(db.String(100), nullable=True, comment="目标标识")

    idempotency_key = db.Column(
        db.String(255), nullable=True, unique=True, comment="幂等键"
    )

    receipts = relationship(
        "NotificationReceipt",
        back_populates="notification",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, exclude=None, include_relations=False):
        data = super().to_dict(exclude=exclude)
        return data


class NotificationReceipt(BaseModel):
    """通知投递回执（每用户一条）"""

    __tablename__ = "notification_receipts"
    __table_args__ = (
        Index("idx_receipt_user_unread", "user_id", "read_at"),
        Index("idx_receipt_notification", "notification_id"),
        Index("idx_receipt_user_notification", "user_id", "notification_id"),
        {"comment": "通知投递回执表"},
    )

    notification_id = db.Column(
        db.BigInteger,
        db.ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        comment="通知ID",
    )
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID",
    )

    read_at = db.Column(db.DateTime, nullable=True, comment="已读时间")

    delivered_channels = db.Column(db.JSON, nullable=True, comment="投递渠道")

    channel_status = db.Column(db.JSON, nullable=True, comment="各渠道实际投递结果")

    ack_required = db.Column(
        db.Boolean, nullable=False, server_default="0", comment="是否需要确认"
    )
    acked_at = db.Column(db.DateTime, nullable=True, comment="确认时间")

    notification = relationship("Notification", back_populates="receipts")

    def to_dict(self, exclude=None, include_relations=False):
        data = super().to_dict(exclude=exclude)
        return data
