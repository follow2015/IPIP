# -*- coding: utf-8 -*-
"""SNMP Trap 接收独立服务入口（P1-1）

架构：原生 UDP socket 收包 → pyasn1 BER 解码（v1/v2c）→ 有界队列（收包循环
永不阻塞，防爆）→ worker 线程（app 上下文内做设备关联/规则匹配/治理/入箱）。

**为何不用 pysnmp ``NotificationReceiver``**：pysnmp 7.1.27 的 asyncio 传输与
hlapi 在 Python 3.13/3.14 上存在 API 漂移与兼容缺陷（本项目 snmp_adapter.py
docstring 已记录过一轮）。Trap 接收只需要「收 UDP + BER 解码 + community 校验」，
用 pyasn1 直接解码 ``SNMPv2c/Message``（RFC 2578 标签 A0/A4/A7）行为完全确定、
不受 pysnmp 版本漂移影响。规则/治理/入箱仍与既有告警链路同构。

用法：
    python run_trapd_service.py [environment]

部署形态：deploy/systemd/ipip-trapd.service（PartOf=ipip.target）。
不部署 unit 即无此能力，且完全不影响轮询采集（回滚 = systemctl disable --now）。

端口说明：UDP/162 为特权端口；无特权环境默认 10162（TRAPD_LISTEN_PORT），
在交换机侧指定 trap 目标端口或在主机上做端口重定向。
"""
import ipaddress
import json
import os
import queue
import socket
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1.error import PyAsn1Error

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

_PDU_TAG_V2_TRAP = 7      # SNMPv2-Trap-PDU [7] IMPLICIT PDU
_PDU_TAG_V1_TRAP = 4      # RFC 1157 Trap-PDU [4] IMPLICIT PDU

_V1_GENERIC_TRAP_BASE = "1.3.6.1.6.3.1.1.5"  # RFC 2576 翻译后的 generic trap 地址族

_WEAK_COMMUNITIES = frozenset({"public", "private"})
_WILDCARD_ADDRESSES = frozenset({"0.0.0.0", "::", ""})  # noqa: S104 -- 通配地址判定集合，非 socket bind


@lru_cache(maxsize=1)
def _snmp_trap_oid() -> str:
    """``SNMPv2-MIB::snmpTrapOID.0`` 的取值 —— **取自 pysnmp，不许手写**。

    [WARN] 这里原来是 ``_SNMP_TRAP_OID = "1.3.6.1.6.3.1.1.6.1"``，
    注释写着 snmpTrapOID.0、值却**抄错了一位**（正确是 ``...1.1.4.1.0``）。
    后果是所有标准设备发的 v2c trap 都匹配不上 ⇒ ``trap_oid`` 恒空
    ⇒ ``decode_trap_message`` 返回 None ⇒ ``_recv_loop`` 以
    「无法解码的报文（非 SNMP trap？）」**全部丢弃**，且日志措辞会把人引向
    「设备没配 trap」。测试夹具当初手抄了同一个错值，与实现双向自洽，
    所以 40 条用例一路全绿 —— 详见设计文档 §9.4 缺陷 1。

    **改为惰性取值的原因**：``_v2c`` 在本文件是**函数内延迟导入**（避免把
    pysnmp 拉进服务启动的关键路径），模块级拿不到。``lru_cache`` 让首次
    之后的调用退化成字典查找，热路径每行 varbind 调一次也不受影响。
    """
    from pysnmp.proto.api import v2c as pysnmp_v2c

    return ".".join(str(x) for x in pysnmp_v2c.apiTrapPDU.snmpTrapOID)


def _split_list(raw) -> list[str]:
    """逗号分隔配置项 → 去空去空白的列表。"""
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def parse_source_allowlist(raw) -> tuple | None:
    """解析 ``TRAPD_SOURCE_ALLOWLIST`` → 网络对象元组；空配置返回 None（不过滤）。

    写错必须 fail-fast：静默失效会让运维误以为「已在防伪造」。
    """
    entries = _split_list(raw)
    if not entries:
        return None
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise SystemExit(
                f"TRAPD_SOURCE_ALLOWLIST 写法非法: {entry!r}（应为 IP 或 CIDR，"
                f"如 10.0.0.0/8,192.168.1.5）：{exc}"
            ) from exc
    return tuple(networks)


