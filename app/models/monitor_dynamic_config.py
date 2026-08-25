# -*- coding: utf-8 -*-
"""动态配置模型：在线可编辑的监控运行参数。

主键为 config_key（复用现有大写 MONITOR_* 名），不复用 BaseModel 的 id 自增主键。
"""
from datetime import datetime

from sqlalchemy.sql import func

from extensions import db


class MonitorDynamicConfig(db.Model):
    __tablename__ = "monitor_dynamic_config"

    config_key = db.Column(
        db.String(64),
        primary_key=True,
        comment="配置键（= 现有 _cfg() 调用点使用的大写 MONITOR_* key）",
    )
    config_value = db.Column(
        db.Text,
        nullable=False,
        comment="配置值（字符串化存储，按 value_type 解析）",
    )
    value_type = db.Column(
        db.String(16),
        nullable=False,
        server_default="string",
        comment="string/int/float/bool/json",
    )
    description = db.Column(
        db.String(255),
        nullable=True,
        server_default="",
        comment="配置说明（前端展示）",
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
    updated_by = db.Column(
        db.String(64),
        nullable=True,
        server_default="",
        comment="操作人（审计）",
    )

    def __repr__(self):
        return f"<MonitorDynamicConfig {self.config_key}={self.config_value}>"
