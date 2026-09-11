# -*- coding: utf-8 -*-
"""
应用工厂模块

提供Flask应用创建和配置功能。
"""
import hmac
import ipaddress
import os

from app.utils.logging import get_logger

from flask import Flask, abort, request
from flask_cors import CORS

from app.utils.logging.manager import logging_manager
from app.exceptions import register_error_handlers
from config import get_config
from extensions import db, check_mysql_session_timezone
from app.infra import report_netmiko_log_switch

logger = get_logger(__name__)

_METRICS_NOTICE = (
    "# ipip /metrics\n"
    "# ai_llm_* / ai_skill_* 为跨进程（Redis）聚合值：每个 gunicorn worker 返回\n"
    "# 相同的数字，抓取多 worker 时会得到 N 条同值序列。查询请用 max() / avg()\n"
    "# / topk(1, ...)，切勿用 sum()，否则数值会被放大 N 倍。\n"
    "# process_* / python_gc_* / python_info 为本进程指标，按 instance 区分，\n"
    "# 可正常聚合。\n"
    "# window=\"day\" 的日期边界按服务器本地时区计算。\n"
)


def create_app(config_name: str = None) -> Flask:
    """创建Flask应用实例（应用工厂模式）

    Args:
        config_name: 配置名称（development、testing、production）

    Returns:
        Flask: Flask应用实例
    """
    app = Flask(__name__, 
                static_folder='../frontend-new/dist',
                static_url_path='')
    
    app.url_map.strict_slashes = False

    config = get_config(config_name)
    app.config.from_object(config)

    config.init_app(app)

    init_extensions(app)

    register_blueprints(app)

    register_middlewares(app)

    register_error_handlers(app)

    logging_manager.init_app(app)

    report_netmiko_log_switch()

    if config_name != "testing":
        try:
            from app.services.ai.config_admin_service import start_config_sync
            start_config_sync()
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.config.start_sync_failed %s", e)

        try:
            from app.services.ai.config_admin_service import report_ai_config_mode
            report_ai_config_mode()
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.config.mode_report_failed %s", e)

    if config_name != "testing":
        from app.services.notification_cleanup import start_cleanup_scheduler
        start_cleanup_scheduler(app)

    if config_name != "testing":
        from app.services.asset_warranty_alert import start_asset_warranty_alert_scheduler
        start_asset_warranty_alert_scheduler(app)

    if config_name != "testing":
        from app.services.channels.inbox import InboxChannel
        from app.services.channels.email import EmailChannel
        from app.services.channels.wechat_work import WeChatWorkWebhookChannel
        from app.services.channels.feishu import FeishuWebhookChannel
        from app.services.notification_service import NotificationService
        from app.services.notification_delivery_worker import start_delivery_worker
        from app.services.ops_alert_bridge import register_ops_alert_callbacks

        NotificationService.register_personal_channel(InboxChannel())
        NotificationService.register_personal_channel(EmailChannel())
        from app.services.channels.voice import VoiceChannel
        NotificationService.register_personal_channel(VoiceChannel())
        NotificationService.register_broadcast_channel(WeChatWorkWebhookChannel())
        NotificationService.register_broadcast_channel(FeishuWebhookChannel())

        start_delivery_worker(app)
        register_ops_alert_callbacks()

        in_process = os.getenv("MONITOR_WORKER_IN_PROCESS")
        in_process = (
            in_process.lower() == "true" if in_process is not None
            else app.config.get("MONITOR_WORKER_IN_PROCESS", True)
        )
        if app.config.get("MONITOR_ENABLED", True) and in_process:
            from app.services.monitoring.monitor_worker import start_monitor_worker
            monitor_threads, monitor_stop_event = start_monitor_worker(app)
            import atexit
            atexit.register(
                lambda: (
                    monitor_stop_event.set(),
                    *[t.join(timeout=5) for t in monitor_threads],
                )
            )

        if config_name != "testing":

            from app.services.scan_scheduler_service import start_scan_scheduler

            start_scan_scheduler(app)

        from app.services.monitoring.heartbeat import (
            in_app_service_name,
            start_heartbeat_thread,
        )

        service_name = in_app_service_name(app.config)
        if service_name:
            start_heartbeat_thread(service_name)

    try:
        from app.celery_app import init_celery
        init_celery(app)
        app.extensions["celery"] = True
    except Exception as e:  # noqa: BLE001
        logger.warning("celery.init_failed %s", e)
        app.extensions["celery"] = False

    _register_db_cli(app)
    _register_monitor_cli(app)
    _register_schema_migration_cli(app)
    _register_ldap_cli(app)
    _warn_on_schema_drift(app)

    logger.info(f"应用创建成功 (环境: {config_name or 'development'})")

    return app


