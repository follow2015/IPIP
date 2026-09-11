# -*- coding: utf-8 -*-
"""
配置管理模块

提供多环境配置支持，包括开发、测试和生产环境。
配置可以从环境变量、配置文件和命令行参数中读取。
"""
import os
import secrets
import warnings
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


_ENV_FALLBACKS: list[str] = []


def _env_num(key: str, default, min_value=None, cast=int):
    """读取数值型环境变量，空串/非法值回退默认值而不是抛异常。

    `AI_TIMEOUT=`（空值）会让裸 int() 在 config 导入阶段抛 ValueError，
    进程直接起不来且只有一行 traceback——部署脚本多打一个等号就踩中。
    这里统一回退到默认值并记账，由启动日志显式告警。

    Args:
        key: 环境变量名。
        default: 解析失败时使用的默认值（决定返回类型）。
        min_value: 最小值，超出范围同样回退（如 timeout <= 0 无意义）。
        cast: int 或 float。

    Returns:
        解析后的数值，或 default。
    """
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        if raw is not None:
            _ENV_FALLBACKS.append(f"{key}=(空值)")
        return default
    try:
        value = cast(str(raw).strip())
    except (TypeError, ValueError):
        _ENV_FALLBACKS.append(f"{key}={raw}")
        return default
    if min_value is not None and value < min_value:
        _ENV_FALLBACKS.append(f"{key}={raw}")
        return default
    return value


def _redis_url_for_db(db: int) -> str:
    """构造指向指定 Redis db 的连接 URL（Celery broker / backend 用）。

    复用 REDIS_HOST / REDIS_PORT / REDIS_PASSWORD（与 Config.REDIS_URL 同源），
    仅替换 db 编号——Celery 的 broker 与 result backend 需用独立 db，避免与
    应用缓存键混杂。

    不能直接用 Config.REDIS_URL：它是 property，类体定义阶段无法访问。

    Args:
        db: 目标 db 编号。

    Returns:
        redis:// URL 字符串。
    """
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _assert_ldap_config(config_cls) -> None:
    """LDAP 显式开启但缺关键配置时 fail-fast（T3）。

    仅在**显式开启**（LDAP_ENABLED=true）却缺 LDAP_SERVER / LDAP_BASE_DN 时报错。
    否则会退化成「所有人都登不上」的静默故障，而且要等到第一个用户尝试登录才暴露。
    关闭状态（默认）不做任何校验 —— 存量部署升级后行为完全不变。

    同时校验 T3.5 的 ``LDAP_GROUP_ROLE_MAP`` 可解析：一份写错的映射表若拖到登录时
    才报错，表现是「部分账号登不上」，且错误只留在日志里 —— 属于必须在启动期挡住的
    配置错误。

    抽成纯函数（不碰 app、不建目录），便于单测直接覆盖三种组合，无需构造假 app。

    Raises:
        RuntimeError: 开启但配置不全，或映射表无法解析。
    """
    if not getattr(config_cls, "LDAP_ENABLED", False):
        return

    if not (getattr(config_cls, "LDAP_SERVER", "") and getattr(config_cls, "LDAP_BASE_DN", "")):
        raise RuntimeError(
            "LDAP_ENABLED=true 但 LDAP_SERVER / LDAP_BASE_DN 未配置；请补全后重启"
            "（如需临时停用外部认证，设 LDAP_ENABLED=false）"
        )

    raw_map = getattr(config_cls, "LDAP_GROUP_ROLE_MAP", "") or ""
    if raw_map:
        from app.services.ldap_role_mapper import (
            GroupRoleMapError,
            parse_group_role_map,
        )

        try:
            parse_group_role_map(raw_map)
        except GroupRoleMapError as exc:
            raise RuntimeError(f"LDAP_GROUP_ROLE_MAP 无法解析：{exc}") from exc


def _generate_dev_key(key_name: str) -> str:
    """为开发环境生成随机密钥并打印警告"""
    key = secrets.token_urlsafe(32)
    warnings.warn(
        f"{key_name} 未设置，已自动生成随机密钥（仅适用于开发环境）",
        stacklevel=3,
    )
    return key


