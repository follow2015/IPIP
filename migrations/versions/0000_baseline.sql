-- ipip schema baseline（版本化迁移链起点，schema 演进见 NNNN_*.py）
-- source: 生产库（主机地址已脱敏，见内部 .env 配置，勿写入本文件）/ip_manager
-- generated: 2026-09-04T04:21:31Z by scripts/export_schema_dump.py（只读元数据导出）
-- 用途：仅全新安装导入；存量库升级使用 flask db-upgrade，勿重复导入本文件
-- updated: 2026-09-04 重生成：应用 0001_drop_redundant_indexes 效果（删除 14 个冗余索引），
--          快照现对应迁移链头 0001；覆盖范围见 0000_baseline.covers

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `ai_conversations`;
CREATE TABLE `ai_conversations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `scenario` varchar(50) NOT NULL COMMENT '场景: chat/alert/nlq/rag/inspection',
  `role` varchar(20) NOT NULL COMMENT 'user/assistant',
  `content` text NOT NULL COMMENT '消息内容',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_conv_user_scenario` (`user_id`,`scenario`),
  CONSTRAINT `fk_ai_conv_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI 对话历史';

DROP TABLE IF EXISTS `ai_diagnosis_sessions`;
CREATE TABLE `ai_diagnosis_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint DEFAULT NULL COMMENT '设备ID（诊断目标，设备删除时保留会话供回溯）',
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `skill_name` varchar(64) NOT NULL COMMENT 'agentic 技能名',
  `question` text NOT NULL COMMENT '用户原始问题',
  `rounds_json` longtext COMMENT '每轮工具调用摘要 JSON',
  `final_answer_json` longtext COMMENT '结构化诊断结论 JSON',
  `status` varchar(20) NOT NULL DEFAULT 'running' COMMENT 'running/completed/incomplete/failed',
  `token_cost` int DEFAULT NULL COMMENT '总 token 消耗',
  `duration_ms` int DEFAULT NULL COMMENT '总耗时毫秒',
  `remedial_executed` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否有 remedial 命令被实际执行',
  `rollback_failed` tinyint(1) NOT NULL DEFAULT '0' COMMENT '回滚是否失败',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_diag_device_user` (`device_id`,`user_id`),
  KEY `idx_ai_diag_skill_status` (`skill_name`,`status`),
  KEY `fk_ai_diag_user` (`user_id`),
  CONSTRAINT `fk_ai_diag_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ai_diag_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI 诊断会话持久化';

DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint DEFAULT NULL COMMENT '操作人 FK→users',
  `action` varchar(64) NOT NULL COMMENT '操作类型(如 device.create, ip.ban)',
  `resource` varchar(64) NOT NULL COMMENT '资源类型(如 device, ip, switch)',
  `resource_id` bigint DEFAULT NULL COMMENT '资源ID',
  `detail` json DEFAULT NULL COMMENT '操作详情',
  `ip_address` varchar(45) DEFAULT NULL COMMENT '客户端IP',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_user` (`user_id`),
  KEY `idx_audit_created_action` (`created_at` DESC,`action`),
  KEY `idx_audit_resource_time` (`resource`,`resource_id`,`created_at`),
  KEY `idx_functional_detail_module` ((cast(json_unquote(json_extract(`detail`,_utf8mb4'$.module')) as char(32) charset utf8mb4)))
) ENGINE=InnoDB AUTO_INCREMENT=424 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作审计日志';

DROP TABLE IF EXISTS `cabinets`;
CREATE TABLE `cabinets` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `cabinet_number` varchar(255) NOT NULL COMMENT '机柜编号',
  `room_id` int NOT NULL COMMENT '所属机房ID',
  `location` varchar(255) DEFAULT NULL COMMENT '具体位置',
  `row` int DEFAULT NULL COMMENT '行号（机房平面图纵坐标，从1开始）',
  `col` int DEFAULT NULL COMMENT '列号（机房平面图横坐标，从1开始）',
  `total_u` int NOT NULL COMMENT '总U位数',
  `used_u` int NOT NULL DEFAULT '0' COMMENT '已用U位数',
  `total_power` int DEFAULT NULL COMMENT '电力容量(W)',
  `used_power` int NOT NULL DEFAULT '0' COMMENT '已用功率(W)',
  `max_weight` float DEFAULT NULL COMMENT '最大承重(KG)',
  `status` int NOT NULL COMMENT '状态: 1-可用, 2-使用中, 3-维护中, 4-已预留',
  `customer_id` bigint DEFAULT NULL COMMENT '客户ID（整柜租赁）',
  `notes` mediumtext,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cabinet_room_number` (`room_id`,`cabinet_number`),
  KEY `idx_cabinet_deleted_room_status` (`room_id`,`status`),
  KEY `idx_cabinet_customer` (`customer_id`),
  CONSTRAINT `fk_cabinet_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_cabinet_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机柜信息表';

DROP TABLE IF EXISTS `component_templates`;
CREATE TABLE `component_templates` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `category` varchar(20) NOT NULL COMMENT '配件类别: cpu/memory/disk/nic',
  `brand` varchar(100) DEFAULT NULL COMMENT '品牌',
  `model` varchar(100) NOT NULL COMMENT '型号',
  `spec` json DEFAULT NULL COMMENT '规格详情(JSON)',
  `is_active` tinyint(1) NOT NULL COMMENT '是否启用',
  `sort_order` smallint NOT NULL COMMENT '排序权重',
  `remark` varchar(200) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `customer_id` bigint DEFAULT NULL,
  `scope` enum('global','customer') NOT NULL DEFAULT 'global' COMMENT '模板作用域: global=公共模板, customer=客户专属模板',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ct_category_customer_model` (`category`,`customer_id`,`model`),
  KEY `ix_component_templates_active_cate` (`is_active`,`category`),
  KEY `fk_component_templates_customer` (`customer_id`),
  KEY `idx_ct_scope` (`scope`),
  CONSTRAINT `fk_component_templates_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=369 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='配件模板';

DROP TABLE IF EXISTS `customer_termination_archive`;
CREATE TABLE `customer_termination_archive` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `customer_id` int NOT NULL COMMENT '客户ID',
  `summary_json` json NOT NULL COMMENT '释放前资源完整快照（与 get_customer_assets 同构）',
  `pdf_blob` longblob COMMENT 'PDF 二进制内容（LONGBLOB，事务外回填）',
  `pdf_size` int DEFAULT NULL COMMENT 'PDF 字节数，便于列表展示/告警',
  `operator_id` int NOT NULL COMMENT '终止操作人ID',
  `reason` varchar(255) DEFAULT NULL COMMENT '终止原因（可选，前端弹窗传入）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间',
  PRIMARY KEY (`id`),
  KEY `ix_cta_customer_created` (`customer_id`,`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户终止存档';

DROP TABLE IF EXISTS `customers`;
CREATE TABLE `customers` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `customer_name` varchar(255) NOT NULL COMMENT '客户名称',
  `customer_status` smallint NOT NULL DEFAULT '0' COMMENT '客户状态(0-活跃 1-停用 2-待审核)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `contact_person` varchar(50) DEFAULT NULL,
  `contact_phone` varchar(20) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `address` varchar(200) DEFAULT NULL,
  `notes` mediumtext,
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间(NULL=未删除)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_customer_manager_customer_name` (`customer_name`),
  KEY `idx_customer_deleted_status` (`deleted_at`,`customer_status`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户信息表';

DROP TABLE IF EXISTS `device_asset`;
CREATE TABLE `device_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_id` bigint NOT NULL COMMENT '关联设备ID（唯一）',
  `asset_number` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '资产编号',
  `supplier` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '供应商名称',
  `supplier_contact` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '供应商联系人',
  `contract_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '采购合同编号',
  `purchase_date` date DEFAULT NULL COMMENT '采购日期',
  `purchase_price` decimal(12,2) DEFAULT NULL COMMENT '采购价格(元)',
  `invoice_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '发票号码',
  `warranty_start` date DEFAULT NULL COMMENT '保修开始日期',
  `warranty_end` date DEFAULT NULL COMMENT '保修到期日期',
  `warranty_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '保修类型',
  `online_date` date DEFAULT NULL COMMENT '上线投产日期',
  `offline_date` date DEFAULT NULL COMMENT '下线/报废日期',
  `lifecycle_years` tinyint DEFAULT NULL COMMENT '预计使用年限',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_asset_device` (`device_id`),
  UNIQUE KEY `uk_asset_number` (`asset_number`),
  KEY `idx_asset_warranty_end` (`warranty_end`),
  KEY `idx_asset_purchase_date` (`purchase_date`),
  KEY `idx_asset_supplier` (`supplier`),
  CONSTRAINT `fk_asset_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备资产台账表（1:1扩展）';