def init_extensions(app: Flask):
    """初始化Flask扩展

    Args:
        app: Flask应用实例
    """
    db.init_app(app)

    with app.app_context():
        check_mysql_session_timezone()

    CORS(
        app,
        origins=app.config["CORS_ORIGINS"],
        methods=app.config["CORS_METHODS"],
        allow_headers=app.config["CORS_ALLOW_HEADERS"],
        supports_credentials=True,
    )

    logger.info("扩展初始化完成")


def register_blueprints(app: Flask):
    """注册蓝图

    按子域分组注册，便于维护和路由冲突检测。

    Args:
        app: Flask应用实例
    """
    @app.route("/")
    def frontend_index():
        """前端首页"""
        from flask import send_from_directory
        return send_from_directory(app.static_folder, 'index.html')
    
    @app.route("/index.html")
    def frontend_index_html():
        """前端首页（HTML文件）"""
        from flask import send_from_directory
        return send_from_directory(app.static_folder, 'index.html')
    
    @app.route("/auth")
    def frontend_auth():
        """前端登录页"""
        from flask import send_from_directory
        return send_from_directory(app.static_folder, 'auth.html')
    
    @app.route("/auth.html")
    def frontend_auth_html():
        """前端登录页（HTML文件）"""
        from flask import send_from_directory
        return send_from_directory(app.static_folder, 'auth.html')
    
    @app.route("/assets/<path:filename>")
    def frontend_assets(filename):
        """前端资源文件"""
        from flask import send_from_directory
        import os
        return send_from_directory(os.path.join(app.static_folder, 'assets'), filename)
    
    @app.route("/config/<path:filename>")
    def frontend_config(filename):
        """前端配置文件"""
        from flask import send_from_directory
        import os
        return send_from_directory(os.path.join(app.static_folder, 'config'), filename)
    
    if app.config.get("METRICS_ENABLED", True):
        def _metrics_allowed_ips():
            """解析 METRICS_ALLOWED_IPS 为 ip_network 列表（忽略非法条目）。"""
            nets = []
            for n in (app.config.get("METRICS_ALLOWED_IPS") or []):
                try:
                    nets.append(ipaddress.ip_network(n, strict=False))
                except ValueError:
                    logger.warning("METRICS_ALLOWED_IPS 含非法条目，已忽略: %s", n)
            return nets

        def _metrics_client_ip():
            """获取真实客户端 IP（n7：不可盲信 X-Forwarded-For）。

            仅在直连对端（remote_addr）落在 TRUSTED_PROXIES 内时，才采信代理
            追加的 XFF 最右段；否则一律以 remote_addr 为准，防止伪造 XFF 绕过白名单。
            """
            peer = request.remote_addr or ""
            try:
                peer_ip = ipaddress.ip_address(peer)
                trusted = any(peer_ip in net for net in _metrics_trusted_nets())
            except ValueError:
                trusted = False
            xff = request.headers.get("X-Forwarded-For", "")
            if trusted and xff:
                return xff.split(",")[-1].strip()
            return peer

        def _metrics_trusted_nets():
            """解析 TRUSTED_PROXIES 为 ip_network 列表（与 https_guard 同一口径）。"""
            nets = []
            for n in (app.config.get("TRUSTED_PROXIES") or []):
                try:
                    nets.append(ipaddress.ip_network(n, strict=False))
                except ValueError:
                    pass
            return nets

        @app.route("/metrics")
        def prometheus_metrics():
            """Prometheus 抓取端点：AI 跨进程聚合指标 + 本进程系统指标。

            安全（opt-in 加固，默认适合内网直抓；公网务必同时开启下列两项）：
            - METRICS_TOKEN 为空时免鉴权；设置后必须带 ?token=<值> 或
              Authorization: Bearer <值> 才放行；
            - METRICS_ALLOWED_IPS 非空时，仅放行白名单来源 IP（与口令校验叠加）。
            """
            allow = _metrics_allowed_ips()
            if allow:
                try:
                    client_ip = ipaddress.ip_address(_metrics_client_ip())
                except ValueError:
                    client_ip = None
                if client_ip is None or not any(client_ip in net for net in allow):
                    logger.warning("拒绝非白名单 IP 的 /metrics 抓取: %s",
                                   request.remote_addr)
                    abort(403)

            expected = app.config.get("METRICS_TOKEN") or ""
            if expected:
                auth = request.headers.get("Authorization", "")
                provided = request.args.get("token") or (
                    auth[7:] if auth.lower().startswith("bearer ") else "")
                if not hmac.compare_digest(provided or "", expected):
                    abort(403)

            from flask import Response

            from app.services.ai.metrics import get_metrics

            snapshot = get_metrics()
            head = "# pid=%s source=%s\n" % (snapshot.get("pid"),
                                             snapshot.get("metrics_source"))
            body = _METRICS_NOTICE + head + (snapshot.get("raw") or "")
            return Response(body, mimetype="text/plain; version=0.0.4")

    @app.route("/<path:filename>")
    def frontend_files(filename):
        """前端静态文件（HTML、JS、CSS等）"""
        from flask import send_from_directory
        import os
        
        file_path = os.path.join(app.static_folder, filename)
        if os.path.exists(file_path):
            return send_from_directory(app.static_folder, filename)
        else:
            from app.api.base import APIResponse
            return APIResponse.error(message=f"文件不存在: {filename}", error_code="NOT_FOUND", status_code=404)
    
    @app.route("/api")
    def api_index():
        """API根路径处理器"""
        from app.api.base import APIResponse
        return APIResponse.success(
            data={
                "message": "欢迎使用 IP/IP 地址管理系统 API",
                "version": "1.0.0",
                "endpoints": {
                    "health": "/api/health/check",
                    "auth": "/api/auth",
                    "users": "/api/users",
                    "rooms": "/api/rooms",
                    "cabinets": "/api/cabinets",
                    "devices": "/api/devices",
                    "customers": "/api/customers",
                }
            },
            message="API 服务正常运行"
        )

    from app.api import auth_bp, cabinet_bp, customer_bp, device_bp, health_bp, room_bp, user_bp
    from app.api.wechat import wechat_bp
    from app.api.routes import api_bp  # 导入高级功能路由
    from app.api.logs import logs_bp  # 导入日志API
    from app.api.device_connection import device_connection_bp  # 导入设备连接API
    from app.api.rbac import register_rbac_routes  # 导入RBAC路由
    from app.api.device_storage import device_storage_bp  # 导入设备存储API
    from app.api.device_nics_port import device_nics_port_bp, _port_bp, _template_bp  # 导入网卡端口API
    from app.api.deployment_plan import deployment_plan_bp  # 上架方案查询API（只读推荐）

    from app.api.ip_routes import router as ip_new_bp
    from app.api.network_routes import router as network_new_bp
    from app.api.switch_routes import router as switch_new_bp

    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(deployment_plan_bp, url_prefix="/api/deployment")  # 上架方案查询
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")  # 注册日志API
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(wechat_bp)  # wechat_bp 已经在定义时设置了 url_prefix
    app.register_blueprint(room_bp, url_prefix="/api/rooms")
    app.register_blueprint(device_bp, url_prefix="/api/devices")
    from app.api.device_import import device_import_bp  # 设备导入导出（从 device.py 拆分）
    app.register_blueprint(device_import_bp, url_prefix="/api/devices")
    app.register_blueprint(cabinet_bp, url_prefix="/api/cabinets")
    from app.api.cabinet_import import cabinet_import_bp  # 机柜导入导出（从 cabinet.py 拆分）
    app.register_blueprint(cabinet_import_bp, url_prefix="/api/cabinets")
    app.register_blueprint(customer_bp, url_prefix="/api/customers")
    from app.api.customer_import import customer_import_bp  # 客户导入导出（从 customer.py 拆分）
    app.register_blueprint(customer_import_bp, url_prefix="/api/customers")
    app.register_blueprint(device_connection_bp)  # 注册设备连接API
    app.register_blueprint(device_storage_bp)  # 注册设备存储API
    app.register_blueprint(device_nics_port_bp)  # 注册网卡端口API
    app.register_blueprint(_port_bp)  # 注册单端口操作API
    app.register_blueprint(_template_bp)  # 注册网卡模板API

    app.register_blueprint(ip_new_bp)
    app.register_blueprint(network_new_bp)
    app.register_blueprint(switch_new_bp)

    from app.api.audit import audit_bp
    from app.api.vlan import vlan_bp
    app.register_blueprint(audit_bp, url_prefix="/api/audit")
    app.register_blueprint(vlan_bp, url_prefix="/api/vlans")

    from app.api.link_aggregation import lag_bp, lag_global_bp
    from app.api.device_config import device_config_bp
    app.register_blueprint(lag_bp, url_prefix="/api/switch")
    app.register_blueprint(lag_global_bp, url_prefix="/api/link-aggregation")
    app.register_blueprint(device_config_bp, url_prefix="/api/devices")

    from app.api.ip_audit import ip_audit_bp
    app.register_blueprint(ip_audit_bp, url_prefix="/api/ip-audit")

    from app.api.device_port_routes import router as device_port_router
    app.register_blueprint(device_port_router)

    from app.api.monitor import monitor_bp
    app.register_blueprint(monitor_bp, url_prefix="/api/monitor")

    from app.api.ai.ai_routes import bp as ai_bp
    app.register_blueprint(ai_bp, url_prefix="/api/ai")

    from app.api.topology_routes import router as topology_router
    app.register_blueprint(topology_router)

    app.register_blueprint(api_bp)  # 注册主API蓝图（仅含错误处理）
    from app.api.dashboard import dashboard_bp
    from app.api.errors import errors_bp

    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(errors_bp, url_prefix="/api/errors")

    from app.api.component_template import component_template_bp
    app.register_blueprint(component_template_bp)

    from app.api.virtual_room_routes import virtual_room_bp
    app.register_blueprint(virtual_room_bp, url_prefix="/api/virtual-rooms")

    from app.api.notification_routes import router as notification_bp
    app.register_blueprint(notification_bp)

    from app.api.webhook_config_routes import router as webhook_config_bp
    app.register_blueprint(webhook_config_bp)

    from app.api.mail_settings_routes import router as mail_settings_bp
    app.register_blueprint(mail_settings_bp)

    from app.api.voice_settings_routes import router as voice_settings_bp
    from app.api.voice_callback_routes import router as voice_callback_bp
    app.register_blueprint(voice_settings_bp)
    app.register_blueprint(voice_callback_bp)

    from app.api.voice_callback_routes import warn_if_callback_protection_missing
    warn_if_callback_protection_missing(app)

    from app.api.sse import sse_bp
    app.register_blueprint(sse_bp, url_prefix="/api/sse")

    register_rbac_routes(app)

    from app.openapi.views import openapi_bp
    app.register_blueprint(openapi_bp, url_prefix="/api")

    logger.info("蓝图注册完成")


