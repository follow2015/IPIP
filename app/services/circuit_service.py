# -*- coding: utf-8 -*-
"""线路服务层 —— G1

承载四类业务规则，全部**集中在本文件**（设计文档 §9：它们共享线路领域上下文，
故不按行数拆分）：

1. 带宽与计费规则 R0–R6（§5.2）
2. 状态机迁移校验（§4）
3. 软删与分段的显式清理（§3.2 / §3.3）
4. 影响面反查（§6）

**不在此层做的事**：任何 DB 访问都走 `CircuitRepository` / `CarrierRepository`；
HTTP 层的入参形状校验走 `app/schemas/circuit.py`，本层只做**跨字段的业务规则**
（这类规则 schema 层做不了，因为要看已有值）。
"""
from typing import Any, Dict, List, Optional

from app.core.enums import (
    COMMIT_BILLING_MODES,
    BillingMode,
    CIRCUIT_STATUS_TRANSITIONS,
    CircuitStatus,
)
from app.exceptions.validation import ValidationError
from app.models.circuit import Circuit
from app.persistence.carrier_repository import CarrierRepository
from app.persistence.circuit_repository import CircuitRepository
from extensions import db
from app.utils.logging import get_logger
from app.utils.time_utils import now_utc_naive, soft_delete_token

logger = get_logger(__name__)


class CircuitService:
    """线路服务"""

    def __init__(self, repository: Optional[CircuitRepository] = None,
                 carrier_repository: Optional[CarrierRepository] = None):
        self.repository = repository or CircuitRepository()
        self.carrier_repository = carrier_repository or CarrierRepository()


    @staticmethod
    def apply_billing_rules(data: Dict[str, Any]) -> Dict[str, Any]:
        """应用 R0–R5，返回**规范化后**的落库字段。

        在 create 与 update 两条路径上都必须调用——只在一处调用是常见漏洞：
        更新时改了 `billing_mode` 却没重算 `committed_mbps`，就会留下非法组合。

        Raises:
            ValidationError: 违反任一规则（400）。
        """
        mode = data.get("billing_mode") or BillingMode.FLAT.value
        try:
            mode_enum = BillingMode(mode)
        except ValueError as exc:
            raise ValidationError(
                message=f"不支持的计费模式：{mode}", field="billing_mode"
            ) from exc

        bandwidth = data.get("bandwidth_mbps")
        committed = data.get("committed_mbps")
        overage = data.get("overage_unit_price")
        traffic = data.get("traffic_unit_price")

        if mode_enum != BillingMode.PER_GB and bandwidth is None:
            raise ValidationError(
                message=f"计费模式为 {mode} 时端口带宽必填", field="bandwidth_mbps"
            )

        if bandwidth is not None and committed is not None and committed == bandwidth:
            mode_enum = BillingMode.FLAT
            committed = None

        if mode_enum == BillingMode.PER_GB:
            if traffic is None:
                raise ValidationError(
                    message="按流量计费（per_gb）必须填写流量单价",
                    field="traffic_unit_price",
                )
            committed = None
        elif mode_enum in COMMIT_BILLING_MODES:
            if committed is None:
                raise ValidationError(
                    message="保底计费模式必须填写保底带宽", field="committed_mbps"
                )
            if bandwidth is None:
                raise ValidationError(
                    message="保底计费模式必须填写端口带宽", field="bandwidth_mbps"
                )
            if committed >= bandwidth:
                raise ValidationError(
                    message="保底带宽必须小于端口带宽；若两者相同请直接用端口买断（flat）",
                    field="committed_mbps",
                )
            if overage is None:
                raise ValidationError(
                    message="保底计费模式必须填写超量单价", field="overage_unit_price"
                )

        if mode_enum == BillingMode.FLAT:
            committed = None

        out = dict(data)
        out["billing_mode"] = mode_enum.value
        out["committed_mbps"] = committed
        out["bandwidth_mbps"] = bandwidth
        out["overage_unit_price"] = overage
        out["traffic_unit_price"] = traffic
        return out

    @staticmethod
    def validate_dates(data: Dict[str, Any]) -> None:
        """R6：到期日不得早于起租日（判据 AC-C-29）。

        只校验**两者都非空**的情形：允许只填到期日（起租日未录入）——
        强制要求会挡住真实的"先录到期日再补起租日"工作流。
        """
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end < start:
            raise ValidationError(
                message="到期日不能早于起租日", field="end_date"
            )

    @staticmethod
    def validate_customer_ref(customer_id: Optional[int]) -> None:
        """R7：线路指向的客户必须存在，否则 400（判据 AC-C-26）。

        **不能靠外键兜底**：`circuits.customer_id` 上确有 `FK→customers.id
        ON DELETE RESTRICT`，但撞约束走的是 `IntegrityError` → 全局处理器转成
        **500 DATA_ACCESS_ERROR /「创建Circuit失败」**（已实测）。既违反判据要求的
        400，也完全说不出是哪个字段错了。前置校验才是能给用户看的那一条。
        """
        if customer_id is None:
            return
        from app.models.customer import Customer

        if not db.session.get(Customer, int(customer_id)):
            raise ValidationError(
                message=f"客户 {customer_id} 不存在", field="customer_id"
            )

    @staticmethod
    def validate_segment_refs(segments: List[Dict[str, Any]]) -> None:
        """R8：分段引用的连接必须存在，否则 400（判据 AC-C-09）。

        理由同 R7，且这里更微妙：`connection_id` 的外键是 `ON DELETE SET NULL`
        ——历史上它被删时会被**静默置空**而非报错，正是 AC-C-09 要防的"静默"；
        而对一个**从未存在过**的 id，SQLite/MySQL 又会撞 FK 抛 IntegrityError，
        变成 409 DATA_INTEGRITY_ERROR（已实测）。两条路都不符合判据，故前置校验。
        """
        conn_ids = {
            int(s["connection_id"])
            for s in segments
            if s.get("connection_id") is not None
        }
        if not conn_ids:
            return
        from app.persistence.network_connection_repository import (
            NetworkConnectionRepository,
        )

        existing = NetworkConnectionRepository().filter_existing_ids(conn_ids)
        missing = sorted(conn_ids - existing)
        if missing:
            raise ValidationError(
                message=f"连接不存在：{missing}，请先建立端口连接或改用跳接点描述",
                field="connection_id",
            )


    @staticmethod
    def validate_transition(current: str, target: str) -> None:
        """校验状态迁移是否在允许表内（AC-C-05）。

        终态 `terminated` 不允许再迁出：终止是租约的终点，要复用请新开线路
        （电路号在软删后会被释放，可以重新开通同一号码）。
        """
        try:
            cur = CircuitStatus(current)
            tgt = CircuitStatus(target)
        except ValueError as exc:
            raise ValidationError(message=f"非法线路状态：{exc}", field="status") from exc

        allowed = CIRCUIT_STATUS_TRANSITIONS.get(cur, set())
        if tgt not in allowed:
            names = sorted(s.value for s in allowed) or ["（无，已到终态）"]
            raise ValidationError(
                message=f"线路状态不能从 {cur.value} 迁移到 {tgt.value}，允许的目标：{', '.join(names)}",
                field="status",
            )


    def delete_circuit(self, circuit_id: int) -> None:
        """软删线路，并在同一事务内物理删除其全部分段（AC-C-06）。

        顺序：**先删分段，再软删线路**。反过来会让分段在瞬时指向一个已软删的父行，
        虽然最终一致，但中间态若被并发读会拿到不完整路径。

        `ON DELETE CASCADE` 在这里**不可用**：软删只 UPDATE `deleted_at`，
        父行从未真正 DELETE，DB 级联永不触发。
        """
        circuit = self.repository.find_by_id(circuit_id)
        if not circuit:
            raise ValidationError(message="线路不存在", field="id")

        self.repository.delete_segments_by_circuit(circuit_id)
        self.repository.soft_delete_circuit(circuit)
        logger.info("软删线路 id=%s circuit_no=%s（分段已清理）", circuit_id, circuit.circuit_no)


    def impact_by_connection(self, connection_id: int) -> Dict[str, Any]:
        """按连接反查受影响的线路与客户（AC-C-04 / AC-C-28）。

        一条连接可能被多条线路共享（共享上联），故返回全部并标注共享数——
        只返回第一条会让运维误以为"影响面就这一条"。
        """
        circuits = self.repository.find_by_connection_id(connection_id)
        shared = self.repository.count_sharing_connection(connection_id)
        return {
            "connection_id": connection_id,
            "shared_by": shared,
            "circuits": circuits,
            "customer_ids": sorted({c.customer_id for c in circuits if c.customer_id}),
        }

    def affected_devices(self, circuit_id: int) -> List[Dict[str, Any]]:
        """线路分段关联的全部设备（AC-C-02）。

        判据挂在"状态变更为 fault"上：故障时刻运维要的第一件事就是
        "这条线路压着哪几台设备"，逐段翻 connection 再翻端口是来不及的。
        这里只做读侧聚合，落库形态不变。
        """
        return [
            {"id": int(d.id), "device_name": d.device_name, "hostname": d.hostname}
            for d in self.repository.list_affected_devices(circuit_id)
        ]

    def affected_device_ids(self, circuit_id: int) -> List[int]:
        return [d["id"] for d in self.affected_devices(circuit_id)]


    def list_expiring(self, within_days: int = 30) -> List[Circuit]:
        """即将到期线路（AC-C-03）。日期口径走仓储层的 `utc_today()`。"""
        return self.repository.list_expiring(within_days)


