# -*- coding: utf-8 -*-
"""
通知外部渠道后台投递线程

不引入任务队列中间件（Celery/RQ）——量级上，一个进程内的 queue.Queue + 单条守护线程
完全够用，风格与 notification_cleanup.py 的 threading.Timer 方案保持一致。

**B-18① 进程重启丢任务**：内存队列在重启/崩溃时会丢掉未处理任务（`_drain_queue`
只是 best-effort，且挡不住 SIGKILL）。补法**不是**加标记或建表，而是利用一个
**既有的、天然的**待投递判据：`receipt.delivered_channels`（该用户分配到的渠道，
notify() 写入）减去 `receipt.channel_status`（已落库的投递结果）——**差集即未投递**。
于是启动时用 `recover_pending_deliveries()` 反查并重投即可，无需迁移、不动表结构，
且**崩溃场景同样覆盖**。中长期若要跨进程统一，再迁 DB outbox。

多进程部署（gunicorn -w N）下每个 worker 各自有一条独立的投递线程 + 独立队列，
互不影响——这里不需要像 SSE 场景那样做跨进程统一（投递没有"顺序/去重必须全局
一致"的硬要求，冷却窗口按进程各自维护即可接受轻微的过量发送，好过复杂的跨进程协调）。

**B-40 任务级有界并发**：单条线程串行消费时，一台慢 SMTP（实测单用户可拖 63s）
会按 63s/用户堵死整条队列——期间**其他通知也投不出去**。B-40 起 `_delivery_loop`
把"处理一条通知"提交到专用有界池（默认 4，`NOTIFICATION_DELIVERY_WORKERS` 可调）：
一条慢通知只占 1 个池线程，其余线程继续投别的通知。并发安全性依据：
① 冷却判定是单条原子 `SET NX`；② 每任务自带 `app_context`（session 按上下文隔离）；
③ 跨进程竞态本来就存在（每个 gunicorn worker 一条线程），池只提高概率、不扩大类别。
⚠️ **同一通知内的用户仍是串行**：voice 渠道在 `send` 内写调用方 session，
用户级并行有跨线程 ORM 危险——那是独立的一项，不在本改动内。
"""
from concurrent.futures import ThreadPoolExecutor

from app.core.enums import ChannelType
from app.utils.logging import get_logger
import queue
import threading
import time

logger = get_logger(__name__)

from app.persistence.notification_repository import (
    NotificationReceiptRepository,
    NotificationRepository,
)
from app.persistence.user_repository import UserRepository

_notification_repo = NotificationRepository()
_user_repo = UserRepository()
_receipt_repo = NotificationReceiptRepository()

_delivery_queue: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
_COOLDOWN_SECONDS = 300  # 同 type+source+channel 5 分钟内只投递一次，inbox 不受影响

_RATE_LIMIT_POLL_INTERVAL = 60  # RateLimitMonitor 轮询间隔（秒）
DELIVERY_TIMEOUT = 5  # 投递队列拉取超时时间（秒）
_seen_rate_limit_alerts: set[str] = set()  # 已通知过的限流告警去重游标

_DEFAULT_DELIVERY_WORKERS = 4

_inflight = threading.BoundedSemaphore(_DEFAULT_DELIVERY_WORKERS * 2)
_rate_limit_alerts_last_clear = 0.0  # 上次清空去重集合的时间戳


def enqueue_delivery(notification_id: int, user_ids: list[int]) -> None:
    """由 notify() 在 DB 提交后调用，非阻塞入队。

    队列满（maxsize=1000）属极端情况：先尽力阻塞 1s 入队以减少丢失，
    仍失败则记 critical 死信日志（不再静默丢弃）。被丢弃的任务**不会永久丢失**：
    其渠道结果未落库，下次进程启动时会由 `recover_pending_deliveries()` 回补（B-18①）。
    """
    try:
        _delivery_queue.put_nowait({"notification_id": notification_id, "user_ids": user_ids})
    except queue.Full:
        try:
            _delivery_queue.put({"notification_id": notification_id, "user_ids": user_ids}, timeout=1)
        except queue.Full:
            logger.critical(
                "通知投递队列已满，丢弃外部渠道投递任务(死信) notification_id=%s",
                notification_id,
            )


