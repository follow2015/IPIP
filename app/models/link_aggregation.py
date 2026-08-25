"""链路聚合组模型"""
from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db
from app.core.enums import LAGStatus


class LinkAggregationGroup(BaseModel):
    __tablename__ = "link_aggregation_groups"
    __table_args__ = (
        Index("uk_lag_device_name", "device_id", "lag_name", unique=True),
        Index("idx_lag_device", "device_id"),
        {"comment": "链路聚合组"},
    )

    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="所属设备 FK→devices")
    lag_name = db.Column(db.String(50), nullable=False, comment="聚合组名(Eth-Trunk/X)")
    lag_type = db.Column(db.Enum('lacp', 'static'), nullable=False, default='lacp', comment="聚合类型")
    algorithm = db.Column(db.String(32), comment="负载均衡算法")
    status = db.Column(db.SmallInteger, nullable=False, default=LAGStatus.ACTIVE.value, comment="LAG状态: 1=活跃 0=停用 (LAGStatus)")
    member_count = db.Column(db.SmallInteger, nullable=False, default=0, comment="成员口数量（冗余字段,可从network_ports.lag_group_id统计）")
    purpose = db.Column(db.String(255), nullable=True, comment="用途说明")

    member_port_list = relationship(
        "NetworkPort",
        foreign_keys="NetworkPort.lag_group_id",
        back_populates="lag_group",
        lazy="select",
    )

    def to_dict(self, exclude=None, include_relations=False):
        result = super().to_dict(exclude=exclude)
        result['purpose'] = self.purpose or ''
        if hasattr(self, 'member_port_list'):
            result['member_ports'] = [p.port_name for p in self.member_port_list]
            result['member_count'] = len(self.member_port_list)
        else:
            result['member_ports'] = []
        return result
