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
        row = cls.query.filter_by(key=key).first()
        if row:
            return row.value
        return cls.DEFAULTS.get(key)

    @classmethod
    def get_all(cls) -> dict:
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
        row = cls.query.filter_by(key=key).first()
        if row:
            return row.value
        return cls.DEFAULTS.get(key)

    @classmethod
    def set(cls, key: str, value: str) -> None:
        if key not in cls.ALLOWED_KEYS:
            raise ValueError(f"不允许的配置键: {key}")
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))

    @classmethod
    def bulk_set(cls, updates: dict) -> None:
        for key, value in updates.items():
            if key in cls.ALLOWED_KEYS and value is not None:
                cls.set(key, str(value))

    @classmethod
    def delete_all(cls) -> int:
        return cls.query.delete(synchronize_session=False)
