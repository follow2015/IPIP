"""工单内核模型（F1）：主表 + CI 关联 + 插件绑定的两张配套表。

权威字段表见 ``docs/design/IPIP-通用工单系统设计文档.md`` §3.2–§3.4（v1.3），
绑定表见 ``docs/design/IPIP-通用工单系统-插件化架构设计.md`` §5。

**三处刻意的形状，改之前先看理由**：

1. ``status`` 用 ``VARCHAR`` 而不是 ``db.Enum``。
   0021 迁移的教训：枚举值不够时 MySQL 严格模式直接 "Data truncated"，
   被 except 吞成"备份失败"，导致 AI 修复**从未真正备份过**且无人察觉。
   工单状态机会演进（9 态今天够用，明天未必），而 MySQL 8.0 只在"末尾追加
   且不改变存储字节数"时才支持 INPLACE —— 中间插入会退化成 COPY + 锁表。
   状态合法性由 ``kernel_status`` 的状态机保证（那才是唯一该管它的地方），
   不由 DB 约束承担。同一理由适用于 ``ticket_type`` / ``priority`` 等。

2. **主表零平台字段**。企微 / 钉钉 / 第三方 ITSM 的标识一律落
   ``ticket_external_bindings``，主表不存任何平台私有字段，也不建 ``ext_json``
   大字段 —— 存了内核读不懂的东西，既不可索引也不可对账。

3. **弱引用不建外键**：``source_incident_id`` / ``source_alert_id`` /
   ``ai_diagnosis_session_id`` 指向的表生命周期与工单不同步（告警事件可先于
   工单关闭，也可在工单关闭后继续聚合）。建外键会把"事件被删除"变成
   "工单写失败"。悬空 ID 由详情接口容错成"关联事件已清理"。

4. ``device_id`` **也不建外键**，尽管它指向的表（``devices``）就在隔壁。
   两条理由，任意一条单独都成立：
   (a) 它是 CI 缓存列（权威在 ``ticket_ci_link``），对工单而言只是"位置标注"；
   (b) 本仓 ``room_service`` 的强删语义是**物理 DELETE 子表行**，而
       ``tests/test_force_delete_manifest_covers_fk.py`` 要求"任何指向
       devices/cabinets/rooms 的外键必须登记进 ``_FORCE_DELETE_*_SCOPED``"
       —— 登记了就等于宣布"强删设备时把工单一起删掉"，这与工单是业务留痕
       的定性相反。与 0022 线路端点是同一道题的同一解法：端点对线路只是
       "位置标注"，0022 因此不建外键、改应用层校验（见 0022 迁移 docstring
       「端点与跳接点是软引用，不建外键」）。此处同口径，不另立标准。

取值域的单一真源在 ``app/services/ticket/kernel_status.py``（``TicketStatus`` /
``TicketType``）。本模块**不** import 它：模型层依赖服务层是倒置方向，
而状态机必须保持零 ORM 依赖才能被单测直接实例化。两边的一致性由
``tests/services/ticket/test_ticket_model_contract.py`` 断言。
"""

from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func

from app.models.base import BaseModel, MEDIUMTEXT
from extensions import db

_STATUS_LEN = 20
_TYPE_LEN = 20


