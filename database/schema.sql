-- MySQL schema dump (generated from SQLAlchemy models)
-- Host: localhost    Database: ip_manager
-- ------------------------------------------------------
-- Server version	8.4

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
CREATE TABLE audit_logs (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	user_id BIGINT COMMENT '操作人ID(逻辑关联users.id,不加FK避免级联影响日志保留)', 
	action VARCHAR(64) NOT NULL COMMENT '操作类型(如 device.create, ip.ban)', 
	resource VARCHAR(64) NOT NULL COMMENT '资源类型(如 device, ip, switch)', 
	resource_id BIGINT COMMENT '资源ID', 
	detail JSON COMMENT '操作详情', 
	ip_address VARCHAR(45) COMMENT '客户端IP', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='操作审计日志';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE customers (
	customer_name VARCHAR(255) NOT NULL COMMENT '客户名称', 
	customer_status SMALLINT NOT NULL COMMENT '客户状态(0-活跃 1-停用 2-待审核 3-终止) (CustomerStatus)', 
	contact_person VARCHAR(50) COMMENT '联系人', 
	contact_phone VARCHAR(20) COMMENT '联系电话', 
	email VARCHAR(100) COMMENT '联系邮箱', 
	address VARCHAR(200) COMMENT '客户地址', 
	notes TEXT COMMENT '备注信息', 
	deleted_at DATETIME COMMENT '软删除时间(NULL=未删除)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (customer_name)
)COMMENT='客户信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_metric_timeseries`
--

DROP TABLE IF EXISTS `device_metric_timeseries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_metric_timeseries (
	id BIGINT NOT NULL COMMENT '主键ID（复合主键第一部分，配合分区键 collected_at）' AUTO_INCREMENT, 
	device_id BIGINT NOT NULL COMMENT '关联设备ID（分区表不支持外键，设备删除由应用层负责清理）', 
	metric_key VARCHAR(64) NOT NULL COMMENT '指标 key，如 cpu_usage / temperature / if_status', 
	index_key VARCHAR(128) NOT NULL COMMENT '指标实例索引，如端口号 ifIndex；无索引时为空串' DEFAULT '', 
	value VARCHAR(255) COMMENT '指标值（字符串存储，前端按 metric_type 解析为数值/状态）', 
	severity VARCHAR(20) COMMENT '告警级别 ok/warn/crit（阈值判定结果）', 
	breached BOOL NOT NULL COMMENT '本次采集是否触发阈值告警' DEFAULT '0', 
	collected_at DATETIME NOT NULL COMMENT '采集时间（=趋势横轴，分区键）', 
	created_at DATETIME NOT NULL COMMENT '写入时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='设备指标值历史时序分区表（每次采集每指标一行，供趋势图，保留90天）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_monitor_probe_events`
--

DROP TABLE IF EXISTS `device_monitor_probe_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_monitor_probe_events (
	id BIGINT NOT NULL COMMENT '主键ID（复合主键第一部分，配合分区键 probed_at）' AUTO_INCREMENT, 
	device_id BIGINT NOT NULL COMMENT '关联设备ID（分区表不支持外键，设备删除由应用层负责清理，见 MEMORY）', 
	protocol VARCHAR(20) NOT NULL COMMENT 'snmp/redfish/ipmi/zabbix', 
	reachable BOOL NOT NULL COMMENT '本次是否可达', 
	latency_ms INTEGER COMMENT '本次探测耗时（毫秒）', 
	consecutive_failures INTEGER NOT NULL COMMENT '探测时连续失败次数（抖动抑制/阈值判定）' DEFAULT '0', 
	episode INTEGER NOT NULL COMMENT '不可达周期序号（每进入一次不可达 +1）' DEFAULT '0', 
	is_alert BOOL NOT NULL COMMENT '本次探测是否触发告警（不可达/恢复）' DEFAULT '0', 
	error TEXT COMMENT '不可达时的错误码/信息', 
	extra JSON COMMENT '协议特有附加信息（精简快照）', 
	probed_at DATETIME NOT NULL COMMENT '探测时间（=趋势横轴，分区键）', 
	created_at DATETIME NOT NULL COMMENT '写入时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='设备探测历史时序分区表（每次探测一行，供趋势图/历史明细，保留90天）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `mail_settings`
--

DROP TABLE IF EXISTS `mail_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE mail_settings (
	`key` VARCHAR(50) NOT NULL COMMENT '配置键', 
	value VARCHAR(500) COMMENT '配置值', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_mail_setting_key UNIQUE (`key`)
)COMMENT='邮件服务器配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_credentials`
--

DROP TABLE IF EXISTS `monitor_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_credentials (
	protocol VARCHAR(20) NOT NULL COMMENT 'snmp/redfish/ipmi', 
	name VARCHAR(128) NOT NULL COMMENT '同协议下唯一的可读标签，如''机房A SNMP只读团体字''（非机密）', 
	encrypted_payload TEXT NOT NULL COMMENT 'AES-256-GCM 加密的凭据 JSON', 
	payload_hash VARCHAR(64) COMMENT 'payload 规范 JSON 的 SHA-256 十六进制（用于同明文凭据去重复用；旧行密文不可逆留空）', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT '1', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_mc_protocol_hash UNIQUE (protocol, payload_hash), 
	CONSTRAINT uk_mc_protocol_name UNIQUE (protocol, name)
)COMMENT='设备监控共享凭据（AES-256-GCM加密）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_device_type_recommends`
--

DROP TABLE IF EXISTS `monitor_device_type_recommends`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_device_type_recommends (
	device_type VARCHAR(16) NOT NULL COMMENT '设备类型 network/server/other', 
	categories JSON NOT NULL COMMENT '推荐的 category 列表，如 ["temperature","fan","power_supply"]', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_device_type_recommend UNIQUE (device_type)
)COMMENT='设备类型推荐配置，定义每种设备类型推荐哪些 category';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_dynamic_config`
--

DROP TABLE IF EXISTS `monitor_dynamic_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_dynamic_config (
	config_key VARCHAR(64) NOT NULL COMMENT '配置键（= 现有 _cfg() 调用点使用的大写 MONITOR_* key）', 
	config_value TEXT NOT NULL COMMENT '配置值（字符串化存储，按 value_type 解析）', 
	value_type VARCHAR(16) NOT NULL COMMENT 'string/int/float/bool/json' DEFAULT 'string', 
	description VARCHAR(255) COMMENT '配置说明（前端展示）' DEFAULT '', 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	updated_by VARCHAR(64) COMMENT '操作人（审计）' DEFAULT '', 
	PRIMARY KEY (config_key)
);
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_metric_template_groups`
--

DROP TABLE IF EXISTS `monitor_metric_template_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_metric_template_groups (
	name VARCHAR(64) NOT NULL COMMENT '组名（运维可读），如 ''华为网络设备核心指标''', 
	device_type VARCHAR(16) NOT NULL COMMENT '适用设备类型 network / server / other；组内模板必须一致', 
	source VARCHAR(16) NOT NULL COMMENT '采集来源 snmp / ipmi / zabbix；组内模板必须一致', 
	vendor VARCHAR(32) COMMENT '厂家约束（可空）；声明时组内模板 vendor 需匹配', 
	display_order INTEGER NOT NULL COMMENT '展示排序（升序），同 device_type+source 内排序', 
	enabled BOOL NOT NULL COMMENT '是否启用', 
	description VARCHAR(255) COMMENT '组说明', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_mmtg_name_devtype_source UNIQUE (name, device_type, source)
)COMMENT='监控指标模板组（运维自定义分组，约束同 device_type+source）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_metric_templates`
--

DROP TABLE IF EXISTS `monitor_metric_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_metric_templates (
	metric_key VARCHAR(64) NOT NULL COMMENT '指标标识，与 monitor_oid_category_rules.category 对齐：temperature / fan / if_status / cpu_usage / power_supply / memory / disk_failure / raid_failure', 
	category VARCHAR(32) COMMENT 'OID 分类标识，关联 monitor_oid_category_rules.category；MIB 扫描导入时自动填充，用于桥接 OID 规则与指标模板', 
	display_name VARCHAR(64) COMMENT '中文显示名（运维视角），表格优先展示；为空时回退 metric_key', 
	device_type VARCHAR(16) NOT NULL COMMENT '适用设备类型 network / server / other', 
	source VARCHAR(16) NOT NULL COMMENT '采集来源 snmp / ipmi / zabbix', 
	vendor VARCHAR(32) COMMENT '厂家约束（enterprise 号），如 2011=华为 / 25506=H3C / 9=思科；声明时仅匹配同厂商设备，模板组校验时与 device_type + source 共同约束', 
	mib VARCHAR(64) COMMENT 'MIB 名称，如 IF-MIB / ENTITY-SENSOR-MIB；IPMI/Zabbix 来源置空', 
	oid_symbol VARCHAR(128) COMMENT 'MIB 符号名，如 ifOperStatus / entPhySensorValue；IPMI/Zabbix 来源置空', 
	oid VARCHAR(128) COMMENT '完整数字 OID，如 1.3.6.1.2.1.2.2.1.7；与 oid_symbol 互补，MIB 扫描导入时承接数字 OID', 
	zabbix_item_key VARCHAR(128) COMMENT 'Zabbix item key，如 system.cpu.util / vm.memory.size[pavailable]；source=zabbix 时必填，其他来源置空', 
	index_kind VARCHAR(32) COMMENT '索引维度：ifIndex（按端口）/ 无索引（NULL）', 
	metric_type VARCHAR(16) NOT NULL COMMENT 'gauge / counter / state / event', 
	unit VARCHAR(16) COMMENT '单位，如 Celsius / bps / %%', 
	poll_interval INTEGER NOT NULL COMMENT '采集频率（秒），默认与统一轮询频率一致', 
	threshold JSON COMMENT '告警阈值（JSON）', 
	severity_default VARCHAR(16) COMMENT '默认告警级别 warn / crit，未配置阈值时回退使用', 
	enabled BOOL NOT NULL COMMENT '是否启用', 
	description VARCHAR(255) COMMENT '指标说明（运维视角）', 
	runbook_url VARCHAR(512) COMMENT '处置预案 URL（内部 wiki / 文档链接），告警详情展示', 
	runbook_title VARCHAR(128) COMMENT '处置预案标题（runbook_url 的显示文本）', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='监控指标模板，驱动 SNMP/IPMI 指标采集';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_oid_category_rules`
--

DROP TABLE IF EXISTS `monitor_oid_category_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_oid_category_rules (
	prefix VARCHAR(128) NOT NULL COMMENT 'OID 前缀，点分隔符锚定匹配（oid==prefix 或 oid.startswith(prefix+''.''）', 
	category VARCHAR(32) NOT NULL COMMENT '类别标识，如 temperature / fan / if_status', 
	label VARCHAR(64) COMMENT '人类可读类别名，如 温度探头', 
	device_type VARCHAR(16) COMMENT '适用设备类型 network/server/other；NULL=全适用', 
	vendor_id VARCHAR(32) COMMENT '厂商 enterprise 号（如 674=DELL）；NULL=通用规则', 
	priority INTEGER NOT NULL COMMENT '优先级，高优先先匹配；厂商特定规则用 100，通用用 10', 
	enabled BOOL NOT NULL COMMENT '是否启用', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='OID 分类规则，探测时按前缀打 category 标签';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_silence_rule`
--

DROP TABLE IF EXISTS `monitor_silence_rule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_silence_rule (
	name VARCHAR(128) NOT NULL COMMENT '规则名称', 
	device_ids JSON COMMENT '静默设备 ID 列表（null=全部设备）', 
	alert_types JSON COMMENT '静默告警类型列表（null=全部类型）', 
	silence_from DATETIME NOT NULL COMMENT '静默开始时间', 
	silence_until DATETIME NOT NULL COMMENT '静默结束时间', 
	reason VARCHAR(255) COMMENT '静默原因', 
	created_by VARCHAR(64) COMMENT '创建人用户名', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT 1, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='监控告警静默规则（G4.1，时间窗口内匹配告警不入箱）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_sla_target`
--

DROP TABLE IF EXISTS `monitor_sla_target`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_sla_target (
	name VARCHAR(128) NOT NULL COMMENT 'SLA 目标名称', 
	target_device_ids JSON NOT NULL COMMENT '目标设备 ID 列表', 
	target_ratio FLOAT NOT NULL COMMENT '可用率目标（0~1，如 0.99=99%%）', 
	window_days INTEGER NOT NULL COMMENT '评估窗口（天）' DEFAULT 30, 
	description VARCHAR(255) COMMENT 'SLA 描述', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT 1, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='SLA/SLO 监控目标（P2-13，基于可达率聚合计算达成度）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_vendor_brands`
--

DROP TABLE IF EXISTS `monitor_vendor_brands`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_vendor_brands (
	enterprise_no VARCHAR(32) NOT NULL COMMENT 'SNMP enterprise 号（如 674=DELL），对应 OID 规则的 vendor_id', 
	brand_name VARCHAR(64) NOT NULL COMMENT '品牌全称（英文），如 Dell EMC / Cisco', 
	label VARCHAR(64) NOT NULL COMMENT '显示名称（含设备类别后缀），如 DELL（服务器） / Cisco（网络）', 
	device_type VARCHAR(16) NOT NULL COMMENT '适用设备类型 network/server/storage/other', 
	enabled BOOL NOT NULL COMMENT '是否启用', 
	sort_order INTEGER NOT NULL COMMENT '排序权重，小的在前', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='厂商品牌，enterprise 号 → 品牌名称映射';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE notifications (
	type VARCHAR(100) NOT NULL COMMENT '通知类型', 
	severity VARCHAR(20) NOT NULL COMMENT '严重程度' DEFAULT 'info', 
	title VARCHAR(255) NOT NULL COMMENT '通知标题', 
	content TEXT COMMENT '通知正文', 
	payload JSON COMMENT '业务载荷', 
	source_module VARCHAR(50) COMMENT '来源模块', 
	target_type VARCHAR(20) NOT NULL COMMENT '目标类型(user/role/broadcast)', 
	target_id VARCHAR(100) COMMENT '目标标识', 
	idempotency_key VARCHAR(255) COMMENT '幂等键', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (idempotency_key)
)COMMENT='统一消息通知表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE permissions (
	code VARCHAR(50) NOT NULL COMMENT '权限编码', 
	name VARCHAR(100) NOT NULL COMMENT '权限名称', 
	category VARCHAR(50) COMMENT '权限分类', 
	description TEXT COMMENT '权限描述', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_permission_code UNIQUE (code)
)COMMENT='权限信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE roles (
	name VARCHAR(50) NOT NULL COMMENT '角色名称', 
	display_name VARCHAR(100) NOT NULL COMMENT '角色显示名称', 
	description TEXT COMMENT '角色描述', 
	status INTEGER NOT NULL COMMENT '状态', 
	data_scope VARCHAR(16) NOT NULL COMMENT '数据权限范围: all/responsible_person/room/custom' DEFAULT 'all', 
	data_scope_config JSON COMMENT 'data_scope 配置: room 模式 {room_ids:[...]} | custom 模式 {device_ids:[...]}', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_role_name UNIQUE (name)
)COMMENT='角色信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `rooms`
--

DROP TABLE IF EXISTS `rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE rooms (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	name VARCHAR(255) NOT NULL COMMENT '机房名称', 
	status INTEGER NOT NULL COMMENT '状态：0-正常，1-停用 (RoomStatus)', 
	location VARCHAR(255) COMMENT '机房位置', 
	contact VARCHAR(255) COMMENT '联系人', 
	contact_phone VARCHAR(50) COMMENT '联系电话', 
	deleted_at DATETIME COMMENT '软删除时间(NULL=未删除)', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id)
)COMMENT='机房信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE users (
	username VARCHAR(20) NOT NULL COMMENT '用户名', 
	password VARCHAR(255) NOT NULL COMMENT '密码（加密）', 
	email VARCHAR(255) COMMENT '邮箱', 
	openid VARCHAR(255) COMMENT '微信OpenID', 
	name VARCHAR(255) NOT NULL COMMENT '真实姓名', 
	department VARCHAR(100) COMMENT '所属部门', 
	contact_phone VARCHAR(20) COMMENT '联系电话', 
	notification_prefs JSON COMMENT '通知偏好设置', 
	status INTEGER NOT NULL COMMENT '状态', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (username)
)COMMENT='用户信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `virtual_rooms`
--

DROP TABLE IF EXISTS `virtual_rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE virtual_rooms (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	name VARCHAR(255) NOT NULL COMMENT '虚拟机房名称', 
	description VARCHAR(500) COMMENT '描述', 
	last_scan_at DATETIME COMMENT '最近扫描完成时间', 
	last_scan_scope VARCHAR(32) COMMENT '最近扫描 scope 标识', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (name)
)COMMENT='虚拟机房（逻辑扫描单元）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `voice_settings`
--

DROP TABLE IF EXISTS `voice_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE voice_settings (
	`key` VARCHAR(50) NOT NULL COMMENT '配置键', 
	value VARCHAR(500) COMMENT '配置值', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_voice_setting_key UNIQUE (`key`)
)COMMENT='语音通知配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_conversations`
--

DROP TABLE IF EXISTS `ai_conversations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ai_conversations (
	user_id BIGINT NOT NULL COMMENT '用户ID（FK→users.id，用户删除时级联清理其对话历史）', 
	scenario VARCHAR(50) NOT NULL COMMENT '场景: chat/alert/nlq/rag/inspection', 
	`role` VARCHAR(20) NOT NULL COMMENT 'user/assistant', 
	content TEXT NOT NULL COMMENT '消息内容', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)COMMENT='AI 对话历史';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cabinets`
--

DROP TABLE IF EXISTS `cabinets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE cabinets (
	cabinet_number VARCHAR(255) NOT NULL COMMENT '机柜编号', 
	room_id INTEGER NOT NULL COMMENT '所属机房ID', 
	location VARCHAR(255) COMMENT '具体位置', 
	`row` INTEGER COMMENT '行号（机房平面图纵坐标，从1开始）', 
	col INTEGER COMMENT '列号（机房平面图横坐标，从1开始）', 
	total_u INTEGER NOT NULL COMMENT '总U位数', 
	used_u INTEGER NOT NULL COMMENT '已用U位数（冗余字段,由update_usage维护,可从devices聚合）', 
	total_power INTEGER COMMENT '电力容量(W)', 
	used_power INTEGER NOT NULL COMMENT '已用功率(W)（冗余字段,由update_usage维护,可从devices聚合）', 
	max_weight FLOAT COMMENT '最大承重(KG)', 
	status INTEGER NOT NULL COMMENT '状态: 0-禁用, 1-可用, 2-使用中, 3-维护中, 4-已预留 (CabinetStatus)', 
	customer_id BIGINT COMMENT '客户ID', 
	notes TEXT COMMENT '备注信息', 
	deleted_at DATETIME COMMENT '软删除时间(NULL=未删除)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_cabinet_room_number UNIQUE (room_id, cabinet_number), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)COMMENT='机柜信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `component_templates`
--

DROP TABLE IF EXISTS `component_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE component_templates (
	category VARCHAR(20) NOT NULL COMMENT '配件类别: cpu/memory/disk/nic/gpu', 
	scope ENUM('global','customer') NOT NULL COMMENT '模板作用域: global=公共模板, customer=客户专属模板', 
	customer_id BIGINT COMMENT '客户ID，scope=customer时必填', 
	brand VARCHAR(100) COMMENT '品牌', 
	model VARCHAR(100) NOT NULL COMMENT '型号', 
	spec JSON COMMENT '规格详情(JSON)', 
	is_active BOOL NOT NULL COMMENT '是否启用', 
	sort_order SMALLINT NOT NULL COMMENT '排序权重(小=靠前)', 
	remark VARCHAR(200) COMMENT '备注', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ct_category_customer_model UNIQUE (category, customer_id, model), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL
)COMMENT='配件模板(预定义CPU/内存/硬盘/网卡规格)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `customer_termination_archive`
--

DROP TABLE IF EXISTS `customer_termination_archive`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE customer_termination_archive (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL COMMENT '客户ID', 
	summary_json JSON NOT NULL COMMENT '释放前资源完整快照（与 get_customer_assets 同构）', 
	pdf_blob BLOB(4294967295) COMMENT 'PDF 二进制内容（LONGBLOB，事务外回填）', 
	pdf_size INTEGER COMMENT 'PDF 字节数，便于列表展示/告警', 
	operator_id INTEGER NOT NULL COMMENT '终止操作人ID', 
	reason VARCHAR(255) COMMENT '终止原因（可选，前端弹窗传入）', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(operator_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_addresses`
--

DROP TABLE IF EXISTS `ip_addresses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ip_addresses (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	ip_address VARCHAR(255) NOT NULL COMMENT 'IP地址', 
	ip_int BIGINT COMMENT 'IP整数表示(INET_ATON),用于范围查询', 
	customer_id INTEGER COMMENT '客户ID', 
	status SMALLINT NOT NULL COMMENT 'IP状态', 
	notes VARCHAR(255) COMMENT '备注', 
	room_id INTEGER COMMENT '机房ID', 
	last_active_at DATETIME COMMENT '最近一次被观测到活跃的时间（陈旧度清理用）', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ip_room UNIQUE (ip_address, room_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL, 
	FOREIGN KEY(room_id) REFERENCES rooms (id)
);
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_allocation_logs`
--

DROP TABLE IF EXISTS `ip_allocation_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ip_allocation_logs (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	ip_address VARCHAR(45) NOT NULL COMMENT 'IP地址', 
	room_id INTEGER NOT NULL COMMENT '机房ID', 
	action ENUM('allocate','release','change_status') NOT NULL COMMENT '操作类型', 
	old_status SMALLINT COMMENT '原状态', 
	new_status SMALLINT COMMENT '新状态', 
	operator_id BIGINT NOT NULL COMMENT '操作人 FK→users', 
	detail JSON COMMENT '附加信息', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(operator_id) REFERENCES users (id)
)COMMENT='IP分配历史日志';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_escalation_policy`
--

DROP TABLE IF EXISTS `monitor_escalation_policy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_escalation_policy (
	name VARCHAR(128) NOT NULL COMMENT '策略名称', 
	alert_type VARCHAR(64) COMMENT '匹配告警类型（null=全部）', 
	severity VARCHAR(16) COMMENT '匹配告警级别（null=全部）', 
	wait_minutes INTEGER NOT NULL COMMENT '未确认等待分钟数，超过即升级', 
	escalate_severity VARCHAR(16) COMMENT '升级后严重级别（如 critical），null=不升级级别', 
	escalate_to_role_id BIGINT COMMENT '升级后通知的角色 ID', 
	escalate_webhook_url VARCHAR(512) COMMENT '升级触发的 webhook URL（可选）', 
	repeat_minutes INTEGER NOT NULL COMMENT '重复升级间隔分钟（0=只升一次）' DEFAULT 0, 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT 1, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(escalate_to_role_id) REFERENCES roles (id) ON DELETE SET NULL
)COMMENT='监控告警升级策略（G4.2，未确认告警到期升级）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_metric_template_group_items`
--

DROP TABLE IF EXISTS `monitor_metric_template_group_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_metric_template_group_items (
	group_id BIGINT NOT NULL COMMENT '组ID', 
	template_id BIGINT UNSIGNED NOT NULL COMMENT '模板ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_mmtgi_group_template UNIQUE (group_id, template_id), 
	FOREIGN KEY(group_id) REFERENCES monitor_metric_template_groups (id) ON DELETE CASCADE, 
	FOREIGN KEY(template_id) REFERENCES monitor_metric_templates (id) ON DELETE CASCADE
)COMMENT='模板组-模板关联（勾选指标入组）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notification_receipts`
--

DROP TABLE IF EXISTS `notification_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE notification_receipts (
	notification_id BIGINT NOT NULL COMMENT '通知ID', 
	user_id BIGINT NOT NULL COMMENT '用户ID', 
	read_at DATETIME COMMENT '已读时间', 
	delivered_channels JSON COMMENT '投递渠道', 
	channel_status JSON COMMENT '各渠道实际投递结果', 
	ack_required BOOL NOT NULL COMMENT '是否需要确认' DEFAULT '0', 
	acked_at DATETIME COMMENT '确认时间', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)COMMENT='通知投递回执表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE role_permissions (
	role_id BIGINT NOT NULL COMMENT '角色ID', 
	permission_id BIGINT NOT NULL COMMENT '权限ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_role_permission UNIQUE (role_id, permission_id), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
	FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
)COMMENT='角色权限关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE user_roles (
	user_id BIGINT NOT NULL COMMENT '用户ID', 
	role_id BIGINT NOT NULL COMMENT '角色ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_user_role UNIQUE (user_id, role_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE
)COMMENT='用户角色关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users_log`
--

DROP TABLE IF EXISTS `users_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE users_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id BIGINT NOT NULL COMMENT '用户ID', 
	login_time DATETIME NOT NULL COMMENT '登录时间', 
	login_type VARCHAR(10) COMMENT '登录类型', 
	login_ip VARCHAR(255) COMMENT '登录IP', 
	user_agent VARCHAR(512) COMMENT '登录设备/浏览器', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)COMMENT='用户登录日志表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `webhook_configs`
--

DROP TABLE IF EXISTS `webhook_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE webhook_configs (
	name VARCHAR(50) NOT NULL COMMENT '配置名称', 
	channel VARCHAR(20) NOT NULL COMMENT '渠道标识: wechat_work/feishu/custom', 
	url VARCHAR(500) NOT NULL COMMENT 'Webhook URL', 
	secret VARCHAR(255) COMMENT '签名密钥', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT '1', 
	message_template JSON COMMENT '消息模板', 
	applicable_types JSON COMMENT '适用通知类型列表', 
	applicable_severities JSON COMMENT '适用严重程度', 
	created_by BIGINT COMMENT '创建者ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
)COMMENT='Webhook 渠道配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `devices`
--

DROP TABLE IF EXISTS `devices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE devices (
	device_name VARCHAR(100) NOT NULL COMMENT '设备名称', 
	device_type VARCHAR(50) NOT NULL COMMENT '设备主类型: server/network/other', 
	device_subtype VARCHAR(20) COMMENT '设备子类型: standalone/chassis/node/storage/gpu/switch/router/firewall/pdu/ups', 
	device_model VARCHAR(100) COMMENT '设备型号', 
	brand VARCHAR(100) COMMENT '品牌厂商', 
	serial_number VARCHAR(255) COMMENT '序列号', 
	hostname VARCHAR(128) COMMENT '主机名', 
	metric_template_group_id BIGINT COMMENT '显式关联的指标模板组ID（可空）。为空时按 device_type+brand+协议自动匹配模板组；选择后监控数据页优先展示该组包含的指标', 
	management_ip VARCHAR(50) COMMENT '管理IP(同步自switch_credentials.ip,展示用)', 
	mac_address VARCHAR(17) COMMENT '主MAC地址', 
	cabinet_id BIGINT COMMENT '机柜ID', 
	u_position INTEGER COMMENT 'U位起始位置', 
	height_u INTEGER COMMENT '占用U位数量', 
	power FLOAT COMMENT '额定功率(W)', 
	status SMALLINT COMMENT '设备状态: 0-报废 1-可用 2-在线 3-离线 4-维护中 5-预留', 
	responsible_person BIGINT COMMENT '责任人ID', 
	notes TEXT COMMENT '备注', 
	customer_id BIGINT COMMENT '客户ID', 
	deleted_at DATETIME COMMENT '软删除时间(NULL=未删除)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_device_status_range CHECK (status BETWEEN 0 AND 7), 
	FOREIGN KEY(metric_template_group_id) REFERENCES monitor_metric_template_groups (id) ON DELETE SET NULL, 
	FOREIGN KEY(cabinet_id) REFERENCES cabinets (id), 
	FOREIGN KEY(responsible_person) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)COMMENT='设备信息核心表（身份/位置/状态）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_escalation_step`
--

DROP TABLE IF EXISTS `monitor_escalation_step`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_escalation_step (
	policy_id INTEGER NOT NULL COMMENT '所属升级策略 ID', 
	step_no INTEGER NOT NULL COMMENT '步骤序号（从 1 开始，按序执行）' DEFAULT 1, 
	wait_minutes INTEGER NOT NULL COMMENT '距告警产生后多少分钟触发本步骤', 
	escalate_severity VARCHAR(16) COMMENT '本步骤升级到的严重级别（null=不升级级别）', 
	escalate_to_role_id BIGINT COMMENT '本步骤通知的角色 ID', 
	escalate_webhook_url VARCHAR(512) COMMENT '本步骤触发的 webhook URL（可选）', 
	enabled BOOL NOT NULL COMMENT '是否启用本步骤' DEFAULT 1, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(policy_id) REFERENCES monitor_escalation_policy (id) ON DELETE CASCADE, 
	FOREIGN KEY(escalate_to_role_id) REFERENCES roles (id) ON DELETE SET NULL
)COMMENT='监控告警升级链步骤（P2-11，多级升级）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_diagnosis_sessions`
--

DROP TABLE IF EXISTS `ai_diagnosis_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ai_diagnosis_sessions (
	device_id BIGINT COMMENT '设备ID（诊断目标设备，设备删除时保留会话供回溯）', 
	user_id BIGINT NOT NULL COMMENT '用户ID', 
	skill_name VARCHAR(64) NOT NULL COMMENT 'agentic 技能名（如 network_troubleshoot）', 
	question TEXT NOT NULL COMMENT '用户原始问题', 
	rounds_json LONGTEXT COMMENT '每轮工具调用摘要 JSON：[{round, tool, args, result_summary, duration_ms}]', 
	final_answer_json LONGTEXT COMMENT '结构化诊断结论 JSON：{diagnosis, confidence, evidence, proposed_commands}', 
	status VARCHAR(20) NOT NULL COMMENT 'running/completed/incomplete/failed', 
	token_cost INTEGER COMMENT '本次诊断总 token 消耗', 
	duration_ms INTEGER COMMENT '本次诊断总耗时毫秒', 
	remedial_executed BOOL NOT NULL COMMENT '是否有 remedial 命令被实际执行', 
	rollback_failed BOOL NOT NULL COMMENT '回滚是否失败（设备滞留已变更未回滚的中间态标记）', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE SET NULL, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)COMMENT='AI 诊断会话持久化';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_asset`
--

DROP TABLE IF EXISTS `device_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_asset (
	device_id BIGINT NOT NULL COMMENT '关联设备ID', 
	asset_number VARCHAR(64) COMMENT '资产编号', 
	supplier VARCHAR(100) COMMENT '供应商名称', 
	supplier_contact VARCHAR(100) COMMENT '供应商联系人', 
	contract_number VARCHAR(100) COMMENT '采购合同编号', 
	purchase_date DATE COMMENT '采购日期', 
	purchase_price NUMERIC(12, 2) COMMENT '采购价格(元)', 
	invoice_number VARCHAR(100) COMMENT '发票号码', 
	warranty_start DATE COMMENT '保修开始日期', 
	warranty_end DATE COMMENT '保修到期日期', 
	warranty_type VARCHAR(50) COMMENT '保修类型', 
	online_date DATE COMMENT '上线投产日期', 
	offline_date DATE COMMENT '下线/报废日期', 
	lifecycle_years SMALLINT COMMENT '预计使用年限', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备资产台账表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_config_backups`
--

DROP TABLE IF EXISTS `device_config_backups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_config_backups (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	device_id BIGINT NOT NULL COMMENT '设备ID FK→devices', 
	config_content MEDIUMTEXT NOT NULL COMMENT '配置内容(MEDIUMTEXT)', 
	config_hash VARCHAR(64) NOT NULL COMMENT 'SHA-256哈希', 
	backup_type ENUM('manual','scheduled','pre_change') NOT NULL COMMENT '备份类型', 
	file_size INTEGER COMMENT '配置文件大小(字节)', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id)
)COMMENT='设备配置备份';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_hardware`
--

DROP TABLE IF EXISTS `device_hardware`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_hardware (
	device_id BIGINT NOT NULL COMMENT '关联设备ID', 
	cpu VARCHAR(100) COMMENT 'CPU型号', 
	cpu_way SMALLINT COMMENT 'CPU路数', 
	cpu_cores SMALLINT COMMENT '单颗CPU核心数', 
	memory VARCHAR(100) COMMENT '内存配置描述', 
	memory_size_gb INTEGER COMMENT '内存总容量(GB)', 
	memory_dimm_count SMALLINT COMMENT '内存条数', 
	gpu VARCHAR(200) COMMENT 'GPU配置描述', 
	gpu_count SMALLINT COMMENT 'GPU数量', 
	gpu_template_id BIGINT COMMENT 'GPU模板ID', 
	storage_summary VARCHAR(200) COMMENT '存储配置摘要', 
	os_version VARCHAR(255) COMMENT '操作系统版本', 
	ipmi_address VARCHAR(50) COMMENT 'IPMI/BMC IP地址', 
	ipmi_username VARCHAR(64) COMMENT 'IPMI用户名', 
	ipmi_password VARCHAR(255) COMMENT 'IPMI密码', 
	ip_address JSON COMMENT 'IP地址列表(手动录入,与ip_addresses表无关联)', 
	device_config JSON COMMENT '扩展配置', 
	cpu_template_id BIGINT COMMENT 'CPU模板ID', 
	memory_template_id BIGINT COMMENT '内存模板ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(gpu_template_id) REFERENCES component_templates (id) ON DELETE SET NULL, 
	FOREIGN KEY(cpu_template_id) REFERENCES component_templates (id) ON DELETE SET NULL, 
	FOREIGN KEY(memory_template_id) REFERENCES component_templates (id) ON DELETE SET NULL
)COMMENT='设备硬件规格表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_metric_alert_state`
--

DROP TABLE IF EXISTS `device_metric_alert_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_metric_alert_state (
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	metric_key VARCHAR(64) NOT NULL COMMENT '指标标识，如 temperature / disk_failure / port_updown / raid_failure', 
	index_key VARCHAR(64) NOT NULL COMMENT '指标实例索引（端口号 / 传感器名），非索引指标为空串', 
	alert_type VARCHAR(40) NOT NULL COMMENT '告警类型（NotificationTypeCode），如 temperature_alert', 
	breached BOOL NOT NULL COMMENT '当前是否处于告警态', 
	severity VARCHAR(20) COMMENT '最近一次告警层级 crit / warn / ok', 
	`last_value` VARCHAR(255) COMMENT '最近一次指标值（快照，供告警/恢复文案）', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_dmas_device_metric_index UNIQUE (device_id, metric_key, index_key), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备指标告警状态（按指标维度去重与恢复）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_metric_baseline`
--

DROP TABLE IF EXISTS `device_metric_baseline`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_metric_baseline (
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	metric_key VARCHAR(64) NOT NULL COMMENT '指标标识，如 cpu_usage', 
	index_key VARCHAR(128) NOT NULL COMMENT '指标实例索引（端口号等），无索引时为空串', 
	hour_of_day SMALLINT NOT NULL COMMENT '小时（0-23），降级基线时固定为 -1 表示不分桶', 
	day_of_week SMALLINT NOT NULL COMMENT '星期（0=周一...6=周日），降级基线时固定为 -1 表示不分桶', 
	mean DECIMAL(20, 6) NOT NULL COMMENT '均值', 
	stddev DECIMAL(20, 6) NOT NULL COMMENT '标准差', 
	sample_count INTEGER NOT NULL COMMENT '样本数（参与计算的采集点数）', 
	baseline_status VARCHAR(30) NOT NULL COMMENT 'normal/degraded/insufficient_samples', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备指标基线（按小时×星期分桶，滑动28天）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_metric_latest`
--

DROP TABLE IF EXISTS `device_metric_latest`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_metric_latest (
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	metric_key VARCHAR(64) NOT NULL COMMENT '指标标识，如 cpu_usage / temperature / zabbix_cpu_usage', 
	index_key VARCHAR(128) NOT NULL COMMENT '指标实例索引（端口号 / 传感器名 / CPU slot 名），非索引指标为空串', 
	value VARCHAR(255) COMMENT '最近一次指标值（字符串快照，前端按 metric_type 解析展示）', 
	severity VARCHAR(20) COMMENT '最近一次告警层级 crit / warn / ok（未超阈值为 ok）', 
	breached BOOL NOT NULL COMMENT '最近一次是否超阈值', 
	collected_at DATETIME NOT NULL COMMENT '最近一次采集时间', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_dml_device_metric_index UNIQUE (device_id, metric_key, index_key), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备指标当前值（每次采集 upsert，含正常值）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_metric_override`
--

DROP TABLE IF EXISTS `device_metric_override`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_metric_override (
	device_id BIGINT NOT NULL COMMENT '设备 ID', 
	metric_key VARCHAR(64) NOT NULL COMMENT '指标标识（对应 monitor_metric_templates.metric_key）', 
	threshold JSON NOT NULL COMMENT '覆盖阈值 JSON: {warn, crit, min, max, expected}', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT 1, 
	note VARCHAR(255) COMMENT '覆盖原因/备注', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备级阈值覆盖（G4.3，按 device_id+metric_key 覆盖全局阈值）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_monitor_credentials`
--

DROP TABLE IF EXISTS `device_monitor_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_monitor_credentials (
	credential_id BIGINT NOT NULL COMMENT '关联共享凭据ID', 
	device_id BIGINT NOT NULL COMMENT '关联设备ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_dmc_cred_device UNIQUE (credential_id, device_id), 
	FOREIGN KEY(credential_id) REFERENCES monitor_credentials (id) ON DELETE CASCADE, 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备监控凭据关联（多对多）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_monitor_status`
--

DROP TABLE IF EXISTS `device_monitor_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_monitor_status (
	device_id BIGINT NOT NULL COMMENT '关联设备ID（每设备一行）', 
	protocol VARCHAR(20) NOT NULL COMMENT 'snmp/redfish/ipmi；每设备单快照，凭据协议切换会覆盖整行', 
	reachable BOOL NOT NULL COMMENT '当前是否可达', 
	ever_reachable BOOL NOT NULL COMMENT '是否曾成功探测过（首探即不可达也能正确告警）' DEFAULT '0', 
	down_alerted BOOL NOT NULL COMMENT '当前是否已处于不可达且已告警状态，防止停留期内重复告警' DEFAULT '0', 
	down_episode INTEGER NOT NULL COMMENT '第几次进入不可达周期，写入 idempotency_key' DEFAULT '0', 
	last_reachable_at DATETIME COMMENT '最后一次可达时间', 
	last_unreachable_at DATETIME COMMENT '最后一次不可达时间', 
	last_checked_at DATETIME NOT NULL COMMENT '最后一次探测时间（无论成败）', 
	consecutive_failures INTEGER NOT NULL COMMENT '连续失败次数（抖动抑制/阈值判定）' DEFAULT '0', 
	latency_ms INTEGER COMMENT '本次探测耗时', 
	extra JSON COMMENT '协议特有附加信息', 
	last_error TEXT COMMENT '最近一次失败的错误信息', 
	monitor_enabled BOOL NOT NULL COMMENT '设备级监控开关：0=暂停探测，1=正常探测（无状态行视为默认启用）' DEFAULT '1', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='设备健康监控最新状态快照（每设备一行，非时序表）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_monitor_timeseries_daily`
--

DROP TABLE IF EXISTS `device_monitor_timeseries_daily`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_monitor_timeseries_daily (
	device_id BIGINT NOT NULL COMMENT '关联设备ID', 
	metric VARCHAR(32) NOT NULL COMMENT 'reachable / latency_ms', 
	day_bucket DATE NOT NULL COMMENT '日期，如 2026-07-31', 
	avg_value FLOAT NOT NULL COMMENT '均值', 
	min_value FLOAT NOT NULL COMMENT '最小值', 
	max_value FLOAT NOT NULL COMMENT '最大值', 
	sample_count INTEGER NOT NULL COMMENT '采样点数（小时桶数）', 
	created_at DATETIME NOT NULL COMMENT '首次聚合时间' DEFAULT now(), 
	PRIMARY KEY (device_id, metric, day_bucket), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='监控时序天级预聚合，从 hourly 降采样，保留730天（架构3 长期趋势层）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_monitor_timeseries_hourly`
--

DROP TABLE IF EXISTS `device_monitor_timeseries_hourly`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_monitor_timeseries_hourly (
	device_id BIGINT NOT NULL COMMENT '关联设备ID', 
	metric VARCHAR(32) NOT NULL COMMENT 'reachable / latency_ms', 
	hour_bucket DATETIME NOT NULL COMMENT '整点时间，如 2026-07-31 10:00:00', 
	avg_value FLOAT NOT NULL COMMENT '均值', 
	min_value FLOAT NOT NULL COMMENT '最小值', 
	max_value FLOAT NOT NULL COMMENT '最大值', 
	sample_count INTEGER NOT NULL COMMENT '采样点数', 
	created_at DATETIME NOT NULL COMMENT '首次聚合时间' DEFAULT now(), 
	PRIMARY KEY (device_id, metric, hour_bucket), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='监控时序小时级预聚合，事件分区表保留窗口外只保留此表，保留90天';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_nics_port`
--

DROP TABLE IF EXISTS `device_nics_port`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_nics_port (
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	nic_number INTEGER NOT NULL COMMENT '网卡编号', 
	nic_name VARCHAR(100) NOT NULL COMMENT '网卡名称', 
	template_id BIGINT COMMENT '网卡模板ID', 
	port_number INTEGER NOT NULL COMMENT '端口编号', 
	port_name VARCHAR(50) COMMENT '端口名称(如eth0, ens192等)', 
	port_type VARCHAR(20) NOT NULL COMMENT '端口类型(RJ45/SFP/SFP+/SFP28/QSFP+/QSFP28/QSFP56/QSFP-DD)', 
	port_speed VARCHAR(20) NOT NULL COMMENT '端口速率(1G/10G/100G)', 
	port_status VARCHAR(20) COMMENT '端口状态(free=空闲/occupied=已占用/disabled=禁用/error=错误)', 
	description VARCHAR(200) COMMENT '端口描述', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(template_id) REFERENCES component_templates (id) ON DELETE SET NULL
)COMMENT='设备网卡端口表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_server_ext`
--

DROP TABLE IF EXISTS `device_server_ext`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_server_ext (
	device_id BIGINT NOT NULL COMMENT '设备ID(PK+FK→devices.id)', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	parent_device_id BIGINT COMMENT '父设备ID(机箱→设备)', 
	is_chassis BOOL COMMENT '是否为机箱', 
	node_position INTEGER COMMENT '节点在机箱中的位置', 
	node_row INTEGER COMMENT '节点行号', 
	node_col INTEGER COMMENT '节点列号', 
	total_nodes INTEGER COMMENT '机箱总节点数', 
	node_rows INTEGER COMMENT '节点行数', 
	node_cols INTEGER COMMENT '节点列数', 
	node_naming_pattern VARCHAR(100) COMMENT '节点命名模式', 
	PRIMARY KEY (device_id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(parent_device_id) REFERENCES devices (id) ON DELETE SET NULL
)COMMENT='服务器扩展表(1:1扩展devices,仅服务器/机箱)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_storage`
--

DROP TABLE IF EXISTS `device_storage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_storage (
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	storage_type VARCHAR(50) NOT NULL COMMENT '存储类型（HDD/SSD/NVMe等）', 
	capacity VARCHAR(50) NOT NULL COMMENT '容量（如 2TB, 500GB）', 
	capacity_gb INTEGER COMMENT '容量数值(GB)', 
	interface_type VARCHAR(50) COMMENT '接口类型（SATA/SAS/NVMe等）', 
	slot_number SMALLINT COMMENT '硬盘槽位号', 
	manufacturer VARCHAR(100) COMMENT '制造商', 
	model VARCHAR(100) COMMENT '型号', 
	template_id BIGINT COMMENT '硬盘模板ID', 
	serial_number VARCHAR(100) COMMENT '序列号（全局唯一）', 
	firmware VARCHAR(50) COMMENT '固件版本', 
	status VARCHAR(20) NOT NULL COMMENT '运行状态: normal/warning/error/offline', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(template_id) REFERENCES component_templates (id) ON DELETE SET NULL
)COMMENT='设备存储表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_switch_ext`
--

DROP TABLE IF EXISTS `device_switch_ext`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_switch_ext (
	device_id BIGINT NOT NULL COMMENT '设备ID(PK+FK→devices.id)', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	switch_role SMALLINT COMMENT '交换机角色: 0=核心, 1=接入, NULL=非交换机', 
	layer SMALLINT COMMENT '网络层级', 
	uplink_device_id BIGINT COMMENT '上行设备ID', 
	uplink_port_ids JSON COMMENT '本机上行端口ID数组(引用network_ports.id,如[1,2])', 
	core_device_id BIGINT COMMENT '核心交换机ID', 
	port_num SMALLINT COMMENT '端口数量', 
	port_sync_enabled BOOL COMMENT '端口同步开关(NULL=跟随全局,True=强制开,False=强制关)', 
	PRIMARY KEY (device_id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(uplink_device_id) REFERENCES devices (id) ON DELETE SET NULL, 
	FOREIGN KEY(core_device_id) REFERENCES devices (id) ON DELETE SET NULL
)COMMENT='交换机扩展表(1:1扩展devices,仅交换机)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_ban_records`
--

DROP TABLE IF EXISTS `ip_ban_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ip_ban_records (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	ip_address VARCHAR(45) NOT NULL COMMENT 'IP地址', 
	ip_int BIGINT COMMENT 'IP整数表示(INET_ATON),用于范围查询', 
	room_id INTEGER NOT NULL COMMENT '机房ID', 
	switch_id BIGINT NOT NULL COMMENT '执行封禁的交换机ID', 
	ban_mode VARCHAR(16) NOT NULL COMMENT '封禁方式(route/arp)', 
	ban_meta JSON COMMENT '封禁元数据(JSON,含mac_address/vlan_id等)', 
	action ENUM('ban','unban') NOT NULL COMMENT '封禁动作', 
	is_active BOOL NOT NULL COMMENT '是否活跃', 
	operator_id BIGINT COMMENT '操作人ID', 
	created_at DATETIME COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(switch_id) REFERENCES devices (id), 
	FOREIGN KEY(operator_id) REFERENCES users (id)
);
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_networks`
--

DROP TABLE IF EXISTS `ip_networks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ip_networks (
	network VARCHAR(45) NOT NULL COMMENT '网段地址(如192.168.1.0/24)', 
	switch_id BIGINT NOT NULL COMMENT '所属交换机', 
	port VARCHAR(50) NOT NULL COMMENT '端口名(空串=无端口)' DEFAULT '', 
	customer_id BIGINT COMMENT '客户ID', 
	gateway VARCHAR(45) COMMENT '网关地址', 
	notes VARCHAR(255) COMMENT '人工备注（文本）', 
	room_id INTEGER NOT NULL COMMENT '机房ID', 
	network_int INTEGER COMMENT '网段起始IP整数(INET_ATON)', 
	prefix SMALLINT COMMENT '子网掩码位数(如24)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(switch_id) REFERENCES devices (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id)
)COMMENT='IP网段规划(仅网段信息)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `link_aggregation_groups`
--

DROP TABLE IF EXISTS `link_aggregation_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE link_aggregation_groups (
	device_id BIGINT NOT NULL COMMENT '所属设备 FK→devices', 
	lag_name VARCHAR(50) NOT NULL COMMENT '聚合组名(Eth-Trunk/X)', 
	lag_type ENUM('lacp','static') NOT NULL COMMENT '聚合类型', 
	algorithm VARCHAR(32) COMMENT '负载均衡算法', 
	status SMALLINT NOT NULL COMMENT 'LAG状态: 1=活跃 0=停用 (LAGStatus)', 
	member_count SMALLINT NOT NULL COMMENT '成员口数量（冗余字段,可从network_ports.lag_group_id统计）', 
	purpose VARCHAR(255) COMMENT '用途说明', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id)
)COMMENT='链路聚合组';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_alert_dependency_rule`
--

DROP TABLE IF EXISTS `monitor_alert_dependency_rule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_alert_dependency_rule (
	name VARCHAR(128) NOT NULL COMMENT '规则名称', 
	upstream_device_id BIGINT NOT NULL COMMENT '上游设备 ID（active 告警在此设备上时触发抑制）', 
	downstream_device_id BIGINT NOT NULL COMMENT '下游设备 ID（被抑制的设备）', 
	alert_types JSON COMMENT '受抑制的告警类型列表（null=全部类型）', 
	reason VARCHAR(255) COMMENT '规则说明', 
	enabled BOOL NOT NULL COMMENT '是否启用' DEFAULT 1, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(upstream_device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(downstream_device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='监控告警依赖抑制规则（P2-17，上游 active 告警抑制下游）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_alert_outbox`
--

DROP TABLE IF EXISTS `monitor_alert_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_alert_outbox (
	device_id BIGINT COMMENT '关联设备ID（设备被删除后置空，历史告警行本身保留）', 
	alert_type VARCHAR(40) NOT NULL COMMENT 'device_unreachable / device_recovered', 
	severity VARCHAR(20) NOT NULL COMMENT 'info / warning / critical', 
	dedup_key VARCHAR(191) NOT NULL COMMENT '= notify idempotency_key，去重/幂等', 
	payload_json TEXT NOT NULL COMMENT 'notify 参数字典的 JSON：type/severity/title/content/payload/source_module/target_type/target_id/channels/idempotency_key/allow_broadcast', 
	status VARCHAR(16) NOT NULL COMMENT 'pending / sent / failed' DEFAULT 'pending', 
	attempts INTEGER NOT NULL COMMENT '投递尝试次数' DEFAULT '0', 
	last_error TEXT COMMENT '最近一次投递失败信息', 
	next_retry_at DATETIME COMMENT '下次允许重试时间（指数退避；NULL 表示立即可重试）', 
	created_at DATETIME NOT NULL COMMENT '入箱时间' DEFAULT CURRENT_TIMESTAMP, 
	sent_at DATETIME COMMENT '投递成功时间', 
	acknowledged_by VARCHAR(64) COMMENT '确认人用户名（G9 人工确认/认领）', 
	acknowledged_at DATETIME COMMENT '确认时间（G9；同时供 G4.2 升级扫描判断未确认告警）', 
	ack_note TEXT COMMENT '确认备注（G9）', 
	closed_by VARCHAR(64) COMMENT '关闭人用户名（P2-16 manual_close）', 
	closed_at DATETIME COMMENT '手动关闭时间（P2-16；IS NOT NULL 表示已关闭，不再计入活跃告警）', 
	close_reason TEXT COMMENT '关闭原因（P2-16）', 
	incident_id BIGINT COMMENT '归属事件ID（事件聚合；NULL 表示未聚合或聚合失败）', 
	reason_code VARCHAR(40) COMMENT '归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE SET NULL
)COMMENT='监控告警发件箱（outbox 模式，解耦状态落库与告警投递）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_incident`
--

DROP TABLE IF EXISTS `monitor_incident`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_incident (
	incident_key VARCHAR(191) NOT NULL COMMENT '归并键，如 device_unreachable:200（比 dedup_key 粗，不含 metric_key/index/action）', 
	title VARCHAR(255) NOT NULL COMMENT '事件标题', 
	severity VARCHAR(20) NOT NULL COMMENT 'info / warning / critical（取事件内最高级别）', 
	status VARCHAR(16) NOT NULL COMMENT 'active / acknowledged / closed' DEFAULT 'active', 
	reason_code VARCHAR(40) COMMENT '归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change', 
	root_device_id BIGINT COMMENT '根因设备ID（设备删除后置空）', 
	alert_count INTEGER NOT NULL COMMENT '累计告警数（入箱的）' DEFAULT '1', 
	device_count INTEGER NOT NULL COMMENT '影响设备数（入箱设备 ∪ 被抑制留痕设备，去重）' DEFAULT '1', 
	first_alert_at DATETIME NOT NULL COMMENT '首条告警时间' DEFAULT CURRENT_TIMESTAMP, 
	last_alert_at DATETIME NOT NULL COMMENT '末条告警时间（L1 时间窗判定基准）' DEFAULT CURRENT_TIMESTAMP, 
	closed_at DATETIME COMMENT '关闭时间', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(root_device_id) REFERENCES devices (id) ON DELETE SET NULL
)COMMENT='监控事件（告警聚合后的运营单元）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monitor_suppressed_alert_log`
--

DROP TABLE IF EXISTS `monitor_suppressed_alert_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE monitor_suppressed_alert_log (
	device_id BIGINT COMMENT '被抑制告警的设备ID（设备删除后置空，留痕行保留）', 
	alert_type VARCHAR(40) NOT NULL COMMENT '告警类型（device_unreachable / cpu_high 等）', 
	severity VARCHAR(20) NOT NULL COMMENT 'info / warning / critical', 
	reason_code VARCHAR(40) NOT NULL COMMENT '抑制来源编码：L2_manual_rule / L2_topology', 
	upstream_device_id BIGINT COMMENT '命中的上游设备ID（根因侧，用于归属事件）', 
	incident_id BIGINT COMMENT '归属事件ID（L2 聚合后回填；NULL 表示尚未归属）', 
	created_at DATETIME NOT NULL COMMENT '留痕时间' DEFAULT CURRENT_TIMESTAMP, 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE SET NULL
)COMMENT='被依赖抑制告警留痕（事件影响面统计，不参与投递）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_credentials`
--

DROP TABLE IF EXISTS `switch_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE switch_credentials (
	device_id BIGINT NOT NULL COMMENT '1:1关联设备', 
	ip VARCHAR(45) COMMENT 'SSH管理IP(与devices.management_ip同步,采集连接唯一数据源)', 
	port SMALLINT COMMENT 'SSH/Telnet端口', 
	username VARCHAR(64) COMMENT '登录用户名', 
	password VARCHAR(512) COMMENT 'AES-256-GCM加密后密码', 
	protocol VARCHAR(10) COMMENT '连接协议', 
	authentication_method VARCHAR(32) COMMENT '认证方式', 
	device_type VARCHAR(20) COMMENT '驱动类型:huawei/h3c/cisco', 
	has_ssh BOOL COMMENT '是否有SSH权限', 
	mac_address VARCHAR(17) COMMENT '管理口MAC', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id)
)COMMENT='交换机凭据(1:1扩展devices,仅认证信息)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_status_cache`
--

DROP TABLE IF EXISTS `switch_status_cache`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE switch_status_cache (
	device_id BIGINT NOT NULL COMMENT '1:1关联设备', 
	device_version VARCHAR(255) COMMENT '设备版本(采集缓存)', 
	device_uptime VARCHAR(255) COMMENT '运行时长(采集缓存)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id)
)COMMENT='交换机采集状态缓存(1:1扩展devices)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `virtual_room_members`
--

DROP TABLE IF EXISTS `virtual_room_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE virtual_room_members (
	virtual_room_id INTEGER NOT NULL COMMENT '虚拟机房ID', 
	device_id BIGINT NOT NULL COMMENT '交换机设备ID', 
	joined_at DATETIME NOT NULL COMMENT '加入时间' DEFAULT now(), 
	PRIMARY KEY (virtual_room_id, device_id), 
	CONSTRAINT uq_vr_member UNIQUE (virtual_room_id, device_id), 
	FOREIGN KEY(virtual_room_id) REFERENCES virtual_rooms (id) ON DELETE CASCADE, 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
)COMMENT='虚拟机房成员（交换机）关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_config_changes`
--

DROP TABLE IF EXISTS `device_config_changes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_config_changes (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	device_id BIGINT NOT NULL COMMENT '设备ID FK→devices', 
	backup_id BIGINT COMMENT '基准备份ID FK→device_config_backups', 
	change_summary VARCHAR(500) NOT NULL COMMENT '变更摘要', 
	change_detail MEDIUMTEXT COMMENT '变更详情(diff)', 
	status ENUM('draft','pending','approved','rejected','applied') NOT NULL COMMENT '审批状态', 
	requested_by BIGINT NOT NULL COMMENT '申请人 FK→users', 
	approved_by BIGINT COMMENT '审批人 FK→users', 
	applied_at DATETIME COMMENT '实际应用时间', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id), 
	FOREIGN KEY(backup_id) REFERENCES device_config_backups (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
)COMMENT='设备配置变更审批';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `network_ports`
--

DROP TABLE IF EXISTS `network_ports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE network_ports (
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	device_id BIGINT NOT NULL COMMENT '设备ID', 
	port_type VARCHAR(50) COMMENT '端口类型', 
	slot INTEGER COMMENT '槽位(-1=无槽位)', 
	card INTEGER COMMENT '板卡号(-1=无板卡)', 
	port_number INTEGER COMMENT '端口号', 
	port_name VARCHAR(100) NOT NULL COMMENT '端口名称', 
	speed VARCHAR(20) COMMENT '端口速率', 
	usage_status ENUM('free','occupied','disabled','error') COMMENT '占用状态(free/occupied/disabled/error)', 
	vlan VARCHAR(200) COMMENT 'VLAN配置(采集缓存,真值来源为vlan_port_members表)', 
	description TEXT COMMENT '端口描述', 
	link_status VARCHAR(50) COMMENT '链路状态(up/down/disabled)', 
	mac VARCHAR(17) COMMENT 'MAC地址', 
	ip_address VARCHAR(45) COMMENT '端口主IP(deprecated,权威源为switch_port_ips)', 
	customer_id BIGINT COMMENT '客户ID', 
	raw_info TEXT COMMENT '原始端口信息(JSON)', 
	data_source ENUM('manual','auto','hybrid') COMMENT '数据来源(manual/auto/hybrid)', 
	last_collected_at DATETIME COMMENT '最后采集时间', 
	lag_group_id BIGINT COMMENT 'LAG成员：所属LAG组ID，NULL=非LAG成员端口', 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_device_port_name UNIQUE (device_id, port_name), 
	FOREIGN KEY(device_id) REFERENCES devices (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(lag_group_id) REFERENCES link_aggregation_groups (id) ON DELETE SET NULL
);
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_routes`
--

DROP TABLE IF EXISTS `switch_routes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE switch_routes (
	switch_id BIGINT NOT NULL COMMENT '交换机设备ID', 
	destination VARCHAR(45) NOT NULL COMMENT '目标网段', 
	nexthop VARCHAR(45) NOT NULL COMMENT '下一跳IP', 
	route_type SMALLINT NOT NULL COMMENT '路由类型(RouteNotes): 0=默认 1=互联 2=子网 3=网络 4=黑洞 5=网关 6=主机', 
	port VARCHAR(50) COMMENT '出接口', 
	room_id INTEGER COMMENT '机房ID FK→rooms', 
	network_id BIGINT COMMENT '所属网段 FK→ip_networks', 
	customer_id BIGINT COMMENT '客户ID FK→customers', 
	notes VARCHAR(255) COMMENT '备注', 
	destination_int INTEGER COMMENT '目标网段起始IP整数(INET_ATON)', 
	destination_prefix SMALLINT COMMENT '目标网段前缀长度(如24)', 
	nexthop_int INTEGER COMMENT '下一跳IP整数(INET_ATON)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(switch_id) REFERENCES devices (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(network_id) REFERENCES ip_networks (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)COMMENT='交换机路由条目';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vlans`
--

DROP TABLE IF EXISTS `vlans`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE vlans (
	vlan_id SMALLINT NOT NULL COMMENT 'VLAN ID (1-4094)', 
	name VARCHAR(64) NOT NULL COMMENT 'VLAN名称', 
	purpose VARCHAR(200) COMMENT '用途说明', 
	subnet_id BIGINT COMMENT '关联网段ID FK→ip_networks', 
	room_id INTEGER COMMENT '所属机房ID', 
	status SMALLINT NOT NULL COMMENT 'VLAN状态: 1=活跃 0=停用 (VLANStatus)', 
	device_id BIGINT NOT NULL COMMENT '所属交换机设备ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_vlan_device UNIQUE (device_id, vlan_id), 
	FOREIGN KEY(subnet_id) REFERENCES ip_networks (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id)
)COMMENT='VLAN资源（设备维度）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_connections`
--

DROP TABLE IF EXISTS `device_connections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE device_connections (
	device_id BIGINT NOT NULL COMMENT '设备ID（服务器）', 
	switch_device_id BIGINT NOT NULL COMMENT '交换机设备ID', 
	switch_port_id BIGINT COMMENT '交换机端口ID(兼容旧数据)', 
	device_nics_port_id BIGINT COMMENT '设备网卡端口ID(关联device_nics_port表)', 
	connection_type VARCHAR(50) COMMENT '连接类型', 
	vlan_id INTEGER COMMENT 'VLAN ID(逻辑关联vlans.vlan_id,不加FK因D2N连接可能引用采集缓存值)', 
	status VARCHAR(20) COMMENT '连接状态(active/inactive)', 
	notes TEXT COMMENT '备注', 
	bandwidth VARCHAR(20) COMMENT '带宽', 
	description VARCHAR(200) COMMENT '描述', 
	lag_group_id BIGINT COMMENT '所属聚合组 FK→link_aggregation_groups', 
	port_role ENUM('standalone','primary','backup','member') NOT NULL COMMENT '连接角色', 
	redundancy_mode ENUM('none','active-standby','active-active') NOT NULL COMMENT '冗余模式', 
	vlan_mode ENUM('access','trunk','hybrid') NOT NULL COMMENT 'VLAN模式', 
	native_vlan SMALLINT COMMENT 'Native VLAN(trunk口用)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(switch_device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(switch_port_id) REFERENCES network_ports (id) ON DELETE SET NULL, 
	FOREIGN KEY(device_nics_port_id) REFERENCES device_nics_port (id) ON DELETE CASCADE, 
	FOREIGN KEY(lag_group_id) REFERENCES link_aggregation_groups (id) ON DELETE SET NULL
)COMMENT='设备连接表(D2N)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ip_switch_info`
--

DROP TABLE IF EXISTS `ip_switch_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE ip_switch_info (
	ip_address VARCHAR(45) NOT NULL COMMENT 'IP地址', 
	ip_int BIGINT COMMENT 'IP整数表示(INET_ATON),用于范围查询', 
	mac_address VARCHAR(17) COMMENT 'MAC地址', 
	switch_id BIGINT NOT NULL COMMENT '交换机设备ID', 
	port VARCHAR(50) COMMENT '端口名', 
	port_id BIGINT COMMENT '端口ID FK→network_ports', 
	vlan_id SMALLINT COMMENT 'VLAN ID', 
	room_id INTEGER COMMENT '机房ID', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_isi_ip_room UNIQUE (ip_address, room_id), 
	FOREIGN KEY(switch_id) REFERENCES devices (id), 
	FOREIGN KEY(port_id) REFERENCES network_ports (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id)
)COMMENT='IP交换机信息(替代旧ip_info)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `network_connections`
--

DROP TABLE IF EXISTS `network_connections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE network_connections (
	local_port_id BIGINT NOT NULL COMMENT '本机端口 FK→network_ports.id', 
	peer_port_id BIGINT NOT NULL COMMENT '对端端口 FK→network_ports.id', 
	local_device_id BIGINT NOT NULL COMMENT '本机设备 FK→devices.id', 
	peer_device_id BIGINT NOT NULL COMMENT '对端设备 FK→devices.id', 
	connection_type VARCHAR(50) COMMENT '连接类型(ethernet/fiber/management/serial/other)', 
	vlan_id SMALLINT COMMENT 'VLAN标识号(1-4094,逻辑关联vlans.vlan_id,不加FK因N2N连接可能引用采集缓存值)', 
	status VARCHAR(20) NOT NULL COMMENT '连接状态(active/inactive)', 
	notes TEXT COMMENT '备注', 
	bandwidth VARCHAR(20) COMMENT '带宽', 
	description VARCHAR(200) COMMENT '描述', 
	lag_group_id BIGINT COMMENT '所属聚合组 FK→link_aggregation_groups', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	UNIQUE (local_port_id), 
	FOREIGN KEY(local_port_id) REFERENCES network_ports (id) ON DELETE CASCADE, 
	UNIQUE (peer_port_id), 
	FOREIGN KEY(peer_port_id) REFERENCES network_ports (id) ON DELETE CASCADE, 
	FOREIGN KEY(local_device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(peer_device_id) REFERENCES devices (id) ON DELETE CASCADE, 
	FOREIGN KEY(lag_group_id) REFERENCES link_aggregation_groups (id) ON DELETE SET NULL
)COMMENT='网络设备间连接表(N2N)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `switch_port_ips`
--

DROP TABLE IF EXISTS `switch_port_ips`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE switch_port_ips (
	device_id BIGINT NOT NULL COMMENT '交换机设备ID', 
	port_id BIGINT COMMENT '端口ID', 
	port_name VARCHAR(255) NOT NULL COMMENT '端口名', 
	ip_address VARCHAR(45) NOT NULL COMMENT 'IP地址', 
	ip_int BIGINT COMMENT 'IP整数表示(INET_ATON),用于范围查询', 
	subnet_mask VARCHAR(20) COMMENT '子网掩码(点分十进制)' DEFAULT '255.255.255.0', 
	prefix SMALLINT COMMENT '子网掩码位数(如24,从subnet_mask转换)', 
	is_primary BOOL COMMENT '是否为主IP' DEFAULT '1', 
	vlan INTEGER COMMENT 'VLAN ID(逻辑关联vlans.vlan_id,不加FK因采集数据可能引用不存在的VLAN)', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_spi_device_port_ip UNIQUE (device_id, port_name, ip_address), 
	FOREIGN KEY(device_id) REFERENCES devices (id), 
	FOREIGN KEY(port_id) REFERENCES network_ports (id)
)COMMENT='交换机端口IP';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vlan_port_members`
--

DROP TABLE IF EXISTS `vlan_port_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE vlan_port_members (
	vlan_id BIGINT NOT NULL COMMENT 'FK→vlans.id', 
	port_id BIGINT NOT NULL COMMENT 'FK→network_ports.id', 
	port_mode ENUM('access','trunk','hybrid') NOT NULL COMMENT '端口模式', 
	id BIGINT NOT NULL COMMENT '主键ID' AUTO_INCREMENT, 
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uk_vpm_vlan_port UNIQUE (vlan_id, port_id), 
	FOREIGN KEY(vlan_id) REFERENCES vlans (id) ON DELETE CASCADE, 
	FOREIGN KEY(port_id) REFERENCES network_ports (id) ON DELETE CASCADE
)COMMENT='VLAN成员端口关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-04 10:41:39
