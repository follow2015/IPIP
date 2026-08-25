# -*- coding: utf-8 -*-
"""客户终止存档模型。

每次客户终止生成一条记录：
- summary_json 在终止事务内写入（释放前完整资源快照，与 get_customer_assets 返回同构）
- pdf_blob 在事务提交后由 on_commit 回调回填（失败则保留 None，可由
  POST /termination-archive/rebuild 凭 summary_json 重建）

详见 docs/CUSTOMER_TERMINATED_PLAN.md §4.4.4。
"""
from sqlalchemy import Column, Integer, String, JSON, LargeBinary, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class CustomerTerminationArchive(BaseModel):

    __tablename__ = "customer_termination_archive"
    __table_args__ = (
        Index("ix_cta_customer_created", "customer_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id = Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True, comment="客户ID")
    summary_json = Column(JSON, nullable=False, comment="释放前资源完整快照（与 get_customer_assets 同构）")
    pdf_blob = Column(LargeBinary(length=2**32 - 1), nullable=True, comment="PDF 二进制内容（LONGBLOB，事务外回填）")
    pdf_size = Column(Integer, nullable=True, comment="PDF 字节数，便于列表展示/告警")
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="终止操作人ID")
    reason = Column(String(255), nullable=True, comment="终止原因（可选，前端弹窗传入）")

    customer = relationship("Customer", lazy="joined")
    operator = relationship("User", lazy="joined")

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_relations=include_relations)
        data.pop("pdf_blob", None)
        return data
