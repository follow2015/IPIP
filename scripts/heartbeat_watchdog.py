#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程自监控判活脚本（P0-T2.3）。

被 systemd timer 每 60s 拉起执行一次（Type=oneshot），**跑在被监控进程之外**
——这是它能发现「监控自身已死」的前提，不能塞进 Flask 里做。

三层信号（任一异常即告警）：
1. systemd：`systemctl show` 取 ActiveState / NRestarts —— 进程已经失败或被反复重启
2. 心跳 TTL：`ipip:heartbeat:<service>` 是否还在 —— 进程在但已僵死（死循环/GC/锁等待）
3. HTTP：`/api/health/check` —— 应用自报 Overall 不健康（DB/Redis 等依赖异常）

为什么三层都要：
- 只有 1：抓不到"活着但卡住"；
- 只有 2：抓不到"心跳线程正好也崩了但服务其实正常"的反向误报；
- 只有 3：端点本身依赖 Nginx/网络，网络抖动会误判。

去刷屏策略（两道）：
- Redis 状态键 `ipip:watchdog:<service>` 记录上次通知时间，冷却期内不重复告警；
- notify 的 idempotency_key 按「服务+原因+小时」兜底 —— Redis 状态丢失时仍能限流。

"无法判定"必须静默：Redis 不可用 / systemctl 无权限时**不产生任何故障判定**，
否则基础设施一抖就是满屏误警，自监控会先于被监控对象失信。

用法：
    python scripts/heartbeat_watchdog.py --dry-run          # 只打印报告
    python scripts/heartbeat_watchdog.py --services web,monitor
    python scripts/heartbeat_watchdog.py --no-systemd       # 非 systemd 环境
    python scripts/heartbeat_watchdog.py --no-http
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.utils.logging import get_logger  # noqa: E402

logger = get_logger("heartbeat_watchdog")

DEFAULT_COOLDOWN = 900  # 同一服务同一故障 15 分钟内只告警一次


def state_key(service: str) -> str:
    """告警状态键。环境隔离方式与心跳一致 —— 否则开发环境的状态会挡住
    生产环境的告警（或反之），排查时会看到"明明冷却已过却没发通知"。

    ipip:heartbeat:<env>: → 取 env 段 → ipip:watchdog:<env>:<service>
    """
    from app.services.monitoring import heartbeat

    parts = heartbeat.namespace().split(":")
    env = parts[-2] if len(parts) >= 4 else "production"
    return f"ipip:watchdog:{env}:{service}"


def unit_name(service: str) -> str:
    return f"ipip-{service}.service"


