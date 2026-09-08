# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_mysql_session_utc(dbapi_conn, connection_record):
    """MySQL 会话时区固定为 UTC。

    背景：库内时间口径已统一为 UTC（应用层写入走
    `app.utils.time_utils.now_utc_naive()`），但库侧仍有三处时间源走
    MySQL 会话时区（默认 SYSTEM，即服务器本地时区）：
    - 列默认值 `DEFAULT CURRENT_TIMESTAMP`；
    - `ON UPDATE CURRENT_TIMESTAMP`；
    - ORM 的 `server_default/onupdate=func.now()`（SQL 内渲染 NOW()）。

    若不固定，这些值会随 MySQL 服务器时区漂移（中国服务器为 +08:00，
    与 UTC 写入相差 8 小时）。在连接层 SET time_zone 后，三者全部落 UTC，
    与应用层写入一致，且不依赖服务器全局时区配置（无需动 DDL）。

    仅对 PyMySQL 连接生效；SQLite（测试库）等其它驱动原样跳过。
    """
    if type(dbapi_conn).__module__.startswith("pymysql"):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SET time_zone='+00:00'")
        finally:
            cursor.close()


def check_mysql_session_timezone(engine=None) -> None:
    """启动时自检 MySQL 会话时区确为 UTC（防御性，仅告警不阻断）。

    连接事件已经 SET time_zone，但若部署环境另有绕过 SQLAlchemy 的连接池配置、
    代理层重写，或有人误加了 init_command 覆盖，这里会立刻暴露。日志级 WARNING：
    时区设置不对不应让进程起不来，但必须可见。

    Args:
        engine: SQLAlchemy Engine；None 时取 flask_sqlalchemy 已绑定的 engine
    """
    from app.utils.logging import get_logger

    logger = get_logger(__name__)
    eng = engine or db.engine
    if eng is None or eng.dialect.name != "mysql":
        return
    try:
        with eng.connect() as conn:
            tz = conn.execute(text("SELECT @@session.time_zone")).scalar()
    except Exception as exc:  # 自检失败不影响启动
        logger.warning("MySQL 会话时区自检失败（不影响启动）: %s", exc)
        return
    if tz is None:
        return
    normalized = str(tz).strip().upper()
    if normalized not in ("+00:00", "UTC", "+0:00", "0:00"):
        logger.warning(
            "MySQL 会话时区为 %s，期望 UTC：库侧 DEFAULT/ON UPDATE/NOW() 会写入"
            "非 UTC 时间，导致与应用层 now_utc_naive() 相差若干小时。请检查网关/"
            "连接池的 init_command 是否覆盖了连接事件的 SET time_zone。",
            tz,
        )
