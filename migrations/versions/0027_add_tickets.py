# -*- coding: utf-8 -*-
"""工单内核建表：tickets + ticket_ci_link + 两张插件绑定表（F1 / Task 1 Step B）


``ticket_external_bindings`` 与 ``user_external_bindings`` 是**插座的配套**，
不是可选优化：没有它们，外部平台的工单标识只能塞进主表（或 ``ext_json``），
内核随即被平台字段污染，且"这张单在钉钉那边什么状态"变成全表扫 JSON 的
不可对账问题。等接第一个真实平台再补，等于先把错误形状跑一段时间。

``ticket_ci_link`` 同理：裁决 A1 的多 CI 关联形态（device + room）是六个存量
场景里 S3（批量上架，room 级）与 S5（机房巡检）的**唯一落点**。主表单列
``device_id`` 承载不了它们。


**纯增量 DDL**（``CREATE TABLE``），不读不改任何既有数据，无不可逆风险。
仍保持幂等：表已存在则跳过该表（重复执行安全，兼容手工建过表的环境）。


```sql
DROP TABLE IF EXISTS user_external_bindings;
DROP TABLE IF EXISTS ticket_external_bindings;
DROP TABLE IF EXISTS ticket_ci_link;
DROP TABLE IF EXISTS tickets;
```

删表会丢掉全部工单数据 —— **Task 2 存量迁移（P1 双写）之前**这是安全的，
因为此时还没有任何业务写入；一旦进入 P1，只能按 Task 2 的回滚判据执行
（关 flag + 删 legacy 行），不可直接删表。


与 0022 线路端点是同一道题：``tests/test_force_delete_manifest_covers_fk.py``
要求"任何指向 devices/cabinets/rooms 的外键必须登记进
``room_service._FORCE_DELETE_*_SCOPED``"，而该清单的语义是**物理 DELETE 子表行**
——登记 ``tickets.device_id`` 等于宣布"强删设备时把工单一并删掉"，与工单是
业务留痕的定性相反。故此处不建外键，参照完整性由应用层校验承担（同 0022 端点
口径；``device_id`` 本身也只是 CI 缓存列，权威在 ``ticket_ci_link``）。


0021 迁移的教训：枚举值不够时 MySQL 严格模式直接 "Data truncated"，被 except
吞成"备份失败"，导致 AI 修复从未真正备份过且无人察觉。工单状态机会演进
（今天是 9 态），而 MySQL 8.0 只在"末尾追加且不改变存储字节数"时支持
INPLACE —— 中间插入会退化成 COPY + 锁表。状态合法性由 ``kernel_status``
的状态机保证，不由 DB 约束承担。
"""

import logging

logger = logging.getLogger(__name__)

_MDL_WAIT_TIMEOUT_SECONDS = 300