class Config:
    """基础配置类

    包含所有环境通用的配置项和默认值。
    子类可以覆盖这些配置以适应特定环境。
    """

    SECRET_KEY = os.getenv("SECRET_KEY")
    VERSION = "1.0.0"

    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Shanghai")

    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = _env_num("FLASK_PORT", 5000)
    DEBUG = False
    TESTING = False

    NETMIKO_SESSION_LOG = False

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = _env_num("MYSQL_PORT", 3306)
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ip_management")

    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # openai/anthropic/custom
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
    AI_TIMEOUT = _env_num("AI_TIMEOUT", 30, min_value=1)
    AI_MAX_TOKENS = _env_num("AI_MAX_TOKENS", 1024, min_value=1)
    AI_TEMPERATURE = _env_num("AI_TEMPERATURE", 0.2, min_value=0, cast=float)

    _AI_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "app", "services", "ai", "skills")
    AI_BUILTIN_SKILLS_DIR = os.path.join(_AI_BASE, "builtin")
    AI_CUSTOM_SKILLS_DIR = os.environ.get(
        "AI_CUSTOM_SKILLS_DIR", os.path.join(_AI_BASE, "custom"))
    AI_AGENTIC_SKILLS_DIR = os.path.join(_AI_BASE, "agentic")

    AI_SKILL_TRIGGER_PREFILTER = os.getenv("AI_SKILL_TRIGGER_PREFILTER", "true").lower() == "true"
    AI_SKILL_RECALL_TOPK = _env_num("AI_SKILL_RECALL_TOPK", 8, min_value=1)
    AI_SKILL_ROUTING_MODE = os.getenv("AI_SKILL_ROUTING_MODE", "domain").lower()

    AI_SKILL_VISIBILITY_FILTER = os.getenv(
        "AI_SKILL_VISIBILITY_FILTER", "false").lower() == "true"

    AI_DOCS_ROOT = os.environ.get(
        "AI_DOCS_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs"))

    AI_STREAM_TIMEOUT = _env_num("AI_STREAM_TIMEOUT", 120, min_value=1)
    MAX_STREAM_CONNECTIONS = _env_num("MAX_STREAM_CONNECTIONS", 100, min_value=1)

    AI_CIRCUIT_FAILURE_THRESHOLD = _env_num("AI_CIRCUIT_FAILURE_THRESHOLD", 5, min_value=1)
    AI_CIRCUIT_COOLDOWN_SECONDS = _env_num("AI_CIRCUIT_COOLDOWN_SECONDS", 30, min_value=1)

    AI_ASYNC_ENABLED = os.getenv("AI_ASYNC_ENABLED", "1") == "1"

    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or _redis_url_for_db(1)
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or _redis_url_for_db(2)
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_TRACK_STARTED = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # 长任务：一次只取一个，避免饿死
    CELERY_TASK_ACKS_LATE = True  # 崩溃后重投；remedial task 单独覆盖为 False
    CELERY_TASK_REJECT_ON_WORKER_LOST = True
    CELERY_TASK_DEFAULT_QUEUE = "ai"
    CELERY_TASK_TIME_LIMIT = 1800  # 硬上限 30min，杀失控 agentic 循环
    CELERY_TASK_SOFT_TIME_LIMIT = 1500
    CELERY_WORKER_MAX_TASKS_PER_CHILD = _env_num("CELERY_WORKER_MAX_TASKS_PER_CHILD", 100)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_use_lifo": True,  # MySQL 8.4 推荐：LIFO 让热点连接保持活跃，减少连接数
    }

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = _env_num("REDIS_PORT", 6379)
    REDIS_DB = _env_num("REDIS_DB", 0)
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

    LDAP_ENABLED = os.getenv("LDAP_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
    LDAP_SERVER = os.getenv("LDAP_SERVER", "")      # 如 ldaps://dc.corp.local:636
    LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "")    # 如 DC=corp,DC=local
    LDAP_BIND_DN = os.getenv("LDAP_BIND_DN", "")    # 服务账号（检索用户/组用），可留空
    LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD", "")
    LDAP_USER_FILTER = os.getenv("LDAP_USER_FILTER", "(sAMAccountName={username})")
    LDAP_TIMEOUT = _env_num("LDAP_TIMEOUT", 5, min_value=1)  # 连接/检索/Bind 超时（秒）

    LDAP_GROUP_ROLE_MAP = os.getenv("LDAP_GROUP_ROLE_MAP", "")
    LDAP_DEFAULT_ROLE = os.getenv("LDAP_DEFAULT_ROLE", "")
    LDAP_AUTO_PROVISION = os.getenv("LDAP_AUTO_PROVISION", "false").strip().lower() in (
        "1", "true", "yes", "on")
    LDAP_SYNC_ROLES_ON_LOGIN = os.getenv("LDAP_SYNC_ROLES_ON_LOGIN", "true").strip().lower() in (
        "1", "true", "yes", "on")
    LDAP_BYPASS_USERS = os.getenv("LDAP_BYPASS_USERS", "")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 10

    CACHE_TYPE = "redis"
    CACHE_DEFAULT_TIMEOUT = 300  # 5分钟
    CACHE_KEY_PREFIX = "ipm:"

    CACHE_TTL_ROOM = 3600  # 机房数据: 1小时
    CACHE_TTL_CABINET = 1800  # 机柜数据: 30分钟
    CACHE_TTL_DEVICE = 900  # 设备数据: 15分钟
    CACHE_TTL_USER_SESSION = 86400  # 用户会话: 24小时

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1小时
    JWT_REFRESH_TOKEN_EXPIRES = 604800  # 7天
    JWT_REFRESH_TOKEN_REMEMBER_EXPIRES = 2592000  # 30天（登录勾选"记住我"时刷新令牌有效期）
    JWT_ALGORITHM = "HS256"

    BCRYPT_LOG_ROUNDS = 12
    PASSWORD_MIN_LENGTH = 8

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]

    MAX_CONTENT_LENGTH = 12 * 1024 * 1024  # 12 MB

    TRUSTED_PROXIES = os.getenv("TRUSTED_PROXIES", "").split(",") if os.getenv("TRUSTED_PROXIES") else []

    ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "").lower() in ("1", "true", "yes")

    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = None  # 使用Redis
    RATELIMIT_DEFAULT = "1000 per minute"  # 增加默认限制
    RATELIMIT_LOGIN = "10 per minute"      # 增加登录限制
    RATELIMIT_API = "500 per minute"       # 大幅增加API限制
    RATE_LIMIT_MAX_ATTEMPTS = _env_num("RATE_LIMIT_MAX_ATTEMPTS", 5)
    RATE_LIMIT_WINDOW_SECONDS = _env_num("RATE_LIMIT_WINDOW_SECONDS", 300)  # 5分钟

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    SCAN_TIME = os.getenv("SCAN_TIME", "02:00")
    SCAN_ON_STARTUP = os.getenv("SCAN_ON_STARTUP", "false").lower() == "true"
    MAX_SCAN_TIME = _env_num("MAX_SCAN_TIME", 3600)
    SCAN_INTERVAL = _env_num("SCAN_INTERVAL", 86400)  # 24小时
    THREAD_POOL_SIZE = _env_num("THREAD_POOL_SIZE", 50)

    COMMON_PORTS = [
        22,     # SSH
        23,     # Telnet（网络设备）
        80,     # HTTP
        443,    # HTTPS
        445,    # SMB（Windows 文件共享）
        3389,   # RDP（Windows 远程桌面）
        8080,   # HTTP Alt（备用 Web）
        5432,   # PostgreSQL
        3306,   # MySQL
    ]

    MAX_RETRY_COUNT = _env_num("MAX_RETRY_COUNT", 3)
    RETRY_DELAY = _env_num("RETRY_DELAY", 5)

    WX_APPID = os.getenv("WX_APPID", "")
    WX_SECRET = os.getenv("WX_SECRET", "")
    WX_TOKEN = os.getenv("WX_TOKEN", "")
    QR_CODE_EXPIRE_MINUTES = _env_num("QR_CODE_EXPIRE_MINUTES", 5)  # 二维码过期时间（分钟）

    SSH_CERTIFICATE = os.getenv("ssh_Certificate", "")
    SSH_PASSPHRASE = os.getenv("ssh_passphrase", "")

    ALLOWED_DOMAINS = os.getenv("ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",")

    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE = _env_num("SENTRY_TRACES_SAMPLE_RATE", 0.1, cast=float)
    SENTRY_PROFILES_SAMPLE_RATE = _env_num("SENTRY_PROFILES_SAMPLE_RATE", 0.1, cast=float)

    ERROR_STATS_ENABLED = True
    ERROR_STATS_WINDOW = 3600  # 统计窗口：1小时

    ENV = os.getenv("ENV", "production")  # development, testing, production（默认 production，安全优先）


    SWITCH_SECRET_KEY = os.environ.get('SWITCH_SECRET_KEY', '')  # AES-256-GCM密钥(R-07)
    CONFIG_BACKUP_INTERVAL = _env_num("CONFIG_BACKUP_INTERVAL", 86400)  # 配置备份间隔(秒)
    CONFIG_BACKUP_MAX_COUNT = _env_num("CONFIG_BACKUP_MAX_COUNT", 30)  # 每设备最大备份数
    AUDIT_LOG_RETENTION_DAYS = _env_num("AUDIT_LOG_RETENTION_DAYS", 90)  # 审计日志保留天数
    IP_ALLOCATION_LOG_RETENTION_DAYS = _env_num("IP_ALLOCATION_LOG_RETENTION_DAYS", 365)  # IP分配日志保留天数
    VLAN_ID_RANGE = (1, 4094)  # VLAN ID允许范围

    MONITOR_FALLBACK_ROLE = os.getenv("MONITOR_FALLBACK_ROLE", "admin")
    MONITOR_CONSECUTIVE_FAILURES_THRESHOLD = _env_num("MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2)

    MONITOR_INTERVAL_SNMP = _env_num("MONITOR_INTERVAL_SNMP", 60)
    MONITOR_INTERVAL_BMC = _env_num("MONITOR_INTERVAL_BMC", 60)
    MONITOR_THREAD_POOL_SIZE = _env_num("MONITOR_THREAD_POOL_SIZE", 20)
    MONITOR_DEVICE_IDS_WHITELIST = os.getenv("MONITOR_DEVICE_IDS_WHITELIST", "")

    MONITOR_INTERVAL_ZABBIX = _env_num("MONITOR_INTERVAL_ZABBIX", 60)
    MONITOR_ZABBIX_CACHE_TTL = _env_num("MONITOR_ZABBIX_CACHE_TTL", 30)

    MONITOR_ENABLED = os.getenv("MONITOR_ENABLED", "true").lower() == "true"
    MONITOR_TIMEOUT_SECONDS = _env_num("MONITOR_TIMEOUT_SECONDS", 5)

    HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"
    HEARTBEAT_INTERVAL_SECONDS = _env_num("HEARTBEAT_INTERVAL_SECONDS", 20)
    HEARTBEAT_TTL_SECONDS = _env_num("HEARTBEAT_TTL_SECONDS", 90)
    HEARTBEAT_SERVICE_NAME = os.getenv("HEARTBEAT_SERVICE_NAME") or None

    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
    METRICS_ALLOWED_IPS = [
        n.strip() for n in os.getenv("METRICS_ALLOWED_IPS", "").split(",") if n.strip()
    ]

    MONITOR_SUPPRESSION_ENABLED = os.getenv("MONITOR_SUPPRESSION_ENABLED", "true").lower() == "true"
    MONITOR_SUPPRESSION_WINDOW = _env_num("MONITOR_SUPPRESSION_WINDOW", 60)  # 滑动窗口秒
    MONITOR_SUPPRESSION_MAX = _env_num("MONITOR_SUPPRESSION_MAX", 5)  # 窗口内最大告警数
    MONITOR_SUPPRESSION_THROTTLE = _env_num("MONITOR_SUPPRESSION_THROTTLE", 300)  # 抑制后降频通知间隔秒

    MONITOR_INCIDENT_ENABLED = os.getenv("MONITOR_INCIDENT_ENABLED", "true").lower() == "true"
    MONITOR_INCIDENT_WINDOW = _env_num("MONITOR_INCIDENT_WINDOW", 300)  # L1 归并时间窗秒
    MONITOR_INCIDENT_CHANGE_WINDOW = _env_num("MONITOR_INCIDENT_CHANGE_WINDOW", 300)  # L3 变更回溯窗秒

    MONITOR_WORKER_IN_PROCESS = os.getenv("MONITOR_WORKER_IN_PROCESS", "true").lower() == "true"

    MONITOR_OUTBOX_LOCK_ENABLED = os.getenv("MONITOR_OUTBOX_LOCK_ENABLED", "true").lower() == "true"

    TRAPD_ENABLED = os.getenv("TRAPD_ENABLED", "false").lower() == "true"
    TRAPD_LISTEN_ADDRESS = os.getenv("TRAPD_LISTEN_ADDRESS", "0.0.0.0")
    TRAPD_LISTEN_PORT = _env_num("TRAPD_LISTEN_PORT", 10162, min_value=1)
    TRAPD_COMMUNITIES = os.getenv("TRAPD_COMMUNITIES", "public")
    TRAPD_RATE_LIMIT_PER_MINUTE = _env_num("TRAPD_RATE_LIMIT_PER_MINUTE", 120, min_value=1)
    TRAPD_QUEUE_SIZE = _env_num("TRAPD_QUEUE_SIZE", 1000, min_value=1)
    TRAP_CUSTOM_RULES = os.getenv("TRAP_CUSTOM_RULES", "")


    @classmethod
    def init_app(cls, app):
        """初始化应用配置

        Args:
            app: Flask应用实例
        """
        config_instance = cls()
        app.config['SQLALCHEMY_DATABASE_URI'] = config_instance.SQLALCHEMY_DATABASE_URI
        pass

    @classmethod
    def validate(cls):
        """验证配置的有效性

        Raises:
            ValueError: 当配置无效时抛出异常
        """
        if not (0 < cls.FLASK_PORT < 65536):
            raise ValueError(f"无效的Flask端口号: {cls.FLASK_PORT}")

        if not (0 < cls.MYSQL_PORT < 65536):
            raise ValueError(f"无效的MySQL端口号: {cls.MYSQL_PORT}")

        if not (0 < cls.REDIS_PORT < 65536):
            raise ValueError(f"无效的Redis端口号: {cls.REDIS_PORT}")

        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY 环境变量未设置，拒绝启动")
        if not cls.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY 环境变量未设置，拒绝启动")
        if cls.SECRET_KEY == cls.JWT_SECRET_KEY:
            warnings.warn("SECRET_KEY 与 JWT_SECRET_KEY 相同，建议使用独立密钥", stacklevel=2)

        if not cls.MYSQL_DATABASE:
            raise ValueError("必须设置MYSQL_DATABASE")

        if cls.BCRYPT_LOG_ROUNDS < 4 or cls.BCRYPT_LOG_ROUNDS > 31:
            raise ValueError(f"BCRYPT_LOG_ROUNDS必须在4-31之间: {cls.BCRYPT_LOG_ROUNDS}")

        if cls.PASSWORD_MIN_LENGTH < 6:
            raise ValueError(f"PASSWORD_MIN_LENGTH不能小于6: {cls.PASSWORD_MIN_LENGTH}")

        if cls.DEFAULT_PAGE_SIZE < 1 or cls.DEFAULT_PAGE_SIZE > cls.MAX_PAGE_SIZE:
            raise ValueError(f"DEFAULT_PAGE_SIZE必须在1-{cls.MAX_PAGE_SIZE}之间")

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """构建SQLAlchemy数据库URI

        MySQL 8.4 专用参数：
        - charset=utf8mb4: 使用完整 Unicode 字符集
        - collation=utf8mb4_0900_ai_ci: MySQL 8.x 默认排序规则，性能优于 utf8mb4_general_ci
        - mysql_native_password: 兼容旧认证，避免 caching_sha2_password 的 SSL 握手开销

        ⚠️ user/password 必须做 URL 编码：MySQL 密码允许包含 @ : / 等字符，直接拼接
        会让 SQLAlchemy 把其中的 @ 当作 user@host 分隔符。实测踩到：随机生成的密码
        以 @ 结尾（...Tb@），URI 被解析成 host='@localhost'，服务启动即报
        "Can't connect to MySQL server on '@localhost' ([Errno -2] Name or service not known)"。
        """
        from urllib.parse import quote_plus

        return (
            f"mysql+pymysql://{quote_plus(self.MYSQL_USER)}:{quote_plus(self.MYSQL_PASSWORD)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4&collation=utf8mb4_0900_ai_ci"
        )

    @property
    def REDIS_URL(self):
        """构建Redis连接URL。

        s5：优先级必须与 realtime_gateway/config.py::_build_redis_url 完全一致——
        1) 环境变量 REDIS_URL（完整 URL，优先）；
        2) 由 REDIS_HOST / REDIS_PORT / REDIS_PASSWORD / REDIS_DB 组装。
        否则运维只设 REDIS_URL 时，网关连 A Redis 而 Flask 连 B Redis，
        事件链路（Flask 发布 → 网关订阅推送）静默断裂且无任何报错。
        """
        explicit = os.getenv("REDIS_URL")
        if explicit:
            return explicit
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class DevelopmentConfig(Config):
    """开发环境配置

    用于本地开发，启用调试模式，使用本地数据库。
    """

    DEBUG = True
    TESTING = False
    ENV = "development"  # 开发环境显式声明，避免继承基类 production 默认导致 wechat 等按生产处理

    SECRET_KEY = os.getenv("SECRET_KEY") or _generate_dev_key("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or _generate_dev_key("JWT_SECRET_KEY")

    LOG_LEVEL = "DEBUG"

    RATELIMIT_ENABLED = False

    CACHE_DEFAULT_TIMEOUT = 60
    CACHE_TTL_ROOM = 300
    CACHE_TTL_CABINET = 180
    CACHE_TTL_DEVICE = 60

    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1小时

    SENTRY_DSN = ""

    @classmethod
    def init_app(cls, app):
        """初始化开发环境应用配置"""
        Config.init_app(app)

        import logging

        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )


class TestingConfig(Config):
    """测试环境配置

    用于运行测试，使用内存数据库，禁用某些功能。
    """

    DEBUG = False
    TESTING = True
    ENV = "testing"  # 测试环境显式声明

    SECRET_KEY = "test-secret-key-not-for-production"
    JWT_SECRET_KEY = "test-jwt-secret-key-not-for-production"

    MYSQL_DATABASE = "test_ip_management"

    REDIS_DB = 1

    MONITOR_ENABLED = False

    HEARTBEAT_ENABLED = False

    LDAP_ENABLED = False

    MONITOR_OUTBOX_LOCK_ENABLED = False

    MONITOR_SUPPRESSION_ENABLED = False

    TRAPD_ENABLED = False

    WTF_CSRF_ENABLED = False

    RATELIMIT_ENABLED = False

    BCRYPT_LOG_ROUNDS = 4

    JWT_ACCESS_TOKEN_EXPIRES = 300  # 5分钟
    JWT_REFRESH_TOKEN_EXPIRES = 600  # 10分钟

    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 0

    SENTRY_DSN = ""

    @classmethod
    def init_app(cls, app):
        """初始化测试环境应用配置"""
        Config.init_app(app)


class ProductionConfig(Config):
    """生产环境配置

    用于生产部署，启用所有安全特性，使用生产数据库。
    """

    DEBUG = False
    TESTING = False

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    SECRET_KEY: Optional[str] = os.getenv("SECRET_KEY")  # type: ignore
    JWT_SECRET_KEY: Optional[str] = os.getenv("JWT_SECRET_KEY")  # type: ignore

    RATELIMIT_ENABLED = True

    BCRYPT_LOG_ROUNDS = 13

    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = _env_num("SENTRY_TRACES_SAMPLE_RATE", 0.2, cast=float)
    SENTRY_PROFILES_SAMPLE_RATE = _env_num("SENTRY_PROFILES_SAMPLE_RATE", 0.2, cast=float)

    @classmethod
    def init_app(cls, app):
        """初始化生产环境应用配置"""
        Config.init_app(app)

        _assert_ldap_config(cls)

        import logging
        from logging.handlers import RotatingFileHandler

        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)

        file_handler = RotatingFileHandler(
            os.path.join(cls.LOG_DIR, "app.log"),
            maxBytes=cls.LOG_MAX_BYTES,
            backupCount=cls.LOG_BACKUP_COUNT,
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)

    @classmethod
    def validate(cls):
        """验证生产环境配置"""
        super().validate()

        if not cls.SECRET_KEY:
            raise ValueError("生产环境必须设置SECRET_KEY环境变量")
        if not cls.JWT_SECRET_KEY:
            raise ValueError("生产环境必须设置JWT_SECRET_KEY环境变量")
        for _key_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
            _val = getattr(cls, _key_name, "")
            if _val and str(_val).lower().startswith("change-me"):
                raise ValueError(
                    f"生产环境 {_key_name} 仍为 change-me 占位符，拒绝启动（请配置随机密钥）"
                )
        if not getattr(cls, 'SWITCH_SECRET_KEY', ''):
            raise ValueError(
                "生产环境必须设置SWITCH_SECRET_KEY环境变量（设备凭据加密密钥）"
            )

        if not cls.CORS_ORIGINS or cls.CORS_ORIGINS == ["*"]:
            raise ValueError("生产环境必须明确指定CORS_ORIGINS")

        if cls.DEBUG:
            raise ValueError("生产环境禁止启用 DEBUG 模式")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def _assert_deploy_location():
    """部署位置守卫：拒绝在 /root 下启动。

    为什么：deploy/systemd 的单元模板启用 ProtectHome=true——该档位使 /root、
    /home、/run/user 对服务进程**完全不可见**（进程看到的 /root 是空目录）。
    项目一旦放在 /root 下，WorkingDirectory 与 .venv 解释器都访问不到，
    服务启动必然失败（systemd 表现为 203/EXEC 反复重启）。

    本检查覆盖**绕过安装脚本手工部署**的场景：脚本安装的目标固定为 /opt/ipip
    （不受 ProtectHome 影响），而手工把代码放 /root 再启动的，在这里得到明确
    的拒绝与修复提示，而不是一行难懂的 systemd 启动错误。
    """
    root = os.path.dirname(os.path.abspath(__file__))
    if root == "/root" or root.startswith("/root/"):
        raise RuntimeError(
            "拒绝启动：项目部署在 /root 下（%s）。\n"
            "  systemd 加固单元启用 ProtectHome=true 时 /root 对服务进程完全不可见，\n"
            "  继续启动必然失败。修复方式二选一：\n"
            "    1) 部署到 /opt/ipip（scripts/install.sh 的固定安装目标，推荐）\n"
            "    2) 将单元模板的 ProtectHome=true 改为 read-only（保留加固，"
            "/root 变为只读可访问）" % root
        )


def get_config(config_name=None):
    """获取配置对象

    Args:
        config_name: 配置名称，可选值: development, testing, production
                    如果为None，则从环境变量FLASK_ENV读取，默认为production

    Returns:
        Config: 配置类实例

    Raises:
        ValueError: 当配置名称无效时
    """
    _assert_deploy_location()

    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "production")

    config_class = config.get(config_name)
    if config_class is None:
        raise ValueError(f"无效的配置名称: {config_name}，可选值: {list(config.keys())}")

    config_class.validate()

    return config_class