DROP TABLE IF EXISTS `device_config_backups`;
CREATE TABLE `device_config_backups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `config_content` mediumtext NOT NULL,
  `config_hash` varchar(64) NOT NULL,
  `backup_type` enum('manual','scheduled','pre_change') NOT NULL DEFAULT 'manual',
  `file_size` int unsigned DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_config_device_created` (`device_id`,`created_at` DESC),
  KEY `idx_config_hash` (`config_hash`),
  CONSTRAINT `fk_config_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备配置备份';

DROP TABLE IF EXISTS `device_config_changes`;
CREATE TABLE `device_config_changes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `backup_id` bigint DEFAULT NULL,
  `change_summary` varchar(500) NOT NULL,
  `change_detail` mediumtext,
  `status` enum('draft','pending','approved','rejected','applied') NOT NULL DEFAULT 'draft',
  `requested_by` bigint NOT NULL,
  `approved_by` bigint DEFAULT NULL,
  `applied_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_change_device_status` (`device_id`,`status`),
  KEY `idx_change_requested` (`requested_by`),
  KEY `fk_change_approver` (`approved_by`),
  KEY `fk_change_backup` (`backup_id`),
  CONSTRAINT `fk_change_approver` FOREIGN KEY (`approved_by`) REFERENCES `users` (`id`),
  CONSTRAINT `fk_change_backup` FOREIGN KEY (`backup_id`) REFERENCES `device_config_backups` (`id`),
  CONSTRAINT `fk_change_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`),
  CONSTRAINT `fk_change_requester` FOREIGN KEY (`requested_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备配置变更审批';

DROP TABLE IF EXISTS `device_connections`;
CREATE TABLE `device_connections` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_id` bigint NOT NULL COMMENT '设备ID（服务器）',
  `switch_device_id` bigint NOT NULL COMMENT '交换机设备ID',
  `connection_type` varchar(50) DEFAULT NULL,
  `vlan_id` smallint unsigned DEFAULT NULL,
  `notes` mediumtext,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `switch_port_id` bigint DEFAULT NULL,
  `device_nics_port_id` bigint DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'active',
  `bandwidth` varchar(20) DEFAULT NULL,
  `description` varchar(200) DEFAULT NULL,
  `lag_group_id` bigint DEFAULT NULL,
  `port_role` enum('standalone','primary','backup','member') NOT NULL DEFAULT 'standalone',
  `redundancy_mode` enum('none','active-standby','active-active') NOT NULL DEFAULT 'none',
  `vlan_mode` enum('access','trunk','hybrid') NOT NULL DEFAULT 'access',
  `native_vlan` smallint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_dc_server_search` (`device_id`,`device_nics_port_id`),
  KEY `idx_dc_switch_search` (`switch_device_id`,`switch_port_id`),
  KEY `idx_dc_status_lag` (`status`,`lag_group_id`),
  KEY `idx_dc_nics_port` (`device_nics_port_id`),
  KEY `fk_dc_lag_group` (`lag_group_id`),
  KEY `fk_switch_port_id` (`switch_port_id`),
  KEY `idx_dc_device_switch` (`device_id`,`switch_device_id`),
  CONSTRAINT `device_connections_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `device_connections_ibfk_2` FOREIGN KEY (`switch_device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dc_lag_group` FOREIGN KEY (`lag_group_id`) REFERENCES `link_aggregation_groups` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_device_connection_nics_port` FOREIGN KEY (`device_nics_port_id`) REFERENCES `device_nics_port` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_switch_port_id` FOREIGN KEY (`switch_port_id`) REFERENCES `network_ports` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备连接表(D2N)';

DROP TABLE IF EXISTS `device_hardware`;
CREATE TABLE `device_hardware` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_id` bigint NOT NULL COMMENT '关联设备ID（唯一）',
  `cpu` varchar(100) DEFAULT NULL COMMENT 'CPU型号',
  `cpu_template_id` bigint DEFAULT NULL,
  `cpu_way` tinyint DEFAULT NULL,
  `cpu_cores` smallint DEFAULT NULL,
  `memory` varchar(100) DEFAULT NULL COMMENT '内存配置描述',
  `memory_template_id` bigint DEFAULT NULL,
  `memory_dimm_count` smallint DEFAULT NULL COMMENT '内存条数',
  `memory_size_gb` int DEFAULT NULL COMMENT '内存总容量(GB)',
  `gpu` varchar(200) DEFAULT NULL COMMENT 'GPU配置描述',
  `gpu_count` smallint DEFAULT NULL COMMENT 'GPU数量',
  `gpu_template_id` bigint DEFAULT NULL COMMENT 'GPU模板ID',
  `storage_summary` varchar(200) DEFAULT NULL,
  `os_version` varchar(255) DEFAULT NULL COMMENT '操作系统版本',
  `ipmi_address` varchar(50) DEFAULT NULL COMMENT 'IPMI/BMC IP地址',
  `ipmi_username` varchar(64) DEFAULT NULL,
  `ipmi_password` varchar(255) DEFAULT NULL,
  `ip_address` json DEFAULT NULL COMMENT 'IP地址列表(JSON数组)',
  `device_config` json DEFAULT NULL COMMENT '扩展配置',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_hardware_device` (`device_id`),
  KEY `idx_hardware_os` (`os_version`(50)),
  KEY `idx_hardware_memory_gb` (`memory_size_gb`),
  KEY `idx_hw_templates` (`cpu_template_id`,`memory_template_id`),
  KEY `fk_hw_memory_template` (`memory_template_id`),
  KEY `idx_hardware_gpu_template` (`gpu_template_id`),
  KEY `idx_functional_hw_os_platform` ((cast(json_unquote(json_extract(`device_config`,_utf8mb4'$.os_platform')) as char(30) charset utf8mb4))),
  CONSTRAINT `fk_hardware_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_hardware_gpu_template` FOREIGN KEY (`gpu_template_id`) REFERENCES `component_templates` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_hw_cpu_template` FOREIGN KEY (`cpu_template_id`) REFERENCES `component_templates` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_hw_memory_template` FOREIGN KEY (`memory_template_id`) REFERENCES `component_templates` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备硬件规格表';

DROP TABLE IF EXISTS `device_metric_alert_state`;
CREATE TABLE `device_metric_alert_state` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '设备ID',
  `metric_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标标识，如 temperature / disk_failure / port_updown / raid_failure',
  `index_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '指标实例索引（端口号/传感器名），非索引指标为空串',
  `alert_type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '告警类型（NotificationTypeCode）',
  `breached` tinyint(1) NOT NULL DEFAULT '0' COMMENT '当前是否处于告警态',
  `severity` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '最近一次告警层级 crit / warn / ok',
  `last_value` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '最近一次指标值快照',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dmas_device_metric_index` (`device_id`,`metric_key`,`index_key`),
  KEY `ix_dmas_metric_key` (`metric_key`),
  CONSTRAINT `fk_dmas_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=972 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设备指标告警状态（按指标维度去重与恢复）';

DROP TABLE IF EXISTS `device_metric_baseline`;
CREATE TABLE `device_metric_baseline` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '设备ID',
  `metric_key` varchar(64) NOT NULL COMMENT '指标标识',
  `index_key` varchar(128) NOT NULL DEFAULT '' COMMENT '指标实例索引',
  `hour_of_day` smallint NOT NULL COMMENT '小时0-23，降级基线为-1',
  `day_of_week` smallint NOT NULL COMMENT '星期0-6，降级基线为-1',
  `mean` decimal(20,6) NOT NULL COMMENT '均值',
  `stddev` decimal(20,6) NOT NULL DEFAULT '0.000000' COMMENT '标准差',
  `sample_count` int NOT NULL DEFAULT '0' COMMENT '样本数',
  `baseline_status` varchar(30) NOT NULL DEFAULT 'normal' COMMENT 'normal/degraded/insufficient_samples',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dmb_device_metric_hour_dow` (`device_id`,`metric_key`,`index_key`,`hour_of_day`,`day_of_week`),
  CONSTRAINT `fk_dmb_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指标基线（按小时×星期分桶，滑动28天）';

DROP TABLE IF EXISTS `device_metric_latest`;
CREATE TABLE `device_metric_latest` (
  `device_id` bigint NOT NULL COMMENT '设备ID',
  `metric_key` varchar(64) NOT NULL COMMENT '指标标识，如 cpu_usage / temperature / zabbix_cpu_usage',
  `index_key` varchar(128) NOT NULL COMMENT '指标实例索引（端口号 / 传感器名 / CPU slot 名），非索引指标为空串',
  `value` varchar(255) DEFAULT NULL COMMENT '最近一次指标值（字符串快照，前端按 metric_type 解析展示）',
  `severity` varchar(20) DEFAULT NULL COMMENT '最近一次告警层级 crit / warn / ok（未超阈值为 ok）',
  `breached` tinyint(1) NOT NULL COMMENT '最近一次是否超阈值',
  `collected_at` datetime NOT NULL COMMENT '最近一次采集时间',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dml_device_metric_index` (`device_id`,`metric_key`,`index_key`),
  KEY `ix_dml_metric_key` (`metric_key`),
  CONSTRAINT `device_metric_latest_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=12278384 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指标当前值（每次采集 upsert，含正常值）';

DROP TABLE IF EXISTS `device_metric_override`;
CREATE TABLE `device_metric_override` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '设备 ID',
  `metric_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标标识',
  `threshold` json NOT NULL COMMENT '覆盖阈值 JSON: {warn, crit, min, max, expected}',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `note` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '覆盖原因/备注',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dmo_device_metric` (`device_id`,`metric_key`),
  CONSTRAINT `fk_dmo_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设备级阈值覆盖（G4.3）';

DROP TABLE IF EXISTS `device_metric_timeseries`;
CREATE TABLE `device_metric_timeseries` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID（复合主键第一部分，配合分区键 collected_at）',
  `device_id` bigint NOT NULL COMMENT '关联设备ID（分区表不支持外键，设备删除由应用层负责清理）',
  `metric_key` varchar(64) NOT NULL COMMENT '指标 key，如 cpu_usage / temperature / if_status',
  `index_key` varchar(128) NOT NULL DEFAULT '' COMMENT '指标实例索引，如端口号 ifIndex；无索引时为空串',
  `value` varchar(255) DEFAULT NULL COMMENT '指标值（字符串存储，前端按 metric_type 解析为数值/状态）',
  `severity` varchar(20) DEFAULT NULL COMMENT '告警级别 ok/warn/crit（阈值判定结果）',
  `breached` tinyint(1) NOT NULL DEFAULT '0' COMMENT '本次采集是否触发阈值告警',
  `collected_at` datetime NOT NULL COMMENT '采集时间（=趋势横轴，分区键）',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '写入时间',
  PRIMARY KEY (`id`),
  KEY `ix_dmts_device_metric_collected` (`device_id`,`metric_key`,`collected_at`),
  KEY `ix_dmts_collected` (`collected_at`)
) ENGINE=InnoDB AUTO_INCREMENT=10560034 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指标值历史时序分区表（每次采集每指标一行，供趋势图，保留90天）';

DROP TABLE IF EXISTS `device_monitor_credentials`;
CREATE TABLE `device_monitor_credentials` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `credential_id` bigint NOT NULL,
  `device_id` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dmc_cred_device` (`credential_id`,`device_id`),
  KEY `fk_dmc_device` (`device_id`),
  CONSTRAINT `fk_dmc_cred` FOREIGN KEY (`credential_id`) REFERENCES `monitor_credentials` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dmc_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备监控凭据关联（多对多）';

DROP TABLE IF EXISTS `device_monitor_probe_events`;
CREATE TABLE `device_monitor_probe_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `protocol` varchar(20) NOT NULL,
  `reachable` tinyint(1) NOT NULL,
  `latency_ms` int DEFAULT NULL,
  `consecutive_failures` int NOT NULL DEFAULT '0',
  `episode` int NOT NULL DEFAULT '0',
  `is_alert` tinyint(1) NOT NULL DEFAULT '0',
  `error` text,
  `extra` json DEFAULT NULL,
  `probed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`,`probed_at`),
  KEY `ix_dmpe_device_probed` (`device_id`,`probed_at`),
  KEY `ix_dmpe_probed` (`probed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=136241 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备探测历史时序分区表（每次探测一行，保留90天）'
/*!50100 PARTITION BY RANGE (to_days(`probed_at`))
(PARTITION p20260704 VALUES LESS THAN (740167) ENGINE = InnoDB,
 PARTITION p20260705 VALUES LESS THAN (740168) ENGINE = InnoDB,
 PARTITION p20260706 VALUES LESS THAN (740169) ENGINE = InnoDB,
 PARTITION p20260707 VALUES LESS THAN (740170) ENGINE = InnoDB,
 PARTITION p20260708 VALUES LESS THAN (740171) ENGINE = InnoDB,
 PARTITION p20260709 VALUES LESS THAN (740172) ENGINE = InnoDB,
 PARTITION p20260710 VALUES LESS THAN (740173) ENGINE = InnoDB,
 PARTITION p20260711 VALUES LESS THAN (740174) ENGINE = InnoDB,
 PARTITION p20260712 VALUES LESS THAN (740175) ENGINE = InnoDB,
 PARTITION p20260713 VALUES LESS THAN (740176) ENGINE = InnoDB,
 PARTITION p20260714 VALUES LESS THAN (740177) ENGINE = InnoDB,
 PARTITION p20260715 VALUES LESS THAN (740178) ENGINE = InnoDB,
 PARTITION p20260716 VALUES LESS THAN (740179) ENGINE = InnoDB,
 PARTITION p20260717 VALUES LESS THAN (740180) ENGINE = InnoDB,
 PARTITION p20260718 VALUES LESS THAN (740181) ENGINE = InnoDB,
 PARTITION p20260719 VALUES LESS THAN (740182) ENGINE = InnoDB,
 PARTITION p20260720 VALUES LESS THAN (740183) ENGINE = InnoDB,
 PARTITION p20260721 VALUES LESS THAN (740184) ENGINE = InnoDB,
 PARTITION p20260722 VALUES LESS THAN (740185) ENGINE = InnoDB,
 PARTITION p20260723 VALUES LESS THAN (740186) ENGINE = InnoDB,
 PARTITION p20260724 VALUES LESS THAN (740187) ENGINE = InnoDB,
 PARTITION p20260725 VALUES LESS THAN (740188) ENGINE = InnoDB,
 PARTITION p20260726 VALUES LESS THAN (740189) ENGINE = InnoDB,
 PARTITION p20260727 VALUES LESS THAN (740190) ENGINE = InnoDB,
 PARTITION p20260728 VALUES LESS THAN (740191) ENGINE = InnoDB,
 PARTITION p20260729 VALUES LESS THAN (740192) ENGINE = InnoDB,
 PARTITION p20260730 VALUES LESS THAN (740193) ENGINE = InnoDB,
 PARTITION p20260731 VALUES LESS THAN (740194) ENGINE = InnoDB,
 PARTITION p20260801 VALUES LESS THAN (740195) ENGINE = InnoDB,
 PARTITION p20260802 VALUES LESS THAN (740196) ENGINE = InnoDB,
 PARTITION p20260803 VALUES LESS THAN (740197) ENGINE = InnoDB,
 PARTITION p20260804 VALUES LESS THAN (740198) ENGINE = InnoDB,
 PARTITION p20260805 VALUES LESS THAN (740199) ENGINE = InnoDB,
 PARTITION p20260806 VALUES LESS THAN (740200) ENGINE = InnoDB,
 PARTITION p20260807 VALUES LESS THAN (740201) ENGINE = InnoDB,
 PARTITION p20260808 VALUES LESS THAN (740202) ENGINE = InnoDB,
 PARTITION p_future VALUES LESS THAN MAXVALUE ENGINE = InnoDB) */;

DROP TABLE IF EXISTS `device_monitor_status`;
CREATE TABLE `device_monitor_status` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `protocol` varchar(20) NOT NULL COMMENT 'snmp/redfish/ipmi；每设备单快照，凭据协议切换（如Redfish→IPMI）会覆盖整行，含extra形状变化，属预期行为',
  `reachable` tinyint(1) NOT NULL COMMENT '当前是否可达',
  `ever_reachable` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否曾成功探测过（用于"首探即不可达"也能正确告警，而不是等一次False→True→False才触发）',
  `down_alerted` tinyint(1) NOT NULL DEFAULT '0' COMMENT '当前是否已处于"不可达且已告警"状态，防止停留期内重复告警',
  `down_episode` int NOT NULL DEFAULT '0' COMMENT '第几次进入不可达周期，写入 idempotency_key 使同一天内"恢复后再次故障"也能正常触发新告警',
  `last_reachable_at` datetime DEFAULT NULL COMMENT '最后一次可达时间',
  `last_unreachable_at` datetime DEFAULT NULL COMMENT '最后一次不可达时间',
  `last_checked_at` datetime NOT NULL COMMENT '最后一次探测时间（无论成败）',
  `consecutive_failures` int NOT NULL DEFAULT '0' COMMENT '连续失败次数（用于抖动抑制/阈值判定）',
  `latency_ms` int DEFAULT NULL COMMENT '本次探测耗时',
  `extra` json DEFAULT NULL COMMENT '协议特有附加信息，字段约定见 CODE_WIKI.md 监控模块章节',
  `last_error` text COMMENT '最近一次失败的错误信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `monitor_enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '设备级监控开关：0=暂停探测，1=正常探测（无状态行视为默认启用）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_device_monitor` (`device_id`),
  KEY `idx_reachable` (`reachable`),
  KEY `idx_last_checked` (`last_checked_at`),
  CONSTRAINT `fk_monitor_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=137935 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备健康监控最新状态快照（每设备一行，非时序表）';

DROP TABLE IF EXISTS `device_monitor_timeseries_daily`;
CREATE TABLE `device_monitor_timeseries_daily` (
  `device_id` bigint NOT NULL,
  `metric` varchar(32) NOT NULL,
  `day_bucket` date NOT NULL,
  `avg_value` float NOT NULL,
  `min_value` float NOT NULL,
  `max_value` float NOT NULL,
  `sample_count` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`,`metric`,`day_bucket`),
  CONSTRAINT `fk_daily_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控时序天级预聚合，从 hourly 降采样，保留730天（架构3 长期趋势层）';

DROP TABLE IF EXISTS `device_monitor_timeseries_hourly`;
CREATE TABLE `device_monitor_timeseries_hourly` (
  `device_id` bigint NOT NULL,
  `metric` varchar(32) NOT NULL,
  `hour_bucket` datetime NOT NULL,
  `avg_value` double NOT NULL,
  `min_value` double NOT NULL,
  `max_value` double NOT NULL,
  `sample_count` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`,`metric`,`hour_bucket`),
  KEY `ix_dmth_bucket` (`hour_bucket`),
  CONSTRAINT `fk_dmth_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控时序小时级预聚合（保留90天）';

DROP TABLE IF EXISTS `device_nics_port`;
CREATE TABLE `device_nics_port` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `nic_number` int NOT NULL,
  `nic_name` varchar(100) NOT NULL DEFAULT '',
  `template_id` bigint DEFAULT NULL,
  `port_number` int NOT NULL,
  `port_name` varchar(50) DEFAULT NULL,
  `mac_address` varchar(17) DEFAULT NULL,
  `port_type` varchar(20) NOT NULL,
  `port_speed` varchar(20) NOT NULL,
  `port_status` varchar(20) NOT NULL DEFAULT 'free',
  `description` varchar(200) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_device_nic_port` (`device_id`,`nic_number`,`port_number`),
  KEY `idx_dnp_device_status` (`device_id`,`port_status`),
  KEY `idx_port_type_speed` (`port_type`,`port_speed`),
  KEY `fk_dnp_template` (`template_id`),
  CONSTRAINT `fk_device_nics_port_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dnp_template` FOREIGN KEY (`template_id`) REFERENCES `component_templates` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=246 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备网卡端口表';

