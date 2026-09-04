"""IP分配日志模型

业务语义日志：记录 IP 生命周期（分配/释放/状态变更）。
安全审计日志由 audit_logs 表负责（审计中间件统一写入）。
业务层只写 ip_allocation_logs，避免双写。
"""
from sqlalchemy import Index
from sqlalchemy.sql import func

from app.models.base import BaseModel, TINYINT
from extensions import db


class IPAllocationLog(db.Model):
    """IP分配历史日志

    只追加日志表，不继承 BaseModel（无 updated_at 字段）。
    """
    __tablename__ = "ip_allocation_logs"
    __table_args__ = (
        Index("idx_alloc_ip", "ip_address", "room_id"),
        Index("idx_alloc_ip_time", "ip_address", "room_id", "created_at"),  # 按IP+机房查分配历史+时间排序
        Index("idx_alloc_operator", "operator_id"),
        Index("idx_alloc_created", "created_at"),
        {"comment": "IP分配历史日志"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    ip_address = db.Column(db.String(45), nullable=False, comment="IP地址")
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, comment="机房ID")
    action = db.Column(db.Enum('allocate', 'release', 'change_status'), nullable=False, comment="操作类型")
    old_status = db.Column(TINYINT(), comment="原状态")
    new_status = db.Column(TINYINT(), comment="新状态")
    operator_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False, comment="操作人 FK→users")
    detail = db.Column(db.JSON, comment="附加信息")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def to_dict(self, exclude=None, include_relations=False):
        """序列化"""
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'room_id': self.room_id,
            'action': self.action,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'operator_id': self.operator_id,
            'detail': self.detail,
            'created_at': BaseModel._serialize_value(self.created_at),
        }
