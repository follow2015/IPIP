# -*- coding: utf-8 -*-
"""资产保修 / 生命周期到期预警。

数据躺在 device_asset 表（warranty_end、online_date + lifecycle_years），
本模块把这些日期变成一条每日站内通知，避免"数据有、功能无"。

调度面沿用 notification_cleanup.py 的进程内守护线程范式：
不依赖 MySQL EVENT、不引入 APScheduler 等新依赖，在 create_app() 中启动。

预警档位（days_left = 到期剩余天数，负数表示已过期）：

- ``0 <= days_left <= 7`` → expiring_7（紧急续保，含"今天到期"）
- ``7 < days_left <= 30`` → expiring_30（预算规划）
- ``days_left < 0``       → expired，且按过期时长降频：
  - 过期 <= 3 天：每天提醒；
  - 过期 4~30 天：每周提醒一次（周一）；
  - 过期 > 30 天：移出汇总，不再提醒。

保修与生命周期共用同一套档位（生命周期到期日 = online_date + lifecycle_years 年）。
"""
import fcntl
import os
import threading
import time
from dataclasses import dataclass
from datetime import date

from app.core.enums import ChannelType, NotificationTypeCode, SeverityLevel
from app.services.notification_service import notification_service
from app.utils.logging import get_logger
from app.utils.time_utils import utc_today

logger = get_logger(__name__)

EXPIRING_SOON_DAYS = 7
EXPIRING_WARN_DAYS = 30
OVERDUE_DAILY_DAYS = 3
OVERDUE_DROP_DAYS = 30
WEEKLY_ALERT_WEEKDAY = 0
MAX_LISTED_PER_BUCKET = 20

BUCKET_EXPIRED = "expired"
BUCKET_EXPIRING_7 = "expiring_7"
BUCKET_EXPIRING_30 = "expiring_30"
BUCKET_ORDER = (BUCKET_EXPIRED, BUCKET_EXPIRING_7, BUCKET_EXPIRING_30)

BUCKET_LABELS = {
    BUCKET_EXPIRED: "已过期",
    BUCKET_EXPIRING_7: "7天内到期",
    BUCKET_EXPIRING_30: "30天内到期",
}

KIND_WARRANTY = "warranty"
KIND_LIFECYCLE = "lifecycle"
KIND_LABELS = {KIND_WARRANTY: "保修", KIND_LIFECYCLE: "生命周期"}

ALERT_INTERVAL = int(os.environ.get("ASSET_WARRANTY_ALERT_INTERVAL", 21600))
STARTUP_DELAY = int(os.environ.get("ASSET_WARRANTY_ALERT_STARTUP_DELAY", 60))

DEFAULT_LOCK_FILENAME = "asset-warranty-alert.lock"

_singleton_lock_handle = None


@dataclass
class AssetRow:
    """扫描输入的最小资产视图（与 ORM 解耦，便于纯函数测试）。"""

    device_id: int
    device_name: str
    warranty_end: date | None = None
    lifecycle_years: int | None = None
    online_date: date | None = None
    offline_date: date | None = None


@dataclass
class AssetAlertItem:
    """一条到期预警。"""

    device_id: int
    device_name: str
    kind: str            # warranty / lifecycle
    bucket: str          # expired / expiring_7 / expiring_30
    due_date: date


def _add_years(base: date, years: int) -> date:
    """给日期加整年，2 月 29 日退化为 2 月 28 日。"""
    try:
        return base.replace(year=base.year + years)
    except ValueError:
        return base.replace(year=base.year + years, day=28)


def _is_weekly_alert_day(today: date) -> bool:
    """判断今天是否为"过期降频"的每周提醒日（周一）。"""
    return today.weekday() == WEEKLY_ALERT_WEEKDAY


def classify_due_date(due_date: date | None, today: date) -> str | None:
    """按到期日判定档位，返回档位标识或 None（无需预警）。

    Args:
        due_date: 到期日（保修到期日 / 生命周期到期日），None 表示数据缺失。
        today: 基准日期。

    Returns:
        档位标识（expired / expiring_7 / expiring_30），不应提醒时返回 None。
    """
    if due_date is None:
        return None

    days_left = (due_date - today).days
    if days_left < 0:
        overdue_days = -days_left
        if overdue_days > OVERDUE_DROP_DAYS:
            return None
        if overdue_days > OVERDUE_DAILY_DAYS and not _is_weekly_alert_day(today):
            return None
        return BUCKET_EXPIRED
    if days_left <= EXPIRING_SOON_DAYS:
        return BUCKET_EXPIRING_7
    if days_left <= EXPIRING_WARN_DAYS:
        return BUCKET_EXPIRING_30
    return None


