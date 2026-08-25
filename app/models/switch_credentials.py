"""交换机凭据模型（Phase 3: 统一交换机体系）

凭据表只保留认证信息，拓扑字段迁移至 devices 表，
采集缓存字段迁移至 SwitchStatusCache 表。
"""
import struct
import socket

from app.core.enums import SwitchDeviceTypeCode
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


def _ip_to_int(ip_address: str) -> int:
    """将 IPv4 地址转换为整数（等价于 MySQL INET_ATON）"""
    try:
        return struct.unpack("!I", socket.inet_aton(ip_address))[0]
    except (OSError, struct.error):
        return None


def _mask_to_prefix(subnet_mask: str) -> int:
    """将点分十进制子网掩码转换为 CIDR 前缀长度

    Args:
        subnet_mask: 点分十进制掩码，如 '255.255.255.0'

    Returns:
        前缀长度整数（如 24），解析失败返回 None
    """
    if not subnet_mask:
        return None
    try:
        import ipaddress
        return ipaddress.IPv4Network(f"0.0.0.0/{subnet_mask}", strict=False).prefixlen
    except (ValueError, TypeError):
        return None


class SwitchCredentials(BaseModel):
    """交换机凭据 - 1:1 扩展 devices

    仅保留认证/连接信息。拓扑属性（switch_role, layer, uplink, core, room_id, port_num）
    已迁移至 devices 表。采集缓存（device_version, device_uptime）已迁移至 SwitchStatusCache。
    """
    __tablename__ = "switch_credentials"
    __table_args__ = (
        Index("uk_switch_device", "device_id", unique=True),
        {"comment": "交换机凭据(1:1扩展devices,仅认证信息)"},
    )

    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="1:1关联设备")
    ip = db.Column(db.String(45), comment="SSH管理IP(与devices.management_ip同步,采集连接唯一数据源)")
    port = db.Column(db.SmallInteger, default=22, comment="SSH/Telnet端口")
    username = db.Column(db.String(64), comment="登录用户名")
    password = db.Column(db.String(512), comment="AES-256-GCM加密后密码")
    protocol = db.Column(db.String(10), default='ssh', comment="连接协议")
    authentication_method = db.Column(db.String(32), comment="认证方式")
    device_type = db.Column(db.String(20), comment="驱动类型:huawei/h3c/cisco")
    has_ssh = db.Column(db.Boolean, default=True, comment="是否有SSH权限")
    mac_address = db.Column(db.String(17), comment="管理口MAC")

    device = relationship("Device", foreign_keys=[device_id], backref=db.backref("switch_credential", uselist=False, lazy="joined"), lazy="joined")

    def get_netmiko_device_type(self) -> str:
        """返回 netmiko 兼容的设备类型字符串

        将内部 device_type 映射为 netmiko 驱动名，
        并根据协议附加 _telnet 后缀（忽略大小写）。
        """
        type_map = {
            SwitchDeviceTypeCode.H3C: "hp_comware",
            SwitchDeviceTypeCode.HUAWEI: "huawei",  # netmiko 驱动名恰好与枚举值相同
            SwitchDeviceTypeCode.CISCO: "cisco_ios",
        }
        dt = type_map.get(self.device_type or "", self.device_type or "")
        if (self.protocol or "").lower() == "telnet":
            dt += "_telnet"
        return dt

    def to_dict(self, exclude=None, include_relations=False):
        """序列化

        Args:
            exclude: 要排除的字段名集合（如 {'password', 'username'}）。
                     password 字段始终被排除（安全考虑）。
            include_relations: 是否包含关联对象（暂未实现）。
        """
        _exclude = {'password'}
        if exclude:
            _exclude.update(exclude)
        result = super().to_dict(exclude=list(_exclude))
        return result


class SwitchStatusCache(BaseModel):
    """交换机采集状态缓存 - 1:1 扩展 devices

    存储由 SSH 采集写入的运行时状态信息，
    与凭据表分离，避免安全审计时暴露采集缓存。
    """
    __tablename__ = "switch_status_cache"
    __table_args__ = (
        Index("uk_ssc_device", "device_id", unique=True),
        {"comment": "交换机采集状态缓存(1:1扩展devices)"},
    )

    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="1:1关联设备")
    device_version = db.Column(db.String(255), comment="设备版本(采集缓存)")
    device_uptime = db.Column(db.String(255), comment="运行时长(采集缓存)")

    device = relationship("Device", foreign_keys=[device_id], backref=db.backref("status_cache", uselist=False, lazy="joined"), lazy="joined")

    def to_dict(self, exclude=None, include_relations=False):
        """序列化"""
        return super().to_dict(exclude=exclude)