class Ticket(db.Model):
    """工单主表（37 列，v1.3 §3.2）。

    不继承 ``BaseModel``：主键与时间戳口径需自定义（``BIGINT`` + MySQL
    ``ON UPDATE CURRENT_TIMESTAMP``），与 ``DeviceConfigChange`` 同款。
    """

    __tablename__ = "tickets"
    __table_args__ = (
        db.Index("uk_ticket_no", "ticket_no", unique=True),
        db.Index("uk_legacy", "legacy_source", "legacy_id", unique=True),
        db.Index("idx_tk_assignee_status", "assignee_id", "status", "created_at"),
        db.Index("idx_tk_status_type", "status", "ticket_type", "created_at"),
        db.Index("idx_tk_requester", "requester_id", "created_at"),
        db.Index("idx_tk_device", "device_id", "status", "created_at"),
        db.Index("idx_tk_status_due", "status", "due_resolution_at"),
        db.Index("idx_tk_incident", "source_incident_id"),
        db.Index("idx_tk_source_created", "source", "created_at"),
        {"comment": "工单主表"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID（内部，不对外暴露）")

    ticket_no = db.Column(db.String(32), nullable=False, comment="对外编号（类型前缀+日期+随机后缀，v1.3 §3.5）")
    source = db.Column(
        db.String(20),
        nullable=False,
        default="web",
        comment="来源：web / alert_auto / api / legacy_import",
    )
    legacy_source = db.Column(db.String(32), comment="存量来源表标识（迁移幂等键之一）")
    legacy_id = db.Column(db.BigInteger, comment="存量原记录ID（迁移幂等键之一）")

    ticket_type = db.Column(
        db.String(_TYPE_LEN),
        nullable=False,
        comment="类型：incident / change / service_request / task",
    )
    ticket_subtype = db.Column(
        db.String(_TYPE_LEN),
        comment="子类型：normal / standard / emergency",
    )

    title = db.Column(db.String(200), nullable=False, comment="标题")
    description = db.Column(MEDIUMTEXT, comment="描述")

    priority = db.Column(db.String(4), nullable=False, default="P3", comment="优先级：P1~P4")
    urgency = db.Column(db.String(16), comment="紧急度")
    impact = db.Column(db.String(16), comment="影响面")

    status = db.Column(
        db.String(_STATUS_LEN),
        nullable=False,
        default="draft",
        comment="状态（9 态，取值域见 kernel_status.TicketStatus）",
    )
    apply_status = db.Column(db.String(16), comment="下发状态：pending / running / success / failed")
    applied_at = db.Column(db.DateTime, comment="下发完成时间")
    apply_error = db.Column(db.Text, comment="下发错误信息")
    change_backup_id = db.Column(
        db.BigInteger,
        db.ForeignKey("device_config_backups.id"),
        comment="变更基准备份ID FK→device_config_backups",
    )
    change_payload_json = db.Column(db.JSON, comment="变更指令载荷")

    requester_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False, comment="申请人 FK→users")
    assignee_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), comment="处理人 FK→users")
    assigned_group = db.Column(db.String(64), comment="处理组")
    approver_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), comment="审批人 FK→users")

    device_id = db.Column(db.BigInteger, comment="设备ID（CI 缓存列，非权威，非外键）")
    source_incident_id = db.Column(db.BigInteger, comment="来源告警事件ID（弱引用 monitor_incident）")
    source_alert_id = db.Column(db.BigInteger, comment="来源告警ID（弱引用 monitor_alert_outbox）")
    ai_diagnosis_session_id = db.Column(db.BigInteger, comment="AI诊断会话ID（弱引用）")
    ai_diagnosis_summary = db.Column(db.Text, comment="AI诊断结论摘要")

    sla_policy_id = db.Column(db.BigInteger, comment="SLA策略ID（弱引用 ticket_sla_policies）")
    due_response_at = db.Column(db.DateTime, comment="响应截止时间（当前生效时钟的冗余）")
    due_resolution_at = db.Column(db.DateTime, comment="解决截止时间（当前生效时钟的冗余）")
    first_responded_at = db.Column(db.DateTime, comment="首次响应 time")
    resolved_at = db.Column(db.DateTime, comment="解决时间（**不是状态**）")
    closed_at = db.Column(db.DateTime, comment="关闭时间（**不是状态**）")
    sla_paused_at = db.Column(db.DateTime, comment="SLA挂起起")
    sla_paused_seconds = db.Column(
        INTEGER(unsigned=True),
        nullable=False,
        default=0,
        comment="SLA累计挂起秒数（挂起/恢复时累加）",
    )

    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def to_dict(self, exclude=None, include_relations=False):
        """序列化。

        [WARN] 不产出 ``status_display`` 之类给人读的中文标签：那是前端 i18n 的事。
        后端返回**取值**，翻译由前端按 locale 决定 —— 否则同一份接口在
        中英文环境下只能给一种，且后端改文案要发版。
        """
        return {
            "id": self.id,
            "ticket_no": self.ticket_no,
            "source": self.source,
            "legacy_source": self.legacy_source,
            "legacy_id": self.legacy_id,
            "ticket_type": self.ticket_type,
            "ticket_subtype": self.ticket_subtype,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "urgency": self.urgency,
            "impact": self.impact,
            "status": self.status,
            "apply_status": self.apply_status,
            "applied_at": BaseModel._serialize_value(self.applied_at),
            "apply_error": self.apply_error,
            "change_backup_id": self.change_backup_id,
            "requester_id": self.requester_id,
            "assignee_id": self.assignee_id,
            "assigned_group": self.assigned_group,
            "approver_id": self.approver_id,
            "device_id": self.device_id,
            "source_incident_id": self.source_incident_id,
            "source_alert_id": self.source_alert_id,
            "ai_diagnosis_session_id": self.ai_diagnosis_session_id,
            "ai_diagnosis_summary": self.ai_diagnosis_summary,
            "sla_policy_id": self.sla_policy_id,
            "due_response_at": BaseModel._serialize_value(self.due_response_at),
            "due_resolution_at": BaseModel._serialize_value(self.due_resolution_at),
            "first_responded_at": BaseModel._serialize_value(self.first_responded_at),
            "resolved_at": BaseModel._serialize_value(self.resolved_at),
            "closed_at": BaseModel._serialize_value(self.closed_at),
            "sla_paused_at": BaseModel._serialize_value(self.sla_paused_at),
            "sla_paused_seconds": self.sla_paused_seconds,
            "created_at": BaseModel._serialize_value(self.created_at),
            "updated_at": BaseModel._serialize_value(self.updated_at),
        }


