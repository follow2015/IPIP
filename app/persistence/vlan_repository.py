# -*- coding: utf-8 -*-
"""
VLAN Repository 实现

提供VLAN相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import cast, String, or_
from sqlalchemy.orm import joinedload

from app.models.vlan import VLAN
from app.persistence.base import SQLAlchemyRepository

logger = get_logger(__name__)


class VLANRepository(SQLAlchemyRepository):
    """VLAN Repository

    提供VLAN相关的数据访问方法。
    """

    def __init__(self, session=None):
        super().__init__(VLAN, session)

    def find_by_vlan_id(self, vlan_id: int, room_id: Optional[int] = None) -> Optional[VLAN]:
        """按VLAN ID查询"""
        filters = {'vlan_id': vlan_id}
        if room_id is not None:
            filters['room_id'] = room_id
        return self.find_one(filters=filters)

    def find_by_device_and_vlan_id(self, device_id: int, vlan_id: int) -> Optional[VLAN]:
        """按设备ID和VLAN ID查询（对应 uq_vlan_device 唯一约束）"""
        return self.find_one(filters={'device_id': device_id, 'vlan_id': vlan_id})

    def find_by_room(self, room_id: int) -> List[VLAN]:
        """按机房查询VLAN"""
        return self.find_all(filters={'room_id': room_id})

    def find_by_device(self, device_id: int) -> List[VLAN]:
        """按设备查询VLAN（含 port_members 预加载，避免 N+1 查询）"""
        from app.models.vlan_port_member import VLANPortMember
        return (
            self.session.query(VLAN)
            .options(joinedload(VLAN.port_members).joinedload(VLANPortMember.port))
            .filter(VLAN.device_id == device_id)
            .order_by(VLAN.vlan_id)
            .all()
        )

    def paginate_with_search(
        self,
        search: Optional[str] = None,
        device_id: Optional[int] = None,
        room_id: Optional[int] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """带搜索和分页的 VLAN 列表查询。

        Args:
            search: 搜索关键词（匹配 name/purpose/vlan_id）
            device_id: 按设备ID过滤
            room_id: 按机房ID过滤
            page: 页码
            per_page: 每页数量

        Returns:
            Dict 包含 data / total_count / page / per_page
        """
        query = self.session.query(VLAN).options(joinedload(VLAN.port_members))

        if search:
            pattern = f'%{search}%'
            query = query.filter(
                or_(
                    VLAN.name.ilike(pattern),
                    VLAN.purpose.ilike(pattern),
                    cast(VLAN.vlan_id, String).ilike(pattern),
                )
            )
        if device_id:
            query = query.filter(VLAN.device_id == device_id)
        if room_id:
            query = query.filter(VLAN.room_id == room_id)

        total_count = query.count()
        data_list = (
            query.order_by(VLAN.device_id, VLAN.vlan_id)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return {
            "data": data_list,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
        }

    def delete_by_device_id(self, device_id: int) -> int:
        """删除指定设备的所有 VLAN

        Args:
            device_id: 设备 ID

        Returns:
            int: 删除行数
        """
        return self.session.query(VLAN).filter_by(device_id=device_id).delete(
            synchronize_session=False,
        )


class VLANPortMemberRepository(SQLAlchemyRepository):
    """VLAN 端口成员关系 Repository

    提供 VLAN-Port 关联的数据访问方法。
    """

    def __init__(self, session=None):
        from app.models.vlan_port_member import VLANPortMember
        super().__init__(VLANPortMember, session)

    def find_by_vlan_id(self, vlan_id: int) -> list:
        """查询指定 VLAN 的所有成员关系

        Args:
            vlan_id: VLAN 表主键 ID（非 vlan_id 编号）

        Returns:
            List[VLANPortMember]
        """
        from app.models.vlan_port_member import VLANPortMember
        return self.session.query(VLANPortMember).filter_by(vlan_id=vlan_id).all()

    def delete_by_vlan_id(self, vlan_id: int) -> int:
        """删除指定 VLAN 的所有成员关系

        Args:
            vlan_id: VLAN 表主键 ID

        Returns:
            int: 删除行数
        """
        from app.models.vlan_port_member import VLANPortMember
        return self.session.query(VLANPortMember).filter_by(vlan_id=vlan_id).delete(
            synchronize_session=False,
        )

    def delete_by_port_id(self, port_id: int) -> int:
        """删除指定端口的所有 VLAN 成员关系

        Args:
            port_id: 端口 ID

        Returns:
            int: 删除行数
        """
        from app.models.vlan_port_member import VLANPortMember
        return self.session.query(VLANPortMember).filter_by(port_id=port_id).delete(
            synchronize_session=False,
        )
