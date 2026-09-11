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
import os
import queue
import socket
import sys
import threading
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

_SNMP_TRAP_OID = "1.3.6.1.6.3.1.1.6.1"      # SNMPv2-MIB::snmpTrapOID.0
_V1_GENERIC_TRAP_BASE = "1.3.6.1.6.3.1.1.5"  # RFC 2576 翻译后的 generic trap 地址族


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
        trap_oid = ""
        varbinds = []
        for name, value in _v2c.apiTrapPDU.get_varbinds(pdu):
            name_s = str(name).strip(".")
            pretty = getattr(value, "prettyPrint", None)
            text = pretty() if callable(pretty) else str(value)
            varbinds.append((name_s, text))
            if name_s == _SNMP_TRAP_OID:
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
        if not cfg.get("TRAPD_ENABLED", False):
            raise SystemExit(
                "TRAPD_ENABLED=false：trapd 服务未启用。"
                "启用请设 TRAPD_ENABLED=true（或直接 systemctl disable --now ipip-trapd）"
            )
        self.listen_address = cfg.get("TRAPD_LISTEN_ADDRESS", "0.0.0.0")
        self.listen_port = int(cfg.get("TRAPD_LISTEN_PORT", 10162))
        self.communities = [
            c.strip() for c in str(cfg.get("TRAPD_COMMUNITIES", "public")).split(",") if c.strip()
        ]
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=int(cfg.get("TRAPD_QUEUE_SIZE", 1000)))
        self._decode = decode_fn or decode_trap_message
        self._ingest = ingest_service or self._build_ingest(cfg)
        self._dropped_count = 0
        self._sock: socket.socket | None = None

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


    def _recv_loop(self):
        """收包线程：阻塞 recvfrom，解码入队。单条失败只丢该条。"""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._sock.bind((self.listen_address, self.listen_port))
        logger.info(
            "[trapd] SNMP Trap UDP 监听已启动: %s:%s communities=%s",
            self.listen_address, self.listen_port, self.communities,
        )
        while True:
            try:
                data, addr = self._sock.recvfrom(65535)
            except OSError:
                break  # socket 关闭（进程退出）
            decoded = self._decode(data)
            if decoded is None:
                logger.warning(
                    "[trapd] 无法解码的报文（非 SNMP trap？）: from=%s size=%s",
                    addr[0], len(data),
                )
                continue
            if decoded["community"] not in self.communities:
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


    def _process_queue(self):
        while True:
            item = self._queue.get()
            try:
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
                except Exception:
                    pass
            finally:
                self._queue.task_done()

    def run(self) -> None:
        """启动 worker 与收包线程（阻塞至进程退出）。"""
        worker = threading.Thread(target=self._process_queue, name="trapd-worker", daemon=True)
        worker.start()
        logger.info("[trapd] worker 线程已启动")
        self._recv_loop()


def main() -> None:
    config_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv("FLASK_ENV", "production")
    from app.services.monitoring.standalone_service import create_headless_monitor_app

    logger.info("启动 SNMP Trap 接收服务（environment=%s）", config_name)
    app = create_headless_monitor_app(config_name)
    TrapdService(app).run()


if __name__ == "__main__":
    main()
