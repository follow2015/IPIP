# -*- coding: utf-8 -*-
"""G1 线路管理：建 `carriers` / `circuits` / `circuit_segments` 三张表

设计文档：`docs/design/G1-线路管理-数据模型设计文档-20260928.md`（v2.4）

背景
----
线路此前在本仓**没有**任何数据承载：`carrier` / `isp_id` / `leased` / `sla_level`
全仓零命中，带宽只作为 `network_connections.bandwidth` 的一个标注字段存在。
而"这条链路归谁、花多少钱、什么时候到期"是运维的核心问题，无法用连接的属性表达。

**关键区分**：`network_connections` 描述"两个端口物理相连"（事实），
`circuits` 描述"一条有主的、花钱的、要管的服务"（资产）。二者不可互相推导，
本迁移**不回填** `network_connections.bandwidth` → `circuits.bandwidth_mbps`。

本迁移必须盯住的四条口径
------------------------
1. **DDL 与 ORM 必须同口径**（评审 B-10/B-11/B-12）：
   `tests/helpers/fk_targets.py:24-31` 已记录本仓存在 12 条
   "ORM `fk.ondelete` 与真库 `DELETE_RULE` 不一致"的漂移，0022 不得再添一条。
   故本文件每条外键都**显式写出 `ON DELETE`**，且与 `app/models/circuit.py` 一致。

2. **有符号 `INT`**（评审 A-8）：`bandwidth_mbps` / `committed_mbps` 的容量论证
   （上限 2147483647 Mbps ≈ 2.1 Pbps）**只在有符号 INT 下成立**。误写成
   `INT UNSIGNED` 或 `BIGINT` 会让该论证的前提失效，且看不出来。

3. **复合唯一键**（评审 B-3）：`circuit_no` / `name` 的唯一键建在
   `(业务列, deleted_token)` 上。软删只写 `deleted_token`、业务列保持原值，
   既释放业务号供复用，又保住"软删后按原号追溯"。**不要**改成单列唯一键。

4. **端点与跳接点是软引用，不建外键**（实施期决定，见 `app/models/circuit.py` 的说明）：
   本仓 `room_service._FORCE_DELETE_*_SCOPED` 的语义是**物理 DELETE 子表行**，
   而 `tests/test_force_delete_manifest_covers_fk.py` 要求"指向 devices/cabinets/rooms
   的外键必须在清单里" ⇒ 建外键就必须登记，登记了就会把**整条线路删掉**。
   端点对线路而言只是"位置标注"（未纳管时本就回退到文本描述），故改为普通列。
   参照完整性由应用层校验承担（创建/更新时校验 id 存在）。
   只保留 `carrier_id` / `customer_id` / `circuit_id` / `connection_id` 四条**归属与锚点**外键。

在线 DDL 纪律（与 0011/0016/0017/0018/0019/0020/0021 一致）
----------------------------------------------------------
- 先 `SET SESSION lock_wait_timeout = 300`，避免 MDL 等待雪崩；
- 三张表都是**新建空表**，无存量行，不存在 COPY 重写，天然在线；
- 外键随建表语句一并创建，避免二次 ALTER。

**幂等**：`SHOW TABLES LIKE` 已存在则跳过（整体跳过，不做逐列补齐——
一期三表结构由本迁移一次性定义）。

**无 downgrade**：本仓 0013–0021 全部只有 `apply(conn)`，`def downgrade` 零命中，
`app/__init__.py` 也未注册 `db-downgrade` 命令。回滚走手工 DDL，
见设计文档 §14.6。
"""
import logging

logger = logging.getLogger(__name__)

_MDL_WAIT_TIMEOUT_SECONDS = 300

_DDL_CARRIERS = """
CREATE TABLE `carriers` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` VARCHAR(100) NOT NULL COMMENT '运营商全称',
  `deleted_token` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '软删占位标记（活跃行为空串；与 name 组成复合唯一键）',
  `short_name` VARCHAR(50) DEFAULT NULL COMMENT '简称（列表/下拉展示用）',
  `carrier_type` VARCHAR(20) DEFAULT NULL COMMENT '类型：basic / isp / idc / agent',
  `status` VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT '状态：active / inactive',
  `contact_person` VARCHAR(100) DEFAULT NULL COMMENT '业务联系人',
  `contact_phone` VARCHAR(50) DEFAULT NULL COMMENT '联系电话',
  `hotline` VARCHAR(50) DEFAULT NULL COMMENT '7x24 报障热线',
  `email` VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
  `default_sla_level` VARCHAR(20) DEFAULT NULL COMMENT '默认 SLA，新建线路时预填',
  `qualification_no` VARCHAR(100) DEFAULT NULL COMMENT '资质/营业执照号',
  `notes` MEDIUMTEXT COMMENT '备注',
  `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_carrier_name` (`name`, `deleted_token`),
  KEY `idx_carrier_type` (`carrier_type`),
  KEY `idx_carrier_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运营商表'
"""

