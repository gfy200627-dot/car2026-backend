"""销量事实表：车型月销 / 品牌月销 / 能源月销 / 地区月销"""

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.mixins import TimestampMixin


class CarSales(TimestampMixin, Base):
    """车型月销量：brand ← cars ← car_sales"""

    __tablename__ = "car_sales"
    __table_args__ = (UniqueConstraint("car_id", "month", name="uq_car_sales_car_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    month: Mapped[date] = mapped_column(Date, comment="月份 YYYY-MM-01")
    sales: Mapped[int] = mapped_column(Integer, comment="销量（辆，>0）")
    revenue: Mapped[float] = mapped_column(default=0, comment="销售额（万元）")
    source: Mapped[str] = mapped_column(String(64), default="seed", comment="数据来源")

    car_rel = relationship("Car", back_populates="sales")


class BrandSales(TimestampMixin, Base):
    """品牌月销量（导入后聚合回填）"""

    __tablename__ = "brand_sales"
    __table_args__ = (UniqueConstraint("brand_id", "month", name="uq_brand_sales_brand_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, comment="品牌 ID"
    )
    month: Mapped[date] = mapped_column(Date, comment="月份")
    sales: Mapped[int] = mapped_column(Integer, comment="销量（辆）")

    brand_rel = relationship("Brand")


class EnergySales(TimestampMixin, Base):
    """能源类型月销量（API 输出时 EREV 并入 PHEV）"""

    __tablename__ = "energy_sales"
    __table_args__ = (UniqueConstraint("energy_type", "month", name="uq_energy_sales_type_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    energy_type: Mapped[str] = mapped_column(String(8), index=True, comment="BEV/PHEV/EREV/HEV/ICE")
    month: Mapped[date] = mapped_column(Date, comment="月份")
    sales: Mapped[int] = mapped_column(Integer, comment="销量（辆）")


class Region(TimestampMixin, Base):
    """省级行政区维表（名称与前端地图 GeoJSON properties.name 对齐）"""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, comment="省份名称")
    weight: Mapped[float] = mapped_column(default=1.0, comment="市场份额权重")
    penetration: Mapped[float] = mapped_column(default=40.0, comment="新能源渗透率 %")


class RegionalSales(TimestampMixin, Base):
    """地区月销量（可选按能源/品牌细分；NULL 表示全国汇总口径）"""

    __tablename__ = "regional_sales"
    __table_args__ = (
        UniqueConstraint("region_id", "month", "energy_type", "brand_id", name="uq_regional_sales"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), index=True, comment="地区 ID"
    )
    month: Mapped[date] = mapped_column(Date, comment="月份")
    energy_type: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, comment="能源类型（NULL=全部）")
    brand_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=True, comment="品牌 ID（NULL=全部）"
    )
    sales: Mapped[int] = mapped_column(Integer, comment="销量（辆）")
    source: Mapped[str] = mapped_column(String(64), default="estimated", comment="来源（公开明细 unavailable 时为 estimated）")
