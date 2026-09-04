# -*- coding: utf-8 -*-
"""
邮件服务器配置模型

采用 key-value 行存储，每行一个配置项。
与 .env 文件不同，配置存在数据库中，通过 API 修改，
所有 worker 读到一致值，且可记录审计日志。
"""
from app.models.base import BaseModel
from extensions import db


class MailSetting(BaseModel):
    """邮件服务器配置（key-value 行存储）"""

    __tablename__ = "mail_settings"
    __table_args__ = (
        db.UniqueConstraint("key", name="uq_mail_setting_key"),
        {"comment": "邮件服务器配置表"},
    )

    key = db.Column(db.String(50), nullable=False, comment="配置键")
    value = db.Column(db.String(500), nullable=True, comment="配置值")

    DEFAULTS = {
        "mail_server": "",
        "mail_port": "587",
        "mail_use_tls": "true",
        "mail_use_ssl": "false",
        "mail_username": "",
        "mail_password": "",
        "mail_default_sender": "",
        "mail_timeout": "10",
    }

    ALLOWED_KEYS = set(DEFAULTS.keys())

    SENSITIVE_KEYS = {"mail_password"}

    @classmethod
    def get(cls, key: str) -> str | None:
        """获取单个配置值"""
        row = cls.query.filter_by(key=key).first()
        if row:
            return row.value
        return cls.DEFAULTS.get(key)

    @classmethod
    def get_all(cls) -> dict:
        """获取所有邮件配置（密码脱敏），数值字段转为正确类型"""
        result = dict(cls.DEFAULTS)
        for row in cls.query.all():
            result[row.key] = row.value
        result["mail_port"] = int(result.get("mail_port") or 587)
        result["mail_timeout"] = int(result.get("mail_timeout") or 10)
        result["mail_use_tls"] = (result.get("mail_use_tls") or "true").lower() == "true"
        result["mail_use_ssl"] = (result.get("mail_use_ssl") or "false").lower() == "true"
        result["mail_password"] = "****" if result.get("mail_password") else ""
        result["mail_password_set"] = bool(cls.query.filter_by(key="mail_password").first()
                                           and cls.query.filter_by(key="mail_password").first().value)
        return result

    @classmethod
    def get_raw(cls, key: str) -> str | None:
        """获取原始配置值（不脱敏），供 EmailChannel 内部使用"""
        row = cls.query.filter_by(key=key).first()
        if row:
            return row.value
        return cls.DEFAULTS.get(key)

    @classmethod
    def get_raw_batch(cls, keys) -> dict[str, str | None]:
        """n3：批量读取原始配置（一次 IN 查询替代 N 次单查）。

        get_mail_config_from_db 原逐 key 调 get_raw（每用户约 8 次 SQL）。
        本方法一次查询取回所有请求键，缺失的 key 回退 DEFAULTS，与 get_raw 语义一致。
        """
        valid = [k for k in keys if k in cls.ALLOWED_KEYS]
        result = {k: cls.DEFAULTS.get(k) for k in keys}
        if not valid:
            return result
        rows = cls.query.filter(cls.key.in_(valid)).all()
        for row in rows:
            result[row.key] = row.value
        return result

    @classmethod
    def set(cls, key: str, value: str) -> None:
        """设置单个配置值（仅允许白名单内的 key）"""
        if key not in cls.ALLOWED_KEYS:
            raise ValueError(f"不允许的配置键: {key}")
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))

    @classmethod
    def bulk_set(cls, updates: dict) -> None:
        """批量设置配置值"""
        for key, value in updates.items():
            if key in cls.ALLOWED_KEYS and value is not None:
                cls.set(key, str(value))

    @classmethod
    def delete_all(cls) -> int:
        """删除所有配置项，返回删除行数"""
        return cls.query.delete(synchronize_session=False)