class TicketCiLink(db.Model):
    """工单 ↔ 配置项关联（v1.3 §0.3 裁决 A1）。

    MVP 只实现 ``device`` / ``room`` 两种 ``ci_type``：六个存量场景里
    S1/S2/S6 落在 device、S3/S5 落在 room、S4 允许为空；``rack`` / ``vlan`` /
    ``subnet`` / ``link`` / ``platform`` 当前**无人填**，做出来是空功能。
    """

    __tablename__ = "ticket_ci_link"
    __table_args__ = (
        db.Index("uk_ticket_ci", "ticket_id", "ci_type", "ci_id", unique=True),
        db.Index("idx_ci_reverse", "ci_type", "ci_id", "role"),
        {"comment": "工单-配置项关联"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        comment="工单ID FK→tickets ON DELETE CASCADE",
    )
    ci_type = db.Column(
        db.String(16),
        nullable=False,
        comment="CI类型：MVP device/room；预留 rack/vlan/subnet/link/platform",
    )
    ci_id = db.Column(db.BigInteger, nullable=False, comment="CI主键（跨域，不建外键）")
    role = db.Column(db.String(16), nullable=False, default="primary", comment="primary=主CI / related=关联CI")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def to_dict(self, exclude=None, include_relations=False):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "ci_type": self.ci_type,
            "ci_id": self.ci_id,
            "role": self.role,
            "created_at": BaseModel._serialize_value(self.created_at),
        }


class TicketExternalBinding(db.Model):
    """工单 ↔ 外部平台绑定（插件插座的配套表，架构 §5）。

    它是**去重与对账的唯一依据**："这张单在钉钉那边现在什么状态"只能查这里。
    刻意不建 ``ext_json``：一个 JSON 大字段存各平台私有参数会导致不可索引、
    不可对账，且与"内核不认识外部字段"自相矛盾 —— 内核存了它读不懂的东西，
    还无法校验。扩展字段按插件各自解析。
    """

    __tablename__ = "ticket_external_bindings"
    __table_args__ = (
        db.Index("uk_ticket_external", "plugin_code", "external_id", unique=True),
        db.Index("idx_teb_ticket", "ticket_id"),
        {"comment": "工单-外部平台绑定"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        comment="工单ID FK→tickets ON DELETE CASCADE",
    )
    plugin_code = db.Column(db.String(32), nullable=False, comment="插件代号（与 TicketPlugin.code 同源）")
    external_id = db.Column(db.String(128), nullable=False, comment="外部平台工单ID")
    external_status_raw = db.Column(db.String(64), comment="外部原始状态（不翻译，供对账）")
    last_synced_at = db.Column(db.DateTime, comment="最近一次同步时间")
    sync_direction = db.Column(
        db.String(16),
        nullable=False,
        default="outbound",
        comment="同步方向：outbound / inbound / bidirectional",
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def to_dict(self, exclude=None, include_relations=False):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "plugin_code": self.plugin_code,
            "external_id": self.external_id,
            "external_status_raw": self.external_status_raw,
            "last_synced_at": BaseModel._serialize_value(self.last_synced_at),
            "sync_direction": self.sync_direction,
            "created_at": BaseModel._serialize_value(self.created_at),
            "updated_at": BaseModel._serialize_value(self.updated_at),
        }


class UserExternalBinding(db.Model):
    """外部身份 ↔ 内部 ``user_id``（插件插座的配套表，架构 §5）。

    业务代码永远只读写内部 ``user_id`` —— 外部身份只在插件边界被解析一次。
    否则"同一个人在企微和钉钉各有一个 ID"会渗进内核，权限判定出现两套口径。
    """

    __tablename__ = "user_external_bindings"
    __table_args__ = (
        db.Index("uk_user_external", "plugin_code", "external_id", unique=True),
        db.Index("idx_ueb_user", "user_id"),
        {"comment": "用户-外部身份绑定"},
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="内部用户ID FK→users ON DELETE CASCADE",
    )
    plugin_code = db.Column(db.String(32), nullable=False, comment="插件代号")
    external_id = db.Column(db.String(128), nullable=False, comment="外部平台用户ID")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def to_dict(self, exclude=None, include_relations=False):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plugin_code": self.plugin_code,
            "external_id": self.external_id,
            "created_at": BaseModel._serialize_value(self.created_at),
            "updated_at": BaseModel._serialize_value(self.updated_at),
        }