def _drain_queue(app) -> None:
    """进程退出前尽力排空队列（best-effort，无法应对 SIGKILL）。

    多 worker 部署下每个进程各自排空自己的内存队列。**未排空的部分不再丢失**：
    其对应的 `channel_status` 仍缺少非 inbox 渠道键，下次进程启动时
    `recover_pending_deliveries()` 会据此把它们捞回来重投（B-18①）。
    """
    drained = 0
    while not _delivery_queue.empty():
        try:
            task = _delivery_queue.get_nowait()
        except queue.Empty:
            break
        try:
            _process_one(app, task)
            drained += 1
        except Exception:
            logger.exception("停机排空时投递失败 notification_id=%s", task.get("notification_id"))
    if drained:
        logger.info("通知投递队列停机排空完成: %d 条", drained)


def _get_cooldown_redis():
    """获取冷却用 Redis 客户端；不可用时返回 None。

    项目没有 `extensions.redis_client`：Redis 统一经
    `app.services.switch_events._get_redis()` 获取，与 AI 模块的
    task_state / task_idempotency / circuit_breaker 同一惯例。
    """
    from app.services.switch_events import _get_redis

    try:
        return _get_redis()
    except Exception:
        logger.warning("冷却 Redis 客户端获取失败，本次不冷却", exc_info=True)
        return None


def _should_skip_cooldown(type_: str, source_module: str | None, channel_name: str) -> bool:
    """检查同 type+source+channel 是否在冷却窗口内（Redis 化）。

    P1-fix: 冷却键加渠道维度，避免邮件挡住语音；Redis 实现多 worker 共享冷却状态。

    Returns:
        True = 应跳过（在冷却窗口内），False = 可以发送
    """
    redis_client = _get_cooldown_redis()
    if redis_client is None:
        return False  # 降级：宁可多发，不可因 Redis 故障中断全部外部渠道

    key = f"cooldown:{type_}:{source_module or ''}:{channel_name}"
    try:
        return not redis_client.set(key, str(time.time()), ex=_COOLDOWN_SECONDS, nx=True)
    except Exception:
        logger.warning("冷却状态读写失败，降级为不冷却 key=%s", key, exc_info=True)
        return False


_CHANNEL_SEND_MAX_ATTEMPTS = 3
_CHANNEL_SEND_BACKOFF_SECONDS = 0.3  # 线性退避；单渠道最坏阻塞 ≈0.9s

_CHANNEL_NO_RETRY = frozenset({ChannelType.VOICE})


