"""采集清洗登记日志（与业务操作日志分表）"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.mixins import TimestampMixin


class CollectionLog(TimestampMixin, Base):
    """采集日志：记录每次采集/导入的源、周期、记录数、失败数、隔离数"""

    __tablename__ = "collection_logs"
    __table_args__ = (UniqueConstraint("source", "collected_at", name="uq_collection_log"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True, comment="来源域名/系统")
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="源 URL")
    collected_at: Mapped[datetime] = mapped_column(index=True, comment="数据截止时间")
    data_period: Mapped[str] = mapped_column(String(16), comment="数据周期（如 2026-08）")
    record_count: Mapped[int] = mapped_column(Integer, default=0, comment="提取记录数")
    passed_count: Mapped[int] = mapped_column(Integer, default=0, comment="清洗通过数")
    fixed_count: Mapped[int] = mapped_column(Integer, default=0, comment="修复记录数")
    quarantined_count: Mapped[int] = mapped_column(Integer, default=0, comment="隔离记录数")
    status: Mapped[str] = mapped_column(String(16), comment="success/partial/error")
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="错误摘要")