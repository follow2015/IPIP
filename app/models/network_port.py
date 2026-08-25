from __future__ import annotations

"""
网络设备端口 ORM 模型

定义网络设备端口拓扑关系表（network_ports）。
统一端口表：同时承载手动维护端口和自动采集端口数据。
"""
from sqlalchemy import Integer, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class NetworkPort(BaseModel):
    __tablename__ = "network_ports"
    __table_args__ = (
        UniqueConstraint("device_id", "port_name", name="uq_device_port_name"),
        Index("ix_np_link_status", "link_status"),
        Index("ix_np_customer_id", "customer_id"),
        Index("ix_np_data_source", "data_source"),
        Index("idx_np_vlan", "vlan"),
        {"extend_existing": True},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id"), nullable=False, comment="设备ID",
    )
    port_type = db.Column(String(50), comment="端口类型")
    slot = db.Column(Integer, default=-1, comment="槽位(-1=无槽位)")
    card = db.Column(Integer, default=-1, comment="板卡号(-1=无板卡)")
    port_number = db.Column(Integer, default=-1, comment="端口号")
    port_name = db.Column(String(100), nullable=False, comment="端口名称")
    speed = db.Column(String(20), comment="端口速率")
    usage_status = db.Column(
        db.Enum("free", "occupied", "disabled", "error", name="port_usage_status_enum"),
        default="free", comment="占用状态(free/occupied/disabled/error)",
    )
    vlan = db.Column(String(200), comment="VLAN配置(采集缓存,真值来源为vlan_port_members表)")
    description = db.Column(db.Text, comment="端口描述")

    link_status = db.Column(String(50), comment="链路状态(up/down/disabled)")
    mac = db.Column(String(17), comment="MAC地址")
    ip_address = db.Column(String(45), comment="端口主IP(deprecated,权威源为switch_port_ips)")
    customer_id = db.Column(db.BigInteger, ForeignKey("customers.id"), comment="客户ID")
    raw_info = db.Column(db.Text, comment="原始端口信息(JSON)")
    data_source = db.Column(
        db.Enum("manual", "auto", "hybrid", name="data_source_enum"),
        default="manual", comment="数据来源(manual/auto/hybrid)",
    )
    last_collected_at = db.Column(DateTime, comment="最后采集时间")

    lag_group_id = db.Column(
        db.BigInteger,
        db.ForeignKey("link_aggregation_groups.id", ondelete="SET NULL"),
        comment="LAG成员：所属LAG组ID，NULL=非LAG成员端口",
    )

    device = relationship("Device", foreign_keys=[device_id])
    connection = relationship(
        "DeviceConnection",
        foreign_keys="DeviceConnection.switch_port_id",
        back_populates="switch_port",
        uselist=False,
    )
    customer = relationship("Customer", foreign_keys=[customer_id])
    lag_group = relationship(
        "LinkAggregationGroup",
        foreign_keys=[lag_group_id],
        back_populates="member_port_list",
    )

    PROTECTED_FIELDS = set()

    LOGICAL_PORT_KEYWORDS = {"trunk", "eth-trunk", "port-channel", "vlanif", "loopback", "vlan", "nve", "tunnel"}

    @staticmethod
    def is_logical_port(port_name: str | None) -> bool:
        if not port_name:
            return False
        pn = port_name.lower()
        return any(kw in pn for kw in NetworkPort.LOGICAL_PORT_KEYWORDS)

    @staticmethod
    def derive_connection_status(local_link_status: str | None, peer_link_status: str | None,
                                  local_port_name: str | None = None, peer_port_name: str | None = None) -> str:
        local_is_logical = NetworkPort.is_logical_port(local_port_name)
        peer_is_logical = NetworkPort.is_logical_port(peer_port_name)

        if local_is_logical and peer_is_logical:
            return "active"

        if not local_is_logical and (local_link_status or "").lower() != "up":
            return "inactive"
        if not peer_is_logical and (peer_link_status or "").lower() != "up":
            return "inactive"

        return "active"

    @staticmethod
    def derive_usage_status(link_status: str | None, port_name: str | None = None) -> str:
        if not link_status:
            return "free"
        ls = link_status.lower()
        if ls in ("admin_down", "administratively down", "*down"):
            return "disabled"
        if ls == "up":
            if port_name:
                pn = port_name.lower()
                if any(kw in pn for kw in NetworkPort.LOGICAL_PORT_KEYWORDS):
                    return "free"
            return "occupied"
        return "free"

    def to_dict(self, include_relations=False):
        base = super().to_dict(include_relations=include_relations)
        for field in ("link_status", "mac", "ip_address", "customer_id",
                      "raw_info", "data_source", "last_collected_at", "usage_status"):
            if field not in base:
                base[field] = getattr(self, field, None)
        base["status"] = base.get("link_status")
        base["customer_name"] = self.customer.customer_name if self.customer else None
        return base
