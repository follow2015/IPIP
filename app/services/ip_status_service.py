# -*- coding: utf-8 -*-
"""
IP 状态检测服务

使用 asyncio 并发 ping + TCP 端口探测，针对内网扫描场景做了安全限速。

核心设计原则：
  - 同一时刻最多 SAFE_MAX_CONCURRENT 个 IP 在探测，防止 ARP 突发洪泛导致
    交换机端口安全触发"源MAC违规"，使扫描机 IP 被封堵（"网络卡死"根因）。
  - ping 使用 asyncio.create_subprocess_exec（真正异步，不占用线程池）。
  - 私网地址只 ping，不做 TCP 扫描（内网无需跨层检测，TCP SYN 会引发 ARP 广播）。
  - TCP 探测按端口顺序串行，发现一个可达即返回，减少连接突发。
"""
import asyncio
import ipaddress
from app.utils.logging import get_logger
import math
import platform
import time
from typing import Callable, List, Optional, Set, Tuple

from sqlalchemy import bindparam
from sqlalchemy import text as sa_text

from app.core.enums import IPStatus
from app.persistence.ip_repositories import IPManagerRepository
from config import Config

logger = get_logger(__name__)


FAST_PROBE_PORTS: tuple = tuple(Config.COMMON_PORTS)

DEFAULT_TIMEOUT: float = 1.5

SAFE_MAX_CONCURRENT: int = 30




async def _async_ping(ip: str, timeout: float) -> bool:
    """使用 asyncio.create_subprocess_exec 发起 ping（不占用线程池）。

    旧版用 run_in_executor(None, subprocess.run, ...) 会为每个 IP
    占用一个 ThreadPoolExecutor 线程，500 并发时同时启动 500 个 ping 进程，
    引发 ARP 洪泛。本版本通过 asyncio 原生协程管理进程生命周期。

    Args:
        ip: 目标 IP 地址
        timeout: 超时（秒），Linux -W 参数向上取整为至少 1s

    Returns:
        bool: ping 通返回 True
    """
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    else:
        timeout_sec = max(1, int(timeout))
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), ip]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout + 1.0)
        return proc.returncode == 0
    except asyncio.TimeoutError:
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                logger.debug("终止ping子进程失败: ip=%s", ip, exc_info=True)
        return False
    except (OSError, FileNotFoundError) as e:
        logger.debug("ping %s 失败: %s", ip, e)
        return False




