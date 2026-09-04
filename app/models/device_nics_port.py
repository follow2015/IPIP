# -*- coding: utf-8 -*-
"""
设备网卡端口模型

管理所有设备的网卡端口信息,包括服务器网卡端口和交换机端口。
"""
from typing import Any, Dict

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class DeviceNicsPort(BaseModel):
    """设备网卡端口模型
    
    统一管理所有设备的端口信息:
    - 服务器设备的网卡端口
    - 交换机设备的端口
    - 其他网络设备的端口
    """
    
    __tablename__ = "device_nics_port"
    __table_args__ = (
        Index("uk_device_nic_port", "device_id", "nic_number", "port_number", unique=True),  # 前缀覆盖 idx_device_id
        Index("idx_port_type_speed", "port_type", "port_speed"),
        {"comment": "设备网卡端口表"},
    )
    
    device_id = db.Column(
        db.BigInteger,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="设备ID"
    )
    
    nic_number = db.Column(db.Integer, nullable=False, comment="网卡编号")
    nic_name = db.Column(db.String(100), nullable=False, default="", comment="网卡名称")
    template_id = db.Column(db.BigInteger, db.ForeignKey('component_templates.id',
                      ondelete='SET NULL'), nullable=True, index=True,
                      comment='网卡模板ID')
    port_number = db.Column(db.Integer, nullable=False, comment="端口编号")
    port_name = db.Column(db.String(50), comment="端口名称(如eth0, ens192等)")
    mac_address = db.Column(db.String(17), nullable=True, comment="MAC地址")
    
    port_type = db.Column(db.String(20), nullable=False, comment="端口类型(RJ45/SFP/SFP+/SFP28/QSFP+/QSFP28/QSFP56/QSFP-DD)")
    port_speed = db.Column(db.String(20), nullable=False, comment="端口速率(1G/10G/100G)")
    port_status = db.Column(
        db.String(20), default='free',
        comment="端口状态(free=空闲/occupied=已占用/disabled=禁用/error=错误)"
    )
    
    description = db.Column(db.String(200), comment="端口描述")
    
    device = relationship(
        "Device",
        foreign_keys=[device_id],
        back_populates="nics_ports",
        lazy="joined"
    )

    template    = relationship('ComponentTemplate', foreign_keys=[template_id], lazy='select')
    
    source_connections = relationship(
        "DeviceConnection",
        foreign_keys="DeviceConnection.device_nics_port_id",
        back_populates="nics_port",
        lazy="select"
    )
    
    @property
    def display_name(self) -> str:
        """获取端口的显示名称

        优先使用 nic_name（如模板生成的 X710-DA2:端口1），
        否则回退到默认格式 网卡{N}:端口{M}。

        Returns:
            格式化的端口显示名称
        """
        if self.nic_name:
            return self.nic_name
        return f"网卡{self.nic_number}:端口{self.port_number}"
    
    @property
    def full_info(self) -> str:
        """获取端口的完整信息描述
        
        Returns:
            完整的端口信息,如"网卡1:端口1 (电口/1G)"
        """
        return f"{self.display_name} ({self.port_type}/{self.port_speed})"
    
    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        """转换为字典
        
        Args:
            exclude: 排除的字段列表
            include_relations: 是否包含关联对象
            
        Returns:
            字典格式的端口信息
        """
        data = super().to_dict(exclude=exclude)
        
        data["display_name"] = self.display_name
        data["full_info"] = self.full_info
        data["template_id"] = self.template_id
        
        if self.device:
            data["device_name"] = self.device.device_name
            data["device_type"] = self.device.device_type
        
        return data
    
    def is_available(self) -> bool:
        """检查端口是否可用
        
        Returns:
            True表示端口空闲可用,False表示端口已占用或禁用
        """
        return self.port_status == 'free'
    
    def occupy(self) -> None:
        """占用端口
        
        将端口状态设置为已占用
        """
        self.port_status = 'occupied'
    
    def release(self) -> None:
        """释放端口
        
        将端口状态设置为空闲
        """
        self.port_status = 'free'
    
    def disable(self) -> None:
        """禁用端口
        
        将端口状态设置为禁用
        """
        self.port_status = 'disabled'
    
    def set_error(self) -> None:
        """设置端口错误状态
        
        将端口状态设置为错误
        """
        self.port_status = 'error'
    
    def __repr__(self) -> str:
        return (
            f"<DeviceNicsPort {self.id}: "
            f"Device {self.device_id} - {self.display_name} ({self.port_type}/{self.port_speed})>"
        )
