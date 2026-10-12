# -*- coding: utf-8 -*-
"""安全中心一期：security_policies（策略 KV）+ security_findings（巡检发现项）

设计依据：
- `docs/design/2026-10-10-安全中心一期-检测与强制-设计与实施方案.md` §4.1
- `docs/design/统一安全中心-设计文档.md` §4（策略模型）/ §7（发现项）


`security_policies` 是"管理员改过的项"的稀疏覆盖层：读路径是 进程内 5s 缓存 →
Redis Hash → 本表 → **代码内注册表默认值**。因此新增一个策略项**不需要数据迁移**，
且"默认值 = 现状"这条纪律由注册表（`app/services/security/policy_registry.py`）
与它的测试保证 —— 建表阶段不做任何默认值写入，避免"迁移里写死的默认值"
与"代码里的默认值"两套事实源。


`security_findings` 的唯一键是 `(rule_id, subject_type, subject_id)`，巡检引擎按
该键做 upsert（同 rule 同主体只留一行，重复命中只刷 `last_seen`）。

MySQL/InnoDB 的唯一索引中 **`NULL` 不参与唯一性判定**（NULL ≠ NULL，可多行共存）。
若 `subject_id` 可空：`system.audit_retention` 这类**没有具体对象**的规则每轮扫描都会
新插一行 —— 表随扫描轮数无界增长、概览的"X/Y 项合规"计数失真，**且全程不报错**。
故系统级 finding 用哨兵值 `0`，列声明 `NOT NULL DEFAULT 0`。

同理，`status` 用 `VARCHAR` 而非 Enum（沿用工单模型对 0021 的教训：Enum 增删值要
改 DDL），一期取值仅 `open` / `resolved`；`excepted` 归后续"例外机制"阶段引入。


**纯增量 DDL**（两张新表，`CREATE TABLE IF NOT EXISTS`），不读不改任何既有数据；
幂等，无不可逆风险。回滚只是丢安全中心的采集结果与策略覆盖，不影响业务表。


```sql
DROP TABLE IF EXISTS `security_findings`;
DROP TABLE IF EXISTS `security_policies`;
```
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DDL_POLICIES = """
CREATE TABLE IF NOT EXISTS `security_policies` (
  `policy_key`  VARCHAR(64)  NOT NULL COMMENT '策略键，如 snmp.allowed_versions',
  `value_json`  JSON         NOT NULL COMMENT '策略值（JSON，按注册表类型解析）',
  `version`     INT          NOT NULL DEFAULT 1 COMMENT '乐观锁版本',
  `updated_by`  BIGINT       NULL COMMENT '操作人 users.id（逻辑关联，无 FK）',
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`policy_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安全策略（只存管理员改过的项）'
"""

_DDL_FINDINGS = """
CREATE TABLE IF NOT EXISTS `security_findings` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `rule_id`      VARCHAR(64)  NOT NULL COMMENT '规则ID，如 snmp.v2c_in_use',
  `severity`     VARCHAR(10)  NOT NULL COMMENT 'critical/high/medium/low',
  `subject_type` VARCHAR(32)  NOT NULL COMMENT 'credential/user/system',
  `subject_id`   BIGINT       NOT NULL DEFAULT 0 COMMENT '主体ID；系统级用哨兵 0，禁止 NULL（NULL 不参与唯一性判定）',
  `status`       VARCHAR(16)  NOT NULL DEFAULT 'open' COMMENT 'open/resolved（excepted 归后续例外机制）',
  `detail`       JSON         NULL COMMENT '结论摘要，禁含口令/community 明文',
  `first_seen`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次发现',
  `last_seen`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近一次仍违规',
  `resolved_at`  DATETIME     NULL COMMENT '消除时间',
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rule_subject` (`rule_id`, `subject_type`, `subject_id`),
  KEY `idx_finding_status_sev` (`status`, `severity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安全巡检发现项'
"""

_TABLES: tuple[tuple[str, str], ...] = (
    ("security_policies", _DDL_POLICIES),
    ("security_findings", _DDL_FINDINGS),
)


def apply(conn) -> None:
    """建两张表（幂等：IF NOT EXISTS）。"""
    cur = conn.cursor()
    try:
        for table, ddl in _TABLES:
            cur.execute(ddl)
            logger.info("已确保表存在：%s", table)
    finally:
        cur.close()
    conn.commit()


def rollback(conn) -> None:
    """删两张表（仅用于开发/回滚演练；丢掉巡检结果与策略覆盖）。"""
    cur = conn.cursor()
    try:
        for table in reversed([t for t, _ in _TABLES]):
            cur.execute(f"DROP TABLE IF EXISTS `{table}`")
            logger.info("已删除表：%s", table)
    finally:
        cur.close()
    conn.commit()
