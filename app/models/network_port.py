from __future__ import annotations
# -*- coding: utf-8 -*-
"""
网络设备端口 ORM 模型

定义网络设备端口拓扑关系表（network_ports）。
统一端口表：同时承载手动维护端口和自动采集端口数据。
"""
import json

from sqlalchemy import Integer, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, MEDIUMTEXT
from extensions import db


class NetworkPort(BaseModel):
    """网络设备端口表 — network_ports

    统一端口表，同时承载：
    - 手动维护端口（设备管理模块创建，data_source='manual'）
    - 自动采集端口（SSH 采集写入，data_source='auto'）
    - 混合端口（既有手动数据又有采集数据，data_source='hybrid'）
    """
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
    description = db.Column(MEDIUMTEXT, comment="端口描述")

    link_status = db.Column(String(50), comment="链路状态(up/down/disabled)")
    mac = db.Column(String(17), comment="MAC地址")
    ip_address = db.Column(String(45), comment="端口主IP(deprecated,权威源为switch_port_ips)")
    customer_id = db.Column(db.BigInteger, ForeignKey("customers.id"), comment="客户ID")
    raw_info = db.Column(db.JSON, comment="原始端口信息(JSON)")
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
    def normalize_raw_info(value):
        """将任意 raw_info 入参归一为可安全写入 JSON 列的值（dict/list/None）。

        JSON 列不接受空串（MySQL: "Invalid JSON text"），且写入端历史上既有
        传 dict、也有传 `json.dumps(...)` 字符串的两套写法，这里统一收敛：

        - None / 空串 / 空白串  -> None（NULL）
        - dict / list           -> 原样
        - 合法 JSON 字符串      -> 解析后的对象（避免二次编码成 JSON 字符串）
        - 其他标量（含非 JSON 文本）-> 原样返回，由 JSON 类型编码为 JSON 标量
        """
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return json.loads(s)
            except (ValueError, TypeError):
                return value
        return value

    @staticmethod
    def is_logical_port(port_name: str | None) -> bool:
        """判断端口是否为逻辑端口

        逻辑端口（Eth-Trunk/Vlanif/LoopBack 等）不参与连接状态推导，
        因为逻辑端口的 link_status 不代表物理链路状态。

        Args:
            port_name: 端口名称

        Returns:
            True 表示逻辑端口，False 表示物理端口
        """
        if not port_name:
            return False
        pn = port_name.lower()
        return any(kw in pn for kw in NetworkPort.LOGICAL_PORT_KEYWORDS)

    @staticmethod
    def derive_connection_status(local_link_status: str | None, peer_link_status: str | None,
                                  local_port_name: str | None = None, peer_port_name: str | None = None) -> str:
        """根据两端端口的物理链路状态推导连接状态

        推导规则：
        - 逻辑端口不参与推导（其 link_status 不代表物理链路）
        - 两端都是逻辑端口 → active（逻辑端口互联不受物理状态约束）
        - 任一物理端口非 up → inactive（物理链路断开）
        - 所有物理端口都 up → active

        Args:
            local_link_status: 本机端口链路状态 (up/down/...)
            peer_link_status: 对端端口链路状态 (up/down/...)
            local_port_name: 本机端口名称（用于判断逻辑端口）
            peer_port_name: 对端端口名称（用于判断逻辑端口）

        Returns:
            "active" 或 "inactive"
        """
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
        """根据链路状态和端口名称推导占用状态

        映射规则：
        - admin_down → disabled（管理关闭=禁用，逻辑/物理端口均适用）
        - 逻辑端口（Eth-Trunk/Vlanif/LoopBack 等）up → free（在线但不等于被占用）
        - 物理端口 up → occupied（在线=已被使用）
        - down / 其他 / None → free
        """
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
        """序列化，包含采集字段及前端兼容别名"""
        base = super().to_dict(include_relations=include_relations)
        for field in ("link_status", "mac", "ip_address", "customer_id",
                      "raw_info", "data_source", "last_collected_at", "usage_status"):
            if field not in base:
                base[field] = getattr(self, field, None)
        raw = base.get("raw_info")
        if isinstance(raw, (dict, list)):
            base["raw_info"] = json.dumps(raw, ensure_ascii=False)
        base["status"] = base.get("link_status")
        base["customer_name"] = self.customer.customer_name if self.customer else None
        return base