async def _async_tcp_probe(ip: str, port: int, timeout: float) -> bool:
    """异步 TCP 单端口探测。

    wait_closed 超时 0.2s，避免对端 RST 响应时长时间挂起。

    Args:
        ip: 目标 IP 地址
        port: 目标端口号
        timeout: connect 超时（秒）

    Returns:
        bool: 端口可达返回 True
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout,
        )
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
        except asyncio.TimeoutError:
            pass
        return True
    except (OSError, asyncio.TimeoutError):
        return False




async def _probe_ip(
    ip: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
    tcp_ports: tuple,
) -> tuple:
    """带信号量限速的单 IP 探测。

    探测策略（顺序执行，非全并发）：
      1. ping（所有 IP 均执行）
      2. TCP 端口顺序探测（仅公网 IP）

    私网 IP 跳过 TCP 原因：
      - 同子网内若 ping 不通，说明该 IP 的 ARP 无响应，设备未在线
      - TCP SYN 会触发 ARP 广播，并发时引发 ARP 洪泛冲击交换机

    旧版 _async_probe_ip 对每个 IP 同时发起 ping + N 个 TCP 任务，
    相当于 max_concurrent × (1 + N_ports) 个并发连接，实际并发远超
    信号量限制值，这是触发网络卡死的直接原因。

    Args:
        ip: 目标 IP 地址
        timeout: 单项超时（秒）
        semaphore: 全局并发信号量（1 个 IP 占 1 个 slot）
        tcp_ports: 需探测的端口元组

    Returns:
        tuple[str, bool]: (ip, is_active)
    """
    async with semaphore:
        if await _async_ping(ip, timeout):
            return ip, True

        try:
            is_private = ipaddress.ip_address(ip).is_private
        except ValueError:
            return ip, False

        if is_private:
            return ip, False

        for port in tcp_ports:
            if await _async_tcp_probe(ip, port, timeout=min(timeout, 0.8)):
                return ip, True

        return ip, False




async def batch_probe_ips(
    ips: List[str],
    timeout: float = DEFAULT_TIMEOUT,
    max_concurrent: int = SAFE_MAX_CONCURRENT,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Set[str]:
    """批量异步探测 IP 活跃状态。

    并发受 max_concurrent 信号量严格限制，防止突发 ARP/SYN 洪泛。

    Args:
        ips: 待探测 IP 列表（允许重复，内部去重）
        timeout: 单 IP 探测超时（秒），默认 1.5s
        max_concurrent: 最大并发探测数，默认 30
        progress_callback: 可选进度回调 (probed_count, total_count)

    Returns:
        Set[str]: 在线 IP 集合
    """
    if not ips:
        return set()

    unique_ips = list(dict.fromkeys(ips))   # 去重，保序
    total = len(unique_ips)
    active_ips: Set[str] = set()
    probed = 0

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _limited(ip: str) -> tuple:
        nonlocal probed
        result = await _probe_ip(ip, timeout, semaphore, FAST_PROBE_PORTS)
        probed += 1
        if progress_callback and (probed % 50 == 0 or probed == total):
            progress_callback(probed, total)
        return result

    overall_timeout = math.ceil(total / max_concurrent) * (timeout + 1.0) + 15

    tasks = [asyncio.create_task(_limited(ip)) for ip in unique_ips]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=overall_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "batch_probe_ips 整体超时(%.0fs)，已探测 %d/%d",
            overall_timeout, probed, total,
        )
        results = []
        for t in tasks:
            if not t.done():
                t.cancel()
            elif t.cancelled():
                continue
            elif t.exception() is not None:
                continue
            else:
                try:
                    results.append(t.result())
                except Exception:
                    logger.debug("获取探测任务结果失败", exc_info=True)

    for r in results:
        if isinstance(r, tuple) and len(r) == 2 and r[1] is True:
            active_ips.add(r[0])

    return active_ips




def detect_ip_status(ip_address: str, timeout: float = DEFAULT_TIMEOUT) -> IPStatus:
    """同步检测单个 IP 在线状态。

    新建独立 event loop，避免与 Flask 请求上下文冲突。

    Args:
        ip_address: 目标 IP 地址
        timeout: 探测超时（秒），默认 1.5s

    Returns:
        IPStatus: ACTIVE 或 INACTIVE
    """
    loop = asyncio.new_event_loop()
    try:
        sem = asyncio.Semaphore(1)
        _, is_active = loop.run_until_complete(
            _probe_ip(ip_address, timeout, sem, FAST_PROBE_PORTS)
        )
    finally:
        loop.close()
    return IPStatus.ACTIVE if is_active else IPStatus.INACTIVE




def _batch_update_inactive_preserve_unused(
    inactive_ips: List[str], room_id: int,
) -> None:
    """将非活跃 IP 标记为 INACTIVE，但保护 UNUSED 状态不被覆盖。

    只将当前 status=ACTIVE 的 IP 更新为 INACTIVE。
    UNUSED(3) 的 IP 表示从未被使用，不应被标记为"非活跃"。
    BANNED(2) 的 IP 也不应被降级。
    """
    if not inactive_ips:
        return
    repo = IPManagerRepository()
    repo.batch_update_status_to_inactive_preserve_unused(inactive_ips, room_id)
    repo.session.flush()


def _batch_update_status_to_db(
    status_data: List[Tuple[str, int, int]],
) -> None:
    """批量更新 IP 状态到数据库。

    按 (room_id, status) 分组批量 UPDATE，减少数据库往返。
    事务提交由 API 层 @transactional 统一管理。

    Args:
        status_data: [(ip_address, status, room_id), ...] 列表
    """
    from collections import defaultdict

    repo = IPManagerRepository()
    groups: dict = defaultdict(list)
    for ip, status, room_id in status_data:
        groups[(room_id, status)].append(ip)
    for (room_id, status), ip_list in groups.items():
        repo.batch_update_status_by_ips(ip_list, status, room_id)
    repo.session.flush()




def batch_detect_network_status(ip_network: str, room_id: int) -> dict:
    """批量检测网段内所有 IP 状态（asyncio 限速并发探测）。

    私网地址（RFC 1918）跳过探测——适用于管理机与业务网在不同 L3 域场景。
    若管理机与业务网同段，请使用 Phase 7 补充探测（supplement_detect_room_ips）。

    Args:
        ip_network: 网段 CIDR（如 203.0.113.0/24）
        room_id: 机房 ID

    Returns:
        dict: {total, active, inactive, updated} 或 {skipped: "private"}
    """
    network = ipaddress.ip_network(ip_network, strict=False)

    if network.is_private:
        logger.info("网段 %s 为私网地址，跳过主动探测", ip_network)
        return {"total": 0, "active": 0, "inactive": 0, "updated": 0, "skipped": "private"}

    all_hosts = [str(h) for h in network.hosts()]
    result = {"total": len(all_hosts), "active": 0, "inactive": 0, "updated": 0}

    if not all_hosts:
        return result

    if len(all_hosts) > 1024:
        logger.warning("网段 %s 主机数 %d 超过建议上限 1024", ip_network, len(all_hosts))

    start = time.time()
    loop = asyncio.new_event_loop()
    try:
        active_ips = loop.run_until_complete(
            batch_probe_ips(all_hosts, timeout=DEFAULT_TIMEOUT,
                            max_concurrent=SAFE_MAX_CONCURRENT)
        )
    finally:
        loop.close()

    elapsed = time.time() - start
    result["active"] = len(active_ips)
    result["inactive"] = len(all_hosts) - len(active_ips)
    result["updated"] = len(all_hosts)
    logger.info(
        "网段 %s 探测完成: 总=%d 在线=%d 离线=%d 耗时=%.1fs",
        ip_network, len(all_hosts), len(active_ips),
        len(all_hosts) - len(active_ips), elapsed,
    )

    active_updates: List[Tuple[str, int, int]] = [
        (ip, int(IPStatus.ACTIVE), room_id)
        for ip in active_ips
    ]
    inactive_ips = [ip for ip in all_hosts if ip not in active_ips]
    _batch_update_inactive_preserve_unused(inactive_ips, room_id)
    _batch_update_status_to_db(active_updates)
    return result




def _raise_fd_limit(target: int = 4096) -> None:
    """提升进程文件描述符软上限，防止 asyncio 并发下 FD 耗尽。

    SAFE_MAX_CONCURRENT=30 时，每轮最多 30 个 asyncio socket，
    通常无需提升 FD 上限；但保留此调用以应对用户自行调大并发的情况。

    Args:
        target: 期望软上限（默认 4096），不超过系统硬上限
    """
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        new_soft = min(target, hard)
        if soft < new_soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
            logger.debug("FD 软上限: %d → %d", soft, new_soft)
    except (ImportError, ValueError, OSError) as e:
        logger.debug("提升 FD 上限失败（通常无影响）: %s", e)




def fast_supplement_detect(
    scope: str,
    probe_ips: List[str],
    db_session,
    timeout: float = DEFAULT_TIMEOUT,
    max_concurrent: int = SAFE_MAX_CONCURRENT,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Phase 7 快速补充探测：对 ARP 未覆盖的规划 IP 执行在线检测。

    在 Phase 6 IP 全量对账之后调用，弥补 ARP 表盲区（缓存超时、
    无权限交换机、跨网段不可见）。仅将实际在线的 IP 升级为 ACTIVE，
    不降级已有状态，不覆盖 BANNED。

    Args:
        scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
        probe_ips: 待探测 IP 列表（已过滤，仅含 UNUSED/INACTIVE）
        db_session: SQLAlchemy session
        timeout: 单项超时（秒）
        max_concurrent: 最大并发探测数
        progress_callback: 进度回调 (probed, total)

    Returns:
        dict: {total, active_found, skipped}
    """
    result = {"total": len(probe_ips), "active_found": 0, "skipped": 0}

    if not probe_ips:
        return result

    _raise_fd_limit()
    start = time.time()

    loop = asyncio.new_event_loop()
    try:
        active_ips = loop.run_until_complete(
            batch_probe_ips(
                probe_ips,
                timeout=timeout,
                max_concurrent=max_concurrent,
                progress_callback=progress_callback,
            )
        )
    finally:
        loop.close()

    elapsed = time.time() - start
    logger.info(
        "[Phase7] 快速探测完成 scope=%s: 探测=%d 在线=%d 耗时=%.1fs",
        scope, len(probe_ips), len(active_ips), elapsed,
    )

    if not active_ips:
        return result

    result["active_found"] = len(active_ips)
    newly_active = list(active_ips)

    repo = IPManagerRepository(db_session)
    for i in range(0, len(newly_active), 500):
        batch = newly_active[i:i + 500]
        repo.batch_update_active_preserve_banned(batch)
    db_session.flush()
    return result


