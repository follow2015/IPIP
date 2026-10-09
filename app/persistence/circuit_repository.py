# -*- coding: utf-8 -*-
"""线路 Repository

唯一合法的 `circuits` / `circuit_segments` 表访问入口。
Service 层禁止直接使用 db_manager 或裸 SQL。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.core.pagination_limits import ensure_offset_within_limit
from app.models.carrier import Carrier
from app.models.circuit import Circuit, CircuitSegment
from app.models.customer import Customer
from app.models.device import Device
from app.models.network_port import NetworkPort
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.utils.logging import get_logger
from app.utils.time_utils import utc_today

logger = get_logger(__name__)


class CircuitRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """线路 Repository

    软删过滤由基类的 `_base_query()` 统一处理（过滤 `deleted_at IS NULL`），
    本类不再重复写该条件——只在一处维护，避免遗漏。
    """

    def __init__(self, session=None):
        super().__init__(Circuit, session)


    def get_by_circuit_no(self, circuit_no: str) -> Optional[Circuit]:
        """按电路号精确查（重名判据 AC-C-01）。

        只匹配**活跃行**（`deleted_token == ''`）：软删行的电路号已被释放，
        不应阻挡新线路复用（AC-C-27）。
        """
        return (
            self.session.query(Circuit)
            .filter(Circuit.circuit_no == circuit_no, Circuit.deleted_token == "")
            .first()
        )

    def resolve_owner_names(
        self, carrier_ids, customer_ids
    ) -> tuple[Dict[int, str], Dict[int, str]]:
        """批量解析线路归属名称（运营商名 / 客户名），供序列化注入。

        **刻意不走 `_base_query()` 的软删过滤**：运营商名下线路全部终止后
        可被软删（AC-C-20 只拦未终止线路），此时历史线路详情仍要能显示
        名称（前端 services/carrier.ts 注释声明的语义）。两条 IN 查询
        （列表/详情各一次调用），不做逐行解析，无 N+1。
        """
        cids = {i for i in carrier_ids if i is not None}
        cuids = {i for i in customer_ids if i is not None}
        carrier_names: Dict[int, str] = {}
        customer_names: Dict[int, str] = {}
        if cids:
            carrier_names = {
                r.id: r.name
                for r in self.session.query(Carrier).filter(Carrier.id.in_(cids))
            }
        if cuids:
            customer_names = {
                r.id: r.customer_name
                for r in self.session.query(Customer).filter(Customer.id.in_(cuids))
            }
        return carrier_names, customer_names

    def resolve_hop_refs(
        self, device_ids, port_ids
    ) -> tuple[Dict[int, str], Dict[int, str]]:
        """批量解析分段跳接引用名称（设备名 / 端口名），供分段序列化注入。

        **刻意不走 `_base_query()` 的软删过滤**：跳接点是软引用（§3.3），
        设备/端口报废删除后，历史线路仍要能显示当年接在哪里。两条 IN
        查询，无 N+1。解析不到（id 不存在）由调用方以 *_missing 标记。
        """
        dids = {i for i in device_ids if i is not None}
        pids = {p for p in port_ids if p is not None}
        device_names: Dict[int, str] = {}
        port_names: Dict[int, str] = {}
        if dids:
            device_names = {
                r.id: r.device_name
                for r in self.session.query(Device).filter(Device.id.in_(dids))
            }
        if pids:
            port_names = {
                r.id: r.port_name
                for r in self.session.query(NetworkPort).filter(NetworkPort.id.in_(pids))
            }
        return device_names, port_names

    def list_with_filters(
        self, filters: Optional[Dict[str, Any]] = None, page: int = 1, per_page: int = 20
    ) -> Dict[str, Any]:
        """分页列表。

        支持筛选：`status` / `carrier_id` / `customer_id` / `room_id`（A 或 Z 端）/
        `billing_mode` / `keyword`（电路号或名称模糊）/ `expiring_in_days`（到期天数内）。
        """
        filters = filters or {}
        query = self._base_query()

        if filters.get("status"):
            query = query.filter(Circuit.status == filters["status"])
        if filters.get("carrier_id"):
            query = query.filter(Circuit.carrier_id == filters["carrier_id"])
        if filters.get("customer_id"):
            query = query.filter(Circuit.customer_id == filters["customer_id"])
        if filters.get("billing_mode"):
            query = query.filter(Circuit.billing_mode == filters["billing_mode"])
        if filters.get("room_id"):
            rid = filters["room_id"]
            query = query.filter(
                (Circuit.a_end_room_id == rid) | (Circuit.z_end_room_id == rid)
            )

        keyword = (filters.get("keyword") or "").strip()
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                Circuit.circuit_no.like(like) | Circuit.name.like(like)
            )

        expiring_in_days = filters.get("expiring_in_days")
        if expiring_in_days:
            from datetime import timedelta

            deadline = utc_today() + timedelta(days=int(expiring_in_days))
            query = query.filter(
                Circuit.end_date.isnot(None), Circuit.end_date <= deadline
            )

        query = query.order_by(Circuit.id.desc())

        total = query.count()
        offset = (max(int(page), 1) - 1) * max(int(per_page), 1)
        offset = ensure_offset_within_limit(offset)
        items = query.offset(offset).limit(max(int(per_page), 1)).all()
        return {"items": items, "total": total, "page": page, "per_page": per_page}

    def list_expiring(self, within_days: int = 30) -> List[Circuit]:
        """取即将到期的线路（AC-C-03）。

        **"当前日期"必须取 `utc_today()`**（判据 AC-C-34）：本仓 `time_utils.py`
        明写不可用 `date.today()`，用本地日会在 UTC+8 时区错判一天。
        """
        from datetime import timedelta

        deadline = utc_today() + timedelta(days=int(within_days))
        return (
            self._base_query()
            .filter(Circuit.end_date.isnot(None), Circuit.end_date <= deadline)
            .order_by(Circuit.end_date)
            .all()
        )

    def find_by_connection_id(self, connection_id: int) -> List[Circuit]:
        """按 `network_connections` 反查受影响的线路（AC-C-04 / AC-C-28）。

        一条连接可能被**多条线路**共享（共享上联），故返回列表而非单条。
        """
        seg_subq = (
            self.session.query(CircuitSegment.circuit_id)
            .filter(CircuitSegment.connection_id == connection_id)
            .distinct()
        )
        return (
            self._base_query().filter(Circuit.id.in_(seg_subq)).all()
        )

    def count_sharing_connection(self, connection_id: int) -> int:
        """统计有多少条线路引用了该连接（AC-C-28 的"被 N 条线路共享"标注）。"""
        return int(
            self.session.query(func.count(CircuitSegment.circuit_id.distinct()))
            .filter(CircuitSegment.connection_id == connection_id)
            .scalar()
            or 0
        )


    def count_active_by_customer(self, customer_id: int) -> int:
        """统计客户名下**未终止**的线路数（AC-C-23 的阻断判据）。

        排除 `terminated`：已终止线路是历史，不该阻止客户终止/删除流程。
        """
        return int(
            self.session.query(func.count(Circuit.id))
            .filter(
                Circuit.customer_id == customer_id,
                Circuit.deleted_at.is_(None),
                Circuit.status != "terminated",
            )
            .scalar()
            or 0
        )

    def stats_by_customer(self, customer_id: int) -> Dict[str, Any]:
        """客户名下的线路统计（AC-C-22 资产视图）。

        返回：总数、按 status 分组、按 billing_mode 分组、月租合计。
        月租合计用 `func.coalesce` 兜 NULL——`monthly_fee` 可空，
        SUM 遇全 NULL 会返回 None 而不是 0，前端会显示成空。
        """
        base = self.session.query(Circuit).filter(
            Circuit.customer_id == customer_id, Circuit.deleted_at.is_(None)
        )

        total = base.count()

        status_rows = (
            base.with_entities(Circuit.status, func.count(Circuit.id))
            .group_by(Circuit.status)
            .all()
        )
        billing_rows = (
            base.with_entities(Circuit.billing_mode, func.count(Circuit.id))
            .group_by(Circuit.billing_mode)
            .all()
        )
        monthly_sum = (
            base.with_entities(func.coalesce(func.sum(Circuit.monthly_fee), 0)).scalar()
            or 0
        )

        return {
            "total": int(total),
            "by_status": {str(r[0]): int(r[1]) for r in status_rows},
            "by_billing_mode": {str(r[0]): int(r[1]) for r in billing_rows},
            "monthly_fee_total": float(monthly_sum),
        }

    def list_by_customer(self, customer_id: int) -> List[Circuit]:
        """客户名下全部线路（AC-C-25 详情标签页）。"""
        return (
            self._base_query()
            .filter(Circuit.customer_id == customer_id)
            .order_by(Circuit.end_date.is_(None), Circuit.end_date)
            .all()
        )

    def list_active_by_carrier(self, carrier_id: int) -> List[Circuit]:
        """运营商名下**未终止**的线路（AC-C-20 删除阻断的判据）。

        与 `count_active_by_customer` 同一口径：排除 `terminated`（已终止线路是
        历史，不该阻止运营商删除）。软删过滤由 `_base_query()` 统一处理，
        此处不重复写 `deleted_at` 条件。
        """
        return (
            self._base_query()
            .filter(
                Circuit.carrier_id == carrier_id,
                Circuit.status != "terminated",
            )
            .all()
        )


    def soft_delete_circuit(self, circuit: Circuit) -> None:
        """软删线路：置 `deleted_at`，并把 `deleted_token` 写成唯一占位值。

        **`circuit_no` 保持不变**（AC-C-27）。唯一键是 `UNIQUE(circuit_no, deleted_token)`，
        写 token 后原电路号即被释放，可重新开通；同时已软删行仍可按原电路号追溯。

        token 必须带 `id` 与时间戳：只写时间戳在批量删除时可能同毫秒碰撞。
        token 的**生成实现**在 `app/utils/time_utils.py::soft_delete_token`
        （全仓唯一实现点，Carrier 也走同一函数，勿在此处另写一份 f-string）。
        """
        from app.utils.time_utils import now_utc_naive, soft_delete_token

        circuit.deleted_at = now_utc_naive()
        circuit.deleted_token = soft_delete_token(circuit.id, circuit.deleted_at)
        self.session.flush()

    def delete_segments_by_circuit(self, circuit_id: int) -> int:
        """物理删除线路的全部分段（AC-C-06 的服务层显式清理）。

        不能依赖 `ON DELETE CASCADE`：软删只 UPDATE `deleted_at`，父行从未真正
        DELETE，DB 级联永不触发（本仓 `base.py:343-348` 的既有行为）。
        分段**不启用软删**（无独立生命周期），物理删不留痕是可接受的。
        """
        return int(
            self.session.query(CircuitSegment)
            .filter(CircuitSegment.circuit_id == circuit_id)
            .delete(synchronize_session=False)
            or 0
        )

    def mark_connection_lost(self, connection_id: int) -> int:
        """连接被删除时，把引用它的分段标为"锚点已失效"（AC-C-31）。

        置 `connection_id_lost = 1` 而不是置 `connection_id = NULL`：
        后者无法区分"从未纳管"（正常）与"曾纳管但已失效"（必须告警），
        而 §3.3 已确立"未纳管跳接点允许为空"，两种情形都会出现 NULL。
        """
        return int(
            self.session.query(CircuitSegment)
            .filter(CircuitSegment.connection_id == connection_id)
            .update(
                {CircuitSegment.connection_id_lost: 1},
                synchronize_session=False,
            )
            or 0
        )


    def list_segments(self, circuit_id: int) -> List[CircuitSegment]:
        return (
            self.session.query(CircuitSegment)
            .filter(CircuitSegment.circuit_id == circuit_id)
            .order_by(CircuitSegment.seq)
            .all()
        )

    def list_affected_devices(self, circuit_id: int) -> List[Any]:
        """分段关联的全部设备（AC-C-02）。

        故障定位要的是"这条线路一断，哪几台设备受影响"。分段上只有两种锚点：

        - `device_id`：跳接设备，直接就是设备；
        - `connection_id`：端口连接，要经 `local_port_id` / `peer_port_id`
          落到 `network_ports.device_id` 才拿得到设备（连接行本身不存设备）。

        两条路都要走，只取 `device_id` 会漏掉占绝大多数的"连接型分段"。
        返回去重后的 `Device` 行，按 id 升序——顺序稳定，测试才断言得住。
        """
        from app.models.device import Device
        from app.models.network_connection import NetworkConnection
        from app.models.network_port import NetworkPort

        segments = self.list_segments(circuit_id)
        device_ids = {int(s.device_id) for s in segments if s.device_id is not None}
        conn_ids = {
            int(s.connection_id) for s in segments if s.connection_id is not None
        }

        if conn_ids:
            port_ids: set = set()
            for local_port_id, peer_port_id in self.session.query(
                NetworkConnection.local_port_id, NetworkConnection.peer_port_id
            ).filter(NetworkConnection.id.in_(conn_ids)):
                for pid in (local_port_id, peer_port_id):
                    if pid is not None:
                        port_ids.add(int(pid))
            if port_ids:
                device_ids.update(
                    int(row[0])
                    for row in self.session.query(NetworkPort.device_id)
                    .filter(NetworkPort.id.in_(port_ids))
                    if row[0] is not None
                )

        if not device_ids:
            return []
        return (
            self.session.query(Device)
            .filter(Device.id.in_(sorted(device_ids)))
            .order_by(Device.id)
            .all()
        )

    def replace_segments(self, circuit_id: int, payloads: List[Dict[str, Any]]) -> None:
        """整批替换分段（先全删再全插）。

        设计文档 §5.3 决策：有序序列的逐条 CRUD 会产生序号空洞与重复中间态，
        故只提供"整批替换"一种写形态。
        """
        self.delete_segments_by_circuit(circuit_id)
        for idx, p in enumerate(payloads, start=1):
            self.session.add(
                CircuitSegment(circuit_id=circuit_id, seq=idx, **p)
            )
        self.session.flush()


class CarrierNameResolver:
    """线路详情里解析运营商名称的小工具。

    单独放是因为它跨两张表，且**允许返回 None**——运营商被软删后，
    线路仍应有名称可读（历史信息），故这里读真库全量而非只查活跃行。
    """

    @staticmethod
    def resolve(session, carrier_ids: List[int]) -> Dict[int, str]:
        if not carrier_ids:
            return {}
        rows = (
            session.query(Carrier.id, Carrier.name)
            .filter(Carrier.id.in_(carrier_ids))
            .all()
        )
        return {int(r[0]): r[1] for r in rows}
