# -*- coding: utf-8 -*-
"""
网络设备端口Repository

提供网络设备端口相关的数据访问方法。
包含端口增量更新（R-01 原子事务）等关键业务逻辑。
"""
from app.utils.logging import get_logger
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import update, delete
from sqlalchemy.exc import SQLAlchemyError

from app.models.network_port import NetworkPort
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError
from app.core.enums import DataSource, TOMBSTONE

logger = get_logger(__name__)

class NetworkPortRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """网络设备端口Repository"""

    def __init__(self, session=None):
        super().__init__(NetworkPort, session)


    def find_by_id(self, port_id: int) -> Optional[Dict[str, Any]]:
        """根据端口 ID 查找"""
        try:
            port = (
                self.session.query(NetworkPort)
                .filter(NetworkPort.id == port_id)
                .first()
            )
            return port.to_dict(include_relations=True) if port else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def find_by_id_for_update(self, port_id: int) -> Optional[Dict[str, Any]]:
        """根据端口 ID 查找并加行级锁（SELECT ... FOR UPDATE），用于并发安全操作

        注意：必须在事务内调用，锁在事务提交/回滚后释放。
        不使用 joinedload，因为 FOR UPDATE 与 eager load 组合可能产生意外行为。
        """
        try:
            port = (
                self.session.query(NetworkPort)
                .filter(NetworkPort.id == port_id)
                .with_for_update()
                .first()
            )
            return port.to_dict(include_relations=True) if port else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口(加锁)失败", original_error=e)

    def find_ports_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        """获取指定设备的全部端口列表"""
        try:
            ports = (
                self.session.query(NetworkPort)
                .filter(NetworkPort.device_id == device_id)
                .order_by(NetworkPort.slot, NetworkPort.card, NetworkPort.port_number)
                .all()
            )
            return [p.to_dict(include_relations=True) for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口列表失败", original_error=e)

    def find_available_ports(self, device_id: int) -> List[Dict[str, Any]]:
        """获取空闲端口（usage_status='free'）"""
        try:
            ports = (
                self.session.query(NetworkPort)
                .filter(NetworkPort.device_id == device_id, NetworkPort.usage_status == "free")
                .order_by(NetworkPort.slot, NetworkPort.card, NetworkPort.port_number)
                .all()
            )
            return [p.to_dict() for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找可用端口失败", original_error=e)

    def find_active_ports(self, device_id: int) -> List[Dict[str, Any]]:
        """获取有效端口（排除 disabled），用于容量计算"""
        try:
            ports = (
                self.session.query(NetworkPort)
                .filter(
                    NetworkPort.device_id == device_id,
                    NetworkPort.usage_status != "disabled",
                )
                .all()
            )
            return [p.to_dict() for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找有效端口失败", original_error=e)

    def occupy_port(self, port_id: int) -> bool:
        """占用网络端口（设置 usage_status='occupied'，跳过 disabled 端口）

        仅 flush，由调用方统一 commit。

        Args:
            port_id: 端口ID

        Returns:
            bool: 操作成功返回 True，端口不存在返回 False
        """
        try:
            port = self.session.query(NetworkPort).filter(NetworkPort.id == port_id).first()
            if not port:
                return False
            if port.usage_status != "disabled":
                port.usage_status = "occupied"
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("占用端口失败", original_error=e)

    def release_customer_ports(self, customer_id: int) -> int:
        """批量释放客户名下所有交换机端口。

        将 usage_status 置 'free'、customer_id 置 NULL、link_status 置 'down'。

        Returns:
            int: 受影响行数
        """
        result = self.session.query(NetworkPort).filter(
            NetworkPort.customer_id == customer_id,
        ).update(
            {NetworkPort.usage_status: "free",
             NetworkPort.customer_id: None,
             NetworkPort.link_status: "down"},
            synchronize_session=False,
        )
        return result

    def release_port(self, port_id: int) -> bool:
        """释放网络端口（设置 usage_status='free'）

        仅 flush，由调用方统一 commit。

        Args:
            port_id: 端口ID

        Returns:
            bool: 操作成功返回 True，端口不存在返回 False
        """
        try:
            port = self.session.query(NetworkPort).filter(NetworkPort.id == port_id).first()
            if not port:
                return False
            port.usage_status = "free"
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("释放端口失败", original_error=e)

    def release_port_and_set_link_down(self, port_id: int) -> bool:
        """释放网络端口并设置物理端口 link_status='down'（仅非逻辑端口）

        仅 flush，由调用方统一 commit。

        Args:
            port_id: 端口ID

        Returns:
            bool: 操作成功返回 True，端口不存在返回 False
        """
        try:
            port = self.session.query(NetworkPort).filter(NetworkPort.id == port_id).first()
            if not port:
                return False
            port.usage_status = "free"
            if not NetworkPort.is_logical_port(port.port_name):
                port.link_status = "down"
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("释放端口并设置link_down失败", original_error=e)

    def find_occupied_ports_by_device_orm(self, device_id: int) -> List[NetworkPort]:
        """查找设备的已占用端口，返回 ORM 对象列表（供 Service 层释放端口）"""
        try:
            return (
                self.session.query(NetworkPort)
                .filter(
                    NetworkPort.device_id == device_id,
                    NetworkPort.usage_status == "occupied",
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找已占用端口失败", original_error=e)

    def find_by_id_orm(self, port_id: int) -> Optional[NetworkPort]:
        """根据端口 ID 查找，返回 ORM 对象（供 Service 层直接修改属性）"""
        try:
            return (
                self.session.query(NetworkPort)
                .filter(NetworkPort.id == port_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口(ORM)失败", original_error=e)

    def find_by_ids_orm(self, port_ids: List[int]) -> List[NetworkPort]:
        """根据端口 ID 列表批量查找，返回 ORM 对象列表（供 API 层构建映射）"""
        if not port_ids:
            return []
        try:
            return (
                self.session.query(NetworkPort)
                .filter(NetworkPort.id.in_(port_ids))
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查找端口(ORM)失败", original_error=e)

    def find_port_by_name(self, device_id: int, port_name: str) -> Optional[Dict[str, Any]]:
        """根据设备 ID 和端口名称查找端口"""
        try:
            port = (
                self.session.query(NetworkPort)
                .filter(
                    NetworkPort.device_id == device_id,
                    NetworkPort.port_name == port_name,
                )
                .first()
            )
            return port.to_dict(include_relations=True) if port else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def count_ports_by_device(self, device_id: int, filters: Dict = None) -> int:
        """统计端口数量，可按 usage_status 过滤"""
        try:
            q = self.session.query(NetworkPort).filter(NetworkPort.device_id == device_id)
            if filters and "usage_status" in filters:
                q = q.filter(NetworkPort.usage_status == filters["usage_status"])
            return q.count()
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计端口数量失败", original_error=e)

    def get_by_device(self, device_id: int) -> List[NetworkPort]:
        """获取设备所有端口（返回 ORM 对象列表，供 API 层使用）"""
        try:
            return (
                self.session.query(NetworkPort)
                .filter(NetworkPort.device_id == device_id)
                .order_by(NetworkPort.slot, NetworkPort.card, NetworkPort.port_number)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取设备端口失败", original_error=e)

    def get_port_names_by_device(self, device_id: int) -> List[str]:
        """获取设备端口名称列表"""
        try:
            rows = self.session.query(NetworkPort.port_name).filter(
                NetworkPort.device_id == device_id,
            ).all()
            return [r[0] for r in rows]
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取端口名称列表失败", original_error=e)


    def create_ports_batch(self, device_id: int, ports: List[Dict]) -> int:
        """批量增量创建端口，跳过已存在的端口名，返回创建数量

        Args:
            device_id: 设备ID
            ports: 端口数据列表
        """
        try:
            existing_names = {
                r[0] for r in self.session.query(NetworkPort.port_name)
                .filter(NetworkPort.device_id == device_id)
                .all()
            }
            new_ports = [p for p in ports if p.get("port_name") not in existing_names]
            objs = [
                NetworkPort(
                    device_id=device_id,
                    port_type=p.get("port_type", ""),
                    slot=p.get("slot", 0),
                    card=p.get("card", 0),
                    port_number=p.get("port_number", 0),
                    port_name=p.get("port_name", ""),
                    speed=p.get("speed", ""),
                    usage_status=p.get("usage_status", "free"),
                )
                for p in new_ports
            ]
            self.session.add_all(objs)
            self.session.flush()
            return len(objs)
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量创建端口失败", original_error=e)

    def update_port(self, port_id: int, data: Dict[str, Any]) -> bool:
        """更新端口字段

        Args:
            port_id: 端口ID
            data: 更新字段字典
        """
        try:
            port = self.session.query(NetworkPort).filter(NetworkPort.id == port_id).first()
            if not port:
                return False

            allowed = {
                "port_type", "slot", "card", "port_number", "port_name",
                "speed", "usage_status",
                "vlan", "description",
                "link_status", "mac", "ip_address", "customer_id",
                "raw_info", "data_source", "last_collected_at",
            }
            for field in allowed:
                if field in data:
                    value = data[field]
                    if field == "raw_info" and value == "":
                        value = None
                    setattr(port, field, value)

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新端口失败", original_error=e)

    def delete_port(self, port_id: int) -> bool:
        """删除单个端口

        Args:
            port_id: 端口ID
        """
        try:
            port = self.session.query(NetworkPort).filter(NetworkPort.id == port_id).first()
            if not port:
                return False
            self.session.delete(port)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除端口失败", original_error=e)

    def delete_device_ports(self, device_id: int) -> int:
        """删除设备全部端口，返回删除数量

        Args:
            device_id: 设备ID
        """
        try:
            count = (
                self.session.query(NetworkPort)
                .filter(NetworkPort.device_id == device_id)
                .delete(synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备端口失败", original_error=e)


    def incremental_update(self, device_id: int, port_rows: list) -> None:
        """端口增量更新三步事务（R-01），写入 network_ports 表

        Step 1: 全标记为 link_status=TOMBSTONE（待删除）
        Step 2: UPSERT 新数据（冲突时恢复 link_status，不覆盖 PROTECTED_FIELDS）
        Step 3: 清理残留（仅删除纯 auto 端口，hybrid 端口仅清除标记）

        事务原子性由调用方保证（通常在 SwitchInfoService.collect_port_info 中 commit）。

        Args:
            device_id: 交换机 device_id
            port_rows: 端口数据字典列表，每个字典包含：
                       port_name, link_status, vlan, mac, ip_address, speed,
                       description, port_type 等字段
        """
        now = datetime.now()

        self.session.execute(
            update(NetworkPort)
            .where(
                NetworkPort.device_id == device_id,
                NetworkPort.data_source.in_([DataSource.AUTO, DataSource.HYBRID]),
            )
            .values(link_status=TOMBSTONE)
        )

        if port_rows:
            existing_map = {
                p.port_name: p
                for p in self.session.query(NetworkPort)
                    .filter(NetworkPort.device_id == device_id)
                    .all()
            }
            for row in port_rows:
                port_name = row.get("port_name", "")

                existing = existing_map.get(port_name)

                if existing:
                    link_status = row.get("link_status")
                    if existing.usage_status == "disabled":
                        new_usage_status = "disabled"
                    else:
                        new_usage_status = NetworkPort.derive_usage_status(link_status, port_name)
                    update_fields = {
                        "port_type": row.get("port_type"),
                        "link_status": link_status,
                        "usage_status": new_usage_status,
                        "slot": row.get("slot"),
                        "card": row.get("card"),
                        "port_number": row.get("port_number"),
                        "vlan": row.get("vlan"),
                        "mac": row.get("mac"),
                        "ip_address": row.get("ip_address"),
                        "speed": row.get("speed"),
                        "description": row.get("description"),
                        "raw_info": row.get("raw_info") or None,
                        "last_collected_at": now,
                        "updated_at": now,
                    }
                    if existing.data_source == DataSource.MANUAL:
                        update_fields["data_source"] = DataSource.HYBRID
                    else:
                        update_fields["data_source"] = DataSource.AUTO

                    for k, v in update_fields.items():
                        if k not in NetworkPort.PROTECTED_FIELDS:
                            setattr(existing, k, v)
                else:
                    link_status = row.get("link_status")
                    new_port = NetworkPort(
                        device_id=device_id,
                        port_name=port_name,
                        slot=row.get("slot", -1),
                        card=row.get("card", -1),
                        port_number=row.get("port_number", -1),
                        port_type=row.get("port_type"),
                        speed=row.get("speed"),
                        usage_status=NetworkPort.derive_usage_status(link_status, port_name),
                        link_status=link_status,
                        vlan=row.get("vlan"),
                        mac=row.get("mac"),
                        ip_address=row.get("ip_address"),
                        customer_id=row.get("customer_id"),
                        description=row.get("description"),
                        raw_info=row.get("raw_info") or None,
                        data_source=DataSource.AUTO,
                        last_collected_at=now,
                    )
                    self.session.add(new_port)

        grace_cutoff = datetime.now().timestamp() - 600  # 10 分钟宽限期
        self.session.execute(
            delete(NetworkPort)
            .where(
                NetworkPort.device_id == device_id,
                NetworkPort.link_status == TOMBSTONE,
                NetworkPort.data_source == DataSource.AUTO,
            )
            .where(
                ~(
                    NetworkPort.updated_at.isnot(None)
                    & NetworkPort.updated_at.op('>')(datetime.fromtimestamp(grace_cutoff))
                )
            )
        )
        self.session.execute(
            update(NetworkPort)
            .where(
                NetworkPort.device_id == device_id,
                NetworkPort.link_status == TOMBSTONE,
                NetworkPort.data_source == DataSource.HYBRID,
            )
            .values(link_status=None)
        )

        self.session.flush()
        logger.info("设备 %d 端口增量更新完成: %d 条记录", device_id, len(port_rows))


    def find_port_ips_by_device_and_names(self, device_id: int, port_names: List[str]) -> List:
        """查询指定设备+端口名列表的 SwitchPortIP 记录

        Args:
            device_id: 交换机设备ID
            port_names: 端口名称列表

        Returns:
            List[SwitchPortIP]: SwitchPortIP ORM 对象列表
        """
        from app.models.switch_credentials import SwitchPortIP
        if not port_names:
            return []
        try:
            return (
                self.session.query(SwitchPortIP)
                .filter(
                    SwitchPortIP.device_id == device_id,
                    SwitchPortIP.port_name.in_(port_names),
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查询端口IP列表失败", original_error=e)


    def find_ports_by_lag_group_id(self, lag_id: int) -> List[NetworkPort]:
        """查询指定 LAG 组的所有成员端口

        Args:
            lag_id: LinkAggregationGroup ID

        Returns:
            List[NetworkPort]: 成员端口列表
        """
        return self.session.query(NetworkPort).filter_by(lag_group_id=lag_id).all()

    def count_ports_by_lag_group_id(self, lag_id: int) -> int:
        """统计指定 LAG 组的成员端口数

        Args:
            lag_id: LinkAggregationGroup ID

        Returns:
            int: 成员端口数
        """
        return self.session.query(NetworkPort).filter_by(lag_group_id=lag_id).count()

    def clear_lag_group_id(self, lag_id: int) -> int:
        """清空指定 LAG 组所有成员的 lag_group_id

        Args:
            lag_id: LinkAggregationGroup ID

        Returns:
            int: 受影响行数
        """
        return self.session.query(NetworkPort).filter_by(lag_group_id=lag_id).update(
            {"lag_group_id": None}, synchronize_session=False,
        )

    def set_lag_group_id(self, port_ids: List[int], lag_id: int) -> int:
        """批量设置端口的 lag_group_id

        Args:
            port_ids: 端口 ID 列表
            lag_id: LinkAggregationGroup ID

        Returns:
            int: 受影响行数
        """
        if not port_ids:
            return 0
        return self.session.query(NetworkPort).filter(
            NetworkPort.id.in_(port_ids),
        ).update({"lag_group_id": lag_id}, synchronize_session=False)

    def clear_vlan_by_device_and_vlan(self, device_id: int, vlan: str) -> int:
        """清除指定设备+VLAN 的端口 vlan 回写字段

        Args:
            device_id: 设备 ID
            vlan: VLAN 标识（字符串）

        Returns:
            int: 受影响行数
        """
        return self.session.query(NetworkPort).filter(
            NetworkPort.device_id == device_id,
            NetworkPort.vlan == vlan,
        ).update({"vlan": None}, synchronize_session=False)

    def clear_vlan_by_port_ids_and_vlan(self, port_ids: List[int], vlan: str) -> int:
        """清除指定端口+VLAN 的 vlan 回写字段

        Args:
            port_ids: 端口 ID 列表
            vlan: VLAN 标识（字符串）

        Returns:
            int: 受影响行数
        """
        if not port_ids:
            return 0
        return self.session.query(NetworkPort).filter(
            NetworkPort.id.in_(port_ids),
            NetworkPort.vlan == vlan,
        ).update({"vlan": None}, synchronize_session=False)

    def set_vlan_by_port_ids(self, port_ids: List[int], vlan: str) -> int:
        """批量设置端口的 vlan 回写字段

        Args:
            port_ids: 端口 ID 列表
            vlan: VLAN 标识（字符串）

        Returns:
            int: 受影响行数
        """
        if not port_ids:
            return 0
        return self.session.query(NetworkPort).filter(
            NetworkPort.id.in_(port_ids),
        ).update({"vlan": vlan}, synchronize_session=False)

    def find_by_ids(self, port_ids: List[int]) -> List[NetworkPort]:
        """按 ID 列表查询端口（ORM 对象）

        Args:
            port_ids: 端口 ID 列表

        Returns:
            List[NetworkPort]: 端口列表
        """
        if not port_ids:
            return []
        return self.session.query(NetworkPort).filter(
            NetworkPort.id.in_(port_ids),
        ).all()
