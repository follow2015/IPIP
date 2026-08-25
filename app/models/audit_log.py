"""审计日志模型

安全审计日志：记录操作人、客户端IP、操作类型等。
由审计中间件统一写入，业务层不应直接写此表。
IP生命周期业务日志由 ip_allocation_logs 负责。
"""
from sqlalchemy import Index
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource", "resource", "resource_id"),
        Index("idx_audit_resource_time", "resource", "resource_id", "created_at"),
        Index("idx_audit_created", "created_at"),
        {"comment": "操作审计日志"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id = db.Column(db.BigInteger, comment="操作人ID(逻辑关联users.id,不加FK避免级联影响日志保留)")
    action = db.Column(db.String(64), nullable=False, comment="操作类型(如 device.create, ip.ban)")
    resource = db.Column(db.String(64), nullable=False, comment="资源类型(如 device, ip, switch)")
    resource_id = db.Column(db.BigInteger, comment="资源ID")
    detail = db.Column(db.JSON, comment="操作详情")
    ip_address = db.Column(db.String(45), comment="客户端IP")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def to_dict(self, exclude=None, include_relations=False):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource': self.resource,
            'resource_id': self.resource_id,
            'detail': self.detail,
            'ip_address': self.ip_address,
            'created_at': BaseModel._serialize_value(self.created_at),
        }