def decode_trap_message(data: bytes) -> dict | None:
    """BER 解码一条 SNMP trap 报文（v2c / v1 统一出口）。

    Message 的第 3 个组件是名为 ``data`` 的 PDUs **choice**：按选项名取
    ``snmpV2-trap``（v2c）/ ``trap``（v1）即天然过滤 GET/SET/RESPONSE，
    非 trap 报文取不到对应选项 → 返回 None。

    Returns:
        dict: {"community": str, "version": str,
               "trap_oid": str, "varbinds": [(oid_str, value_str), ...]}
        无法解码/不是 trap 报文返回 None。
    """
    from pysnmp.proto.api import v2c as _v2c, v1 as _v1  # 延迟导入，仅服务/测试用

    try:
        message, _ = ber_decoder.decode(data, asn1Spec=_v2c.Message())
        community = str(message.getComponentByPosition(1))
        data_choice = message.getComponentByName("data")
        pdu = data_choice.getComponentByName("snmpV2-trap")
        trap_oid_key = _snmp_trap_oid()  # 循环外取一次，避免每行重入 lru_cache
        trap_oid = ""
        varbinds = []
        for name, value in _v2c.apiTrapPDU.get_varbinds(pdu):
            name_s = str(name).strip(".")
            pretty = getattr(value, "prettyPrint", None)
            text = pretty() if callable(pretty) else str(value)
            varbinds.append((name_s, text))
            if name_s == trap_oid_key:
                trap_oid = text.strip().lstrip(".")
        if trap_oid:
            return {"community": community, "version": "v2c",
                    "trap_oid": trap_oid, "varbinds": varbinds}
        return None
    except PyAsn1Error:
        pass

    try:
        message, _ = ber_decoder.decode(data, asn1Spec=_v1.Message())
        community = str(message.getComponentByPosition(1))
        data_choice = message.getComponentByName("data")
        pdu = data_choice.getComponentByName("trap")
        enterprise = str(pdu.getComponentByName("enterprise")).strip(".")
        generic = int(pdu.getComponentByName("generic-trap"))
        specific = int(pdu.getComponentByName("specific-trap"))
        if generic == 6:  # enterpriseSpecific → RFC 2576: enterprise.0.specific
            trap_oid = f"{enterprise}.0.{specific}"
        else:             # generic → RFC 2576 翻译到 snmpTraps 地址族（下标 = generic+1）
            trap_oid = f"{_V1_GENERIC_TRAP_BASE}.{generic + 1}"
        varbinds = []
        for name, value in _v1.apiTrapPDU.get_varbinds(pdu):
            pretty = getattr(value, "prettyPrint", None)
            varbinds.append((str(name).strip("."),
                             pretty() if callable(pretty) else str(value)))
        return {"community": community, "version": "v1",
                "trap_oid": trap_oid, "varbinds": varbinds}
    except PyAsn1Error:
        return None


