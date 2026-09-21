# -*- coding: utf-8 -*-
"""
通知域 Repository

提供 Notification / NotificationReceipt 的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import List, Optional, Tuple
from app.utils.time_utils import now_utc_naive

from sqlalchemy import not_, exists

from app.persistence.base import BaseRepository
from app.core.pagination_limits import ensure_offset_within_limit
from app.models.notification import Notification, NotificationReceipt
from extensions import db

logger = get_logger(__name__)


class NotificationRepository(BaseRepository):
    """Notification 数据访问层"""

    def __init__(self, session=None):
        super().__init__(Notification, session or db.session)

    def delete_orphans_before(self, cutoff) -> int:
        """删除无回执引用的孤立通知（早于 cutoff 时间）

        Args:
            cutoff: datetime，截止时间

        Returns:
            int: 删除行数
        """
        subq = self.session.query(NotificationReceipt.notification_id).filter(
            NotificationReceipt.notification_id == Notification.id
        )
        return self.session.query(Notification).filter(
            Notification.created_at < cutoff,
            not_(exists(subq)),
        ).delete(synchronize_session=False)

    def find_recent_receipts_with_notification_id(
        self, cutoff, limit: int,
    ) -> List[Tuple[NotificationReceipt, int]]:
        """查询近期通知的回执（含通知 id），供启动回补扫描待重投任务（B-42①）

        原 ``recover_pending_deliveries`` 里的裸 ``db.session.query`` 收敛至此。
        多实体 join 用不了 ``_base_query()``（它只建单模型查询）；若 Notification
        将来开启软删除，软删过滤的**唯一修正面在本仓储目录**（B-42 的核心动机：
        把分叉从"app 全域"压缩到"persistence 一个目录"）。

        Args:
            cutoff: datetime，只看 created_at 晚于它的通知
            limit: 行数上限

        Returns:
            List[Tuple[NotificationReceipt, int]]: (回执, 通知 id)，通知 id 倒序
        """
        return (
            self.session.query(NotificationReceipt, Notification.id)
            .join(Notification, Notification.id == NotificationReceipt.notification_id)
            .filter(Notification.created_at >= cutoff)
            .order_by(Notification.id.desc())
            .limit(limit)
            .all()
        )


class NotificationReceiptRepository(BaseRepository):
    """NotificationReceipt 数据访问层"""

    def __init__(self, session=None):
        super().__init__(NotificationReceipt, session or db.session)

    def find_by_user_unread(self, user_id: int) -> List[NotificationReceipt]:
        """查询用户未读回执

        Args:
            user_id: 用户 ID

        Returns:
            List[NotificationReceipt]
        """
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).all()

    def count_unread(self, user_id: int) -> int:
        """统计用户未读回执数

        Args:
            user_id: 用户 ID

        Returns:
            int: 未读数
        """
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).count()

    def list_by_user_paginated(
        self, user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False,
    ) -> Tuple[List[NotificationReceipt], int]:
        """分页查询用户通知回执（含关联通知，未读优先、时间倒序）

        Args:
            user_id: 用户 ID
            page: 页码
            per_page: 每页数量
            unread_only: 是否仅返回未读

        Returns:
            Tuple[List[NotificationReceipt], int]: (回执列表, 总数)
        """
        query = self.session.query(NotificationReceipt).filter_by(
            user_id=user_id,
        ).join(Notification)
        if unread_only:
            query = query.filter(NotificationReceipt.read_at.is_(None))
        query = query.order_by(
            NotificationReceipt.read_at.is_(None).desc(),
            Notification.created_at.desc(),
        )
        total = query.count()
        offset = (page - 1) * per_page
        ensure_offset_within_limit(offset)
        items = query.offset(offset).limit(per_page).all()
        return items, total

    def mark_read(self, user_id: int) -> int:
        """标记用户所有未读回执为已读

        Returns:
            int: 更新行数
        """
        from datetime import datetime, timezone
        now = now_utc_naive()
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).update(
            {NotificationReceipt.read_at: now},
            synchronize_session=False,
        )

    def mark_read_by_ids(self, user_id: int, notification_ids: list) -> int:
        """标记用户指定通知的未读回执为已读

        Args:
            user_id: 用户 ID
            notification_ids: 通知 ID 列表

        Returns:
            int: 更新行数
        """
        from datetime import datetime, timezone
        now = now_utc_naive()
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).filter(
            NotificationReceipt.notification_id.in_(notification_ids),
        ).update(
            {NotificationReceipt.read_at: now},
            synchronize_session=False,
        )

    def delete_read(self, user_id: int) -> int:
        """删除用户已读回执

        Args:
            user_id: 用户 ID

        Returns:
            int: 删除行数
        """
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id,
        ).filter(
            NotificationReceipt.read_at.isnot(None),
        ).delete(synchronize_session=False)

    def find_by_user_and_notification(
        self, user_id: int, notification_id: int,
    ) -> Optional[NotificationReceipt]:
        """查询用户对指定通知的回执

        Args:
            user_id: 用户 ID
            notification_id: 通知 ID

        Returns:
            Optional[NotificationReceipt]
        """
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, notification_id=notification_id,
        ).first()

    def find_by_notification_and_users(
        self, notification_id: int, user_ids: List[int],
    ) -> List[NotificationReceipt]:
        """批量查询一条通知下指定用户的回执（投递 worker 的预取入口，B-42①）

        走 ``_base_query()`` 而非裸 ``self.session.query``：与 find_by_id(s) 一致地
        享受软删除过滤 —— B-42 的教训是"仓储与裸 query 语义分叉"（前者过滤软删、
        后者不过滤），新增方法必须站在过滤的一侧。

        Args:
            notification_id: 通知 ID
            user_ids: 用户 ID 列表（可能为空）

        Returns:
            List[NotificationReceipt]（同键多行时顺序不确定，调用方按 user_id 建索引用）
        """
        if not user_ids:
            return []
        return self._base_query().filter(
            NotificationReceipt.notification_id == notification_id,
            NotificationReceipt.user_id.in_(user_ids),
        ).all()

    def delete_read_acked_before(self, cutoff) -> int:
        """删除早于 cutoff 的已读且已确认回执

        Args:
            cutoff: datetime，截止时间

        Returns:
            int: 删除行数
        """
        return self.session.query(NotificationReceipt).filter(
            NotificationReceipt.read_at.isnot(None),
            NotificationReceipt.read_at < cutoff,
            NotificationReceipt.acked_at.isnot(None),
            NotificationReceipt.acked_at < cutoff,
        ).delete(synchronize_session=False)
