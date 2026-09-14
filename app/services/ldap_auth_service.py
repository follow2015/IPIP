# -*- coding: utf-8 -*-
"""LDAP/AD 只读透传 Bind 认证服务（T3.3）。

铁律（与 config.LDAP_* 的注释一致）：
- **只做透传 Bind**：用「用户当次登录输入的密码」去域控校验，不缓存、不落库、
  不做任何形式的密码同步。本模块任何日志路径都不得出现密码。
- **失败原因必须可区分**：域控不可达 / 凭据错误 / 用户不存在 对应三种完全不同的
  运维动作（查网络与端口 / 让用户重输 / 核对账号与过滤器），混为一谈会把排查引向
  错误方向。因此返回值用 ``status`` 显式区分，调用方**不得只判 True/False**。
  注意分工：服务层区分是为了日志与运维定位；入口层（T3.4）对终端用户的提示应统一
  话术，避免「用户不存在 / 密码错误」的差异被用来做用户名枚举。

为什么不用长连接池：
  本服务在 gunicorn 多线程 worker 内被调用，跨线程共享一个 ldap3 Connection 需要
  额外加锁，且其重连语义脆弱（半开连接难判）。LDAP 对短连接的承受力足够，且每次
  调用都有 connect/receive 超时上界。故刻意为「每次调用一条短连接」，thread-safe
  由无共享可变状态保证。

依赖注入：
  ``ldap_module`` 可注入假的 ldap3（测试用），默认惰性 import 真实 ldap3。注入点
  刻意选在「库边界」——测试喂的是真实 AD 会返回的响应形状（invalidCredentials 的
  data 子码、socket 异常），而不是自造的假目录结构。
"""
from __future__ import annotations

import logging
import os
import re
import ssl
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_USER_NOT_FOUND = "user_not_found"
STATUS_INVALID_CREDENTIALS = "invalid_credentials"
STATUS_UNREACHABLE = "unreachable"
STATUS_DISABLED = "disabled"          # AD：账号被禁用（data 533）
STATUS_LOCKED = "locked"              # AD：账号被锁定（data 775）
STATUS_AMBIGUOUS = "ambiguous"        # 过滤器命中多条，无法唯一定位
STATUS_LDAP_DISABLED = "ldap_disabled"  # 功能未开启
STATUS_MISCONFIGURED = "misconfigured"  # 已开启但配置不全 / 服务账号不可用

ALL_STATUSES = frozenset({
    STATUS_OK, STATUS_USER_NOT_FOUND, STATUS_INVALID_CREDENTIALS, STATUS_UNREACHABLE,
    STATUS_DISABLED, STATUS_LOCKED, STATUS_AMBIGUOUS, STATUS_LDAP_DISABLED,
    STATUS_MISCONFIGURED,
})

_AD_DATA_ACCOUNT_DISABLED = 533
_AD_DATA_ACCOUNT_LOCKED = 775

_NETWORK_EXC_NAMES = frozenset({
    "LDAPSocketOpenError", "LDAPSocketReceiveError", "LDAPSocketSendError",
    "LDAPConnectionError", "LDAPConnectError", "LDAPSocketConnectionError",
    "LDAPSocketsInactiveError",
})
_INVALID_CREDENTIALS_EXC_NAMES = frozenset({"LDAPInvalidCredentialsResult"})

_DEFAULT_ATTRS = ("displayName", "cn", "mail", "memberOf", "sAMAccountName", "uid")

_FILTER_SPECIALS = frozenset({"\\", "*", "(", ")", "\x00"})