DROP TABLE IF EXISTS `device_server_ext`;
CREATE TABLE `device_server_ext` (
  `device_id` bigint NOT NULL COMMENT '设备ID(PK+FK→devices.id)',
  `parent_device_id` bigint DEFAULT NULL COMMENT '父设备ID(机箱→设备)',
  `is_chassis` tinyint(1) DEFAULT '0' COMMENT '是否为机箱',
  `node_position` int DEFAULT NULL COMMENT '节点在机箱中的位置',
  `node_row` int DEFAULT NULL COMMENT '节点行号',
  `node_col` int DEFAULT NULL COMMENT '节点列号',
  `total_nodes` int DEFAULT NULL COMMENT '机箱总节点数',
  `node_rows` int DEFAULT NULL COMMENT '节点行数',
  `node_cols` int DEFAULT NULL COMMENT '节点列数',
  `node_naming_pattern` varchar(100) DEFAULT NULL COMMENT '节点命名模式',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`device_id`),
  KEY `idx_server_ext_parent` (`parent_device_id`),
  KEY `idx_server_ext_chassis` (`is_chassis`),
  CONSTRAINT `fk_server_ext_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_server_ext_parent` FOREIGN KEY (`parent_device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='服务器扩展表(1:1扩展devices,仅服务器/机箱)';

DROP TABLE IF EXISTS `device_storage`;
CREATE TABLE `device_storage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `storage_type` varchar(50) NOT NULL,
  `capacity` varchar(50) NOT NULL,
  `interface_type` varchar(50) DEFAULT NULL,
  `manufacturer` varchar(100) DEFAULT NULL,
  `model` varchar(100) DEFAULT NULL,
  `template_id` bigint DEFAULT NULL,
  `serial_number` varchar(100) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `capacity_gb` int DEFAULT NULL,
  `slot_number` smallint DEFAULT NULL,
  `firmware` varchar(50) DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'normal',
  PRIMARY KEY (`id`),
  UNIQUE KEY `serial_number` (`serial_number`),
  KEY `idx_ds_device_status` (`device_id`,`status`),
  KEY `fk_ds_template` (`template_id`),
  KEY `idx_storage_device_type` (`device_id`,`storage_type`),
  CONSTRAINT `device_storage_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ds_template` FOREIGN KEY (`template_id`) REFERENCES `component_templates` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=106 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `device_switch_ext`;
CREATE TABLE `device_switch_ext` (
  `device_id` bigint NOT NULL COMMENT '设备ID(PK+FK→devices.id)',
  `switch_role` smallint DEFAULT NULL COMMENT '交换机角色: 0=核心, 1=接入, NULL=非交换机',
  `layer` smallint DEFAULT NULL COMMENT '网络层级',
  `uplink_device_id` bigint DEFAULT NULL COMMENT '上行设备ID',
  `uplink_port_ids` json DEFAULT NULL COMMENT '上行端口ID数组(引用network_ports.id)',
  `core_device_id` bigint DEFAULT NULL COMMENT '核心交换机ID',
  `port_num` smallint DEFAULT NULL COMMENT '端口数量',
  `port_sync_enabled` tinyint(1) DEFAULT NULL COMMENT '端口同步开关(NULL=跟随全局,True=强制开,False=强制关)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`device_id`),
  KEY `idx_switch_ext_role` (`switch_role`),
  KEY `idx_switch_ext_uplink` (`uplink_device_id`),
  KEY `idx_switch_ext_core` (`core_device_id`),
  CONSTRAINT `fk_switch_ext_core` FOREIGN KEY (`core_device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_switch_ext_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_switch_ext_uplink` FOREIGN KEY (`uplink_device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交换机扩展表(1:1扩展devices,仅交换机)';

DROP TABLE IF EXISTS `devices`;
CREATE TABLE `devices` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_name` varchar(100) NOT NULL COMMENT '设备名称',
  `device_model` varchar(100) DEFAULT NULL COMMENT '设备型号',
  `brand` varchar(100) DEFAULT NULL COMMENT '品牌',
  `device_type` varchar(50) NOT NULL COMMENT '设备类型',
  `serial_number` varchar(255) DEFAULT NULL COMMENT '序列号',
  `management_ip` varchar(50) DEFAULT NULL COMMENT '管理IP',
  `mac_address` varchar(17) DEFAULT NULL COMMENT 'MAC地址',
  `hostname` varchar(128) DEFAULT NULL COMMENT '主机名',
  `metric_template_group_id` bigint DEFAULT NULL COMMENT '显式关联的指标模板组ID（可空，为空时自动匹配）',
  `cabinet_id` bigint DEFAULT NULL COMMENT '机柜ID',
  `u_position` int DEFAULT NULL COMMENT 'U位起始位置',
  `height_u` int DEFAULT NULL COMMENT '占用U位数量',
  `power` float DEFAULT NULL COMMENT '功率(W)',
  `device_subtype` varchar(20) DEFAULT NULL,
  `status` smallint DEFAULT NULL COMMENT '设备状态',
  `responsible_person` bigint DEFAULT NULL COMMENT '责任人',
  `notes` mediumtext,
  `customer_id` bigint DEFAULT NULL COMMENT '客户ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间',
  PRIMARY KEY (`id`),
  KEY `idx_device_deleted_type_status` (`deleted_at`,`device_type`,`status`),
  KEY `idx_device_cabinet_u` (`cabinet_id`,`u_position`),
  KEY `idx_device_serial` (`serial_number`),
  KEY `idx_device_management_ip` (`management_ip`),
  KEY `idx_device_name` (`device_name`),
  KEY `idx_device_customer` (`customer_id`),
  KEY `fk_device_responsible_person` (`responsible_person`),
  KEY `ix_devices_mmtg` (`metric_template_group_id`),
  CONSTRAINT `fk_device_cabinet` FOREIGN KEY (`cabinet_id`) REFERENCES `cabinets` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_device_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_device_responsible_person` FOREIGN KEY (`responsible_person`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_devices_mmtg` FOREIGN KEY (`metric_template_group_id`) REFERENCES `monitor_metric_template_groups` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=178 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备信息表';

DROP TABLE IF EXISTS `ip_addresses`;
CREATE TABLE `ip_addresses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(45) NOT NULL COMMENT 'IP地址',
  `customer_id` bigint DEFAULT NULL COMMENT '客户ID',
  `status` tinyint NOT NULL DEFAULT '3' COMMENT 'IP状态: 0=活跃 1=非活跃 2=封禁 3=未使用',
  `notes` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `room_id` int DEFAULT NULL,
  `ip_int` int unsigned DEFAULT NULL COMMENT 'IP整数表示(INET_ATON),用于范围查询',
  `last_active_at` datetime DEFAULT NULL COMMENT '最近一次被观测到活跃的时间（陈旧度清理用）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_ip_room` (`ip_address`,`room_id`),
  KEY `idx_ip_deleted_room_status` (`room_id`,`status`),
  KEY `idx_ip_int_status` (`ip_int`,`status`),
  KEY `fk_customer` (`customer_id`),
  KEY `ix_ip_last_active` (`last_active_at`),
  CONSTRAINT `fk_ip_manager_customer_id` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `ip_addresses_ibfk_1` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=70626 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ip详情';

DROP TABLE IF EXISTS `ip_allocation_logs`;
CREATE TABLE `ip_allocation_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(45) NOT NULL,
  `room_id` int NOT NULL,
  `action` enum('allocate','release','change_status') NOT NULL,
  `old_status` tinyint DEFAULT NULL,
  `new_status` tinyint DEFAULT NULL,
  `operator_id` bigint NOT NULL,
  `detail` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_alloc_created_operator` (`created_at` DESC,`operator_id`),
  KEY `fk_alloc_operator` (`operator_id`),
  KEY `fk_alloc_room` (`room_id`),
  KEY `idx_alloc_ip_time` (`ip_address`,`room_id`,`created_at`),
  CONSTRAINT `fk_alloc_operator` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`),
  CONSTRAINT `fk_alloc_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP分配历史日志';

DROP TABLE IF EXISTS `ip_ban_records`;
CREATE TABLE `ip_ban_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(45) NOT NULL,
  `room_id` int NOT NULL,
  `switch_id` bigint NOT NULL,
  `ban_mode` varchar(16) NOT NULL DEFAULT 'route',
  `ban_meta` json DEFAULT NULL,
  `action` enum('ban','unban') NOT NULL DEFAULT 'ban',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `operator_id` bigint DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `ip_int` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ban_lookup` (`is_active`,`room_id`,`switch_id`),
  KEY `idx_ban_ip_int` (`ip_int`,`is_active`),
  KEY `idx_ban_ip_room_active` (`ip_address`,`room_id`,`is_active`),
  KEY `fk_ban_operator` (`operator_id`),
  KEY `fk_ban_switch_device` (`switch_id`),
  KEY `fk_ip_ban_records_room_id` (`room_id`),
  CONSTRAINT `fk_ban_operator` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ban_switch_device` FOREIGN KEY (`switch_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ip_ban_records_room_id` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP封禁信息';

DROP TABLE IF EXISTS `ip_networks`;
CREATE TABLE `ip_networks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `network` varchar(45) NOT NULL COMMENT '网段地址(如192.168.1.0/24)',
  `switch_id` bigint NOT NULL COMMENT '所属交换机 FK→device_manager',
  `port` varchar(50) NOT NULL DEFAULT '' COMMENT '端口名',
  `customer_id` bigint DEFAULT NULL,
  `gateway` varchar(45) DEFAULT NULL,
  `notes` varchar(255) DEFAULT NULL,
  `room_id` int NOT NULL,
  `network_int` int unsigned DEFAULT NULL COMMENT '网段起始IP整数',
  `prefix` tinyint unsigned DEFAULT NULL COMMENT '子网掩码位数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_net_switch_port_room` (`network`,`switch_id`,`port`,`room_id`),
  KEY `idx_net_room_customer` (`room_id`,`customer_id`),
  KEY `idx_net_network_int_prefix` (`network_int`,`prefix`),
  KEY `idx_net_switch_room` (`switch_id`,`room_id`),
  CONSTRAINT `fk_net_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_net_switch` FOREIGN KEY (`switch_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1930 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP网段规划';

DROP TABLE IF EXISTS `ip_switch_info`;
CREATE TABLE `ip_switch_info` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(45) NOT NULL,
  `mac_address` varchar(17) DEFAULT NULL,
  `switch_id` bigint NOT NULL,
  `port_id` bigint DEFAULT NULL,
  `port` varchar(50) DEFAULT NULL,
  `vlan_id` smallint DEFAULT NULL,
  `room_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `ip_int` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_isi_ip_room` (`ip_address`,`room_id`),
  KEY `idx_isi_switch_port` (`switch_id`,`port_id`),
  KEY `idx_isi_ip_int` (`ip_int`),
  KEY `idx_isi_mac_room` (`mac_address`,`room_id`),
  KEY `fk_isi_port` (`port_id`),
  KEY `fk_isi_room` (`room_id`),
  CONSTRAINT `fk_isi_port` FOREIGN KEY (`port_id`) REFERENCES `network_ports` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_isi_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_isi_switch` FOREIGN KEY (`switch_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=10742 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP交换机定位信息';

DROP TABLE IF EXISTS `link_aggregation_groups`;
CREATE TABLE `link_aggregation_groups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '所属设备 FK→device_manager',
  `lag_name` varchar(50) NOT NULL COMMENT '聚合组名',
  `lag_type` enum('lacp','static') NOT NULL DEFAULT 'lacp' COMMENT '聚合类型',
  `algorithm` varchar(32) DEFAULT NULL,
  `status` tinyint NOT NULL DEFAULT '1',
  `member_count` smallint NOT NULL DEFAULT '0',
  `purpose` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lag_device_name` (`device_id`,`lag_name`),
  KEY `idx_lag_device_status` (`device_id`,`status`),
  CONSTRAINT `fk_lag_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='链路聚合组';

DROP TABLE IF EXISTS `mail_settings`;
CREATE TABLE `mail_settings` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `key` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置键',
  `value` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '配置值',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_mail_setting_key` (`key`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件服务器配置表';

DROP TABLE IF EXISTS `monitor_alert_dependency_rule`;
CREATE TABLE `monitor_alert_dependency_rule` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL COMMENT '规则名称',
  `upstream_device_id` bigint NOT NULL COMMENT '上游设备ID',
  `downstream_device_id` bigint NOT NULL COMMENT '下游设备ID',
  `alert_types` json DEFAULT NULL COMMENT '受抑制告警类型列表(null=全部)',
  `reason` varchar(255) DEFAULT NULL COMMENT '规则说明',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_madr_upstream` (`upstream_device_id`),
  KEY `ix_madr_downstream` (`downstream_device_id`),
  KEY `ix_madr_enabled` (`enabled`),
  CONSTRAINT `fk_madr_downstream` FOREIGN KEY (`downstream_device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_madr_upstream` FOREIGN KEY (`upstream_device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控告警依赖抑制规则(P2-17)';

DROP TABLE IF EXISTS `monitor_alert_outbox`;
CREATE TABLE `monitor_alert_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_id` bigint DEFAULT NULL COMMENT '关联设备ID（设备被删除后置空，历史告警行本身保留）',
  `alert_type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'device_unreachable/device_recovered',
  `severity` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'info/warning/critical',
  `dedup_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '=notify idempotency_key，去重/幂等',
  `payload_json` longtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'notify 参数字典的 JSON',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT 'pending/sent/failed',
  `attempts` int NOT NULL DEFAULT '0' COMMENT '投递尝试次数',
  `last_error` text COLLATE utf8mb4_unicode_ci COMMENT '最近一次投递失败信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入箱时间',
  `sent_at` datetime DEFAULT NULL COMMENT '投递成功时间',
  `acknowledged_by` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '确认人用户名（G9 人工确认/认领）',
  `acknowledged_at` datetime DEFAULT NULL COMMENT '确认时间（G9；供 G4.2 升级扫描判断未确认告警）',
  `ack_note` text COLLATE utf8mb4_unicode_ci COMMENT '确认备注（G9）',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `closed_by` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关闭人用户名（P2-16 manual_close）',
  `closed_at` datetime DEFAULT NULL COMMENT '手动关闭时间（P2-16）',
  `close_reason` text COLLATE utf8mb4_unicode_ci COMMENT '关闭原因（P2-16）',
  `next_retry_at` datetime DEFAULT NULL COMMENT '下次允许重试时间（指数退避；NULL 表示立即可重试）',
  `incident_id` bigint DEFAULT NULL COMMENT '归属事件ID（事件聚合；NULL 表示未聚合或聚合失败）',
  `reason_code` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change',
  PRIMARY KEY (`id`),
  KEY `ix_mao_status` (`status`),
  KEY `ix_mao_dedup_key` (`dedup_key`),
  KEY `ix_mao_created_at` (`created_at`),
  KEY `ix_mao_device` (`device_id`),
  KEY `ix_mao_acknowledged_at` (`acknowledged_at`),
  KEY `ix_mao_closed_at` (`closed_at`),
  KEY `idx_mao_incident` (`incident_id`),
  CONSTRAINT `fk_mao_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=1266 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控告警发件箱（outbox 模式，解耦状态落库与告警投递）';

DROP TABLE IF EXISTS `monitor_credentials`;
CREATE TABLE `monitor_credentials` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `protocol` varchar(20) NOT NULL COMMENT 'snmp/redfish/ipmi',
  `encrypted_payload` text NOT NULL COMMENT 'AES-256-GCM 加密的凭据 JSON，复用 app/utils/security/encryption.py',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `name` varchar(128) NOT NULL COMMENT '同协议下唯一的可读标签',
  `payload_hash` varchar(64) DEFAULT NULL COMMENT 'payload 规范 JSON 的 SHA-256 十六进制（用于同明文凭据去重复用；旧行留空）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_mc_protocol_name` (`protocol`,`name`),
  UNIQUE KEY `uk_mc_protocol_hash` (`protocol`,`payload_hash`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备监控凭据（AES-256-GCM加密）';

DROP TABLE IF EXISTS `monitor_device_type_recommends`;
CREATE TABLE `monitor_device_type_recommends` (
  `device_type` varchar(16) NOT NULL COMMENT '设备类型 network/server/other',
  `categories` json NOT NULL COMMENT '推荐的 category 列表，如 ["temperature","fan","power_supply"]',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_device_type_recommend` (`device_type`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备类型推荐配置，定义每种设备类型推荐哪些 category';

DROP TABLE IF EXISTS `monitor_dynamic_config`;
CREATE TABLE `monitor_dynamic_config` (
  `config_key` varchar(64) NOT NULL COMMENT '配置键（= 现有 _cfg() 调用点使用的大写 MONITOR_* key）',
  `config_value` text NOT NULL COMMENT '配置值（字符串化存储，按 value_type 解析）',
  `value_type` varchar(16) NOT NULL DEFAULT 'string' COMMENT 'string/int/float/bool/json',
  `description` varchar(255) DEFAULT '' COMMENT '配置说明（前端展示）',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  `updated_by` varchar(64) DEFAULT '' COMMENT '操作人（审计）',
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `monitor_escalation_policy`;
CREATE TABLE `monitor_escalation_policy` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '策略名称',
  `alert_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '匹配告警类型（null=全部）',
  `severity` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '匹配告警级别（null=全部）',
  `wait_minutes` int NOT NULL COMMENT '未确认等待分钟数',
  `escalate_severity` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '升级后严重级别',
  `escalate_to_role_id` bigint DEFAULT NULL COMMENT '升级后通知的角色 ID',
  `escalate_webhook_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '升级触发的 webhook URL',
  `repeat_minutes` int NOT NULL DEFAULT '0' COMMENT '重复升级间隔分钟（0=只升一次）',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `ix_mep_enabled` (`enabled`),
  KEY `ix_mep_alert_type` (`alert_type`),
  KEY `fk_mep_role` (`escalate_to_role_id`),
  CONSTRAINT `fk_mep_role` FOREIGN KEY (`escalate_to_role_id`) REFERENCES `roles` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控告警升级策略（G4.2）';

DROP TABLE IF EXISTS `monitor_escalation_step`;
CREATE TABLE `monitor_escalation_step` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `policy_id` bigint unsigned NOT NULL,
  `step_no` int NOT NULL DEFAULT '1' COMMENT '步骤序号（从 1 开始）',
  `wait_minutes` int NOT NULL COMMENT '距告警产生后多少分钟触发',
  `escalate_severity` varchar(16) DEFAULT NULL COMMENT '本步骤升级到的严重级别',
  `escalate_to_role_id` bigint DEFAULT NULL,
  `escalate_webhook_url` varchar(512) DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_mes_policy_step` (`policy_id`,`step_no`),
  KEY `fk_mes_role` (`escalate_to_role_id`),
  CONSTRAINT `fk_mes_policy` FOREIGN KEY (`policy_id`) REFERENCES `monitor_escalation_policy` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_mes_role` FOREIGN KEY (`escalate_to_role_id`) REFERENCES `roles` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控告警升级链步骤（P2-11）';

DROP TABLE IF EXISTS `monitor_incident`;
CREATE TABLE `monitor_incident` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `incident_key` varchar(191) NOT NULL COMMENT '归并键，如 device_unreachable:200（比 dedup_key 粗，不含 metric_key/index/action）',
  `title` varchar(255) NOT NULL COMMENT '事件标题',
  `severity` varchar(20) NOT NULL COMMENT 'info / warning / critical（取事件内最高级别）',
  `status` varchar(16) NOT NULL DEFAULT 'active' COMMENT 'active / acknowledged / closed',
  `reason_code` varchar(40) DEFAULT NULL COMMENT '归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change',
  `root_device_id` bigint DEFAULT NULL COMMENT '根因设备ID（设备删除后置空）',
  `alert_count` int NOT NULL DEFAULT '1' COMMENT '累计告警数（入箱的）',
  `device_count` int NOT NULL DEFAULT '1' COMMENT '影响设备数（根因 ∪ 入箱设备 ∪ 被抑制留痕设备，去重）',
  `first_alert_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首条告警时间',
  `last_alert_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '末条告警时间（L1 时间窗判定基准）',
  `closed_at` datetime DEFAULT NULL COMMENT '关闭时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_incident_key` (`incident_key`),
  KEY `idx_incident_status` (`status`),
  KEY `idx_incident_last_alert` (`last_alert_at`),
  KEY `fk_incident_root_device` (`root_device_id`),
  CONSTRAINT `fk_incident_root_device` FOREIGN KEY (`root_device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=387 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控事件（告警聚合后的运营单元）';

DROP TABLE IF EXISTS `monitor_metric_template_group_items`;
CREATE TABLE `monitor_metric_template_group_items` (
  `group_id` bigint NOT NULL COMMENT '组ID',
  `template_id` bigint unsigned NOT NULL COMMENT '模板ID',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_mmtgi_group_template` (`group_id`,`template_id`),
  KEY `template_id` (`template_id`),
  CONSTRAINT `monitor_metric_template_group_items_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `monitor_metric_template_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `monitor_metric_template_group_items_ibfk_2` FOREIGN KEY (`template_id`) REFERENCES `monitor_metric_templates` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=200 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='模板组-模板关联（勾选指标入组）';

DROP TABLE IF EXISTS `monitor_metric_template_groups`;
CREATE TABLE `monitor_metric_template_groups` (
  `name` varchar(64) NOT NULL COMMENT '组名（运维可读），如 ''华为网络设备核心指标''',
  `device_type` varchar(16) NOT NULL COMMENT '适用设备类型 network / server / other；组内模板必须一致',
  `source` varchar(16) NOT NULL COMMENT '采集来源 snmp / ipmi / zabbix；组内模板必须一致',
  `vendor` varchar(32) DEFAULT NULL COMMENT '厂家约束（可空）；声明时组内模板 vendor 需匹配',
  `display_order` int NOT NULL COMMENT '展示排序（升序），同 device_type+source 内排序',
  `enabled` tinyint(1) NOT NULL COMMENT '是否启用',
  `description` varchar(255) DEFAULT NULL COMMENT '组说明',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_mmtg_name_devtype_source` (`name`,`device_type`,`source`),
  KEY `ix_mmtg_devtype_source` (`device_type`,`source`)
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控指标模板组（运维自定义分组，约束同 device_type+source）';

DROP TABLE IF EXISTS `monitor_metric_templates`;
CREATE TABLE `monitor_metric_templates` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `metric_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标标识，如 temperature / disk_failure / port_updown / raid_failure',
  `category` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'OID 分类标识，关联 monitor_oid_category_rules.category；MIB 扫描导入时自动填充',
  `display_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '中文显示名（运维视角），表格优先展示；为空时回退 metric_key',
  `device_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '适用设备类型 network / server / other',
  `source` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'snmp' COMMENT '采集来源 snmp / ipmi / zabbix',
  `vendor` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '厂家约束（品牌厂商），可空',
  `mib` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'MIB 名称，如 IF-MIB / ENTITY-SENSOR-MIB',
  `oid_symbol` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'MIB 符号，如 ifOperStatus / entPhySensorValue',
  `oid` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '完整数字 OID，如 1.3.6.1.2.1.2.2.1.7；与 oid_symbol（MIB 符号名）互补',
  `zabbix_item_key` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Zabbix item key，source=zabbix 时必填',
  `index_kind` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '索引维度：ifIndex / NULL',
  `metric_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'gauge' COMMENT 'gauge / counter / state / event',
  `unit` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '单位，如 Celsius / bps / %',
  `poll_interval` int NOT NULL DEFAULT '60' COMMENT '采集频率（秒）',
  `threshold` json DEFAULT NULL COMMENT '告警阈值 JSON',
  `severity_default` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '默认告警级别 warn / crit，未配置阈值时回退使用',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '指标说明（运维视角）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `runbook_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '处置预案 URL（P2-14）',
  `runbook_title` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '处置预案标题（P2-14）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_metric_tpl_devtype_metric_vendor` (`device_type`,`metric_key`,`vendor`),
  KEY `ix_metric_tpl_category` (`category`)
) ENGINE=InnoDB AUTO_INCREMENT=428 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控指标模板，驱动 SNMP/IPMI 指标采集';

DROP TABLE IF EXISTS `monitor_oid_category_rules`;
CREATE TABLE `monitor_oid_category_rules` (
  `prefix` varchar(128) NOT NULL COMMENT 'OID 前缀，点分隔符锚定匹配（oid==prefix 或 oid.startswith(prefix+''.''）',
  `category` varchar(32) NOT NULL COMMENT '类别标识，如 temperature / fan / if_status',
  `label` varchar(64) DEFAULT NULL COMMENT '人类可读类别名，如 温度探头',
  `device_type` varchar(16) DEFAULT NULL COMMENT '适用设备类型 network/server/other；NULL=全适用',
  `vendor_id` varchar(32) DEFAULT NULL COMMENT '厂商 enterprise 号（如 674=DELL）；NULL=通用规则',
  `priority` int NOT NULL COMMENT '优先级，高优先先匹配；厂商特定规则用 100，通用用 10',
  `enabled` tinyint(1) NOT NULL COMMENT '是否启用',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_oid_rule_prefix` (`prefix`),
  KEY `idx_oid_rule_vendor` (`vendor_id`)
) ENGINE=InnoDB AUTO_INCREMENT=573 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='OID 分类规则，探测时按前缀打 category 标签';

DROP TABLE IF EXISTS `monitor_silence_rule`;
CREATE TABLE `monitor_silence_rule` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '规则名称',
  `device_ids` json DEFAULT NULL COMMENT '静默设备 ID 列表（null=全部设备）',
  `alert_types` json DEFAULT NULL COMMENT '静默告警类型列表（null=全部类型）',
  `silence_from` datetime NOT NULL COMMENT '静默开始时间',
  `silence_until` datetime NOT NULL COMMENT '静默结束时间',
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '静默原因',
  `created_by` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '创建人用户名',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `ix_msr_enabled` (`enabled`),
  KEY `ix_msr_silence_until` (`silence_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控告警静默规则（G4.1）';

DROP TABLE IF EXISTS `monitor_sla_target`;
CREATE TABLE `monitor_sla_target` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL COMMENT 'SLA 目标名称',
  `target_device_ids` json NOT NULL COMMENT '目标设备 ID 列表',
  `target_ratio` float NOT NULL COMMENT '可用率目标(0~1)',
  `window_days` int NOT NULL DEFAULT '30' COMMENT '评估窗口(天)',
  `description` varchar(255) DEFAULT NULL COMMENT 'SLA 描述',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_mst_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='SLA/SLO 监控目标(P2-13)';

DROP TABLE IF EXISTS `monitor_suppressed_alert_log`;
CREATE TABLE `monitor_suppressed_alert_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint DEFAULT NULL COMMENT '被抑制告警的设备ID（设备删除后置空，留痕行保留）',
  `alert_type` varchar(40) NOT NULL COMMENT '告警类型（device_unreachable / cpu_high 等）',
  `severity` varchar(20) NOT NULL COMMENT 'info / warning / critical',
  `reason_code` varchar(40) NOT NULL COMMENT '抑制来源编码：L2_manual_rule / L2_topology',
  `upstream_device_id` bigint DEFAULT NULL COMMENT '命中的上游设备ID（根因侧，用于归属事件）',
  `incident_id` bigint DEFAULT NULL COMMENT '归属事件ID（L2 聚合后回填；NULL 表示尚未归属）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '留痕时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_msal_incident` (`incident_id`),
  KEY `idx_msal_upstream` (`upstream_device_id`),
  KEY `idx_msal_created_at` (`created_at`),
  KEY `fk_msal_device` (`device_id`),
  CONSTRAINT `fk_msal_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=75 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='被依赖抑制告警留痕（事件影响面统计，不参与投递）';

DROP TABLE IF EXISTS `monitor_vendor_brands`;
CREATE TABLE `monitor_vendor_brands` (
  `enterprise_no` varchar(32) NOT NULL COMMENT 'SNMP enterprise 号（如 674=DELL），对应 OID 规则的 vendor_id',
  `brand_name` varchar(64) NOT NULL COMMENT '品牌全称（英文），如 Dell EMC / Cisco',
  `label` varchar(64) NOT NULL COMMENT '显示名称（含设备类别后缀），如 DELL（服务器） / Cisco（网络）',
  `device_type` varchar(16) NOT NULL COMMENT '适用设备类型 network/server/storage/other',
  `enabled` tinyint(1) NOT NULL COMMENT '是否启用',
  `sort_order` int NOT NULL COMMENT '排序权重，小的在前',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_vendor_brand_device_type` (`device_type`),
  KEY `idx_vendor_brand_enterprise` (`enterprise_no`)
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='厂商品牌，enterprise 号 → 品牌名称映射';

DROP TABLE IF EXISTS `network_connections`;
CREATE TABLE `network_connections` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `local_port_id` bigint NOT NULL,
  `peer_port_id` bigint NOT NULL,
  `local_device_id` bigint NOT NULL,
  `peer_device_id` bigint NOT NULL,
  `connection_type` varchar(50) DEFAULT NULL,
  `vlan_id` smallint DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'active',
  `notes` text,
  `bandwidth` varchar(20) DEFAULT NULL,
  `description` varchar(200) DEFAULT NULL,
  `lag_group_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_local_port` (`local_port_id`),
  UNIQUE KEY `uq_peer_port` (`peer_port_id`),
  KEY `idx_nc_local_topology` (`local_device_id`,`peer_device_id`),
  KEY `idx_lag_group` (`lag_group_id`),
  KEY `fk_nc_peer_dev` (`peer_device_id`),
  CONSTRAINT `fk_nc_local_dev` FOREIGN KEY (`local_device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_nc_local_port` FOREIGN KEY (`local_port_id`) REFERENCES `network_ports` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_nc_peer_dev` FOREIGN KEY (`peer_device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_nc_peer_port` FOREIGN KEY (`peer_port_id`) REFERENCES `network_ports` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=32 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备间连接表(N2N)';

DROP TABLE IF EXISTS `network_ports`;
CREATE TABLE `network_ports` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '交换机设备ID',
  `port_type` varchar(50) DEFAULT NULL,
  `slot` int NOT NULL DEFAULT '-1',
  `card` int NOT NULL DEFAULT '-1',
  `port_number` int NOT NULL DEFAULT '-1',
  `port_name` varchar(100) NOT NULL COMMENT '端口名称',
  `usage_status` enum('free','occupied','disabled','error') DEFAULT 'free',
  `speed` varchar(20) DEFAULT NULL,
  `description` mediumtext,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `vlan` varchar(200) DEFAULT NULL,
  `link_status` varchar(50) DEFAULT NULL,
  `mac` varchar(17) DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `customer_id` bigint DEFAULT NULL,
  `raw_info` json DEFAULT NULL,
  `data_source` enum('manual','auto','hybrid') DEFAULT 'manual',
  `last_collected_at` datetime DEFAULT NULL,
  `lag_group_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_device_port_name` (`device_id`,`port_name`),
  KEY `idx_np_device_status_link` (`device_id`,`usage_status`,`link_status`),
  KEY `ix_np_customer_id` (`customer_id`),
  KEY `idx_np_lag_group` (`lag_group_id`),
  CONSTRAINT `fk_np_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `network_ports_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1106 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备端口表';

DROP TABLE IF EXISTS `notification_receipts`;
CREATE TABLE `notification_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `notification_id` bigint NOT NULL COMMENT '通知ID FK→notifications',
  `user_id` bigint NOT NULL COMMENT '用户ID FK→users',
  `read_at` datetime DEFAULT NULL COMMENT '已读时间(NULL=未读)',
  `delivered_channels` json DEFAULT NULL COMMENT '投递渠道(["inbox"])',
  `channel_status` json DEFAULT NULL COMMENT '各渠道实际投递结果',
  `ack_required` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否需要手动确认',
  `acked_at` datetime DEFAULT NULL COMMENT '确认时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_receipt_user_unread` (`user_id`,`read_at`),
  KEY `idx_receipt_notification` (`notification_id`),
  KEY `idx_receipt_user_notification` (`user_id`,`notification_id`),
  CONSTRAINT `fk_receipt_notification` FOREIGN KEY (`notification_id`) REFERENCES `notifications` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_receipt_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=305 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知投递回执表';

DROP TABLE IF EXISTS `notifications`;
CREATE TABLE `notifications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知类型(业务语义标识)',
  `severity` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'info' COMMENT '严重程度: info/warning/critical',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知标题',
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '通知正文',
  `payload` json DEFAULT NULL COMMENT '业务载荷(跳转用)',
  `source_module` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '来源模块(devices/switches/ip/scan)',
  `target_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '目标类型: user/role/broadcast',
  `target_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '目标标识(user_id/role_name/NULL=广播)',
  `idempotency_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '幂等键(防重复通知)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_idempotency_key` (`idempotency_key`),
  KEY `idx_notification_type` (`type`),
  KEY `idx_notification_severity` (`severity`),
  KEY `idx_notification_target` (`target_type`,`target_id`),
  KEY `idx_notification_source` (`source_module`),
  KEY `idx_notification_created` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=312 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一消息通知表';

DROP TABLE IF EXISTS `permissions`;
CREATE TABLE `permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `code` varchar(50) NOT NULL COMMENT '权限编码',
  `name` varchar(100) NOT NULL COMMENT '权限名称',
  `category` varchar(50) DEFAULT NULL COMMENT '权限分类',
  `description` mediumtext,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_permission_code` (`code`),
  KEY `idx_permission_category` (`category`)
) ENGINE=InnoDB AUTO_INCREMENT=372 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='权限信息表';

DROP TABLE IF EXISTS `role_permissions`;
CREATE TABLE `role_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `role_id` bigint NOT NULL,
  `permission_id` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_permission` (`role_id`,`permission_id`),
  KEY `idx_role_permission_permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=751 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色权限关联表';

DROP TABLE IF EXISTS `roles`;
CREATE TABLE `roles` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) NOT NULL COMMENT '角色名称',
  `display_name` varchar(100) NOT NULL COMMENT '角色显示名称',
  `description` mediumtext,
  `status` int NOT NULL,
  `data_scope` varchar(16) NOT NULL DEFAULT 'all' COMMENT '数据权限范围: all/responsible_person/room/custom',
  `data_scope_config` json DEFAULT NULL COMMENT 'data_scope 配置: room {room_ids:[...]} | custom {device_ids:[...]}',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_name` (`name`),
  KEY `idx_role_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色信息表';

DROP TABLE IF EXISTS `rooms`;
CREATE TABLE `rooms` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT '机房名称',
  `status` int NOT NULL COMMENT '状态：0-正常，1-停用',
  `location` varchar(255) DEFAULT NULL COMMENT '机房位置',
  `contact` varchar(255) DEFAULT NULL COMMENT '联系人',
  `contact_phone` varchar(50) DEFAULT NULL COMMENT '联系电话',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_jf_manager_db_name` (`name`),
  KEY `idx_room_deleted_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机房信息表';

DROP TABLE IF EXISTS `switch_credentials`;
CREATE TABLE `switch_credentials` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `ip` varchar(45) DEFAULT NULL COMMENT 'SSH管理IP',
  `port` smallint DEFAULT '22',
  `username` varchar(64) DEFAULT NULL COMMENT '登录用户名',
  `password` varchar(512) DEFAULT NULL COMMENT 'AES-256-GCM加密后密码',
  `protocol` varchar(10) DEFAULT 'ssh',
  `authentication_method` varchar(32) DEFAULT NULL,
  `device_type` varchar(20) DEFAULT NULL COMMENT '驱动类型:huawei/h3c/cisco',
  `has_ssh` tinyint(1) DEFAULT '1',
  `mac_address` varchar(17) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_switch_device` (`device_id`),
  CONSTRAINT `fk_switch_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交换机凭据';

DROP TABLE IF EXISTS `switch_port_ips`;
CREATE TABLE `switch_port_ips` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL COMMENT '交换机设备ID FK→device_manager',
  `port_id` bigint DEFAULT NULL COMMENT '端口ID FK→network_ports',
  `port_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '端口名',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'IP地址',
  `subnet_mask` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '255.255.255.0' COMMENT '子网掩码',
  `is_primary` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否为主IP',
  `vlan` int DEFAULT NULL COMMENT 'VLAN ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `ip_int` int unsigned DEFAULT NULL COMMENT 'IP整数表示(INET_ATON),用于范围查询',
  `prefix` tinyint unsigned DEFAULT NULL COMMENT '子网掩码位数(如24,从subnet_mask转换)',
  PRIMARY KEY (`id`),
  KEY `idx_spi_device` (`device_id`),
  KEY `idx_spi_port` (`port_id`),
  KEY `idx_spi_ip_int` (`ip_int`),
  CONSTRAINT `fk_spi_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`),
  CONSTRAINT `fk_spi_port` FOREIGN KEY (`port_id`) REFERENCES `network_ports` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2904 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备端口IP表';

DROP TABLE IF EXISTS `switch_routes`;
CREATE TABLE `switch_routes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `switch_id` bigint NOT NULL,
  `destination` varchar(45) NOT NULL,
  `nexthop` varchar(45) NOT NULL,
  `route_type` tinyint NOT NULL DEFAULT '0',
  `port` varchar(50) DEFAULT NULL,
  `room_id` int DEFAULT NULL,
  `network_id` bigint DEFAULT NULL,
  `customer_id` bigint DEFAULT NULL,
  `notes` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `destination_int` int unsigned DEFAULT NULL,
  `destination_prefix` tinyint unsigned DEFAULT NULL,
  `nexthop_int` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_route_switch_dest_nexthop_type` (`switch_id`,`destination`,`nexthop`,`route_type`),
  KEY `idx_route_switch_room` (`switch_id`,`room_id`),
  KEY `idx_route_dest_int_prefix` (`destination_int`,`destination_prefix`),
  KEY `fk_route_room` (`room_id`),
  KEY `fk_route_network` (`network_id`),
  KEY `fk_route_customer` (`customer_id`),
  CONSTRAINT `fk_route_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_route_network` FOREIGN KEY (`network_id`) REFERENCES `ip_networks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_route_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_route_switch` FOREIGN KEY (`switch_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3814 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `switch_status_cache`;
CREATE TABLE `switch_status_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` bigint NOT NULL,
  `device_version` varchar(255) DEFAULT NULL,
  `device_uptime` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ssc_device` (`device_id`),
  CONSTRAINT `fk_ssc_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交换机采集状态缓存';

DROP TABLE IF EXISTS `user_roles`;
CREATE TABLE `user_roles` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` bigint NOT NULL,
  `role_id` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_role` (`user_id`,`role_id`),
  KEY `idx_user_role_role_id` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户角色关联表';

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `username` varchar(20) NOT NULL COMMENT '用户名',
  `password` varchar(255) NOT NULL COMMENT '密码（加密）',
  `email` varchar(255) DEFAULT NULL COMMENT '邮箱',
  `openid` varchar(255) DEFAULT NULL COMMENT '微信OpenID',
  `name` varchar(255) NOT NULL COMMENT '真实姓名',
  `department` varchar(100) DEFAULT NULL COMMENT '所属部门',
  `contact_phone` varchar(20) DEFAULT NULL COMMENT '联系电话',
  `notification_prefs` json DEFAULT NULL COMMENT '通知偏好设置',
  `status` int NOT NULL COMMENT '状态',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_user_status_created` (`status`,`created_at`),
  KEY `idx_user_openid` (`openid`),
  KEY `idx_user_email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

DROP TABLE IF EXISTS `users_log`;
CREATE TABLE `users_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `login_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `login_type` varchar(10) DEFAULT 'web',
  `login_ip` varchar(255) DEFAULT NULL,
  `user_agent` varchar(512) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user_id_login` (`user_id`,`login_time` DESC),
  CONSTRAINT `fk_users_log_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=246 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `virtual_room_members`;
CREATE TABLE `virtual_room_members` (
  `virtual_room_id` int NOT NULL COMMENT '虚拟机房ID',
  `device_id` bigint NOT NULL COMMENT '交换机设备ID',
  `joined_at` datetime NOT NULL DEFAULT (now()) COMMENT '加入时间',
  PRIMARY KEY (`virtual_room_id`,`device_id`),
  KEY `idx_vrm_device` (`device_id`),
  CONSTRAINT `virtual_room_members_ibfk_1` FOREIGN KEY (`virtual_room_id`) REFERENCES `virtual_rooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `virtual_room_members_ibfk_2` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚拟机房成员（交换机）关联表';

DROP TABLE IF EXISTS `virtual_rooms`;
CREATE TABLE `virtual_rooms` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT '虚拟机房名称',
  `description` varchar(500) DEFAULT NULL COMMENT '描述',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  `last_scan_at` datetime DEFAULT NULL COMMENT '最近扫描完成时间',
  `last_scan_scope` varchar(32) DEFAULT NULL COMMENT '最近扫描 scope 标识',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_virtual_room_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚拟机房（逻辑扫描单元）';

DROP TABLE IF EXISTS `vlan_port_members`;
CREATE TABLE `vlan_port_members` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `vlan_id` bigint NOT NULL,
  `port_id` bigint NOT NULL,
  `port_mode` enum('access','trunk','hybrid') NOT NULL DEFAULT 'access',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_vpm_vlan_port` (`vlan_id`,`port_id`),
  KEY `idx_vpm_port` (`port_id`),
  CONSTRAINT `fk_vpm_port` FOREIGN KEY (`port_id`) REFERENCES `network_ports` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_vpm_vlan` FOREIGN KEY (`vlan_id`) REFERENCES `vlans` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=14598 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='VLAN成员端口关联表';

DROP TABLE IF EXISTS `vlans`;
CREATE TABLE `vlans` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `vlan_id` smallint unsigned NOT NULL COMMENT 'VLAN ID',
  `name` varchar(64) NOT NULL COMMENT 'VLAN名称',
  `purpose` varchar(255) DEFAULT NULL,
  `subnet_id` bigint DEFAULT NULL,
  `room_id` int DEFAULT NULL,
  `status` tinyint NOT NULL DEFAULT '1',
  `device_id` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_vlan_device` (`device_id`,`vlan_id`),
  KEY `idx_vlan_room_status` (`room_id`,`status`),
  KEY `fk_vlan_subnet` (`subnet_id`),
  CONSTRAINT `fk_vlan_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`),
  CONSTRAINT `fk_vlan_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`),
  CONSTRAINT `fk_vlan_subnet` FOREIGN KEY (`subnet_id`) REFERENCES `ip_networks` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=861 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='VLAN资源池';

DROP TABLE IF EXISTS `voice_settings`;
CREATE TABLE `voice_settings` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `key` varchar(50) NOT NULL COMMENT '配置键',
  `value` varchar(500) DEFAULT NULL COMMENT '配置值',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_voice_setting_key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='语音通知配置表';

DROP TABLE IF EXISTS `webhook_configs`;
CREATE TABLE `webhook_configs` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置名称',
  `channel` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '渠道标识: wechat_work/feishu/custom',
  `url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Webhook URL',
  `secret` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '签名密钥',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `message_template` json DEFAULT NULL COMMENT '消息模板',
  `applicable_types` json DEFAULT NULL COMMENT '适用通知类型列表',
  `applicable_severities` json DEFAULT NULL COMMENT '适用严重程度',
  `created_by` bigint DEFAULT NULL COMMENT '创建者ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_webhook_channel` (`channel`),
  KEY `idx_webhook_enabled` (`enabled`),
  KEY `fk_webhook_created_by` (`created_by`),
  CONSTRAINT `fk_webhook_created_by` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Webhook 渠道配置表';

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_addr_before_insert`;;
CREATE TRIGGER `trg_ip_addr_before_insert` BEFORE INSERT ON `ip_addresses` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_addr_before_update`;;
CREATE TRIGGER `trg_ip_addr_before_update` BEFORE UPDATE ON `ip_addresses` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_ban_before_insert`;;
CREATE TRIGGER `trg_ip_ban_before_insert` BEFORE INSERT ON `ip_ban_records` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_ban_before_update`;;
CREATE TRIGGER `trg_ip_ban_before_update` BEFORE UPDATE ON `ip_ban_records` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_net_before_insert`;;
CREATE TRIGGER `trg_ip_net_before_insert` BEFORE INSERT ON `ip_networks` FOR EACH ROW BEGIN
    
    SET NEW.network_int = INET_ATON(SUBSTRING_INDEX(NEW.network, '/', 1));
    
    SET NEW.prefix = CAST(SUBSTRING_INDEX(NEW.network, '/', -1) AS SIGNED);
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_net_before_update`;;
CREATE TRIGGER `trg_ip_net_before_update` BEFORE UPDATE ON `ip_networks` FOR EACH ROW BEGIN
    SET NEW.network_int = INET_ATON(SUBSTRING_INDEX(NEW.network, '/', 1));
    SET NEW.prefix = CAST(SUBSTRING_INDEX(NEW.network, '/', -1) AS SIGNED);
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_switch_before_insert`;;
CREATE TRIGGER `trg_ip_switch_before_insert` BEFORE INSERT ON `ip_switch_info` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_ip_switch_before_update`;;
CREATE TRIGGER `trg_ip_switch_before_update` BEFORE UPDATE ON `ip_switch_info` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_np_after_delete`;;
CREATE TRIGGER `trg_np_after_delete` AFTER DELETE ON `network_ports` FOR EACH ROW BEGIN
    IF OLD.lag_group_id IS NOT NULL THEN
        UPDATE link_aggregation_groups
        SET member_count = GREATEST(member_count - 1, 0)
        WHERE id = OLD.lag_group_id;
    END IF;
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_np_after_insert`;;
CREATE TRIGGER `trg_np_after_insert` AFTER INSERT ON `network_ports` FOR EACH ROW BEGIN
    IF NEW.lag_group_id IS NOT NULL THEN
        UPDATE link_aggregation_groups
        SET member_count = member_count + 1
        WHERE id = NEW.lag_group_id;
    END IF;
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_np_after_update`;;
CREATE TRIGGER `trg_np_after_update` AFTER UPDATE ON `network_ports` FOR EACH ROW BEGIN
    
    IF OLD.lag_group_id IS NOT NULL AND OLD.lag_group_id <> NEW.lag_group_id THEN
        UPDATE link_aggregation_groups
        SET member_count = GREATEST(member_count - 1, 0)
        WHERE id = OLD.lag_group_id;
    END IF;

    
    IF NEW.lag_group_id IS NOT NULL AND NEW.lag_group_id <> OLD.lag_group_id THEN
        UPDATE link_aggregation_groups
        SET member_count = member_count + 1
        WHERE id = NEW.lag_group_id;
    END IF;
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_spi_before_insert`;;
CREATE TRIGGER `trg_spi_before_insert` BEFORE INSERT ON `switch_port_ips` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_spi_before_update`;;
CREATE TRIGGER `trg_spi_before_update` BEFORE UPDATE ON `switch_port_ips` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address);;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_switch_route_before_insert`;;
CREATE TRIGGER `trg_switch_route_before_insert` BEFORE INSERT ON `switch_routes` FOR EACH ROW BEGIN
    SET NEW.destination_int = INET_ATON(SUBSTRING_INDEX(NEW.destination, '/', 1));
    SET NEW.destination_prefix = CAST(SUBSTRING_INDEX(NEW.destination, '/', -1) AS SIGNED);
    SET NEW.nexthop_int = INET_ATON(NEW.nexthop);
END;;
DELIMITER ;

DELIMITER ;;
DROP TRIGGER IF EXISTS `trg_switch_route_before_update`;;
CREATE TRIGGER `trg_switch_route_before_update` BEFORE UPDATE ON `switch_routes` FOR EACH ROW BEGIN
    SET NEW.destination_int = INET_ATON(SUBSTRING_INDEX(NEW.destination, '/', 1));
    SET NEW.destination_prefix = CAST(SUBSTRING_INDEX(NEW.destination, '/', -1) AS SIGNED);
    SET NEW.nexthop_int = INET_ATON(NEW.nexthop);
END;;
DELIMITER ;

SET FOREIGN_KEY_CHECKS = 1;
