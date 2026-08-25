# -*- coding: utf-8 -*-
"""
Webhook 配置模型

存储企业微信/飞书群机器人 Webhook URL 及其匹配规则。
"""
from app.utils.logging import get_logger
import re
import socket
import ipaddress
from urllib.parse import urlparse

from sqlalchemy import Index

from app.models.base import BaseModel
from extensions import db

logger = get_logger(__name__)

_INTERNAL_HOSTNAME_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.",
    "192.168.", "127.", "169.254.",
)

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL 必须使用 https 协议")
    host = parsed.hostname or ""

    if host == "localhost" or any(host.startswith(p) for p in _INTERNAL_HOSTNAME_PREFIXES):
        raise ValueError("Webhook URL 不能指向内网地址")

    try:
        resolved_ips = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                raise ValueError(f"Webhook URL 解析到内网地址 ({ip_str})，不允许访问")
    except socket.gaierror:
        pass


class WebhookConfig(BaseModel):

    __tablename__ = "webhook_configs"
    __table_args__ = (
        Index("idx_webhook_channel", "channel"),
        Index("idx_webhook_enabled", "enabled"),
        {"comment": "Webhook 渠道配置表"},
    )

    name = db.Column(db.String(50), nullable=False, comment="配置名称")
    channel = db.Column(db.String(20), nullable=False, comment="渠道标识: wechat_work/feishu/custom")
    url = db.Column(db.String(500), nullable=False, comment="Webhook URL")
    secret = db.Column(db.String(255), nullable=True, comment="签名密钥")
    enabled = db.Column(db.Boolean, nullable=False, server_default="1", comment="是否启用")
    message_template = db.Column(db.JSON, nullable=True, comment="消息模板")
    applicable_types = db.Column(db.JSON, nullable=True, comment="适用通知类型列表")
    applicable_severities = db.Column(db.JSON, nullable=True, comment="适用严重程度")
    created_by = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建者ID")

    def to_dict(self, exclude=None, include_relations=False):
        data = super().to_dict(exclude=exclude)
        if data.get("secret"):
            s = data["secret"]
            data["secret"] = (s[:4] + "***") if len(s) > 4 else "***"
        if data.get("url"):
            data["url"] = re.sub(r"(key=|token=|secret=)[^&]+", r"\1***", data["url"])
        return data
