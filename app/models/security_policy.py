# -*- coding: utf-8 -*-
"""安全策略 KV 模型。

只存**管理员改过的项**：无行 = 使用 `app/services/security/policy_registry.py`
里的注册表默认值（因此新增策略项不需要数据迁移）。
主键是业务键 `policy_key`（照 `MonitorDynamicConfig` 的既有范式），不是自增 id。
"""
from sqlalchemy.sql import func

from extensions import db


class SecurityPolicy(db.Model):
    """安全策略覆盖行。"""

    __tablename__ = "security_policies"

    policy_key = db.Column(db.String(64), primary_key=True, comment="策略键，如 snmp.allowed_versions")
    value_json = db.Column(db.JSON, nullable=False, comment="策略值（按注册表类型解析）")
    version = db.Column(db.Integer, nullable=False, server_default="1", comment="乐观锁版本")
    updated_by = db.Column(db.BigInteger, nullable=True, comment="操作人 users.id")
    updated_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<SecurityPolicy {self.policy_key} v{self.version}>"