def resolve_tls_policy(server: str, starttls: bool = False, ca_file: str = "",
                       allow_insecure: bool = False) -> str | None:
    """校验 LDAP 传输安全策略。返回**人类可读的错误描述**，``None`` = 通过。

    策略：**不允许明文传输凭据**。二选一：
      - ``ldaps://``（全程 TLS）
      - ``ldap://`` + ``LDAP_STARTTLS=true``（连接后立即协商升级）

    ``ldap://`` 且未开 StartTLS 时明确拒绝：那会把域控服务账号 Bind 口令与每个
    用户的登录口令**明文**暴露在内网上，ARP/DNS 劫持即可截获。
    同时校验 ``LDAP_CA_FILE`` 指向的文件真实存在 —— 路径写错若拖到登录时才由
    ldap3 抛错，表现是「所有人都登不上」，且日志里只有一行 SSL 配置异常。

    ``allow_insecure=True``（``LDAP_ALLOW_INSECURE_TRANSPORT``）**仅供联调**：给
    只有明文监听、尚未配 TLS 的试验目录用。此时不报错，但服务启动与每次认证都会
    记 WARNING，避免它被当成"生产可用配置"。

    抽成纯函数：``config._assert_ldap_config``（启动期 fail-fast）与
    ``ldap_config_check``（``flask ldap-check`` 上线自检）共用同一套判据，
    避免两处口径漂移。
    """
    url = (server or "").strip().lower()
    if not url:
        return "LDAP_SERVER 未配置"
    if url.startswith("ldaps://"):
        pass
    elif url.startswith("ldap://"):
        if not starttls and not allow_insecure:
            return (
                "LDAP_SERVER 为 ldap://（明文）且未启用 StartTLS：域控服务账号口令与"
                "用户登录口令将明文经过内网。请改用 ldaps://，或设 LDAP_STARTTLS=true"
                "（仅联调可用 LDAP_ALLOW_INSECURE_TRANSPORT=true，不建议）。"
            )
    else:
        return f"LDAP_SERVER 协议无法识别（应为 ldaps:// 或 ldap://）：{server}"

    if ca_file and not os.path.isfile(ca_file):
        return f"LDAP_CA_FILE 指向的文件不存在：{ca_file}"
    return None


def transport_is_plaintext(server: str, starttls: bool = False) -> bool:
    """最终生效的传输是否会明文发送凭据（供启动/认证期告警）。"""
    url = (server or "").strip().lower()
    return url.startswith("ldap://") and not starttls


