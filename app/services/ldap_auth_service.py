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
import re
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

        ldap3 = self._ldap3()
        server = self._make_server(ldap3)

        try:
            found = self._search_user(ldap3, server, username)
        except _Unreachable as exc:
            return LdapAuthResult(STATUS_UNREACHABLE, f"域控不可达：{exc}")
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
        use_ssl = url.lower().startswith("ldaps://")
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
        )

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
            if not conn.bind():
                detail = _describe(conn)
                if _result_is_invalid_credentials(conn):
                    raise _ServiceBindFailed(detail)
                raise _Unreachable(detail)
            return conn
        except (_Unreachable, _ServiceBindFailed):
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
            ok = conn.bind()
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