_DDL_CIRCUITS = """
CREATE TABLE `circuits` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `circuit_no` VARCHAR(64) NOT NULL COMMENT '运营商电路号/业务号（报障唯一凭据）',
  `deleted_token` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '软删占位标记（活跃行为空串；与 circuit_no 组成复合唯一键）',
  `name` VARCHAR(100) DEFAULT NULL COMMENT '人读名称',
  `carrier_id` BIGINT DEFAULT NULL COMMENT '运营商ID',
  `customer_id` BIGINT DEFAULT NULL COMMENT '归属客户ID',
  `bandwidth_mbps` INT DEFAULT NULL COMMENT '端口带宽（Mbps，绝对值为唯一真源）',
  `bandwidth_step` SMALLINT NOT NULL DEFAULT 1000 COMMENT '进位步进：1000(SI) / 1024(IEC)，仅影响展示换算',
  `billing_mode` VARCHAR(20) NOT NULL DEFAULT 'flat' COMMENT '计费模式：flat / commit_95 / commit_peak / commit_avg / per_gb',
  `committed_mbps` INT DEFAULT NULL COMMENT '保底带宽（Mbps）；买断模式为 NULL',
  `monthly_fee` DECIMAL(12,2) DEFAULT NULL COMMENT '保底月租（元），不含超量费',
  `overage_unit_price` DECIMAL(12,4) DEFAULT NULL COMMENT '超量单价（元/Mbps/月），commit_* 必填',
  `traffic_unit_price` DECIMAL(12,4) DEFAULT NULL COMMENT '流量单价（元/GB），per_gb 必填',
  `currency` VARCHAR(3) NOT NULL DEFAULT 'CNY' COMMENT '币种',
  `access_type` VARCHAR(20) DEFAULT NULL COMMENT '接入方式：mstp / sdh / wdm / bare_fiber / ethernet / internet / other',
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '线路状态：pending / active / fault / suspended / terminated',
  `sla_level` VARCHAR(20) DEFAULT NULL COMMENT 'SLA：5x8 / 7x24 / best_effort',
  `start_date` DATE DEFAULT NULL COMMENT '起租日',
  `end_date` DATE DEFAULT NULL COMMENT '到期日（驱动续租提醒）',
  `contract_no` VARCHAR(100) DEFAULT NULL COMMENT '关联合同号',
  `a_end_room_id` INT DEFAULT NULL COMMENT 'A端机房ID',
  `z_end_room_id` INT DEFAULT NULL COMMENT 'Z端机房ID',
  `a_end_device_id` BIGINT DEFAULT NULL COMMENT 'A端设备ID',
  `z_end_device_id` BIGINT DEFAULT NULL COMMENT 'Z端设备ID',
  `a_end_port_id` BIGINT DEFAULT NULL COMMENT 'A端端口ID',
  `z_end_port_id` BIGINT DEFAULT NULL COMMENT 'Z端端口ID',
  `a_end_desc` VARCHAR(200) DEFAULT NULL COMMENT 'A端未纳管时的物理位置描述',
  `z_end_desc` VARCHAR(200) DEFAULT NULL COMMENT 'Z端未纳管时的物理位置描述',
  `notes` MEDIUMTEXT COMMENT '备注',
  `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_circuit_no` (`circuit_no`, `deleted_token`),
  KEY `idx_circuit_status` (`status`),
  KEY `idx_circuit_end_date` (`end_date`),
  KEY `idx_circuit_carrier` (`carrier_id`),
  KEY `idx_circuit_customer` (`customer_id`),
  KEY `idx_circuit_billing_mode` (`billing_mode`),
  KEY `idx_circuit_a_dev` (`a_end_device_id`),
  KEY `idx_circuit_z_dev` (`z_end_device_id`),
  CONSTRAINT `fk_circuits_carrier` FOREIGN KEY (`carrier_id`) REFERENCES `carriers` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_circuits_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='线路资产表'
"""

_DDL_CIRCUIT_SEGMENTS = """
CREATE TABLE `circuit_segments` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `circuit_id` BIGINT NOT NULL COMMENT '所属线路ID',
  `seq` SMALLINT NOT NULL COMMENT '分段序号（从 1 起）',
  `connection_id` BIGINT DEFAULT NULL COMMENT '绑定的端口级连接ID（反查锚点）',
  `connection_id_lost` TINYINT NOT NULL DEFAULT 0 COMMENT '锚点是否已失效（1=原连接已删除；0=正常或从未纳管）',
  `device_id` BIGINT DEFAULT NULL COMMENT '跳接设备ID',
  `port_id` BIGINT DEFAULT NULL COMMENT '跳接端口ID',
  `hop_desc` VARCHAR(200) DEFAULT NULL COMMENT '未纳管跳接点描述',
  `notes` VARCHAR(500) DEFAULT NULL COMMENT '备注',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_segment_circuit_seq` (`circuit_id`, `seq`),
  KEY `idx_segment_connection` (`connection_id`),
  KEY `idx_segment_device` (`device_id`),
  CONSTRAINT `fk_segments_circuit` FOREIGN KEY (`circuit_id`) REFERENCES `circuits` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_segments_connection` FOREIGN KEY (`connection_id`) REFERENCES `network_connections` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='线路分段表'
"""

_TABLES = (
    ("carriers", _DDL_CARRIERS),
    ("circuits", _DDL_CIRCUITS),
    ("circuit_segments", _DDL_CIRCUIT_SEGMENTS),
)


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW TABLES LIKE '{table}'")
        return cur.fetchone() is not None
    finally:
        cur.close()


def apply(conn) -> None:
    """建三张表（幂等；已存在则整体跳过该表）"""
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
        logger.info("G1 线路管理建表完成：%s", ", ".join(created))
    else:
        logger.info("G1 线路管理：三张表均已存在，无需建表")
