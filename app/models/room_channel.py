# -*- coding: utf-8 -*-
"""
机房通道模型模块

描述相邻两列机柜之间的通道（气流组织），用于平面图上的冷/热通道色带渲染。
只描述气流组织，**不是设施资产台账**——不追踪封闭件的型号、序列号与维保记录。

坐标口径（见设计文档 §2.1）：字母 = 列、数字 = 列内柜号，通道沿 row 方向延伸，
"位于哪两条通道之间"由列号区分，故唯一键用 col_number 而非 row_number。
"""
from typing import Any, Dict

from sqlalchemy import ForeignKey, UniqueConstraint

from app.models.base import BaseModel
from extensions import db


class RoomChannel(BaseModel):
    """机房通道配置——相邻两列机柜之间的通道。

    channel_type 取值：
    - 'cold'  冷通道：相邻两列柜门相对（送风面朝向的通道）；新式模块机房的封闭冷通道即此类
    - 'hot'   热通道：相邻两列柜背相对（排风面朝向的通道）
    - 'mixed' 混合通道：两列同向，一列的排风面紧邻另一列的进风面
              （属早期不规范布置，保留表达能力，不是老式机房的默认值）

    col_number = 0 表示"第 1 列外侧"——现场机柜不与墙/门/精密空调贴合，
    最外侧一列的外部同样是真实空间（且常正是空调侧），故允许 0。
    """

    __tablename__ = "room_channels"
    __table_args__ = (
        UniqueConstraint("room_id", "col_number", name="uk_room_col_channel"),
        {"comment": "机房通道配置表"},
    )

    room_id = db.Column(
        db.Integer, ForeignKey("rooms.id"), nullable=False, index=True, comment="所属机房ID"
    )
    col_number = db.Column(
        db.Integer,
        nullable=False,
        comment="通道位于第 col_number 列与第 col_number+1 列之间；0 表示第 1 列外侧",
    )
    channel_type = db.Column(
        db.String(20), nullable=False, comment="cold 冷 / hot 热 / mixed 混合(不规范布置)"
    )
    enclosed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="是否封闭(端门/顶板)；新式模块机房的封闭冷通道为 True，封闭热通道(HAC)亦为 True",
    )
    supply = db.Column(
        db.String(20),
        nullable=True,
        comment="送风方式：floor(地板下,推荐) / direct(上送风直吹通道,易掺混,非推荐) / none(无)",
    )
    label = db.Column(db.String(100), nullable=True, comment="展示文本,如'A-B 冷通道'")
    notes = db.Column(db.String(500), nullable=True, comment="备注")

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        """转换为字典（在基类逐列序列化之上补一个展示名）

        display_name 由后端统一下发，避免列表式配置弹窗与图上色带的
        "第 N 列与第 N+1 列之间"文案在前端两处各写一遍。
        """
        data = super().to_dict(exclude=exclude)

        if not data.get("label"):
            if self.col_number == 0:
                data["display_name"] = "第 1 列外侧"
            else:
                data["display_name"] = f"第 {self.col_number} 列与第 {self.col_number + 1} 列之间"

        return data

    def __repr__(self) -> str:
        return (
            f"<RoomChannel(id={self.id}, room_id={self.room_id}, "
            f"col={self.col_number}, type='{self.channel_type}')>"
        )