def _send_with_retry(channel, *args) -> tuple[bool, int]:
    """有限重试地投递一条渠道消息，返回 ``(是否成功, 尝试次数)``。

    仅对**异常**重试（返回值 False 视为确定性结果）；非幂等渠道只尝试一次。
    重试耗尽后仍抛最后一次异常，保持调用方既有的 `failed:<异常类名>` 记录语义。
    """
    name = channel.get_channel_name()
    max_attempts = 1 if name in _CHANNEL_NO_RETRY else _CHANNEL_SEND_MAX_ATTEMPTS
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return bool(channel.send(*args)), attempt
        except Exception as exc:  # noqa: BLE001 - 逐次重试，耗尽后原样抛出
            last_exc = exc
            if attempt < max_attempts:
                delay = _CHANNEL_SEND_BACKOFF_SECONDS * attempt
                logger.warning(
                    "渠道 %s 第 %d/%d 次投递异常，%.1fs 后重试: %s",
                    name, attempt, max_attempts, delay, exc,
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _prefetch_targets(notification, raw_user_ids) -> tuple[list, dict, dict]:
    """一次 IN 批量取回本任务的 User 与 Receipt。

    Returns:
        ``(user_ids, users_by_id, receipts_by_user)``；``user_ids`` 已做 ``None`` 归一。

    A-P1-2：替代「每用户 2 次查询」（500 人广播 = 1000 次 DB 往返）。
    ⚠️ notify() 主流程早有同族修法（`notification_service.py` 的 "n1"：
    "批量加载用户（一次 IN 查询）替代逐用户 find_by_id 的 N+1"），但只覆盖了**创建侧**、
    漏了**投递侧**，本处补齐。B-42①：数据访问统一走仓储（与 notify 同源），
    不再裸 `Model.query` —— 消除"仓储过滤软删除、裸 query 不过滤"的语义分叉。

    ⚠️ 已知边界（**未分块**）：`user_ids` 直接进 `IN`。广播可达数千用户，大 IN 会受
    MySQL `max_allowed_packet` / `range_optimizer_max_mem_size` 与 SQLite 绑定变量上限影响。
    不改的理由：创建侧对同一批 `user_ids` 早就是同样的未分块 `IN`，此处不引入新形态。
    """
    user_ids = raw_user_ids or []
    users_by_id: dict = {}
    receipts_by_user: dict = {}
    if not user_ids:
        return user_ids, users_by_id, receipts_by_user

    users_by_id = {u.id: u for u in _user_repo.find_by_ids(user_ids)}
    for receipt in _receipt_repo.find_by_notification_and_users(
        notification.id, user_ids,
    ):
        receipts_by_user.setdefault(receipt.user_id, receipt)
    return user_ids, users_by_id, receipts_by_user


def _commit_without_expire(session) -> None:
    """提交，但**不**让已加载对象过期（使逐用户提交不产生任何额外的重读 SELECT）。

    ⚠️ 只包 **worker 自己这一次** commit，**不修改全局口径**：渠道内部的 commit
    （`VoiceChannel.send` 里的两次 `db.session.commit()`）仍走默认 ``expire_on_commit=True``，
    从而 worker 随后的 ``status.update(dict(receipt.channel_status or {}))`` 会**重读**
    数据库里的最新值 —— N5 的语音终态保护正是建立在这个"重读"上
    （见 `channels/voice.py` 的"事务安全"说明与本函数调用处的 merge 注释）。

    若图省事**全局**关掉该开关：voice 的内部 commit 也不再过期，worker 会把内存旧值写回、
    覆盖语音回调刚落库的终态 ⇒ 轮询看不到结果 → 超时重试 → **同一人被重复外呼并烧掉外呼
    预算**；而**现有 N5 用例抓不到这个回归**（它用 _FakeReceipt + MagicMock session，
    不经历真实的过期语义）。故必须把"不过期"的范围限制在一次提交之内。
    """
    from sqlalchemy.orm import scoped_session

    real = session() if isinstance(session, scoped_session) else session

    prev = real.expire_on_commit
    real.expire_on_commit = False
    try:
        real.commit()
    finally:
        real.expire_on_commit = prev


def _process_one(app, task: dict) -> None:
    """处理一条投递任务"""
    from app.services.notification_service import NotificationService
    from extensions import db

    try:
        with app.app_context():
            notification = _notification_repo.find_by_id(task["notification_id"])
            if not notification:
                return

            for channel in NotificationService.get_broadcast_channels():
                ch_name = channel.get_channel_name()
                if _should_skip_cooldown(notification.type, notification.source_module, ch_name):
                    logger.debug("广播渠道 %s 命中冷却，跳过", ch_name)
                    continue
                try:
                    ok, _attempts = _send_with_retry(channel, notification)
                    if not ok:
                        logger.warning(
                            "广播渠道 %s 投递未成功（无匹配配置或全部失败）"
                            " notification_id=%s", ch_name, notification.id,
                        )
                    elif _attempts > 1:
                        logger.info("广播渠道 %s 重试后成功 attempts=%d", ch_name, _attempts)
                except Exception:
                    logger.exception("广播渠道 %s 投递失败", ch_name)

            cooldown_decisions: dict[str, bool] = {
                ch.get_channel_name(): _should_skip_cooldown(
                    notification.type, notification.source_module, ch.get_channel_name()
                )
                for ch in NotificationService.get_personal_channels()
                if ch.get_channel_name() != ChannelType.INBOX
            }

            user_ids, users_by_id, receipts_by_user = _prefetch_targets(
                notification, task["user_ids"]
            )

            for uid in user_ids:
                receipt = receipts_by_user.get(uid)
                user = users_by_id.get(uid)
                if not receipt or not user:
                    continue

                status = dict(receipt.channel_status or {})

                for channel in NotificationService.get_personal_channels():
                    name = channel.get_channel_name()
                    if name == ChannelType.INBOX:
                        status[name] = "ok"  # inbox 已在 notify() 主流程里落库
                        continue
                    if not channel.is_available(user):
                        status[name] = "skipped:unavailable"
                        continue
                    if cooldown_decisions.get(name):
                        status[name] = "skipped:cooldown"
                        continue
                    try:
                        _t0 = time.perf_counter()
                        ok, _attempts = _send_with_retry(channel, notification, receipt, user)
                        _duration_ms = int((time.perf_counter() - _t0) * 1000)
                        status.update(dict(receipt.channel_status or {}))
                        if name == ChannelType.VOICE and ok:
                            pass
                        else:
                            status[name] = "ok" if ok else "failed:unknown"
                        logger.info(
                            "渠道投递完成 channel=%s user_id=%s duration_ms=%d ok=%s attempts=%d",
                            name, uid, _duration_ms, ok, _attempts,
                        )
                    except Exception as exc:
                        logger.exception("渠道 %s 投递失败 user_id=%s", name, uid)
                        status.update(dict(receipt.channel_status or {}))
                        status[name] = f"failed:{type(exc).__name__}"

                from sqlalchemy.orm.attributes import flag_modified
                receipt.channel_status = status
                flag_modified(receipt, "channel_status")

                _commit_without_expire(db.session)
    except Exception:
        db.session.rollback()
        logger.exception("通知投递结果落库失败 notification_id=%s", task.get("notification_id"))


def _poll_rate_limit_alerts(app) -> None:
    """RateLimitMonitor 轮询桥接

    RateLimitMonitor 目前只有 get_alerts() 拉取接口，没有回调机制，
    这里用轮询 + 内容去重的方式桥接。
    """
    global _rate_limit_alerts_last_clear

    try:
        from app.utils.rate_limiting.limiter import UnifiedRateLimiter
        from app.services.ops_alert_bridge import bridge_rate_limit_alert
    except ImportError:
        return

    with app.app_context():
        try:
            from app.utils.rate_limiting.decorators import rate_limiter
            if not hasattr(rate_limiter, 'storage'):
                return
            monitor = getattr(rate_limiter, '_monitor', None)
            if monitor is None or not hasattr(monitor, 'get_alerts'):
                return
            alerts = monitor.get_alerts()
        except Exception:  # noqa: BLE001 - rate_limiter 未挂载 _monitor 时跳过监控采集（限流本身仍生效）
            return

        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            alert_key = f"{alert.get('key', '')}:{alert.get('endpoint', '')}"
            if alert_key in _seen_rate_limit_alerts:
                continue
            _seen_rate_limit_alerts.add(alert_key)
            try:
                bridge_rate_limit_alert(alert)
            except Exception:
                logger.exception("限流告警桥接失败")

        now = time.time()
        if now - _rate_limit_alerts_last_clear > 21600:  # 6 小时
            _seen_rate_limit_alerts.clear()
            _rate_limit_alerts_last_clear = now


_RECOVER_LOOKBACK_HOURS = 24
_RECOVER_MAX_TASKS = 200


def _pending_channels(receipt) -> list:
    """该 receipt 中「已分配渠道」减去「已落库投递结果」的差集（排除 inbox）。

    `notify()` 创建 receipt 时写入 `delivered_channels`（该用户实际分配到的渠道）
    与初始 `channel_status`（inbox 预置 `ok`），**非 inbox 渠道的结果由本模块
    worker 写入**——因此"缺失"即"未投递"，且该状态**持久化在 DB 里**：
    进程重启/SIGKILL 后依然成立，无需额外写标记。
    """
    delivered = receipt.delivered_channels or []
    status = receipt.channel_status or {}
    return [c for c in delivered if c != ChannelType.INBOX and c not in status]


def recover_pending_deliveries(app, lookback_hours: int = _RECOVER_LOOKBACK_HOURS,
                               max_tasks: int = _RECOVER_MAX_TASKS) -> int:
    """启动回补因进程重启/崩溃丢失的投递任务（B-18①），返回回补条数。

    判据见 `_pending_channels`：`delivered_channels − channel_status` 的差集非空
    即该通知尚有渠道未投递。按 notification 聚合用户后逐条 `_process_one` 重投。

    边界（避免启动瞬间的突发外部投递）：
    - 只看 `created_at` 在 `lookback_hours` 内的通知；
    - 单次最多 `max_tasks` 条；
    - 任何异常都只记日志、不影响正常投递链路（回补是 best-effort）。
    """
    from datetime import timedelta

    from app.utils.time_utils import now_utc_naive

    try:
        with app.app_context():
            cutoff = now_utc_naive() - timedelta(hours=lookback_hours)
            rows = _notification_repo.find_recent_receipts_with_notification_id(
                cutoff, limit=max_tasks * 5,
            )
            by_notification: dict = {}
            for receipt, nid in rows:
                if not _pending_channels(receipt):
                    continue
                if nid not in by_notification and len(by_notification) >= max_tasks:
                    break
                by_notification.setdefault(nid, []).append(receipt.user_id)
        if not by_notification:
            return 0

        recovered = 0
        for nid, user_ids in by_notification.items():
            try:
                _process_one(app, {"notification_id": nid, "user_ids": user_ids})
                recovered += 1
            except Exception:  # noqa: BLE001 - 单条失败不影响其余回补
                logger.exception("启动回补投递失败 notification_id=%s", nid)
        logger.info("启动回补投递完成: %d 条（重启/崩溃丢失的投递任务已重投）", recovered)
        return recovered
    except Exception:  # noqa: BLE001 - 回补失败不影响正常投递
        logger.exception("启动回补投递失败（不影响正常投递链路）")
        return 0


def _get_pool_size(app) -> int:
    """投递并发数（B-40）：读配置并兜底。

    ⚠️ 两条路径的越界语义**不同**（复审 M2 澄清，勿合并表述）：
    · env 路径（生产）：`config._env_num(..., min_value=1)` 已把 0/负数/非法值
      **回退成默认 4**，根本到不了这里；
    · 程序化路径（测试/代码内直接改 app.config）：此处钳 `max(1, n)`、
      非法值回退默认。
    两条路径的结果都安全（0 个并发不可能出现）。
    """
    raw = app.config.get(
        "NOTIFICATION_DELIVERY_WORKERS", _DEFAULT_DELIVERY_WORKERS
    )
    try:
        n = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "NOTIFICATION_DELIVERY_WORKERS 配置非法（%r），回退默认 %d",
            raw, _DEFAULT_DELIVERY_WORKERS,
        )
        return _DEFAULT_DELIVERY_WORKERS
    return max(1, n)


