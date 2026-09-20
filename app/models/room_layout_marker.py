# -*- coding: utf-8 -*-
"""
机房平面图占位标记模型模块

只服务于"这个格子不能放机柜"这一件事——门、精密空调、PDU、立柱等占位设施的
位置提示。**不是设施资产台账**：需要追踪型号/序列号/维保的场景应建独立资产模型，
不在本次设计范围内。
"""
from sqlalchemy import ForeignKey, UniqueConstraint

from app.models.base import BaseModel
from extensions import db


class RoomLayoutMarker(BaseModel):
    """机房平面图非机柜占位标记。

    坐标域比机柜宽：机柜要求 `row > 0 && col > 0`，而标记允许 `row >= 0 && col >= 0`——
    门、端头精密空调、走道设备等大量位于机柜网格之外，不允许就表达不了。
    渲染时网格范围取"机柜 ∪ 标记"的并集（见设计文档 §2.2 / §3.2）。

    注意：因坐标域不同，前端**不可**对标记复用机柜的 `isPositioned` 谓词，
    否则外侧标记会被静默丢弃。
    """

    __tablename__ = "room_layout_markers"
    __table_args__ = (
        UniqueConstraint("room_id", "row_number", "col_number", name="uk_marker_position"),
        {"comment": "机房平面图占位标记表"},
    )

    room_id = db.Column(
        db.Integer, ForeignKey("rooms.id"), nullable=False, index=True, comment="所属机房ID"
    )
    row_number = db.Column(db.Integer, nullable=False, comment="行号（允许 0，用于机柜网格外侧）")
    col_number = db.Column(db.Integer, nullable=False, comment="列号（允许 0，用于机柜网格外侧）")
    marker_type = db.Column(
        db.String(20), nullable=False, comment="ac(空调) / pdu / pillar(立柱) / door / other"
    )
    label = db.Column(db.String(100), nullable=True, comment="展示文本,如'空调-01'")
    notes = db.Column(db.String(500), nullable=True, comment="备注")

    def __repr__(self) -> str:
        return (
            f"<RoomLayoutMarker(id={self.id}, room_id={self.room_id}, "
            f"pos=({self.row_number},{self.col_number}), type='{self.marker_type}')>"
        )