def register_middlewares(app: Flask):
    """注册中间件

    Args:
        app: Flask应用实例
    """
    from app.middleware.audit_middleware import AuditMiddleware
    AuditMiddleware(app)

    from app.middleware.https_guard import register_https_guard
    register_https_guard(app)

    logger.info("中间件注册完成")


def create_tables(app: Flask):
    """创建数据库表

    Args:
        app: Flask应用实例
    """
    with app.app_context():
        from app.models import Cabinet, Customer, Device, Room, User
        from app.models.rbac import Role, Permission, UserRole, RolePermission

        db.create_all()

        logger.info("数据库表创建完成")


def drop_tables(app: Flask, confirm: bool = False):
    """删除所有数据库表（谨慎使用，不可逆！）

    Args:
        app: Flask应用实例
        confirm: 必须为 True 才会真正执行删除。任何调用路径都必须显式确认，
                 以防在代码或交互式终端中误清空数据库。

    Raises:
        RuntimeError: 未确认、或生产环境缺少强制环境变量时拒绝执行。
    """
    if not confirm:
        raise RuntimeError(
            "拒绝执行 drop_tables：该操作会删除全部数据库表且不可逆。"
            "请显式传入 confirm=True（CLI: `flask drop-tables --confirm`）后再执行。"
        )

    if _is_production(app) and os.getenv("FORCE_DROP_PRODUCTION") != "1":
        raise RuntimeError(
            "拒绝在生产环境执行 drop_tables：即使已 --confirm，仍需显式设置环境变量 "
            "FORCE_DROP_PRODUCTION=1 才能放行，以防误清空生产数据库。"
        )

    with app.app_context():
        db.drop_all()
        logger.warning("所有数据库表已删除（不可逆操作已执行）")