class CarrierService:
    """运营商服务

    与线路同文件：`carriers` 只有两张表级关系（线路挂靠），独立成文件后
    两者的删除阻断规则会各自漂移——AC-C-20 的判据正是跨两张表的。
    """

    def __init__(self, repository: Optional[CarrierRepository] = None,
                 circuit_repository: Optional[CircuitRepository] = None):
        self.repository = repository or CarrierRepository()
        self.circuit_repository = circuit_repository or CircuitRepository()

    def delete_carrier(self, carrier_id: int) -> None:
        """软删运营商，**有未终止线路挂靠时拒绝**（AC-C-20）。

        为什么阻断必须写在这里而不是靠 `ON DELETE RESTRICT`：
        `Carrier` 是软删模型且全仓无 `purge` 入口，DB 级 RESTRICT **永不触发**
        （评审 B-8）。FK 上的 RESTRICT 只作为防御性兜底保留。
        """
        carrier = self.repository.find_by_id(carrier_id)
        if not carrier:
            raise ValidationError(message="运营商不存在", field="id")

        blocking = self.circuit_repository.list_active_by_carrier(carrier_id)
        if blocking:
            raise ValidationError(
                message=(
                    f"运营商「{carrier.name}」名下仍有 {len(blocking)} 条未终止线路，"
                    "请先转移或终止这些线路"
                ),
                field="carrier_id",
                details={
                    "circuit_ids": [c.id for c in blocking][:50],
                    "circuit_nos": [c.circuit_no for c in blocking][:50],
                },
            )

        carrier.deleted_at = now_utc_naive()
        carrier.deleted_token = soft_delete_token(carrier.id, carrier.deleted_at)
        self.repository.session.flush()
        logger.info("软删运营商 id=%s name=%s", carrier_id, carrier.name)