class IPSwitchInfo(BaseModel):
    """IP交换机信息表 — ip_switch_info

    替代旧 ip_info 表，记录 IP 与交换机端口的关联信息。
    """
    __tablename__ = "ip_switch_info"
    __table_args__ = (
        UniqueConstraint("ip_address", "room_id", name="uk_isi_ip_room"),
        Index("idx_isi_switch", "switch_id"),
        Index("idx_isi_room", "room_id"),
        Index("idx_isi_ip_int", "ip_int"),  # ip_int 范围查询索引
        {"comment": "IP交换机信息(替代旧ip_info)"},
    )

    ip_address = db.Column(db.String(45), nullable=False, comment="IP地址")
    ip_int = db.Column(db.BigInteger, nullable=True, comment="IP整数表示(INET_ATON),用于范围查询")
    mac_address = db.Column(db.String(17), comment="MAC地址")
    switch_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="交换机设备ID")
    port = db.Column(db.String(50), comment="端口名")
    port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("network_ports.id"),
        comment="端口ID FK→network_ports",
    )
    vlan_id = db.Column(db.SmallInteger, comment="VLAN ID")
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), comment="机房ID")

    def __init__(self, **kwargs):
        """自动填充 ip_int"""
        if "ip_address" in kwargs and "ip_int" not in kwargs:
            kwargs["ip_int"] = _ip_to_int(kwargs["ip_address"])
        super().__init__(**kwargs)

    switch = relationship("Device", foreign_keys=[switch_id])
    room = relationship("Room", foreign_keys=[room_id])

    def to_dict(self, exclude=None, include_relations=False):
        """序列化"""
        return super().to_dict(exclude=exclude)


class SwitchPortIP(BaseModel):
    """交换机端口IP"""
    __tablename__ = "switch_port_ips"
    __table_args__ = (
        Index("idx_spi_device", "device_id"),
        Index("idx_spi_port", "port_id"),
        Index("idx_spi_device_vlan", "device_id", "vlan"),
        Index("idx_spi_ip_int", "ip_int"),  # ip_int 范围查询索引
        UniqueConstraint("device_id", "port_name", "ip_address", name="uk_spi_device_port_ip"),
        {"comment": "交换机端口IP"},
    )

    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="交换机设备ID")
    port_id = db.Column(db.BigInteger, db.ForeignKey("network_ports.id"), comment="端口ID")
    port_name = db.Column(db.String(255), nullable=False, comment="端口名")
    ip_address = db.Column(db.String(45), nullable=False, comment="IP地址")
    ip_int = db.Column(db.BigInteger, nullable=True, comment="IP整数表示(INET_ATON),用于范围查询")
    subnet_mask = db.Column(db.String(20), server_default="255.255.255.0", comment="子网掩码(点分十进制)")
    prefix = db.Column(db.SmallInteger, nullable=True, comment="子网掩码位数(如24,从subnet_mask转换)")
    is_primary = db.Column(db.Boolean, server_default="1", comment="是否为主IP")
    vlan = db.Column(db.Integer, comment="VLAN ID(逻辑关联vlans.vlan_id,不加FK因采集数据可能引用不存在的VLAN)")

    def __init__(self, **kwargs):
        """自动填充 ip_int 和 prefix"""
        if "ip_address" in kwargs and "ip_int" not in kwargs:
            kwargs["ip_int"] = _ip_to_int(kwargs["ip_address"])
        if "subnet_mask" in kwargs and "prefix" not in kwargs:
            kwargs["prefix"] = _mask_to_prefix(kwargs["subnet_mask"])
        super().__init__(**kwargs)

    def to_dict(self, exclude=None, include_relations=False):
        """序列化"""
        result = super().to_dict(exclude=exclude)
        result['switch_id'] = self.device_id
        result['port'] = self.port_name
        return result
