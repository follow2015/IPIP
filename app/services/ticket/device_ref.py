# -*- coding: utf-8 -*-
"""工单设备引用的「非静默」解析（软引用 ``tickets.device_id`` 的配套兜底）

为什么需要本模块
----------------
``tickets.device_id`` 是**软引用**：列名像设备引用、但不建外键（理由见
``app/models/ticket.py`` 模块 docstring 第 4 条 —— 建外键就得登记进
``room_service._FORCE_DELETE_*_SCOPED``，而该清单的语义是物理 DELETE 子表行，
等于宣布「强删设备时把工单一并删掉」）。

代价是：设备被彻底删除后这个 id **必然悬空**，DB 既不置空也不报 1451。
``tests/test_device_delete_fk_closure.py::test_soft_reference_columns_are_accounted_for``
要求这类列必须被认领，二选一 —— 「快照 + 置空」或「写清为什么能留」。
工单是业务留痕，保留引用是正确语义，故走 ``SOFT_REF_ACCEPTED``。

**但豁免不等于没有配套。** 那份台账的注释里记着 2026-09-18 的实测教训：
G1 线路端点曾把豁免理由写成「读取详情时置 ``endpoint_lost: true``」，而该字段
**全仓零命中** —— 理由写得很具体，机制却从未落地，豁免实际等于理由为空。
工单不重蹈覆辙：本模块就是"非静默"承诺的落地，并由
``tests/services/ticket/test_device_ref.py`` 钉住三种情形（在册 / 已软删 /
已被彻底删除）。

为什么用 ``session.get`` 而不是 ``Device.query``
------------------------------------------------
``Device`` 启用了软删（``__soft_delete__ = True``），``Device.query`` 会自动带
``deleted_at IS NULL``。而工单的历史视角里，"这张单当年的设备后来被软删了"
恰恰是**最常见**的悬空成因 —— 用 query 会把它判成"设备不存在"，与"被彻底删除"
混为一谈。``session.get`` 直取主键，绕开软删过滤，再由调用方按
``device_lost`` / 业务状态自行区分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DeviceRef", "resolve_device_ref"]


@dataclass(frozen=True)
class DeviceRef:
    """一张工单指向的设备引用解析结果。

    ``device_lost=True`` 的含义是**引用无法解析**，不是"设备被软删了"：
    软删的设备仍能取到名字，此时 ``device_lost=False``（历史视角下它仍可解读）。
    只有连主键都查不到（彻底删除 / id 本身是脏数据）才为 True。
    """

    device_id: int | None
    device_name: str | None
    device_lost: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_lost": self.device_lost,
        }


def resolve_device_ref(device_id: int | None) -> DeviceRef:
    """解析工单的设备引用；解析不到时显式标记 ``device_lost``，不静默返回 None。

    Args:
        device_id: ``tickets.device_id``（CI 缓存列，可为空）。

    Returns:
        :class:`DeviceRef`。``device_id`` 为空时返回 ``device_lost=False`` 的三空
        结果 —— "这张单本来就没绑设备"不是悬空，标 lost 会把空值误报成故障。
    """
    if device_id is None:
        return DeviceRef(device_id=None, device_name=None, device_lost=False)

    from app.models.device import Device  # 局部导入：避免模型↔服务层的导入环
    from extensions import db

    device = db.session.get(Device, device_id)
    if device is None:
        return DeviceRef(device_id=device_id, device_name=None, device_lost=True)
    return DeviceRef(device_id=device_id, device_name=device.device_name, device_lost=False)
