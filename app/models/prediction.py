"""算法产物：销量预测 / 推荐快照"""

from datetime import date
from typing import Optional

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.mixins import TimestampMixin


class SalesPrediction(TimestampMixin, Base):
    """销量预测：cars ← sales_predictions（UNIQUE car+month+model）"""

    __tablename__ = "sales_predictions"
    __table_args__ = (
        UniqueConstraint("car_id", "prediction_month", "model_name", name="uq_prediction_car_month_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    prediction_month: Mapped[date] = mapped_column(Date, comment="预测月份")
    predicted_sales: Mapped[int] = mapped_column(Integer, comment="预测销量（辆）")
    lower: Mapped[int] = mapped_column(Integer, default=0, comment="置信下界")
    upper: Mapped[int] = mapped_column(Integer, default=0, comment="置信上界")
    model_name: Mapped[str] = mapped_column(String(64), default="LinearRegression-Seasonal", comment="模型名")
    accuracy: Mapped[float] = mapped_column(default=0.0, comment="验证集准确率 0~1")

    car_rel = relationship("Car")


class Recommendation(TimestampMixin, Base):
    """推荐结果快照（request_hash 幂等）"""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_hash: Mapped[str] = mapped_column(String(32), index=True, comment="请求指纹 MD5")
    request_body: Mapped[dict] = mapped_column(JSON, comment="原始请求")
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    score: Mapped[float] = mapped_column(comment="综合匹配度 0~100")
    rank_no: Mapped[int] = mapped_column(Integer, default=1, comment="本次请求内排名")
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="推荐理由")
    model_name: Mapped[str] = mapped_column(String(64), default="AutoRec-DB v1.0", comment="算法标识")
