# -*- coding: utf-8 -*-
"""
通知模型

定义统一消息通知的数据模型：
- Notification：通知主体（一条通知发给多人时只存一条）
- NotificationReceipt：投递回执（每用户一条，记录已读状态）
"""
import logging

from sqlalchemy import Index
from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint

from app.models.base import BaseModel
from extensions import db

logger = logging.getLogger(__name__)


class Notification(BaseModel):
    """通知主体模型"""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint('idempotency_key', name='uk_idempotency_key'),
        Index('idx_notification_type', 'type'),
        Index('idx_notification_severity', 'severity'),
        Index('idx_notification_target', 'target_type', 'target_id'),
        Index('idx_notification_source', 'source_module'),
        Index('idx_notification_created', 'created_at'),
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
        UniqueConstraint(
            "notification_id", "user_id", name="uk_receipt_notification_user"
        ),
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

    REPAIR_BATCH_SIZE = 200

    @staticmethod
    def repair_duplicates(conn) -> int:
        """删除 (notification_id, user_id) 重复行，每组保留 id 最小者。返回删除数。

        供迁移 0016（加唯一约束前的存量修复）与测试共用。**保 MIN(id)** 与读侧
        既有语义一致：`.first()` / A-P1-2 的 `setdefault` 都是"首条胜出"，修复前后
        "读到哪条"不得变化；被删行的 id 与 channel_status **逐条记 WARNING**
        （信息不丢，只是不进库）。

        Args:
            conn: **DBAPI** 连接（与迁移 runner 注入的一致；测试侧用
                ``db.engine.raw_connection()`` 同接口）。

        SQL 方言说明：SQLite/MySQL 通吃的写法，无行值构造器；占位符因 pymysql
        （pyformat）与 sqlite3（qmark）paramstyle 不同而**不使用**——值全部来自
        表内 int 列且经 ``int()`` 强转后才拼接，无注入面。
        """
        import json as _json

        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT notification_id, user_id, MIN(id) AS keep_id
                FROM notification_receipts
                GROUP BY notification_id, user_id
                HAVING COUNT(*) > 1
                """
            )
            groups = cur.fetchall()
            if not groups:
                return 0

            removed_total = 0
            for notification_id, user_id, keep_id in groups:
                nid, uid, keep_id = int(notification_id), int(user_id), int(keep_id)
                cur.execute(
                    "SELECT id, delivered_channels, channel_status "
                    "FROM notification_receipts "
                    f"WHERE notification_id = {nid} AND user_id = {uid} "
                    f"AND id <> {keep_id} ORDER BY id"
                )
                rows = cur.fetchall()
                for row_id, delivered, status in rows:
                    rid = int(row_id)
                    logger.warning(
                        "回执重复行：id=%s (notification_id=%s, user_id=%s) "
                        "保留 id=%s，删除本行。delivered_channels=%s channel_status=%s",
                        rid, nid, uid, keep_id, delivered,
                        status if isinstance(status, str) else _json.dumps(status),
                    )

                bad_ids = [int(r[0]) for r in rows]
                for start in range(0, len(bad_ids), NotificationReceipt.REPAIR_BATCH_SIZE):
                    chunk = bad_ids[start:start + NotificationReceipt.REPAIR_BATCH_SIZE]
                    cur.execute(
                        "DELETE FROM notification_receipts "
                        f"WHERE id IN ({','.join(str(i) for i in chunk)})"
                    )
                    removed_total += cur.rowcount
                    conn.commit()  # 尽快释放行锁，别攒到迁移结束（0011 同款）
            return removed_total
        finally:
            cur.close()
