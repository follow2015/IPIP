# -*- coding: utf-8 -*-
"""
device_repository.py — 关键修复
覆盖 BUG-2 / BUG-3 / BUG-5 / BUG-9 / BUG-12 / BUG-13
"""
from app.utils.logging import get_logger
import random
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from app.utils.time_utils import now_utc_naive

from sqlalchemy import and_, case, distinct, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, joinedload

from app.models.device import Device
from app.models.device_hardware import (
    SNAPSHOT_KEY_CHILDREN,
    SNAPSHOT_KEY_LOCATION,
)
from app.core.enums import DeviceStatus
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError
from app.core.pagination_limits import ensure_offset_within_limit
from app.utils.query_optimizer import monitor_query_performance
from extensions import db

logger = get_logger(__name__)


class DeviceRepository(SQLAlchemyRepository, QueryOptimizationMixin):

    _WRITABLE_FIELDS = {
        "device_name", "device_type", "device_subtype", "device_model", "brand",
        "serial_number", "hostname", "management_ip", "mac_address",
        "metric_template_group_id",
        "cabinet_id", "u_position", "height_u", "power",
        "status", "responsible_person", "notes", "customer_id",
        "parent_device_id", "is_chassis", "node_position", "node_row", "node_col",
        "total_nodes", "node_rows", "node_cols", "node_naming_pattern",
        "switch_role", "layer",
    }

    def __init__(self, session=None):
        super().__init__(Device, session)

    def find_ids_by_responsible_person(
        self, user_id: int, alive_only: bool = False,
    ) -> List[int]:
        """查询指定用户负责的设备 ID 列表（供告警历史「我负责的」过滤）。

        由 ``monitor_routes.list_alerts`` 的 scope=mine 分支调用，
        避免在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。

        ⚠️ ``alive_only`` 是**两个调用点的口径分歧**（B-44 收敛时发现，勿合并）：
        · ``False``（默认，告警历史）：**含**已软删设备 —— 历史记录的作用域按
          "当时谁负责"还原，设备删了也要能看到它那条历史；
        · ``True``（monitor_service 的 alert 看板 scope=mine）：**排除**已软删设备
          —— 看板是"当前"视图，已删设备不该出现。
        合并成一个口径必然改错其中一处的可见内容。
        """
        query = self.session.query(Device.id).filter(
            Device.responsible_person == user_id
        )
        if alive_only:
            query = query.filter(Device.deleted_at.is_(None))
        return [r.id for r in query.all()]

    def find_alive_by_ids(self, device_ids) -> List[Device]:
        """按 ID 集合取设备（**排除软删**；B-46 批 4：拓扑外部占位节点）。

        走 ``_base_query()``：外部节点必须是存活设备（软删设备的连接边不该
        进拓扑图 —— 原实现显式带 ``deleted_at IS NULL``）。
        """
        ids = list(device_ids)
        if not ids:
            return []
        return self._base_query().filter(Device.id.in_(ids)).all()

    def find_by_management_ip(self, ip_address: str) -> Optional[Device]:
        """按 ``management_ip`` 查设备（软删除除外；B-44 收敛：SNMP Trap 源 IP 解析）。

        走 `_base_query()`：Trap 处理必须忽略已软删设备（原实现显式带
        ``deleted_at IS NULL``，换仓储后由基查询统一保证）。
        """
        return (
            self._base_query()
            .filter(Device.management_ip == ip_address)
            .first()
        )

    def list_switch_ids_by_cabinet_ids(self, cabinet_ids) -> List[int]:
        """取机柜集合内的交换机设备 ID（排除软删；B-44 部署计划批）。

        ⚠️ "交换机" = ``device_type == "network"`` **且**
        ``device_subtype == "switch"``（两个条件都要 —— 只认 type 会把
        路由器/防火墙也算成交换机，二层域会被拖大）。
        """
        ids = tuple(cabinet_ids)
        if not ids:
            return []
        rows = (
            self._base_query()
            .filter(
                Device.cabinet_id.in_(ids),
                Device.device_type == "network",
                Device.device_subtype == "switch",
            )
            .all()
        )
        return [d.id for d in rows]

    def list_by_management_ip(self, ip_address: str) -> List[Device]:
        """按 `management_ip` 取**全部**匹配设备（软删除除外；B-44 拓扑批收敛）。

        ⚠️ 与 `find_by_management_ip` **刻意不同**：那个返 `.first()`（Trap 解析"认一台"），
        这个返**列表** —— 拓扑对端解析要判"**命中多台即歧义**"（拿列表长度说话），
        退化成 `.first()` 会把歧义静默变成"随便挑一台画进拓扑"。
        """
        return (
            self._base_query()
            .filter(Device.management_ip == ip_address)
            .all()
        )

    def list_by_name(self, name: str) -> List[Device]:
        """按 `device_name` **或** `hostname` 精确等于 ``name`` 取全部设备（软删除除外）。

        ⚠️ **单个名字**，不是候选列表 —— 拓扑对端解析是"候选名**逐个**试、首个唯一命中
        即返回"，把候选列表一次性塞进 ``IN`` 会把"名1 命中 A、名2 命中 B"从
        "返回 A"变成"判为歧义"（**语义改变**）。候选循环与歧义策略属业务逻辑，
        留在 service；仓储只答"这个名字命中哪几台"。

        返回**列表**：调用方要判"命中多台即歧义"（拿长度说话），退化成 `.first()`
        会把歧义静默变成"随便挑一台画进拓扑"。排除软删由 `_base_query()` 统一保证
        （B-43 口径：已删设备不得被画进拓扑）。
        """
        return (
            self._base_query()
            .filter(
                or_(
                    Device.device_name == name,
                    Device.hostname == name,
                )
            )
            .all()
        )


    def topology_switch_query(self, alive_only: bool = True) -> Query:
        """拓扑用「网络设备」查询构造器（预加载 switch_ext + cabinet.room）。

        · `outerjoin(DeviceSwitchExt)`：**LEFT** —— 没有 switch_ext 记录的网络设备
          （路由器/防火墙）也必须出现在拓扑里（改成 inner join 会静默丢节点）。
        · **默认排除已软删设备**（B-48 拍板，2026-09-22）：原实现不过滤，与同域
          `topology_query_service` 的显式 `deleted_at IS NULL` 口径相反 —— 同一个
          "拓扑"概念两个可见集不同。统一为**排除**，依据三条：
          ① 设备删除会释放其端口/连接（见 `test_device_occupation_release`）⇒
             把已删设备画进拓扑只会得到**孤立节点/悬空链路**；
          ② 同域索引页本来就排除 ⇒ 统一方向应取"索引页口径"；
          ③ "历史设备留痕"另有承担者（软删记录、审计日志、留痕快照列），
             不需要靠拓扑图承担。
        · `alive_only=False` 作为**逃生舱**保留（若将来要"历史拓扑"视图，显式传 False
          并在调用点写明理由）。
        """
        from app.models.cabinet import Cabinet
        from app.models.device_switch_ext import DeviceSwitchExt

        query = (
            self.session.query(Device)
            .filter(Device.device_type == "network")
            .outerjoin(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id)
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
        )
        if alive_only:
            query = query.filter(Device.deleted_at.is_(None))
        return query

    def topology_device_query(
        self, device_types: Sequence[str], *,
        with_customer: bool = False, alive_only: bool = True,
    ) -> Query:
        """拓扑用「设备」查询构造器（预加载 switch_ext + cabinet.room[/customer]）。

        Args:
            device_types: 参与拓扑的设备类型（调用方传，勿在仓储里写死）
            with_customer: 是否额外预加载 `customer`（拓扑索引页要客户名，按需）
            alive_only: 是否排除已软删设备。**默认 True = 排除**（B-48 拍板，
                2026-09-22）：原先两个调用点口径相反（`topology_service` 不过滤、
                索引页显式排除），同一个"拓扑"概念两个可见集不同。统一为排除，
                依据见 `topology_switch_query` 的同段说明（删除已释放端口/连接 ⇒
                画出来是孤立节点；历史留痕另有承担者）。`alive_only=False` 作为
                逃生舱保留给将来的"历史拓扑"视图。
        """
        from app.models.cabinet import Cabinet

        query = (
            self.session.query(Device)
            .filter(Device.device_type.in_(list(device_types)))
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
        )
        if with_customer:
            query = query.options(joinedload(Device.customer))
        if alive_only:
            query = query.filter(Device.deleted_at.is_(None))
        return query

    def find_switch_with_topology(self, device_id: int) -> Optional[Device]:
        """按 ID 取**网络设备**并预加载拓扑所需关联（星形拓扑的中心交换机）。

        ⚠️ 带 `Device.device_type == "network"` 条件：传非网络设备返回 None
        （调用方据此返回空拓扑），**不是**普通 `find_by_id` 的别名。
        不预加载 customer（星形拓扑不展示客户名，按需再加）。
        """
        from app.models.cabinet import Cabinet

        return (
            self.session.query(Device)
            .filter(Device.id == device_id, Device.device_type == "network")
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
            .first()
        )

    def list_by_ids_with_topology(self, device_ids: Sequence[int]) -> List[Device]:
        """按 ID 列表批量取设备并预加载拓扑关联（**替代二次查询**）。

        空列表返回 `[]`（调用方用 `if peer_ids else []` 保护过，语义一致）。
        不过滤软删（与原实现一致，见 `topology_switch_query` 的口径说明）。
        """
        if not device_ids:
            return []
        from app.models.cabinet import Cabinet

        return (
            self.session.query(Device)
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
            .filter(Device.id.in_(tuple(device_ids)))
            .all()
        )

    def clear_metric_template_group(self, device_id: int) -> int:
        """把设备的模板组绑定置空（B-44 收敛：监控协议切换时清理）。

        协议切换后旧协议的模板组对新协议无意义，保留会让监控数据页展示旧协议指标。
        走 `_base_query()` ⇒ 已软删设备**不被这条旁路写入**（update 的命中语义
        必须与其余设备查询一致，否则"已删行仍被改"又是一处分叉 —— B-43 同款）。

        Returns:
            int: 受影响行数（0 = 设备不存在或已软删）
        """
        return (
            self._base_query()
            .filter(Device.id == device_id)
            .update(
                {Device.metric_template_group_id: None},
                synchronize_session=False,
            )
        )

    def find_ids_by_room_ids(self, room_ids: List[int]) -> List[int]:
        """查询位于指定机房列表内的设备 ID（供 data_scope_service room 模式使用）。"""
        if not room_ids:
            return []
        from app.models.cabinet import Cabinet
        rows = (
            self.session.query(Device.id)
            .join(Cabinet, Cabinet.id == Device.cabinet_id)
            .filter(Cabinet.room_id.in_(room_ids))
            .all()
        )
        return [r.id for r in rows]

    def find_responsible_person_by_id(self, device_id: int) -> Optional[int]:
        """查询设备责任人 ID（供 data_scope_service 反查使用）。"""
        row = (
            self.session.query(Device.responsible_person)
            .filter(Device.id == device_id)
            .first()
        )
        return row.responsible_person if row else None


    def find_by_id(self, device_id: int) -> Optional[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer), joinedload(Device.switch_credential))
                .filter(Device.id == device_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_ids(self, device_ids: list) -> dict:
        """批量按 ID 查找设备，返回 {device_id: Device}。

        P1 修复：消除 batch_set_monitor_enabled 的 N+1 查询。
        """
        if not device_ids:
            return {}
        try:
            rows = (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer), joinedload(Device.switch_credential))
                .filter(Device.id.in_(device_ids))
                .all()
            )
            return {d.id: d for d in rows}
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查找设备失败", original_error=e)

    def find_by_id_or_404(self, device_id: int) -> Device:
        """按 ID 查找设备，不存在则抛出 404（供 Task 8 手动探测路径使用）"""
        device = self.find_by_id(device_id)
        if device is None:
            from flask import abort
            abort(404)
        return device

    def find_id_name_map(self, device_ids: list, include_deleted: bool = False) -> dict:
        """批量取 id → device_name 映射（B-43：替代 device_service 的裸 query 快照）

        只 SELECT 两列（不 joinedload）——原调用点就是"名字快照"用途，
        换成 find_by_ids 会额外加载三张关联表，对批量路径是明显放大。

        ``include_deleted``：**口径必须由调用方显式声明**。告警留痕快照
        （永久删除链路，设备必已软删）要 ``True`` 才能取到名字，否则快照写 None。
        """
        if not device_ids:
            return {}
        query = self.session.query(Device.id, Device.device_name)
        if not include_deleted:
            query = self._base_query().with_entities(Device.id, Device.device_name)
        return dict(query.filter(Device.id.in_(device_ids)).all())

    def find_deleted_by_device_name(self, device_name: str) -> Optional[Device]:
        """按名称查找**已软删除**的设备（B-43：机箱节点恢复场景）

        恢复逻辑要先确认"这个名字的原子节点确实在回收站里"，故必须
        **只匹配已删**（含活设备的匹配会让恢复逻辑误改未删除设备）。
        """
        return (
            self.session.query(Device)
            .filter(Device.device_name == device_name, Device.deleted_at.isnot(None))
            .first()
        )

    def find_by_id_including_deleted(self, device_id: int) -> Optional[Device]:
        """查询设备（含已软删除），用于回收站恢复场景"""
        try:
            return (
                self.session.query(Device)
                .options(
                    joinedload(Device.hardware),
                    joinedload(Device.server_ext),
                )
                .filter(Device.id == device_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败（含已删除）", original_error=e)

    def find_ids_by_type(self, device_ids: List[int], device_types: set) -> List[int]:
        """批量按 id + 设备类型过滤，仅返回 id 列表（供监控 worker 减少 N 次单查）。

        返回 id 升序；device_ids 或 device_types 为空时返回 []。
        仅 SELECT id，不带 joinedload，避免为过滤而加载完整设备行。
        """
        if not device_ids or not device_types:
            return []
        try:
            return [
                row[0] for row in self.session.query(Device.id)
                .filter(Device.id.in_(device_ids), Device.device_type.in_(device_types))
                .order_by(Device.id)
                .all()
            ]
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查询设备 ID 失败", original_error=e)

    def find_by_device_name(self, device_name: str) -> Optional[Device]:
        try:
            return self._base_query().filter(Device.device_name == device_name).first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_serial_number(self, serial_number: str) -> Optional[Device]:
        try:
            return (
                self._base_query()
                .filter(Device.serial_number == serial_number)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_nodes_by_chassis(self, chassis_id: int) -> List[Device]:
        """获取机箱的所有子节点（按 node_position 排序）"""
        try:
            from app.models.device_server_ext import DeviceServerExt
            return (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    DeviceServerExt.parent_device_id == chassis_id,
                )
                .order_by(DeviceServerExt.node_position)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找机箱子节点失败", original_error=e)

    def find_chassis_by_id(self, device_id: int) -> Optional[Device]:
        """查找机箱设备（排除已报废和已删除）"""
        try:
            return (
                self._base_query()
                .filter(
                    Device.id == device_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找机箱失败", original_error=e)

    def find_node_by_position(
        self, chassis_id: int, position: int, exclude_id: int = None
    ) -> Optional[Device]:
        """按位置查找节点（用于冲突检测）"""
        try:
            from app.models.device_server_ext import DeviceServerExt
            q = (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    DeviceServerExt.parent_device_id == chassis_id,
                    DeviceServerExt.node_position == position,
                    Device.status != DeviceStatus.SCRAPPED,
                )
            )
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return q.first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找节点位置失败", original_error=e)

    def find_active_devices(self) -> List[Device]:
        try:
            return (
                self._base_query()
                .filter(Device.status != DeviceStatus.SCRAPPED)
                .order_by(Device.device_name)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_cabinet_id(self, cabinet_id: int) -> List[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer))
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_customer_id_ordered(
        self, customer_id: int, limit: Optional[int] = None,
        device_ids: Optional[List[int]] = None,
    ) -> List[Device]:
        """按客户取设备（id 升序，可选 limit / 数据域过滤；B-44 收敛）

        ⚠️ 与 `find_by_customer_id` 的区别：**不过滤 SCRAPPED 状态** —— 两处调用点
        （AI 客户实体解析、AI「客户设备能力」）的口径是"客户名下有哪些设备"，
        含报废设备；且 `device_ids` 为数据域白名单（``None`` = 不限）。
        """
        query = self._base_query().filter(Device.customer_id == customer_id)
        if device_ids is not None:
            query = query.filter(Device.id.in_(device_ids))
        query = query.order_by(Device.id)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_by_customer_id(
        self, customer_id: int, device_ids: Optional[List[int]] = None,
    ) -> int:
        """统计某客户名下设备数（可选数据域过滤）——与上面的取数**同口径**。"""
        query = self._base_query().filter(Device.customer_id == customer_id)
        if device_ids is not None:
            query = query.filter(Device.id.in_(device_ids))
        return query.count()

    def search_exact_identity(
        self, query_text: str, device_types: Optional[List[str]] = None, limit: int = 10,
    ) -> List[Device]:
        """**精确**命中任一身份字段（device_name / hostname / management_ip），AI 实体解析用

        返回 0 条 = 未命中、1 条 = 命中、>1 条 = 由调用方按"歧义"处理（原逻辑如此）。
        """
        query = self._base_query().filter(or_(
            Device.device_name == query_text,
            Device.hostname == query_text,
            Device.management_ip == query_text,
        ))
        if device_types:
            query = query.filter(Device.device_type.in_(device_types))
        return query.order_by(Device.id).limit(limit).all()

    def search_name_contains(
        self, like_pattern: str, device_types: Optional[List[str]] = None,
        limit: int = 10, escape: str = "\\",
    ) -> List[Device]:
        """**模糊**命中 device_name / hostname（ilike + 显式转义），AI 实体解析候选用

        ``like_pattern`` 由调用方构造（含 ``%``；用户输入须先 `_escape_like` 转义，
        防 ``%``/``_`` 被当通配符导致候选溢出）。
        """
        query = self._base_query().filter(or_(
            Device.device_name.ilike(like_pattern, escape=escape),
            Device.hostname.ilike(like_pattern, escape=escape),
        ))
        if device_types:
            query = query.filter(Device.device_type.in_(device_types))
        return query.order_by(Device.id).limit(limit).all()

    def find_peers_in_cabinets(
        self, cabinet_ids: List[int], exclude_device_id: int, limit: int,
    ) -> List[Device]:
        """取这些机柜内的其它设备（根因分析的 peer 集合，B-44 收敛）

        与 `find_by_cabinet_id` 的区别（不可合并）：**不过滤 SCRAPPED 状态**
        （根因分析要看"当时在场的设备"，报废设备也可能是故障源），但**过滤软删除**
        （`_base_query`；已软删设备不得作为 peer —— B-43 曾就地加过显式过滤，
        本方法把该口径收进仓储一处）。

        Args:
            cabinet_ids: 机柜 id 列表（空则返回 []）
            exclude_device_id: 排除的设备（通常是告警设备自身）
            limit: 行数上限（根因分析只取前 N 台，防候选爆炸）
        """
        if not cabinet_ids:
            return []
        try:
            return (
                self._base_query()
                .filter(
                    Device.cabinet_id.in_(cabinet_ids),
                    Device.id != exclude_device_id,
                )
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找同机柜设备失败", original_error=e)

    def find_by_customer_id(self, customer_id: int) -> List[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer))
                .filter(
                    Device.customer_id == customer_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def clear_customer(self, customer_id: int) -> int:
        """批量解绑客户名下所有设备（customer_id 置 NULL）。

        Returns:
            int: 受影响行数
        """
        from extensions import db
        result = db.session.query(Device).filter(
            Device.customer_id == customer_id,
        ).update({Device.customer_id: None}, synchronize_session=False)
        return result

    def find_by_status(self, status: int) -> List[Device]:
        try:
            return self._base_query().filter(Device.status == status).all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_child_devices(self, parent_device_id: int) -> List[Device]:
        try:
            from app.models.device_server_ext import DeviceServerExt
            return (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(DeviceServerExt.parent_device_id == parent_device_id)
                .order_by(DeviceServerExt.node_position)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找子设备失败", original_error=e)

    def find_by_room_id(self, room_id: int) -> List[Device]:
        try:
            from app.models.cabinet import Cabinet
            return (
                self._base_query()
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .options(joinedload(Device.cabinet))
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .order_by(Device.device_name)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_node_position_conflict(
        self, parent_device_id: int, node_position: int, exclude_device_id: int = None
    ) -> Optional[Device]:
        from app.models.device_server_ext import DeviceServerExt
        query = (
            self._base_query()
            .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
            .filter(
                DeviceServerExt.parent_device_id == parent_device_id,
                DeviceServerExt.node_position    == node_position,
                Device.status           != DeviceStatus.SCRAPPED,
            )
        )
        if exclude_device_id:
            query = query.filter(Device.id != exclude_device_id)
        return query.first()


    def _apply_device_filters(
        self,
        query,
        cabinet_id=None,
        customer_id=None,
        device_id=None,
        room_id=None,
        parent_device_id=None,
        is_chassis=None,
        device_type=None,
        device_subtype=None,
        include_scrapped=False,
        has_ssh=None,
    ):
        """统一设备过滤条件，供 get_all_devices 和 count 查询共用"""
        from app.models.cabinet import Cabinet

        if not include_scrapped:
            query = query.filter(Device.status != DeviceStatus.SCRAPPED)

        if cabinet_id:
            query = query.filter(Device.cabinet_id == cabinet_id)
        if customer_id:
            query = query.filter(Device.customer_id == customer_id)
        if device_id:
            query = query.filter(Device.id == device_id)
        if room_id:
            query = query.join(Cabinet, Device.cabinet_id == Cabinet.id).filter(
                Cabinet.room_id == room_id
            )
        if parent_device_id is not None:
            from app.models.device_server_ext import DeviceServerExt
            query = query.join(DeviceServerExt, DeviceServerExt.device_id == Device.id).filter(
                DeviceServerExt.parent_device_id == parent_device_id
            )
        if is_chassis is not None:
            from app.models.device_server_ext import DeviceServerExt
            if parent_device_id is None:
                query = query.join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
            query = query.filter(DeviceServerExt.is_chassis == is_chassis)
        if device_type:
            query = query.filter(Device.device_type == device_type)
        if device_subtype:
            query = query.filter(Device.device_subtype == device_subtype)

        if has_ssh is not None:
            from app.models.switch_credentials import SwitchCredentials
            query = query.join(SwitchCredentials, SwitchCredentials.device_id == Device.id)
            if has_ssh:
                query = query.filter(SwitchCredentials.has_ssh == True)
            else:
                query = query.filter(SwitchCredentials.has_ssh == False)

        return query

    @monitor_query_performance
    def get_all_devices(
        self,
        cabinet_id: int = None,
        customer_id: int = None,
        device_id: int = None,
        room_id: int = None,
        parent_device_id: int = None,
        is_chassis: int = None,
        device_type: str = None,
        device_subtype: str = None,
        page: int = 1,
        page_size: int = 20,
        include_scrapped: bool = False,   # BUG-3 修复：显式参数控制是否包含报废设备
        has_ssh: bool = None,             # has_ssh 筛选（仅网络设备有效）
    ) -> Dict[str, Any]:
        try:
            base_query = self._base_query().options(
                joinedload(Device.switch_credential),
            )

            filtered_query = self._apply_device_filters(
                base_query,
                cabinet_id=cabinet_id,
                customer_id=customer_id,
                device_id=device_id,
                room_id=room_id,
                parent_device_id=parent_device_id,
                is_chassis=is_chassis,
                device_type=device_type,
                device_subtype=device_subtype,
                include_scrapped=include_scrapped,
                has_ssh=has_ssh,
            )

            total = (
                filtered_query
                .with_entities(func.count(distinct(Device.id)))
                .scalar()
                or 0
            )
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            page = max(1, min(page, total_pages or 1))
            offset = (page - 1) * page_size
            ensure_offset_within_limit(offset)

            devices = (
                filtered_query
                .order_by(Device.device_name)
                .limit(page_size)
                .offset(offset)
                .all()
            )

            return {
                "devices":     [d.to_dict() for d in devices],
                "total":       total,
                "total_pages": total_pages,
                "page":        page,
                "page_size":   page_size,
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取设备列表失败", original_error=e)

    def list_devices_keyset(
        self,
        cabinet_id: int = None,
        customer_id: int = None,
        device_id: int = None,
        room_id: int = None,
        parent_device_id: int = None,
        is_chassis: int = None,
        device_type: str = None,
        device_subtype: str = None,
        include_scrapped: bool = False,
        has_ssh: bool = None,
        after_name: str = None,
        after_id: int = None,
        limit: int = 5000,
    ) -> List[Device]:
        """按 ``(device_name, id)`` keyset 游标取一页设备（全量遍历场景，如导出）。

        与 :meth:`get_all_devices` 的两点本质差别：

        - **不执行 COUNT、不使用 OFFSET**。``OFFSET`` 翻到第 k 页要先扫描并丢弃
          ``(k-1) * limit`` 行，全量遍历的累计代价是 O(n²/limit)；keyset 每页都是
          索引范围扫描（需 ``(device_name, id)`` 联合索引），累计 O(n)。
        - 游标是"上一页最后一条的 ``(device_name, id)``"而非页码 —— 遍历期间即使
          有并发插入/删除也不会漏行或重复行（``OFFSET`` 的经典问题）。

        游标语义：只返回**严格大于** ``(after_name, after_id)`` 的行。
        ``device_name`` 非唯一，必须带 ``id`` 打破并列；``device_name`` 建表时为
        NOT NULL（``app/models/device.py``），因此不存在 NULL 参与比较导致**静默丢行**
        的风险 —— 若将来该列放宽为可空，本方法必须改用 ``COALESCE`` 或改走纯 id 游标。

        Args:
            after_name / after_id: 上一页最后一条的游标值；首次取传 None
            limit: 单页行数
            其余参数与 :meth:`get_all_devices` 同义

        Returns:
            按 ``(device_name, id)`` 升序排列的 ORM 设备对象（调用方负责序列化）
        """
        try:
            filtered_query = self._apply_device_filters(
                self._base_query().options(joinedload(Device.switch_credential)),
                cabinet_id=cabinet_id,
                customer_id=customer_id,
                device_id=device_id,
                room_id=room_id,
                parent_device_id=parent_device_id,
                is_chassis=is_chassis,
                device_type=device_type,
                device_subtype=device_subtype,
                include_scrapped=include_scrapped,
                has_ssh=has_ssh,
            )

            if after_name is not None:
                cursor_id = after_id if after_id is not None else 0
                filtered_query = filtered_query.filter(
                    or_(
                        Device.device_name > after_name,
                        and_(
                            Device.device_name == after_name,
                            Device.id > cursor_id,
                        ),
                    )
                )

            return (
                filtered_query
                .order_by(Device.device_name, Device.id)
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("按游标获取设备列表失败", original_error=e)

    @monitor_query_performance
    def search_devices(
        self,
        keyword: str = None,
        device_type: str = None,
        status: int = None,
        cabinet_id: int = None,
        customer_id: int = None,
        page: int = 1,
        page_size: int = 20,
        include_scrapped: bool = False,
    ) -> Dict[str, Any]:
        try:
            from app.models.device_hardware import DeviceHardware

            filters: Dict[str, Any] = {}
            if device_type:
                filters["device_type"] = device_type
            if cabinet_id:
                filters["cabinet_id"] = cabinet_id
            if customer_id:
                filters["customer_id"] = customer_id
            if status is not None:
                filters["status"] = status

            exclude_filters: Dict[str, Any] = {}
            if not include_scrapped and status is None:
                exclude_filters["status"] = DeviceStatus.SCRAPPED

            join_search_fields = [
                {"model": DeviceHardware, "field": "ip_address", "cast": "Text"},
                {"model": DeviceHardware, "field": "ipmi_address"},
            ]

            joins = [{"model": DeviceHardware, "type": "outerjoin"}]

            result = self.search(
                search_fields=[
                    "device_name", "serial_number", "hostname",
                    "management_ip", "mac_address",
                ],
                keyword=keyword,
                filters=filters if filters else None,
                exclude_filters=exclude_filters if exclude_filters else None,
                page=page,
                page_size=page_size,
                joins=joins,
                join_search_fields=join_search_fields,
                distinct=True,
            )

            data_ids = [d.id for d in result["data"]]
            if data_ids:
                loaded = (
                    self._base_query()
                    .filter(Device.id.in_(data_ids))
                    .options(joinedload(Device.switch_credential))
                    .order_by(Device.device_name)
                    .all()
                )
                result["data"] = loaded

            return result
        except SQLAlchemyError as e:
            raise QueryExecutionError("搜索设备失败", original_error=e)


    def check_u_position_conflict(
        self,
        cabinet_id: int,
        u_position: int,
        height_u: int,
        exclude_id: int = None,
    ) -> List[Device]:
        """检查 U 位冲突（SQL 范围重叠，不在 Python 做集合运算）

        两区间 [a, a+ha) 与 [b, b+hb) 重叠的充要条件：
            a < b+hb  AND  b < a+ha
        """
        try:
            from app.models.device_server_ext import DeviceServerExt
            q = (
                self._base_query()
                .outerjoin(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.u_position.isnot(None),
                    Device.height_u.isnot(None),
                    DeviceServerExt.parent_device_id.is_(None),
                    Device.status != DeviceStatus.SCRAPPED,
                    Device.u_position < u_position + height_u,
                    u_position < Device.u_position + Device.height_u,
                )
            )
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return q.all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查 U 位冲突失败", original_error=e)


    @monitor_query_performance
    def get_room_device_statistics(self, room_id: int) -> Dict[str, int]:
        """机房设备统计（适配 device_type: server/network/other 新方案）"""
        try:
            from app.models.cabinet import Cabinet

            result = (
                self._base_query()
                .with_entities(
                    func.count(Device.id).label("device_count"),
                    func.sum(func.coalesce(Device.height_u, 0)).label("used_u"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .first()
            )

            type_stats = (
                self._base_query()
                .with_entities(
                    Device.device_type,
                    func.count(Device.id).label("count"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Device.device_type)
                .all()
            )

            type_statistics = {"网络设备": 0, "服务器": 0, "其他": 0}
            for stat in type_stats:
                dt = (stat.device_type or "").lower()
                if dt == "network":
                    type_statistics["网络设备"] += stat.count
                elif dt == "server":
                    type_statistics["服务器"] += stat.count
                else:
                    type_statistics["其他"] += stat.count

            type_u_stats = (
                self._base_query()
                .with_entities(
                    Device.device_type,
                    Device.height_u,
                    func.count(Device.id).label("count"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Device.device_type, Device.height_u)
                .all()
            )

            type_u_statistics = {"网络设备": {}, "服务器": {}, "其他": {}}
            for stat in type_u_stats:
                dt = (stat.device_type or "").lower()
                if dt == "network":
                    cat = "网络设备"
                elif dt == "server":
                    cat = "服务器"
                else:
                    cat = "其他"
                u_key = f"{stat.height_u or 1}U"
                type_u_statistics[cat][u_key] = (
                    type_u_statistics[cat].get(u_key, 0) + stat.count
                )

            return {
                "device_count":      result.device_count or 0,
                "used_u":            int(result.used_u or 0),
                "type_statistics":   type_statistics,
                "type_u_statistics": type_u_statistics,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取机房设备统计失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("获取机房设备统计失败", original_error=e)


    def sync_chassis_nodes(self, chassis_id: int, changed_params: Dict[str, Any]) -> bool:
        """同步机箱参数到全部子节点（BUG-13：仅对遵循命名规则的节点重命名）"""
        try:
            nodes = self.find_child_devices(chassis_id)
            if not nodes:
                return True

            syncable    = {"brand", "device_model", "cabinet_id", "customer_id"}
            hw_syncable = {"cpu", "cpu_way", "memory"}
            hw_fields   = {f: changed_params[f] for f in hw_syncable if f in changed_params}

            chassis_name = changed_params.get("device_name")
            auto_name_pattern = re.compile(r"^.+-Node\d+$")

            for node in nodes:
                for field in syncable:
                    if field in changed_params:
                        setattr(node, field, changed_params[field])

                if hw_fields and node.hardware:
                    for f, v in hw_fields.items():
                        setattr(node.hardware, f, v)

                if chassis_name and auto_name_pattern.match(node.device_name or ""):
                    node.device_name = f"{chassis_name}-Node{node.node_position}"
                    node.notes = f"{chassis_name}的第{node.node_position}个节点"

            self.session.flush()
            logger.info(f"同步机箱 {chassis_id} 参数到 {len(nodes)} 个节点")
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("同步机箱节点失败", original_error=e)


    def count_active_devices(self) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_cabinet(self, cabinet_id: int) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_room(self, room_id: int) -> int:
        try:
            from app.models.cabinet import Cabinet
            return (
                self._base_query()
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_status(self, status) -> int:
        """按设备状态统计数量。"""
        try:
            return (
                self._base_query()
                .filter(
                    Device.status == status,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_switches(self) -> int:
        """统计交换机数量。

        数据契约：交换机的 device_type='network'，device_subtype='switch'。
        兼容历史数据中 device_type 直接写 'switch' 的情况。
        """
        try:
            return (
                self._base_query()
                .filter(
                    or_(
                        Device.device_subtype.ilike('%switch%'),
                        Device.device_type.ilike('%switch%'),
                    ),
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计交换机数量失败", original_error=e)

    def create(self, data: Dict[str, Any]) -> Device:
        try:
            safe_data = {k: v for k, v in data.items() if k in self._WRITABLE_FIELDS}
            device = Device(**safe_data)
            self.session.add(device)
            self.session.flush()
            return device
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建设备失败", original_error=e)

    def update(self, device_id: int, data: Dict[str, Any]) -> Optional[Device]:
        try:
            device = self.find_by_id(device_id)
            if not device:
                return None
            for k, v in data.items():
                if k in self._WRITABLE_FIELDS:
                    setattr(device, k, v)
            self.session.flush()
            return device
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新设备失败", original_error=e)

    def delete(self, device_id: int) -> bool:
        """软删除设备（遵循 __soft_delete__ = True），由调用方负责 commit"""
        return super().delete(device_id)

    def batch_update_status(self, device_ids: List[int], new_status: int) -> int:
        if not device_ids:
            return 0
        try:
            count = (
                self._base_query()
                .filter(Device.id.in_(device_ids))
                .update({"status": new_status}, synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量更新状态失败", original_error=e)

    def update_location(self, device_id: int, cabinet_id: int) -> bool:
        try:
            device = self._base_query().filter(Device.id == device_id).first()
            if not device:
                return False
            device.cabinet_id = cabinet_id
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新设备位置失败", original_error=e)

    def check_management_ip_exists(self, ip_address: str, exclude_id: int = 0) -> bool:
        """检查管理IP是否已被其他设备占用

        Args:
            ip_address: 管理IP地址
            exclude_id: 排除的设备ID

        Returns:
            bool: 存在返回True
        """
        if not ip_address:
            return False
        try:
            query = self._base_query().filter(Device.management_ip == ip_address)
            if exclude_id:
                query = query.filter(Device.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验管理IP失败", original_error=e)

    def check_device_name_duplicate(self, device_name: str, cabinet_id: int = None, exclude_id: int = 0) -> Optional[Device]:
        """检查同机柜内是否存在同名设备

        Args:
            device_name: 设备名称
            cabinet_id: 机柜ID（可选，若提供则仅检查同机柜）
            exclude_id: 排除的设备ID（更新时排除自身）

        Returns:
            冲突的 Device 对象，无冲突返回 None
        """
        if not device_name:
            return None
        try:
            query = self._base_query().filter(Device.device_name == device_name)
            from app.core.enums import DeviceStatus
            query = query.filter(Device.status != DeviceStatus.SCRAPPED)
            if cabinet_id:
                query = query.filter(Device.cabinet_id == cabinet_id)
            if exclude_id:
                query = query.filter(Device.id != exclude_id)
            return query.first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验设备名称失败", original_error=e)

    def check_serial_number_exists(self, serial_number: str, exclude_id: int = None) -> bool:
        if not serial_number:
            return False
        try:
            q = self._base_query().filter(Device.serial_number == serial_number)
            from app.core.enums import DeviceStatus
            q = q.filter(Device.status != DeviceStatus.SCRAPPED)
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return self.session.query(q.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验序列号失败", original_error=e)

    def generate_unique_serial_number(
        self, prefix="SN", format_type="timestamp", length=16, max_retries=10
    ) -> str:
        for _ in range(max_retries):
            if format_type == "timestamp":
                ts = now_utc_naive().strftime("%Y%m%d%H%M%S")
                sn = f"{prefix}{ts}{''.join(str(random.randint(0,9)) for _ in range(4))}"
            elif format_type == "uuid":
                sn = f"{prefix}{str(uuid.uuid4()).upper()}" if prefix else str(uuid.uuid4()).upper()
            elif format_type == "random":
                sn = f"{prefix}{''.join(str(random.randint(0,9)) for _ in range(length))}"
            elif format_type == "custom":
                date = now_utc_naive().strftime("%Y%m%d")
                sn = f"{prefix}{date}{''.join(str(random.randint(0,9)) for _ in range(6))}"
            else:
                raise ValueError(f"不支持的 format_type: {format_type}")
            if not self.check_serial_number_exists(sn):
                return sn
        raise RuntimeError(f"无法生成唯一序列号，已重试 {max_retries} 次")

    @monitor_query_performance
    def get_device_statistics(self) -> Dict[str, Any]:
        try:
            basic = self._base_query().with_entities(
                func.count(Device.id).label("total"),
                func.sum(case((Device.status == DeviceStatus.ONLINE, 1), else_=0)).label("online"),
                func.sum(case((Device.status == DeviceStatus.AVAILABLE, 1), else_=0)).label("available"),
                func.sum(case((Device.status == DeviceStatus.OFFLINE, 1), else_=0)).label("offline"),
                func.sum(case((Device.status == DeviceStatus.MAINTENANCE, 1), else_=0)).label("maintenance"),
                func.sum(case((Device.status == DeviceStatus.RESERVED, 1), else_=0)).label("reserved"),
                func.sum(case((Device.power.isnot(None), Device.power), else_=0)).label("total_power"),
                func.avg(case((Device.power.isnot(None), Device.power), else_=None)).label("avg_power"),
            ).first()

            status_rows = (
                self._base_query().with_entities(Device.status, func.count(Device.id))
                .group_by(Device.status).all()
            )
            type_rows = (
                self._base_query().with_entities(Device.device_type, func.count(Device.id))
                .filter(Device.status != DeviceStatus.SCRAPPED)
                .group_by(Device.device_type).all()
            )

            from app.models.cabinet import Cabinet
            cabinet_rows = (
                self.session.query(Cabinet.cabinet_number, func.count(Device.id).label("cnt"))
                .join(Device, Cabinet.id == Device.cabinet_id)
                .filter(
                    Cabinet.deleted_at.is_(None),
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Cabinet.id, Cabinet.cabinet_number).all()
            )

            return {
                "total_devices":       basic.total or 0,
                "online_devices":      basic.online or 0,
                "available_devices":   basic.available or 0,
                "offline_devices":     basic.offline or 0,
                "maintenance_devices": basic.maintenance or 0,
                "reserved_devices":    basic.reserved or 0,
                "status_statistics":   {DeviceStatus.STATUS_NAMES.get(s, f"状态{s}"): c for s, c in status_rows},
                "type_statistics":     {t or "unknown": c for t, c in type_rows},
                "cabinet_statistics":  {cn: c for cn, c in cabinet_rows},
                "power_statistics": {
                    "total_power":   float(basic.total_power or 0),
                    "average_power": round(float(basic.avg_power or 0), 2),
                },
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取统计信息失败", original_error=e)


    @monitor_query_performance
    def get_deleted_devices(
        self,
        page: int = 1,
        page_size: int = 20,
        start_date=None,
        end_date=None,
        room_id: int = None,
        cabinet_id: int = None,
        device_type: str = None,
        ip_search: str = None,
    ) -> Dict[str, Any]:
        """查询已软删除的设备列表（回收站）

        支持：分页、删除时间段、机房/机柜/设备类型筛选、IP地址搜索
        IP搜索同时匹配 devices.management_ip、device_hardware.ipmi_address、
        device_hardware.ip_address（JSON列 LIKE cast）
        """
        try:
            from app.models.device_hardware import DeviceHardware
            from app.models.cabinet import Cabinet

            query = (
                self.session.query(Device)
                .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
                .filter(Device.deleted_at.isnot(None))
            )

            if start_date:
                query = query.filter(Device.deleted_at >= start_date)
            if end_date:
                query = query.filter(Device.deleted_at <= end_date)

            if cabinet_id:
                query = query.filter(Device.cabinet_id == cabinet_id)
            elif room_id:
                query = query.filter(
                    func.json_extract(
                        DeviceHardware.device_config,
                        f"$.{SNAPSHOT_KEY_LOCATION}.room_id"
                    ) == str(room_id)
                )

            if device_type:
                query = query.filter(Device.device_type == device_type)

            if ip_search:
                ip_pattern = f"%{ip_search}%"
                hw_ip_match = DeviceHardware.ip_address.cast(db.Text).ilike(ip_pattern)
                query = query.filter(
                    or_(
                        Device.management_ip.ilike(ip_pattern),
                        DeviceHardware.ipmi_address.ilike(ip_pattern),
                        hw_ip_match,
                    )
                )

            total = (
                query.with_entities(func.count(distinct(Device.id))).scalar() or 0
            )
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            page = max(1, min(page, total_pages or 1))
            offset = (page - 1) * page_size
            ensure_offset_within_limit(offset)

            devices = (
                query
                .options(joinedload(Device.hardware), joinedload(Device.customer))
                .order_by(Device.deleted_at.desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

            devices_data = []
            for d in devices:
                dd = d.to_dict()
                if d.hardware and d.hardware.device_config:
                    dd[SNAPSHOT_KEY_LOCATION] = d.hardware.device_config.get(SNAPSHOT_KEY_LOCATION)
                    dd[SNAPSHOT_KEY_CHILDREN] = d.hardware.device_config.get(SNAPSHOT_KEY_CHILDREN)
                devices_data.append(dd)

            return {
                "devices": devices_data,
                "total": total,
                "total_pages": total_pages,
                "page": page,
                "page_size": page_size,
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("查询已删除设备失败", original_error=e)

    def get_child_device_ids(self, parent_device_id: int) -> list[int]:
        """查询机箱的所有子节点 device_id 列表。

        parent_device_id 是 DeviceServerExt 表的列，不是 Device 的列。
        """
        from app.models.device_server_ext import DeviceServerExt
        rows = self.session.query(DeviceServerExt.device_id).filter_by(
            parent_device_id=parent_device_id
        ).all()
        return [r[0] for r in rows if r[0] is not None]
