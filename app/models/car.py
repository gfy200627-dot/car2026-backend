"""车型与车型别名词典"""

import re
from typing import List, Optional

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.session import Base
from app.models.mixins import TimestampMixin


class Car(TimestampMixin, Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="RESTRICT"), index=True, comment="品牌 ID"
    )
    name: Mapped[str] = mapped_column(String(128), comment="车型显示名")
    name_norm: Mapped[str] = mapped_column(String(128), comment="清洗归一名（去空格/动力修饰）")
    model_code: Mapped[str] = mapped_column(String(32), unique=True, comment="车型代号")
    category: Mapped[str] = mapped_column(String(16), index=True, comment="轿车/SUV/MPV/跑车/皮卡")
    # 数据库层含 EREV（增程）；API 输出层映射为 PHEV（乘联会口径）
    energy_type: Mapped[str] = mapped_column(String(8), index=True, comment="BEV/PHEV/EREV/HEV/ICE")
    price: Mapped[float] = mapped_column(comment="指导价（万元）")
    price_min: Mapped[float] = mapped_column(comment="终端起售价（万元）")
    price_max: Mapped[float] = mapped_column(comment="终端顶配价（万元）")
    range_km: Mapped[int] = mapped_column(Integer, default=0, comment="纯电续航（km）")
    battery_kwh: Mapped[float] = mapped_column(default=0, comment="电池容量（kWh）")
    power_kw: Mapped[int] = mapped_column(Integer, default=0, comment="最大功率（kW）")
    torque_nm: Mapped[int] = mapped_column(Integer, default=0, comment="峰值扭矩（N·m）")
    wheelbase: Mapped[int] = mapped_column(Integer, default=0, comment="轴距（mm）")
    length: Mapped[int] = mapped_column(Integer, default=0, comment="车长（mm）")
    width: Mapped[int] = mapped_column(Integer, default=0, comment="车宽（mm）")
    height: Mapped[int] = mapped_column(Integer, default=0, comment="车高（mm）")
    seats: Mapped[int] = mapped_column(Integer, default=5, comment="座位数")
    launch_date: Mapped[str] = mapped_column(Date, comment="上市时间")
    launch_year: Mapped[int] = mapped_column(Integer, index=True, comment="上市年份")
    # 聚合快照（导入后回填）
    sales_12m: Mapped[int] = mapped_column(Integer, default=0, comment="近 12 个月销量")
    last_month_sales: Mapped[int] = mapped_column(Integer, default=0, comment="上月销量")
    rating: Mapped[float] = mapped_column(default=4.0, comment="用户评分 0~5")
    intelligence_score: Mapped[int] = mapped_column(Integer, default=70, comment="智能化评分")
    comfort_score: Mapped[int] = mapped_column(Integer, default=70, comment="舒适性评分")
    space_score: Mapped[int] = mapped_column(Integer, default=70, comment="空间评分")
    performance_score: Mapped[int] = mapped_column(Integer, default=70, comment="性能评分")
    review_count: Mapped[int] = mapped_column(Integer, default=0, comment="评价数")
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="销量排名")
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, comment="标签")
    image: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="车型图片 URL")
    source: Mapped[str] = mapped_column(String(64), default="seed", comment="数据来源")

    __table_args__ = (
        UniqueConstraint("brand_id", "name_norm", "energy_type", name="uq_car_brand_name_energy"),
        Index("ix_cars_price", "price"),
        Index("ix_cars_sort_sales", "sales_12m"),
    )

    brand_rel = relationship("Brand", back_populates="cars")
    sales = relationship("CarSales", back_populates="car_rel", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="car_rel")

    @validates("image")
    def _normalize_image_url(self, key: str, value: Optional[str]) -> Optional[str]:
        """规范化车型图片地址，避免 Markdown 包装导致 VARCHAR(255) 超长。"""
        if not value:
            return None
        value = str(value).strip()

        # 兼容 [https://example.com/a.jpg](https://example.com/a.jpg) 这种误存格式。
        match = re.fullmatch(r"\[.*?\]\((https?://[^)]+)\)", value)
        if match:
            value = match.group(1).strip()

        # URL 仍超过数据库字段上限时不写入无效的截断 URL。
        return value if len(value) <= 255 else None


class ModelAlias(TimestampMixin, Base):
    """车型别名词典：秦 PLUS / 秦PLUS DM-i → 秦PLUS"""

    __tablename__ = "model_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    alias: Mapped[str] = mapped_column(String(128), index=True, comment="别名")

    __table_args__ = (UniqueConstraint("car_id", "alias", name="uq_model_alias"),)