def _lifecycle_due_date(row: AssetRow) -> date | None:
    """计算生命周期到期日 = online_date + lifecycle_years 年。"""
    if row.online_date is None or not row.lifecycle_years:
        return None
    return _add_years(row.online_date, int(row.lifecycle_years))


def collect_asset_alerts(rows, today: date) -> list[AssetAlertItem]:
    """把资产行转换为到期预警列表（纯函数，不访问数据库）。

    Args:
        rows: 可迭代的 AssetRow（离线/软删除过滤由调用方在查询层完成）。
        today: 基准日期。

    Returns:
        AssetAlertItem 列表，按档位紧急度、到期日排序。
    """
    items: list[AssetAlertItem] = []
    for row in rows:
        if row.offline_date is not None:
            continue

        for kind, due_date in (
            (KIND_WARRANTY, row.warranty_end),
            (KIND_LIFECYCLE, _lifecycle_due_date(row)),
        ):
            bucket = classify_due_date(due_date, today)
            if bucket is None:
                continue
            items.append(
                AssetAlertItem(
                    device_id=row.device_id,
                    device_name=row.device_name or f"device-{row.device_id}",
                    kind=kind,
                    bucket=bucket,
                    due_date=due_date,
                )
            )

    items.sort(key=lambda it: (BUCKET_ORDER.index(it.bucket), it.due_date, it.device_id))
    return items


def build_summary(items: list[AssetAlertItem]) -> tuple[str, str, str, dict]:
    """把预警列表汇总为一条通知的标题/正文/级别/载荷（纯函数）。

    Args:
        items: collect_asset_alerts() 的输出。

    Returns:
        (title, content, severity, payload)。
    """
    severity = (
        SeverityLevel.INFO
        if all(it.bucket == BUCKET_EXPIRING_30 for it in items)
        else SeverityLevel.WARNING
    )

    buckets: dict[str, list[AssetAlertItem]] = {b: [] for b in BUCKET_ORDER}
    for item in items:
        buckets[item.bucket].append(item)

    title = f"资产到期提醒: 共 {len(items)} 项"
    lines: list[str] = []
    for bucket in BUCKET_ORDER:
        group = buckets[bucket]
        if not group:
            continue
        lines.append(f"【{BUCKET_LABELS[bucket]}】{len(group)} 项")
        for item in group[:MAX_LISTED_PER_BUCKET]:
            lines.append(
                f"  - {item.device_name}（{KIND_LABELS[item.kind]}，到期 {item.due_date}）"
            )
        if len(group) > MAX_LISTED_PER_BUCKET:
            lines.append(f"  - 等 {len(group) - MAX_LISTED_PER_BUCKET} 项")

    payload = {
        "device_ids": list(dict.fromkeys(it.device_id for it in items)),
        "buckets": {b: len(buckets[b]) for b in BUCKET_ORDER if buckets[b]},
        "total": len(items),
    }
    return title, "\n".join(lines), severity, payload


def _load_asset_rows() -> list[AssetRow]:
    """从数据库读取待扫描的资产行。

    过滤下推到 SQL（只查需要的列，避免水化完整实体）：
    - Device.deleted_at IS NULL：Device 是软删除模型，不过滤会扫出幽灵设备；
    - DeviceAsset.offline_date IS NULL：已下线/报废设备的到期无意义；
    - Device.status != SCRAPPED：报废设备不提醒（见 DeviceStatus 注释）。
    """
    from app.core.enums import DeviceStatus
    from app.models.device import Device
    from app.models.device_asset import DeviceAsset
    from extensions import db

    rows = (
        db.session.query(
            DeviceAsset.device_id,
            Device.device_name,
            DeviceAsset.warranty_end,
            DeviceAsset.lifecycle_years,
            DeviceAsset.online_date,
            DeviceAsset.offline_date,
        )
        .join(Device, Device.id == DeviceAsset.device_id)
        .filter(
            Device.deleted_at.is_(None),
            Device.status != DeviceStatus.SCRAPPED,
            DeviceAsset.offline_date.is_(None),
        )
        .all()
    )
    return [AssetRow(*row) for row in rows]


def scan_and_notify(today: date | None = None) -> int:
    """执行一次扫描：有到期项则给 admin 角色投递一条汇总站内通知。

    Args:
        today: 基准日期，默认取 UTC 日历日（供测试注入）。

    Returns:
        预警条目数；0 表示本次无需提醒（不投递）。
    """
    today = today or utc_today()
    items = collect_asset_alerts(_load_asset_rows(), today)
    if not items:
        return 0

    title, content, severity, payload = build_summary(items)
    notification = notification_service.notify(
        type=NotificationTypeCode.ASSET_WARRANTY_ALERT,
        severity=severity,
        title=title,
        content=content,
        payload=payload,
        source_module="asset_warranty_alert",
        target_type="role",
        target_id="admin",
        channels=(ChannelType.INBOX,),
        idempotency_key=f"asset_warranty_alert:{today.isoformat()}",
        allow_broadcast=False,
    )
    if notification is None:
        logger.info("资产到期预警未投递（当日已发或投递失败）: %d 项", len(items))
    else:
        logger.info("资产到期预警已投递: 共 %d 项 %s", len(items), payload["buckets"])
    return len(items)


