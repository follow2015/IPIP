# -*- coding: utf-8 -*-
"""
机柜模型模块
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, MEDIUMTEXT
from extensions import db
from app.core.enums import CabinetStatus

if TYPE_CHECKING:
    from app.models.device import Device


class Cabinet(BaseModel):
    """机柜模型

    管理机柜的基本信息，包括编号、位置、容量等。
    一个机柜属于一个机房，可以包含多个设备。
    """

    __tablename__ = "cabinets"
    __table_args__ = (
        UniqueConstraint("room_id", "cabinet_number", name="uk_cabinet_room_number"),
        Index("idx_cabinet_customer",    "customer_id"),
        Index("idx_cabinet_status",      "status"),
        Index("idx_cabinet_created_at",  "created_at"),
        Index("idx_cabinet_room_status", "room_id", "status"),  # 前缀覆盖 idx_cabinet_room
        {"comment": "机柜信息表"},
    )

    cabinet_number = db.Column(
        db.String(255), nullable=False, comment="机柜编号"
    )
    room_id = db.Column(
        db.Integer, ForeignKey("rooms.id"), nullable=False, index=True,
        comment="所属机房ID"
    )
    location = db.Column(db.String(255), comment="具体位置")
    row = db.Column(db.Integer, comment="行号（机房平面图纵坐标，从1开始）")
    col = db.Column(db.Integer, comment="列号（机房平面图横坐标，从1开始）")

    total_u = db.Column(db.Integer, default=42, nullable=False, comment="总U位数")
    used_u  = db.Column(db.Integer, default=0,  nullable=False,
                        comment="已用U位数（冗余字段,由update_usage维护,可从devices聚合）")

    total_power = db.Column(db.Integer, comment="电力容量(W)")
    used_power  = db.Column(db.Integer, default=0, nullable=False,
                            comment="已用功率(W)（冗余字段,由update_usage维护,可从devices聚合）")

    max_weight = db.Column(db.Float, comment="最大承重(KG)")
    status = db.Column(
        db.Integer, default=CabinetStatus.AVAILABLE.value, nullable=False,
        comment="状态: 0-禁用, 1-可用, 2-使用中, 3-维护中, 4-已预留 (CabinetStatus)"
    )

    customer_id = db.Column(
        db.BigInteger, ForeignKey("customers.id"), comment="客户ID"
    )
    notes = db.Column(MEDIUMTEXT, comment="备注信息")

    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间(NULL=未删除)")


    customer = relationship(
        "Customer",
        foreign_keys=[customer_id],
        backref="cabinets",
        lazy="joined",
    )

    devices = relationship(
        "Device",
        foreign_keys="Device.cabinet_id",
        backref="cabinet_rel",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


    @property
    def _parent_devices(self) -> List["Device"]:
        """仅返回父设备（过滤机箱子节点），直接使用已加载的 relationship，无额外查询。

        parent_device_id 存储在 DeviceServerExt 扩展表中，
        通过 d.parent_device_id 代理属性访问（避免触发 server_ext 懒加载 N+1）。
        """
        return [d for d in self.devices if d.deleted_at is None and not d.parent_device_id]


    def get_used_u_positions(self) -> List[int]:
        """获取已占用 U 位编号列表（已排序、去重）。

        直接遍历 self.devices（已由 selectin 预加载），无额外 DB 查询。
        """
        used: set[int] = set()
        for device in self._parent_devices:
            if device.u_position and device.height_u:
                for u in range(device.u_position, device.u_position + device.height_u):
                    if u <= self.total_u:
                        used.add(u)
        return sorted(used)

    def get_available_u_count(self) -> int:
        """获取可用 U 位数量。"""
        return self.total_u - len(self.get_used_u_positions())

    def get_available_u_ranges(self) -> List[Dict[str, int]]:
        """获取可用 U 位连续区间列表。

        Returns:
            List[Dict]: 每项含 start、end、count
        """
        used      = set(self.get_used_u_positions())
        available = sorted(set(range(1, self.total_u + 1)) - used)
        if not available:
            return []

        ranges: List[Dict[str, int]] = []
        start = end = available[0]
        for u in available[1:]:
            if u == end + 1:
                end = u
            else:
                ranges.append({"start": start, "end": end, "count": end - start + 1})
                start = end = u
        ranges.append({"start": start, "end": end, "count": end - start + 1})
        return ranges

    def can_fit_device(self, u_height: int, preferred_position: Optional[int] = None) -> bool:
        """检查能否容纳指定 U 高的设备。

        Args:
            u_height: 设备高度（U 位数）
            preferred_position: 首选起始位置，None 表示任意位置均可

        Returns:
            bool
        """
        if preferred_position is not None:
            try:
                start_u = int(preferred_position)
            except (TypeError, ValueError):
                return False
            used     = set(self.get_used_u_positions())
            required = set(range(start_u, start_u + u_height))
            return not (required & used) and (start_u + u_height - 1) <= self.total_u

        return any(r["count"] >= u_height for r in self.get_available_u_ranges())

    def check_u_position_conflict(
        self,
        u_position: int,
        height_u: int,
        exclude_device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """检查指定 U 位区间是否与现有设备冲突。

        Args:
            u_position: 起始 U 位
            height_u: 设备高度
            exclude_device_id: 排除该设备 ID（用于更新场景）

        Returns:
            {"has_conflict": bool, "conflicting_devices": List[Dict]}
        """
        required = set(range(u_position, u_position + height_u))
        conflicting: List[Dict[str, Any]] = []

        for device in self._parent_devices:
            if exclude_device_id and device.id == exclude_device_id:
                continue
            if device.u_position and device.height_u:
                occupied = set(range(device.u_position, device.u_position + device.height_u))
                if required & occupied:
                    conflicting.append({
                        "id":         device.id,
                        "name":       device.device_name,
                        "u_position": device.u_position,
                        "height_u":   device.height_u,
                    })

        return {"has_conflict": bool(conflicting), "conflicting_devices": conflicting}

    def update_usage(self) -> None:
        """重新计算并同步 used_u / used_power 冗余字段。

        ⚠️ 本方法不提交事务，调用方负责 db.session.commit()，
        以便融入外层事务，避免意外提交。
        原代码在此处直接 db.session.commit()，导致无法与上层事务合并。
        """
        self.used_u     = len(self.get_used_u_positions())
        self.used_power = int(sum(float(d.power or 0) for d in self._parent_devices))

    def to_dict(
        self,
        exclude: Optional[List[str]] = None,
        include_relations: bool = False,
    ) -> Dict[str, Any]:
        """序列化为字典。

        Args:
            exclude: 要排除的字段列表
            include_relations: True 时附加设备列表及 U 位详情

        Returns:
            Dict
        """
        data = super().to_dict(exclude=exclude)

        data["available_u"] = self.get_available_u_count()

        if self.room:
            data["room_name"]     = self.room.name
            data["room_location"] = getattr(self.room, "location", None)

        if self.customer:
            data["customer_name"] = self.customer.customer_name

        active_devices = [d for d in self.devices if d.deleted_at is None]
        data["device_count"]     = len(active_devices)
        live_used_u = len(self.get_used_u_positions())
        data["u_usage_rate"]     = (
            round((live_used_u / self.total_u) * 100, 2) if self.total_u > 0 else 0
        )
        data["power_usage_rate"] = (
            round((self.used_power / self.total_power) * 100, 2)
            if (self.total_power and self.total_power > 0)
            else 0
        )

        if include_relations:
            data["devices"]            = [d.to_dict() for d in active_devices]
            data["used_u_positions"]   = self.get_used_u_positions()
            data["available_u_ranges"] = self.get_available_u_ranges()

        return data

    def __repr__(self) -> str:
        return f"<Cabinet(id={self.id}, number='{self.cabinet_number}')>"
