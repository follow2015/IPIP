# -*- coding: utf-8 -*-
"""设备监控共享凭据模型（AES-256-GCM 加密）

monitor_credentials 退化为「共享凭据」实体：只存协议 + 密文 + 可读标签，
不含 device_id；设备关联经 device_monitor_credentials 多对多表。
encrypted_payload 永不通过 to_dict() 回显，比照 SwitchCredentials.password。
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import BaseModel
from extensions import db
from app.utils.security.encryption import decrypt

import json

NON_SECRET_KEYS = {
    "username",
    "auth_protocol",
    "priv_protocol",
    "snmp_version",
    "api_url",
    "verify_ssl",
    "match_by",
}


class MonitorCredential(BaseModel):

    __tablename__ = "monitor_credentials"
    __table_args__ = (
        Index("ix_mc_protocol", "protocol"),
        UniqueConstraint("protocol", "payload_hash", name="uk_mc_protocol_hash"),
        UniqueConstraint("protocol", "name", name="uk_mc_protocol_name"),
        {"comment": "设备监控共享凭据（AES-256-GCM加密）"},
    )

    protocol = db.Column(
        db.String(20),
        nullable=False,
        comment="snmp/redfish/ipmi",
    )
    name = db.Column(
        db.String(128),
        nullable=False,
        comment="同协议下唯一的可读标签，如'机房A SNMP只读团体字'（非机密）",
    )
    encrypted_payload = db.Column(
        db.Text,
        nullable=False,
        comment="AES-256-GCM 加密的凭据 JSON",
    )
    payload_hash = db.Column(
        db.String(64),
        nullable=True,
        comment="payload 规范 JSON 的 SHA-256 十六进制（用于同明文凭据去重复用；旧行密文不可逆留空）",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default="1",
        comment="是否启用",
    )

    def to_dict(self, exclude=None, include_relations=False):
        _exclude = {"encrypted_payload"}
        if exclude:
            _exclude.update(exclude)
        result = super().to_dict(exclude=list(_exclude))
        result["payload_meta"] = self._payload_meta()
        return result

    def _payload_meta(self) -> dict:
        try:
            payload = json.loads(decrypt(self.encrypted_payload))
        except Exception:
            return {}
        meta: dict = {}
        for key, value in payload.items():
            if key in NON_SECRET_KEYS:
                meta[key] = value
        if "community" in payload:
            meta["has_community"] = True
        return meta


class DeviceMonitorCredential(BaseModel):

    __tablename__ = "device_monitor_credentials"
    __table_args__ = (
        UniqueConstraint("credential_id", "device_id", name="uk_dmc_cred_device"),
        {"comment": "设备监控凭据关联（多对多）"},
    )

    credential_id = db.Column(
        BigInteger,
        ForeignKey("monitor_credentials.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联共享凭据ID",
    )
    device_id = db.Column(
        BigInteger,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联设备ID",
    )
