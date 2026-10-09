# -*- coding: utf-8 -*-
"""
线路（Circuit）模型模块 —— G1

`Circuit` 与 `CircuitSegment` **同文件**：二者是 1:N 强聚合，拆开会把"线路及其路径"
这一完整语义割裂开（设计文档 §9 的模块划分口径——按语义内聚，不按行数）。

**关键区分**：`NetworkConnection` 描述"两个端口物理相连"（事实），
`Circuit` 描述"一条有主的、花钱的、要管的服务"（资产）。二者不是同一件事的两个视图，
不可互相推导，也**禁止**与 `network_connections.bandwidth` 双向同步（重蹈 F8 双真源）。
"""
from sqlalchemy import Index, UniqueConstraint

from app.core.enums import BANDWIDTH_STEP_SI, BillingMode, CircuitStatus
from app.models.base import MEDIUMTEXT, TINYINT, BaseModel
from extensions import db


class Circuit(BaseModel):
    """线路资产。

    启用软删除。唯一键采用**占位列分离**方案：`uk_circuit_no` 建在
    `(circuit_no, deleted_token)` 上，软删时只写 `deleted_token`，`circuit_no`
    **保持原值**。

    为什么不能"软删时把 circuit_no 改写成占位值"（设计 v2.2 原方案，已废弃）：
    `circuit_no` 是 String(64)，占位值最长 `64 + 20 + 9 = 93` 字符必然溢出，
    严格模式 ERROR 1406（根本删不掉）、非严格模式静默截断并与真实电路号撞键；
    且电路号是运营商给的外部自由文本，改写后归档无法按原号追溯。
    """

    __tablename__ = "circuits"
    __soft_delete__ = True
    __table_args__ = (
        UniqueConstraint("circuit_no", "deleted_token", name="uk_circuit_no"),
        Index("idx_circuit_status", "status"),
        Index("idx_circuit_end_date", "end_date"),
        Index("idx_circuit_carrier", "carrier_id"),
        Index("idx_circuit_customer", "customer_id"),
        Index("idx_circuit_billing_mode", "billing_mode"),
        Index("idx_circuit_a_dev", "a_end_device_id"),
        Index("idx_circuit_z_dev", "z_end_device_id"),
        {"comment": "线路资产表"},
    )

    circuit_no = db.Column(
        db.String(64), nullable=False, comment="运营商电路号/业务号（报障唯一凭据）"
    )
    deleted_token = db.Column(
        db.String(64), nullable=False, default="", server_default="",
        comment="软删占位标记（活跃行为空串；与 circuit_no 组成复合唯一键）",
    )
    name = db.Column(db.String(100), nullable=True, comment="人读名称，如'北京-上海 10G 主用'")
    carrier_id = db.Column(
        db.BigInteger, db.ForeignKey("carriers.id", ondelete="RESTRICT"),
        nullable=True, comment="运营商ID FK→carriers（RESTRICT）",
    )
    customer_id = db.Column(
        db.BigInteger, db.ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True, comment="归属客户ID FK→customers（RESTRICT）",
    )

    bandwidth_mbps = db.Column(db.Integer, nullable=True, comment="端口带宽（Mbps，绝对值为唯一真源）")
    bandwidth_step = db.Column(
        db.SmallInteger, nullable=False, default=BANDWIDTH_STEP_SI,
        server_default=str(BANDWIDTH_STEP_SI),
        comment="进位步进：1000(SI) / 1024(IEC)，仅影响展示换算",
    )

    billing_mode = db.Column(
        db.String(20), nullable=False, default=BillingMode.FLAT.value,
        server_default=BillingMode.FLAT.value,
        comment="计费模式：flat / commit_95 / commit_peak / commit_avg / per_gb",
    )
    committed_mbps = db.Column(db.Integer, nullable=True, comment="保底带宽（Mbps）；买断模式为 NULL")
    monthly_fee = db.Column(
        db.Numeric(12, 2), nullable=True, comment="保底月租（元），不含超量费"
    )
    overage_unit_price = db.Column(
        db.Numeric(12, 4), nullable=True, comment="超量单价（元/Mbps/月），commit_* 必填"
    )
    traffic_unit_price = db.Column(
        db.Numeric(12, 4), nullable=True, comment="流量单价（元/GB），per_gb 必填"
    )
    currency = db.Column(
        db.String(3), nullable=False, default="CNY", server_default="CNY", comment="币种"
    )

    access_type = db.Column(
        db.String(20), nullable=True,
        comment="接入方式：mstp / sdh / wdm / bare_fiber / ethernet / internet / other",
    )
    status = db.Column(
        db.String(20), nullable=False, default=CircuitStatus.PENDING.value,
        server_default=CircuitStatus.PENDING.value, comment="线路状态，见 CircuitStatus",
    )
    sla_level = db.Column(db.String(20), nullable=True, comment="SLA：5x8 / 7x24 / best_effort")
    start_date = db.Column(db.Date, nullable=True, comment="起租日")
    end_date = db.Column(db.Date, nullable=True, comment="到期日（驱动续租提醒）")
    contract_no = db.Column(db.String(100), nullable=True, comment="关联合同号")

    a_end_room_id = db.Column(db.Integer, nullable=True, comment="A端机房ID（软引用→rooms.id）")
    z_end_room_id = db.Column(db.Integer, nullable=True, comment="Z端机房ID（软引用→rooms.id）")
    a_end_device_id = db.Column(db.BigInteger, nullable=True, comment="A端设备ID（软引用→devices.id）")
    z_end_device_id = db.Column(db.BigInteger, nullable=True, comment="Z端设备ID（软引用→devices.id）")
    a_end_port_id = db.Column(db.BigInteger, nullable=True, comment="A端端口ID（软引用→network_ports.id）")
    z_end_port_id = db.Column(db.BigInteger, nullable=True, comment="Z端端口ID（软引用→network_ports.id）")
    a_end_desc = db.Column(db.String(200), nullable=True, comment="A端未纳管时的物理位置描述")
    z_end_desc = db.Column(db.String(200), nullable=True, comment="Z端未纳管时的物理位置描述")
    notes = db.Column(MEDIUMTEXT, nullable=True, comment="备注")

    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间")

    def __repr__(self) -> str:
        return (
            f"<Circuit(id={self.id}, no='{self.circuit_no}', "
            f"status='{self.status}', bw={self.bandwidth_mbps})>"
        )


