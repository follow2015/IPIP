# -*- coding: utf-8 -*-
"""P2-17: 监控告警依赖抑制规则

手动配置的告警依赖关系：上游设备 active 告警时抑制下游设备的同类型告警，
避免网络抖动时下游设备大量告警淹没根因。

自动推断的依赖关系（DeviceServerExt.parent_device_id）不在此表，
由 alert_dependency_service 直接查拓扑；此表仅存手动配置的覆盖/补充规则。
"""
from sqlalchemy import BigInteger, Boolean, Index, String, text

from app.models.base import BaseModel
from extensions import db


class MonitorAlertDependencyRule(BaseModel):
    """监控告警依赖抑制规则（手动配置）"""

    __tablename__ = "monitor_alert_dependency_rule"
    __table_args__ = (
        Index("ix_madr_upstream", "upstream_device_id"),
        Index("ix_madr_downstream", "downstream_device_id"),
        Index("ix_madr_enabled", "enabled"),
        {"comment": "监控告警依赖抑制规则（P2-17，上游 active 告警抑制下游）"},
    )

    name = db.Column(
        db.String(128),
        nullable=False,
        comment="规则名称",
    )
    upstream_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="上游设备 ID（active 告警在此设备上时触发抑制）",
    )
    downstream_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="下游设备 ID（被抑制的设备）",
    )
    alert_types = db.Column(
        db.JSON,
        nullable=True,
        comment="受抑制的告警类型列表（null=全部类型）",
    )
    reason = db.Column(
        db.String(255),
        nullable=True,
        comment="规则说明",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否启用",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "upstream_device_id": self.upstream_device_id,
            "downstream_device_id": self.downstream_device_id,
            "alert_types": self.alert_types,
            "reason": self.reason,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