def _is_production(app: Flask) -> bool:
    """粗略判断当前是否为生产环境。"""
    env = (
        app.config.get("ENV") or os.getenv("ENV") or os.getenv("FLASK_ENV") or "production"
    ).lower()
    return env == "production"


def _register_db_cli(app: Flask):
    """注册数据库维护相关的 Flask CLI 命令。

    - drop-tables  : 删除所有表，必须 --confirm（生产环境还需 FORCE_DROP_PRODUCTION=1）
    - create-tables: 创建所有表（幂等，已存在则跳过）
    """
    import click

    @app.cli.command("drop-tables")
    @click.option("--confirm", is_flag=True, help="必须显式传入才会执行删除（不可逆）")
    def drop_tables_cmd(confirm):
        """删除所有数据库表（谨慎使用，不可逆）"""
        try:
            drop_tables(app, confirm=confirm)
        except RuntimeError as e:
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)

    @app.cli.command("create-tables")
    def create_tables_cmd():
        """创建所有数据库表（幂等，已存在则跳过）"""
        create_tables(app)


def _register_monitor_cli(app: Flask):
    """注册监控时序归档 / 分区管理相关的 Flask CLI 命令。

    - monitor-archive          : 降采样 + 事件分区清理 + 预聚合表清理（cron 03:00）
    - monitor-manage-partitions: 预创建未来事件/指标分区（cron 02:00，在归档前执行）

    分区 / 降采样 DDL 仅 MySQL 生效；非 MySQL（本地 SQLite 等）下命令为空跑（no-op）。
    """
    import click

    from extensions import db
    from app.persistence.monitor_timeseries_repository import MonitorTimeseriesRepository

    @app.cli.command("monitor-archive")
    def monitor_archive_cmd():
        """监控时序归档：降采样 + 事件分区清理 + 预聚合表清理（建议 cron 03:00）

        架构3 分层保留：events(30s,7d) → hourly(1h,90d) → daily(1d,730d)
        """
        repo = MonitorTimeseriesRepository(db.session)
        try:
            repo.downsample_to_hourly()
            repo.downsample_to_daily()
            dropped = repo.drop_expired_event_partitions()
            metric_dropped = repo.drop_expired_metric_partitions()
            deleted = repo.cleanup_hourly()
            daily_deleted = repo.cleanup_daily()
        except Exception as e:  # noqa: BLE001 - CLI 顶层捕获并报告
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)
        click.echo(
            f"monitor-archive done: "
            f"downsample_ok=1 dropped_partitions={dropped} "
            f"metric_dropped_partitions={metric_dropped} "
            f"hourly_deleted={deleted} daily_deleted={daily_deleted}"
        )

    @app.cli.command("monitor-manage-partitions")
    def monitor_manage_partitions_cmd():
        """预创建未来事件/指标分区（建议 cron 02:00，在归档前执行）"""
        repo = MonitorTimeseriesRepository(db.session)
        try:
            added = repo.add_future_event_partitions()
            metric_added = repo.add_future_metric_partitions()
        except Exception as e:  # noqa: BLE001 - CLI 顶层捕获并报告
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)
        click.echo(
            f"monitor-manage-partitions done: added={added} metric_added={metric_added}"
        )

    @app.cli.command("monitor-outbox-cleanup")
    @click.option(
        "--sent-days",
        default=30,
        type=int,
        help="sent 行保留天数（默认 30）",
    )
    @click.option(
        "--failed-days",
        default=90,
        type=int,
        help="failed 行保留天数（默认 90）",
    )
    def monitor_outbox_cleanup_cmd(sent_days, failed_days):
        """清理超期 sent/failed 告警 outbox 行（建议 cron 04:00）

        用法: flask monitor-outbox-cleanup [--sent-days 30] [--failed-days 90]
        """
        from app.persistence.monitor_alert_outbox_repository import (
            MonitorAlertOutboxRepository,
        )

        repo = MonitorAlertOutboxRepository(db.session)
        try:
            result = repo.cleanup_expired(
                sent_retention_days=sent_days,
                failed_retention_days=failed_days,
            )
            db.session.commit()
        except Exception as e:  # noqa: BLE001 - CLI 顶层捕获并报告
            db.session.rollback()
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)
        click.echo(
            f"monitor-outbox-cleanup done: "
            f"sent_deleted={result['sent_deleted']}, "
            f"failed_deleted={result['failed_deleted']}"
        )

    @app.cli.command("snmp-mib-scan")
    @click.argument("ip")
    @click.argument("protocol", default="v2c")
    @click.option("--community", default="public", help="SNMP v2c community")
    @click.option("--out", default=None, help="输出 JSON 文件路径")
    def snmp_mib_scan_cmd(ip, protocol, community, out):
        """SNMP MIB 扫描：自动探测设备支持的 OID，生成指标接入清单。

        用法: flask snmp-mib-scan <ip> [v2c|v3] [--community public] [--out metrics.json]
        """
        from app.services.monitoring.snmp_mib_service import scan_to_file

        if protocol == "v3":
            click.echo("v3 扫描需通过凭证管理接口配置，请改用 v2c 或后续扩展")
            raise SystemExit(1)
        cred = {"community": community, "snmp_version": "v2c"}
        out_path = out or f"detected_metrics_{ip.replace('.', '_')}.json"
        try:
            scan_to_file(ip, cred, out_path)
        except Exception as e:  # noqa: BLE001 - CLI 顶层捕获并报告
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)
        click.echo(f"snmp-mib-scan done: 清单已写入 {out_path}（登记 OID 到指标模板即完成接入）")

    @app.cli.command("baseline-recompute")
    @click.option(
        "--window-days",
        default=28,
        type=int,
        help="滑动窗口天数（默认 28）",
    )
    def baseline_recompute_cmd(window_days):
        """重算所有设备指标基线（建议 cron 01:00，与 monitor-archive 错开）

        Phase 3.1：从 device_metric_timeseries 按近 window_days 样本计算滑动基线。
        样本 ≥28 天按 hour×weekday 分桶；7-28 天降级全局均值；<7 天标记 insufficient_samples。

        用法: flask baseline-recompute [--window-days 28]
        """
        from app.services.ai.baseline_service import BaselineService

        try:
            service = BaselineService()
            updated = service.recompute_all_baselines(window_days=window_days)
        except Exception as e:  # noqa: BLE001 - CLI 顶层捕获并报告
            db.session.rollback()
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(1)
        click.echo(f"baseline-recompute done: updated_rows={updated}")


