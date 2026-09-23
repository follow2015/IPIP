# -*- coding: utf-8 -*-
"""
网络设备间连接 Repository（N2N）

提供 network_connections 表的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.models.network_connection import NetworkConnection
from app.persistence.base import SQLAlchemyRepository
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)

class NetworkConnectionRepository(SQLAlchemyRepository):
    """网络设备间连接 Repository"""

    def __init__(self, session=None):
        super().__init__(NetworkConnection, session)


    def find_by_id(self, conn_id: int) -> Optional[Dict[str, Any]]:
        """根据连接ID查找，含两端端口和设备信息"""
        try:
            conn = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(NetworkConnection.id == conn_id)
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找N2N连接失败", original_error=e)

    def find_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        """查询设备的所有 N2N 连接（作为 local 或 peer 任一端）"""
        try:
            conns = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(
                    or_(
                        NetworkConnection.local_device_id == device_id,
                        NetworkConnection.peer_device_id == device_id,
                    )
                )
                .all()
            )
            return [c.to_dict(perspective_device_id=device_id) for c in conns]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查询设备N2N连接失败", original_error=e)

    def find_by_port(self, port_id: int) -> Optional[Dict[str, Any]]:
        """根据端口ID查找连接（一个端口最多一条 N2N 连接）"""
        try:
            conn = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接失败", original_error=e)

    def list_by_local_port_device_ids(self, device_ids) -> list[NetworkConnection]:
        """取 **local 端口**所属设备在集合内的 N2N 连接（B-46 批 4：拓扑建边）。

        [WARN] 只按 ``local_port_id → NetworkPort.device_id`` 过滤（原实现即如此）：
        拓扑建边随后**双向**用 local/peer 关系补对端（见图内逻辑），
        这里若改成"任一端"会把同一条边算两次。
        """
        from app.models.network_port import NetworkPort

        ids = list(device_ids)
        if not ids:
            return []
        return (
            self.session.query(NetworkConnection)
            .join(NetworkPort, NetworkConnection.local_port_id == NetworkPort.id)
            .filter(NetworkPort.device_id.in_(ids))
            .all()
        )

    def find_by_port_ids_orm(self, port_ids: list[int]) -> list[NetworkConnection]:
        """根据端口 ID 列表查找关联的 N2N 连接，返回 ORM 对象列表（含 joinedload 预加载）"""
        if not port_ids:
            return []
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id.in_(port_ids),
                        NetworkConnection.peer_port_id.in_(port_ids),
                    )
                )
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口列表查找N2N连接失败", original_error=e)

    def find_by_port_for_update(self, port_id: int) -> Optional[Dict[str, Any]]:
        """根据端口ID查找连接并加行级锁，用于并发安全操作"""
        try:
            conn = (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .with_for_update()
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接(加锁)失败", original_error=e)

    def find_by_port_for_update_orm(self, port_id: int) -> Optional[NetworkConnection]:
        """根据端口ID查找连接并加行级锁，返回 ORM 对象（供 Service 层删除/修改）"""
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .with_for_update()
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接(加锁ORM)失败", original_error=e)

    def find_by_id_for_update_orm(self, conn_id: int) -> Optional[NetworkConnection]:
        """根据连接ID查找并加行级锁，返回 ORM 对象（供 Service 层删除/修改）"""
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(NetworkConnection.id == conn_id)
                .with_for_update()
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据ID查找N2N连接(加锁ORM)失败", original_error=e)

    def find_existing_by_ports_orm(self, local_port_id: int, peer_port_id: int) -> Optional[NetworkConnection]:
        """查找涉及指定端口的已有 N2N 连接，返回 ORM 对象（供 Service 层判断旧端口释放）"""
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == local_port_id,
                        NetworkConnection.peer_port_id == local_port_id,
                        NetworkConnection.local_port_id == peer_port_id,
                        NetworkConnection.peer_port_id == peer_port_id,
                    )
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找已有N2N连接(ORM)失败", original_error=e)

    def list_by_device_via_ports(self, device_id: int) -> List[NetworkConnection]:
        """取该设备经**任一端端口**参与的全部 N2N 连接（B-44 扫尾批：MAC 表比对）。

        端口归属判定走关系 ``has`` 子查询（local 或 peer 端口属于该设备）；
        ``joinedload`` 两端端口 —— 调用方随后要读 ``conn.local_port.port_name``
        等属性，懒加载会 N+1（原实现无预加载，属同结果的顺带优化）。
        """
        from app.models.network_port import NetworkPort

        return (
            self.session.query(NetworkConnection)
            .filter(
                or_(
                    NetworkConnection.local_port.has(
                        NetworkPort.device_id == device_id
                    ),
                    NetworkConnection.peer_port.has(
                        NetworkPort.device_id == device_id
                    ),
                )
            )
            .options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            )
            .all()
        )

    def find_pair_connection_orm(self, local_port_id: int, peer_port_id: int) -> Optional[NetworkConnection]:
        """查找**这一对**端口之间已存在的 N2N 连接（含反向），返回 ORM 对象。

        B-44 拓扑批新增：`topology_discovery_service._find_connection` 的"连接已存在"
        判定入口 —— 错误信息里要带上 ``#{连接id}``，故需实体而非 bool。

        [WARN] **与 `find_existing_by_ports_orm` 语义不同，勿互相替代**：
        · 本方法 = "**这一对**端口之间（A→B 或 B→A）是否有连接" —— 用于判"链路已存在"；
        · `find_existing_by_ports_orm` = "**任一**端口是否出现在**任何**连接里"
          —— 用于"旧端口释放"（换口场景：本端换了但旧口仍挂着别的链路也要处理）。
        把后者当前者用，会把"本端口与**第三方**端口之间的连接"误报成"链路已存在"
        （拓扑发现直接漏建连）；反之用前者替后者，则换口时旧端口的残留链路不会被处理。
        """
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        (NetworkConnection.local_port_id == local_port_id)
                        & (NetworkConnection.peer_port_id == peer_port_id),
                        (NetworkConnection.local_port_id == peer_port_id)
                        & (NetworkConnection.peer_port_id == local_port_id),
                    )
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口对之间的N2N连接失败", original_error=e)

    def list_by_device_ids(
        self, device_ids, *, with_ports: bool = False, any_side: bool = True,
    ) -> List[NetworkConnection]:
        """按设备 ID 集合取 N2N 连接（B-44 拓扑批 2/2）。

        Args:
            device_ids: 设备 ID 集合/列表
            with_ports: 是否预加载两端端口（拓扑画边要端口名 ⇒ True；只算邻接表 ⇒ False）
            any_side: ``True`` = **任一侧**命中（local 或 peer 在集合里，拓扑收敛用）；
                ``False`` = **两侧都要**在集合里（"集合内部的连线"，索引页用）。
                两者结果集不同（前者含跨出集合的边），**不可互相替代**。

        空 `device_ids` 返回 `[]`（调用方据此也常提前 return，语义一致）。
        不过滤软删：`NetworkConnection` 未开启 `__soft_delete__`，无此列。
        """
        if not device_ids:
            return []
        ids = tuple(device_ids)
        if any_side:
            condition = or_(
                NetworkConnection.local_device_id.in_(ids),
                NetworkConnection.peer_device_id.in_(ids),
            )
        else:
            condition = and_(
                NetworkConnection.local_device_id.in_(ids),
                NetworkConnection.peer_device_id.in_(ids),
            )
        query = self.session.query(NetworkConnection).filter(condition)
        if with_ports:
            query = query.options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            )
        try:
            return query.all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("按设备集合查询N2N连接失败", original_error=e)

    def exists_by_ports(self, local_port_id: int, peer_port_id: int) -> bool:
        """检查两个端口之间是否已存在连接"""
        try:
            return self.session.query(NetworkConnection).filter(
                or_(
                    (NetworkConnection.local_port_id == local_port_id) & (NetworkConnection.peer_port_id == peer_port_id),
                    (NetworkConnection.local_port_id == peer_port_id) & (NetworkConnection.peer_port_id == local_port_id),
                )
            ).first() is not None
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查N2N连接存在性失败", original_error=e)


    def create_connection(self, data: Dict[str, Any]) -> int:
        """创建或更新 N2N 连接（UPSERT）

        如果 local_port_id 或 peer_port_id 已存在连接记录，
        则更新该记录的对端信息，而非插入新行（避免唯一键冲突）。
        返回连接ID。
        """
        try:
            local_port_id = data.get("local_port_id")
            peer_port_id  = data.get("peer_port_id")

            existing = (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == local_port_id,
                        NetworkConnection.peer_port_id == local_port_id,
                        NetworkConnection.local_port_id == peer_port_id,
                        NetworkConnection.peer_port_id == peer_port_id,
                    )
                )
                .first()
            )

            if existing:
                existing.local_port_id = local_port_id
                existing.peer_port_id  = peer_port_id
                existing.local_device_id = data.get("local_device_id")
                existing.peer_device_id  = data.get("peer_device_id")
                for field in ("connection_type", "vlan_id", "status", "notes",
                              "bandwidth", "description", "lag_group_id"):
                    if field in data:
                        setattr(existing, field, data[field])
                self.session.flush()
                return existing.id

            conn = NetworkConnection(
                local_port_id=local_port_id,
                peer_port_id=peer_port_id,
                local_device_id=data.get("local_device_id"),
                peer_device_id=data.get("peer_device_id"),
                connection_type=data.get("connection_type"),
                vlan_id=data.get("vlan_id"),
                status=data.get("status", "active"),
                notes=data.get("notes"),
                bandwidth=data.get("bandwidth"),
                description=data.get("description"),
                lag_group_id=data.get("lag_group_id"),
            )
            self.session.add(conn)
            self.session.flush()
            return conn.id
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建N2N连接失败", original_error=e)

    def update_connection(self, conn_id: int, data: Dict[str, Any]) -> bool:
        """更新 N2N 连接的业务字段"""
        try:
            conn = self.session.query(NetworkConnection).filter(
                NetworkConnection.id == conn_id
            ).first()
            if not conn:
                return False

            allowed = {
                "connection_type", "vlan_id", "status", "notes",
                "bandwidth", "description", "lag_group_id",
            }
            for field in allowed:
                if field in data:
                    setattr(conn, field, data[field])

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新N2N连接失败", original_error=e)

    def delete_connection_orm(self, conn: "NetworkConnection") -> None:
        """删除 N2N 连接 ORM 对象（仅 flush，由调用方统一 commit）

        Args:
            conn: NetworkConnection ORM 对象
        """
        try:
            self.session.delete(conn)
            self.session.flush()
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除N2N连接(ORM)失败", original_error=e)

    def delete_connection(self, conn_id: int) -> bool:
        """删除 N2N 连接"""
        try:
            conn = self.session.query(NetworkConnection).filter(
                NetworkConnection.id == conn_id
            ).first()
            if not conn:
                return False
            self.session.delete(conn)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除N2N连接失败", original_error=e)

    def delete_by_device(self, device_id: int) -> int:
        """删除设备的所有 N2N 连接，返回删除数量"""
        try:
            count = self.session.query(NetworkConnection).filter(
                or_(
                    NetworkConnection.local_device_id == device_id,
                    NetworkConnection.peer_device_id == device_id,
                )
            ).delete(synchronize_session=False)
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备N2N连接失败", original_error=e)