_DDL_TICKETS = """
CREATE TABLE `tickets` (
  `id`                       BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID（内部，不对外暴露）',
  `ticket_no`                VARCHAR(32)  NOT NULL           COMMENT '对外编号（类型前缀+日期+随机后缀）',
  `source`                   VARCHAR(20)  NOT NULL DEFAULT 'web' COMMENT '来源：web / alert_auto / api / legacy_import',
  `legacy_source`            VARCHAR(32)  DEFAULT NULL       COMMENT '存量来源表标识（迁移幂等键之一）',
  `legacy_id`                BIGINT       DEFAULT NULL       COMMENT '存量原记录ID（迁移幂等键之一）',
  `ticket_type`              VARCHAR(20)  NOT NULL           COMMENT '类型：incident / change / service_request / task',
  `ticket_subtype`           VARCHAR(20)  DEFAULT NULL       COMMENT '子类型：normal / standard / emergency',
  `title`                    VARCHAR(200) NOT NULL           COMMENT '标题',
  `description`              MEDIUMTEXT                      COMMENT '描述',
  `priority`                 VARCHAR(4)   NOT NULL DEFAULT 'P3' COMMENT '优先级：P1~P4',
  `urgency`                  VARCHAR(16)  DEFAULT NULL       COMMENT '紧急度',
  `impact`                   VARCHAR(16)  DEFAULT NULL       COMMENT '影响面',
  `status`                   VARCHAR(20)  NOT NULL DEFAULT 'draft' COMMENT '状态（9 态，取值域见 kernel_status.TicketStatus）',
  `apply_status`             VARCHAR(16)  DEFAULT NULL       COMMENT '下发状态：pending / running / success / failed',
  `applied_at`               DATETIME     DEFAULT NULL       COMMENT '下发完成时间',
  `apply_error`              TEXT                            COMMENT '下发错误信息',
  `change_backup_id`         BIGINT       DEFAULT NULL       COMMENT '变更基准备份ID FK→device_config_backups',
  `change_payload_json`      JSON                            COMMENT '变更指令载荷',
  `requester_id`             BIGINT       NOT NULL           COMMENT '申请人 FK→users',
  `assignee_id`              BIGINT       DEFAULT NULL       COMMENT '处理人 FK→users',
  `assigned_group`           VARCHAR(64)  DEFAULT NULL       COMMENT '处理组',
  `approver_id`              BIGINT       DEFAULT NULL       COMMENT '审批人 FK→users',
  `device_id`                BIGINT       DEFAULT NULL       COMMENT '设备ID（CI 缓存列，非权威，非外键）',
  `source_incident_id`       BIGINT       DEFAULT NULL       COMMENT '来源告警事件ID（弱引用，不建外键）',
  `source_alert_id`          BIGINT       DEFAULT NULL       COMMENT '来源告警ID（弱引用，不建外键）',
  `ai_diagnosis_session_id`  BIGINT       DEFAULT NULL       COMMENT 'AI诊断会话ID（弱引用，不建外键）',
  `ai_diagnosis_summary`     TEXT                            COMMENT 'AI诊断结论摘要',
  `sla_policy_id`            BIGINT       DEFAULT NULL       COMMENT 'SLA策略ID（弱引用）',
  `due_response_at`          DATETIME     DEFAULT NULL       COMMENT '响应截止时间（当前生效时钟的冗余）',
  `due_resolution_at`        DATETIME     DEFAULT NULL       COMMENT '解决截止时间（当前生效时钟的冗余）',
  `first_responded_at`       DATETIME     DEFAULT NULL       COMMENT '首次响应时间',
  `resolved_at`              DATETIME     DEFAULT NULL       COMMENT '解决时间（不是状态）',
  `closed_at`                DATETIME     DEFAULT NULL       COMMENT '关闭时间（不是状态）',
  `sla_paused_at`            DATETIME     DEFAULT NULL       COMMENT 'SLA挂起起始时间',
  `sla_paused_seconds`       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'SLA累计挂起秒数',
  `created_at`               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ticket_no` (`ticket_no`),
  UNIQUE KEY `uk_legacy` (`legacy_source`, `legacy_id`),
  KEY `idx_tk_assignee_status` (`assignee_id`, `status`, `created_at`),
  KEY `idx_tk_status_type` (`status`, `ticket_type`, `created_at`),
  KEY `idx_tk_requester` (`requester_id`, `created_at`),
  KEY `idx_tk_device` (`device_id`, `status`, `created_at`),
  KEY `idx_tk_status_due` (`status`, `due_resolution_at`),
  KEY `idx_tk_incident` (`source_incident_id`),
  KEY `idx_tk_source_created` (`source`, `created_at`),
  CONSTRAINT `fk_tk_requester` FOREIGN KEY (`requester_id`) REFERENCES `users` (`id`),
  CONSTRAINT `fk_tk_assignee`  FOREIGN KEY (`assignee_id`)  REFERENCES `users` (`id`),
  CONSTRAINT `fk_tk_approver`  FOREIGN KEY (`approver_id`)  REFERENCES `users` (`id`),
  CONSTRAINT `fk_tk_backup`    FOREIGN KEY (`change_backup_id`) REFERENCES `device_config_backups` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工单主表'
"""

