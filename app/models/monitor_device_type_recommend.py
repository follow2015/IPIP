# -*- coding: utf-8 -*-
"""设备类型推荐配置表（monitor_device_type_recommends）

定义每种设备类型推荐哪些 category。前端"推荐勾选"按钮按此配置
从探测结果中筛 category ∈ 推荐列表 的 OID。

categories 用 JSON 数组存储，省 JOIN，一次读取拿到推荐列表。
"""
from extensions import db

from .base import BaseModel


class MonitorDeviceTypeRecommend(BaseModel):

    __tablename__ = "monitor_device_type_recommends"
    __table_args__ = (
        db.UniqueConstraint("device_type", name="uq_device_type_recommend"),
        {
            "comment": "设备类型推荐配置，定义每种设备类型推荐哪些 category",
        },
    )

    device_type = db.Column(
        db.String(16),
        nullable=False,
        comment="设备类型 network/server/other",
    )
    categories = db.Column(
        db.JSON,
        nullable=False,
        comment="推荐的 category 列表，如 [\"temperature\",\"fan\",\"power_supply\"]",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False):
        return super().to_dict(exclude=exclude, include_relations=include_relations)
