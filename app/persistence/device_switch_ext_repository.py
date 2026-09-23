# -*- coding: utf-8 -*-
"""交换机扩展信息仓库（DeviceSwitchExtRepository）

[WARN] 与 `switch_ext_repository.SwitchExtRepository` **不是同一张表**：
后者管 `switch_credentials`（Phase 3 重构后合并了旧的 sw_switch_ext），
本仓储管 `device_switch_ext`（角色/层级/上联设备等链路属性）。

B-44 收敛：`root_cause_analyzer` 的"同上游设备"集合原先直用
`db.session.query(DeviceSwitchExt)`，现收进本仓储。
"""
from typing import List, Optional

from extensions import db
from app.models.device_switch_ext import DeviceSwitchExt


class DeviceSwitchExtRepository:
    """交换机扩展信息（链路属性）仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def find_by_device_id(self, device_id: int) -> Optional[DeviceSwitchExt]:
        """按设备查扩展行（B-44 收敛：端口同步开关的设备级覆盖）。

        可能不存在（非受管设备无扩展行）—— 调用方据此回退全局开关，
        故返回 ``None`` 而非抛错。
        """
        return (
            self.session.query(DeviceSwitchExt)
            .filter_by(device_id=device_id)
            .first()
        )

    def list_by_uplink_device_id(self, uplink_device_id: int) -> List[DeviceSwitchExt]:
        """取所有以该设备为上联的交换机扩展行（根因分析的"同上游"集合）。

        调用方会经 ``ext.device`` 取设备实体并按 `ext.device_id` 去重/排除自身，
        故此处返回实体（关系随同一 session 可用）。
        """
        return (
            self.session.query(DeviceSwitchExt)
            .filter_by(uplink_device_id=uplink_device_id)
            .all()
        )
