# -*- coding: utf-8 -*-
"""
设备模型模块
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.enums import DeviceStatus
from app.models.base import BaseModel
from extensions import db


class Device(BaseModel):

    __tablename__ = "devices"
    __soft_delete__ = True
    __table_args__ = (
        Index("idx_device_type_subtype", "device_type", "device_subtype"),
        Index("idx_device_status_cabinet", "status", "cabinet_id"),
        Index("idx_device_customer_status", "customer_id", "status"),
        Index("idx_device_name", "device_name"),
        Index("idx_device_created_at", "created_at"),
        Index("idx_device_deleted", "deleted_at"),
        CheckConstraint("status BETWEEN 0 AND 7", name="ck_device_status_range"),
        {"comment": "设备信息核心表（身份/位置/状态）"},
    )

    device_name = db.Column(db.String(100), nullable=False, comment="设备名称")
    device_type = db.Column(db.String(50), nullable=False, comment="设备主类型: server/network/other")
    device_subtype = db.Column(db.String(20), comment="设备子类型: standalone/chassis/node/storage/gpu/switch/router/firewall/pdu/ups")
    device_model = db.Column(db.String(100), comment="设备型号")
    brand = db.Column(db.String(100), comment="品牌厂商")
    serial_number = db.Column(db.String(255), comment="序列号")
    hostname = db.Column(db.String(128), comment="主机名")
    metric_template_group_id = db.Column(
        db.BigInteger,
        ForeignKey("monitor_metric_template_groups.id", ondelete="SET NULL"),
        nullable=True,
        comment="显式关联的指标模板组ID（可空）。为空时按 device_type+brand+协议自动匹配模板组；"
        "选择后监控数据页优先展示该组包含的指标",
    )

    management_ip = db.Column(db.String(50), comment="管理IP(同步自switch_credentials.ip,展示用)")
    mac_address = db.Column(db.String(17), comment="主MAC地址")

    cabinet_id = db.Column(db.BigInteger, ForeignKey("cabinets.id"), comment="机柜ID")
    u_position = db.Column(db.Integer, comment="U位起始位置")
    height_u = db.Column(db.Integer, default=1, comment="占用U位数量")
    power = db.Column(db.Float, comment="额定功率(W)")

    status = db.Column(
        db.SmallInteger,
        default=DeviceStatus.AVAILABLE,
        comment="设备状态: 0-报废 1-可用 2-在线 3-离线 4-维护中 5-预留",
    )
    responsible_person = db.Column(db.BigInteger, ForeignKey("users.id", ondelete="SET NULL"), comment="责任人ID")
    notes = db.Column(db.Text, comment="备注")

    customer_id = db.Column(db.BigInteger, ForeignKey("customers.id"), comment="客户ID")

    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间(NULL=未删除)")

    cabinet = relationship(
        "Cabinet", foreign_keys=[cabinet_id],
        back_populates="devices", lazy="selectin", overlaps="cabinet_rel",
    )
    customer = relationship(
        "Customer", foreign_keys=[customer_id],
        back_populates="devices", lazy="selectin",
    )
    responsible_person_user = relationship(
        "User", foreign_keys=[responsible_person],
        lazy="selectin",
    )

    hardware = relationship(
        "DeviceHardware", back_populates="device", uselist=False, lazy="selectin",
        cascade="all, delete-orphan",
    )
    asset = relationship(
        "DeviceAsset", back_populates="device", uselist=False, lazy="selectin",
        cascade="all, delete-orphan",
    )
    server_ext = relationship(
        "DeviceServerExt", foreign_keys="DeviceServerExt.device_id",
        back_populates="device", uselist=False, lazy="selectin",
        cascade="all, delete-orphan",
    )
    switch_ext = relationship(
        "DeviceSwitchExt", foreign_keys="DeviceSwitchExt.device_id",
        back_populates="device", uselist=False, lazy="selectin",
        cascade="all, delete-orphan",
    )

    connections = relationship(
        "DeviceConnection", foreign_keys="DeviceConnection.device_id",
        back_populates="device", lazy="select", cascade="all, delete-orphan",
    )
    switch_connections = relationship(
        "DeviceConnection", foreign_keys="DeviceConnection.switch_device_id",
        back_populates="switch_device", lazy="select",
        cascade="save-update, merge",
    )

    storage_devices = relationship(
        "DeviceStorage", back_populates="device",
        lazy="select", cascade="all, delete-orphan",
    )
    nics_ports = relationship(
        "DeviceNicsPort", back_populates="device",
        lazy="select", cascade="all, delete-orphan",
    )


    def _ensure_server_ext(self):
        if not self.server_ext:
            from app.models.device_server_ext import DeviceServerExt
            self.server_ext = DeviceServerExt()

    @property
    def parent_device_id(self) -> Optional[int]:
        return self.server_ext.parent_device_id if self.server_ext else None

    @parent_device_id.setter
    def parent_device_id(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.parent_device_id = value

    @property
    def is_chassis(self) -> Optional[bool]:
        return self.server_ext.is_chassis if self.server_ext else None

    @is_chassis.setter
    def is_chassis(self, value: Optional[bool]):
        self._ensure_server_ext()
        self.server_ext.is_chassis = value

    @property
    def node_position(self) -> Optional[int]:
        return self.server_ext.node_position if self.server_ext else None

    @node_position.setter
    def node_position(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.node_position = value

    @property
    def node_row(self) -> Optional[int]:
        return self.server_ext.node_row if self.server_ext else None

    @node_row.setter
    def node_row(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.node_row = value

    @property
    def node_col(self) -> Optional[int]:
        return self.server_ext.node_col if self.server_ext else None

    @node_col.setter
    def node_col(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.node_col = value

    @property
    def total_nodes(self) -> Optional[int]:
        return self.server_ext.total_nodes if self.server_ext else None

    @total_nodes.setter
    def total_nodes(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.total_nodes = value

    @property
    def node_rows(self) -> Optional[int]:
        return self.server_ext.node_rows if self.server_ext else None

    @node_rows.setter
    def node_rows(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.node_rows = value

    @property
    def node_cols(self) -> Optional[int]:
        return self.server_ext.node_cols if self.server_ext else None

    @node_cols.setter
    def node_cols(self, value: Optional[int]):
        self._ensure_server_ext()
        self.server_ext.node_cols = value

    @property
    def node_naming_pattern(self) -> Optional[str]:
        return self.server_ext.node_naming_pattern if self.server_ext else None

    @node_naming_pattern.setter
    def node_naming_pattern(self, value: Optional[str]):
        self._ensure_server_ext()
        self.server_ext.node_naming_pattern = value

    def _ensure_switch_ext(self):
        if not self.switch_ext:
            from app.models.device_switch_ext import DeviceSwitchExt
            self.switch_ext = DeviceSwitchExt()

    @property
    def switch_role(self) -> Optional[int]:
        return self.switch_ext.switch_role if self.switch_ext else None

    @switch_role.setter
    def switch_role(self, value: Optional[int]):
        self._ensure_switch_ext()
        self.switch_ext.switch_role = value

    @property
    def layer(self) -> Optional[int]:
        return self.switch_ext.layer if self.switch_ext else None

    @layer.setter
    def layer(self, value: Optional[int]):
        self._ensure_switch_ext()
        self.switch_ext.layer = value

    @property
    def uplink_device_id(self) -> Optional[int]:
        return self.switch_ext.uplink_device_id if self.switch_ext else None

    @property
    def uplink_port_ids(self) -> Optional[list]:
        return self.switch_ext.uplink_port_ids if self.switch_ext else None

    @property
    def core_device_id(self) -> Optional[int]:
        return self.switch_ext.core_device_id if self.switch_ext else None

    @property
    def port_num(self) -> Optional[int]:
        return self.switch_ext.port_num if self.switch_ext else None

    @property
    def is_active(self) -> bool:
        return self.status != DeviceStatus.SCRAPPED

    @property
    def status_name(self) -> str:
        return DeviceStatus.STATUS_NAMES.get(self.status, "未知")

    @property
    def cabinet_number(self) -> Optional[str]:
        if self.cabinet_id and self.cabinet:
            return self.cabinet.cabinet_number
        return None

    def get_ip_list(self) -> str:
        if self.hardware and self.hardware.ip_address:
            return self.hardware.get_ip_list()
        return ""

    def set_ip_list(self, ip_string: str) -> None:
        if not self.hardware:
            from app.models.device_hardware import DeviceHardware
            self.hardware = DeviceHardware(device_id=self.id)
        self.hardware.set_ip_list(ip_string)

    def get_primary_ip(self) -> Optional[str]:
        if self.hardware:
            return self.hardware.get_primary_ip()
        return None

    def _ensure_hardware(self):
        if not self.hardware:
            from app.models.device_hardware import DeviceHardware
            self.hardware = DeviceHardware(device_id=self.id)

    def _ensure_asset(self):
        if not self.asset:
            from app.models.device_asset import DeviceAsset
            self.asset = DeviceAsset(device_id=self.id)

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        data = super().to_dict(exclude=exclude)

        if self.hardware:
            hw = self.hardware
            data["cpu"] = hw.cpu
            data["cpu_way"] = hw.cpu_way
            data["cpu_cores"] = hw.cpu_cores
            data["memory"] = hw.memory
            data["memory_size_gb"] = hw.memory_size_gb
            data["storage"] = hw.storage_summary
            data["storage_summary"] = hw.storage_summary
            data["os_version"] = hw.os_version
            data["ipmi_address"] = hw.ipmi_address
            data["ip_address"] = hw.get_ip_list()
            data["cpu_template_id"] = hw.cpu_template_id
            data["memory_template_id"] = hw.memory_template_id
            data["memory_dimm_count"] = hw.memory_dimm_count
            data["gpu"] = hw.gpu
            data["gpu_count"] = hw.gpu_count
            data["gpu_template_id"] = hw.gpu_template_id
            if hw.ipmi_username:
                data["ipmi_username"] = hw.ipmi_username
            data["has_ipmi_password"] = bool(hw.ipmi_password)
        else:
            data["cpu"] = None
            data["cpu_way"] = None
            data["memory"] = None
            data["storage"] = None
            data["os_version"] = None
            data["ipmi_address"] = None
            data["ip_address"] = ""

        if self.asset:
            a = self.asset
            data["asset_number"] = a.asset_number
            data["supplier"] = a.supplier
            data["supplier_contact"] = a.supplier_contact
            data["contract_number"] = a.contract_number
            data["purchase_date"] = a.purchase_date.isoformat() if a.purchase_date else None
            data["purchase_price"] = float(a.purchase_price) if a.purchase_price else None
            data["invoice_number"] = a.invoice_number
            data["warranty_start"] = a.warranty_start.isoformat() if a.warranty_start else None
            data["warranty_end"] = a.warranty_end.isoformat() if a.warranty_end else None
            data["warranty_type"] = a.warranty_type
            data["online_date"] = a.online_date.isoformat() if a.online_date else None
            data["offline_date"] = a.offline_date.isoformat() if a.offline_date else None
            data["lifecycle_years"] = a.lifecycle_years

        data["cabinet_number"] = self.cabinet_number
        data["status_name"] = self.status_name
        if self.customer:
            data["customer_name"] = self.customer.customer_name
        if self.cabinet and self.cabinet.room:
            data["room_id"] = self.cabinet.room_id
            data["room_name"] = self.cabinet.room.name
        if self.power is not None:
            data["power"] = float(self.power)
        
        if self.responsible_person_user:
            data["responsible_person_name"] = self.responsible_person_user.name
            data["responsible_person_username"] = self.responsible_person_user.username

        if self.server_ext:
            se = self.server_ext
            data["parent_device_id"] = se.parent_device_id
            data["is_chassis"] = se.is_chassis
            data["node_position"] = se.node_position
            data["node_row"] = se.node_row
            data["node_col"] = se.node_col
            data["total_nodes"] = se.total_nodes
            data["node_rows"] = se.node_rows
            data["node_cols"] = se.node_cols
            data["node_naming_pattern"] = se.node_naming_pattern
            if se.is_chassis and se.node_rows and se.node_cols:
                data["total_nodes"] = se.node_rows * se.node_cols
            if se.parent_device_id and se.parent_device:
                data["parent_u_position"] = se.parent_device.u_position
                data["parent_height_u"] = se.parent_device.height_u

        if self.switch_ext:
            swe = self.switch_ext
            data["switch_role"] = swe.switch_role
            data["layer"] = swe.layer
            data["uplink_device_id"] = swe.uplink_device_id
            data["uplink_port_ids"] = swe.uplink_port_ids
            data["core_device_id"] = swe.core_device_id
            data["port_num"] = swe.port_num

        if self.device_type == "network" and self.switch_credential:
            sc = self.switch_credential
            data["switch_credential"] = {
                "id": sc.id,
                "ip": sc.ip,
                "has_ssh": sc.has_ssh,
                "device_type": sc.device_type,
                "port_num": sc.port,
                "username": sc.username,
                "protocol": sc.protocol,
                "authentication_method": sc.authentication_method,
            }
            if self.switch_ext:
                data["switch_credential"]["switch_role"] = self.switch_ext.switch_role
                data["switch_credential"]["layer"] = self.switch_ext.layer
                data["switch_credential"]["uplink_device_id"] = self.switch_ext.uplink_device_id
                data["switch_credential"]["uplink_port_ids"] = self.switch_ext.uplink_port_ids
                data["switch_credential"]["core_device_id"] = self.switch_ext.core_device_id
                data["switch_credential"]["port_num"] = self.switch_ext.port_num
            data["switch_credential"]["room_id"] = self.cabinet.room_id if self.cabinet else None
            if self.status_cache:
                data["switch_credential"]["device_version"] = self.status_cache.device_version
                data["switch_credential"]["device_uptime"] = self.status_cache.device_uptime

        return data

    def to_dict_with_parent(self, parent_name: str = None) -> Dict[str, Any]:
        data = self.to_dict()
        if parent_name:
            data["parent_device_name"] = parent_name
        return data

    def __repr__(self) -> str:
        return f"<Device(id={self.id}, name='{self.device_name}', status={self.status})>"