class CircuitSegment(BaseModel):
    """线路分段。

    线路的端到端路径由若干分段组成。`connection_id` **允许为空**——真实链路里
    常存在未纳管跳接点（运营商机房、光转接架），强制全纳管会让功能不可用，
    故用 `hop_desc` 文本兜底。

    **不启用软删除**：它是线路的组成部分，无独立生命周期（设计文档 §3.3）。
    线路软删时由服务层在同一事务内物理删除其全部分段——不能依赖
    `ON DELETE CASCADE`，因为软删只 UPDATE deleted_at，父行从未真正 DELETE。
    """

    __tablename__ = "circuit_segments"
    __table_args__ = (
        UniqueConstraint("circuit_id", "seq", name="uk_segment_circuit_seq"),
        Index("idx_segment_connection", "connection_id"),
        Index("idx_segment_device", "device_id"),
        {"comment": "线路分段表"},
    )

    circuit_id = db.Column(
        db.BigInteger, db.ForeignKey("circuits.id", ondelete="CASCADE"),
        nullable=False, comment="所属线路ID FK→circuits",
    )
    seq = db.Column(db.SmallInteger, nullable=False, comment="分段序号（从 1 起）")
    connection_id = db.Column(
        db.BigInteger, db.ForeignKey("network_connections.id", ondelete="SET NULL"),
        nullable=True, comment="绑定的端口级连接ID FK→network_connections（反查锚点）",
    )
    connection_id_lost = db.Column(
        TINYINT(), nullable=False, default=0, server_default="0",
        comment="锚点是否已失效（1=原连接已删除；0=正常或从未纳管）",
    )
    device_id = db.Column(db.BigInteger, nullable=True, comment="跳接设备ID（软引用→devices.id）")
    port_id = db.Column(db.BigInteger, nullable=True, comment="跳接端口ID（软引用→network_ports.id）")
    hop_desc = db.Column(
        db.String(200), nullable=True, comment="未纳管跳接点描述（如'XX 运营商机房光转接'）"
    )
    notes = db.Column(db.String(500), nullable=True, comment="备注")

    def __repr__(self) -> str:
        return (
            f"<CircuitSegment(id={self.id}, circuit_id={self.circuit_id}, "
            f"seq={self.seq}, conn={self.connection_id}, lost={self.connection_id_lost})>"
        )
