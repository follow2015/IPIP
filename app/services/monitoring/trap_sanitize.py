# -*- coding: utf-8 -*-
"""SNMP Trap varbinds 脱敏（SNMPv3 支持 · 步 6）。

规格：``docs/design/trapd-SNMPv3支持-设计文档-20261006.md`` §4.5 / §9.2。

**只掩 2 项**（用户名 / 凭据标识），**显式保留 3 项**（源 IP / 线路 / 认证方式）。

保留那三项不是"漏做"，是拍板的设计决策 —— §4.5 给了三条理由，核心是：它们是
告警价值的全部（"谁、从哪条线、用什么方式登录了"）。掩掉之后告警只剩"有人登录
了"，运维无法判断是否异常 ⇒ 告警被忽略 ⇒ 引入等于没引入；更糟的是过度脱敏会逼
运维去设备侧直接查，反而绕过了告警链路（也就绕过了审计）。

两条刻意**不做**的事（§9.2）—— 都是"看起来更灵活、实则更危险"的设计：

- **不做成环境变量**：脱敏规则被误配成空表等于**静默关闭防护**，风险大于收益。
  改这张表应当是代码评审的事，不是运维配置的事。
- **不提供"完全关闭脱敏"开关**：开关一旦存在，就会有人在排障时打开它然后忘记
  关回来 —— 那时脱敏已名存实亡，而**没有任何红灯**会告诉你这件事。

原则：**OID 保留、值掩码**。规则匹配依赖 OID（把 OID 掩了规则就全瞎了），值只
用于展示与排障。
"""

_MASK = "***"

_SENSITIVE_OID_PREFIXES: tuple[str, ...] = (
    "1.3.6.1.4.1.2011.5.25.207.1.2.1.1.2",  # 用户名
    "1.3.6.1.4.1.2011.5.25.207.1.2.1.1.6",  # 凭据标识（实测已含明文 _public_）
)

_PRESERVED_OID_PREFIXES: tuple[str, ...] = (
    "1.3.6.1.4.1.2011.5.25.207.1.2.1.1.3",  # 源 IP —— 排障必需：不知道"谁在登"的告警是废告警
    "1.3.6.1.4.1.2011.5.25.207.1.2.1.1.4",  # 线路（VTY1…）
    "1.3.6.1.4.1.2011.5.25.207.1.2.1.1.5",  # 认证方式（aaa…）
)


def _matches_prefix(oid: str, prefix: str) -> bool:
    """OID 是否落在 ``prefix`` 之下 —— 按**弧段**比，不是按字符串前缀。

    [WARN] 写成 ``oid.startswith(prefix)`` 是错的：``"...1.1.2"`` 是
    ``"...1.1.20"`` 的**字符串**前缀，会把语义完全无关的另一个 OID 一并掩掉
    （华为这个族里确实存在 ``.1.1.20`` 一类的兄弟节点）。OID 是点分弧段树，
    判据必须是"等于 prefix"或"以 prefix + '.' 开头"。
    """
    return oid == prefix or oid.startswith(prefix + ".")


def _assert_tables_disjoint() -> None:
    """掩码表与保留表不得重叠 —— 重叠意味着策略自相矛盾（同一 OID 既要掩又要留）。

    **导入期**就跑，而不是等第一条 trap 进来：策略配错属于"代码写错了"，
    让它 fail-fast 远比让其在运行时静默挑一个分支执行要好。
    """
    for sensitive in _SENSITIVE_OID_PREFIXES:
        for preserved in _PRESERVED_OID_PREFIXES:
            if _matches_prefix(sensitive, preserved) or _matches_prefix(preserved, sensitive):
                raise ValueError(
                    f"脱敏策略自相矛盾：{sensitive} 与 {preserved} 落在同一弧段下，"
                    "同一条 varbind 既要掩码又要保留"
                )


_assert_tables_disjoint()


def sanitize_varbinds(varbinds) -> list[tuple[str, str]]:
    """按 OID 弧段前缀掩码敏感值；OID 本身与其余值原样返回。

    Args:
        varbinds: ``[(oid, value), ...]``，值可以是任意可被 ``str()`` 化的对象。
            传 ``None`` 得空列表（收包链路上"没有 varbinds"是合法状态）。

    Returns:
        同形状的**新**列表 —— 入参不被改动（调用方常把同一份 varbinds 同时
        喂给规则匹配与落库，就地改会让规则匹配看到掩码后的值）。

    不做的：**不**提供 enabled 开关、**不**读环境变量（理由见模块 docstring）。
    """
    out: list[tuple[str, str]] = []
    for oid, value in varbinds or ():
        oid_s = str(oid)
        if any(_matches_prefix(oid_s, prefix) for prefix in _SENSITIVE_OID_PREFIXES):
            out.append((oid_s, _MASK))
        else:
            out.append((oid_s, str(value)))
    return out


__all__ = ["sanitize_varbinds"]
