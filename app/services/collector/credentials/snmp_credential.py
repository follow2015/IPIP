# -*- coding: utf-8 -*-
"""多通道采集 · SNMP 凭据值对象与通道层自有凭据读取器（T0.6 / G9）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` 决策 4、§3.5。

三道防 v3→v2c 静默降级的闸（T-V3-1）：

1. ``SnmpCredential.__post_init__``：version 白名单 + v2c 缺 community 报错 +
   v3 缺 username 报错 + v3 协议名不在自持值域报错（T-V3-2，明确报错而非
   ``_build_snmp_cred`` 的 warning 后静默降级）。
2. ``to_adapter_payload()`` 的 payload 必带 ``"version"`` 键 —— 与
   ``snmp_adapter._resolve_snmp_version``（snmp_adapter.py:145-156）「键存在即采用
   其值」的语义对齐：键必然存在，缺省回退 v2c 的分支**永远走不到**。
3. 协议值域自持（OD-1 总监裁决：不改监控侧）：与 ``_build_snmp_cred`` 内
   ``_auth_map`` / ``_priv_map`` 键集合**值域对齐**，一致性由 AST 漂移守卫单测
   盯住（不 import 监控侧私有函数）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.utils.logging import get_logger
from app.utils.security.encryption import decrypt

logger = get_logger(__name__)


class SnmpCredentialError(RuntimeError):
    """凭据**获取/解析**失败的统一异常（T0.9 异常收窄）。

    覆盖两类运行期失败：无 app context、解密/解析失败。落到
    ``meta["errors"][cap]["code"]`` 时类名可与其它运行期故障区分。

    「设备未配置 SNMP 凭据」**不是**失败 —— provider.get 以 None 表达，
    语义由调用方决定（``SnmpChannel`` 落 FAILED 并写明原因）。
    """

SNMP_AUTH_PROTOCOLS: frozenset[str] = frozenset(
    {"sha", "sha224", "sha256", "sha384", "sha512", "md5", "none"}
)

SNMP_PRIV_PROTOCOLS: frozenset[str] = frozenset(
    {"aes", "aes192", "aes256", "des", "3des", "none"}
)

_PAYLOAD_VERSION_KEY = "snmp_version"


@dataclass(frozen=True)
class SnmpCredential:
    """SNMP 凭据值对象。

    ``version`` 是**必填显式字段**（唯一入口，不允许缺省）；``SnmpChannel`` 不接受
    裸 dict，只接受本对象（规格决策 4）。
    """

    version: str
    community: str | None = None      # 仅 v2c
    username: str | None = None       # 仅 v3
    auth_key: str | None = None       # 仅 v3
    priv_key: str | None = None       # 仅 v3
    auth_protocol: str = "sha"        # 仅 v3
    priv_protocol: str = "aes"        # 仅 v3

    def __post_init__(self) -> None:
        if self.version not in ("v2c", "v3"):
            raise ValueError(f"不支持的 SNMP version: {self.version!r}（只允许 v2c / v3）")
        if self.version == "v2c":
            if not self.community:
                raise ValueError("v2c 凭据缺少 community")
            return
        if not self.username:
            raise ValueError("v3 凭据缺少 username")
        auth = (self.auth_protocol or "").strip().lower()
        if auth not in SNMP_AUTH_PROTOCOLS:
            raise ValueError(f"不支持的 SNMP v3 auth_protocol: {self.auth_protocol!r}")
        priv = (self.priv_protocol or "").strip().lower()
        if priv not in SNMP_PRIV_PROTOCOLS:
            raise ValueError(f"不支持的 SNMP v3 priv_protocol: {self.priv_protocol!r}")
        if auth != self.auth_protocol or priv != self.priv_protocol:
            object.__setattr__(self, "auth_protocol", auth)
            object.__setattr__(self, "priv_protocol", priv)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SnmpCredential":
        """从加密 payload 的明文 dict 构造。

        payload 缺版本键时**报错**而不是回退 v2c：通道层不猜测。

        [WARN] 兼容归一（2026-10-05）：存量凭据（设备详情页凭据 Tab 等入口）曾以
        ``version`` 键名提交（键名漂移，已在前端统一为 ``snmp_version``），且存在
        ``version=None`` 的行 —— 这里兼容读取旧键；两个键都缺才报错。
        """
        version = payload.get(_PAYLOAD_VERSION_KEY) or payload.get("version")
        if not version:
            raise ValueError(
                f"SNMP 凭据 payload 缺少 {_PAYLOAD_VERSION_KEY} 键，通道层不猜测协议版本"
            )
        return cls(
            version=str(version),
            community=payload.get("community"),
            username=payload.get("username"),
            auth_key=payload.get("auth_key"),
            priv_key=payload.get("priv_key"),
            auth_protocol=payload.get("auth_protocol") or "sha",
            priv_protocol=payload.get("priv_protocol") or "aes",
        )

    def to_adapter_payload(self) -> tuple[dict[str, Any], str]:
        """返回 ``(payload, version)``。

        payload 必带 ``"version"`` 键：与 ``_resolve_snmp_version`` 的「键存在即采用
        其值」语义对齐 —— 因为键必然存在，v3 凭据不可能被静默降级为 v2c。
        """
        payload: dict[str, Any] = {"version": self.version}
        if self.version == "v2c":
            payload["community"] = self.community
        else:
            payload.update(
                {
                    "snmp_version": self.version,
                    "username": self.username,
                    "auth_key": self.auth_key,
                    "priv_key": self.priv_key,
                    "auth_protocol": self.auth_protocol,
                    "priv_protocol": self.priv_protocol,
                }
            )
        return payload, self.version

    def security_level(self) -> str:
        """``authPriv`` / ``authNoPriv`` / ``noAuthNoPriv``（v3），v2c 恒 ``"v2c"``。"""
        if self.version == "v2c":
            return "v2c"
        if self.auth_key and self.priv_key:
            return "authPriv"
        if self.auth_key:
            return "authNoPriv"
        return "noAuthNoPriv"

    def audit_info(self) -> dict[str, str]:
        """``meta["snmp_security"]`` 的形状：记录协议名原值与安全级别，供审计追溯。"""
        return {
            "version": self.version,
            "security_level": self.security_level(),
            "auth_protocol": self.auth_protocol if self.version == "v3" else None,
            "priv_protocol": self.priv_protocol if self.version == "v3" else None,
        }


class SnmpCredentialProvider:
    """通道层自有凭据读取器（规格决策 4：凭据由通道层自取，不经 ``credential_service``）。

    - 只认 ``monitor_credentials``（``protocol="snmp"``，经 device_monitor_credentials
      多对多关联设备）；**禁止** import ``app.services.monitoring.credential_service``（L2）。
    - 短事务：SELECT + 解密后**立即 commit** 再返回明文（P0-MDL：SNMP 探测可持续
      分钟级，凭据事务横跨探测期会持有 monitor_credentials 的共享 MDL，令该表
      DDL 拿不到排他锁 —— 复刻 ``credential_service.get_decrypted`` 的教训）。
    - 必须在 Flask app context 内调用；**无 context 抛 ``RuntimeError`` 明确报错，
      不得静默返回 None**（F1 / T0.9 对齐）。
    """

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo

    def _ensure_repo(self):
        if self._repo is None:
            from app.persistence.monitor_credential_repository import (
                MonitorCredentialRepository,
            )

            self._repo = MonitorCredentialRepository()
        return self._repo

    def get(self, device_id: int) -> SnmpCredential | None:
        """读取设备启用的 SNMP 凭据并解密为 ``SnmpCredential``；未配置返回 None。"""
        from flask import has_app_context

        if not has_app_context():
            raise SnmpCredentialError(
                "SnmpCredentialProvider.get 必须在 Flask app context 内调用："
                "无 context 时静默返回 None 会把『没配凭据』与『取不到凭据』混为一谈"
            )
        repo = self._ensure_repo()
        try:
            cred = repo.find_enabled(device_id, "snmp")
            if cred is None:
                return None
            try:
                payload = json.loads(decrypt(cred.encrypted_payload))
            except Exception as exc:
                raise SnmpCredentialError(
                    f"设备 {device_id} 的 SNMP 凭据解密或解析失败"
                ) from exc
        finally:
            repo.session.commit()
        return SnmpCredential.from_payload(payload)


__all__ = [
    "SNMP_AUTH_PROTOCOLS",
    "SNMP_PRIV_PROTOCOLS",
    "SnmpCredential",
    "SnmpCredentialError",
    "SnmpCredentialProvider",
]
