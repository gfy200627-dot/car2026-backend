"""评价与情感分析：reviews ← cars"""

from datetime import date
from typing import List, Optional

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.mixins import TimestampMixin


class Review(TimestampMixin, Base):
    """公开用户评价（来源必须可追溯，禁止 AI 生成）"""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, comment="品牌 ID（冗余便于按品牌聚合）"
    )
    user_name: Mapped[str] = mapped_column(String(64), default="匿名用户", comment="评价人")
    rating: Mapped[int] = mapped_column(comment="评分 1~5")
    content: Mapped[str] = mapped_column(String(2000), comment="评价内容")
    published_at: Mapped[date] = mapped_column(Date, index=True, comment="发布日期")
    likes: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    source: Mapped[str] = mapped_column(String(64), default="manual", comment="来源平台")
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="来源 URL")

    sentiment_rel = relationship("Sentiment", back_populates="review_rel", uselist=False, cascade="all, delete-orphan")
    car_rel = relationship("Car", back_populates="reviews")


class Sentiment(TimestampMixin, Base):
    """评价情感判定结果（一行评价一条）"""

    __tablename__ = "sentiments"
    __table_args__ = (UniqueConstraint("review_id", name="uq_sentiment_review"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True, comment="评价 ID"
    )
    label: Mapped[str] = mapped_column(String(16), index=True, comment="positive/neutral/negative")
    score: Mapped[float] = mapped_column(comment="情感分 0~1")
    keywords: Mapped[List[str]] = mapped_column(JSON, default=list, comment="命中关键词")
    model_name: Mapped[str] = mapped_column(String(64), default="snownlp", comment="分析模型")

    review_rel = relationship("Review", back_populates="sentiment_rel")
