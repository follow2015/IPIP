# -*- coding: utf-8 -*-
"""
IP 相关 ORM 模型

定义 IPManager、IPBanRecord。
IP交换机信息见 switch_credentials.py（IPSwitchInfo→ip_switch_info）。
路由信息见 switch_route.py（IPNetwork→ip_networks, SwitchRoute→switch_routes）。
"""

from sqlalchemy import (
    BigInteger, Integer, String, SmallInteger, DateTime,
    ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.orm import relationship
import struct
import socket

from sqlalchemy.dialects.mysql import INTEGER
from app.models.base import BaseModel, TINYINT
from app.core.enums import IPStatus
from extensions import db


def ip_to_int(ip_address: str) -> int:
    """将 IPv4 地址转换为整数（等价于 MySQL INET_ATON）

    Args:
        ip_address: IPv4 地址字符串

    Returns:
        int: 整数表示，无效 IP 返回 None
    """
    try:
        return struct.unpack("!I", socket.inet_aton(ip_address))[0]
    except (OSError, struct.error):
        return None

class IPManager(BaseModel):
    """IP地址管理主表 — ip_manager

    记录每个 IP 的状态、客户归属等信息。
    """
    __tablename__ = "ip_addresses"
    __table_args__ = (
        UniqueConstraint("ip_address", "room_id", name="uq_ip_room"),
        Index("ix_ip_manager_status", "status"),
        Index("ix_ip_manager_room", "room_id"),
        Index("ix_ip_int", "ip_int"),  # ip_int 范围查询索引
        Index("ix_ip_last_active", "last_active_at"),  # 陈旧度清理索引
        {"extend_existing": True},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    ip_address = db.Column(String(45), nullable=False, comment="IP地址")
    ip_int = db.Column(INTEGER(unsigned=True), nullable=True, comment="IP整数表示(INET_ATON),用于范围查询")
    customer_id = db.Column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True, comment="客户ID",
    )
    status = db.Column(
        TINYINT(), default=IPStatus.UNUSED, nullable=False, comment="IP状态",
    )
    notes = db.Column(String(255), nullable=True, comment="备注")
    room_id = db.Column(
        Integer, ForeignKey("rooms.id"), nullable=True, comment="机房ID",
    )
    last_active_at = db.Column(
        DateTime, nullable=True, comment="最近一次被观测到活跃的时间（陈旧度清理用）",
    )

    def __init__(self, **kwargs):
        """自动填充 ip_int"""
        if "ip_address" in kwargs and "ip_int" not in kwargs:
            kwargs["ip_int"] = ip_to_int(kwargs["ip_address"])
        super().__init__(**kwargs)

    ip_switch_info = relationship(
        "IPSwitchInfo",
        primaryjoin="IPManager.ip_address==IPSwitchInfo.ip_address",
        foreign_keys="[IPSwitchInfo.ip_address]",
        uselist=False,
        viewonly=True,
    )

    def is_banned(self) -> bool:
        """判断当前 IP 是否处于封禁状态（含封禁中）"""
        return self.status in (IPStatus.BANNED, IPStatus.PENDING_BAN)

    def to_dict(self, exclude=None, include_relations=False):
        """序列化，增加 status 文本描述"""
        result = super().to_dict(exclude=exclude, include_relations=include_relations)
        result["status_text"] = {
            0: "活跃", 1: "非活跃", 2: "封禁", 3: "未使用",
            4: "封禁中", 5: "解封中",
        }.get(self.status, "未知")
        return result

class IPBanRecord(BaseModel):
    """IP封禁记录表 — ip_ban_records

    记录封禁元数据，支持黑洞路由(route)和静态ARP(arp)两种封禁方式。
    """
    __tablename__ = "ip_ban_records"
    __table_args__ = (
        Index("idx_ban_ip_room_active", "ip_address", "room_id", "is_active"),
        {"extend_existing": True},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    ip_address = db.Column(String(45), nullable=False, comment="IP地址")
    ip_int = db.Column(INTEGER(unsigned=True), nullable=True, comment="IP整数表示(INET_ATON),用于范围查询")
    room_id = db.Column(Integer, ForeignKey("rooms.id"), nullable=False, comment="机房ID")
    switch_id = db.Column(
        db.BigInteger, ForeignKey("devices.id"), nullable=False, comment="执行封禁的交换机ID",
    )
    ban_mode = db.Column(String(16), nullable=False, default="route", comment="封禁方式(route/arp)")
    ban_meta = db.Column(db.JSON, nullable=True, comment="封禁元数据(JSON,含mac_address/vlan_id等)")
    action = db.Column(
        db.Enum("ban", "unban", name="ban_action_enum"),
        nullable=False, default="ban", comment="封禁动作",
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment="是否活跃")
    operator_id = db.Column(
        db.BigInteger, ForeignKey("users.id"),
        nullable=True, comment="操作人ID",
    )
    created_at = db.Column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    def __init__(self, **kwargs):
        """自动填充 ip_int"""
        if "ip_address" in kwargs and "ip_int" not in kwargs:
            kwargs["ip_int"] = ip_to_int(kwargs["ip_address"])
        super().__init__(**kwargs)