def _register_schema_migration_cli(app: Flask):
    """注册 Schema 版本化迁移 CLI 命令。

    - db-upgrade: 按序应用 migrations/versions/ 中未记录的迁移（幂等可重跑）
    - db-status : 查看已应用 / 待应用版本
    - db-check  : 校验 ORM 模型与实际库是否漂移（缺表/缺列），漂移以退出码 1 报警

    详见 app/services/schema_migration_service.py 模块 docstring。
    """
    import os

    import click
    import pymysql

    from app.services.schema_migration_service import SchemaMigrationRunner

    _VERSIONS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "migrations", "versions",
    )

    def _connect():
        conn = pymysql.connect(
            host=app.config.get("MYSQL_HOST", os.getenv("MYSQL_HOST", "localhost")),
            port=int(app.config.get("MYSQL_PORT", os.getenv("MYSQL_PORT", 3306))),
            user=app.config.get("MYSQL_USER", os.getenv("MYSQL_USER", "root")),
            password=app.config.get("MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", "")),
            database=app.config.get("MYSQL_DATABASE", os.getenv("MYSQL_DATABASE", "ip_management")),
            charset="utf8mb4",
            autocommit=False,
        )
        try:
            cur = conn.cursor()
            cur.execute("SET SESSION lock_wait_timeout = 60")
            cur.close()
        except Exception:  # noqa: BLE001 - 非MySQL后端（如测试）无此变量，忽略
            pass
        return conn

    @app.cli.command("db-status")
    def db_status_cmd():
        """查看 schema 迁移状态：已应用版本 / 待应用迁移列表"""
        conn = _connect()
        try:
            runner = SchemaMigrationRunner(conn, _VERSIONS_DIR)
            applied = sorted(runner.applied_versions())
            pending = runner.pending()
        finally:
            conn.close()
        click.echo(f"已应用: {', '.join(applied) if applied else '（无）'}")
        if pending:
            click.echo("待应用:")
            for m in pending:
                click.echo(f"  {m.version}  {m.description}  ({m.path.name})")
        else:
            click.echo("待应用: （无，schema 已是最新）")

    @app.cli.command("db-upgrade")
    @click.option("--dry-run", is_flag=True, help="只打印将应用的迁移，不执行（只读预检）")
    def db_upgrade_cmd(dry_run):
        """应用待执行的 schema 迁移（幂等，失败重跑安全；升级前建议先备份）"""
        conn = _connect()
        try:
            runner = SchemaMigrationRunner(conn, _VERSIONS_DIR)
            if dry_run:
                pending = runner.pending()
                if not pending:
                    click.echo("dry-run: 无待应用迁移")
                    return
                click.echo("dry-run: 将按序应用以下迁移（未执行）：")
                for m in pending:
                    click.echo(f"  {m.version}  {m.description}  ({m.path.name})")
                return
            applied = runner.run()
        finally:
            conn.close()
        if applied:
            click.echo(f"db-upgrade done: applied={', '.join(applied)}")
        else:
            click.echo("db-upgrade done: 无待应用迁移，schema 已是最新")

    @app.cli.command("db-check")
    def db_check_cmd():
        """校验 ORM 模型与实际库是否漂移（缺表/缺列）；发现漂移以退出码 1 报警。

        db-upgrade 只能覆盖「已写了迁移」的变更，写漏或跑漏都需靠本命令兜底。

        用法: flask db-check
        """
        import sys

        from app.services.schema_migration_service import collect_missing_columns

        if db.engine.dialect.name != "mysql":
            click.echo("db-check skipped: 非 MySQL 方言（无 information_schema）")
            return
        problems = collect_missing_columns(db.session)
        if problems:
            click.echo(f"检测到 {len(problems)} 处 schema 漂移（模型已声明但库中不存在）：")
            for p in problems:
                click.echo(f"  {p}")
            click.echo(
                "处理：在 migrations/versions/ 补 NNNN_*.py 增量迁移，然后 flask db-upgrade"
            )
            sys.exit(1)
        click.echo("db-check OK：无表/列漂移")