class TrapdService:
    """Trap 接收服务：UDP 收包线程与加工 worker 线程解耦（有界队列衔接）。"""

    def __init__(self, app, ingest_service=None, decode_fn=None):
        self.app = app
        cfg = app.config
        self.listen_address = cfg.get("TRAPD_LISTEN_ADDRESS", "0.0.0.0")  # noqa: S104 -- 归因见批次4
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=int(cfg.get("TRAPD_QUEUE_SIZE", 1000)))
        self._ingest_injected = ingest_service is not None
        self._decode_injected = decode_fn is not None
        self._decode = decode_fn or decode_trap_message
        if ingest_service is not None:
            self._ingest = ingest_service
        else:
            self._ingest = None

        self.listen_port = int(cfg.get("TRAPD_LISTEN_PORT", 10162))
        self.communities: list = []
        self.v3_enabled = False
        self.v3_users: dict = {}
        self.source_allowlist = None
        self._sock: socket.socket | None = None
        self._recv_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._runtime_sig: tuple | None = None
        self._current_cfg: dict | None = None
        self._last_error: str | None = None
        self._stopping = False
        self._closing = False
        self._dyncfg_failures = 0
        self._dyncfg_retry_at = 0.0
        self._dropped_count = 0
        self._decode_error_count = 0
        self._rejected_source_count = 0
        self._v3_rejected_count = 0

    _CFG_KEYS = (
        "TRAPD_ENABLED",
        "TRAPD_LISTEN_PORT",
        "TRAPD_SOURCE_ALLOWLIST",
        "TRAPD_RATE_LIMIT_PER_MINUTE",
        "TRAPD_ALLOW_WEAK_COMMUNITY",
        "TRAPD_V3_ENABLED",
        "TRAPD_V3_USERS",
    )

    _DYNCFG_FAIL_THRESHOLD = 3
    _DYNCFG_BACKOFF_MAX = 300

    def _runtime_config(self) -> dict:
        """读一份最新运行时配置（每次循环重读，实现热开关）。

        动态配置不可达时**退避**：前 ``_DYNCFG_FAIL_THRESHOLD`` 次连续失败照常
        重试（应对瞬时抖动），超过后按指数退避到 ``_DYNCFG_BACKOFF_MAX``。
        退避期间直接返回上一份配置 / .env 初值，不碰 Redis、不打日志。
        """
        cfg = self.app.config
        v3_enabled = bool(cfg.get("TRAPD_V3_ENABLED", False))
        v3_users_raw = str(cfg.get("TRAPD_V3_USERS", "") or "")
        out = {
            "enabled": bool(cfg.get("TRAPD_ENABLED", False)),
            "port": int(cfg.get("TRAPD_LISTEN_PORT", 10162)),
            "allowlist": cfg.get("TRAPD_SOURCE_ALLOWLIST", "") or "",
            "rate_limit": int(cfg.get("TRAPD_RATE_LIMIT_PER_MINUTE", 120)),
            "allow_weak": bool(cfg.get("TRAPD_ALLOW_WEAK_COMMUNITY", False)),
            "v3_enabled": v3_enabled,
            "v3_users": {},
        }
        now = time.monotonic()
        if self._dyncfg_failures >= self._DYNCFG_FAIL_THRESHOLD:
            if now < self._dyncfg_retry_at:
                return self._current_cfg or out  # 退避窗口内：不试、不打日志
        try:
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig

            with self.app.app_context():
                for key in self._CFG_KEYS:
                    val = MonitorDynamicConfig.get(key)
                    if val is None:
                        continue
                    if key == "TRAPD_ENABLED":
                        out["enabled"] = bool(val)
                    elif key == "TRAPD_LISTEN_PORT":
                        out["port"] = int(val)
                    elif key == "TRAPD_SOURCE_ALLOWLIST":
                        out["allowlist"] = str(val or "")
                    elif key == "TRAPD_RATE_LIMIT_PER_MINUTE":
                        out["rate_limit"] = int(val)
                    elif key == "TRAPD_ALLOW_WEAK_COMMUNITY":
                        out["allow_weak"] = bool(val)
                    elif key == "TRAPD_V3_ENABLED":
                        out["v3_enabled"] = bool(val)
                    elif key == "TRAPD_V3_USERS":
                        v3_users_raw = str(val or "")
        except Exception:  # 已在上面 logger.exception 留痕，此处仅尽力回滚
            self._dyncfg_failures += 1
            if self._dyncfg_failures == self._DYNCFG_FAIL_THRESHOLD:
                logger.warning(
                    "[trapd] 动态配置连续读取失败 %d 次，转入退避（热开关暂不可用；"
                    "Redis 恢复后会自动接上）",
                    self._dyncfg_failures,
                    exc_info=True,
                )
            if self._dyncfg_failures >= self._DYNCFG_FAIL_THRESHOLD:
                backoff = min(
                    self.POLL_INTERVAL_SECONDS * (2 ** (self._dyncfg_failures - self._DYNCFG_FAIL_THRESHOLD)),
                    self._DYNCFG_BACKOFF_MAX,
                )
                self._dyncfg_retry_at = now + backoff
            return self._finalize_cfg(self._current_cfg or out, v3_users_raw)
        if self._dyncfg_failures:
            logger.info(
                "[trapd] 动态配置已恢复（此前连续失败 %d 次）", self._dyncfg_failures
            )
        self._dyncfg_failures = 0
        self._dyncfg_retry_at = 0.0
        return self._finalize_cfg(out, v3_users_raw)

    def _finalize_cfg(self, out: dict, v3_users_raw: str) -> dict:
        """配置收口：按最终开关值决定是否解析 v3 用户表。

        **只在 v3 开启时解析**，且只在这里做一次（不在动态配置循环内逐键做）：
        解析要遍历凭据库并逐行解密，而 ``_runtime_config`` 每 POLL_INTERVAL_SECONDS
        秒就跑一次 —— 默认关闭的情况下每 10s 白读一次全表，DB 不可达时还会每 10s
        多一条 warning 刷屏。

        抽成方法是为了让**两条返回路径都过这一关**（见调用处的 [WARN]）。
        """
        if out.get("v3_enabled"):
            out["v3_users"] = self._resolve_v3_users(v3_users_raw)
        else:
            out["v3_users"] = {}
        return out

    def _iter_snmp_payloads(self):
        """遍历凭据库里启用中的凭据，逐个产出解密后的 payload dict（坏行跳过）。

        为何要抽出来而不是在两处各写一遍：community 门（v1/v2c）与 USM 用户表
        （v3）读的是同一份凭据库。两段逻辑若各写一份，必然在「什么样的行算坏行」
        上漂移 —— 一边记日志一边不记、一边 strip 一边不 strip。届时同一份凭据库
        在两道门下给出不同答案，而这种不一致**没有单点可以断言**：单测各自绿，
        真机第一包才暴露。

        失败语义刻意分两层，不能合并：
        - **整体失败**（DB 不可达 / 依赖不可用）→ warning 一次，退化为空迭代。
          trapd 继续跑，只是回退源没了（不该因为读不到凭据就把收包线程搞死）。
        - **单行失败**（该条解密不了 / 不是 JSON 对象）→ debug 一条，跳过该行。
          一条凭据坏了不该让其它凭据一起失效。
        """
        try:
            from app.models.monitor_credential import MonitorCredential
            from app.utils.security.encryption import decrypt

            with self.app.app_context():
                rows = MonitorCredential.query.filter_by(enabled=True).all()
        except Exception:
            logger.warning("[trapd] 回退读取凭据库失败", exc_info=True)
            return
        for cred in rows:
            try:
                payload = json.loads(decrypt(cred.encrypted_payload))
            except Exception:  # noqa: BLE001 -- 单条凭据解密失败只跳过该条，不得影响其余凭据
                logger.debug("监控凭证解密失败，跳过 credential_id=%s", getattr(cred, "id", "?"))
                continue
            if not isinstance(payload, dict):
                logger.debug("监控凭证 payload 非 JSON 对象，跳过 credential_id=%s", getattr(cred, "id", "?"))
                continue
            yield payload

    def _communities_from_credentials(self) -> list:
        """回退源：凭据库里全部启用凭据的 SNMP v2c community。

        trap 的 community 就是设备侧 `snmp-server host` 配的那个，本来就在凭据库
        里（加密存储、默认不回显）。未显式配 TRAPD_COMMUNITIES 时回退到这里，
        使「一键开启」不必先去 .env 手填凭据 —— 这是"开启步骤太多"的根因之一。

        [WARN] 本方法只看 ``community`` 键，**不做版本过滤**：v3 凭据也可能带着
        遗留的 community 键，把它收进来对 v1/v2c 门无害（设备不会用它发 v3 包），
        而一旦过滤就要在 trapd 里再实现一份"什么算 v2c 凭据"的判断 —— 那正是
        本文件不该有的第二套解释。版本语义归 :class:`SnmpCredential`。
        """
        out = []
        for payload in self._iter_snmp_payloads():
            community = str(payload.get("community") or "").strip()
            if community:
                out.append(community)
        return out

    def _v3_users_from_credentials(self) -> dict:
        """回退源：凭据库里全部启用凭据的 SNMPv3 USM 用户表。

        Returns:
            ``{username: {auth_key, priv_key, auth_protocol, priv_protocol,
            security_level}}``

        键名与 ``security_level`` 的档位推导**都不在本文件重新实现**，一律走
        :class:`SnmpCredential`（多通道采集的权威源）。手写第二套就是 P0 缺陷 1
        的同型重演：两侧各自"看起来对"，直到真机第一包打进来才发现对不上 ——
        而那时现象是「v3 trap 全被拒」，日志却指向设备侧。

        同名用户以**后读到的为准**：凭据库不约束 username 唯一，取最后一条至少
        是确定性的；若取第一条，结果就取决于 DB 的行顺序，重启前后可能不同。
        """
        try:
            from app.services.collector.credentials.snmp_credential import SnmpCredential
        except Exception:
            logger.warning("[trapd] SNMPv3 用户表不可用（SnmpCredential 导入失败）", exc_info=True)
            return {}
        out: dict = {}
        for payload in self._iter_snmp_payloads():
            try:
                cred = SnmpCredential.from_payload(payload)
            except ValueError:
                logger.debug("[trapd] 跳过非 SNMP 或形状不合法的凭据")
                continue
            if cred.version != "v3":
                continue
            out[cred.username] = {
                "auth_key": cred.auth_key,
                "priv_key": cred.priv_key,
                "auth_protocol": cred.auth_protocol,
                "priv_protocol": cred.priv_protocol,
                "security_level": cred.security_level(),
            }
        return out

    def _resolve_v3_users(self, whitelist_raw: str) -> dict:
        """按 ``TRAPD_V3_USERS`` 白名单裁剪凭据库里的 v3 用户表；空 = 不限制。

        为何要留这一层（而不是直接用凭据库全集）：与 ``TRAPD_COMMUNITIES`` 同构
        —— 显式指定就只用指定的，不配才回退凭据库。v3 侧若没有对应的显式手段，
        运维想"只让某几台设备的 v3 用户进来"就只能改凭据库本身，而那是**全局**
        改动、会波及轮询采集。

        两种配错都会在**这里**说出来，而不是等到收包时表现为"v3 trap 全被拒"：
        - 白名单里的名字在凭据库没有 ⇒ warning（名字打错 / 凭据被停用）；
        - 凭据库有但被白名单排除 ⇒ info（属预期裁剪，不告警）。
        """
        users = self._v3_users_from_credentials()
        allowed = _split_list(whitelist_raw)
        if not allowed:
            return users
        allowed_set = set(allowed)
        missing = sorted(allowed_set - set(users))
        if missing:
            logger.warning(
                "[trapd] TRAPD_V3_USERS 中的用户名在凭据库里没有对应的启用 v3 凭据: %s"
                "（名字打错或该凭据已停用 —— 这些用户发的 trap 会被全部拒绝）",
                missing,
            )
        skipped = sorted(set(users) - allowed_set)
        if skipped:
            logger.info("[trapd] TRAPD_V3_USERS 白名单生效，凭据库中的 v3 用户被忽略: %s", skipped)
        return {name: entry for name, entry in users.items() if name in allowed_set}

    @staticmethod
    def _runtime_signature(cfg: dict, communities) -> tuple:
        """监听身份签名：签名变了才需要重启监听（配置热生效的判据）。

        [WARN] **两处调用点必须共用这一个构造**（``_start_recv`` 写、``_apply`` 比）。
        当初的设计文档只写了"两处都要改"，那是把负担留给后来者 —— 分开写必然
        漂移：一边加了新键一边没加 ⇒ 签名恒不等 ⇒ 每 10s 重启一次监听
        （"配置已变更"日志刷屏、端口反复闪断）；反过来若漏在"写"侧 ⇒ 签名恒等
        ⇒ 改了配置永远不生效。**两种症状都不报错**。

        v3 用户表进签名时取 ``sorted(...)`` 而非 dict 本身：dict 无序，同一份
        配置两次读出来顺序可能不同，会让签名无谓地变化。
        """
        return (
            cfg["port"],
            cfg["allowlist"],
            tuple(communities),
            cfg["allow_weak"],
            tuple(sorted(cfg["v3_users"])),
            cfg["v3_enabled"],
        )

    def _start_recv(self, cfg: dict) -> None:
        """按配置启动收包线程；配置不合法时**只记录不退出**（待机重试）。

        [WARN] 整个校验段必须被一把 ``try/except SystemExit`` 兜住，而不是给每条
        校验单独包一层：``_validate_communities`` / ``parse_source_allowlist`` /
        ``_build_ingest`` 三个入口**都会**抛 ``SystemExit`` 表达"配置非法"
        （它们原本是 fail-fast 的出口）。漏包任何一条，异常就会穿到 ``_apply()``
        → 穿到 ``run()`` 的监督循环 —— 而那里的注释写着"绝不能因单次异常退出"。
        实测（2026-09-28）：只包了 community 那条时，坏白名单/坏规则会让监督
        循环直接 ``SystemExit`` 退出线程，``_start_service`` 拿到 SystemExit
        而不是"拒绝监听"，且端口静默不可达。收成一束后新增校验路径不会再漏。
        """
        try:
            communities = _split_list(self.app.config.get("TRAPD_COMMUNITIES", ""))
            if not communities:
                communities = self._communities_from_credentials()
            self._validate_communities(communities, cfg["allow_weak"], cfg["v3_enabled"])
            allowlist = parse_source_allowlist(cfg["allowlist"])

            ingest = self._ingest
            if not self._ingest_injected:
                merged = dict(self.app.config)
                merged["TRAPD_RATE_LIMIT_PER_MINUTE"] = cfg["rate_limit"]
                ingest = self._build_ingest(merged)
        except SystemExit as exc:
            self._last_error = str(exc)
            logger.warning("[trapd] 暂未启动监听（配置不合法）: %s", exc)
            return

        self.communities = communities
        self.listen_port = cfg["port"]
        self.source_allowlist = allowlist
        self._ingest = ingest
        self.v3_enabled = cfg["v3_enabled"]
        self.v3_users = cfg["v3_users"]
        if self.v3_enabled and not self.v3_users:
            logger.warning(
                "[trapd] v3 已开启但用户表为空（凭据库无启用的 SNMPv3 凭据，或 "
                "TRAPD_V3_USERS 白名单把全都裁掉了）：所有 v3 报文会以 unknown_user 被拒"
            )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        try:
            sock.bind((self.listen_address, self.listen_port))
        except OSError as exc:
            sock.close()
            self._last_error = f"监听端口绑定失败（{self.listen_address}:{self.listen_port}）：{exc}"
            logger.warning("[trapd] 暂未启动监听（端口绑定失败）: %s", exc, exc_info=True)
            return
        self._sock = sock
        self._recv_thread = threading.Thread(
            target=self._recv_loop, args=(sock,), name="trapd-recv", daemon=True
        )
        self._recv_thread.start()
        self._runtime_sig = self._runtime_signature(cfg, communities)
        self._last_error = None
        logger.info(
            "[trapd] 监听已启动: %s:%s communities=%s 来源白名单=%s 限流=%s/分钟",
            self.listen_address, sock.getsockname()[1], len(communities),
            "已启用" if self.source_allowlist else "未启用", cfg["rate_limit"],
        )

    def _stop_recv(self) -> None:
        """停止收包：置关闭标志 + 关 socket，等收包线程退出。

        为什么要置 `_closing` 而不只靠 `sock.close()`：见 `_start_recv` 里
        `settimeout(0.5)` 处的说明 —— close() 不保证唤醒阻塞在 recvfrom 的线程。
        两道保险叠加：标志让轮询超时路径退出，close() 让 OSError 路径退出。
        """
        sock, thread = self._sock, self._recv_thread
        self._sock, self._recv_thread = None, None
        self._runtime_sig = None
        self._closing = True
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=5)
        self._closing = False
        logger.info("[trapd] 监听已停止（待机中，端口不再接收）")

    def _apply(self, cfg: dict) -> None:
        """让运行状态收敛到 cfg：开→监听（配置变则重启），关→待机。"""
        self._current_cfg = cfg
        if not cfg["enabled"]:
            if self._recv_thread is not None:
                self._stop_recv()
            return
        sig = self._runtime_signature(cfg, self.communities)
        if self._recv_thread is not None and sig != self._runtime_sig:
            logger.info("[trapd] 配置已变更，重启监听: %s → %s", self._runtime_sig, sig)
            self._stop_recv()
        if self._recv_thread is None:
            self._start_recv(cfg)

    def _validate_communities(self, communities, allow_weak: bool,
                              v3_enabled: bool = False) -> None:
        """community 是 SNMPv1/v2c 的**唯一**凭据，配置不当等于不设防 → 拒绝启动。

        原实现的默认值 ``public`` 是知名公开凭据，配合默认监听 ``0.0.0.0`` 与
        缺失的源校验，使「伪造设备 IP + 发 linkDown」即可投毒告警箱。
        注意：这里**不再**用 SystemExit 直接退出进程 —— 常驻待机模型下，
        配置不合法只应阻止本轮监听（由 _start_recv 捕获并记录）。

        ``v3_enabled``（默认 **False** = 保守/fail-close）决定是否容忍空 community
        集合 —— 这是 ops 文档 §7.3 待改造点 3「v3-only 部署不该因无 community 拒启」：

        - **空集合 + v3 开**：放行并告警。此时 v1/v2c 门是**恒拒**的（``community
          not in ()`` 永真，见 ``_recv_loop``），端口并不"不设防"，只是退化成
          v3-only；拒启则把纯 v3 现场彻底堵死 —— 现场（id=17 的凭据是
          ``version=v3``、无 community 键）实测正是被这条卡住：开了总开关、
          端口却永远不监听，日志只有一句「未找到可用的 SNMP community」，
          与"还没配凭据"的表现完全同形。
        - **空集合 + v3 关**：维持原 SystemExit —— 没有任何可用凭据时开端口
          才真的是不设防。
        """
        if not communities:
            if v3_enabled:
                logger.warning(
                    "[trapd] 未找到任何 SNMP community（TRAPD_COMMUNITIES 为空且凭据库"
                    "无启用中的 v2c 凭据），以 **v3-only** 模式监听：v1/v2c 报文将被"
                    "全部拒绝。需同时接收 v2c trap 请配置 community"
                )
                return
            raise SystemExit(
                "未找到可用的 SNMP community：凭据库里没有启用中的 SNMP 凭据，"
                "且未配置 TRAPD_COMMUNITIES。SNMPv1/v2c 的 community 是唯一凭据，"
                "留空等于不设防。"
            )
        weak = sorted({c for c in communities if c.lower() in _WEAK_COMMUNITIES})
        if weak and not allow_weak:
            raise SystemExit(
                f"TRAPD_COMMUNITIES 含知名默认值 {weak}：这是公开凭据，任何能到达本端口"
                f"的主体都可伪造 trap。请改用强随机口令；确需在隔离环境保留，"
                f"请显式设 TRAPD_ALLOW_WEAK_COMMUNITY=true。"
            )

    def _source_allowed(self, source_ip: str) -> bool:
        """源 IP 是否在白名单内（未配置白名单时恒 True）。"""
        if self.source_allowlist is None:
            return True
        try:
            addr = ipaddress.ip_address(source_ip)
        except ValueError:
            return False
        return any(addr in net for net in self.source_allowlist)

    @staticmethod
    def _build_ingest(cfg):
        from app.services.monitoring.trap_receiver_service import (
            TrapIngressService,
            TrapRateLimiter,
        )
        from app.services.monitoring.trap_rule_service import (
            TrapRuleError,
            TrapRuleMatcher,
            parse_custom_rules,
        )

        try:
            custom = parse_custom_rules(cfg.get("TRAP_CUSTOM_RULES", ""))
        except TrapRuleError as exc:
            raise SystemExit(f"TRAP_CUSTOM_RULES 解析失败: {exc}") from exc
        matcher = TrapRuleMatcher(custom_rules=custom)
        limiter = TrapRateLimiter(int(cfg.get("TRAPD_RATE_LIMIT_PER_MINUTE", 120)))
        return TrapIngressService(matcher=matcher, rate_limiter=limiter)


    @staticmethod
    def _is_v3(decoded: dict) -> bool:
        """解码结果是否为 SNMPv3。

        两个键都认：``decode_v3_trap`` 同时写 ``version`` 与 ``snmp_version``，
        而测试夹具注入的 decode_fn 可能只给一个。判据取「任一为 v3」而不是
        「两者都为 v3」—— 缺键是常态（v1/v2c 出口只有 ``version``），要求两者
        齐全会让"只写了别名的 v3 出口"被当成 v2c 送进 community 门。
        """
        return str(decoded.get("snmp_version") or decoded.get("version") or "") == "v3"

    def _decode_packet(self, data: bytes) -> tuple[dict | None, str | None]:
        """版本分派：v3 走 USM 解码器，其余走 v1/v2c 解码器。

        **v3 关闭时零改动** —— 不 import v3 解码器、不碰用户表，与步 5 之前
        逐字同行为（``_recv_loop`` 只调 ``self._decode``）。

        Returns:
            ``(decoded, v3_reject_reason)``。第二个值非 ``None`` 表示**已确认**
            这是 v3 报文、但被某道门（未知用户 / secLevel 不符 / HMAC 失败 /
            解密失败）拒收；此时第一个值恒为 ``None``，且**不回落**到 v1/v2c ——
            回落只会让 v2c 解码器同样失败，最终被 ``_recv_loop`` 记成「无法解码
            的报文（非 SNMP trap？）」，而那条日志会把排障引向"设备没配 trap"，
            真因却是鉴权失败/用户表没这个人。这正是 P0 缺陷 1 的同型陷阱：
            现象正确、归因错误。区分手段是 ``on_reject`` —— 解码器只在**已经
            确认报文是 v3 且走 USM** 之后才会回调它。
        """
        if not self.v3_enabled:
            return self._decode(data), None

        from app.services.monitoring.trap_v3_decoder import decode_v3_trap

        rejected: list = []

        def _on_reject(reason: str, info: dict) -> None:
            rejected.append(reason)
            logger.warning("[trapd] v3 报文被拒: reason=%s info=%s", reason, info)

        decoded = decode_v3_trap(data, self.v3_users, on_reject=_on_reject)
        if decoded is not None:
            return decoded, None
        if rejected:
            return None, rejected[0]
        return self._decode(data), None

    def _recv_loop(self, sock: socket.socket):
        """收包线程：阻塞 recvfrom，解码入队。**任何单条失败都只丢该条，绝不终止循环。**

        socket 由 `_start_recv` 创建后传入（不再在循环内自建）：热开关需要能从
        监督循环里关闭它来让本线程退出，故 socket 的属主是 TrapdService 而非本函数。
        """
        if self.listen_address in _WILDCARD_ADDRESSES and self.source_allowlist is None:
            logger.warning(
                "[trapd] 监听 %s 且未配置 TRAPD_SOURCE_ALLOWLIST：UDP 源 IP 可被伪造，"
                "而设备关联按源 IP 反查，存在伪造 trap 投毒告警的风险。"
                "建议用 TRAPD_SOURCE_ALLOWLIST 限定为管理网段（如 10.0.0.0/8）。",
                self.listen_address,
            )
        while not self._closing:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break  # socket 已被关闭（进程退出或热开关关闭监听）
            if not self._source_allowed(addr[0]):
                self._rejected_source_count += 1
                if self._rejected_source_count % 100 == 1:
                    logger.warning(
                        "[trapd] 源 IP 不在白名单内，丢弃（from=%s，累计 %s 条）",
                        addr[0], self._rejected_source_count,
                    )
                continue
            try:
                decoded, v3_reject = self._decode_packet(data)
            except Exception:
                self._decode_error_count += 1
                if self._decode_error_count % 100 == 1:
                    logger.exception(
                        "[trapd] 报文解码异常，丢弃该条（from=%s size=%s，累计 %s 条）",
                        addr[0], len(data), self._decode_error_count,
                    )
                continue
            if decoded is None:
                if v3_reject is not None:
                    self._v3_rejected_count += 1
                else:
                    logger.warning(
                        "[trapd] 无法解码的报文（非 SNMP trap？）: from=%s size=%s",
                        addr[0], len(data),
                    )
                continue
            if not self._is_v3(decoded) and decoded["community"] not in self.communities:
                logger.warning(
                    "[trapd] community 校验失败，拒绝: from=%s community=%s",
                    addr[0], decoded["community"],
                )
                continue
            item = {"source_ip": addr[0], **decoded}
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self._dropped_count += 1
                if self._dropped_count % 100 == 1:
                    logger.warning(
                        "[trapd] 接收队列已满，累计丢弃 %s 条 trap（worker 处理不过来）",
                        self._dropped_count,
                    )


    _STOP_SENTINEL = object()

    def _process_queue(self):
        while True:
            item = self._queue.get()
            try:
                if item is self._STOP_SENTINEL:
                    return
                with self.app.app_context():
                    self._ingest.handle_trap(
                        source_ip=item["source_ip"],
                        snmp_version=item["version"],
                        community=item["community"],
                        trap_oid=item["trap_oid"],
                        varbinds=item["varbinds"],
                    )
            except Exception:
                logger.exception("[trapd] trap 处理异常（跳过该条）")
                try:
                    from extensions import db
                    db.session.rollback()
                except Exception:  # noqa: BLE001, S110 - 上方 logger.exception 已留痕，此处仅尽力回滚
                    pass
            finally:
                self._queue.task_done()

    def _stop_worker(self) -> None:
        """放哨兵并等 worker 退出；队列满（极端 storm）时退化为 daemon 丢弃。"""
        worker = self._worker_thread
        self._worker_thread = None
        if worker is None:
            return
        try:
            self._queue.put_nowait(self._STOP_SENTINEL)
        except queue.Full:
            logger.warning("[trapd] 停机时队列已满，worker 未走优雅退出路径")
            return
        worker.join(timeout=5)
        if worker.is_alive():
            logger.warning("[trapd] worker 未在 5s 内退出（仍在处理积压 trap）")

    POLL_INTERVAL_SECONDS = 10

    def request_stop(self) -> None:
        """请求退出常驻循环并停止监听（幂等；供测试/优雅退出使用）。"""
        self._stopping = True

    def run(self) -> None:
        """常驻监督循环：按动态配置启停监听，阻塞至进程被停止。

        为什么是「常驻 + 热读」而不是「未启用即退出」：
        原先 `TRAPD_ENABLED=false` 走 SystemExit(退出码 1) → systemd 判为崩溃 →
        `Restart=on-failure` 每 10s 重启一轮（每轮完整初始化 Flask 应用，实测
        6.4s CPU + 几十行日志），撞 StartLimitBurst=5 才停。而「功能关闭」是
        **预期状态**，不该用进程失败来表达 —— 那正是「服务看起来一直坏着」的根因。
        """
        worker = threading.Thread(target=self._process_queue, name="trapd-worker", daemon=True)
        self._worker_thread = worker
        worker.start()
        logger.info("[trapd] worker 线程已启动（常驻监督中，开关由动态配置驱动）")
        while not self._stopping:
            cfg = self._runtime_config()
            try:
                self._apply(cfg)
            except Exception:
                logger.exception("[trapd] 应用运行时配置失败，将在下个周期重试")
            for _ in range(int(self.POLL_INTERVAL_SECONDS / 0.2)):
                if self._stopping:
                    break
                time.sleep(0.2)
        if self._recv_thread is not None:
            self._stop_recv()
        self._stop_worker()
        logger.info("[trapd] 监督循环已退出")


def main() -> None:
    config_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv("FLASK_ENV", "production")
    from app.services.monitoring.standalone_service import create_headless_monitor_app

    logger.info("启动 SNMP Trap 接收服务（environment=%s）", config_name)
    app = create_headless_monitor_app(config_name)
    TrapdService(app).run()


if __name__ == "__main__":
    main()
