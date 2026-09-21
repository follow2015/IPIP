# -*- coding: utf-8 -*-
"""机箱子节点扩展信息仓储（DeviceServerExtRepository）

B-44 device_service 批：机箱-子节点结构（parent_device_id / node_position 等）
原先散在 device_service 的直查里，现收进本仓储。
"""
from typing import List

from app.models.device_server_ext import DeviceServerExt
from app.persistence.base import SQLAlchemyRepository


class DeviceServerExtRepository(SQLAlchemyRepository):
    """机箱子节点扩展信息仓储（device_server_ext 表）"""

    def __init__(self, session=None):
        super().__init__(DeviceServerExt, session)

    def list_by_parent_device(self, parent_device_id: int) -> List[DeviceServerExt]:
        """取机箱名下全部子节点扩展行（软删过滤由调用方的口径决定 ——
        软删场景需要**含**已删子节点，勿在仓储里加 deleted_at 过滤）。"""
        return (
            self.session.query(DeviceServerExt)
            .filter_by(parent_device_id=parent_device_id)
            .all()
        )

    def list_node_positions(self, parent_device_id: int) -> List[int]:
        """取机箱子节点的 U 位集合（含 None 行由调用方过滤）。"""
        return [
            r[0]
            for r in self.session.query(DeviceServerExt.node_position)
            .filter_by(parent_device_id=parent_device_id)
            .all()
        ]

    def delete_by_device(self, device_id: int) -> int:
        """清空该设备自身的扩展行（B-44 收敛：机箱重建的清理面）。"""
        return (
            self.session.query(DeviceServerExt)
            .filter_by(device_id=device_id)
            .delete()
        )
