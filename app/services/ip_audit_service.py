# -*- coding: utf-8 -*-
"""IP 审计服务

统一 IP 生命周期业务日志的读取与写入：

- 读取：把 ip_allocation_logs（归属变更 allocate/release）与 ip_ban_records
  （封禁/解封 ban/unban）合并为一条审计流，供审计页展示。
- 写入：只记录**人工**的归属变更（allocate/release）。封禁/解封由
  ip_ban_service 写入 ip_ban_records，本服务不重复写。

与 AuditLog（安全审计）的分工：审计页只做展示层合并，两套日志不互相写。
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.persistence.ip_audit_repository import IPAuditRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ROW_KEY_PREFIX = {"allocation": "alloc", "ban": "ban"}


def _create_audit_session() -> Session:
    """创建独立于业务事务的审计专用 session（照 AuditService.log 范式）

    本服务的写入发生在 on_commit 回调里——彼时业务事务已提交完毕，若再向
    db.session add+flush，这些行**没有任何后续 commit**（请求结束
    session.remove() 即回滚），审计记录会静默丢失。StaticPool 单连接的
    本地测试对丢失免疫（共享连接上未提交数据对本 session 可见），生产
    MySQL 独立连接下才会暴露。故绑定同 engine 的独立 Session 写完立即
    commit，与 AuditService.log 的既有纪律一致。
    """
    from extensions import db

    return Session(bind=db.engine, expire_on_commit=False)


def _parse_json(raw: Any) -> Optional[Any]:
    """解析 JSON 列

    原生 SQL 查询不走 ORM 类型处理器：MySQL 与 SQLite 都返回 JSON 文本，
    故在此统一反序列化。已是 dict/list 时直接返回（ORM 路径）。

    Args:
        raw: 原始值（str / bytes / dict / list / None）

    Returns:
        解析后的对象；解析失败或为 None 时返回 None
    """
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("IP审计 detail 解析失败，已按空处理: %r", raw)
        return None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    """把时间入参统一成 datetime（API 层传入的是 ISO 字符串）"""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning("IP审计时间参数格式非法，已忽略: %r", value)
            return None
    return None


def _isoformat(value: Any) -> Optional[str]:
    """把时间统一输出为 ISO 字符串

    MySQL 驱动返回 datetime，SQLite 原生查询返回 'YYYY-MM-DD HH:MM:SS.ffffff'
    字符串；统一成 ISO，保证前端拿到一致的形态。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).replace(" ", "T", 1)


