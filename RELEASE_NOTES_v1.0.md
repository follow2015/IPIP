# IPIP v1.0 Release Notes

**IP / IPAM 管理系统** — 机房、机柜、设备、IP 分配、VLAN、交换机、监控告警、客户管理一体化平台。

## 功能清单

### 机房与机柜管理
- 机房 CRUD（名称、位置、联系人、备注）
- 机柜 CRUD（机房内机柜，行列编号、容量管理）
- 虚拟机房与成员管理

### 设备管理
- 服务器/交换机/网络设备统一台账
- 设备硬件信息（CPU/内存/硬盘/网卡/GPU 配件模板）
- 设备配置备份与变更历史
- 设备连接拓扑（端口级连接关系）
- 设备导入导出（Excel/CSV 批量）
- 设备回收站（软删除恢复）
- 配件模板库（162 条预置：CPU/内存/硬盘/网卡/GPU）

### IP 地址管理（IPAM）
- IP 网段与子网管理
- IP 地址分配、回收、Ban/Unban
- IP 分配日志审计
- IP 与设备/端口绑定关系
- IP ARP/MAC 表自动发现与对账

### 网络管理
- VLAN 管理（84 条预置）
- 链路聚合组（LAG）
- 交换机端口管理（端口状态、VLAN 成员、IP 绑定）
- 交换机路由表查看
- 网络拓扑可视化（@antv/g6 图引擎）

### 交换机操作
- SSH 批量配置下发（华为/H3C/Cisco 多厂商适配）
- 端口配置同步
- ARP/MAC/接口/VLAN 信息采集（TextFSM 模板解析）
- 会话日志与操作审计

### 监控与告警
- 设备健康监控（SNMP/BMC/IPMI/Zabbix 多协议）
- 监控指标模板（239 条预置）+ 指标分组
- OID 分类规则（159 条预置）
- 厂商品牌识别（27 条预置）
- 告警规则与静默策略
- 告警升级策略（escalation policy）
- 告警依赖规则（抑制级联告警）
- 指标时序存储（原始/小时/日聚合）
- SLA 目标与达成率统计
- 独立监控进程（Route A：asyncio 事件循环，与 Flask HTTP 解耦）

### 实时推送
- SSE 事件流（交换机级 + 全局）
- Redis Pub/Sub 事件总线
- 断线重放（since_seq 增量推送）
- 连接数限流

### 客户管理
- 客户 CRUD（名称、联系人、合同）
- 客户终止存档（PDF 导出）
- 客户与设备/IP 关联

### 用户与权限
- RBAC 角色权限（4 角色 / 63 权限码 / 107 映射）
- 用户管理（启用/禁用/角色分配）
- JWT 认证（access/refresh token）
- 微信小程序登录
- 操作审计日志
- 登录日志

### 通知
- 站内通知
- Webhook 外部通知
- 邮件通知配置

### 仪表盘
- 资源统计概览（设备/IP/客户/告警）
- 监控指标看板

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.14 · Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.4 · Redis 8 |
| 认证 | JWT · bcrypt · 微信 OAuth |
| 网络协议 | pysnmp · netmiko · pyghmi（IPMI） |
| 前端 | TypeScript 6 · React 19 · Vite 8 · Ant Design 6 |
| 状态 | Zustand 5（客户端）· TanStack Query 5（服务端） |
| 路由 | React Router 7 |
| 图表 | @ant-design/charts · @antv/g6 |
| 实时网关 | Starlette · uvicorn · Redis Pub/Sub · SSE |
| 导出 | pandas · openpyxl · reportlab（PDF） |

## 部署

```bash
git clone git@github.com:follow2015/IPIP.git
cd IPIP
bash scripts/install.sh    # venv + 前端构建 + 数据库 + 种子
vi .env                    # 配置实际密码
bash scripts/install.sh    # 重跑（跳过已完成步骤）
bash scripts/start.sh      # 启动
```

**一键安装**：`scripts/install.sh`（Python venv + pnpm 前端构建 + MySQL schema + 种子数据）
**一键启动**：`scripts/start.sh`（Flask + realtime_gateway + monitor 三进程管理）

## 数据库

- 65 张表（完整 DDL 见 `database/schema.sql`）
- 1069 行配置类种子数据（权限/角色/指标模板/OID 规则/VLAN/配件模板等）
- 默认管理员账户（首次安装时随机生成密码并打印）

## License

Apache License 2.0
