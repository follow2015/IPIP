# -*- coding: utf-8 -*-
"""Webhook 配置仓储

提供 WebhookConfig 的数据访问方法。
"""
from typing import List, Optional

from app.models.webhook_config import WebhookConfig
from app.persistence.base import BaseRepository


class WebhookConfigRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(WebhookConfig, session=session)

    def find_all_ordered(self) -> List[WebhookConfig]:
        return (
            self._base_query()
            .order_by(WebhookConfig.created_at.desc())
            .all()
        )

    def find_by_name_channel(self, name: str, channel: str) -> Optional[WebhookConfig]:
        return self._base_query().filter_by(name=name, channel=channel).first()
