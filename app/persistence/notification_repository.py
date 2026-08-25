# -*- coding: utf-8 -*-
"""
通知域 Repository

提供 Notification / NotificationReceipt 的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import List, Optional, Tuple

from sqlalchemy import not_, exists

from app.persistence.base import BaseRepository
from app.models.notification import Notification, NotificationReceipt
from extensions import db

logger = get_logger(__name__)


class NotificationRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(Notification, session or db.session)

    def delete_orphans_before(self, cutoff) -> int:
        subq = self.session.query(NotificationReceipt.notification_id).filter(
            NotificationReceipt.notification_id == Notification.id
        )
        return self.session.query(Notification).filter(
            Notification.created_at < cutoff,
            not_(exists(subq)),
        ).delete(synchronize_session=False)


class NotificationReceiptRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(NotificationReceipt, session or db.session)

    def find_by_user_unread(self, user_id: int) -> List[NotificationReceipt]:
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).all()

    def count_unread(self, user_id: int) -> int:
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).count()

    def list_by_user_paginated(
        self, user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False,
    ) -> Tuple[List[NotificationReceipt], int]:
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
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return items, total

    def mark_read(self, user_id: int) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        unread = self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).all()
        for r in unread:
            r.read_at = now
        return len(unread)

    def mark_read_by_ids(self, user_id: int, notification_ids: list) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, read_at=None,
        ).filter(
            NotificationReceipt.notification_id.in_(notification_ids),
        ).update(
            {NotificationReceipt.read_at: now},
            synchronize_session=False,
        )

    def delete_read(self, user_id: int) -> int:
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id,
        ).filter(
            NotificationReceipt.read_at.isnot(None),
        ).delete(synchronize_session=False)

    def find_by_user_and_notification(
        self, user_id: int, notification_id: int,
    ) -> Optional[NotificationReceipt]:
        return self.session.query(NotificationReceipt).filter_by(
            user_id=user_id, notification_id=notification_id,
        ).first()

    def delete_read_acked_before(self, cutoff) -> int:
        return self.session.query(NotificationReceipt).filter(
            NotificationReceipt.read_at.isnot(None),
            NotificationReceipt.read_at < cutoff,
            NotificationReceipt.acked_at.isnot(None),
            NotificationReceipt.acked_at < cutoff,
        ).delete(synchronize_session=False)
