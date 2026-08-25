"""交换机路由条目模型（Phase 4: ip_network 拆分）

ip_networks 只管理网段（CIDR+gateway+归属），
路由条目统一归 switch_routes。
"""
import struct
import socket

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


def _cidr_to_ints(cidr: str):
    try:
        ip_part, prefix_part = cidr.rsplit("/", 1)
        network_int = struct.unpack("!I", socket.inet_aton(ip_part))[0]
        prefix = int(prefix_part)
        return network_int, prefix
    except (OSError, ValueError, struct.error):
        return None, None


class IPNetwork(BaseModel):
    __tablename__ = "ip_networks"
    __table_args__ = (
        Index("idx_net_switch", "switch_id"),
        Index("idx_net_room", "room_id"),
        Index("idx_net_customer", "customer_id"),
        Index("idx_net_network_int", "network_int"),
        Index("uk_net_switch_port_room", "network", "switch_id", "port", "room_id", unique=True),
        {"comment": "IP网段规划(仅网段信息)"},
    )

    network = db.Column(db.String(45), nullable=False, comment="网段地址(如192.168.1.0/24)")
    switch_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="所属交换机")
    port = db.Column(db.String(50), nullable=False, server_default="", comment="端口名(空串=无端口)")
    customer_id = db.Column(db.BigInteger, db.ForeignKey("customers.id"), comment="客户ID")
    gateway = db.Column(db.String(45), comment="网关地址")
    notes = db.Column(db.String(255), nullable=True, comment="人工备注（文本）")
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, comment="机房ID")
    network_int = db.Column(db.Integer, nullable=True, comment="网段起始IP整数(INET_ATON)")
    prefix = db.Column(db.SmallInteger, nullable=True, comment="子网掩码位数(如24)")

    def __init__(self, **kwargs):
        if "network" in kwargs:
            if "network_int" not in kwargs or "prefix" not in kwargs:
                ni, pf = _cidr_to_ints(kwargs["network"])
                if "network_int" not in kwargs and ni is not None:
                    kwargs["network_int"] = ni
                if "prefix" not in kwargs and pf is not None:
                    kwargs["prefix"] = pf
        super().__init__(**kwargs)

    switch = relationship("Device", foreign_keys=[switch_id], lazy="joined")
    room = relationship("Room", foreign_keys=[room_id], lazy="joined")
    customer = relationship("Customer", foreign_keys=[customer_id], lazy="joined")

    def to_dict(self, exclude=None, include_relations=False):
        result = super().to_dict(exclude=exclude)
        result['ip_network'] = self.network
        return result


class SwitchRoute(BaseModel):
    __tablename__ = "switch_routes"
    __table_args__ = (
        Index("uk_route_switch_dest_nexthop_type", "switch_id", "destination", "nexthop", "route_type", unique=True),
        Index("idx_route_dest_int", "destination_int", "destination_prefix"),
        {"comment": "交换机路由条目"},
    )

    switch_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="交换机设备ID")
    destination = db.Column(db.String(45), nullable=False, comment="目标网段")
    nexthop = db.Column(db.String(45), nullable=False, comment="下一跳IP")
    route_type = db.Column(db.SmallInteger, nullable=False, default=0, comment="路由类型(RouteNotes): 0=默认 1=互联 2=子网 3=网络 4=黑洞 5=网关 6=主机")
    port = db.Column(db.String(50), comment="出接口")
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), comment="机房ID FK→rooms")
    network_id = db.Column(db.BigInteger, db.ForeignKey("ip_networks.id"), comment="所属网段 FK→ip_networks")
    customer_id = db.Column(db.BigInteger, db.ForeignKey("customers.id"), comment="客户ID FK→customers")
    notes = db.Column(db.String(255), comment="备注")
    destination_int = db.Column(db.Integer, nullable=True, comment="目标网段起始IP整数(INET_ATON)")
    destination_prefix = db.Column(db.SmallInteger, nullable=True, comment="目标网段前缀长度(如24)")
    nexthop_int = db.Column(db.Integer, nullable=True, comment="下一跳IP整数(INET_ATON)")

    def __init__(self, **kwargs):
        if "destination" in kwargs:
            ni, pf = _cidr_to_ints(kwargs["destination"])
            if "destination_int" not in kwargs and ni is not None:
                kwargs["destination_int"] = ni
            if "destination_prefix" not in kwargs and pf is not None:
                kwargs["destination_prefix"] = pf
        if "nexthop" in kwargs and "nexthop_int" not in kwargs:
            try:
                kwargs["nexthop_int"] = struct.unpack("!I", socket.inet_aton(kwargs["nexthop"]))[0]
            except (OSError, struct.error):
                pass
        super().__init__(**kwargs)

    def to_dict(self, exclude=None, include_relations=False):
        return super().to_dict(exclude=exclude)
