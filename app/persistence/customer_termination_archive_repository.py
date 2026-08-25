# -*- coding: utf-8 -*-
"""客户终止存档 Repository。

提供 customer_termination_archive 表的数据访问方法。
列表查询对 pdf_blob 使用 defer，避免大字段 IO（见 §4.4.4 F2）。
"""
from typing import List, Optional

from sqlalchemy.orm import defer

from app.models.customer_termination_archive import CustomerTerminationArchive
from app.persistence.base import SQLAlchemyRepository
from extensions import db


class CustomerTerminationArchiveRepository(SQLAlchemyRepository):

    def __init__(self, session=None):
        super().__init__(CustomerTerminationArchive, session)

    def find_by_customer_id(self, customer_id: int) -> List[CustomerTerminationArchive]:
        return (
            db.session.query(CustomerTerminationArchive)
            .options(defer(CustomerTerminationArchive.pdf_blob))
            .filter_by(customer_id=customer_id)
            .order_by(CustomerTerminationArchive.created_at.desc())
            .all()
        )

    def find_latest_by_customer_id(self, customer_id: int) -> Optional[CustomerTerminationArchive]:
        return (
            db.session.query(CustomerTerminationArchive)
            .filter_by(customer_id=customer_id)
            .order_by(CustomerTerminationArchive.created_at.desc())
            .first()
        )

    def find_by_id_with_blob(self, archive_id: int) -> Optional[CustomerTerminationArchive]:
        return (
            db.session.query(CustomerTerminationArchive)
            .filter_by(id=archive_id)
            .first()
        )
