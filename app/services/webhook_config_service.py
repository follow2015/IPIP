# -*- coding: utf-8 -*-
"""Webhook 配置服务

业务逻辑层：所有数据访问经由 WebhookConfigRepository，
API 层不再直接使用 db.session 或 Model.query。
"""
from typing import Any, Dict, List, Optional

from app.core.enums import ChannelType, BROADCAST_CHANNELS
from app.exceptions.validation import ValidationError
from app.models.webhook_config import WebhookConfig, validate_webhook_url
from app.persistence.webhook_config_repository import WebhookConfigRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)

_VALID_CHANNELS = BROADCAST_CHANNELS


class WebhookConfigService:
    """Webhook 配置服务"""

    def __init__(self, webhook_config_repository: WebhookConfigRepository):
        self.webhook_config_repository = webhook_config_repository

    def list_configs(self) -> List[Dict[str, Any]]:
        """列出所有 Webhook 配置。"""
        configs = self.webhook_config_repository.find_all_ordered()
        return [c.to_dict() for c in configs]

    def get_config(self, config_id: int) -> Optional[WebhookConfig]:
        """获取单个 Webhook 配置。"""
        return self.webhook_config_repository.find_by_id(config_id)

    def create_config(self, data: Dict[str, Any], created_by: int) -> WebhookConfig:
        """创建 Webhook 配置。

        Raises:
            ValidationError: 必填项缺失、渠道无效、名称重复、URL 不合法
        """
        name = data.get("name")
        channel = data.get("channel")
        url = data.get("url")

        if not name or not channel or not url:
            raise ValidationError("name、channel、url 为必填项")

        if channel not in _VALID_CHANNELS:
            raise ValidationError(f"channel 必须为 {'/'.join(_VALID_CHANNELS)}")

        existing = self.webhook_config_repository.find_by_name_channel(name, channel)
        if existing:
            raise ValidationError(f"同渠道下已存在同名 Webhook 配置: {name}")

        validate_webhook_url(url)

        config = WebhookConfig(
            name=name,
            channel=channel,
            url=url,
            secret=data.get("secret"),
            enabled=data.get("enabled", True),
            message_template=data.get("message_template"),
            applicable_types=data.get("applicable_types"),
            applicable_severities=data.get("applicable_severities"),
            created_by=created_by,
        )
        self.webhook_config_repository.session.add(config)

        logger.info("Webhook 配置已创建: name=%s channel=%s", name, channel)
        return config

    def update_config(
        self, config_id: int, data: Dict[str, Any]
    ) -> Optional[WebhookConfig]:
        """更新 Webhook 配置。

        Raises:
            ValidationError: URL 不合法
        """
        config = self.webhook_config_repository.find_by_id(config_id)
        if not config:
            return None

        new_url = data.get("url", config.url)
        if new_url != config.url:
            validate_webhook_url(new_url)

        updatable_fields = [
            "name", "channel", "url", "secret", "enabled",
            "message_template", "applicable_types", "applicable_severities",
        ]
        for field in updatable_fields:
            if field in data:
                setattr(config, field, data[field])

        logger.info("Webhook 配置已更新: id=%s", config_id)
        return config

    def delete_config(self, config_id: int) -> bool:
        """删除 Webhook 配置。"""
        config = self.webhook_config_repository.find_by_id(config_id)
        if not config:
            return False
        self.webhook_config_repository.session.delete(config)
        logger.info("Webhook 配置已删除: id=%s", config_id)
        return True


webhook_config_service = WebhookConfigService(WebhookConfigRepository())