class IPAuditService:
    """IP 审计服务"""

    def __init__(self, repo: IPAuditRepository):
        """初始化

        Args:
            repo: IP 审计 Repository
        """
        self.repo = repo

    def query_audit_logs(
        self,
        page: int = 1,
        per_page: int = 20,
        action: Optional[str] = None,
        ip_address: Optional[str] = None,
        room_id: Optional[int] = None,
        operator_id: Optional[int] = None,
        start_time: Any = None,
        end_time: Any = None,
    ) -> Dict[str, Any]:
        """合并查询 IP 审计日志（归属变更 + 封禁/解封）

        Args:
            page: 页码（从 1 开始）
            per_page: 每页条数（上限 100）
            action: 动作过滤（allocate/release/ban/unban）
            ip_address: IP 精确匹配
            room_id: 机房 ID
            operator_id: 操作人 ID
            start_time: 起始时间（datetime 或 ISO 字符串，含）
            end_time: 结束时间（datetime 或 ISO 字符串，含）

        Returns:
            Dict: {items: [DTO...], total, page, per_page}
        """
        rows, total = self.repo.query(
            action=action,
            ip_address=ip_address,
            room_id=room_id,
            operator_id=operator_id,
            start_time=_coerce_datetime(start_time),
            end_time=_coerce_datetime(end_time),
            page=page,
            per_page=per_page,
        )

        items = [self._to_dto(row) for row in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    def record_allocation(
        self,
        ip_address: str,
        room_id: int,
        action: str,
        operator_id: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """记录单条 IP 归属变更（best-effort，失败绝不阻断业务）

        Args:
            ip_address: IP 地址
            room_id: 机房 ID
            action: allocate / release
            operator_id: 操作人；不传则取当前登录用户，取不到则跳过留痕
            detail: 附加信息（客户快照等）

        Returns:
            日志对象；无操作人或写入失败时返回 None
        """
        operator_id = self._resolve_operator(operator_id)
        if operator_id is None:
            logger.warning(
                "无操作人上下文，跳过IP归属审计留痕: ip=%s action=%s", ip_address, action,
            )
            return None

        session = _create_audit_session()
        try:
            repo = IPAuditRepository(session=session)
            log = repo.insert_allocation({
                "ip_address": ip_address,
                "room_id": room_id,
                "action": action,
                "operator_id": operator_id,
                "detail": detail,
            })
            session.commit()
            return log
        except Exception:  # noqa: BLE001 - 审计留痕失败不能阻断 IP 业务操作
            session.rollback()
            logger.exception("IP归属审计留痕失败（不影响业务）: ip=%s", ip_address)
            return None
        finally:
            session.close()

    def record_allocation_batch(
        self,
        entries: List[Dict[str, Any]],
        operator_id: Optional[int] = None,
        batch_id: Optional[str] = None,
    ) -> int:
        """批量记录 IP 归属变更（best-effort，一次 flush）

        网段级分配一次可能涉及数千个 IP，逐条 insert 会显著拉长事务。

        Args:
            entries: [{"ip_address", "room_id", "action", "detail"?}, ...]
            operator_id: 操作人；不传则取当前登录用户，取不到则跳过留痕
            batch_id: 批次号；不传则自动生成，同批共享以追溯同一次操作

        Returns:
            int: 写入条数；无操作人、空列表或写入失败时返回 0
        """
        operator_id = self._resolve_operator(operator_id)
        if operator_id is None:
            logger.warning("无操作人上下文，跳过 %d 条IP归属审计留痕", len(entries))
            return 0
        if not entries:
            return 0

        batch_id = batch_id or uuid.uuid4().hex
        rows = []
        for entry in entries:
            detail = dict(entry.get("detail") or {})
            detail["batch_id"] = batch_id
            rows.append({
                "ip_address": entry["ip_address"],
                "room_id": entry["room_id"],
                "action": entry["action"],
                "operator_id": operator_id,
                "detail": detail,
            })

        session = _create_audit_session()
        try:
            repo = IPAuditRepository(session=session)
            count = repo.bulk_insert_allocations(rows)
            session.commit()
            return count
        except Exception:  # noqa: BLE001 - 审计留痕失败不能阻断 IP 业务操作
            session.rollback()
            logger.exception("IP归属审计批量留痕失败（不影响业务），共 %d 条", len(rows))
            return 0
        finally:
            session.close()

    @staticmethod
    def _resolve_operator(operator_id: Optional[int]) -> Optional[int]:
        """确定操作人：显式传入优先，否则取当前登录用户

        无请求上下文时（Celery / 定时任务 / 系统扫描）get_current_user_id()
        取不到人，且无 app context 时访问 flask.g 会抛异常——两种情况统一
        返回 None，由调用方跳过留痕。这是「只记人工操作」的结构性保证。
        """
        if operator_id is not None:
            return operator_id
        try:
            from app.utils.auth import get_current_user_id

            return get_current_user_id()
        except Exception:  # noqa: BLE001 - 无 app context 时 g 访问会抛异常
            return None

    @staticmethod
    def load_customer_names(customer_ids) -> Dict[int, str]:
        """批量加载客户名称快照（审计 detail 专用）

        名称写进审计 detail 属于快照语义：客户改名后历史记录仍保留当时的
        名称，且查询侧无需 join。

        Args:
            customer_ids: 客户 ID 集合（可含 None，会被忽略）

        Returns:
            Dict[int, str]: 客户ID → 客户名称
        """
        from app.persistence.customer_repository import CustomerRepository

        ids = {cid for cid in customer_ids if cid is not None}
        if not ids:
            return {}
        repo = CustomerRepository()
        model = repo.model_class
        rows = repo.session.query(model.id, model.customer_name).filter(
            model.id.in_(ids),
        ).all()
        return {r.id: r.customer_name for r in rows}

    def _to_dto(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """把一行 UNION 结果转换为统一 DTO

        两表字段不对齐（归属侧有客户信息、封禁侧有 ban_mode/switch_id），
        缺失侧一律置 None，保证前端拿到稳定的形状。

        Args:
            row: Repository 返回的原始行

        Returns:
            Dict: 统一 DTO
        """
        source = row.get("source")
        detail = _parse_json(row.get("payload"))
        is_allocation = source == "allocation"
        customer = detail if (is_allocation and isinstance(detail, dict)) else {}

        return {
            "id": f"{_ROW_KEY_PREFIX.get(source, source)}:{row.get('id')}",
            "source": source,
            "ip_address": row.get("ip_address"),
            "room_id": row.get("room_id"),
            "action": row.get("action"),
            "operator_id": row.get("operator_id"),
            "customer_id": customer.get("customer_id"),
            "customer_name": customer.get("customer_name"),
            "ban_mode": row.get("ban_mode"),
            "switch_id": row.get("switch_id"),
            "detail": detail,
            "created_at": _isoformat(row.get("created_at")),
        }
