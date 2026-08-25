-- ============================================================
-- seed_data.sql - 配置类种子数据
-- 说明: 幂等，可重复执行。每张表先 DELETE 再 INSERT。
-- ============================================================
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- permissions: 63 rows
DELETE FROM `permissions`;
INSERT INTO `permissions` (`id`, `code`, `name`, `category`, `description`, `created_at`, `updated_at`) VALUES
(121, 'room:view', '查看机房', 'room', '查看机房信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(122, 'room:create', '创建机房', 'room', '创建新机房', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(123, 'room:update', '更新机房', 'room', '修改机房信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(124, 'room:delete', '删除机房', 'room', '删除机房', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(125, 'cabinet:view', '查看机柜', 'cabinet', '查看机柜信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(126, 'cabinet:create', '创建机柜', 'cabinet', '创建新机柜', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(127, 'cabinet:update', '更新机柜', 'cabinet', '修改机柜信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(128, 'cabinet:delete', '删除机柜', 'cabinet', '删除机柜', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(129, 'device:view', '查看设备', 'device', '查看设备信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(130, 'device:create', '创建设备', 'device', '创建新设备', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(131, 'device:update', '更新设备', 'device', '修改设备信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(132, 'device:delete', '删除设备', 'device', '删除设备', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(133, 'customer:view', '查看客户', 'customer', '查看客户信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(134, 'customer:create', '创建客户', 'customer', '创建新客户', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(135, 'customer:update', '更新客户', 'customer', '修改客户信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(136, 'customer:delete', '删除客户', 'customer', '删除客户', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(137, 'user:view', '查看用户', 'user', '查看用户信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(138, 'user:create', '创建用户', 'user', '创建新用户', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(139, 'user:update', '更新用户', 'user', '修改用户信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(140, 'user:delete', '删除用户', 'user', '删除用户', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(141, 'user:permission', '管理用户权限', 'user', '管理用户权限分配', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(142, 'user:role', '管理用户角色', 'user', '管理用户角色分配', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(143, 'user:log', '管理用户登录日志', 'user', '查看和管理用户登录日志', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(144, 'network:view', '查看网络', 'network', '查看网络信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(145, 'network:create', '创建网络', 'network', '创建新网络', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(146, 'network:update', '更新网络', 'network', '修改网络信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(147, 'network:delete', '删除网络', 'network', '删除网络', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(148, 'network:scan', '网络扫描', 'network', '执行网络扫描', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(149, 'switch:view', '查看交换机', 'switch', '查看交换机信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(150, 'switch:create', '创建交换机', 'switch', '创建新交换机', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(151, 'switch:update', '更新交换机', 'switch', '修改交换机信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(152, 'switch:delete', '删除交换机', 'switch', '删除交换机', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(153, 'switch:config', '配置交换机', 'switch', '配置交换机参数', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(154, 'ip:view', '查看IP', 'ip', '查看IP地址信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(155, 'ip:update', '更新IP', 'ip', '修改IP地址信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(156, 'ip:scan', 'IP扫描', 'ip', '执行IP扫描', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(157, 'system:config', '系统配置', 'system', '管理系统配置', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(158, 'system:logs', '查看日志', 'system', '查看系统日志', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(159, 'system:backup', '备份恢复', 'system', '执行系统备份和恢复', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(160, 'system:scan', '系统扫描', 'system', '执行系统扫描', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(161, 'system:stats', '查看统计', 'system', '查看系统统计数据', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(162, 'asset:view', '查看资产', 'asset', '查看资产信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(163, 'asset:create', '创建资产', 'asset', '创建新资产', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(164, 'asset:update', '更新资产', 'asset', '修改资产信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(165, 'asset:delete', '删除资产', 'asset', '删除资产', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(166, 'monitor:view', '查看监控', 'monitor', '查看监控信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(167, 'monitor:alert', '管理告警', 'monitor', '管理监控告警', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(168, 'monitor:report', '查看报表', 'monitor', '查看监控报表', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(169, 'maintenance:view', '查看维护', 'maintenance', '查看维护信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(170, 'maintenance:create', '创建维护', 'maintenance', '创建维护记录', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(171, 'maintenance:update', '更新维护', 'maintenance', '修改维护记录', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(172, 'maintenance:delete', '删除维护', 'maintenance', '删除维护记录', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(173, 'security:read', '查看安全设置', 'security', '查看安全相关配置', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(174, 'security:config', '配置安全设置', 'security', '修改安全相关配置', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(175, 'security:session', '管理会话', 'security', '管理用户会话', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(176, 'rbac:view', '查看角色权限', 'rbac', '查看角色和权限配置', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(177, 'rbac:create', '创建角色', 'rbac', '创建新角色', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(178, 'rbac:update', '更新角色', 'rbac', '修改角色信息', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(179, 'rbac:delete', '删除角色', 'rbac', '删除角色', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(180, 'audit:view', '查看审计日志', 'audit', '查看审计日志记录', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(181, 'import:view', '查看导入导出', 'import', '查看导入导出记录', '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(228, 'monitor:config', '配置监控', 'monitor', '配置监控凭据和探测参数', '2026-08-04 11:45:21', '2026-08-04 11:45:21'),
(260, 'customer:terminate', '终止客户', 'customer', '终止客户并释放全部资源（含重建存档 PDF）', '2026-08-24 11:14:14', '2026-08-24 11:14:14');

-- roles: 4 rows
DELETE FROM `roles`;
INSERT INTO `roles` (`id`, `name`, `display_name`, `description`, `status`, `data_scope`, `data_scope_config`, `created_at`, `updated_at`) VALUES
(9, 'admin', '管理员', '拥有所有权限的系统管理员', 0, 'all', NULL, '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(10, 'operator', '操作员', '可以查看和修改数据，但不能删除', 0, 'all', NULL, '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(11, 'viewer', '查看者', '只能查看数据', 0, 'all', NULL, '2026-07-13 12:56:25', '2026-07-13 12:56:25'),
(12, 'user', '普通用户', '只能查看基本信息', 0, 'all', NULL, '2026-07-13 12:56:25', '2026-07-13 12:56:25');

-- role_permissions: 107 rows
DELETE FROM `role_permissions`;
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`, `created_at`, `updated_at`) VALUES
(534, 9, 121, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(535, 9, 122, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(536, 9, 123, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(537, 9, 124, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(538, 9, 125, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(539, 9, 126, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(540, 9, 127, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(541, 9, 128, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(542, 9, 129, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(543, 9, 130, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(544, 9, 131, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(545, 9, 132, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(546, 9, 133, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(547, 9, 134, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(548, 9, 135, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(549, 9, 136, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(550, 9, 260, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(551, 9, 137, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(552, 9, 138, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(553, 9, 139, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(554, 9, 140, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(555, 9, 141, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(556, 9, 142, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(557, 9, 143, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(558, 9, 144, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(559, 9, 145, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(560, 9, 146, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(561, 9, 147, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(562, 9, 148, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(563, 9, 149, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(564, 9, 150, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(565, 9, 151, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(566, 9, 152, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(567, 9, 153, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(568, 9, 154, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(569, 9, 155, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(570, 9, 156, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(571, 9, 157, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(572, 9, 158, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(573, 9, 159, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(574, 9, 160, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(575, 9, 161, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(576, 9, 162, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(577, 9, 163, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(578, 9, 164, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(579, 9, 165, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(580, 9, 166, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(581, 9, 228, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(582, 9, 167, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(583, 9, 168, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(584, 9, 169, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(585, 9, 170, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(586, 9, 171, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(587, 9, 172, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(588, 9, 173, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(589, 9, 174, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(590, 9, 175, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(591, 9, 176, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(592, 9, 177, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(593, 9, 178, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(594, 9, 179, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(595, 9, 180, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(596, 9, 181, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(597, 10, 121, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(598, 10, 122, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(599, 10, 123, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(600, 10, 125, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(601, 10, 126, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(602, 10, 127, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(603, 10, 129, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(604, 10, 130, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(605, 10, 131, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(606, 10, 133, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(607, 10, 134, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(608, 10, 135, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(609, 10, 137, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(610, 10, 144, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(611, 10, 145, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(612, 10, 146, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(613, 10, 148, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(614, 10, 149, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(615, 10, 150, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(616, 10, 151, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(617, 10, 153, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(618, 10, 154, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(619, 10, 155, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(620, 10, 156, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(621, 10, 160, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(622, 10, 161, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(623, 10, 166, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(624, 10, 228, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(625, 11, 121, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(626, 11, 125, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(627, 11, 129, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(628, 11, 133, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(629, 11, 137, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(630, 11, 144, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(631, 11, 149, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(632, 11, 154, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(633, 11, 161, '2026-08-24 11:14:14', '2026-08-24 11:14:14');
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`, `created_at`, `updated_at`) VALUES
(634, 12, 121, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(635, 12, 125, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(636, 12, 129, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(637, 12, 144, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(638, 12, 149, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(639, 12, 154, '2026-08-24 11:14:14', '2026-08-24 11:14:14'),
(640, 12, 161, '2026-08-24 11:14:14', '2026-08-24 11:14:14');

-- component_templates: 162 rows
DELETE FROM `component_templates`;
INSERT INTO `component_templates` (`id`, `category`, `brand`, `model`, `spec`, `is_active`, `sort_order`, `remark`, `created_at`, `updated_at`, `customer_id`, `scope`) VALUES
(207, 'cpu', 'Intel', 'Xeon Platinum 8490H', '{"tdp_w": 350, "architecture": "x86_64", "base_freq_ghz": 1.9, "cores_per_cpu": 60, "boost_freq_ghz": 3.5}', 1, 10, 'Sapphire Rapids，最高端', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(208, 'cpu', 'Intel', 'Xeon Platinum 8480+', '{"tdp_w": 350, "architecture": "x86_64", "base_freq_ghz": 2.0, "cores_per_cpu": 56, "boost_freq_ghz": 3.4}', 1, 11, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(209, 'cpu', 'Intel', 'Xeon Gold 6458Q', '{"tdp_w": 250, "architecture": "x86_64", "base_freq_ghz": 3.0, "cores_per_cpu": 32, "boost_freq_ghz": 3.8}', 1, 20, 'Sapphire Rapids，高频', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(210, 'cpu', 'Intel', 'Xeon Gold 6448Y', '{"tdp_w": 225, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 32, "boost_freq_ghz": 4.1}', 1, 21, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(211, 'cpu', 'Intel', 'Xeon Gold 6430', '{"tdp_w": 270, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 32, "boost_freq_ghz": 3.4}', 1, 22, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(212, 'cpu', 'Intel', 'Xeon Gold 5418N', '{"tdp_w": 150, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 24, "boost_freq_ghz": 3.4}', 1, 30, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(213, 'cpu', 'Intel', 'Xeon Silver 4416+', '{"tdp_w": 165, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 20, "boost_freq_ghz": 3.6}', 1, 40, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(214, 'cpu', 'Intel', 'Xeon Silver 4410Y', '{"tdp_w": 150, "architecture": "x86_64", "base_freq_ghz": 2.0, "cores_per_cpu": 12, "boost_freq_ghz": 3.9}', 1, 41, 'Sapphire Rapids', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(215, 'cpu', 'Intel', 'Xeon Bronze 3408U', '{"tdp_w": 125, "architecture": "x86_64", "base_freq_ghz": 1.8, "cores_per_cpu": 8, "boost_freq_ghz": 2.3}', 1, 50, 'Sapphire Rapids，入门', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(216, 'cpu', 'Intel', 'Xeon Platinum 8380', '{"tdp_w": 270, "architecture": "x86_64", "base_freq_ghz": 2.3, "cores_per_cpu": 40, "boost_freq_ghz": 3.4}', 1, 60, 'Ice Lake', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(217, 'cpu', 'Intel', 'Xeon Gold 6354', '{"tdp_w": 205, "architecture": "x86_64", "base_freq_ghz": 3.0, "cores_per_cpu": 18, "boost_freq_ghz": 3.6}', 1, 70, 'Ice Lake', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(218, 'cpu', 'Intel', 'Xeon Silver 4314', '{"tdp_w": 135, "architecture": "x86_64", "base_freq_ghz": 2.4, "cores_per_cpu": 16, "boost_freq_ghz": 3.4}', 1, 80, 'Ice Lake', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(219, 'cpu', 'AMD', 'EPYC 9654', '{"tdp_w": 360, "architecture": "x86_64", "base_freq_ghz": 2.4, "cores_per_cpu": 96, "boost_freq_ghz": 3.7}', 1, 100, 'Genoa，96核旗舰', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(220, 'cpu', 'AMD', 'EPYC 9554', '{"tdp_w": 360, "architecture": "x86_64", "base_freq_ghz": 3.1, "cores_per_cpu": 64, "boost_freq_ghz": 3.75}', 1, 101, 'Genoa', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(221, 'cpu', 'AMD', 'EPYC 9454', '{"tdp_w": 290, "architecture": "x86_64", "base_freq_ghz": 2.75, "cores_per_cpu": 48, "boost_freq_ghz": 3.65}', 1, 102, 'Genoa', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(222, 'cpu', 'AMD', 'EPYC 9354', '{"tdp_w": 280, "architecture": "x86_64", "base_freq_ghz": 3.25, "cores_per_cpu": 32, "boost_freq_ghz": 3.8}', 1, 103, 'Genoa', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(223, 'cpu', 'AMD', 'EPYC 9254', '{"tdp_w": 200, "architecture": "x86_64", "base_freq_ghz": 2.9, "cores_per_cpu": 24, "boost_freq_ghz": 4.15}', 1, 104, 'Genoa', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(224, 'cpu', 'AMD', 'EPYC 9124', '{"tdp_w": 200, "architecture": "x86_64", "base_freq_ghz": 3.0, "cores_per_cpu": 16, "boost_freq_ghz": 3.7}', 1, 105, 'Genoa', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(225, 'cpu', 'AMD', 'EPYC 7763', '{"tdp_w": 280, "architecture": "x86_64", "base_freq_ghz": 2.45, "cores_per_cpu": 64, "boost_freq_ghz": 3.5}', 1, 110, 'Milan', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(226, 'cpu', 'AMD', 'EPYC 7713', '{"tdp_w": 225, "architecture": "x86_64", "base_freq_ghz": 2.0, "cores_per_cpu": 64, "boost_freq_ghz": 3.675}', 1, 111, 'Milan', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(227, 'cpu', 'AMD', 'EPYC 7543', '{"tdp_w": 225, "architecture": "x86_64", "base_freq_ghz": 2.8, "cores_per_cpu": 32, "boost_freq_ghz": 3.7}', 1, 112, 'Milan', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(228, 'cpu', '海光', 'C86-3185', '{"tdp_w": 95, "architecture": "x86_64", "base_freq_ghz": 2.0, "cores_per_cpu": 8, "boost_freq_ghz": 2.5}', 1, 200, '海光 C86 系列', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(229, 'cpu', '海光', 'C86-3280', '{"tdp_w": 150, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 16, "boost_freq_ghz": 2.8}', 1, 201, '海光 C86 系列', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(230, 'cpu', '海光', 'C86-5380', '{"tdp_w": 200, "architecture": "x86_64", "base_freq_ghz": 2.5, "cores_per_cpu": 32, "boost_freq_ghz": 3.0}', 1, 202, '海光 C86 系列', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(231, 'cpu', '华为', '鲲鹏 920-7260', '{"tdp_w": 180, "architecture": "ARM64", "base_freq_ghz": 2.6, "cores_per_cpu": 64, "boost_freq_ghz": 3.0}', 1, 210, '鲲鹏 920', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(232, 'cpu', '华为', '鲲鹏 920-5250', '{"tdp_w": 150, "architecture": "ARM64", "base_freq_ghz": 2.6, "cores_per_cpu": 48, "boost_freq_ghz": 3.0}', 1, 211, '鲲鹏 920', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(233, 'memory', 'Samsung', 'M321R4GA3BB6-CQK', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 10, 'DDR5-4800 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(234, 'memory', 'Samsung', 'M321R8GA3BB6-CQK', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 11, 'DDR5-4800 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(235, 'memory', 'Samsung', 'M321RAGA3BB6-CQK', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 128, "form_factor": "RDIMM"}', 1, 12, 'DDR5-4800 128GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(236, 'memory', 'SK Hynix', 'HMCG88AEBRA115N', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 20, 'DDR5-4800 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(237, 'memory', 'SK Hynix', 'HMCG78AEBRA109N', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 21, 'DDR5-4800 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(238, 'memory', 'Micron', 'MTC20F2085S1RC48BA1', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 30, 'DDR5-4800 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(239, 'memory', 'Micron', 'MTC40F2046S1RC48BA1', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 31, 'DDR5-4800 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(240, 'memory', 'Samsung', 'M393A4K40DB3-CWE', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 100, 'DDR4-3200 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(241, 'memory', 'Samsung', 'M393A8K40DB3-CWE', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 101, 'DDR4-3200 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(242, 'memory', 'Samsung', 'M393A2K40CB3-CWE', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 16, "form_factor": "RDIMM"}', 1, 102, 'DDR4-3200 16GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(243, 'memory', 'SK Hynix', 'HMAA4GR7AJR8N-XN', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 110, 'DDR4-3200 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(244, 'memory', 'SK Hynix', 'HMAA8GR7AJR8N-XN', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 111, 'DDR4-3200 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(245, 'memory', 'Micron', 'MTA36ASF4G72PZ-2G6E1', '{"ecc": true, "type": "DDR4", "speed_mhz": 2666, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 120, 'DDR4-2666 32GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(246, 'memory', 'Micron', 'MTA36ASF8G72PZ-2G6E1', '{"ecc": true, "type": "DDR4", "speed_mhz": 2666, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 121, 'DDR4-2666 64GB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(247, 'memory', '长鑫存储', 'CXDQ5A8AM-CG', '{"ecc": false, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 16, "form_factor": "UDIMM"}', 1, 200, 'DDR4-3200 16GB 消费级', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(248, 'memory', '记忆科技', 'RAMAXEL DDR4-3200 32GB', '{"ecc": true, "type": "DDR4", "speed_mhz": 3200, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 210, 'DDR4-3200 32GB 国产', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(249, 'memory', '记忆科技', 'RAMAXEL DDR5-4800 64GB', '{"ecc": true, "type": "DDR5", "speed_mhz": 4800, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 211, 'DDR5-4800 64GB 国产', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(250, 'disk', 'Samsung', 'PM1733a', '{"capacity_gb": 15360, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 28000, "interface_type": "NVMe"}', 1, 11, 'U.2 NVMe 15.36TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(251, 'disk', 'Samsung', 'PM893', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 14000, "interface_type": "SATA"}', 1, 21, 'SATA SSD 7.68TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(252, 'disk', 'Intel', 'D7-P5520', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 31, 'U.2 NVMe 7.68TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(253, 'disk', 'Intel', 'D3-S4520', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 7000, "interface_type": "SATA"}', 1, 41, 'SATA SSD 3.84TB', '2026-07-13 12:56:35', '2026-07-28 09:30:26', NULL, 'global'),
(254, 'disk', 'Micron', '7450 PRO', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 51, 'U.2 NVMe 7.68TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(255, 'disk', 'Micron', '5400 PRO', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 14000, "interface_type": "SATA"}', 1, 61, 'SATA SSD 7.68TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(256, 'disk', 'Kioxia', 'CM7-R', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 71, 'U.2 NVMe 7.68TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(257, 'disk', 'WD', 'SN640', '{"capacity_gb": 15360, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 28000, "interface_type": "NVMe"}', 1, 81, 'U.2 NVMe 15.36TB', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(258, 'disk', 'Seagate', 'Exos X18', '{"capacity_gb": 18000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 100, '3.5" SATA 18TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(259, 'disk', 'Seagate', 'Exos X20', '{"capacity_gb": 20000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 101, '3.5" SATA 20TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(260, 'disk', 'Seagate', 'Exos X22', '{"capacity_gb": 22000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 102, '3.5" SATA 22TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(261, 'disk', 'WD', 'Ultrastar DC HC560', '{"capacity_gb": 20000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 110, '3.5" SATA 20TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(262, 'disk', 'WD', 'Ultrastar DC HC580', '{"capacity_gb": 24000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 111, '3.5" SATA 24TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(263, 'disk', 'Toshiba', 'MG10ACA', '{"capacity_gb": 20000, "form_factor": "3.5\\"", "storage_type": "HDD", "endurance_tbw": 0, "interface_type": "SATA"}', 1, 120, '3.5" SATA 20TB', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(264, 'disk', '长江存储', 'PE310', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 201, 'U.2 NVMe 7.68TB 国产', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(265, 'disk', '忆恒创源', 'PBlaze6 6530', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 211, 'U.2 NVMe 7.68TB 国产', '2026-07-13 12:56:35', '2026-07-28 09:01:17', NULL, 'global'),
(266, 'nic', 'Intel', 'X710-DA2', '{"port_type": "SFP+", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 10, '双口 10G SFP+', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(267, 'nic', 'Intel', 'X710-DA4', '{"port_type": "SFP+", "port_count": 4, "port_speed": "10G", "form_factor": "PCIe"}', 1, 11, '四口 10G SFP+', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(268, 'nic', 'Intel', 'X550-T2', '{"port_type": "RJ45", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 20, '双口 10G 电口', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(269, 'nic', 'Intel', 'E810-CQDA2', '{"port_type": "QSFP28", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 30, '双口 100G QSFP28', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(270, 'nic', 'Intel', 'E810-XXVDA2', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 31, '双口 25G SFP28', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(271, 'nic', 'Intel', 'E810-XXVDA4', '{"port_type": "SFP28", "port_count": 4, "port_speed": "25G", "form_factor": "PCIe"}', 1, 32, '四口 25G SFP28', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(272, 'nic', 'NVIDIA', 'ConnectX-6 Dx', '{"port_type": "QSFP28", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 50, '双口 100G，智能卸载', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(273, 'nic', 'NVIDIA', 'ConnectX-6 Lx', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 51, '双口 25G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(274, 'nic', 'NVIDIA', 'ConnectX-7', '{"port_type": "QSFP-DD", "port_count": 1, "port_speed": "400G", "form_factor": "PCIe"}', 1, 52, '单口 400G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(275, 'nic', 'NVIDIA', 'BlueField-3', '{"port_type": "QSFP112", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 60, 'DPU 智能网卡 100G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(276, 'nic', 'Broadcom', 'BCM57414', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 70, '双口 25G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(277, 'nic', 'Broadcom', 'BCM57508', '{"port_type": "QSFP28", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 71, '双口 100G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(278, 'nic', 'Marvell', 'QLogic QL41112', '{"port_type": "RJ45", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 80, '双口 10G 电口', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(279, 'nic', 'Marvell', 'QLogic QL41212', '{"port_type": "SFP+", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 81, '双口 10G SFP+', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(280, 'nic', '华为', 'SP570', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 200, '双口 25G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(281, 'nic', '华为', 'SP580', '{"port_type": "QSFP28", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 201, '双口 100G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(282, 'nic', '新华三', 'NIC-10GE-2P-520F-B2', '{"port_type": "SFP+", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 210, '双口 10G SFP+', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(283, 'nic', '新华三', 'NIC-25GE-2P-620F-B2', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 211, '双口 25G SFP28', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(284, 'nic', '浪潮', 'INSPUR 10G 双口', '{"port_type": "SFP+", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 220, '双口 10G SFP+', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(285, 'nic', '浪潮', 'INSPUR 25G 双口', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 221, '双口 25G SFP28', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(286, 'nic', 'Intel', 'X710-T2L (OCP)', '{"port_type": "RJ45", "port_count": 2, "port_speed": "10G", "form_factor": "OCP"}', 1, 300, 'OCP 3.0 双口 10G 电口', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(287, 'nic', 'NVIDIA', 'ConnectX-6 Lx (OCP)', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "OCP"}', 1, 301, 'OCP 3.0 双口 25G', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(288, 'gpu', 'NVIDIA', 'H100 SXM5 80GB', '{"tdp_w": 700, "vram_gb": 80, "interface": "SXM5", "cuda_cores": 16896, "fp32_tflops": 67, "gpu_memory_type": "HBM3"}', 1, 10, 'Hopper 架构，旗舰训练卡', '2026-07-13 12:56:35', '2026-07-13 12:56:35', NULL, 'global'),
(289, 'gpu', 'NVIDIA', 'H100 PCIe 80GB', '{"tdp_w": 350, "vram_gb": 80, "interface": "PCIe 5.0", "cuda_cores": 14592, "fp32_tflops": 51, "gpu_memory_type": "HBM3"}', 1, 11, 'Hopper 架构，PCIe 版', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(290, 'gpu', 'NVIDIA', 'H200 SXM5 141GB', '{"tdp_w": 700, "vram_gb": 141, "interface": "SXM5", "cuda_cores": 16896, "fp32_tflops": 67, "gpu_memory_type": "HBM3e"}', 1, 12, 'Hopper 升级版，大显存', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(291, 'gpu', 'NVIDIA', 'B200 SXM5 192GB', '{"tdp_w": 1000, "vram_gb": 192, "interface": "SXM5", "cuda_cores": 18432, "fp32_tflops": 90, "gpu_memory_type": "HBM3e"}', 1, 13, 'Blackwell 架构，次世代', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(292, 'gpu', 'NVIDIA', 'A100 SXM4 80GB', '{"tdp_w": 400, "vram_gb": 80, "interface": "SXM4", "cuda_cores": 6912, "fp32_tflops": 19.5, "gpu_memory_type": "HBM2e"}', 1, 20, 'Ampere 架构，主流训练卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(293, 'gpu', 'NVIDIA', 'A100 PCIe 80GB', '{"tdp_w": 300, "vram_gb": 80, "interface": "PCIe 4.0", "cuda_cores": 6912, "fp32_tflops": 19.5, "gpu_memory_type": "HBM2e"}', 1, 21, 'Ampere 架构，PCIe 版', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(294, 'gpu', 'NVIDIA', 'A100 SXM4 40GB', '{"tdp_w": 400, "vram_gb": 40, "interface": "SXM4", "cuda_cores": 6912, "fp32_tflops": 19.5, "gpu_memory_type": "HBM2e"}', 1, 22, 'Ampere 架构，40GB 版', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(295, 'gpu', 'NVIDIA', 'L40S 48GB', '{"tdp_w": 350, "vram_gb": 48, "interface": "PCIe 4.0", "cuda_cores": 18176, "fp32_tflops": 91.6, "gpu_memory_type": "GDDR6X"}', 1, 30, 'Ada Lovelace 架构，推理+图形', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(296, 'gpu', 'NVIDIA', 'L40 48GB', '{"tdp_w": 300, "vram_gb": 48, "interface": "PCIe 4.0", "cuda_cores": 18176, "fp32_tflops": 90.5, "gpu_memory_type": "GDDR6X"}', 1, 31, 'Ada Lovelace 架构，图形渲染', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(297, 'gpu', 'NVIDIA', 'A30 24GB', '{"tdp_w": 165, "vram_gb": 24, "interface": "PCIe 4.0", "cuda_cores": 3584, "fp32_tflops": 10.3, "gpu_memory_type": "HBM2e"}', 1, 40, 'Ampere 架构，推理入门', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(298, 'gpu', 'NVIDIA', 'A10 24GB', '{"tdp_w": 150, "vram_gb": 24, "interface": "PCIe 4.0", "cuda_cores": 9216, "fp32_tflops": 31.2, "gpu_memory_type": "GDDR6"}', 1, 41, 'Ampere 架构，推理+图形', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(299, 'gpu', 'NVIDIA', 'T4 16GB', '{"tdp_w": 70, "vram_gb": 16, "interface": "PCIe 3.0", "cuda_cores": 2560, "fp32_tflops": 8.1, "gpu_memory_type": "GDDR6"}', 1, 50, 'Turing 架构，低功耗推理', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(300, 'gpu', 'AMD', 'Instinct MI300X 192GB', '{"tdp_w": 750, "vram_gb": 192, "interface": "OAM", "fp32_tflops": 81.7, "compute_units": 304, "gpu_memory_type": "HBM3"}', 1, 100, 'CDNA 3 架构，大显存', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(301, 'gpu', 'AMD', 'Instinct MI250X 128GB', '{"tdp_w": 560, "vram_gb": 128, "interface": "OAM", "fp32_tflops": 47.9, "compute_units": 232, "gpu_memory_type": "HBM2e"}', 1, 110, 'CDNA 2 架构', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(302, 'gpu', 'AMD', 'Instinct MI210 64GB', '{"tdp_w": 300, "vram_gb": 64, "interface": "PCIe 4.0", "fp32_tflops": 22.6, "compute_units": 104, "gpu_memory_type": "HBM2e"}', 1, 120, 'CDNA 2 架构，PCIe 版', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(303, 'gpu', 'Intel', 'Data Center GPU Max 1550', '{"tdp_w": 600, "vram_gb": 128, "interface": "PCIe 5.0", "fp32_tflops": 52.4, "execution_units": 128, "gpu_memory_type": "HBM2e"}', 1, 150, 'Ponte Vecchio 架构', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(304, 'gpu', 'Intel', 'Data Center GPU Max 1100', '{"tdp_w": 300, "vram_gb": 48, "interface": "PCIe 5.0", "fp32_tflops": 22.3, "execution_units": 56, "gpu_memory_type": "HBM2e"}', 1, 151, 'Ponte Vecchio 架构，入门', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(305, 'gpu', '华为', '昇腾 910B 64GB', '{"tdp_w": 310, "vram_gb": 64, "ai_cores": 80, "interface": "PCIe 4.0", "fp32_tflops": 32, "gpu_memory_type": "HBM2e"}', 1, 200, '达芬奇架构，训练卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(306, 'gpu', '华为', '昇腾 310P 24GB', '{"tdp_w": 75, "vram_gb": 24, "ai_cores": 8, "interface": "PCIe 4.0", "fp32_tflops": 7.2, "gpu_memory_type": "LPDDR4X"}', 1, 210, '达芬奇架构，推理卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global');
INSERT INTO `component_templates` (`id`, `category`, `brand`, `model`, `spec`, `is_active`, `sort_order`, `remark`, `created_at`, `updated_at`, `customer_id`, `scope`) VALUES
(307, 'gpu', '寒武纪', '思元 370-S4 32GB', '{"tdp_w": 150, "vram_gb": 32, "ai_cores": 32, "interface": "PCIe 4.0", "fp32_tflops": 12, "gpu_memory_type": "LPDDR5"}', 1, 220, '推理卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(308, 'gpu', '寒武纪', '思元 590 64GB', '{"tdp_w": 350, "vram_gb": 64, "ai_cores": 64, "interface": "PCIe 4.0", "fp32_tflops": 28, "gpu_memory_type": "HBM2e"}', 1, 221, '训练卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(309, 'gpu', '壁仞', 'BR100 64GB', '{"tdp_w": 550, "vram_gb": 64, "interface": "OAM", "fp32_tflops": 40, "compute_units": 128, "gpu_memory_type": "HBM2e"}', 1, 230, '训练卡', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(310, 'gpu', '摩尔线程', 'MTT S4000 32GB', '{"tdp_w": 200, "vram_gb": 32, "interface": "PCIe 4.0", "fp32_tflops": 15, "compute_units": 64, "gpu_memory_type": "GDDR6"}', 1, 240, '推理+图形', '2026-07-13 12:56:36', '2026-07-13 12:56:36', NULL, 'global'),
(311, 'nic', 'BMC', 'BMC', '{"port_type": "RJ45", "port_count": 1, "port_speed": "1G", "form_factor": "Onboard"}', 1, 0, 'IPMI远程管理卡', '2026-07-15 11:16:32', '2026-07-15 11:16:32', NULL, 'global'),
(312, 'cpu', 'Intel', 'Xeon Platinum 8280', '{"tdp_w": 205, "architecture": "x86_64", "base_freq_ghz": 2.7, "cores_per_cpu": 28, "boost_freq_ghz": 4.0}', 1, 55, 'Cascade Lake，旗舰', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(313, 'cpu', 'Intel', 'Xeon Gold 6248', '{"tdp_w": 150, "architecture": "x86_64", "base_freq_ghz": 2.5, "cores_per_cpu": 20, "boost_freq_ghz": 3.9}', 1, 56, 'Cascade Lake', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(314, 'cpu', 'Intel', 'Xeon Gold 6230', '{"tdp_w": 125, "architecture": "x86_64", "base_freq_ghz": 2.1, "cores_per_cpu": 20, "boost_freq_ghz": 3.9}', 1, 57, 'Cascade Lake', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(315, 'cpu', 'Intel', 'Xeon Silver 4210', '{"tdp_w": 85, "architecture": "x86_64", "base_freq_ghz": 2.2, "cores_per_cpu": 10, "boost_freq_ghz": 3.2}', 1, 58, 'Cascade Lake', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(316, 'cpu', 'Intel', 'Xeon Bronze 3204', '{"tdp_w": 85, "architecture": "x86_64", "base_freq_ghz": 1.9, "cores_per_cpu": 6, "boost_freq_ghz": 2.0}', 1, 59, 'Cascade Lake，入门', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(317, 'cpu', 'AMD', 'EPYC 9575F', '{"tdp_w": 400, "architecture": "x86_64", "base_freq_ghz": 3.3, "cores_per_cpu": 64, "boost_freq_ghz": 5.0}', 1, 106, 'Turin，高主频', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(318, 'cpu', 'AMD', 'EPYC 9455', '{"tdp_w": 300, "architecture": "x86_64", "base_freq_ghz": 3.15, "cores_per_cpu": 48, "boost_freq_ghz": 4.8}', 1, 107, 'Turin', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(319, 'cpu', 'AMD', 'EPYC 9255', '{"tdp_w": 200, "architecture": "x86_64", "base_freq_ghz": 3.25, "cores_per_cpu": 24, "boost_freq_ghz": 4.8}', 1, 108, 'Turin', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(320, 'cpu', 'AMD', 'EPYC 9754', '{"tdp_w": 360, "architecture": "x86_64", "base_freq_ghz": 2.25, "cores_per_cpu": 128, "boost_freq_ghz": 3.1}', 1, 113, 'Bergamo，128核', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(321, 'cpu', '华为', '鲲鹏 920-3210', '{"tdp_w": 90, "architecture": "ARM64", "base_freq_ghz": 2.6, "cores_per_cpu": 24, "boost_freq_ghz": 3.0}', 1, 212, '鲲鹏 920，低功耗', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(322, 'cpu', '华为', '鲲鹏 920-3226', '{"tdp_w": 120, "architecture": "ARM64", "base_freq_ghz": 2.6, "cores_per_cpu": 48, "boost_freq_ghz": 3.0}', 1, 213, '鲲鹏 920', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(323, 'cpu', '飞腾', 'FT-2000+', '{"tdp_w": 110, "architecture": "ARM64", "base_freq_ghz": 2.0, "cores_per_cpu": 64, "boost_freq_ghz": 2.4}', 1, 250, '国产 ARM，服务器', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(324, 'cpu', '飞腾', 'S2500', '{"tdp_w": 150, "architecture": "ARM64", "base_freq_ghz": 2.1, "cores_per_cpu": 64, "boost_freq_ghz": 2.2}', 1, 251, '国产 ARM，多路', '2026-07-28 09:01:16', '2026-07-28 09:01:16', NULL, 'global'),
(325, 'memory', 'Samsung', 'M321R8GA0PB2-CCP', '{"ecc": true, "type": "DDR5", "speed_mhz": 5600, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 13, 'DDR5-5600 64GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(326, 'memory', 'Samsung', 'M321R4GA0PB2-CCP', '{"ecc": true, "type": "DDR5", "speed_mhz": 5600, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 14, 'DDR5-5600 32GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(327, 'memory', 'SK Hynix', 'HMCG88AEBRA168N', '{"ecc": true, "type": "DDR5", "speed_mhz": 5600, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 22, 'DDR5-5600 64GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(328, 'memory', 'Micron', 'MTC40F2046S1RC56BD1', '{"ecc": true, "type": "DDR5", "speed_mhz": 5600, "capacity_gb": 64, "form_factor": "RDIMM"}', 1, 32, 'DDR5-5600 64GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(329, 'memory', 'Samsung', 'M393A4K40CB3-CVF', '{"ecc": true, "type": "DDR4", "speed_mhz": 2933, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 130, 'DDR4-2933 32GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(330, 'memory', 'SK Hynix', 'HMA84GR7DJR4N-XN', '{"ecc": true, "type": "DDR4", "speed_mhz": 2933, "capacity_gb": 32, "form_factor": "RDIMM"}', 1, 131, 'DDR4-2933 32GB', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(331, 'disk', 'Samsung', 'PM9A3', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 14, 'U.2 NVMe 7.68TB 主流', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(332, 'disk', 'Kioxia', 'CM6-R', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 73, 'U.2 NVMe 7.68TB PCIe4.0', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(333, 'disk', 'Solidigm', 'D5-P5316', '{"capacity_gb": 30720, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 45000, "interface_type": "NVMe"}', 1, 91, 'U.2 QLC 30.72TB 大容量', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(334, 'disk', 'Micron', '6500 ION', '{"capacity_gb": 30720, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 40000, "interface_type": "NVMe"}', 1, 62, 'U.2 30.72TB 大容量', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(335, 'nic', 'NVIDIA', 'ConnectX-5 Ex', '{"port_type": "QSFP28", "port_count": 2, "port_speed": "100G", "form_factor": "PCIe"}', 1, 54, '双口 100G QSFP28', '2026-07-28 09:01:17', '2026-07-28 13:04:10', NULL, 'global'),
(336, 'nic', 'Intel', 'XXV710-DA2', '{"port_type": "SFP28", "port_count": 2, "port_speed": "25G", "form_factor": "PCIe"}', 1, 33, '双口 25G SFP28', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(337, 'nic', 'NVIDIA', 'ConnectX-6 (200G)', '{"port_type": "QSFP56", "port_count": 2, "port_speed": "200G", "form_factor": "PCIe"}', 1, 56, '双口 200G QSFP56', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(338, 'nic', '华为', 'SP310', '{"port_type": "SFP+", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 202, '双口 10G SFP+', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(339, 'nic', '华为', 'SP680', '{"port_type": "QSFP28", "port_count": 4, "port_speed": "100G", "form_factor": "PCIe"}', 1, 203, '四口 100G QSFP28', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(340, 'nic', 'Broadcom', 'BCM57412', '{"port_type": "RJ45", "port_count": 2, "port_speed": "10G", "form_factor": "PCIe"}', 1, 72, '双口 10G 电口', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(341, 'gpu', 'NVIDIA', 'A800 SXM4 80GB', '{"tdp_w": 400, "vram_gb": 80, "interface": "SXM4", "cuda_cores": 6912, "fp32_tflops": 19.5, "gpu_memory_type": "HBM2e"}', 1, 23, 'Ampere，中国特供版', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(342, 'gpu', 'NVIDIA', 'H800 SXM5 80GB', '{"tdp_w": 700, "vram_gb": 80, "interface": "SXM5", "cuda_cores": 16896, "fp32_tflops": 67, "gpu_memory_type": "HBM3"}', 1, 14, 'Hopper，中国特供版', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(343, 'gpu', 'NVIDIA', 'L20 48GB', '{"tdp_w": 350, "vram_gb": 48, "interface": "PCIe 4.0", "cuda_cores": 11776, "fp32_tflops": 59.8, "gpu_memory_type": "GDDR6"}', 1, 32, 'Ada Lovelace，推理主流', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(344, 'gpu', 'NVIDIA', 'L4 24GB', '{"tdp_w": 72, "vram_gb": 24, "interface": "PCIe 4.0", "cuda_cores": 7424, "fp32_tflops": 30.3, "gpu_memory_type": "GDDR6"}', 1, 42, 'Ada Lovelace，低功耗推理', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(345, 'gpu', 'NVIDIA', 'RTX 6000 Ada 48GB', '{"tdp_w": 300, "vram_gb": 48, "interface": "PCIe 4.0", "cuda_cores": 18176, "fp32_tflops": 91.1, "gpu_memory_type": "GDDR6"}', 1, 52, 'Ada Lovelace，图形/推理', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(346, 'gpu', '沐曦', 'C500 64GB', '{"tdp_w": 350, "vram_gb": 64, "interface": "PCIe 4.0", "fp32_tflops": 26, "compute_units": 128, "gpu_memory_type": "HBM2e"}', 1, 250, '训练卡', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(347, 'gpu', '天数智芯', '天垓 100 32GB', '{"tdp_w": 250, "vram_gb": 32, "interface": "PCIe 4.0", "fp32_tflops": 18, "compute_units": 64, "gpu_memory_type": "HBM2"}', 1, 260, '训练卡', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(348, 'gpu', '摩尔线程', 'MTT S3000 32GB', '{"tdp_w": 250, "vram_gb": 32, "interface": "PCIe 4.0", "fp32_tflops": 15.2, "compute_units": 64, "gpu_memory_type": "GDDR6"}', 1, 241, '推理+图形', '2026-07-28 09:01:17', '2026-07-28 09:01:17', NULL, 'global'),
(349, 'disk', 'Samsung', 'PM1733a', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 10, 'U.2 NVMe 7.68TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(350, 'disk', 'Samsung', 'PM893', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 7000, "interface_type": "SATA"}', 1, 20, 'SATA SSD 3.84TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(351, 'disk', 'Intel', 'D7-P5520', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 30, 'U.2 NVMe 3.84TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(352, 'disk', 'Intel', 'D3-S4520', '{"capacity_gb": 1920, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 3500, "interface_type": "SATA"}', 1, 40, 'SATA SSD 1.92TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(353, 'disk', 'Micron', '7450 PRO', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 50, 'U.2 NVMe 3.84TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(354, 'disk', 'Micron', '5400 PRO', '{"capacity_gb": 1920, "form_factor": "2.5\\"", "storage_type": "SSD", "endurance_tbw": 3500, "interface_type": "SATA"}', 1, 60, 'SATA SSD 1.92TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(355, 'disk', 'Kioxia', 'CM7-R', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 70, 'U.2 NVMe 3.84TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(356, 'disk', 'WD', 'SN640', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 14000, "interface_type": "NVMe"}', 1, 80, 'U.2 NVMe 7.68TB', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(357, 'disk', '长江存储', 'PE310', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 200, 'U.2 NVMe 3.84TB 国产', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(358, 'disk', '忆恒创源', 'PBlaze6 6530', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 210, 'U.2 NVMe 3.84TB 国产', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(359, 'disk', 'Samsung', 'PM9A3', '{"capacity_gb": 1920, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 3500, "interface_type": "NVMe"}', 1, 12, 'U.2 NVMe 1.92TB 主流', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(360, 'disk', 'Samsung', 'PM9A3', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 13, 'U.2 NVMe 3.84TB 主流', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(361, 'disk', 'Kioxia', 'CM6-R', '{"capacity_gb": 3840, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 7000, "interface_type": "NVMe"}', 1, 72, 'U.2 NVMe 3.84TB PCIe4.0', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(362, 'disk', 'Solidigm', 'D5-P5316', '{"capacity_gb": 15360, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 22000, "interface_type": "NVMe"}', 1, 90, 'U.2 QLC 15.36TB 大容量', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(363, 'disk', 'Micron', '6500 ION', '{"capacity_gb": 7680, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 10000, "interface_type": "NVMe"}', 1, 60, 'U.2 7.68TB 大容量', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(364, 'disk', 'Micron', '6500 ION', '{"capacity_gb": 15360, "form_factor": "2.5\\"", "storage_type": "NVMe", "endurance_tbw": 20000, "interface_type": "NVMe"}', 1, 61, 'U.2 15.36TB 大容量', '2026-07-28 09:30:26', '2026-07-28 09:30:26', NULL, 'global'),
(365, 'gpu', 'NVIDIA', 'RTX PRO 6000 Blackwell 96GB', '{"tdp_w": 600, "vram_gb": 96, "interface": "PCIe 5.0", "cuda_cores": 24064, "fp32_tflops": 125, "gpu_memory_type": "GDDR7"}', 1, 53, 'Blackwell 架构，工作站旗舰 96GB', '2026-07-28 13:04:10', '2026-07-28 13:04:10', NULL, 'global'),
(366, 'gpu', 'NVIDIA', 'RTX PRO 6000D Blackwell 84GB', '{"tdp_w": 600, "vram_gb": 84, "interface": "PCIe 5.0", "cuda_cores": 19968, "fp32_tflops": 97, "gpu_memory_type": "GDDR7"}', 1, 54, 'Blackwell 架构，6000D 服务器版 84GB', '2026-07-28 13:04:10', '2026-07-28 13:04:10', NULL, 'global'),
(367, 'gpu', 'NVIDIA', 'RTX 5090 32GB', '{"tdp_w": 575, "vram_gb": 32, "interface": "PCIe 5.0", "cuda_cores": 21760, "fp32_tflops": 165, "gpu_memory_type": "GDDR7"}', 1, 55, 'Blackwell 架构，消费级旗舰', '2026-07-28 13:04:10', '2026-07-28 13:04:10', NULL, 'global'),
(368, 'gpu', 'NVIDIA', 'RTX 4090 24GB', '{"tdp_w": 450, "vram_gb": 24, "interface": "PCIe 4.0", "cuda_cores": 16384, "fp32_tflops": 82.6, "gpu_memory_type": "GDDR6X"}', 1, 56, 'Ada Lovelace 架构，消费级旗舰', '2026-07-28 13:04:10', '2026-07-28 13:04:10', NULL, 'global');

-- monitor_vendor_brands: 27 rows
DELETE FROM `monitor_vendor_brands`;
INSERT INTO `monitor_vendor_brands` (`enterprise_no`, `brand_name`, `label`, `device_type`, `enabled`, `sort_order`, `id`, `created_at`, `updated_at`) VALUES
('674', 'Dell EMC', 'DELL（服务器）', 'server', 1, 10, 1, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('232', 'HP ProLiant', 'HP（服务器）', 'server', 1, 20, 2, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('10876', 'Supermicro', 'Supermicro（服务器）', 'server', 1, 30, 3, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('19046', 'Lenovo ThinkSystem', 'Lenovo（服务器）', 'server', 1, 40, 4, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('437', 'IBM', 'IBM（服务器）', 'server', 1, 50, 5, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('161', 'Fujitsu PRIMERGY', 'Fujitsu（服务器）', 'server', 1, 60, 6, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('2011', 'Huawei TaiShan', 'Huawei（服务器）', 'server', 1, 70, 7, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('5855', 'Inspur', 'Inspur（服务器）', 'server', 1, 80, 8, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('9', 'Cisco', 'Cisco（网络）', 'network', 1, 10, 9, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('2011', 'Huawei VRP', 'Huawei（网络）', 'network', 1, 20, 10, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('25506', 'H3C Comware', 'H3C（网络）', 'network', 1, 30, 11, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('119', 'Juniper JUNOS', 'Juniper（网络）', 'network', 1, 40, 12, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('2636', 'F5 BIG-IP', 'F5 Networks（网络）', 'network', 1, 50, 13, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('45', 'Nortel', 'Nortel/Avaya（网络）', 'network', 1, 60, 14, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('1872', 'Ruijie', 'Ruijie（网络）', 'network', 1, 70, 15, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('4881', 'MikroTik RouterOS', 'MikroTik（网络）', 'network', 1, 80, 16, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('14988', 'TP-Link', 'TP-Link（网络）', 'network', 1, 90, 17, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('171', 'Extreme Networks', 'Extreme（网络）', 'network', 1, 100, 18, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('1588', 'Aruba', 'Aruba（网络）', 'network', 1, 110, 19, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('674', 'Dell EMC Storage', 'DELL（存储）', 'storage', 1, 10, 20, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('2469', 'NetApp', 'NetApp（存储）', 'storage', 1, 20, 21, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('789', 'Hitachi VSP', 'Hitachi（存储）', 'storage', 1, 30, 22, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('1602', 'Pure Storage', 'Pure Storage（存储）', 'storage', 1, 40, 23, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('19046', 'Lenovo Storage', 'Lenovo（存储）', 'storage', 1, 50, 24, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('8072', 'VMware ESXi', 'VMware（虚拟化）', 'other', 1, 10, 25, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('311', 'Microsoft Windows', 'Microsoft（系统）', 'other', 1, 20, 26, '2026-08-07 12:19:47', '2026-08-07 12:19:47'),
('42', 'Oracle Solaris', 'Sun/Oracle（系统）', 'other', 1, 30, 27, '2026-08-07 12:19:47', '2026-08-07 12:19:47');

-- monitor_oid_category_rules: 159 rows
DELETE FROM `monitor_oid_category_rules`;
INSERT INTO `monitor_oid_category_rules` (`prefix`, `category`, `label`, `device_type`, `vendor_id`, `priority`, `enabled`, `id`, `created_at`, `updated_at`) VALUES
('1.3.6.1.2.1.1.3.0', 'system_uptime', '系统运行时间', NULL, NULL, 10, 1, 414, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.1.1.0', 'sys_descr', '系统描述', NULL, NULL, 10, 1, 415, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.1.5.0', 'sys_name', '系统名称', NULL, NULL, 10, 1, 416, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.7', 'if_status', '端口状态', NULL, NULL, 10, 1, 417, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.10', 'if_in_octets', '入流量', NULL, NULL, 10, 1, 418, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.16', 'if_out_octets', '出流量', NULL, NULL, 10, 1, 419, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.14', 'if_in_errors', '入错包', NULL, NULL, 10, 1, 420, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.20', 'if_out_errors', '出错包', NULL, NULL, 10, 1, 421, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.13', 'if_in_discards', '入丢包', NULL, NULL, 10, 1, 422, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.19', 'if_out_discards', '出丢包', NULL, NULL, 10, 1, 423, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.5', 'if_speed', '端口速率', NULL, NULL, 10, 1, 424, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.2.2.1.2', 'if_descr', '端口描述', NULL, NULL, 10, 1, 425, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.25.3.3.1.2', 'cpu_usage', 'CPU利用率', 'server', NULL, 10, 1, 426, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.25.2.3.1.5', 'storage_size', '存储总量', 'server', NULL, 10, 1, 427, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.25.2.3.1.6', 'storage_used', '存储已用', 'server', NULL, 10, 1, 428, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.2.1.25.1.1.0', 'hr_uptime', 'HR系统运行时间', 'server', NULL, 10, 1, 429, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.2', 'temperature', 'DELL温度', 'server', '674', 200, 1, 430, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.11', 'temperature', 'DELL温度', 'server', '674', 200, 1, 431, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.1', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 432, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.3', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 433, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.4', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 434, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.5', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 435, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.6', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 436, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.7', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 437, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.8', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 438, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.9', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 439, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.10', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 440, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40.1.12', 'threshold_descriptor', 'DELL温度阈值描述', 'server', '674', 200, 1, 441, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.300.40', 'threshold_descriptor', 'DELL温度描述', 'server', '674', 100, 1, 442, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.2', 'voltage', 'DELL电压', 'server', '674', 200, 1, 443, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.11', 'voltage', 'DELL电压', 'server', '674', 200, 1, 444, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.1', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 445, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.3', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 446, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.4', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 447, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.5', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 448, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.6', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 449, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.7', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 450, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.8', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 451, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.9', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 452, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.10', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 453, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20.1.12', 'threshold_descriptor', 'DELL电压阈值描述', 'server', '674', 200, 1, 454, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.600.20', 'threshold_descriptor', 'DELL电压描述', 'server', '674', 100, 1, 455, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.2', 'fan', 'DELL风扇', 'server', '674', 200, 1, 456, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.11', 'fan', 'DELL风扇', 'server', '674', 200, 1, 457, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.1', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 458, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.3', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 459, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.4', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 460, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.5', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 461, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.6', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 462, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.7', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 463, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.8', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 464, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.9', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 465, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.10', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 466, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12.1.12', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 467, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.12', 'threshold_descriptor', 'DELL风扇描述', 'server', '674', 100, 1, 468, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.2', 'fan', 'DELL风扇', 'server', '674', 200, 1, 469, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.11', 'fan', 'DELL风扇', 'server', '674', 200, 1, 470, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.1', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 471, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.3', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 472, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.4', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 473, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.5', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 474, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.6', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 475, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.7', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 476, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.8', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 477, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.9', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 478, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.10', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 479, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20.1.12', 'threshold_descriptor', 'DELL风扇阈值描述', 'server', '674', 200, 1, 480, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.700.20', 'threshold_descriptor', 'DELL风扇描述', 'server', '674', 100, 1, 481, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.2', 'power_supply', 'DELL电源', 'server', '674', 200, 1, 482, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.11', 'power_supply', 'DELL电源', 'server', '674', 200, 1, 483, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.1', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 484, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.3', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 485, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.4', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 486, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.5', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 487, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.6', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 488, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.7', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 489, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.8', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 490, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.9', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 491, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.10', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 492, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80.1.12', 'threshold_descriptor', 'DELL电源阈值描述', 'server', '674', 200, 1, 493, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.1100.80', 'threshold_descriptor', 'DELL电源描述', 'server', '674', 100, 1, 494, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.2', 'memory', 'DELL内存', 'server', '674', 200, 1, 495, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.11', 'memory', 'DELL内存', 'server', '674', 200, 1, 496, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.1', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 497, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.3', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 498, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.4', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 499, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.5', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 500, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.6', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 501, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.7', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 502, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.8', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 503, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.9', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 504, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.10', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 505, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10.1.12', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 506, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.10', 'threshold_descriptor', 'DELL内存描述', 'server', '674', 100, 1, 507, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.2', 'memory', 'DELL内存', 'server', '674', 200, 1, 508, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.11', 'memory', 'DELL内存', 'server', '674', 200, 1, 509, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.1', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 510, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.3', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 511, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.4', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 512, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.5', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 513, '2026-08-13 15:58:16', '2026-08-13 15:58:16');
INSERT INTO `monitor_oid_category_rules` (`prefix`, `category`, `label`, `device_type`, `vendor_id`, `priority`, `enabled`, `id`, `created_at`, `updated_at`) VALUES
('1.3.6.1.4.1.674.10892.5.4.200.20.1.6', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 514, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.7', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 515, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.8', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 516, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.9', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 517, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.10', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 518, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20.1.12', 'threshold_descriptor', 'DELL内存阈值描述', 'server', '674', 200, 1, 519, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.200.20', 'threshold_descriptor', 'DELL内存描述', 'server', '674', 100, 1, 520, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.2', 'storage', 'DELL物理盘', 'server', '674', 200, 1, 521, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.11', 'storage', 'DELL物理盘', 'server', '674', 200, 1, 522, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.1', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 523, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.3', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 524, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.4', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 525, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.5', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 526, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.6', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 527, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.7', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 528, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.8', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 529, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.9', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 530, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.10', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 531, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10.1.12', 'threshold_descriptor', 'DELL物理盘阈值描述', 'server', '674', 200, 1, 532, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.10', 'threshold_descriptor', 'DELL物理盘描述', 'server', '674', 100, 1, 533, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.2', 'storage', 'DELL虚拟盘', 'server', '674', 200, 1, 534, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.11', 'storage', 'DELL虚拟盘', 'server', '674', 200, 1, 535, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.1', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 536, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.3', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 537, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.4', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 538, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.5', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 539, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.6', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 540, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.7', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 541, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.8', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 542, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.9', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 543, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.10', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 544, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20.1.12', 'threshold_descriptor', 'DELL虚拟盘阈值描述', 'server', '674', 200, 1, 545, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.20', 'threshold_descriptor', 'DELL虚拟盘描述', 'server', '674', 100, 1, 546, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.2', 'storage', 'DELL RAID', 'server', '674', 200, 1, 547, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.11', 'storage', 'DELL RAID', 'server', '674', 200, 1, 548, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.1', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 549, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.3', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 550, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.4', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 551, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.5', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 552, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.6', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 553, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.7', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 554, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.8', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 555, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.9', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 556, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.10', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 557, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30.1.12', 'threshold_descriptor', 'DELL RAID阈值描述', 'server', '674', 200, 1, 558, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.674.10892.5.4.40.30', 'threshold_descriptor', 'DELL RAID描述', 'server', '674', 100, 1, 559, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.1.1', 'temperature', 'HP温度读数', 'server', '232', 100, 1, 560, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.1.6', 'temperature', 'HP温度状态', 'server', '232', 100, 1, 561, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.2.1', 'fan', 'HP风扇转速', 'server', '232', 100, 1, 562, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.2.6', 'fan', 'HP风扇状态', 'server', '232', 100, 1, 563, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.3.1', 'power_supply', 'HP电源状态', 'server', '232', 100, 1, 564, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.232.1.2.10.1', 'temperature', 'HP温度探头读数', 'server', '232', 100, 1, 565, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.10876.2.1.1', 'temperature', 'Supermicro温度', 'server', '10876', 100, 1, 566, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.10876.2.1.2', 'fan', 'Supermicro风扇', 'server', '10876', 100, 1, 567, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.10876.2.1.3', 'voltage', 'Supermicro电压', 'server', '10876', 100, 1, 568, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.10876.2.1.4', 'power_supply', 'Supermicro电源', 'server', '10876', 100, 1, 569, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.19046.11.1.1', 'temperature', 'Lenovo温度', 'server', '19046', 100, 1, 570, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.19046.11.1.2', 'fan', 'Lenovo风扇', 'server', '19046', 100, 1, 571, '2026-08-13 15:58:16', '2026-08-13 15:58:16'),
('1.3.6.1.4.1.19046.11.1.3', 'voltage', 'Lenovo电压', 'server', '19046', 100, 1, 572, '2026-08-13 15:58:16', '2026-08-13 15:58:16');

-- monitor_metric_templates: 239 rows
DELETE FROM `monitor_metric_templates`;
INSERT INTO `monitor_metric_templates` (`id`, `metric_key`, `category`, `display_name`, `device_type`, `source`, `vendor`, `mib`, `oid_symbol`, `oid`, `zabbix_item_key`, `index_kind`, `metric_type`, `unit`, `poll_interval`, `threshold`, `severity_default`, `enabled`, `description`, `created_at`, `updated_at`, `runbook_url`, `runbook_title`) VALUES
(185, 'if_status', 'if_status', '端口状态', 'network', 'snmp', NULL, 'IF-MIB', 'ifOperStatus', '1.3.6.1.2.1.2.2.1.8', NULL, 'ifIndex', 'state', NULL, 60, '{"expected": "up"}', 'warn', 1, '交换机端口 up/down 状态（按订阅端口监控）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(186, 'if_in_octets', 'if_in_octets', '入流量', 'network', 'snmp', NULL, 'IF-MIB', 'ifInOctets', '1.3.6.1.2.1.2.2.1.10', NULL, 'ifIndex', 'counter', 'octets', 60, '{}', 'info', 1, '端口入方向字节数（Counter32，需差分计算速率）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(187, 'if_out_octets', 'if_out_octets', '出流量', 'network', 'snmp', NULL, 'IF-MIB', 'ifOutOctets', '1.3.6.1.2.1.2.2.1.16', NULL, 'ifIndex', 'counter', 'octets', 60, '{}', 'info', 1, '端口出方向字节数（Counter32，需差分计算速率）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(188, 'if_in_errors', 'if_in_errors', '入错包', 'network', 'snmp', NULL, 'IF-MIB', 'ifInErrors', '1.3.6.1.2.1.2.2.1.14', NULL, 'ifIndex', 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, '端口入方向错包数（超阈值触发告警）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(189, 'if_out_errors', 'if_out_errors', '出错包', 'network', 'snmp', NULL, 'IF-MIB', 'ifOutErrors', '1.3.6.1.2.1.2.2.1.20', NULL, 'ifIndex', 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, '端口出方向错包数（超阈值触发告警）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(190, 'if_in_discards', 'if_in_discards', '入丢包', 'network', 'snmp', NULL, 'IF-MIB', 'ifInDiscards', '1.3.6.1.2.1.2.2.1.13', NULL, 'ifIndex', 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, '端口入方向丢包数（IF-MIB ifInDiscards，超阈值触发告警）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(191, 'if_out_discards', 'if_out_discards', '出丢包', 'network', 'snmp', NULL, 'IF-MIB', 'ifOutDiscards', '1.3.6.1.2.1.2.2.1.19', NULL, 'ifIndex', 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, '端口出方向丢包数（IF-MIB ifOutDiscards，超阈值触发告警）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(192, 'if_utilization', 'if_utilization', '端口利用率', 'network', 'snmp', NULL, 'IF-MIB', 'ifHCInOctets/ifHCOutOctets', '1.3.6.1.2.1.31.1.1.1.6', NULL, 'ifIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, '端口带宽利用率（基于 ifHCInOctets/ifHCOutOctets 64位计数器差分）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(193, 'sys_uptime', 'system_uptime', '系统运行时间', 'network', 'snmp', NULL, 'SNMPv2-MIB', 'sysUpTime', '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'timeticks', 60, '{}', 'info', 1, '设备启动后的运行时间（重启检测：当前值 < 上次值）', '2026-08-14 13:14:50', '2026-08-20 14:01:31', NULL, NULL),
(194, 'cpu_usage', 'cpu_usage', 'CPU 利用率', 'network', 'snmp', NULL, 'HOST-RESOURCES-MIB', 'hrProcessorLoad', '1.3.6.1.2.1.25.3.3.1.2', NULL, 'hrDeviceIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, 'CPU 利用率（HOST-RESOURCES-MIB 通用，华为/H3C/思科均支持）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(195, 'memory_usage', 'memory_usage', '内存利用率', 'network', 'snmp', NULL, 'HOST-RESOURCES-MIB', 'hrStorageUsed/hrStorageSize', '1.3.6.1.2.1.25.2.3.1.6', NULL, 'hrStorageIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 85}', 'warn', 1, '内存利用率（HOST-RESOURCES-MIB::hrStorageTable）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(196, 'cpu_usage', 'cpu_usage', 'CPU 利用率(华为)', 'network', 'snmp', '2011', 'HUAWEI-MIB', 'hwCpuDevUsage', '1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5', NULL, 'hwEntityIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, '华为设备 CPU 利用率（HUAWEI-MIB::hwCpuDevUsage）', '2026-08-14 13:14:50', '2026-08-20 15:01:51', NULL, NULL),
(197, 'memory_usage', 'memory_usage', '内存利用率(华为)', 'network', 'snmp', '2011', 'HUAWEI-MIB', 'hwMemUsage', '1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7', NULL, 'hwEntityIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 85}', 'warn', 1, '华为设备内存利用率（HUAWEI-MIB::hwMemUsage）', '2026-08-14 13:14:50', '2026-08-20 15:01:51', NULL, NULL),
(198, 'temperature', 'temperature', '温度(华为)', 'network', 'snmp', '2011', 'HUAWEI-MIB', 'hwEntityTemperature', '1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11', NULL, 'hwEntityIndex', 'gauge', 'Celsius', 60, '{"crit": 75, "warn": 60}', 'warn', 1, '华为设备温度（HUAWEI-MIB::hwEntityTemperature）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(199, 'cpu_usage', 'cpu_usage', 'CPU 利用率(H3C)', 'network', 'snmp', '25506', 'HH3C-OAM-MIB', 'hh3cDevMgrCPUUtil', '1.3.6.1.4.1.25506.2.6.1.1.1.1.6', NULL, 'hh3cDevMgrIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, 'H3C 设备 CPU 利用率（HH3C-OAM-MIB::hh3cDevMgrCPUUtil）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(200, 'memory_usage', 'memory_usage', '内存利用率(H3C)', 'network', 'snmp', '25506', 'HH3C-OAM-MIB', 'hh3cDevMgrMemoryUtil', '1.3.6.1.4.1.25506.2.6.1.1.1.1.8', NULL, 'hh3cDevMgrIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 85}', 'warn', 1, 'H3C 设备内存利用率（HH3C-OAM-MIB::hh3cDevMgrMemoryUtil）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(201, 'cpu_usage', 'cpu_usage', 'CPU 利用率(思科)', 'network', 'snmp', '9', 'CISCO-PROCESS-MIB', 'cpmCPUTotal5secRev', '1.3.6.1.4.1.9.9.109.1.1.1.1.6', NULL, 'cpmCPUTotalIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, '思科设备 CPU 利用率（CISCO-PROCESS-MIB::cpmCPUTotal5secRev）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(202, 'memory_usage', 'memory_usage', '内存利用率(思科)', 'network', 'snmp', '9', 'CISCO-MEMORY-POOL-MIB', 'ciscoMemoryPoolUsed/ciscoMemoryPoolFree', '1.3.6.1.4.1.9.9.48.1.1.1.5', NULL, 'ciscoMemoryPoolIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 85}', 'warn', 1, '思科设备内存利用率（CISCO-MEMORY-POOL-MIB）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(203, 'temperature', 'temperature', '温度(思科)', 'network', 'snmp', '9', 'CISCO-ENVMON-MIB', 'ciscoEnvMonTemperatureValue', '1.3.6.1.4.1.9.9.13.1.3.1.3', NULL, 'ciscoEnvMonTemperatureIndex', 'gauge', 'Celsius', 60, '{"crit": 75, "warn": 60}', 'warn', 1, '思科设备温度（CISCO-ENVMON-MIB::ciscoEnvMonTemperatureValue）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(204, 'temperature', 'temperature', '温度', 'server', 'snmp', NULL, 'ENTITY-SENSOR-MIB', 'entPhySensorValue', '1.3.6.1.2.1.99.1.1.1.5', NULL, NULL, 'gauge', 'Celsius', 60, '{"crit": 70, "warn": 60}', 'warn', 1, '温度传感器告警（超阈值触发）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(205, 'raid_failure', 'raid_failure', 'RAID 故障', 'server', 'ipmi', NULL, NULL, 'SEL', NULL, NULL, NULL, 'event', NULL, 60, '{}', 'crit', 0, 'IPMI SEL 磁盘/存储故障事件告警', '2026-08-14 13:14:50', '2026-08-20 15:27:02', NULL, NULL),
(206, 'disk_failure', 'disk_failure', '硬盘故障', 'server', 'ipmi', NULL, NULL, 'SEL', NULL, NULL, NULL, 'event', NULL, 60, '{}', 'crit', 1, '硬盘故障事件告警', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(207, 'cpu_usage', 'cpu_usage', 'CPU 利用率', 'server', 'zabbix', NULL, 'HOST-RESOURCES-MIB', 'hrProcessorLoad', '1.3.6.1.2.1.25.3.3.1.2', 'system.cpu.util', 'hrDeviceIndex', 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, 'Zabbix 采集 CPU 利用率（system.cpu.util，多核返回多实例）', '2026-08-14 13:14:50', '2026-08-20 16:24:04', NULL, NULL),
(208, 'memory_usage', 'memory_usage', '内存利用率', 'server', 'zabbix', NULL, 'HOST-RESOURCES-MIB', 'hrMemorySize', '1.3.6.1.2.1.25.1.2.0', 'vm.memory.size[pavailable]', NULL, 'gauge', '%', 60, '{"crit": 5, "warn": 15}', 'warn', 1, 'Zabbix 采集内存可用率（vm.memory.size[pavailable]，低于阈值告警）', '2026-08-14 13:14:50', '2026-08-20 16:24:04', NULL, NULL),
(209, 'zabbix_temperature', 'temperature', '温度(Zabbix)', 'server', 'zabbix', NULL, NULL, NULL, NULL, 'sensor.temp.value', NULL, 'gauge', 'Celsius', 60, '{"crit": 75, "warn": 60}', 'warn', 1, 'Zabbix 采集温度传感器（sensor.temp.value，多传感器返回多实例）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(210, 'fan_speed', 'fan_speed', '风扇转速', 'server', 'zabbix', NULL, NULL, NULL, NULL, 'fan.speed', NULL, 'gauge', 'RPM', 60, '{"warn": 1000}', 'warn', 1, 'Zabbix 采集风扇转速（fan.speed，低于阈值告警）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(211, 'sys_uptime', 'system_uptime', '系统运行时间', 'server', 'zabbix', NULL, 'HOST-RESOURCES-MIB', 'hrSystemUptime', '1.3.6.1.2.1.25.1.1.0', 'system.uptime', NULL, 'gauge', 's', 60, '{}', 'info', 1, 'Zabbix 采集系统运行时间（system.uptime，重启检测：当前值 < 上次值）', '2026-08-14 13:14:50', '2026-08-20 16:24:04', NULL, NULL),
(212, 'zabbix_cpu_usage', 'cpu_usage', 'CPU 利用率(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'system.cpu.util', NULL, 'gauge', '%', 60, '{"crit": 95, "warn": 80}', 'warn', 1, 'Zabbix 采集网络设备 CPU 利用率（system.cpu.util）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(213, 'zabbix_memory_usage', 'memory_usage', '内存利用率(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'vm.memory.utilization', NULL, 'gauge', '%', 60, '{"crit": 95, "warn": 85}', 'warn', 1, 'Zabbix 采集网络设备内存利用率（vm.memory.utilization）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(214, 'zabbix_temperature', 'temperature', '温度(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'sensor.temp.value', NULL, 'gauge', 'Celsius', 60, '{"crit": 75, "warn": 60}', 'warn', 1, 'Zabbix 采集网络设备温度（sensor.temp.value）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(215, 'zabbix_sys_uptime', 'system_uptime', '系统运行时间(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'system.uptime', NULL, 'gauge', 's', 60, '{}', 'info', 1, 'Zabbix 采集网络设备系统运行时间（system.uptime）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(216, 'zabbix_if_in_errors', 'if_in_errors', '入错包(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'net.if.in.errors', NULL, 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, 'Zabbix 采集网络端口入方向错包数（net.if.in.errors[<if>]，多端口返回多实例）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(217, 'zabbix_if_out_errors', 'if_out_errors', '出错包(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'net.if.out.errors', NULL, 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, 'Zabbix 采集网络端口出方向错包数（net.if.out.errors[<if>]，多端口返回多实例）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(218, 'zabbix_if_in_discards', 'if_in_discards', '入丢包(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'net.if.in.discards', NULL, 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, 'Zabbix 采集网络端口入方向丢包数（net.if.in.discards[<if>]，多端口返回多实例）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(219, 'zabbix_if_out_discards', 'if_out_discards', '出丢包(Zabbix)', 'network', 'zabbix', NULL, NULL, NULL, NULL, 'net.if.out.discards', NULL, 'counter', NULL, 60, '{"warn": 100}', 'warn', 1, 'Zabbix 采集网络端口出方向丢包数（net.if.out.discards[<if>]，多端口返回多实例）', '2026-08-14 13:14:50', '2026-08-14 13:14:50', NULL, NULL),
(220, 'cpu_usage_alcatel', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '6527', 'TIMETRA-SYSTEM-MIB', NULL, '1.3.6.1.4.1.6527.3.1.2.1.1.1.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: TIMETRA-SYSTEM-MIB
The value of sgiCpuUsage indicates the current CPU utilization for the system.
', '2026-08-17 16:57:45', '2026-08-20 15:16:46', NULL, NULL),
(221, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '800', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:45', '2026-08-17 16:57:45', NULL, NULL),
(222, 'cpu_usage_arista', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '30065', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.3.3.1.2', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: HOST-RESOURCES-MIB
The average, over the last minute, of the percentage of time that processors was not idle.
Implementations may approximate this one minute smoothing period if necessary.
', '2026-08-17 16:57:45', '2026-08-17 16:57:45', NULL, NULL),
(223, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '30065', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:45', '2026-08-17 16:57:45', NULL, NULL),
(224, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '1271', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:46', '2026-08-17 16:57:46', NULL, NULL),
(225, 'cpu_usage_brocade', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '1588', 'SW-MIB', NULL, '1.3.6.1.4.1.1588.2.1.1.1.26.1.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: SW-MIB
System''s CPU usage.
', '2026-08-17 16:57:46', '2026-08-17 16:57:46', NULL, NULL),
(226, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '1588', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:46', '2026-08-17 16:57:46', NULL, NULL),
(227, 'memory_usage_brocade', 'memory_usage', 'Memory utilization', 'network', 'snmp', '1588', 'SW-MIB', NULL, '1.3.6.1.4.1.1588.2.1.1.1.26.6.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: SW-MIB
Memory utilization in %.
', '2026-08-17 16:57:46', '2026-08-17 16:57:46', NULL, NULL),
(228, 'fan_speed', 'fan_speed', 'SNMP walk fan sensors', 'network', 'snmp', '2620', NULL, NULL, '1.3.6.1.4.1.2620.1.6.7.8.2.1.2', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'Used for discovering fan sensors from CHECKPOINT-MIB.', '2026-08-17 16:57:46', '2026-08-20 15:29:43', NULL, NULL),
(229, 'power_supply', 'power_supply', 'SNMP walk PSU sensors', 'network', 'snmp', '2620', NULL, NULL, '1.3.6.1.4.1.2620.1.6.7.9.1.1.1', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'Used for discovering power supply sensors from CHECKPOINT-MIB.', '2026-08-17 16:57:46', '2026-08-20 15:29:43', NULL, NULL),
(230, 'temperature_fortinet', 'temperature', 'SNMP walk temperature sensors', 'network', 'snmp', '2620', NULL, NULL, '1.3.6.1.4.1.2620.1.6.7.8.1.1.2', NULL, NULL, 'state', NULL, 60, '{"crit": 75.0, "warn": 65.0}', 'crit', 1, 'Used for discovering temperature sensors from CHECKPOINT-MIB.', '2026-08-17 16:57:46', '2026-08-20 15:29:43', NULL, NULL),
(231, 'cpu_load', 'cpu_load', 'SNMP walk CPU load averages', 'network', 'snmp', '2021', 'UCD-SNMP-MIB', NULL, '1.3.6.1.4.1.2021.10.1.2', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: UCD-SNMP-MIB
SNMP walk through laTable. The collected data used in dependent CPU load average items.
', '2026-08-17 16:57:46', '2026-08-20 15:29:43', NULL, NULL),
(232, 'cpu_usage_fortinet', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '2620', 'CHECKPOINT-MIB', NULL, '1.3.6.1.4.1.2620.1.6.7.2.4.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: CHECKPOINT-MIB
CPU utilization per core in %.
', '2026-08-17 16:57:46', '2026-08-20 15:29:43', NULL, NULL),
(233, 'sys_uptime', 'sys_uptime', 'System uptime', 'network', 'snmp', '12356', 'HOST-RESOURCES-V2-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 60, 'null', 'info', 1, 'MIB: HOST-RESOURCES-V2-MIB
Time since the network management portion of the system was last re-initialized.
', '2026-08-17 16:57:46', '2026-08-17 16:57:46', NULL, NULL),
(234, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '9', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 60, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(235, 'if_duplex', 'if_duplex', 'Cisco IOS: SNMP walk EtherLike-MIB interfaces', 'network', 'snmp', '9', NULL, NULL, '1.3.6.1.2.1.10.7.2.1.19', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'Discovering interfaces from IF-MIB and EtherLike-MIB. Interfaces with `up(1)` Operational Status are discovered.', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(236, 'fan_speed', 'fan_speed', 'Cisco IOS: SNMP walk fans', 'network', 'snmp', '9', NULL, NULL, '1.3.6.1.4.1.9.9.13.1.4.1.2', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'Discovering system fans.', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(237, 'power_supply', 'power_supply', 'Cisco IOS: SNMP walk PSUs', 'network', 'snmp', '9', NULL, NULL, '1.3.6.1.4.1.9.9.13.1.5.1.2', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'The table of power supply status maintained by the environmental monitor card.', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(238, 'temperature_cisco', 'temperature', 'Cisco IOS: SNMP walk temperature sensors', 'network', 'snmp', '9', NULL, NULL, '1.3.6.1.4.1.9.9.13.1.3.1.2', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'Discovery of ciscoEnvMonTemperatureTable (ciscoEnvMonTemperatureDescr), a table of ambient temperature status maintained by the environmental monitor.', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(239, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'server', 'snmp', '674', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(240, 'cpu_usage_dlink', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '171', 'MY-PROCESS-MIB', NULL, '1.3.6.1.4.1.171.10.97.2.36.1.1.3.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: MY-PROCESS-MIB
The CPU utilization expressed in %.
', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(241, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '171', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:47', '2026-08-17 16:57:47', NULL, NULL),
(242, 'temperature_extreme', 'temperature', 'Temperature status', 'network', 'snmp', '1916', 'EXTREME-SYSTEM-MIB', NULL, '1.3.6.1.4.1.1916.1.1.1.7.0', NULL, NULL, 'gauge', NULL, 180, 'null', 'info', 1, 'MIB: EXTREME-SYSTEM-MIB
Temperature status of testpoint: Device
', '2026-08-17 16:57:47', '2026-08-20 15:29:43', NULL, NULL),
(243, 'cpu_usage_extreme', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '1916', 'EXTREME-SOFTWARE-MONITOR-MIB', NULL, '1.3.6.1.4.1.1916.1.32.1.2.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: EXTREME-SOFTWARE-MONITOR-MIB
Total CPU utilization (percentage) as of last sampling.
', '2026-08-17 16:57:47', '2026-08-20 15:29:43', NULL, NULL),
(244, 'memory_usage_fortinet', 'memory_usage', 'Memory utilization', 'network', 'snmp', '12356', NULL, NULL, '1.3.6.1.4.1.12356.101.4.1.4.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'Current memory utilization (percentage).', '2026-08-17 16:57:48', '2026-08-17 16:57:48', NULL, NULL),
(245, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '25506', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:48', '2026-08-17 16:57:48', NULL, NULL),
(246, 'cpu_usage_hp', 'cpu_usage', 'CPU utilization', 'server', 'snmp', '11', 'STATISTICS-MIB', NULL, '1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: STATISTICS-MIB
The CPU utilization in percent(%).
Reference: http://h20564.www2.hpe.com/hpsc/doc/public/display?docId=emr_na-c02597344&sp4ts.oid=51079
', '2026-08-17 16:57:48', '2026-08-20 15:24:52', NULL, NULL),
(247, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'server', 'snmp', '232', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(249, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '3300', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(250, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '119', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(251, 'cpu_usage_mellanox', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '3300', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.3.3.1.2', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: HOST-RESOURCES-MIB
The average, over the last minute, of the percentage of time that processors was not idle.
Implementations may approximate this one minute smoothing period if necessary.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(252, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '4881', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(253, 'cpu_usage_netgear', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '4526', 'FASTPATH-SWITCHING-MIB', NULL, '1.3.6.1.4.1.4526.10.1.1.4.9.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: FASTPATH-SWITCHING-MIB
The CPU utilization expressed in %.
', '2026-08-17 16:57:49', '2026-08-20 15:16:46', NULL, NULL),
(254, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '45', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(255, 'temperature', 'temperature', 'Temperature', 'network', 'snmp', '27514', 'QTECH-MIB', NULL, '1.3.6.1.4.1.27514.100.1.11.9.0', NULL, NULL, 'gauge', '°C', 180, 'null', 'info', 1, 'MIB: QTECH-MIB
Temperature readings of testpoint.
', '2026-08-17 16:57:49', '2026-08-20 15:27:02', NULL, NULL),
(256, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '14988', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(257, 'cpu_load', 'cpu_load', 'Load average (1m avg)', 'network', 'snmp', '10002', 'FROGFOOT-RESOURCES-MIB', NULL, '1.3.6.1.4.1.10002.1.1.1.4.2.1.3.1', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: FROGFOOT-RESOURCES-MIB
1 minute load average of processor load.
', '2026-08-17 16:57:49', '2026-08-20 15:16:46', NULL, NULL),
(258, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'network', 'snmp', '41112', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:49', '2026-08-17 16:57:49', NULL, NULL),
(259, 'cpu_load', 'cpu_load', 'Load average (1m avg)', 'network', 'snmp', '1588', 'UCD-SNMP-MIB', NULL, '1.3.6.1.4.1.2021.10.1.3.1', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 0, 'MIB: UCD-SNMP-MIB
Average number of processes being executed or waiting over the last minute.
', '2026-08-17 16:57:49', '2026-08-20 15:30:05', NULL, NULL),
(260, 'temperature_hpe', 'temperature', 'System temperature status', 'server', 'snmp', '232', 'CPQHLTH-MIB', NULL, '1.3.6.1.4.1.232.6.2.6.1.0', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: CPQHLTH-MIB
This value specifies the overall condition of the system''s thermal environment.
This value will be one of the following:
other(1)  Temperature could not be determined.
ok(2)  The temperature sensor is within normal operating range.
degrad', '2026-08-17 16:57:50', '2026-08-20 15:24:52', NULL, NULL),
(261, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'server', 'snmp', '11', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:50', '2026-08-17 16:57:50', NULL, NULL),
(262, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'server', 'snmp', '437', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:50', '2026-08-17 16:57:50', NULL, NULL),
(263, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'server', 'snmp', '10876', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:51', '2026-08-17 16:57:51', NULL, NULL),
(264, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'other', 'snmp', '318', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:51', '2026-08-17 16:57:51', NULL, NULL),
(265, 'sys_uptime', 'sys_uptime', 'Uptime (hardware)', 'other', 'snmp', '2469', 'HOST-RESOURCES-MIB', NULL, '1.3.6.1.2.1.25.1.1.0', NULL, NULL, 'gauge', 'uptime', 30, 'null', 'info', 1, 'MIB: HOST-RESOURCES-MIB
The amount of time since this host was last initialized. Note that this is different from sysUpTime in the SNMPv2-MIB [RFC1907] because sysUpTime is the uptime of the network management portion of the system.
', '2026-08-17 16:57:51', '2026-08-17 16:57:51', NULL, NULL),
(266, 'sys_uptime_alcatel', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '800', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(267, 'sys_uptime_8300s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '1271', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(268, 'cpu_usage_brocade_foundry', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '1991', 'FOUNDRY-SN-AGENT-MIB', NULL, '1.3.6.1.4.1.1991.1.1.2.1.52.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: FOUNDRY-SN-AGENT-MIB
The statistics collection of 1 minute CPU utilization.
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(269, 'sys_uptime_foundry', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '1588', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(270, 'memory_usage_brocade_foundry', 'memory_usage', 'Memory utilization', 'network', 'snmp', '1991', 'FOUNDRY-SN-AGENT-MIB', NULL, '1.3.6.1.4.1.1991.1.1.2.1.53.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: FOUNDRY-SN-AGENT-MIB
The system dynamic memory utilization, in unit of percentage.
Deprecated: Refer to snAgSystemDRAMUtil.
For NI platforms, refer to snAgentBrdMemoryUtil100thPercent.
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(271, 'sys_uptime_3906', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '1271', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(272, 'sys_uptime_3750v2-24fs', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(273, 'sys_uptime_3750v2-24ps', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(274, 'sys_uptime_3750v2-24ts', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(275, 'sys_uptime_3750v2-48ps', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(276, 'sys_uptime_3750v2-48ts', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(277, 'sys_uptime_9000', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', 'sysUpTime', '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMP-FRAMEWORK-MIB::snmpEngineTime.
The number of seconds since the value of the `snmpEngineBoots` object has had a last change.
When incrementing this object''s value would cause it to exceed its maximum, the `snmpEngineBoots` is incremented as if a ', '2026-08-19 09:32:56', '2026-08-20 15:16:46', NULL, NULL),
(278, 'sys_uptime_ios', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(279, 'sys_uptime_force', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '674', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(280, 'sys_uptime_7200', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '171', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(281, 'cpu_usage_dlink_link', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '171', 'DLINK-AGENT-MIB', NULL, '1.3.6.1.4.1.171.12.1.1.6.2.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: DLINK-AGENT-MIB
The unit of time is 1 minute. The value will be between 0% (idle) and 100%(very busy).
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(282, 'sys_uptime_link', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '171', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(283, 'temperature_extreme_exos', 'temperature', 'Temperature', 'network', 'snmp', '1916', 'EXTREME-SYSTEM-MIB', NULL, '1.3.6.1.4.1.1916.1.1.1.8.0', NULL, NULL, 'gauge', '°C', 180, 'null', 'info', 1, 'MIB: EXTREME-SYSTEM-MIB
Temperature readings of testpoint: Device
Reference: https://gtacknowledge.extremenetworks.com/articles/Q_A/Does-EXOS-support-temperature-polling-via-SNMP-on-all-nodes-in-a-stack
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(284, 'sys_uptime_exos', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '171', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(285, 'cpu_usage_fortinet_fortigate', 'cpu_usage', 'CPU utilization', 'network', 'snmp', '12356', 'FORTINET-FORTIGATE-MIB', NULL, '1.3.6.1.4.1.12356.101.4.1.3.0', NULL, NULL, 'gauge', '%', 60, '{"crit": 90.0}', 'crit', 1, 'MIB: FORTINET-FORTIGATE-MIB
CPU utilization in %.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL);
INSERT INTO `monitor_metric_templates` (`id`, `metric_key`, `category`, `display_name`, `device_type`, `source`, `vendor`, `mib`, `oid_symbol`, `oid`, `zabbix_item_key`, `index_kind`, `metric_type`, `unit`, `poll_interval`, `threshold`, `severity_default`, `enabled`, `description`, `created_at`, `updated_at`, `runbook_url`, `runbook_title`) VALUES
(286, 'sys_uptime_fortigate', 'sys_uptime', 'System uptime', 'network', 'snmp', '12356', 'FORTINET-FORTIGATE-MIB', NULL, '1.3.6.1.4.1.12356.101.4.1.20.0', NULL, NULL, 'gauge', 'uptime', 60, 'null', 'info', 1, 'MIB: FORTINET-FORTIGATE-MIB
Time since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(287, 'sys_uptime_network', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', NULL, 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(288, 'sys_uptime_hh3c', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '25506', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(289, 'sys_uptime_enterprise', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '232', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(291, 'sys_uptime', 'sys_uptime', 'Uptime', 'network', 'snmp', '2011', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 13:51:49', NULL, NULL),
(292, 'sys_uptime_intel', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '3300', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(293, 'sys_uptime_mellanox', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '3300', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(294, 'sys_uptime_ccr1009-7g-1c-1s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(295, 'sys_uptime_ccr1009-7g-1c-pc', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(296, 'sys_uptime_ccr1016-12g', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(297, 'sys_uptime_ccr1016-12s-1s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(298, 'sys_uptime_ccr1036-12g-4s-e', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(299, 'sys_uptime_ccr1036-12g-4s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(300, 'sys_uptime_ccr1036-8g-2sem', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(301, 'sys_uptime_ccr1036-8g-2s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(302, 'sys_uptime_ccr1072-1g-8s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(303, 'sys_uptime_ccr2004-16g-2s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(304, 'sys_uptime_ccr2004-1g-12s2x', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(305, 'sys_uptime_crs106-1c-5s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(306, 'sys_uptime_crs109-8g-1s-2hn', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(307, 'sys_uptime_crs112-8g-4s-in', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(308, 'sys_uptime_crs112-8p-4s-in', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(309, 'sys_uptime_crs125-24g-1s-2h', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(310, 'sys_uptime_crs212-1g-10s-1s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(311, 'sys_uptime_crs305-1g-4sin', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(312, 'sys_uptime_crs309-1g-8sin', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(313, 'sys_uptime_crs312-4c8xg-rm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(314, 'sys_uptime_crs317-1g-16srm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(315, 'sys_uptime_crs326-24g-2sin', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(316, 'sys_uptime_crs326-24g-2srm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(317, 'sys_uptime_crs326-24s2qrm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(318, 'sys_uptime_crs328-24p-4srm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(319, 'sys_uptime_crs328-4c-20s-4s', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(320, 'sys_uptime_crs354-48g-4s2qr', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(321, 'sys_uptime_crs354-48p-4s2qr', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(322, 'sys_uptime_css326-24g-2srm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(323, 'sys_uptime_css610-8g-2sin', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(324, 'sys_uptime_fiberbox', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(325, 'sys_uptime_powerbox', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(326, 'sys_uptime_rb1100ahx4', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(327, 'sys_uptime_rb2011uias-in', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(328, 'sys_uptime_rb2011uias-rm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(329, 'sys_uptime_rb2011il-in', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(330, 'sys_uptime_rb2011il-rm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(331, 'sys_uptime_rb2011ils-in', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(332, 'sys_uptime_rb260gsp', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(333, 'sys_uptime_rb260gs', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(334, 'sys_uptime_rb3011uias-rm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(335, 'sys_uptime_rb4011igsrm', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(336, 'sys_uptime_rb5009ugsin', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(337, 'sys_uptime_hex', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(338, 'sys_uptime_15fr', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(339, 'sys_uptime_16p', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(340, 'sys_uptime_7r', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '4881', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(341, 'battery_voltage', 'battery_voltage', 'Battery: Battery Voltage discovery', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.30.0', NULL, NULL, 'gauge', 'V', 900, 'null', 'info', 1, 'MIB: PROSTAR-MPPT', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(342, 'load_current', 'load_current', 'Load: Current', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.34.0', NULL, NULL, 'gauge', 'A', 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Load Current
 Description:Load Current
 Scaling Factor:1.0
 Units:A
 Range:[0, 60]
 Modbus address:0x0016
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(343, 'load_state', 'load_state', 'Load: State', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.53.0', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Load State
 Description:Load State
 Modbus address:0x002E

 0: Start
1: Normal
2: LvdWarning
3: Lvd
4: Fault
5: Disconnect
6: NormalOff
7: Override
8: NotUsed
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(344, 'load_voltage', 'load_voltage', 'Load: Voltage', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.32.0', NULL, NULL, 'gauge', 'V', 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Load Voltage
 Description:Load Voltage
 Scaling Factor:1.0
 Units:V
 Range:[0, 80]
 Modbus address:0x0014
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(345, 'status_alarms', 'status_alarms', 'Status: Alarms', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.59.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Description:Alarms
Modbus addresses:H=0x0038 L=0x0039
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(346, 'status_array_faults', 'status_array_faults', 'Status: Array Faults', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.46.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Description:Array Faults
Modbus address:0x0022
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(347, 'status_load_faults', 'status_load_faults', 'Status: Load Faults', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.54.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-MPPT
Description:Array Faults
Modbus address:0x0022
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(348, 'temperature_morningstar', 'temperature', 'Temperature: Ambient', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.40.0', NULL, NULL, 'gauge', 'C', 60, '{"crit": 60.0, "warn": 0.0}', 'crit', 1, 'MIB: PROSTAR-MPPT
Ambient Temperature
 Description:Ambient Temperature
 Scaling Factor:1.0
 Units:deg C
 Range:[-128, 127]
 Modbus address:0x001C
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(349, 'temperature_morningstar_morningstar', 'temperature', 'Temperature: Battery', 'network', 'snmp', '33333', 'PROSTAR-MPPT', NULL, '1.3.6.1.4.1.33333.5.39.0', NULL, NULL, 'gauge', 'C', 60, '{"crit": 60.0, "warn": 0.0}', 'crit', 1, 'MIB: PROSTAR-MPPT
Battery Temperature
  Description:Battery Temperature
  Scaling Factor:1.0
  Units:deg C
  Range:[-128, 127]
  Modbus address:0x001B
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(350, 'battery_voltage_morningstar', 'battery_voltage', 'Battery: Battery Voltage discovery', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.30.0', NULL, NULL, 'gauge', 'V', 900, 'null', 'info', 1, 'MIB: PROSTAR-PWM', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(351, 'load_current_morningstar', 'load_current', 'Load: Current', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.34.0', NULL, NULL, 'gauge', 'A', 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Load Current
Scaling Factor:1.0
Units:A
Range:[0, 60]
Modbus address:0x0016
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(352, 'load_state_morningstar', 'load_state', 'Load: State', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.53.0', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Load State
Modbus address:0x002E

0: Start
1: Normal
2: LvdWarning
3: Lvd
4: Fault
5: Disconnect
6: NormalOff
7: Override
8: NotUsed
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(353, 'load_voltage_morningstar', 'load_voltage', 'Load: Voltage', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.32.0', NULL, NULL, 'gauge', 'V', 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Load Voltage
Scaling Factor:1.0
Units:V
Range:[0, 80]
Modbus address:0x0014
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(354, 'status_alarms_morningstar', 'status_alarms', 'Status: Alarms', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.59.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Alarms
Modbus addresses:H=0x0038 L=0x0039
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(355, 'status_array_faults_morningstar', 'status_array_faults', 'Status: Array Faults', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.46.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Array Faults
Modbus address:0x0022
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(356, 'status_load_faults_morningstar', 'status_load_faults', 'Status: Load Faults', 'network', 'snmp', '33333', 'PROSTAR-PWM', NULL, '1.3.6.1.4.1.33333.6.54.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: PROSTAR-PWM
Description:Load Faults
Modbus address:0x002F
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(357, 'battery_voltage_600v', 'battery_voltage', 'Battery: Battery Voltage discovery', 'network', 'snmp', '33333', 'TRISTAR-MPPT', NULL, '1.3.6.1.4.1.33333.7.36.0', NULL, NULL, 'gauge', 'V', 900, 'null', 'info', 1, 'MIB: TRISTAR-MPPT
Description:Battery voltage
Scaling Factor:1.0
Units:V
Range:[-10, 80]
Modbus address:0x0018
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(358, 'status_alarms_600v', 'status_alarms', 'Status: Alarms', 'network', 'snmp', '33333', 'TRISTAR-MPPT', NULL, '1.3.6.1.4.1.33333.7.57.0', NULL, NULL, 'state', NULL, 60, 'null', 'info', 1, 'MIB: TRISTAR-MPPT
Description:Alarms
Modbus addresses:H=0x002e L=0x002f
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(359, 'temperature_morningstar_600v', 'temperature', 'Temperature: Battery', 'network', 'snmp', '33333', 'TRISTAR-MPPT', NULL, '1.3.6.1.4.1.33333.7.48.0', NULL, NULL, 'gauge', 'C', 60, '{"crit": 60.0, "warn": 0.0}', 'crit', 1, 'MIB: TRISTAR-MPPT
Description:Batt. Temp
Scaling Factor:1.0
Units:C
Range:[-40, 80]
Modbus address:0x0025
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(360, 'sys_uptime_netgear', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '45', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(361, 'sys_uptime_qtech', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', NULL, 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(362, 'sys_uptime_link', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '14988', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(363, 'cpu_load_airos', 'cpu_load', 'Load average (5m avg)', 'network', 'snmp', '10002', 'FROGFOOT-RESOURCES-MIB', NULL, '1.3.6.1.4.1.10002.1.1.1.4.2.1.3.2', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: FROGFOOT-RESOURCES-MIB
5 minute load average of processor load.
', '2026-08-19 09:32:56', '2026-08-20 15:16:46', NULL, NULL),
(364, 'sys_uptime_airos', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '41112', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(365, 'cpu_load_vyatta', 'cpu_load', 'Load average (5m avg)', 'network', 'snmp', '2021', 'UCD-SNMP-MIB', NULL, '1.3.6.1.4.1.2021.10.1.3.2', NULL, NULL, 'gauge', NULL, 60, 'null', 'info', 1, 'MIB: UCD-SNMP-MIB
Average number of processes being executed or waiting over the last 5 minutes.
', '2026-08-19 09:32:56', '2026-08-20 15:29:43', NULL, NULL),
(366, 'sys_uptime_vyatta', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '1588', 'DISMAN-EVENT-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: DISMAN-EVENT-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(367, 'sys_uptime_ucs', 'sys_uptime', 'Uptime (network)', 'network', 'snmp', '9', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time in seconds since the network management
portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(368, 'sys_uptime_bl460', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '232', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(369, 'sys_uptime_bl920', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '232', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(370, 'sys_uptime_dl360', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '232', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(371, 'sys_uptime_dl380', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '232', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 60, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(372, 'sys_uptime_ilo', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '11', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(373, 'sys_uptime_imm', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '437', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(374, 'sys_uptime_aten', 'sys_uptime', 'Uptime (network)', 'server', 'snmp', '10876', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(375, 'battery_capacity', 'battery_capacity', 'Battery capacity', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.2.3.1.0', NULL, NULL, 'gauge', '%', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The remaining battery capacity expressed as
 percentage of full capacity.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(376, 'temperature_apc', 'temperature', 'Battery temperature', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.2.3.2.0', NULL, NULL, 'gauge', '℃', 60, '{"warn": 55.0}', 'warn', 1, 'MIB: PowerNet-MIB
The current internal UPS temperature in Celsius.
Temperatures below zero read as 0.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(377, 'battery_voltage', 'battery_voltage', 'Battery voltage', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.2.3.4.0', NULL, NULL, 'gauge', 'V', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The actual battery bus voltage in Volts.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(378, 'input_frequency', 'input_frequency', 'Input frequency', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.3.3.4.0', NULL, NULL, 'gauge', 'Hz', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The current input frequency to the UPS system in Hz.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(379, 'input_voltage', 'input_voltage', 'Input voltage', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.3.3.1.0', NULL, NULL, 'gauge', 'V', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The current utility line voltage in VAC.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(380, 'output_current', 'output_current', 'Output current', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.4.3.4.0', NULL, NULL, 'gauge', 'A', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The current in amperes drawn by the load on the UPS.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(381, 'output_load', 'output_load', 'Output load', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.4.3.3.0', NULL, NULL, 'gauge', '%', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The current UPS load expressed as percentage
of rated capacity.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(382, 'output_voltage', 'output_voltage', 'Output voltage', 'other', 'snmp', '318', 'PowerNet-MIB', NULL, '1.3.6.1.4.1.318.1.1.1.4.3.1.0', NULL, NULL, 'gauge', 'V', 60, 'null', 'info', 1, 'MIB: PowerNet-MIB
The output voltage of the UPS system in VAC.
', '2026-08-19 09:32:56', '2026-08-19 09:32:56', NULL, NULL),
(383, 'sys_uptime_3500', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(384, 'sys_uptime_2200', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(385, 'sys_uptime_3000', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(386, 'sys_uptime_1000', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL);
INSERT INTO `monitor_metric_templates` (`id`, `metric_key`, `category`, `display_name`, `device_type`, `source`, `vendor`, `mib`, `oid_symbol`, `oid`, `zabbix_item_key`, `index_kind`, `metric_type`, `unit`, `poll_interval`, `threshold`, `severity_default`, `enabled`, `description`, `created_at`, `updated_at`, `runbook_url`, `runbook_title`) VALUES
(387, 'sys_uptime_5000', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(388, 'sys_uptime_8000', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(389, 'sys_uptime_ups', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '318', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
The time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(392, 'sys_uptime_fas3220', 'sys_uptime', 'Uptime (network)', 'other', 'snmp', '2469', 'SNMPv2-MIB', NULL, '1.3.6.1.2.1.1.3.0', NULL, NULL, 'timeticks', 'uptime', 30, 'null', 'info', 1, 'MIB: SNMPv2-MIB
Time (in hundredths of a second) since the network management portion of the system was last re-initialized.
', '2026-08-19 09:32:56', '2026-08-20 14:01:31', NULL, NULL),
(393, 'fan_status', NULL, '风扇状态(华为)', 'network', 'snmp', '2011', 'HUAWEI-ENTITY-EXTENT-MIB', 'hwEntityFanState', '1.3.6.1.4.1.2011.5.25.31.1.1.10.1.7', NULL, 'hwEntityIndex', 'state', '', 60, NULL, NULL, 1, NULL, '2026-08-20 15:16:46', '2026-08-20 15:16:46', NULL, NULL),
(394, 'temperature_cpu_hp', NULL, 'CPU 温度(HPE)', 'server', 'snmp', '232', 'CPQHLTH-MIB', 'cpqHeTemperatureCelsius', '1.3.6.1.4.1.232.6.2.6.8.1.4', NULL, 'cpqHeTemperatureIndex', 'gauge', 'Celsius', 60, NULL, NULL, 1, NULL, '2026-08-20 15:24:52', '2026-08-20 15:24:52', NULL, NULL),
(395, 'fan_status_hp', NULL, '风扇状态(HPE)', 'server', 'snmp', '232', 'CPQHLTH-MIB', 'cpqHeFltTolFanCondition', '1.3.6.1.4.1.232.6.2.6.7.1.9', NULL, 'cpqHeFltTolFanIndex', 'state', '', 60, NULL, NULL, 1, NULL, '2026-08-20 15:24:52', '2026-08-20 15:24:52', NULL, NULL),
(396, 'power_status_hp', NULL, '电源状态(HPE)', 'server', 'snmp', '232', 'CPQHLTH-MIB', 'cpqHeFltTolPowerSupplyCondition', '1.3.6.1.4.1.232.6.2.9.3.1.4', NULL, 'cpqHeFltTolPowerSupplyIndex', 'state', '', 60, NULL, NULL, 1, NULL, '2026-08-20 15:24:52', '2026-08-20 15:24:52', NULL, NULL),
(397, 'memory_usage_hp', NULL, '内存利用率(HP)', 'server', 'snmp', '11', 'HP-SNMP-AGENT-MIB', 'hpLocalMemAllocBytes', '1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.7', NULL, 'hpLocalMemIndex', 'gauge', '%', 60, NULL, NULL, 1, NULL, '2026-08-20 15:24:52', '2026-08-20 15:24:52', NULL, NULL),
(398, 'system_health_hpe', 'health', '系统健康状态(HPE)', 'server', 'snmp', '232', 'CPQHLTH-MIB', 'cpqHeMibCondition', '1.3.6.1.4.1.232.6.1.3.0', NULL, NULL, 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(399, 'temperature_condition_hpe', 'temperature', '温度传感器条件(HPE)', 'server', 'snmp', '232', 'CPQHLTH-MIB', 'cpqHeTemperatureCondition', '1.3.6.1.4.1.232.6.2.6.8.1.6', NULL, 'cpqHeTemperatureIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(400, 'disk_array_status_hpe', 'disk', '磁盘阵列控制器状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaCntlrCondition', '1.3.6.1.4.1.232.3.2.2.1.1.6', NULL, 'cpqDaCntlrIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(401, 'disk_array_cache_status_hpe', 'disk', '磁盘阵列缓存状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaAccelStatus', '1.3.6.1.4.1.232.3.2.2.2.1.2', NULL, 'cpqDaAccelCntlrIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(402, 'disk_array_battery_status_hpe', 'disk', '阵列缓存电池状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaAccelBattery', '1.3.6.1.4.1.232.3.2.2.2.1.6', NULL, 'cpqDaAccelCntlrIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(403, 'physical_disk_status_hpe', 'disk', '物理磁盘状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaPhyDrvStatus', '1.3.6.1.4.1.232.3.2.5.1.1.6', NULL, 'cpqDaPhyDrvIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(404, 'physical_disk_smart_status_hpe', 'disk', '物理磁盘SMART状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaPhyDrvSmartStatus', '1.3.6.1.4.1.232.3.2.5.1.1.57', NULL, 'cpqDaPhyDrvIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(405, 'virtual_disk_status_hpe', 'disk', '虚拟磁盘状态(HPE)', 'server', 'snmp', '232', 'CPQIDA-MIB', 'cpqDaLogDrvStatus', '1.3.6.1.4.1.232.3.2.3.1.1.4', NULL, 'cpqDaLogDrvIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(406, 'nic_status_hpe', 'network', '网卡状态(HPE)', 'server', 'snmp', '232', 'CPQNIC-MIB', 'cpqNicIfPhysAdapterStatus', '1.3.6.1.4.1.232.18.2.3.1.1.14', NULL, 'cpqNicIfPhysAdapterIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:57:47', '2026-08-20 15:57:47', NULL, NULL),
(407, 'fan_status_hp_switch', 'fan', '风扇状态(HP Switch)', 'network', 'snmp', '11', 'HP-ICF-OID', 'hpicfSensorStatus', '1.3.6.1.4.1.11.2.14.11.1.2.6.1.4', NULL, 'hpicfSensorIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 15:58:30', '2026-08-20 15:58:30', NULL, NULL),
(408, 'memory_free_hp_switch', 'memory', '可用内存(HP Switch)', 'network', 'snmp', '11', 'HP-ICF-OID', 'hpLocalMemFreeBytes', '1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.6', NULL, 'hpLocalMemIndex', 'gauge', 'Bytes', 60, NULL, NULL, 1, NULL, '2026-08-20 15:58:30', '2026-08-20 15:58:30', NULL, NULL),
(409, 'memory_total_hp_switch', 'memory', '总内存(HP Switch)', 'network', 'snmp', '11', 'HP-ICF-OID', 'hpLocalMemTotalBytes', '1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.5', NULL, 'hpLocalMemIndex', 'gauge', 'Bytes', 60, NULL, NULL, 1, NULL, '2026-08-20 15:58:30', '2026-08-20 15:58:30', NULL, NULL),
(410, 'hardware_uptime_dell', 'uptime', '硬件运行时间(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'systemPowerUpTime', '1.3.6.1.4.1.674.10892.5.2.5.0', NULL, NULL, 'timeticks', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(411, 'cpu_status_dell', 'cpu', 'CPU状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'processorDeviceStatus', '1.3.6.1.4.1.674.10892.5.4.1100.32.1.5.1', NULL, 'processorDeviceIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(412, 'cpu_usage_dell', 'cpu', 'CPU利用率(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'processorDeviceReading', '1.3.6.1.4.1.674.10892.5.4.1100.32.1.6.1', NULL, 'processorDeviceIndex', 'gauge', '%', 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(413, 'memory_status_dell', 'memory', '内存状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'memoryDeviceStatus', '1.3.6.1.4.1.674.10892.5.4.1100.50.1.5.1', NULL, 'memoryDeviceIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(414, 'memory_size_dell', 'memory', '内存大小(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'memoryDeviceSize', '1.3.6.1.4.1.674.10892.5.4.1100.50.1.8.1', NULL, 'memoryDeviceIndex', 'gauge', 'Bytes', 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(415, 'temperature_dell', 'temperature', '温度(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'temperatureProbeReading', '1.3.6.1.4.1.674.10892.5.4.700.20.1.6.1', NULL, 'temperatureProbeIndex', 'gauge', 'Celsius', 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(416, 'temperature_status_dell', 'temperature', '温度状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'temperatureProbeStatus', '1.3.6.1.4.1.674.10892.5.4.700.20.1.5.1', NULL, 'temperatureProbeIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(417, 'fan_speed_dell', 'fan', '风扇转速(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'coolingDeviceReading', '1.3.6.1.4.1.674.10892.5.4.700.12.1.6.1', NULL, 'coolingDeviceIndex', 'gauge', 'RPM', 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(418, 'fan_status_dell', 'fan', '风扇状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'coolingDeviceStatus', '1.3.6.1.4.1.674.10892.5.4.700.12.1.5.1', NULL, 'coolingDeviceIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(419, 'power_status_dell', 'power', '电源状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'powerSupplyStatus', '1.3.6.1.4.1.674.10892.5.4.600.12.1.5.1', NULL, 'powerSupplyIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(420, 'physical_disk_status_dell', 'disk', '物理磁盘状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'physicalDiskState', '1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.6', NULL, 'physicalDiskIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(421, 'physical_disk_smart_status_dell', 'disk', '物理磁盘SMART状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'physicalDiskSmartStatus', '1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.31', NULL, 'physicalDiskIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(422, 'virtual_disk_status_dell', 'disk', '虚拟磁盘状态(Dell)', 'server', 'snmp', '674', 'IDRAC-MIB-SMIV2', 'virtualDiskState', '1.3.6.1.4.1.674.10892.5.5.1.20.140.1.1.4', NULL, 'virtualDiskIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:00:27', '2026-08-20 16:00:27', NULL, NULL),
(423, 'temperature_h3c', 'temperature', '温度(H3C)', 'network', 'snmp', '25506', 'HH3C-ENTITY-EXT-MIB', 'hh3cEntityExtTemperature', '1.3.6.1.4.1.25506.2.6.1.1.1.1.12', NULL, 'hh3cEntityIndex', 'gauge', 'Celsius', 60, NULL, NULL, 1, NULL, '2026-08-20 16:08:19', '2026-08-20 16:08:34', NULL, NULL),
(424, 'fan_status_h3c', 'fan', '风扇状态(H3C)', 'network', 'snmp', '25506', 'HH3C-ENTITY-EXT-MIB', 'hh3cEntityExtErrorStatus', '1.3.6.1.4.1.25506.2.6.1.1.1.1.19', NULL, 'hh3cEntityIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:08:19', '2026-08-20 16:08:19', NULL, NULL),
(425, 'power_status_h3c', 'power', '电源状态(H3C)', 'network', 'snmp', '25506', 'HH3C-ENTITY-EXT-MIB', 'hh3cEntityExtErrorStatus', '1.3.6.1.4.1.25506.2.6.1.1.1.1.19', NULL, 'hh3cEntityIndex', 'state', NULL, 60, NULL, NULL, 1, NULL, '2026-08-20 16:08:19', '2026-08-20 16:08:19', NULL, NULL),
(426, 'temperature_supermicro', 'temperature', '温度(Supermicro)', 'server', 'snmp', '10876', 'SUPERMICRO-MIB', 'sensorReading', '1.3.6.1.4.1.21317.1.3.1.2', NULL, 'sensorIndex', 'gauge', 'Celsius', 60, NULL, NULL, 1, NULL, '2026-08-20 16:11:30', '2026-08-20 16:11:30', NULL, NULL),
(427, 'fan_speed_supermicro', 'fan', '风扇转速(Supermicro)', 'server', 'snmp', '10876', 'SUPERMICRO-MIB', 'sensorReading', '1.3.6.1.4.1.21317.1.3.1.2', NULL, 'sensorIndex', 'gauge', 'RPM', 60, NULL, NULL, 1, NULL, '2026-08-20 16:11:30', '2026-08-20 16:11:30', NULL, NULL);

-- monitor_metric_template_groups: 26 rows
DELETE FROM `monitor_metric_template_groups`;
INSERT INTO `monitor_metric_template_groups` (`name`, `device_type`, `source`, `vendor`, `display_order`, `enabled`, `description`, `id`, `created_at`, `updated_at`) VALUES
('Alcatel网络设备SNMP指标', 'network', 'snmp', '800', 0, 1, '从 Zabbix 官方模版提取（厂商=alcatel, 大类=network, 来源=snmp）', 1, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
('Arista网络设备SNMP指标', 'network', 'snmp', '30065', 0, 1, '从 Zabbix 官方模版提取（厂商=arista, 大类=network, 来源=snmp）', 2, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
('Ciena网络设备SNMP指标', 'network', 'snmp', '1271', 0, 1, '从 Zabbix 官方模版提取（厂商=ciena, 大类=network, 来源=snmp）', 3, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
('Brocade网络设备SNMP指标', 'network', 'snmp', '1588', 0, 1, '从 Zabbix 官方模版提取（厂商=brocade, 大类=network, 来源=snmp）', 4, '2026-08-17 16:57:52', '2026-08-17 16:57:52'),
('Fortinet网络设备SNMP指标', 'network', 'snmp', '12356', 0, 1, '从 Zabbix 官方模版提取（厂商=fortinet, 大类=network, 来源=snmp）', 5, '2026-08-17 16:57:53', '2026-08-17 16:57:53'),
('思科网络设备SNMP指标', 'network', 'snmp', '9', 0, 1, '从 Zabbix 官方模版提取（厂商=cisco, 大类=network, 来源=snmp）', 6, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
('Dell服务器SNMP指标', 'server', 'snmp', '674', 0, 1, '从 Zabbix 官方模版提取（厂商=dell, 大类=server, 来源=snmp）', 7, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
('D-Link网络设备SNMP指标', 'network', 'snmp', '171', 0, 1, '从 Zabbix 官方模版提取（厂商=dlink, 大类=network, 来源=snmp）', 8, '2026-08-17 16:57:55', '2026-08-17 16:57:55'),
('Extreme网络设备SNMP指标', 'network', 'snmp', '171', 0, 1, '从 Zabbix 官方模版提取（厂商=extreme, 大类=network, 来源=snmp）', 9, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
('H3C网络设备SNMP指标', 'network', 'snmp', '25506', 0, 1, '从 Zabbix 官方模版提取（厂商=h3c, 大类=network, 来源=snmp）', 10, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
('HP服务器SNMP指标', 'server', 'snmp', '232', 0, 1, '从 Zabbix 官方模版提取（厂商=hp, 大类=server, 来源=snmp）', 11, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
('华为网络设备SNMP指标', 'network', 'snmp', '2011', 0, 1, '从 Zabbix 官方模版提取（厂商=huawei, 大类=network, 来源=snmp）', 12, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
('Mellanox网络设备SNMP指标', 'network', 'snmp', '3300', 0, 1, '从 Zabbix 官方模版提取（厂商=mellanox, 大类=network, 来源=snmp）', 13, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
('Juniper网络设备SNMP指标', 'network', 'snmp', '119', 0, 1, '从 Zabbix 官方模版提取（厂商=juniper, 大类=network, 来源=snmp）', 14, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
('MikroTik网络设备SNMP指标', 'network', 'snmp', '4881', 0, 1, '从 Zabbix 官方模版提取（厂商=mikrotik, 大类=network, 来源=snmp）', 15, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
('Netgear网络设备SNMP指标', 'network', 'snmp', '45', 0, 1, '从 Zabbix 官方模版提取（厂商=netgear, 大类=network, 来源=snmp）', 16, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
('QTech网络设备SNMP指标', 'network', 'snmp', NULL, 0, 1, '从 Zabbix 官方模版提取（厂商=qtech, 大类=network, 来源=snmp）', 17, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
('TP-Link网络设备SNMP指标', 'network', 'snmp', '14988', 0, 1, '从 Zabbix 官方模版提取（厂商=tp_link, 大类=network, 来源=snmp）', 18, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
('Ubiquiti网络设备SNMP指标', 'network', 'snmp', '41112', 0, 1, '从 Zabbix 官方模版提取（厂商=ubiquiti, 大类=network, 来源=snmp）', 19, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
('HPE服务器SNMP指标', 'server', 'snmp', '11', 0, 1, '从 Zabbix 官方模版提取（厂商=hpe, 大类=server, 来源=snmp）', 20, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
('IBM服务器SNMP指标', 'server', 'snmp', '437', 0, 1, '从 Zabbix 官方模版提取（厂商=ibm, 大类=server, 来源=snmp）', 21, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
('Supermicro服务器SNMP指标', 'server', 'snmp', '10876', 0, 1, '从 Zabbix 官方模版提取（厂商=supermicro, 大类=server, 来源=snmp）', 22, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
('APC其他设备SNMP指标', 'other', 'snmp', '318', 0, 1, '从 Zabbix 官方模版提取（厂商=apc, 大类=other, 来源=snmp）', 23, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
('NetApp其他设备SNMP指标', 'other', 'snmp', '2469', 0, 1, '从 Zabbix 官方模版提取（厂商=netapp, 大类=other, 来源=snmp）', 24, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
('通用网络设备SNMP指标', 'network', 'snmp', NULL, 0, 1, '从 Zabbix 官方模版提取（厂商=generic, 大类=network, 来源=snmp）', 25, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
('Morningstar网络设备SNMP指标', 'network', 'snmp', '22474', 0, 1, '从 Zabbix 官方模版提取（厂商=morningstar, 大类=network, 来源=snmp）', 26, '2026-08-19 09:32:57', '2026-08-19 09:32:57');

-- monitor_metric_template_group_items: 193 rows
DELETE FROM `monitor_metric_template_group_items`;
INSERT INTO `monitor_metric_template_group_items` (`group_id`, `template_id`, `id`, `created_at`, `updated_at`) VALUES
(1, 220, 1, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
(1, 221, 2, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
(2, 222, 3, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
(2, 223, 4, '2026-08-17 16:57:51', '2026-08-17 16:57:51'),
(3, 224, 5, '2026-08-17 16:57:52', '2026-08-17 16:57:52'),
(4, 225, 6, '2026-08-17 16:57:52', '2026-08-17 16:57:52'),
(4, 226, 7, '2026-08-17 16:57:52', '2026-08-17 16:57:52'),
(4, 227, 8, '2026-08-17 16:57:53', '2026-08-17 16:57:53'),
(4, 259, 9, '2026-08-17 16:57:53', '2026-08-17 16:57:53'),
(5, 228, 10, '2026-08-17 16:57:53', '2026-08-17 16:57:53'),
(5, 229, 11, '2026-08-17 16:57:53', '2026-08-17 16:57:53'),
(5, 230, 12, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(5, 231, 13, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(5, 232, 14, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(5, 233, 15, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(5, 244, 16, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(6, 234, 17, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(6, 235, 18, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(6, 236, 19, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(6, 237, 20, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(6, 238, 21, '2026-08-17 16:57:54', '2026-08-17 16:57:54'),
(7, 239, 22, '2026-08-17 16:57:55', '2026-08-17 16:57:55'),
(8, 240, 23, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(8, 241, 24, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(9, 242, 25, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(9, 243, 26, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(10, 245, 27, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(11, 246, 28, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(11, 247, 29, '2026-08-17 16:57:56', '2026-08-17 16:57:56'),
(13, 249, 31, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
(13, 251, 32, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
(14, 250, 33, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
(15, 252, 34, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
(16, 253, 35, '2026-08-17 16:57:57', '2026-08-17 16:57:57'),
(16, 254, 36, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(17, 255, 37, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(18, 256, 38, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(19, 257, 39, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(19, 258, 40, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(20, 260, 41, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(20, 261, 42, '2026-08-17 16:57:58', '2026-08-17 16:57:58'),
(21, 262, 43, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
(22, 263, 44, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
(23, 264, 45, '2026-08-17 16:57:59', '2026-08-17 16:57:59'),
(24, 265, 46, '2026-08-17 16:58:00', '2026-08-17 16:58:00'),
(1, 266, 47, '2026-08-19 09:32:56', '2026-08-19 09:32:56'),
(3, 267, 48, '2026-08-19 09:32:56', '2026-08-19 09:32:56'),
(3, 271, 49, '2026-08-19 09:32:56', '2026-08-19 09:32:56'),
(4, 268, 50, '2026-08-19 09:32:56', '2026-08-19 09:32:56'),
(4, 269, 51, '2026-08-19 09:32:56', '2026-08-19 09:32:56'),
(4, 270, 52, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(4, 365, 53, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(4, 366, 54, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 272, 55, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 273, 56, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 274, 57, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 275, 58, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 276, 59, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 277, 60, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 278, 61, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(6, 367, 62, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(7, 279, 63, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(8, 280, 64, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(8, 281, 65, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(8, 282, 66, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(9, 283, 67, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(9, 284, 68, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(5, 285, 69, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(5, 286, 70, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(25, 287, 71, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(10, 288, 72, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(11, 289, 73, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(11, 368, 74, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(11, 369, 75, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(11, 370, 76, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(11, 371, 77, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(12, 291, 79, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(13, 292, 82, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(13, 293, 83, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 294, 84, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 295, 85, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 296, 86, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 297, 87, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 298, 88, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 299, 89, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 300, 90, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 301, 91, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 302, 92, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 303, 93, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 304, 94, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 305, 95, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 306, 96, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 307, 97, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 308, 98, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 309, 99, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 310, 100, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 311, 101, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 312, 102, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 313, 103, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 314, 104, '2026-08-19 09:32:57', '2026-08-19 09:32:57');
INSERT INTO `monitor_metric_template_group_items` (`group_id`, `template_id`, `id`, `created_at`, `updated_at`) VALUES
(15, 315, 105, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 316, 106, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 317, 107, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 318, 108, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 319, 109, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 320, 110, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 321, 111, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 322, 112, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 323, 113, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 324, 114, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 325, 115, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 326, 116, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 327, 117, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 328, 118, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 329, 119, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 330, 120, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 331, 121, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 332, 122, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 333, 123, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 334, 124, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 335, 125, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 336, 126, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 337, 127, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 338, 128, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 339, 129, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(15, 340, 130, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 341, 131, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 342, 132, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 343, 133, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 344, 134, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 345, 135, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 346, 136, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 347, 137, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 348, 138, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 349, 139, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 350, 140, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 351, 141, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 352, 142, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 353, 143, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 354, 144, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 355, 145, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 356, 146, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 357, 147, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 358, 148, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(26, 359, 149, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(16, 360, 150, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(17, 361, 151, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(18, 362, 152, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(19, 363, 153, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(19, 364, 154, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(20, 372, 155, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(21, 373, 156, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(22, 374, 157, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 375, 158, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 376, 159, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 377, 160, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 378, 161, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 379, 162, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 380, 163, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 381, 164, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 382, 165, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 383, 166, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 384, 167, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 385, 168, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 386, 169, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 387, 170, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 388, 171, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(23, 389, 172, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(24, 392, 173, '2026-08-19 09:32:57', '2026-08-19 09:32:57'),
(12, 198, 176, '2026-08-20 14:19:26', '2026-08-20 14:19:26'),
(12, 196, 177, '2026-08-20 15:01:51', '2026-08-20 15:01:51'),
(12, 197, 178, '2026-08-20 15:01:51', '2026-08-20 15:01:51'),
(12, 393, 179, '2026-08-20 15:16:46', '2026-08-20 15:16:46'),
(7, 411, 180, '2026-08-20 17:13:37', '2026-08-20 17:13:37'),
(7, 412, 181, '2026-08-20 17:13:37', '2026-08-20 17:13:37'),
(7, 417, 182, '2026-08-20 17:13:37', '2026-08-20 17:13:37'),
(7, 418, 183, '2026-08-20 17:13:37', '2026-08-20 17:13:37'),
(7, 410, 184, '2026-08-20 17:13:37', '2026-08-20 17:13:37'),
(7, 414, 185, '2026-08-20 17:13:42', '2026-08-20 17:13:42'),
(7, 413, 186, '2026-08-20 17:13:42', '2026-08-20 17:13:42'),
(7, 421, 187, '2026-08-20 17:13:42', '2026-08-20 17:13:42'),
(7, 420, 188, '2026-08-20 17:13:42', '2026-08-20 17:13:42'),
(7, 419, 189, '2026-08-20 17:13:42', '2026-08-20 17:13:42'),
(7, 415, 190, '2026-08-20 17:13:46', '2026-08-20 17:13:46'),
(7, 416, 191, '2026-08-20 17:13:46', '2026-08-20 17:13:46'),
(7, 422, 192, '2026-08-20 17:13:46', '2026-08-20 17:13:46'),
(22, 427, 193, '2026-08-20 17:13:56', '2026-08-20 17:13:56'),
(22, 426, 194, '2026-08-20 17:13:56', '2026-08-20 17:13:56'),
(10, 199, 195, '2026-08-20 17:14:38', '2026-08-20 17:14:38'),
(10, 424, 196, '2026-08-20 17:14:38', '2026-08-20 17:14:38'),
(10, 200, 197, '2026-08-20 17:14:38', '2026-08-20 17:14:38'),
(10, 425, 198, '2026-08-20 17:14:38', '2026-08-20 17:14:38'),
(10, 423, 199, '2026-08-20 17:14:38', '2026-08-20 17:14:38');

-- monitor_device_type_recommends: 3 rows
DELETE FROM `monitor_device_type_recommends`;
INSERT INTO `monitor_device_type_recommends` (`device_type`, `categories`, `id`, `created_at`, `updated_at`) VALUES
('network', '["system_uptime", "if_status", "if_in_octets", "if_out_octets", "if_in_errors", "if_out_errors", "if_in_discards", "if_out_discards", "if_speed"]', 7, '2026-08-07 11:28:04', '2026-08-13 14:40:41'),
('server', '["system_uptime", "temperature", "voltage", "fan", "power_supply", "memory", "storage", "cpu_usage", "storage_size", "storage_used"]', 8, '2026-08-07 11:28:04', '2026-08-13 14:40:41'),
('other', '["system_uptime", "if_status", "if_in_octets", "if_out_octets"]', 9, '2026-08-07 11:28:04', '2026-08-13 14:40:41');

-- monitor_dynamic_config: 1 rows
DELETE FROM `monitor_dynamic_config`;
INSERT INTO `monitor_dynamic_config` (`config_key`, `config_value`, `value_type`, `description`, `updated_at`, `updated_by`) VALUES
('MONITOR_CONSECUTIVE_FAILURES_THRESHOLD', '3', 'int', '连续失败阈值（达到后判定不可达并告警）', '2026-08-11 10:51:00', '2');


SET FOREIGN_KEY_CHECKS=1;
-- Total: 985 rows across 12 tables
-- seed_data.sql END