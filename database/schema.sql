-- MySQL dump 10.13  Distrib 8.4.9, for Linux (x86_64)
--
-- Host: localhost    Database: ip_manager
-- ------------------------------------------------------
-- Server version	8.4.9

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  KEY `idx_audit_resource_id` (`resource`,`resource_id`),
  KEY `idx_audit_created_action` (`created_at` DESC,`action`),
  KEY `idx_audit_resource_time` (`resource`,`resource_id`,`created_at`),
  KEY `idx_functional_detail_module` ((cast(json_unquote(json_extract(`detail`,_utf8mb4'$.module')) as char(32) charset utf8mb4)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作审计日志';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cabinets`
--

DROP TABLE IF EXISTS `cabinets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间(NULL=未删除)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cabinet_room_number` (`room_id`,`cabinet_number`),
  KEY `idx_cabinet_deleted_room_status` (`deleted_at`,`room_id`,`status`),
  KEY `idx_cabinet_customer` (`customer_id`),
  CONSTRAINT `fk_cabinet_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_cabinet_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机柜信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `component_templates`
--

DROP TABLE IF EXISTS `component_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=207 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='配件模板';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_asset`
--

DROP TABLE IF EXISTS `device_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备资产台账表（1:1扩展）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_config_backups`
--

DROP TABLE IF EXISTS `device_config_backups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_config_changes`
--

DROP TABLE IF EXISTS `device_config_changes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_connections`
--

DROP TABLE IF EXISTS `device_connections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_hardware`
--

DROP TABLE IF EXISTS `device_hardware`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device_hardware` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `device_id` bigint NOT NULL COMMENT '关联设备ID（唯一）',
  `cpu` varchar(100) DEFAULT NULL COMMENT 'CPU型号',
  `cpu_template_id` bigint DEFAULT NULL,
  `cpu_way` tinyint DEFAULT NULL,
  `cpu_cores` smallint DEFAULT NULL,
  `memory` varchar(100) DEFAULT NULL COMMENT '内存配置描述',
  `memory_template_id` bigint DEFAULT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备硬件规格表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_nics_port`
--

DROP TABLE IF EXISTS `device_nics_port`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=216 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备网卡端口表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_server_ext`
--

DROP TABLE IF EXISTS `device_server_ext`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_storage`
--

DROP TABLE IF EXISTS `device_storage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=77 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_switch_ext`
--

DROP TABLE IF EXISTS `device_switch_ext`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device_switch_ext` (
  `device_id` bigint NOT NULL COMMENT '设备ID(PK+FK→devices.id)',
  `switch_role` smallint DEFAULT NULL COMMENT '交换机角色: 0=核心, 1=接入, NULL=非交换机',
  `layer` smallint DEFAULT NULL COMMENT '网络层级',
  `uplink_device_id` bigint DEFAULT NULL COMMENT '上行设备ID',
  `uplink_port_ids` json DEFAULT NULL COMMENT '上行端口ID数组(引用network_ports.id)',
  `core_device_id` bigint DEFAULT NULL COMMENT '核心交换机ID',
  `port_num` smallint DEFAULT NULL COMMENT '端口数量',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `devices`
--

DROP TABLE IF EXISTS `devices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  CONSTRAINT `fk_device_cabinet` FOREIGN KEY (`cabinet_id`) REFERENCES `cabinets` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_device_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_device_responsible_person` FOREIGN KEY (`responsible_person`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=90 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_addresses`
--

DROP TABLE IF EXISTS `ip_addresses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ip_addresses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(45) NOT NULL COMMENT 'IP地址',
  `customer_id` bigint DEFAULT NULL COMMENT '客户ID',
  `status` tinyint NOT NULL DEFAULT '3' COMMENT 'IP状态: 0=活跃 1=非活跃 2=封禁 3=未使用',
  `notes` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `room_id` int DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间',
  `ip_int` int unsigned DEFAULT NULL COMMENT 'IP整数表示(INET_ATON),用于范围查询',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_ip_room` (`ip_address`,`room_id`),
  KEY `idx_ip_deleted_room_status` (`deleted_at`,`room_id`,`status`),
  KEY `idx_ip_int_status` (`ip_int`,`status`),
  KEY `fk_customer` (`customer_id`),
  KEY `ip_addresses_ibfk_1` (`room_id`),
  CONSTRAINT `fk_ip_manager_customer_id` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `ip_addresses_ibfk_1` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10120 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ip详情';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_addr_before_insert` BEFORE INSERT ON `ip_addresses` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_addr_before_update` BEFORE UPDATE ON `ip_addresses` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `ip_allocation_logs`
--

DROP TABLE IF EXISTS `ip_allocation_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  KEY `idx_alloc_ip` (`ip_address`,`room_id`),
  KEY `idx_alloc_created_operator` (`created_at` DESC,`operator_id`),
  KEY `fk_alloc_operator` (`operator_id`),
  KEY `fk_alloc_room` (`room_id`),
  KEY `idx_alloc_ip_time` (`ip_address`,`room_id`,`created_at`),
  CONSTRAINT `fk_alloc_operator` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`),
  CONSTRAINT `fk_alloc_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP分配历史日志';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_ban_records`
--

DROP TABLE IF EXISTS `ip_ban_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP封禁信息';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_ban_before_insert` BEFORE INSERT ON `ip_ban_records` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_ban_before_update` BEFORE UPDATE ON `ip_ban_records` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `ip_networks`
--

DROP TABLE IF EXISTS `ip_networks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=296 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP网段规划';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_net_before_insert` BEFORE INSERT ON `ip_networks` FOR EACH ROW BEGIN
    
    SET NEW.network_int = INET_ATON(SUBSTRING_INDEX(NEW.network, '/', 1));
    
    SET NEW.prefix = CAST(SUBSTRING_INDEX(NEW.network, '/', -1) AS SIGNED);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_net_before_update` BEFORE UPDATE ON `ip_networks` FOR EACH ROW BEGIN
    SET NEW.network_int = INET_ATON(SUBSTRING_INDEX(NEW.network, '/', 1));
    SET NEW.prefix = CAST(SUBSTRING_INDEX(NEW.network, '/', -1) AS SIGNED);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `ip_switch_info`
--

DROP TABLE IF EXISTS `ip_switch_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=1529 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP交换机定位信息';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_switch_before_insert` BEFORE INSERT ON `ip_switch_info` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_ip_switch_before_update` BEFORE UPDATE ON `ip_switch_info` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `link_aggregation_groups`
--

DROP TABLE IF EXISTS `link_aggregation_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='链路聚合组';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `mail_settings`
--

DROP TABLE IF EXISTS `mail_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mail_settings` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `key` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置键',
  `value` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '配置值',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_mail_setting_key` (`key`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件服务器配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `network_connections`
--

DROP TABLE IF EXISTS `network_connections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备间连接表(N2N)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `network_ports`
--

DROP TABLE IF EXISTS `network_ports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=556 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备端口表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_np_after_insert` AFTER INSERT ON `network_ports` FOR EACH ROW BEGIN
    IF NEW.lag_group_id IS NOT NULL THEN
        UPDATE link_aggregation_groups
        SET member_count = member_count + 1
        WHERE id = NEW.lag_group_id;
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_np_after_update` AFTER UPDATE ON `network_ports` FOR EACH ROW BEGIN
    
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
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_np_after_delete` AFTER DELETE ON `network_ports` FOR EACH ROW BEGIN
    IF OLD.lag_group_id IS NOT NULL THEN
        UPDATE link_aggregation_groups
        SET member_count = GREATEST(member_count - 1, 0)
        WHERE id = OLD.lag_group_id;
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `notification_receipts`
--

DROP TABLE IF EXISTS `notification_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知投递回执表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notifications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知类型(业务语义标识)',
  `severity` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'info' COMMENT '严重程度: info/warning/critical',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知标题',
  `content` text COLLATE utf8mb4_unicode_ci COMMENT '通知正文',
  `payload` json DEFAULT NULL COMMENT '业务载荷(跳转用)',
  `source_module` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '来源模块(devices/switches/ip/scan)',
  `target_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '目标类型: user/role/broadcast',
  `target_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '目标标识(user_id/role_name/NULL=广播)',
  `idempotency_key` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '幂等键(防重复通知)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_idempotency_key` (`idempotency_key`),
  KEY `idx_notification_type` (`type`),
  KEY `idx_notification_severity` (`severity`),
  KEY `idx_notification_target` (`target_type`,`target_id`),
  KEY `idx_notification_source` (`source_module`),
  KEY `idx_notification_created` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一消息通知表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='权限信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=325 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色权限关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) NOT NULL COMMENT '角色名称',
  `display_name` varchar(100) NOT NULL COMMENT '角色显示名称',
  `description` mediumtext,
  `status` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_name` (`name`),
  KEY `idx_role_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `rooms`
--

DROP TABLE IF EXISTS `rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rooms` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT '机房名称',
  `status` int NOT NULL COMMENT '状态：0-正常，1-停用',
  `location` varchar(255) DEFAULT NULL COMMENT '机房位置',
  `contact` varchar(255) DEFAULT NULL COMMENT '联系人',
  `contact_phone` varchar(50) DEFAULT NULL COMMENT '联系电话',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间(NULL=未删除)',
  PRIMARY KEY (`id`),
  KEY `ix_jf_manager_db_name` (`name`),
  KEY `idx_room_deleted_status` (`deleted_at`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机房信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_credentials`
--

DROP TABLE IF EXISTS `switch_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交换机凭据';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_port_ips`
--

DROP TABLE IF EXISTS `switch_port_ips`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=1466 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络设备端口IP表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_spi_before_insert` BEFORE INSERT ON `switch_port_ips` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_spi_before_update` BEFORE UPDATE ON `switch_port_ips` FOR EACH ROW SET NEW.ip_int = INET_ATON(NEW.ip_address) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `switch_routes`
--

DROP TABLE IF EXISTS `switch_routes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=2180 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_switch_route_before_insert` BEFORE INSERT ON `switch_routes` FOR EACH ROW BEGIN
    SET NEW.destination_int = INET_ATON(SUBSTRING_INDEX(NEW.destination, '/', 1));
    SET NEW.destination_prefix = CAST(SUBSTRING_INDEX(NEW.destination, '/', -1) AS SIGNED);
    SET NEW.nexthop_int = INET_ATON(NEW.nexthop);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=CURRENT_USER*/ /*!50003 TRIGGER `trg_switch_route_before_update` BEFORE UPDATE ON `switch_routes` FOR EACH ROW BEGIN
    SET NEW.destination_int = INET_ATON(SUBSTRING_INDEX(NEW.destination, '/', 1));
    SET NEW.destination_prefix = CAST(SUBSTRING_INDEX(NEW.destination, '/', -1) AS SIGNED);
    SET NEW.nexthop_int = INET_ATON(NEW.nexthop);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `switch_status_cache`
--

DROP TABLE IF EXISTS `switch_status_cache`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交换机采集状态缓存';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户角色关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users_log`
--

DROP TABLE IF EXISTS `users_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `virtual_room_members`
--

DROP TABLE IF EXISTS `virtual_room_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `virtual_room_members` (
  `virtual_room_id` int NOT NULL COMMENT '虚拟机房ID',
  `device_id` bigint NOT NULL COMMENT '交换机设备ID',
  `joined_at` datetime NOT NULL DEFAULT (now()) COMMENT '加入时间',
  PRIMARY KEY (`virtual_room_id`,`device_id`),
  UNIQUE KEY `uq_vr_member` (`virtual_room_id`,`device_id`),
  KEY `idx_vrm_device` (`device_id`),
  CONSTRAINT `virtual_room_members_ibfk_1` FOREIGN KEY (`virtual_room_id`) REFERENCES `virtual_rooms` (`id`) ON DELETE CASCADE,
  CONSTRAINT `virtual_room_members_ibfk_2` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚拟机房成员（交换机）关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `virtual_rooms`
--

DROP TABLE IF EXISTS `virtual_rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `virtual_rooms` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT '虚拟机房名称',
  `description` varchar(500) DEFAULT NULL COMMENT '描述',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  `last_scan_at` datetime DEFAULT NULL COMMENT '最近扫描完成时间',
  `last_scan_scope` varchar(32) DEFAULT NULL COMMENT '最近扫描 scope 标识',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `uq_virtual_room_name` (`name`),
  KEY `idx_virtual_room_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚拟机房（逻辑扫描单元）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vlan_port_members`
--

DROP TABLE IF EXISTS `vlan_port_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=6281 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='VLAN成员端口关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vlans`
--

DROP TABLE IF EXISTS `vlans`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=175 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='VLAN资源池';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `webhook_configs`
--

DROP TABLE IF EXISTS `webhook_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_configs` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '配置名称',
  `channel` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '渠道标识: wechat_work/feishu/custom',
  `url` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Webhook URL',
  `secret` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '签名密钥',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Webhook 渠道配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-07-08 10:30:07