def check_systemd(service: str, timeout: int = 10) -> dict:
    """查 systemd：返回 Available/ActiveState/SubState/NRestarts。

    ⚠️ 不要用 `--value` 按行号取值：`systemctl show` 的输出顺序**不保证**与
    --property 的书写顺序一致（实测 NRestarts 会排在 ActiveState 之前），
    按行号解析必然错位 —— 表现为 active 取到 "0"、sub 取到 "active"，
    于是**所有健康服务都被判为异常**（实测：5 个 active/running 的服务被判 5 个异常，
    这类假警比不告警更糟：它会训练运维忽略告警）。
    改为解析自描述的 KEY=VALUE 输出，与顺序无关。
    """
    result = {"available": False, "active": None, "sub": None, "nrestarts": 0}
    try:
        proc = subprocess.run(
            [
                "systemctl", "show", unit_name(service),
                "--property=ActiveState", "--property=SubState", "--property=NRestarts",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError) as exc:
        logger.debug("systemctl 不可用 service=%s: %s", service, exc)
        return result

    if proc.returncode != 0:
        logger.debug("systemctl 返回 %s service=%s: %s", proc.returncode, service,
                     proc.stderr.strip())
        return result

    props = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            props[key.strip()] = val.strip()

    active = props.get("ActiveState")
    if not active:
        return result
    result["available"] = True
    result["active"] = active
    result["sub"] = props.get("SubState")
    try:
        result["nrestarts"] = int(props.get("NRestarts") or 0)
    except ValueError:
        result["nrestarts"] = 0
    return result


def check_http(base_url: str, timeout: int = 8) -> dict:
    """应用层自报健康；网络/网关异常时 'available=False'（不判故障）。"""
    result = {"available": False, "healthy": None, "detail": None}
    if not base_url:
        return result
    try:
        import requests

        resp = requests.get(f"{base_url.rstrip('/')}/api/health/check", timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        result["detail"] = str(exc)
        return result

    result["available"] = True
    try:
        payload = resp.json().get("data", {})
    except Exception:  # noqa: BLE001
        payload = {}
    result["healthy"] = bool(payload.get("overall_status") == "healthy")
    result["detail"] = f"HTTP {resp.status_code} overall={payload.get('overall_status')}"
    return result


def diagnose(service: str, sd: dict, hb: dict, stale_after: int, http: dict = None,
             restart_baseline: int = None):
    """合成单服务结论。返回 (problems: list[str], usable: bool)。

    usable=False 表示三层信号全都不可用、无法判定 —— 调用方必须跳过告警，
    否则基础设施一抖动就是满屏假警。

    http 层只归因给 web：`/api/health/check` 是应用整体健康，由 Flask 进程
    提供，挂到 monitor/gateway/celery 上是张冠李戴。

    restart_baseline：上一轮已计入的 NRestarts 基线，只报**超出基线的新增重启**。

    ⚠️ NRestarts 是**累计值**，只有 `systemctl reset-failed` 才清零，绝不能用
    `> 0` 当异常判据：一次历史崩溃会让此后每一轮都报「进程被重启过 N 次」，
    冷却期（默认 900s）一到就重复轰炸，而且因为 problems 恒非空，
    「恢复判定」永远走不到 → 告警无限循环、永不收敛。
    （实测踩到：crash 测试留下的 NRestarts=1 让 web/monitor 被持续告警。）
    """
    problems = []
    usable = False

    if sd.get("available"):
        usable = True
        if sd["active"] != "active":
            problems.append(f"systemd 状态异常: {sd['active']}/{sd['sub']}")
        else:
            nrestarts = sd.get("nrestarts") or 0
            baseline = restart_baseline or 0
            if nrestarts > baseline:
                delta = nrestarts - baseline
                problems.append(
                    f"进程被重启过 {delta} 次（累计 {nrestarts} 次，可能反复崩溃）"
                )

    if hb["checked"]:
        usable = True
        if not hb["alive"]:
            problems.append("心跳已过期：进程可能僵死或已退出")
        elif hb["age_seconds"] is not None and hb["age_seconds"] > stale_after:
            problems.append(f"心跳滞后 {hb['age_seconds']}s（阈值 {stale_after}s）")

    if http and http.get("available") and service == "web":
        usable = True
        if http.get("healthy") is False:
            problems.append(f"应用层健康检查未通过（{http.get('detail')}）")

    return problems, usable


def load_state(redis_client, service: str) -> dict:
    if redis_client is None:
        return {}
    try:
        raw = redis_client.get(state_key(service))
        return json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(redis_client, service: str, state: dict) -> None:
    if redis_client is None:
        return
    try:
        redis_client.set(state_key(service), json.dumps(state), ex=7 * 24 * 3600)
    except Exception as exc:  # noqa: BLE001
        logger.warning("watchdog 状态写入失败 service=%s: %s", service, exc)


def _advance_restart_baseline(redis_client, service: str, state: dict, sd: dict,
                              dry_run: bool) -> None:
    """无异常时把当前 NRestarts 记入基线。

    NRestarts 是累计值（见 diagnose 说明），不推进基线的后果是：历史累计值在
    每一轮都被判成「新增重启」→ 告警永不收敛。此处只在值确实变化时写 Redis，
    避免 timer 每分钟一次的无谓写入。
    """
    if dry_run or not sd.get("available"):
        return
    nrestarts = sd.get("nrestarts") or 0
    if state.get("last_nrestarts") == nrestarts:
        return
    state["last_nrestarts"] = nrestarts
    save_state(redis_client, service, state)


def should_notify(state: dict, now: float, cooldown: int) -> bool:
    last = state.get("notified_at")
    return last is None or (now - float(last)) >= cooldown


def run(args) -> dict:
    from app.services.monitoring import heartbeat
    from app.services.monitoring.heartbeat import SERVICES

    services = tuple(args.services.split(",")) if args.services else SERVICES
    now = _now()
    redis_client = heartbeat.get_redis_client()

    hb_view = heartbeat.build_heartbeat_view(services, client=redis_client, now=now)
    stale_after = hb_view["stale_after_seconds"]

    report = {
        "checked_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "redis_available": redis_client is not None,
        "services": {},
        "http": {"skipped": args.no_http},
        "alerts": [],
        "recovered": [],
    }

    if not args.no_http:
        report["http"] = check_http(args.base_url)

    for service in services:
        sd = {} if args.no_systemd else check_systemd(service, timeout=args.systemd_timeout)
        hb = hb_view["services"][service]
        state = load_state(redis_client, service)
        problems, usable = diagnose(service, sd, hb, stale_after, http=report["http"],
                                    restart_baseline=state.get("last_nrestarts"))
        entry = {"systemd": sd, "heartbeat": hb, "problems": problems,
                 "usable": usable, "unit": unit_name(service)}
        report["services"][service] = entry
        if not problems:
            _advance_restart_baseline(redis_client, service, state, sd, args.dry_run)
            continue
        if not usable:
            continue

        reason = problems[0]
        entry["state"] = state
        if not should_notify(state, now, args.cooldown):
            entry["suppressed"] = True
            continue
        report["alerts"].append({"service": service, "unit": unit_name(service),
                                 "reason": reason, "problems": problems})
        if args.dry_run:
            continue
        if _notify_down(service, problems, unit_name(service), now):
            state.update({"down": True, "reason": reason, "since": now,
                          "notified_at": now,
                          "last_nrestarts": sd.get("nrestarts") or 0})
            save_state(redis_client, service, state)
        else:
            entry["notify_failed"] = True  # 投递失败：下一轮重试，不进冷却

    for service in services:
        entry = report["services"][service]
        if entry["problems"] or not entry["usable"]:
            continue
        state = load_state(redis_client, service)
        if not state.get("down"):
            continue
        report["recovered"].append({"service": service, "unit": unit_name(service),
                                    "previous_reason": state.get("reason")})
        if not args.dry_run:
            _notify_recovered(service, unit_name(service), now)
            save_state(redis_client, service, {
                "down": False, "recovered_at": now,
                "last_nrestarts": state.get("last_nrestarts"),
            })

    if redis_client is None and not args.dry_run:
        _notify_watchdog_blind()
        report["watchdog_blind"] = True

    return report


def _now() -> float:
    import time

    return time.time()


def _notify_down(service: str, problems: list, unit: str, now: float) -> bool:
    """发出「服务异常」告警。返回是否投递成功。

    必须用 notify_strict 而非 notify：notify 把「投递失败」与「幂等去重」都返回
    None（见 notification_service.notify 的告警说明），调用方无法区分，会把失败
    当成功 → 告警静默丢失。这里必须拿到真实结果才能决定要不要落冷却状态。
    """
    from app.core.enums import ChannelType, NotificationTypeCode, SeverityLevel
    from app.services.notification_service import notification_service

    hour = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d%H")
    try:
        notification_service.notify_strict(
            type=NotificationTypeCode.SERVICE_UNHEALTHY,
            severity=SeverityLevel.CRITICAL,
            title=f"服务异常: {service}",
            content="；".join(problems),
            payload={"service": service, "unit": unit, "problems": problems},
            source_module="heartbeat_watchdog",
            target_type="role",
            target_id="admin",
            channels=(ChannelType.INBOX, ChannelType.EMAIL, ChannelType.WECHAT_WORK),
            idempotency_key=f"watchdog_down_{service}_{hour}",
            ack_required=True,
        )
        return True
    except Exception as exc:  # noqa: BLE001  单条投递失败不得中断其余服务的检查
        logger.error("watchdog 告警投递失败 service=%s: %s", service, exc)
        return False


def _notify_recovered(service: str, unit: str, now: float) -> bool:
    """发出「服务已恢复」通知。返回是否投递成功。

    恢复通知是信息性（INFO）而非告警，丢一条不至于让人误判系统状态，故走
    best-effort 的 notify；但状态清理仍以「已判定恢复」为准，不因投递失败
    反复重发恢复通知。
    """
    from app.core.enums import ChannelType, NotificationTypeCode, SeverityLevel
    from app.services.notification_service import notification_service

    hour = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d%H")
    notification_service.notify(
        type=NotificationTypeCode.SERVICE_RECOVERED,
        severity=SeverityLevel.INFO,
        title=f"服务已恢复: {service}",
        content=f"{unit} 三层判活信号恢复正常",
        payload={"service": service, "unit": unit},
        source_module="heartbeat_watchdog",
        target_type="role",
        target_id="admin",
        channels=(ChannelType.INBOX,),
        idempotency_key=f"watchdog_recovered_{service}_{hour}",
    )
    return True


def _notify_watchdog_blind() -> bool:
    """Redis 不可用 → watchdog 失去心跳信号源，必须让人知道（按小时去重）。"""
    from app.core.enums import ChannelType, NotificationTypeCode, SeverityLevel
    from app.services.notification_service import notification_service
    from datetime import datetime as _dt

    hour = _dt.now(tz=timezone.utc).strftime("%Y%m%d%H")
    try:
        notification_service.notify_strict(
            type=NotificationTypeCode.SERVICE_UNHEALTHY,
            severity=SeverityLevel.WARNING,
            title="自监控能力降级: Redis 不可用",
            content="watchdog 无法读取进程心跳，所有服务的「僵死」判定暂时失效，请检查 Redis",
            payload={"source": "heartbeat_watchdog"},
            source_module="heartbeat_watchdog",
            target_type="role",
            target_id="admin",
            channels=(ChannelType.INBOX,),
            idempotency_key=f"watchdog_blind_{hour}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog 失明告警投递失败: %s", exc)
        return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="IPIP 进程自监控判活")
    parser.add_argument("--services", help="逗号分隔的服务名，默认全部常驻服务")
    parser.add_argument("--base-url", default=os.getenv("WATCHDOG_BASE_URL",
                        "http://127.0.0.1:5000"), help="健康检查基址")
    parser.add_argument("--dry-run", action="store_true", help="只打印报告，不告警不写状态")
    parser.add_argument("--no-systemd", action="store_true", help="跳过 systemd 层（容器/无特权环境）")
    parser.add_argument("--no-http", action="store_true", help="跳过 HTTP 健康层")
    parser.add_argument("--cooldown", type=int, default=int(
        os.getenv("WATCHDOG_COOLDOWN", DEFAULT_COOLDOWN)), help="同一故障告警冷却秒数")
    parser.add_argument("--systemd-timeout", type=int, default=10)
    parser.add_argument("--quiet", action="store_true", help="无异常时不输出")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from app import create_app

    app = create_app(os.getenv("FLASK_CONFIG", "production"))
    with app.app_context():
        report = run(args)

    alert_count = len(report["alerts"])
    if not args.quiet or alert_count or report["recovered"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if alert_count:
        logger.warning("watchdog 判定 %d 个服务异常", alert_count)
    return 1 if alert_count else 0


if __name__ == "__main__":
    sys.exit(main())
