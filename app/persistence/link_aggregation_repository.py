# -*- coding: utf-8 -*-
"""
链路聚合组 Repository 实现

提供链路聚合组相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import joinedload

from app.models.link_aggregation import LinkAggregationGroup
from app.persistence.base import SQLAlchemyRepository

logger = get_logger(__name__)

class LinkAggregationRepository(SQLAlchemyRepository):
    """链路聚合组 Repository

    提供链路聚合组相关的数据访问方法。
    """

    def __init__(self, session=None):
        super().__init__(LinkAggregationGroup, session)

    def find_by_device(self, device_id: int) -> List[LinkAggregationGroup]:
        """按设备查询聚合组（含 member_port_list 预加载，避免 N+1 查询）"""
        return (
            self.session.query(LinkAggregationGroup)
            .options(joinedload(LinkAggregationGroup.member_port_list))
            .filter(LinkAggregationGroup.device_id == device_id)
            .all()
        )

    def find_by_device_and_name(self, device_id: int, lag_name: str) -> Optional[LinkAggregationGroup]:
        """按设备和聚合组名查询"""
        return self.find_one(filters={'device_id': device_id, 'lag_name': lag_name})

    def find_all_with_device_info(self, room_id: int = None, device_id: int = None) -> List[Dict[str, Any]]:
        """查询所有聚合组，关联设备名称和机房

        Args:
            room_id: 可选机房ID筛选
            device_id: 可选设备ID筛选

        Returns:
            包含设备信息的聚合组字典列表
        """
        from app.models.device import Device
        from app.models.switch_credentials import SwitchCredentials
        from app.models.cabinet import Cabinet

        query = (
            self.session.query(LinkAggregationGroup)
            .join(Device, LinkAggregationGroup.device_id == Device.id)
            .outerjoin(SwitchCredentials, SwitchCredentials.device_id == Device.id)
            .outerjoin(Cabinet, Device.cabinet_id == Cabinet.id)
            .order_by(Device.device_name, LinkAggregationGroup.lag_name)
        )
        if room_id:
            query = query.filter(Cabinet.room_id == room_id)
        if device_id:
            query = query.filter(LinkAggregationGroup.device_id == device_id)

        rows = query.all()

        device_ids = list({lag.device_id for lag in rows})
        if device_ids:
            sc_map = {
                sc.device_id: sc
                for sc in self.session.query(SwitchCredentials)
                .filter(SwitchCredentials.device_id.in_(device_ids))
                .all()
            }
            dev_map = {
                dev.id: dev
                for dev in self.session.query(Device)
                .options(joinedload(Device.cabinet))
                .filter(Device.id.in_(device_ids))
                .all()
            }
        else:
            sc_map = {}
            dev_map = {}

        result_list = []
        for lag in rows:
            d = lag.to_dict()
            sc = sc_map.get(lag.device_id)
            dev = dev_map.get(lag.device_id)
            d['device_name'] = dev.device_name if dev else None
            d['room_id'] = dev.cabinet.room_id if dev and dev.cabinet else None
            d['has_ssh'] = sc.has_ssh if sc else False
            result_list.append(d)
        return result_list

    def find_all_with_device_info_paginated(
        self, page: int = 1, per_page: int = 20,
        search: str = None, room_id: int = None, device_id: int = None,
    ) -> Dict[str, Any]:
        """查询所有聚合组（分页），关联设备名称和机房

        Args:
            page: 页码
            per_page: 每页数量
            search: 模糊搜索（匹配聚合组名称）
            room_id: 可选机房ID筛选
            device_id: 可选设备ID筛选

        Returns:
            Dict: {"items": [...], "total": int}
        """
        from app.models.device import Device
        from app.models.switch_credentials import SwitchCredentials
        from app.models.cabinet import Cabinet

        query = (
            self.session.query(LinkAggregationGroup)
            .join(Device, LinkAggregationGroup.device_id == Device.id)
            .outerjoin(SwitchCredentials, SwitchCredentials.device_id == Device.id)
            .outerjoin(Cabinet, Device.cabinet_id == Cabinet.id)
        )
        if search:
            pattern = f'%{search}%'
            query = query.filter(LinkAggregationGroup.lag_name.like(pattern))
        if room_id:
            query = query.filter(Cabinet.room_id == room_id)
        if device_id:
            query = query.filter(LinkAggregationGroup.device_id == device_id)

        total_count = query.count()
        rows = (
            query.order_by(Device.device_name, LinkAggregationGroup.lag_name)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        device_ids = list({lag.device_id for lag in rows})
        if device_ids:
            sc_map = {
                sc.device_id: sc
                for sc in self.session.query(SwitchCredentials)
                .filter(SwitchCredentials.device_id.in_(device_ids))
                .all()
            }
            dev_map = {
                dev.id: dev
                for dev in self.session.query(Device)
                .options(joinedload(Device.cabinet))
                .filter(Device.id.in_(device_ids))
                .all()
            }
        else:
            sc_map = {}
            dev_map = {}

        items = []
        for lag in rows:
            d = lag.to_dict()
            sc = sc_map.get(lag.device_id)
            dev = dev_map.get(lag.device_id)
            d['device_name'] = dev.device_name if dev else None
            d['room_id'] = dev.cabinet.room_id if dev and dev.cabinet else None
            d['has_ssh'] = sc.has_ssh if sc else False
            items.append(d)
        return {"items": items, "total": total_count}

    def update_member_count(self, lag_id: int, count: int) -> bool:
        """更新聚合组成员数量

        Args:
            lag_id: 聚合组 ID
            count: 新的成员数量

        Returns:
            bool: 是否更新成功
        """
        result = self.session.query(LinkAggregationGroup).filter_by(id=lag_id).update(
            {"member_count": count}, synchronize_session=False,
        )
        return result > 0

    def delete_by_device_id(self, device_id: int) -> int:
        """删除指定设备的所有链路聚合组

        Args:
            device_id: 设备 ID

        Returns:
            int: 删除行数
        """
        return self.session.query(LinkAggregationGroup).filter_by(device_id=device_id).delete(
            synchronize_session=False,
        )
