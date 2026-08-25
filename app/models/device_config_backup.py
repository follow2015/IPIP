"""设备配置备份与变更模型"""
from sqlalchemy import Index
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class DeviceConfigBackup(db.Model):
    __tablename__ = "device_config_backups"
    __table_args__ = (
        Index("idx_config_device", "device_id"),
        Index("idx_config_device_time", "device_id", "created_at"),
        Index("idx_config_hash", "config_hash"),
        Index("idx_config_created", "created_at"),
        {"comment": "设备配置备份"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="设备ID FK→devices")
    config_content = db.Column(MEDIUMTEXT, nullable=False, comment="配置内容(MEDIUMTEXT)")
    config_hash = db.Column(db.String(64), nullable=False, comment="SHA-256哈希")
    backup_type = db.Column(
        db.Enum('manual', 'scheduled', 'pre_change'),
        nullable=False, default='manual', comment="备份类型"
    )
    file_size = db.Column(db.Integer, comment="配置文件大小(字节)")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def to_dict(self, exclude=None, include_relations=False):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'config_content': self.config_content,
            'config_hash': self.config_hash,
            'backup_type': self.backup_type,
            'file_size': self.file_size,
            'created_at': BaseModel._serialize_value(self.created_at),
        }


class DeviceConfigChange(db.Model):
    __tablename__ = "device_config_changes"
    __table_args__ = (
        Index("idx_change_device", "device_id"),
        Index("idx_change_status", "status"),
        Index("idx_change_requested", "requested_by"),
        {"comment": "设备配置变更审批"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="设备ID FK→devices")
    backup_id = db.Column(db.BigInteger, db.ForeignKey("device_config_backups.id"), comment="基准备份ID FK→device_config_backups")
    change_summary = db.Column(db.String(500), nullable=False, comment="变更摘要")
    change_detail = db.Column(MEDIUMTEXT, comment="变更详情(diff)")
    status = db.Column(
        db.Enum('draft', 'pending', 'approved', 'rejected', 'applied'),
        nullable=False, default='draft', comment="审批状态"
    )
    requested_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False, comment="申请人 FK→users")
    approved_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), comment="审批人 FK→users")
    applied_at = db.Column(db.DateTime, comment="实际应用时间")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def to_dict(self, exclude=None, include_relations=False):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'backup_id': self.backup_id,
            'change_summary': self.change_summary,
            'change_detail': self.change_detail,
            'status': self.status,
            'requested_by': self.requested_by,
            'approved_by': self.approved_by,
            'applied_at': BaseModel._serialize_value(self.applied_at),
            'created_at': BaseModel._serialize_value(self.created_at),
            'updated_at': BaseModel._serialize_value(self.updated_at),
        }