def escape_filter_chars(value: str) -> str:
    """按 RFC 4515 转义过滤器特殊字符，避免用户名注入检索过滤器。

    例：``admin)(|(uid=*`` 必须变成字面量，而不是把过滤器提前闭合。
    非 ASCII 字符不做逐字节转义（用户名实践中为 ASCII；如需支持应改按 UTF-8
    逐字节 \\xx 转义）。
    """
    out = []
    for ch in value:
        if ch in _FILTER_SPECIALS:
            out.append("\\%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class LdapAuthResult:
    """一次 LDAP 认证的结果。``status`` 是唯一权威判据，``ok`` 只是便捷属性。"""

    status: str
    message: str = ""
    dn: str | None = None
    display_name: str | None = None
    email: str | None = None
    groups: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


class _Unreachable(Exception):
    """域控网络不可达（连接被拒/超时/半开）。"""


class _ServiceBindFailed(Exception):
    """服务账号 Bind 失败 —— 是配置问题，绝不可当成「用户密码错」。"""


class _TlsFailed(Exception):
    """TLS 协商或证书校验失败。

    刻意与 ``_Unreachable`` 区分：这属于**配置 / 信任链**问题（域控未开 StartTLS、
    CA 不匹配、证书过期），不是网络可达性问题。混为一谈会把运维引去查网络与端口。
    """


class LdapAuthService:
    """LDAP 认证服务（无状态；可安全跨线程复用实例）。"""

    def __init__(
        self,
        *,
        server: str = "",
        base_dn: str = "",
        bind_dn: str = "",
        bind_password: str = "",
        user_filter: str = "(sAMAccountName={username})",
        timeout: int = 5,
        enabled: bool = True,
        ldap_module: Any = None,
        user_attributes: tuple[str, ...] = _DEFAULT_ATTRS,
        starttls: bool = False,
        ca_file: str = "",
        allow_insecure_transport: bool = False,
    ) -> None:
        self.server_url = (server or "").strip()
        self.base_dn = (base_dn or "").strip()
        self.bind_dn = (bind_dn or "").strip()
        self.bind_password = bind_password or ""
        self.user_filter = user_filter or "(sAMAccountName={username})"
        self.timeout = max(1, int(timeout or 5))
        self.enabled = bool(enabled)
        self._ldap = ldap_module
        self._attrs = tuple(user_attributes)
        self.starttls = bool(starttls)
        self.ca_file = (ca_file or "").strip()
        self.allow_insecure_transport = bool(allow_insecure_transport)

    @property
    def _use_ssl(self) -> bool:
        return self.server_url.lower().startswith("ldaps://")

    @classmethod
    def from_config(cls, config: Any) -> "LdapAuthService":
        """从 Flask config（dict 或 Config 类）构造。"""

        def g(key: str, default: Any = "") -> Any:
            try:
                return config.get(key, default)  # type: ignore[union-attr]
            except AttributeError:
                return getattr(config, key, default)

        return cls(
            server=g("LDAP_SERVER"),
            base_dn=g("LDAP_BASE_DN"),
            bind_dn=g("LDAP_BIND_DN"),
            bind_password=g("LDAP_BIND_PASSWORD"),
            user_filter=g("LDAP_USER_FILTER", "(sAMAccountName={username})"),
            timeout=g("LDAP_TIMEOUT", 5),
            enabled=bool(g("LDAP_ENABLED", False)),
            starttls=bool(g("LDAP_STARTTLS", False)),
            ca_file=g("LDAP_CA_FILE", ""),
            allow_insecure_transport=bool(g("LDAP_ALLOW_INSECURE_TRANSPORT", False)),
        )

    def _ldap3(self) -> Any:
        if self._ldap is None:
            import ldap3  # 惰性 import：未启用 LDAP 的部署无须加载

            self._ldap = ldap3
        return self._ldap

    def is_ready(self) -> bool:
        """功能已开启且关键配置齐全。"""
        return bool(self.enabled and self.server_url and self.base_dn)

    def authenticate(self, username: str, password: str) -> LdapAuthResult:
        """校验一组凭据。永不抛业务异常，一切失败都映射为可区分的 status。"""
        if not self.is_ready():
            if not self.enabled:
                return LdapAuthResult(STATUS_LDAP_DISABLED, "LDAP 认证未启用")
            return LdapAuthResult(STATUS_MISCONFIGURED, "LDAP 配置不完整（缺 SERVER 或 BASE_DN）")

        username = (username or "").strip()
        if not username or not password:
            return LdapAuthResult(STATUS_INVALID_CREDENTIALS, "用户名或密码为空")

        policy_error = resolve_tls_policy(
            self.server_url, self.starttls, self.ca_file, self.allow_insecure_transport)
        if policy_error:
            logger.error("[ldap] 传输安全策略不满足，拒绝认证：%s", policy_error)
            return LdapAuthResult(
                STATUS_MISCONFIGURED, f"LDAP 传输安全策略不满足：{policy_error}")
        if transport_is_plaintext(self.server_url, self.starttls):
            logger.warning(
                "[ldap] 正在以**明文**传输域控凭据（%s）：LDAP_ALLOW_INSECURE_TRANSPORT "
                "仅限联调，生产必须改用 ldaps:// 或 StartTLS", self.server_url)

        ldap3 = self._ldap3()
        server = self._make_server(ldap3)

        try:
            found = self._search_user(ldap3, server, username)
        except _Unreachable as exc:
            return LdapAuthResult(STATUS_UNREACHABLE, f"域控不可达：{exc}")
        except _TlsFailed as exc:
            return LdapAuthResult(STATUS_MISCONFIGURED, f"TLS 协商/证书校验失败：{exc}")
        except _ServiceBindFailed as exc:
            return LdapAuthResult(STATUS_MISCONFIGURED, f"服务账号 Bind 失败：{exc}")

        if found is None:
            return LdapAuthResult(STATUS_USER_NOT_FOUND, f"目录中不存在用户 {username}")
        if found == "ambiguous":
            return LdapAuthResult(
                STATUS_AMBIGUOUS,
                "LDAP_USER_FILTER 命中多个条目，请收紧过滤器以避免认证到错误账号",
            )

        dn, attrs = found
        return self._bind_user(ldap3, server, username, dn, attrs, password)

    def _make_server(self, ldap3: Any):
        url = self.server_url
        use_ssl = self._use_ssl
        host = url.split("://", 1)[1] if "://" in url else url
        host = host.rstrip("/")
        if ":" in host and not host.startswith("["):
            hostname, _, port_s = host.rpartition(":")
            try:
                port = int(port_s)
            except ValueError:
                hostname, port = host, (636 if use_ssl else 389)
        else:
            hostname, port = host, (636 if use_ssl else 389)
        return ldap3.Server(
            hostname, port=port, use_ssl=use_ssl,
            connect_timeout=self.timeout, get_info=getattr(ldap3, "NONE", None),
            tls=self._make_tls(ldap3),
        )

    def _make_tls(self, ldap3: Any):
        """构造显式证书校验的 Tls 配置（``ca_file`` 留空则用系统信任库）。

        **必须显式传 validate**：ldap3 的 ``Tls`` 默认 ``ssl.CERT_NONE`` —— 不传
        等于连证书链都不验，``ldaps://`` 也挡不住中间人。

        残余风险（ldap3 2.9.1 的库内限制，已实测确认）：``Tls.wrap_socket`` 内部
        **无条件**执行 ``ssl_context.check_hostname = False``，且 ``Server`` 只接受
        ``Tls`` 对象、无法注入自带 SSLContext，故**主机名校验无法开启**。这意味着
        当信任锚是系统公共 CA 库时，持有任意受信 CA 签发证书者仍可 MITM。
        → 因此在企业场景**强烈建议**用 ``LDAP_CA_FILE`` 指向自家 CA 证书，把信任锚
        收窄到企业 CA；此时仅靠证书链校验已足够（攻击者需先拿到自家 CA 签发的证书）。
        """
        tls_cls = getattr(ldap3, "Tls", None)
        if tls_cls is None:
            return None
        kwargs: dict[str, Any] = {"validate": ssl.CERT_REQUIRED}
        if self.ca_file:
            kwargs["ca_certs_file"] = self.ca_file
        return tls_cls(**kwargs)

    def _start_tls_if_needed(self, conn: Any) -> None:
        """StartTLS：必须在 ``bind()`` **之前**调用。

        放在 bind 之后等于口令已明文发出、再升级也白做。``ldaps://`` 下不调用
        （连接本身就是 TLS，再协商 StartTLS 会被域控拒绝）。
        """
        if not (self.starttls and not self._use_ssl):
            return
        try:
            started = conn.start_tls()
        except Exception as exc:  # noqa: BLE001 - 统一归为配置/信任链问题
            raise _TlsFailed(str(exc) or type(exc).__name__) from exc
        if started is False:
            raise _TlsFailed(_describe(conn))

    def _connect_service(self, ldap3: Any, server: Any):
        """以服务账号（或匿名）连接，用于检索。失败抛 _Unreachable/_ServiceBindFailed。"""
        auth_simple = getattr(ldap3, "AUTH_SIMPLE", "SIMPLE")
        auth_anon = getattr(ldap3, "AUTH_ANONYMOUS", "ANONYMOUS")
        try:
            conn = ldap3.Connection(
                server,
                user=self.bind_dn or None,
                password=self.bind_password or None,
                authentication=auth_simple if self.bind_dn else auth_anon,
                receive_timeout=self.timeout,
            )
            self._start_tls_if_needed(conn)
            if not conn.bind():
                detail = _describe(conn)
                if _result_is_invalid_credentials(conn):
                    raise _ServiceBindFailed(detail)
                raise _Unreachable(detail)
            return conn
        except (_Unreachable, _ServiceBindFailed, _TlsFailed):
            raise
        except Exception as exc:  # noqa: BLE001 - 统一归类，避免异常类型外泄
            if _is_network_exc(exc):
                raise _Unreachable(str(exc)) from exc
            if _is_invalid_credentials_exc(exc):
                raise _ServiceBindFailed(str(exc)) from exc
            raise

    def _search_user(self, ldap3: Any, server: Any, username: str):
        search_filter = self.user_filter.replace("{username}", escape_filter_chars(username))
        conn = self._connect_service(ldap3, server)
        try:
            conn.search(
                search_base=self.base_dn,
                search_filter=search_filter,
                search_scope=getattr(ldap3, "SUBTREE", "SUBTREE"),
                attributes=list(self._attrs),
            )
            entries = list(conn.entries)
        except Exception as exc:  # noqa: BLE001
            if _is_network_exc(exc):
                raise _Unreachable(str(exc)) from exc
            raise
        finally:
            _safe_unbind(conn)

        if not entries:
            return None
        if len(entries) > 1:
            return "ambiguous"
        entry = entries[0]
        return str(getattr(entry, "entry_dn", "")) or None, _entry_attrs(entry)

    def _bind_user(
        self, ldap3: Any, server: Any, username: str, dn: str | None,
        attrs: dict[str, list[str]], password: str,
    ) -> LdapAuthResult:
        if not dn:
            return LdapAuthResult(
                STATUS_MISCONFIGURED, "目录条目缺少 DN，无法执行用户 Bind",
            )
        conn = None
        try:
            conn = ldap3.Connection(
                server, user=dn, password=password,
                authentication=getattr(ldap3, "AUTH_SIMPLE", "SIMPLE"),
                receive_timeout=self.timeout,
            )
            self._start_tls_if_needed(conn)
            ok = conn.bind()
        except _TlsFailed as exc:
            return LdapAuthResult(STATUS_MISCONFIGURED, f"TLS 协商/证书校验失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            if _is_network_exc(exc):
                return LdapAuthResult(STATUS_UNREACHABLE, f"域控不可达：{exc}")
            ad = _from_ad_data(_extract_data_code(exc), username)
            if ad is not None:
                return ad
            if _is_invalid_credentials_exc(exc):
                return LdapAuthResult(STATUS_INVALID_CREDENTIALS, "凭据错误")
            raise
        finally:
            _safe_unbind(conn)

        if ok:
            return LdapAuthResult(
                STATUS_OK, "", dn=dn,
                display_name=_first(attrs, "displayname", "cn"),
                email=_first(attrs, "mail"),
                groups=tuple(attrs.get("memberof", ())),
            )
        ad = _from_ad_data(_extract_data_code(conn), username)
        if ad is not None:
            return ad
        return LdapAuthResult(STATUS_INVALID_CREDENTIALS, "凭据错误")


def _mro_names(obj: Any) -> set[str]:
    return {c.__name__ for c in type(obj).__mro__}


def _is_network_exc(exc: Any) -> bool:
    return bool(_mro_names(exc) & _NETWORK_EXC_NAMES) or isinstance(exc, OSError)


def _is_invalid_credentials_exc(exc: Any) -> bool:
    return bool(exc is not None and (_mro_names(exc) & _INVALID_CREDENTIALS_EXC_NAMES))


def _result_exception(conn: Any) -> Any:
    return getattr(conn, "last_exception", None)


def _result_is_invalid_credentials(conn: Any) -> bool:
    """bind() 返回 False 时判定是否「凭据无效」。

    ldap3 默认 ``raise_exceptions=False``：Bind 失败不抛异常，只把描述写进
    ``conn.result``；部分版本则把异常留在 ``conn.last_exception``。两种都要认 ——
    否则「服务账号密码错」会被误判成「域控不可达」，把运维引去查网络。
    """
    result = getattr(conn, "result", None)
    if isinstance(result, dict):
        if "invalidcredential" in str(result.get("description") or "").lower():
            return True
        if "invalidcredential" in str(result.get("message") or "").lower():
            return True
    return _is_invalid_credentials_exc(getattr(conn, "last_exception", None))


def _describe(conn: Any) -> str:
    """把连接结果浓缩成一句可审计的说明（不含任何凭据）。"""
    result = getattr(conn, "result", None)
    if isinstance(result, dict):
        desc = result.get("description") or result.get("type") or ""
        msg = result.get("message") or ""
        return f"{desc} {msg}".strip() or "未知错误"
    exc = _result_exception(conn)
    return str(exc) if exc else "未知错误"


def _extract_data_code(obj: Any) -> int | None:
    """从结果/异常中取 AD 的 invalidCredentials data 子码。"""
    result = getattr(obj, "result", None)
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, int):
            return data
        match = re.search(r"data\s+(\d+)", str(result.get("message", "")))
        if match:
            return int(match.group(1))
    return None


def _from_ad_data(code: int | None, username: str) -> LdapAuthResult | None:
    if code == _AD_DATA_ACCOUNT_DISABLED:
        return LdapAuthResult(STATUS_DISABLED, f"账号 {username} 已被禁用")
    if code == _AD_DATA_ACCOUNT_LOCKED:
        return LdapAuthResult(STATUS_LOCKED, f"账号 {username} 已被锁定")
    return None


def _entry_attrs(entry: Any) -> dict[str, list[str]]:
    """把 ldap3 Entry 归一成 ``{小写属性名: [值, ...]}``。"""
    raw: dict[str, Any] = {}
    try:
        raw = dict(entry.entry_attributes_as_dict)
    except (AttributeError, TypeError):
        for name in _DEFAULT_ATTRS:
            attr = getattr(entry, name, None)
            if attr is None:
                continue
            raw[name] = getattr(attr, "value", attr)
    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        if value is None:
            out[str(key).lower()] = []
        elif isinstance(value, (list, tuple, set)):
            out[str(key).lower()] = [str(v) for v in value if v is not None]
        else:
            out[str(key).lower()] = [str(value)]
    return out


def _first(attrs: dict[str, list[str]], *names: str) -> str | None:
    for name in names:
        values = attrs.get(name)
        if values:
            return values[0]
    return None


def _safe_unbind(conn: Any) -> None:
    if conn is None:
        return
    try:
        conn.unbind()
    except Exception:  # noqa: BLE001 - 关闭失败不影响认证结论
        pass
