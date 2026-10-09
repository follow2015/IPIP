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

# 加载环境变量
# WP-4：离线预检脚本（scripts/precheck_prod_config.py）注入 IPIP_PRECHECK_SKIP_DOTENV=1
# 时跳过 .env 加载 —— 预检的判据必须只来自显式给定的 env 文件/环境，
# 否则开发机仓库里的 .env 会静默补齐缺失项，把"该报的缺陷"洗成"通过"。
if not os.getenv("IPIP_PRECHECK_SKIP_DOTENV"):
    load_dotenv()


# 数值型环境变量解析失败/为空的记录（"KEY=原始值"）。
# 启动自检 report_ai_config_mode() 会把它打印出来：这类问题在 config 导入阶段
# 发生，日志系统尚未初始化，只有裸 traceback，排障成本极高。
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
        # 未设置不算异常（用默认值即可），仅空串记账——那是部署脚本的显式错误
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
        # 关闭状态不做任何校验 —— 存量部署升级后行为完全不变
        # （即便误留了一份写错的映射表，也不应影响本地登录部署的启动）
        return

    if not (getattr(config_cls, "LDAP_SERVER", "") and getattr(config_cls, "LDAP_BASE_DN", "")):
        raise RuntimeError(
            "LDAP_ENABLED=true 但 LDAP_SERVER / LDAP_BASE_DN 未配置；请补全后重启"
            "（如需临时停用外部认证，设 LDAP_ENABLED=false）"
        )

    # 传输安全：禁止明文凭据（ldap:// 未开 StartTLS）与写错的 CA 路径。
    # 与 TLS 握手时才发现相比，启动期拦下能让「配错即起不来」，而不是
    # 「服务起来了但所有人都登不上，日志里只有一行 SSL 异常」。
    from app.services.ldap_auth_service import resolve_tls_policy

    policy_error = resolve_tls_policy(
        getattr(config_cls, "LDAP_SERVER", "") or "",
        bool(getattr(config_cls, "LDAP_STARTTLS", False)),
        getattr(config_cls, "LDAP_CA_FILE", "") or "",
        bool(getattr(config_cls, "LDAP_ALLOW_INSECURE_TRANSPORT", False)),
    )
    if policy_error:
        raise RuntimeError(f"LDAP 传输安全策略不满足：{policy_error}")

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

    # 应用基础配置
    SECRET_KEY = os.getenv("SECRET_KEY")
    # 版本号唯一来源（无独立 VERSION 文件）。1.x 主版本位表示**产品阶段**：
    # 1.0.x = IPAM 核心 / 1.2.x = 监控上线 / 1.3.x = AI 上线 / 1.4.x = 国际化（i18n）落地；
    # 阶段内每次对外发布递增补丁位（1.3.1、1.3.2…），破坏性变更不用主版本位表达
    # 而在 CHANGELOG 用 ⚠️ 显式标注 —— 详见 CHANGELOG.md 头部「版本系列/递增规则」。
    # 递增时机：只在「同步 deploy 仓并 push」那一刻（docs/ops/升级发布SOP.md §0.4），
    # 主仓普通提交不动版本号。
    # 运行时出口：GET /api/health 的 data.version（前端侧边栏底部亦展示）。
    VERSION = "1.5.0"

    # 应用时区（语音夜间限呼窗口 / 通知免打扰等本地时间逻辑依赖）。
    # 腾讯云夜间限呼按北京时间执行，worker 跑在 UTC 容器时必须显式配置，
    # 否则窗口会整体错位 8 小时。
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Shanghai")

    # Flask配置
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")  # noqa: S104 -- 服务端部署默认值，可用环境变量覆盖
    FLASK_PORT = _env_num("FLASK_PORT", 5000)
    DEBUG = False
    TESTING = False

    # 通知投递并发数（B-40）：投递循环把"一条通知"提交到有界池，
    # 一台慢 SMTP 只占 1 个池线程，其余线程继续投别的通知。
    # 上限受 DB 连接池约束（pool_size 10 + max_overflow 20 = 30）：
    # 每个池线程最多占 1 条连接，默认 4 留足余量给 web 请求。
    NOTIFICATION_DELIVERY_WORKERS = _env_num(
        "NOTIFICATION_DELIVERY_WORKERS", 4, min_value=1
    )

    # netmiko 会话日志开关（仅调试用）：默认关闭。
    # 开启方式二选一：① 环境变量 NETMIKO_SESSION_LOG=1；② 这里临时设为 True。
    # 开启后 netmiko 向 logs/netmiko_{ip}_{时间戳}.log 写入含登录凭证的完整会话，
    # 调试结束后务必改回 False 并删除 logs/netmiko_*.log。
    # 与 DEBUG 无关，生产环境设 True 不会触发 DEBUG 的启动校验。
    # ⚠️ 当前为定位「2 端口批量失败」临时开启，调试完必须改回 False 并删日志（含明文密码）。
    NETMIKO_SESSION_LOG = False

    # 数据库配置
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = _env_num("MYSQL_PORT", 3306)
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ip_management")

    # 时序存储后端：ClickHouse **连接面**
    # 设计依据 docs/design/监控时序存储-统一设计与施工方案-20261005.md §5.1 / §9。
    # ⚠️ 键名兼容两种写法：CLICKHOUSE_URL（文档口径）优先，否则由 HOST+PORT 拼。
    # ⚠️ CLICKHOUSE_DB 必须显式给：不设时客户端会落到服务端的 `default` 库
    #    （实测该库与业务数据无关，但混库会让"删库/清表"这类操作打错目标）。
    _CH_URL = os.getenv("CLICKHOUSE_URL", "").strip()
    CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    CLICKHOUSE_PORT = _env_num("CLICKHOUSE_PORT", 8123)
    CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "ipip_monitor")
    CLICKHOUSE_HTTP_URL = _CH_URL or f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"

    # 时序存储后端选择器（D3）
    # ------------------------------------------------------------------
    # ⚠️ **默认必须是不启用 CH**：CH 是"选择开启"而非自动开启（用户口径）。
    #    下面的默认值保证在没有任何 CH 配置的机器上，行为与改造前**逐字节相同**。
    #
    # MONITOR_TS_BACKEND：`mysql`（默认）| `clickhouse` | `split`
    #   - 只有 `clickhouse` / `split` 才可能碰 CH；
    # MONITOR_TS_SPLIT_AT：`split` 模式的**时间分界**（ISO 8601，UTC）。
    #   语义：**>= 该时刻**的写入/查询走 CH，**< 该时刻**留在 MySQL 读历史。
    #   边界刻意取 `>=`（新后端接管"分界点及其之后"）：反过来会让分界点那一条
    #   既不在 M 也不在 CH 里 —— 丢一行是最难查的一类 bug。
    #
    # 两个键都是**字符串**（不做类型强转）：非法值必须在 `validate()` 里显式报错，
    # 悄悄回退默认值会让"配错了却看起来在跑"成为可能。
    MONITOR_TS_BACKEND = os.getenv("MONITOR_TS_BACKEND", "mysql").strip().lower()
    MONITOR_TS_SPLIT_AT = os.getenv("MONITOR_TS_SPLIT_AT", "").strip()

    # AI 能力配置（工厂注册模式，默认 OpenAI 兼容协议，公网可用）
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # openai/anthropic/custom
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
    AI_TIMEOUT = _env_num("AI_TIMEOUT", 30, min_value=1)
    AI_MAX_TOKENS = _env_num("AI_MAX_TOKENS", 1024, min_value=1)
    AI_TEMPERATURE = _env_num("AI_TEMPERATURE", 0.2, min_value=0, cast=float)

    # AI 技能目录（Task 2.3）：内置随包发布，自定义受版本控制
    _AI_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "app", "services", "ai", "skills")
    AI_BUILTIN_SKILLS_DIR = os.path.join(_AI_BASE, "builtin")
    AI_CUSTOM_SKILLS_DIR = os.environ.get(
        "AI_CUSTOM_SKILLS_DIR", os.path.join(_AI_BASE, "custom"))
    AI_AGENTIC_SKILLS_DIR = os.path.join(_AI_BASE, "agentic")

    # ── AI 技能路由（Phase A：技能膨胀治理 L0 域隔离）────────────────────
    # 开启后，路由阶段先用技能 triggers 做零成本关键词粗筛，仅把命中集注入 prompt，
    # 避免技能总数膨胀稀释 LLM 注意力。命中为空或过多(>AI_SKILL_RECALL_TOPK)时
    # 回退全量 catalog（等价于现网行为），可一键降级。
    AI_SKILL_TRIGGER_PREFILTER = os.getenv("AI_SKILL_TRIGGER_PREFILTER", "true").lower() == "true"
    AI_SKILL_RECALL_TOPK = _env_num("AI_SKILL_RECALL_TOPK", 8, min_value=1)
    # 技能路由模式（Phase A/B）：控制注入 prompt 的技能集构造方式。
    #   full         = 全量（现网行为，等价于关闭 L0/L1）
    #   domain       = L0 triggers 粗筛（默认，Phase A 已上线）
    #   recall       = L1 rag 语义召回 top-k（技能规模大到单域仍拥挤时启用）
    #   domain+recall= L0 粗筛失败时再用 L1 召回兜底
    # 任意阶段出问题改 "full" 即零代码回滚到现网行为。
    AI_SKILL_ROUTING_MODE = os.getenv("AI_SKILL_ROUTING_MODE", "domain").lower()

    # ── Phase C（L2 入口技能白名单）──────────────────────────────────────
    # 开启后，入口按用户权限裁剪可见技能集：技能所需权限 ⊄ 用户权限 → 不进 prompt。
    # 让 LLM 看不到用户无权执行的技能，减少越权误选；执行前仍由既有的
    # check_skill_permission（fail-closed）兜底，二者语义同源（都基于权限码）。
    # 默认关闭 = 现网行为；裁剪逻辑本身 fail-open（权限信息缺失/解析失败 → 不裁剪）。
    AI_SKILL_VISIBILITY_FILTER = os.getenv(
        "AI_SKILL_VISIBILITY_FILTER", "false").lower() == "true"

    # RAG 入库文档根目录白名单（C2 修复）：docs_dir 必须在此根目录之下
    AI_DOCS_ROOT = os.environ.get(
        "AI_DOCS_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs"))

    # 流式响应配置（Task 5.3）
    AI_STREAM_TIMEOUT = _env_num("AI_STREAM_TIMEOUT", 120, min_value=1)
    MAX_STREAM_CONNECTIONS = _env_num("MAX_STREAM_CONNECTIONS", 100, min_value=1)

    # AI 熔断器配置（M11 修复：从 Config 读取，避免硬编码）
    AI_CIRCUIT_FAILURE_THRESHOLD = _env_num("AI_CIRCUIT_FAILURE_THRESHOLD", 5, min_value=1)
    AI_CIRCUIT_COOLDOWN_SECONDS = _env_num("AI_CIRCUIT_COOLDOWN_SECONDS", 30, min_value=1)

    # AI 长任务是否走 Celery 异步执行（方案 §Phase 3 回退开关）。
    # 设为 False 回退到进程内线程池，用于异步化验证期的紧急回退。
    # H3 修复：统一走 Config，此前三处散落 os.getenv("AI_ASYNC_ENABLED")，
    # 绕开配置体系导致测试无法覆盖、多环境行为不一致。
    AI_ASYNC_ENABLED = os.getenv("AI_ASYNC_ENABLED", "1") == "1"

    # ── Celery 配置（AI 长任务异步化，方案 §Phase 1）────────────────────
    # broker 与 result backend 分离 db（上轮 Q4 修复）：避免 Celery 内部键与
    # 应用缓存键混杂在同一 db，便于排障与按 db 做容量/清理策略。
    # Redis db 分配：
    #   db 0/6: 应用缓存（session / rate limiting / task_state / SSE ticket）
    #   db 1:   Celery broker（队列与内部键）
    #   db 2:   Celery result backend（任务结果）
    # 默认值复用 REDIS_HOST/PORT/PASSWORD（与 REDIS_URL 同源），可整体覆盖。
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or _redis_url_for_db(1)
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or _redis_url_for_db(2)
    # 序列化：仅 JSON。禁止传 SQLAlchemy 对象 / set / datetime（方案 Q1 约束）。
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
    # ── O2：显式声明，别让它们停留在"依赖默认值"的隐式状态 ──────────────
    # Redis broker 的可见性超时：任务被取走后，超过这个时间仍未见 ack，
    # broker 就认为 worker 已死并把消息**重新投递**给别的 worker。
    # 它必须 > task_time_limit，否则一个跑满 30min 的合法任务会在执行期间
    # 被判定超时而重投 ⇒ 同一任务跑两遍（对 remedial / 语音这类外部调用即资损）。
    # 当前 Redis 默认 1h 恰好大于 1800，"碰巧是对的"——一旦有人把
    # time_limit 调到 3600 以上，或换 broker，这个约束就会静默失效。
    # 故显式写死，并由 tests/test_celery_app.py 断言二者的大小关系。
    #
    # ⚠️ 位置必须是 broker_transport_options，不能写成 CELERY_BROKER_VISIBILITY_TIMEOUT：
    # Celery 5.6.3 **没有**这个顶层设置项（已实测 celery.app.defaults 无该键），
    # 写了也不会报错，只是被静默丢弃 —— 典型的「假配置」，比不写更糟。
    # Redis 传输层只从 transport options 里读 visibility_timeout。
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "visibility_timeout": _env_num("CELERY_BROKER_VISIBILITY_TIMEOUT", 3600),
    }
    # 任务结果保留 24h：够排障回溯，又不会让 result backend 无界增长。
    CELERY_RESULT_EXPIRES = _env_num("CELERY_RESULT_EXPIRES", 86400)
    # 子进程回收：LLM 任务上下文大，定期回收防内存泄漏累积
    CELERY_WORKER_MAX_TASKS_PER_CHILD = _env_num("CELERY_WORKER_MAX_TASKS_PER_CHILD", 100)

    # SQLAlchemy配置
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_use_lifo": True,  # MySQL 8.4 推荐：LIFO 让热点连接保持活跃，减少连接数
    }

    # Redis配置
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = _env_num("REDIS_PORT", 6379)
    REDIS_DB = _env_num("REDIS_DB", 0)
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

    # ── 企业身份集成（LDAP/AD，只读透传 Bind）────────────────────────────
    # 铁律：只用「用户登录时输入的密码」原样去域控 Bind 校验，**不做密码同步、
    # 不落库任何明文**；本地账号（auth_source=local）完全不受影响。
    # LDAP_ENABLED 默认 false —— 存量部署升级后行为不变，显式开启才启用外部认证。
    LDAP_ENABLED = os.getenv("LDAP_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
    LDAP_SERVER = os.getenv("LDAP_SERVER", "")      # 如 ldaps://dc.corp.local:636
    # StartTLS：仅在 LDAP_SERVER 为 ldap:// 时需要。开启后在 bind() **之前**协商
    # 升级为 TLS。二者都不满足时拒绝启动（明文传域控口令，见 resolve_tls_policy）。
    LDAP_STARTTLS = os.getenv("LDAP_STARTTLS", "false").strip().lower() in (
        "1", "true", "yes", "on"
    )
    # 企业 CA 证书（PEM）。留空 = 用系统信任库。ldap3 的 Tls 默认 CERT_NONE，
    # 本服务显式改用 CERT_REQUIRED；但因 ldap3 2.9.1 强制关闭主机名校验，
    # 信任锚为公共 CA 时仍可被持任意受信证书者 MITM —— 企业场景建议指向自家 CA。
    LDAP_CA_FILE = os.getenv("LDAP_CA_FILE", "")
    # 逃生舱：允许明文传输（仅限「尚未配 TLS 的试验目录」联调用）。生产必须 false。
    LDAP_ALLOW_INSECURE_TRANSPORT = os.getenv(
        "LDAP_ALLOW_INSECURE_TRANSPORT", "false"
    ).strip().lower() in ("1", "true", "yes", "on")
    LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "")    # 如 DC=corp,DC=local
    LDAP_BIND_DN = os.getenv("LDAP_BIND_DN", "")    # 服务账号（检索用户/组用），可留空
    LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD", "")
    # 用户检索过滤器，{username} 为占位符：AD 用 sAMAccountName，OpenLDAP 常用 uid。
    LDAP_USER_FILTER = os.getenv("LDAP_USER_FILTER", "(sAMAccountName={username})")
    LDAP_TIMEOUT = _env_num("LDAP_TIMEOUT", 5, min_value=1)  # 连接/检索/Bind 超时（秒）

    # ── 企业身份集成：组→角色映射与自动建号（T3.5）──────────────────────
    # 组→角色映射。留空 = 角色仍由管理员在本地维护（仅认证走 LDAP），这是默认行为：
    # 开启 LDAP 却忘了配映射，不应该把存量账号的角色洗成空集。
    # 非空时角色即由目录托管（每次登录按 memberOf 重算）。
    # 支持 JSON：{"IPIP-Ops": "operator"} 或分隔串：IPIP-Ops=>operator;Admins=>admin
    LDAP_GROUP_ROLE_MAP = os.getenv("LDAP_GROUP_ROLE_MAP", "")
    # 目录中没有任何组命中时的兜底角色；留空 = 判为「未授权」并拒绝登录（fail-close）。
    LDAP_DEFAULT_ROLE = os.getenv("LDAP_DEFAULT_ROLE", "")
    # 首次登录自动建号。默认关闭 —— 建号会写库，必须由运维显式开启。
    LDAP_AUTO_PROVISION = os.getenv("LDAP_AUTO_PROVISION", "false").strip().lower() in (
        "1", "true", "yes", "on")
    # 每次登录按目录组重算角色（仅在 LDAP_GROUP_ROLE_MAP 非空时生效）。
    LDAP_SYNC_ROLES_ON_LOGIN = os.getenv("LDAP_SYNC_ROLES_ON_LOGIN", "true").strip().lower() in (
        "1", "true", "yes", "on")
    # 应急管理员通道（T3.6）：逗号分隔的**本地**账号白名单，恒走本地口令、绕过 LDAP。
    # 用途：域控故障或被防火墙隔断时仍能登录抢修。每次使用都会写审计（auth.ldap_bypass）。
    # 留空 = 无应急通道（默认）。注意：这些账号应保持 auth_source=local。
    LDAP_BYPASS_USERS = os.getenv("LDAP_BYPASS_USERS", "")

    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 10

    # 缓存配置
    CACHE_TYPE = "redis"
    CACHE_DEFAULT_TIMEOUT = 300  # 5分钟
    # [DEPRECATED] 本值**不被存储层消费**，改它不会生效：
    # RedisCacheStorage._make_key 读的是**环境变量** CACHE_KEY_PREFIX（默认 "ipip:"），
    # 从不读本类属性；realtime_gateway/auth.py 亦刻意镜像"读 env"这条规则。
    # 刻意在值上保持与事实不同（"ipm:" vs 实际 "ipip:"）—— 一旦改成相同值，
    # 就会制造"改这里能生效"的错觉，比现状更隐蔽。
    # 契约见 tests/test_p0_gateway_revocation_key_contract.py
    #   ::test_flask_storage_reads_env_not_config_class_attr
    CACHE_KEY_PREFIX = "ipm:"

    # 缓存TTL配置（秒）
    CACHE_TTL_ROOM = 3600  # 机房数据: 1小时
    CACHE_TTL_CABINET = 1800  # 机柜数据: 30分钟
    CACHE_TTL_DEVICE = 900  # 设备数据: 15分钟
    CACHE_TTL_USER_SESSION = 86400  # 用户会话: 24小时

    # JWT配置
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1小时
    JWT_REFRESH_TOKEN_EXPIRES = 604800  # 7天
    JWT_REFRESH_TOKEN_REMEMBER_EXPIRES = 2592000  # 30天（登录勾选"记住我"时刷新令牌有效期）
    JWT_ALGORITHM = "HS256"

    # 安全配置
    BCRYPT_LOG_ROUNDS = 12
    PASSWORD_MIN_LENGTH = 8

    # CORS配置
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]

    # HTTP 请求体上限（Flask 层 413 前置拦截，防止超大请求体读入内存打爆 worker）
    # 业务上限：批量导入单文件 10MB（import_export_service.MAX_IMPORT_FILE_BYTES），
    # 此处留 multipart 编码开销余量，略大于业务上限。
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024  # 12 MB

    # 可信代理配置（限流模块用于从 X-Forwarded-For 获取真实IP）
    # 仅当请求来自此列表中的代理IP时才信任 X-Forwarded-For 头
    # 生产环境应设置为实际的反向代理IP（如 ["10.0.0.1", "172.16.0.1"]）
    TRUSTED_PROXIES = os.getenv("TRUSTED_PROXIES", "").split(",") if os.getenv("TRUSTED_PROXIES") else []

    # HTTPS 强制（opt-in，默认关闭）：登录密码为明文 JSON 传输，安全性依赖 TLS。
    # 部署在 TLS 反代之后时设 ENFORCE_HTTPS=true，非 HTTPS 请求将被 400 拒绝
    # （/api/health 探活豁免）；X-Forwarded-Proto 仅采信来自 TRUSTED_PROXIES 的请求。
    ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "").lower() in ("1", "true", "yes")

    # 请求频率限制配置
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = None  # 使用Redis
    RATELIMIT_DEFAULT = "1000 per minute"  # 增加默认限制
    RATELIMIT_LOGIN = "10 per minute"      # 增加登录限制
    RATELIMIT_API = "500 per minute"       # 大幅增加API限制
    RATE_LIMIT_MAX_ATTEMPTS = _env_num("RATE_LIMIT_MAX_ATTEMPTS", 5)
    RATE_LIMIT_WINDOW_SECONDS = _env_num("RATE_LIMIT_WINDOW_SECONDS", 300)  # 5分钟

    # 分页配置
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # 网络扫描配置
    SCAN_TIME = os.getenv("SCAN_TIME", "02:00")
    SCAN_ON_STARTUP = os.getenv("SCAN_ON_STARTUP", "false").lower() == "true"
    MAX_SCAN_TIME = _env_num("MAX_SCAN_TIME", 3600)
    SCAN_INTERVAL = _env_num("SCAN_INTERVAL", 86400)  # 24小时
    THREAD_POOL_SIZE = _env_num("THREAD_POOL_SIZE", 50)

    # 常用端口扫描列表（精简：去掉 DNS/MSRPC/NetBIOS/IMAPS/POP3S/PPTP/PG/MySQL/8443/8888）
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

    # 重试配置
    MAX_RETRY_COUNT = _env_num("MAX_RETRY_COUNT", 3)
    RETRY_DELAY = _env_num("RETRY_DELAY", 5)

    # 微信小程序配置
    WX_APPID = os.getenv("WX_APPID", "")
    WX_SECRET = os.getenv("WX_SECRET", "")
    WX_TOKEN = os.getenv("WX_TOKEN", "")
    QR_CODE_EXPIRE_MINUTES = _env_num("QR_CODE_EXPIRE_MINUTES", 5)  # 二维码过期时间（分钟）

    # SSH配置
    SSH_CERTIFICATE = os.getenv("ssh_Certificate", "")
    SSH_PASSPHRASE = os.getenv("ssh_passphrase", "")

    # 允许的域名
    ALLOWED_DOMAINS = os.getenv("ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",")

    # Sentry 配置
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE = _env_num("SENTRY_TRACES_SAMPLE_RATE", 0.1, cast=float)
    SENTRY_PROFILES_SAMPLE_RATE = _env_num("SENTRY_PROFILES_SAMPLE_RATE", 0.1, cast=float)

    # 错误统计配置
    ERROR_STATS_ENABLED = True
    ERROR_STATS_WINDOW = 3600  # 统计窗口：1小时

    # 环境配置
    ENV = os.getenv("ENV", "production")  # development, testing, production（默认 production，安全优先）

    # 邮件配置已迁移到数据库 mail_settings 表，通过前端"邮件配置"页面管理
    # 不再从 .env 文件读取 MAIL_* 配置项

    # Phase 1+3 新增配置项
    SWITCH_SECRET_KEY = os.environ.get('SWITCH_SECRET_KEY', '')  # AES-256-GCM密钥(R-07)
    CONFIG_BACKUP_INTERVAL = _env_num("CONFIG_BACKUP_INTERVAL", 86400)  # 配置备份间隔(秒)
    CONFIG_BACKUP_MAX_COUNT = _env_num("CONFIG_BACKUP_MAX_COUNT", 30)  # 每设备最大备份数
    AUDIT_LOG_RETENTION_DAYS = _env_num("AUDIT_LOG_RETENTION_DAYS", 90)  # 审计日志保留天数
    IP_ALLOCATION_LOG_RETENTION_DAYS = _env_num("IP_ALLOCATION_LOG_RETENTION_DAYS", 365)  # IP分配日志保留天数
    VLAN_ID_RANGE = (1, 4094)  # VLAN ID允许范围

    # 设备健康监控配置（运行时通过 current_app.config 读取，避免模块级 get_config()）
    MONITOR_FALLBACK_ROLE = os.getenv("MONITOR_FALLBACK_ROLE", "admin")
    MONITOR_CONSECUTIVE_FAILURES_THRESHOLD = _env_num("MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2)

    # 监控后台轮询线程配置（Task 6）
    MONITOR_INTERVAL_SNMP = _env_num("MONITOR_INTERVAL_SNMP", 60)
    MONITOR_INTERVAL_BMC = _env_num("MONITOR_INTERVAL_BMC", 60)
    # 语义是「单个轮询循环的并发上限」，不是「进程总并发」——全部 loop 共用
    # 一个进程级共享池（见 monitor_worker._acquire_shared_executor），总并发
    # 还受下面的 MONITOR_MAX_DB_CONCURRENCY 封顶。
    MONITOR_THREAD_POOL_SIZE = _env_num("MONITOR_THREAD_POOL_SIZE", 20)
    # 监控线程能同时占用的 DB 连接上限。DB 池是 pool_size 10 + max_overflow 20 = 30，
    # 默认 24 是留 6 条给 web 请求 / Celery：监控把 30 条占满时，用户点页面会卡在
    # 「等连接」而不是「等探测」，那是更难诊断的一类故障。
    MONITOR_MAX_DB_CONCURRENCY = _env_num("MONITOR_MAX_DB_CONCURRENCY", 24)
    MONITOR_DEVICE_IDS_WHITELIST = os.getenv("MONITOR_DEVICE_IDS_WHITELIST", "")

    # Zabbix 集中式拉取监控配置（Route A：协议注册表 worker_loop="zabbix"）
    # 间隔默认回退由 protocol_registry.DEFAULT_LOOP_INTERVALS 提供，此处为环境变量覆盖入口；
    # MONITOR_ZABBIX_CACHE_TTL 为 ZabbixAdapter 批量 host 索引缓存 TTL（应 < 轮询间隔，
    # 避免缓存陈旧导致 host 永久未找到，见 v4-final §4）。
    MONITOR_INTERVAL_ZABBIX = _env_num("MONITOR_INTERVAL_ZABBIX", 60)
    MONITOR_ZABBIX_CACHE_TTL = _env_num("MONITOR_ZABBIX_CACHE_TTL", 30)

    # 监控总开关 + 探测超时（Task 10）
    MONITOR_ENABLED = os.getenv("MONITOR_ENABLED", "true").lower() == "true"
    MONITOR_TIMEOUT_SECONDS = _env_num("MONITOR_TIMEOUT_SECONDS", 5)

    # ── 进程心跳（P0-T2.2 自监控闭环）──────────────────────────
    # 每个常驻进程周期性写 ipip:heartbeat:<service>，由 watchdog 判活。
    HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"
    # 写入周期（秒）。30s 以下保证故障在半分钟内被发现。
    HEARTBEAT_INTERVAL_SECONDS = _env_num("HEARTBEAT_INTERVAL_SECONDS", 20)
    # key 有效期（秒）。必须 ≥ 3×周期，否则一次网络抖动就误判进程死亡；
    # app.services.monitoring.heartbeat.resolve_ttl() 会兜底纠正偏小的值。
    HEARTBEAT_TTL_SECONDS = _env_num("HEARTBEAT_TTL_SECONDS", 90)
    # 本进程对外声明的服务名（web/monitor/gateway/celery-ai/celery-voice）。
    # 留空时各进程按自身身份兜底；多实例部署需显式区分时在此指定。
    HEARTBEAT_SERVICE_NAME = os.getenv("HEARTBEAT_SERVICE_NAME") or None

    # ── Prometheus 抓取端点（/metrics）──────────────────────────────
    # 总开关：默认开启。公网部署且不想暴露时设 METRICS_ENABLED=false（返 404）。
    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    # 抓取口令：为空 = 免鉴权（默认，适合内网直抓）。
    # 设置后必须带 ?token=<值> 或 Authorization: Bearer <值> 才放行。
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
    # 来源 IP 白名单（逗号分隔的 IP 或 CIDR，如 "10.0.0.5,192.168.1.0/24"）。
    # 默认空 = 不限制来源（内网直抓默认）。公网部署务必配置，与 METRICS_TOKEN
    # 叠加生效：既校验口令，又仅放行白名单来源，避免暴露调用量/技能清单/模型名。
    METRICS_ALLOWED_IPS = [
        n.strip() for n in os.getenv("METRICS_ALLOWED_IPS", "").split(",") if n.strip()
    ]

    # G13: 告警风暴抑制（同 dedup_key 滑动窗口内限频，避免指标抖动放大）
    MONITOR_SUPPRESSION_ENABLED = os.getenv("MONITOR_SUPPRESSION_ENABLED", "true").lower() == "true"
    MONITOR_SUPPRESSION_WINDOW = _env_num("MONITOR_SUPPRESSION_WINDOW", 60)  # 滑动窗口秒
    MONITOR_SUPPRESSION_MAX = _env_num("MONITOR_SUPPRESSION_MAX", 5)  # 窗口内最大告警数
    MONITOR_SUPPRESSION_THROTTLE = _env_num("MONITOR_SUPPRESSION_THROTTLE", 300)  # 抑制后降频通知间隔秒

    # 事件聚合（Incident）：把散落告警归并为可运营事件
    # 注意：WINDOW 当前为文档建议值，库内是测试数据无法回放校准，
    # 待有真实告警数据后应按实际分布重新确定（见 docs/superpowers/plans 已知限制）。
    MONITOR_INCIDENT_ENABLED = os.getenv("MONITOR_INCIDENT_ENABLED", "true").lower() == "true"
    MONITOR_INCIDENT_WINDOW = _env_num("MONITOR_INCIDENT_WINDOW", 300)  # L1 归并时间窗秒
    MONITOR_INCIDENT_CHANGE_WINDOW = _env_num("MONITOR_INCIDENT_CHANGE_WINDOW", 300)  # L3 变更回溯窗秒
    # 事件自动关闭（停滞清扫）：活跃事件超过 N 小时无新告警即归档关闭（<=0 关闭该规则）。
    # ⚠️ N 必须**严格大于**设备重告警间隔，否则会误关仍在故障中的事件：
    #    清扫判据 = `last_alert_at < now - N`（monitor_incident_repository.close_stale_active），
    #    而 `last_alert_at` 只在有新告警时才刷新 ⇒ 两次重告警之间的静默期若超过 N，
    #    事件会在"故障未恢复"的状态下被关掉。
    #    实测口径：重告警间隔 `MONITOR_REALERT_INTERVAL_MINUTES`（动态配置，非环境变量）
    #    默认 360 分钟 = 6h ⇒ 默认 N=24h 为 **4 倍**余量（静默期最长 6h < 24h）。
    #    ⚠️ 该配置项上限 1440 分钟 = 24h，**正好等于默认 N** ⇒ 若运维把它调到上限，
    #    清扫与重告警同周期赛跑（边界相等，先后顺序决定结果）。调大重告警间隔前
    #    必须先调大 N，两者是耦合的。
    MONITOR_INCIDENT_AUTOCLOSE_HOURS = _env_num("MONITOR_INCIDENT_AUTOCLOSE_HOURS", 24)
    # 清扫最小间隔秒：outbox 发件线程每 5s 轮一转，无闸会白打一次 UPDATE
    MONITOR_INCIDENT_AUTOCLOSE_INTERVAL = _env_num("MONITOR_INCIDENT_AUTOCLOSE_INTERVAL", 600)

    # 是否在本进程内启动监控 worker（默认 True，保持历史「Flask 进程内守护线程」行为）。
    # 当监控被抽离为独立 async 微服务（run_monitor_service.py）运行时，应在 HTTP
    # 应用进程设此值为 false，避免与独立服务双跑。create_app 同时读取同名环境变量，
    # 使独立服务进程无需改动配置类即可禁用 in-Flask worker。
    MONITOR_WORKER_IN_PROCESS = os.getenv("MONITOR_WORKER_IN_PROCESS", "true").lower() == "true"

    # 轮询循环的「最小间隔闸门」（限速器，默认 True）。
    # 背景：`monitor:lock:<loop>` 只保证互斥、**不保证限速** —— 多进程部署
    # （gunicorn 多 worker + celery + 独立采集服务）下每个实例各自按自己的
    # interval 起轮，聚合频率 = interval ÷ 实例数（实测 60 s 被打成 ≈18.9 s）。
    # 开启后同 loop 的全部实例共享一个 interval 配额。
    # 置 false 仅用于现场排障 / 需要无视节奏立刻跑一轮 —— 关掉即回到放大状态。
    MONITOR_RATE_LIMIT_ENABLED = os.getenv(
        "MONITOR_RATE_LIMIT_ENABLED", "true"
    ).lower() == "true"

    # 告警发件箱（outbox）轮询是否加 Redis 进程间互斥锁。
    # 多 gunicorn worker 部署下每个进程各起一个发件线程，不加锁会并发拉到同一批
    # pending 行 → 重复投递 + attempts 竞态（重复投递本身由 notify 的
    # idempotency_key 兜底去重，但 attempts 竞态可能未满上限即被判 failed）。
    # 单进程部署可置 false，省掉每轮一次 Redis 往返。
    MONITOR_OUTBOX_LOCK_ENABLED = os.getenv("MONITOR_OUTBOX_LOCK_ENABLED", "true").lower() == "true"

    # 设备操作锁的部署形态开关 `DEVICE_OP_LOCK_REQUIRE_REDIS`（无 Redis 时 write
    # 模式是否 fail-closed）**刻意不登记在本类里** —— 见
    # `app/services/device_op_lock.py` 的 POLICY_ENV 说明：本类属性是**类定义期**
    # 固化的，一旦登记，`from_object` 会把它拷进 `app.config`，之后改环境变量
    # 就再也影响不到进程（也无从区分"显式声明过"与"压根没配"）。该开关由
    # device_op_lock 在**每次取锁时**读 env / `app.config`，单一真源在那边。

    # ── SNMP Trap 接收（P1-1，独立服务 run_trapd_service.py）──────────
    # 默认关闭：启用需部署 ipip-trapd unit（端口授权见 .env.example 注释）。
    TRAPD_ENABLED = os.getenv("TRAPD_ENABLED", "false").lower() == "true"
    # 监听地址/端口。162 为特权端口（root capability 或 NET_ADMIN）；
    # 无特权时用 10162 并在交换机侧配置 trap 目标端口，或在主机上做端口重定向。
    TRAPD_LISTEN_ADDRESS = os.getenv("TRAPD_LISTEN_ADDRESS", "0.0.0.0")  # noqa: S104 -- 服务端部署默认值，可用环境变量覆盖
    TRAPD_LISTEN_PORT = _env_num("TRAPD_LISTEN_PORT", 10162, min_value=1)
    # 允许接收的 community（逗号分隔）。**无默认值**：SNMPv1/v2c 的 community 就是
    # 唯一凭据，留空或使用知名默认值（public/private）时 trapd 启动即失败（fail-fast），
    # 见 run_trapd_service.TrapdService.__init__。校验发生在 run_trapd_service 收包
    # 循环内（解码后、入队前），不匹配的报文不进处理链。
    TRAPD_COMMUNITIES = os.getenv("TRAPD_COMMUNITIES", "")
    # 源 IP 白名单（逗号分隔，支持单 IP 与 CIDR，如 10.0.0.0/8,192.168.1.5）。
    # 留空 = 不启用源过滤。UDP 源 IP 可伪造，而 resolve_device() 正是用源 IP 反查设备
    # ——把 trap 源限定在管理网段是防「伪造设备 IP 投毒告警」的关键一环。
    # 写法非法（非 IP / 掩码越界）时启动即失败，避免静默失效。
    TRAPD_SOURCE_ALLOWLIST = os.getenv("TRAPD_SOURCE_ALLOWLIST", "")
    # 逃生舱：显式允许弱 community（实验/隔离内网联调）。生产必须留 false。
    TRAPD_ALLOW_WEAK_COMMUNITY = (
        os.getenv("TRAPD_ALLOW_WEAK_COMMUNITY", "false").lower() == "true"
    )
    # 全局限流：每分钟最多处理的 trap 条数（超出拒收并记日志，防 trap 风暴打垮 DB）
    TRAPD_RATE_LIMIT_PER_MINUTE = _env_num("TRAPD_RATE_LIMIT_PER_MINUTE", 120, min_value=1)
    # 有界接收队列：worker 处理不过来时新 trap 被丢弃（UDP 本身不可靠，不阻塞收包循环）
    TRAPD_QUEUE_SIZE = _env_num("TRAPD_QUEUE_SIZE", 1000, min_value=1)
    # ── SNMPv3 Trap（SNMPv3 支持 · 步 4）────────────────────────────
    # 默认**关**：与 MONITOR_TS_BACKEND 同范式 —— 新后端是"选择开启"而不是
    # "自动开启"。关闭时 v3 报文在版本分派处即被丢弃，v1/v2c 路径零影响；
    # 未部署 trapd unit 的存量环境完全感知不到本组配置的存在。
    TRAPD_V3_ENABLED = os.getenv("TRAPD_V3_ENABLED", "false").lower() == "true"
    # 可选的 v3 用户名白名单（逗号分隔）。**默认空 = 不限制** —— 用凭据库里
    # 全部启用中的 v3 凭据。显式指定则只接受这些 username（与 TRAPD_COMMUNITIES
    # 同构：显式优先，不配才回退凭据库）。配了名字但凭据库里没有对应 v3 凭据时，
    # trapd 会**启动时告警**（而不是等到收包时表现为"v3 trap 全被拒"）。
    TRAPD_V3_USERS = os.getenv("TRAPD_V3_USERS", "")
    # 站点自定义规则（JSON 数组：name/match_oid/severity[/title/content/index_varbind]）。
    # 解析失败在 trapd 启动期 fail-fast（见 app/services/monitoring/trap_rule_service.py）。
    TRAP_CUSTOM_RULES = os.getenv("TRAP_CUSTOM_RULES", "")


    @classmethod
    def init_app(cls, app):
        """初始化应用配置

        Args:
            app: Flask应用实例
        """
        # 设置数据库URI（从property获取实际值）
        config_instance = cls()
        app.config['SQLALCHEMY_DATABASE_URI'] = config_instance.SQLALCHEMY_DATABASE_URI
        pass

    @classmethod
    def validate(cls):
        """验证配置的有效性

        Raises:
            ValueError: 当配置无效时抛出异常
        """
        # 验证端口号
        if not (0 < cls.FLASK_PORT < 65536):
            raise ValueError(f"无效的Flask端口号: {cls.FLASK_PORT}")

        if not (0 < cls.MYSQL_PORT < 65536):
            raise ValueError(f"无效的MySQL端口号: {cls.MYSQL_PORT}")

        if not (0 < cls.REDIS_PORT < 65536):
            raise ValueError(f"无效的Redis端口号: {cls.REDIS_PORT}")

        cls._validate_monitor_ts_backend()

    @classmethod
    def _validate_monitor_ts_backend(cls):
        """校验时序后端选择器（D3）。

        **为什么非法值必须报错而不是回退默认**：静默回退会让"配错却在跑"
        成立 —— 运维以为数据进了 CH，实际还在 MySQL，等发现时已经过去很久，
        而且这期间的数据没有 CH 副本（不可逆）。宁可起不来。

        约束：
        - ``MONITOR_TS_BACKEND`` ∈ {mysql, clickhouse, split}；
        - ``split`` **必须**给合法的 ``MONITOR_TS_SPLIT_AT``（缺了就没有分界点，
          等于无法判断该写哪边）；
        - ``MONITOR_TS_SPLIT_AT`` 给了就必须能解析（给错格式同样拒绝）。
        """
        allowed = ("mysql", "clickhouse", "split")
        backend = str(getattr(cls, "MONITOR_TS_BACKEND", "mysql") or "mysql").lower()
        if backend not in allowed:
            raise ValueError(
                f"MONITOR_TS_BACKEND 取值非法：{backend!r}，"
                f"只允许 {'/'.join(allowed)}（留空视为 mysql）"
            )
        raw_split = str(getattr(cls, "MONITOR_TS_SPLIT_AT", "") or "").strip()
        if backend == "split" and not raw_split:
            raise ValueError(
                "MONITOR_TS_BACKEND=split 时必须设置 MONITOR_TS_SPLIT_AT"
                "（ISO 8601，如 2026-10-06T00:00:00），否则无法判断分界点"
            )
        if raw_split:
            from datetime import datetime as _dt

            try:
                _dt.fromisoformat(raw_split.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    f"MONITOR_TS_SPLIT_AT 不是合法 ISO 8601 时间：{raw_split!r}"
                ) from exc

        # 验证必需的配置项
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY 环境变量未设置，拒绝启动")
        if not cls.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY 环境变量未设置，拒绝启动")
        if cls.SECRET_KEY == cls.JWT_SECRET_KEY:
            warnings.warn("SECRET_KEY 与 JWT_SECRET_KEY 相同，建议使用独立密钥", stacklevel=2)

        if not cls.MYSQL_DATABASE:
            raise ValueError("必须设置MYSQL_DATABASE")

        # 验证数值范围
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

    # 开发环境：未设置时自动生成随机密钥（仅用于开发）
    SECRET_KEY = os.getenv("SECRET_KEY") or _generate_dev_key("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or _generate_dev_key("JWT_SECRET_KEY")

    # 开发环境使用更详细的日志
    LOG_LEVEL = "DEBUG"

    # 开发环境禁用请求频率限制
    RATELIMIT_ENABLED = False

    # 开发环境使用较短的缓存时间
    CACHE_DEFAULT_TIMEOUT = 60
    CACHE_TTL_ROOM = 300
    CACHE_TTL_CABINET = 180
    CACHE_TTL_DEVICE = 60

    # 开发环境使用较短的JWT过期时间（方便测试）
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1小时

    # 开发环境禁用 Sentry
    SENTRY_DSN = ""

    @classmethod
    def init_app(cls, app):
        """初始化开发环境应用配置"""
        Config.init_app(app)

        # 开发环境特定的初始化
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

    # 测试环境使用固定密钥
    SECRET_KEY = "test-secret-key-not-for-production"  # noqa: S105 -- TestingConfig 专用固定值，仅测试环境装配
    JWT_SECRET_KEY = "test-jwt-secret-key-not-for-production"  # noqa: S105 -- 同上

    # 测试环境使用内存数据库
    MYSQL_DATABASE = "test_ip_management"

    # 测试环境使用独立的Redis数据库
    REDIS_DB = 1

    # 测试环境不启动后台监控轮询线程（外层已按 config_name != "testing" 拦截，
    # 此处显式关闭作为防御，避免任何路径下测试启动后台线程）
    MONITOR_ENABLED = False

    # 心跳依赖真实 Redis 且会常驻后台线程，测试环境必须关闭（同 MONITOR_ENABLED）
    HEARTBEAT_ENABLED = False

    # 企业身份集成（T3）：测试环境默认关闭，避免用例连真实域控；
    # LDAP 分支的测试用注入的假连接，不依赖此开关。
    LDAP_ENABLED = False

    # 测试为单进程 + SQLite，无需 outbox 进程间互斥；关闭可避免用例连真实 Redis
    MONITOR_OUTBOX_LOCK_ENABLED = False

    # 测试环境禁用告警风暴抑制（G13）：抑制依赖真实 Redis，若启用会误抑制
    # 告警入箱类测试（如 test_monitor_service 的 check_device 场景），使期望的
    # outbox 行为断言失效。风暴抑制的判定逻辑由专门单测覆盖，此处关闭以保证
    # 入箱/投递类测试的确定性。与 MONITOR_ENABLED=False 同属测试隔离策略。
    MONITOR_SUPPRESSION_ENABLED = False

    # SNMP Trap 接收：测试环境不启动 UDP 监听服务（由专门用例自管端口）
    TRAPD_ENABLED = False
    # v3 同理默认关：开启需要真的 USM 凭据与解码链路，测试环境不该意外进入
    TRAPD_V3_ENABLED = False

    # 测试环境禁用CSRF保护
    WTF_CSRF_ENABLED = False

    # 测试环境禁用请求频率限制
    RATELIMIT_ENABLED = False

    # 测试环境使用更快的密码哈希（加快测试速度）
    BCRYPT_LOG_ROUNDS = 4

    # 测试环境使用较短的JWT过期时间
    JWT_ACCESS_TOKEN_EXPIRES = 300  # 5分钟
    JWT_REFRESH_TOKEN_EXPIRES = 600  # 10分钟

    # 测试环境禁用缓存
    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 0

    # 测试环境禁用 Sentry
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

    # 生产环境使用INFO级别日志
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 生产环境必须从环境变量读取敏感配置
    SECRET_KEY: Optional[str] = os.getenv("SECRET_KEY")  # type: ignore
    JWT_SECRET_KEY: Optional[str] = os.getenv("JWT_SECRET_KEY")  # type: ignore

    # 生产环境启用请求频率限制
    RATELIMIT_ENABLED = True

    # 生产环境使用更强的密码哈希
    BCRYPT_LOG_ROUNDS = 13

    # 生产环境使用HTTPS
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # 生产环境限制CORS源
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

    # 生产环境启用 Sentry（必须配置）
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = _env_num("SENTRY_TRACES_SAMPLE_RATE", 0.2, cast=float)
    SENTRY_PROFILES_SAMPLE_RATE = _env_num("SENTRY_PROFILES_SAMPLE_RATE", 0.2, cast=float)

    @classmethod
    def init_app(cls, app):
        """初始化生产环境应用配置"""
        Config.init_app(app)

        # LDAP（T3）：显式开启但缺关键配置时 fail-fast，见 _assert_ldap_config。
        _assert_ldap_config(cls)

        # 生产环境特定的初始化
        import logging
        from logging.handlers import RotatingFileHandler

        # 确保日志目录存在
        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)

        # 配置文件日志处理器
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

    # ── WP-4：校验逻辑抽为独立检查方法 ──────────────────────────────────
    # validate() 保持"逐条检查、命中即抛"的既有行为（消息与顺序零变化）；
    # collect_violations() 供离线预检脚本用：一次收集全部缺陷而不是中止在第一处。
    # 两者消费同一份检查注册表，判据单一真源，不会各自漂移。
    # ID 是对外稳定契约（预检测试按集合严格相等断言），显式登记、不靠方法名推导。
    _PRODUCTION_CHECKS = (
        ("REQUIRED_SECRETS", "_check_required_secrets"),
        ("CORS_ORIGINS", "_check_cors_origins"),
        ("DEBUG_DISABLED", "_check_debug_disabled"),
        ("METRICS_EXPOSURE", "_check_metrics_exposure"),
        ("SECRET_KEY_DUPLICATE", "_check_secret_key_duplication"),
        ("LDAP_CA_MISSING", "_check_ldap_ca"),
    )

    @classmethod
    def _check_required_secrets(cls):
        # 生产环境额外验证
        if not cls.SECRET_KEY:
            raise ValueError("生产环境必须设置SECRET_KEY环境变量")
        if not cls.JWT_SECRET_KEY:
            raise ValueError("生产环境必须设置JWT_SECRET_KEY环境变量")
        # 占位符密钥等于弱默认密钥（会话/JWT 可被伪造），bootstrap.sh 会自动生成
        # 随机值，正常不会触发；绕过安装器手工部署时在此拒绝启动。
        for _key_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
            _val = getattr(cls, _key_name, "")
            if _val and str(_val).lower().startswith("change-me"):
                raise ValueError(
                    f"生产环境 {_key_name} 仍为 change-me 占位符，拒绝启动（请配置随机密钥）"
                )
        # SEC-2: 设备凭据加密密钥必须非空
        if not getattr(cls, 'SWITCH_SECRET_KEY', ''):
            raise ValueError(
                "生产环境必须设置SWITCH_SECRET_KEY环境变量（设备凭据加密密钥）"
            )

    @classmethod
    def _check_cors_origins(cls):
        if not cls.CORS_ORIGINS or cls.CORS_ORIGINS == ["*"]:
            raise ValueError("生产环境必须明确指定CORS_ORIGINS")

    @classmethod
    def _check_debug_disabled(cls):
        # 生产环境禁止 DEBUG=True
        if cls.DEBUG:
            raise ValueError("生产环境禁止启用 DEBUG 模式")

    @classmethod
    def _check_metrics_exposure(cls):
        # ① `/metrics` 暴露面：开关打开却无 token ⇒ 任何能连上端口的人都能抓走
        #    设备数/告警数等运行态数据。此前只靠文档"务必配置"，属可误配。
        #    规则刻意是"**至少一项**"而不是"必须给 token"：`METRICS_ALLOWED_IPS`
        #    本身就能把抓取面收到指定来源（见 .env.example 的三项说明），
        #    强迫所有内网直抓部署都造口令属于过度收紧。
        if getattr(cls, "METRICS_ENABLED", False):
            _has_token = bool(getattr(cls, "METRICS_TOKEN", ""))
            _has_allowlist = bool(getattr(cls, "METRICS_ALLOWED_IPS", None))
            if not (_has_token or _has_allowlist):
                raise ValueError(
                    "生产环境 /metrics 默认开启且免鉴权 ⇒ 必须至少限制一项："
                    "METRICS_TOKEN（抓取须带口令）或 METRICS_ALLOWED_IPS（来源白名单）；"
                    "确实不需要该端点请设 METRICS_ENABLED=false（路由直接 404）"
                )

    @classmethod
    def _check_secret_key_duplication(cls):
        # ② 会话密钥与 JWT 密钥相同：基类只 warn（开发/测试可接受），
        #    生产升级为**拒绝启动** —— 一把密钥同时签发会话与 JWT，泄漏面翻倍。
        if cls.SECRET_KEY and cls.SECRET_KEY == cls.JWT_SECRET_KEY:
            raise ValueError(
                "生产环境 SECRET_KEY 与 JWT_SECRET_KEY 不得相同："
                "同一把密钥既用于会话签名又用于 JWT 签发，任一泄漏即两者同时失守"
                "（请分别用 `openssl rand -hex 32` 生成）"
            )

    @classmethod
    def _check_ldap_ca(cls):
        # ③ LDAP 启用时必须**显式**指定 CA：ldap3 2.9.1 强制关闭主机名校验，
        #    信任锚若为公共 CA，持**任意**受信证书者即可 MITM（见 .env.example 的
        #    同段说明）。收窄信任锚是这种情况下唯一有效的补偿措施，故不能靠默认值。
        if getattr(cls, "LDAP_ENABLED", False) and not getattr(cls, "LDAP_CA_FILE", ""):
            raise ValueError(
                "生产环境启用 LDAP 时必须设置 LDAP_CA_FILE（企业 CA 证书 PEM 路径）："
                "ldap3 强制关闭主机名校验，把信任锚收窄到自家 CA 才是有效补偿。"
                "确需依赖系统信任库的部署请**显式**指向系统 CA bundle"
                "（如 /etc/ssl/certs/ca-certificates.crt），而不是留空"
            )

    @classmethod
    def collect_violations(cls):
        """收集全部生产配置缺陷（不中止在第一处）——离线预检专用。

        Returns:
            list[tuple[str, str]]: (检查 ID, 错误消息) 列表；空列表 = 通过。
            检查 ID 是稳定契约，预检测试按集合严格相等断言（防漏报/多报双向漂移）。
        """
        violations = []
        try:
            super().validate()
        except ValueError as exc:
            violations.append(("BASE_CONFIG", str(exc)))
        for _id, _name in cls._PRODUCTION_CHECKS:
            try:
                getattr(cls, _name)()
            except ValueError as exc:
                violations.append((_id, str(exc)))
        return violations

    @classmethod
    def validate(cls):
        """验证生产环境配置"""
        super().validate()
        for _id, _name in cls._PRODUCTION_CHECKS:
            getattr(cls, _name)()


# 配置字典，用于根据环境名称获取配置类
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
            "    1) 部署到 /opt/ipip（scripts/installer/bootstrap.sh 的固定安装目标，推荐）\n"
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

    # 验证配置
    config_class.validate()

    return config_class