def _register_ldap_cli(app: Flask):
    """注册 LDAP 企业身份集成自检命令。

    - ldap-check: 校验 LDAP 必填项、映射语法，以及映射表/默认角色指向的每个
      角色在 roles 表中存在且启用；发现问题以退出码 1 报警。
      不需要连真实域控，可直接用于上线检查清单（对应手册 §2 检查步骤）。

    为什么角色缺失不是「补数据迁移」：映射表是环境配置、角色是 RBAC 业务数据，
    每个客户集合不同；迁移只承载产品级种子角色。缺角色属于**部署疏漏**，
    正确防线是部署期 fail-fast（本命令），而不是把某个环境的角色烧进迁移。
    """
    import click

    from app.persistence.rbac_repository import RoleRepository
    from app.services.ldap_config_check import collect_ldap_check_issues

    @app.cli.command("ldap-check")
    def ldap_check_cmd():
        """校验 LDAP 配置与角色目标（LDAP_ENABLED=false 时输出 skipped）"""
        issues = collect_ldap_check_issues(app.config, RoleRepository())
        if not issues:
            if not app.config.get("LDAP_ENABLED"):
                click.echo("ldap-check skipped: LDAP 未启用（关闭态不做校验）")
            else:
                click.echo("ldap-check OK：映射与默认角色全部存在且启用")
            return
        for issue in issues:
            click.echo(f"ERROR: {issue}", err=True)
        raise SystemExit(1)


