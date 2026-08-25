# -*- coding: utf-8 -*-
"""
用户登录日志模型

映射 users_log 表，记录用户每次登录的时间、IP 和类型。

设计说明：
- 未继承 BaseModel：users_log 是只追加的日志表，不存在修改操作，
  故不需要 updated_at 字段；login_time 承担 created_at 的语义。
- charset utf8mb4（对应 users_log 建表 DDL），其余表为 utf8；
  建议后续统一迁移至 utf8mb4。
"""
from datetime import datetime

from sqlalchemy import Index, ForeignKey

from app.models.base import BaseModel
from extensions import db


class UserLog(db.Model):
    """用户登录日志模型

    对应 users_log 表。只追加，不修改，不继承 BaseModel。
    """

    __tablename__ = "users_log"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_user_login_time", "user_id", "login_time"),  # 按用户查登录历史+时间排序
        {"comment": "用户登录日志表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, ForeignKey("users.id"), nullable=False, comment="用户ID")
    login_time = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        comment="登录时间",
    )
    login_type = db.Column(
        db.String(10),
        nullable=True,
        default="web",
        comment="登录类型",
    )
    login_ip = db.Column(db.String(255), nullable=True, comment="登录IP")
    user_agent = db.Column(db.String(512), nullable=True, comment="登录设备/浏览器")

    def __repr__(self):
        return (
            f"<UserLog user_id={self.user_id} "
            f"login_time={self.login_time} type={self.login_type}>"
        )

    def to_dict(self):
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "login_time": BaseModel._serialize_value(self.login_time),
            "login_type": self.login_type,
            "login_ip":   self.login_ip,
            "user_agent": self.user_agent,
        }