def _alert_loop() -> None:
    """扫描循环（后台守护线程）：启动后先扫一次，再按间隔周期执行。"""
    time.sleep(STARTUP_DELAY)
    while True:
        try:
            scan_and_notify()
        except Exception:
            logger.warning("资产到期预警扫描失败", exc_info=True)
            _rollback_session()
        finally:
            _release_session()
        time.sleep(ALERT_INTERVAL)


def _session():
    """取当前 session（延迟导入，避免模块加载时依赖 db）。"""
    from extensions import db

    return db.session


def _rollback_session() -> None:
    """扫描异常后回滚，避免 session 进入 PendingRollbackError 导致后续全失败。"""
    try:
        _session().rollback()
    except Exception:
        logger.warning("资产到期预警回滚失败", exc_info=True)


def _release_session() -> None:
    """释放本轮 session，把连接归还连接池。"""
    try:
        _session().remove()
    except Exception:
        logger.warning("资产到期预警 session.remove 失败", exc_info=True)


def _enabled() -> bool:
    """是否启用（环境变量 ASSET_WARRANTY_ALERT_ENABLED，默认开启）。"""
    return os.environ.get("ASSET_WARRANTY_ALERT_ENABLED", "1").lower() not in ("0", "false", "no")


def _lock_path() -> str:
    """调度器单实例锁文件路径。

    可用 ASSET_WARRANTY_ALERT_LOCK_FILE 覆盖（测试/多实例部署时重定向到可写目录），
    否则落到<项目根>/instance/locks/asset-warranty-alert.lock。
    每次调用实时读 env，便于运行期打桩与部署期覆盖。
    """
    override = os.environ.get("ASSET_WARRANTY_ALERT_LOCK_FILE")
    if override:
        return override
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "instance", "locks", DEFAULT_LOCK_FILENAME)


def _acquire_singleton_lock():
    """尝试获取每主机独占的调度器锁（非阻塞）。

    Returns:
        成功时返回已加锁的文件对象（须由调用方长期持有，见模块级
        ``_singleton_lock_handle``）；锁已被其他进程持有时返回 None。

    Raises:
        OSError: 锁文件无法创建/打开（目录不可写等环境故障）。由调用方决定
            降级策略——此处不吞掉，避免"锁不可用"被误判成"已被别人占用"。

    实现选 flock 而非"锁文件是否存在"：flock 与 fd 绑定，进程退出（含崩溃）由
    内核自动释放，不会像残留锁文件那样把调度器永久卡死。
    """
    path = _lock_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def start_asset_warranty_alert_scheduler(app) -> None:
    """启动资产到期预警后台线程（在 create_app() 中调用，每主机单实例）。

    多 worker（gunicorn N 进程）都会执行 create_app()，若不设防则 N 个进程各起
    一个 ``_alert_loop`` 并发扫描；而通知去重是"按 idempotency_key 先查后插"，
    并发下存在 check-then-insert 竞态→重复投递。故先抢独占文件锁，抢不到者直接
    返回（静默让位，属正常情形）。

    Args:
        app: Flask 应用实例（后台线程不在请求上下文内，需显式提供 app_context）。
    """
    if not _enabled():
        logger.info("资产到期预警线程未启用（ASSET_WARRANTY_ALERT_ENABLED=0）")
        return

    global _singleton_lock_handle
    try:
        handle = _acquire_singleton_lock()
    except OSError as exc:
        logger.warning("资产到期预警调度器锁不可用（%s），本进程在无单实例保护下继续", exc)
        handle = None
    else:
        if handle is None:
            logger.info(
                "资产到期预警调度器锁已由其他进程持有（%s），本进程不再启动扫描线程",
                _lock_path(),
            )
            return
    _singleton_lock_handle = handle

    def _run_with_app_context() -> None:
        with app.app_context():
            _alert_loop()

    thread = threading.Thread(
        target=_run_with_app_context, daemon=True, name="asset-warranty-alert",
    )
    thread.start()
    logger.info(
        "资产到期预警线程已启动 (间隔=%ds, 首次延迟=%ds)",
        ALERT_INTERVAL, STARTUP_DELAY,
    )