def _warn_on_schema_drift(app: Flask) -> None:
    """启动时比对 ORM 模型与实际库结构，漂移则告警（只读，绝不阻塞启动）。

    防复发机制：历史事故为模型新增 `monitor_dynamic_config.created_at` 而存量库
    未执行对应增量迁移，ORM 按模型全列拼 SELECT 报 1054，整条监控探测链路 500。
    `flask db-upgrade` 覆盖不到「迁移没写」或「写了没跑」两种漏网，只能靠本项在
    启动第一时间暴露，而不是等某个用户请求踩到。

    非 MySQL 方言（如测试的 SQLite）与查询异常一律跳过：自检不得拖垮启动。
    """
    with app.app_context():
        try:
            if db.engine.dialect.name != "mysql":
                return
            from app.services.schema_migration_service import collect_missing_columns

            problems = collect_missing_columns(db.session)
        except Exception as e:  # noqa: BLE001 - 自检失败不得阻塞启动
            logger.warning("schema drift check 跳过：%s", e)
            return
    if problems:
        logger.warning(
            "检测到 %d 处 schema 漂移（模型已声明但库中不存在）：", len(problems)
        )
        for p in problems:
            logger.warning("  %s", p)
        logger.warning(
            "处理：在 migrations/versions/ 补 NNNN_*.py 增量迁移后执行 flask db-upgrade"
        )
