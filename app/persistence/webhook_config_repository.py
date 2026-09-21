# -*- coding: utf-8 -*-
"""Webhook 配置仓储

提供 WebhookConfig 的数据访问方法。
"""
from typing import List, Optional

from app.models.webhook_config import WebhookConfig
from app.persistence.base import BaseRepository


class WebhookConfigRepository(BaseRepository):
    """Webhook 配置仓储"""

    def __init__(self, session=None):
        super().__init__(WebhookConfig, session=session)

    def list_enabled_by_channel(self, channel: str) -> List[WebhookConfig]:
        """取某渠道**启用**的 webhook 配置（B-44 扫尾批：投递入口）。"""
        return (
            self.session.query(WebhookConfig)
            .filter_by(channel=channel, enabled=True)
            .all()
        )

    def find_all_ordered(self) -> List[WebhookConfig]:
        """按创建时间倒序列出所有配置。"""
        return (
            self._base_query()
            .order_by(WebhookConfig.created_at.desc())
            .all()
        )

    def find_by_name_channel(self, name: str, channel: str) -> Optional[WebhookConfig]:
        """按 name + channel 联合唯一查找。"""
        return self._base_query().filter_by(name=name, channel=channel).first()