def _create_pool(app) -> ThreadPoolExecutor:
    """投递专用池。**不复用**全局 task_executor：那批是用户触发的扫描任务
    （容量 4、带 task_id 跟踪与 SSE task_failed 兜底推送），语义与容量都不同，
    混用会互相挤占。"""
    global _inflight
    n = _get_pool_size(app)
    _inflight = threading.BoundedSemaphore(n * 2)
    return ThreadPoolExecutor(
        max_workers=n, thread_name_prefix="notif_delivery"
    )


def _safe_process_one(app, task) -> None:
    """池线程里的异常捕获点：旧串行实现靠循环级 try/except，上池后异常
    发生在池线程里，不在这里捕获会被 Future **静默吞掉**（连日志都没有）。"""
    try:
        _process_one(app, task)
    except Exception:
        logger.exception(
            "通知投递任务处理失败 notification_id=%s", task.get("notification_id")
        )


def _run_task(app, task) -> None:
    """池线程入口：执行 + 归还在途额度。额度在 `_handle_task`（循环线程）acquire，
    必须在任务**完成后**才还——acquire/release 跨线程配对正是背压的机关。"""
    try:
        _safe_process_one(app, task)
    finally:
        _inflight.release()


def _handle_task(app, executor: ThreadPoolExecutor, task: dict) -> None:
    """单任务处理：先占在途额度（**阻塞点=背压点**），再提交池；退出期回退同步。

    ⚠️ B-28 实测坑：解释器退出时 concurrent.futures 的 `_python_exit` 已把
    `_shutdown` 置真，此后 `submit()` 必抛 "cannot schedule new futures after
    shutdown"——不回退的话退出期反复 submit 会刷屏（曾 4.3 万行）并拖住退出。
    回退同步即保持旧版"退出前尽力而为"语义，任务也不丢（额度当场归还，
    同步路径不占在途名额）。
    """
    _inflight.acquire()
    try:
        executor.submit(_run_task, app, task)
    except Exception:
        _inflight.release()
        _safe_process_one(app, task)


def _delivery_loop(app) -> None:
    """后台投递线程主循环（先回补上次进程遗留的未投递任务）"""
    last_rate_limit_poll = 0.0

    recover_pending_deliveries(app)

    executor = _create_pool(app)

    while True:
        try:
            task = _delivery_queue.get(timeout=DELIVERY_TIMEOUT)
            _handle_task(app, executor, task)
        except queue.Empty:
            pass
        except Exception:
            logger.exception("通知投递线程异常，继续循环")

        now = time.time()
        if now - last_rate_limit_poll > _RATE_LIMIT_POLL_INTERVAL:
            last_rate_limit_poll = now
            try:
                _poll_rate_limit_alerts(app)
            except Exception:
                logger.exception("RateLimitMonitor 轮询失败")


def start_delivery_worker(app) -> None:
    """启动后台投递线程（应在 create_app() 中调用）"""
    import atexit
    atexit.register(lambda: _drain_queue(app))  # 进程退出前尽力排空，减少通知丢失
    thread = threading.Thread(target=_delivery_loop, args=(app,), daemon=True)
    thread.start()
    logger.info("通知投递后台线程已启动")