def supplement_detect_room_ips(
    room_id: int,
    db_session,
    max_workers: int = SAFE_MAX_CONCURRENT,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """从数据库加载规划网段，筛选 UNUSED/INACTIVE IP 后执行补充探测。

    本函数负责"从数据库找候选 IP"的准备阶段，
    探测本身委托给 fast_supplement_detect。

    Args:
        room_id: 机房 ID
        db_session: SQLAlchemy session
        max_workers: 最大并发数（对齐旧接口参数名）
        timeout: 单项超时（秒）

    Returns:
        dict: {total, active_found, skipped}
    """
    from app.core.enums import RouteNotes
    networks = db_session.execute(sa_text("""
        SELECT DISTINCT ipn.network FROM ip_networks ipn
        LEFT JOIN switch_routes sr
          ON sr.network_id = ipn.id AND sr.switch_id = ipn.switch_id
        WHERE ipn.room_id = :rid
          AND (sr.route_type NOT IN (:bh, :nh) OR sr.route_type IS NULL)
          AND ipn.network NOT LIKE '%/32'
    """), {
        "rid": room_id,
        "bh": int(RouteNotes.BLACKHOLE),
        "nh": int(RouteNotes.NEXTHOP),
    }).fetchall()

    if not networks:
        return {"total": 0, "active_found": 0, "skipped": 0}

    candidate_ips: list = []
    skipped_private = 0
    for (net_cidr,) in networks:
        try:
            net = ipaddress.ip_network(net_cidr, strict=False)
            if net.num_addresses > 4096:
                continue
            if net.is_private:
                skipped_private += 1
                continue
            for host in net.hosts():
                candidate_ips.append(str(host))
        except ValueError:
            continue

    if skipped_private:
        logger.info("[Phase7] 跳过 %d 个私网网段（跨段不可达）", skipped_private)

    if not candidate_ips:
        return {"total": 0, "active_found": 0, "skipped": skipped_private}

    probe_ips: set = set()
    for i in range(0, len(candidate_ips), 500):
        chunk = candidate_ips[i:i + 500]
        rows = db_session.execute(
            sa_text("""
                SELECT ip_address FROM ip_addresses
                WHERE room_id = :rid
                  AND status IN (:unused, :inactive)
                  AND ip_address IN :ips
            """).bindparams(bindparam("ips", expanding=True)),
            {
                "rid": room_id,
                "unused": int(IPStatus.UNUSED),
                "inactive": int(IPStatus.INACTIVE),
                "ips": chunk,
            },
        ).fetchall()
        probe_ips.update(r[0] for r in rows)

    result = fast_supplement_detect(
        scope=f"r:{room_id}",
        probe_ips=list(probe_ips),
        db_session=db_session,
        timeout=timeout,
        max_concurrent=max_workers,
    )
    result["skipped"] = len(candidate_ips) - len(probe_ips)
    return result