_DDL_TICKET_CI_LINK = """
CREATE TABLE `ticket_ci_link` (
  `id`         BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `ticket_id`  BIGINT      NOT NULL                COMMENT '工单ID FK→tickets ON DELETE CASCADE',
  `ci_type`    VARCHAR(16) NOT NULL                COMMENT 'CI类型：MVP device/room；预留 rack/vlan/subnet/link/platform',
  `ci_id`      BIGINT      NOT NULL                COMMENT 'CI主键（跨域，不建外键）',
  `role`       VARCHAR(16) NOT NULL DEFAULT 'primary' COMMENT 'primary=主CI / related=关联CI',
  `created_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ticket_ci` (`ticket_id`, `ci_type`, `ci_id`),
  KEY `idx_ci_reverse` (`ci_type`, `ci_id`, `role`),
  CONSTRAINT `fk_ci_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工单-配置项关联'
"""

_DDL_TICKET_EXTERNAL_BINDINGS = """
CREATE TABLE `ticket_external_bindings` (
  `id`                   BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `ticket_id`            BIGINT       NOT NULL                COMMENT '工单ID FK→tickets ON DELETE CASCADE',
  `plugin_code`          VARCHAR(32)  NOT NULL                COMMENT '插件代号（与 TicketPlugin.code 同源）',
  `external_id`          VARCHAR(128) NOT NULL                COMMENT '外部平台工单ID',
  `external_status_raw`  VARCHAR(64)  DEFAULT NULL            COMMENT '外部原始状态（不翻译，供对账）',
  `last_synced_at`       DATETIME     DEFAULT NULL            COMMENT '最近一次同步时间',
  `sync_direction`       VARCHAR(16)  NOT NULL DEFAULT 'outbound' COMMENT '同步方向：outbound / inbound / bidirectional',
  `created_at`           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ticket_external` (`plugin_code`, `external_id`),
  KEY `idx_teb_ticket` (`ticket_id`),
  CONSTRAINT `fk_teb_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工单-外部平台绑定'
"""

_DDL_USER_EXTERNAL_BINDINGS = """
CREATE TABLE `user_external_bindings` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id`     BIGINT       NOT NULL                COMMENT '内部用户ID FK→users ON DELETE CASCADE',
  `plugin_code` VARCHAR(32)  NOT NULL                COMMENT '插件代号',
  `external_id` VARCHAR(128) NOT NULL                COMMENT '外部平台用户ID',
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_external` (`plugin_code`, `external_id`),
  KEY `idx_ueb_user` (`user_id`),
  CONSTRAINT `fk_ueb_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-外部身份绑定'
"""

_TABLES = (
    ("tickets", _DDL_TICKETS),
    ("ticket_ci_link", _DDL_TICKET_CI_LINK),
    ("ticket_external_bindings", _DDL_TICKET_EXTERNAL_BINDINGS),
    ("user_external_bindings", _DDL_USER_EXTERNAL_BINDINGS),
)


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW TABLES LIKE '{table}'")
        return cur.fetchone() is not None
    finally:
        cur.close()


def apply(conn) -> None:
    """建四张表（幂等；已存在则跳过该表）。"""
    created = []
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        for table, ddl in _TABLES:
            if _table_exists(conn, table):
                logger.info("跳过：表 %s 已存在", table)
                continue
            cur.execute(ddl)
            created.append(table)
            logger.info("已建表 %s", table)
    finally:
        cur.close()

    if created:
        logger.info("F1 工单内核建表完成：%s", ", ".join(created))
    else:
        logger.info("F1 工单内核：四张表均已存在，无需建表")
