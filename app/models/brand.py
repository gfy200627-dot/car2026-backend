"""品牌与别名词典"""

from typing import List

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.mixins import TimestampMixin


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, comment="中文名")
    name_en: Mapped[str] = mapped_column(String(64), default="", comment="英文名")
    country: Mapped[str] = mapped_column(String(32), default="中国", comment="国别")
    group: Mapped[str] = mapped_column(String(32), default="自主", comment="阵营：自主/新势力/德系/日系/美系/韩系/欧系")
    color: Mapped[str] = mapped_column(String(16), default="#111111", comment="品牌主色")
    founded_year: Mapped[int] = mapped_column(Integer, default=2000, comment="成立年份")
    energy_focus: Mapped[List[str]] = mapped_column(JSON, default=list, comment="主打能源类型")
    weight: Mapped[float] = mapped_column(Integer, default=10, comment="市场规模权重（相对值）")
    model_count: Mapped[int] = mapped_column(Integer, default=0, comment="在售车型数")
    annual_sales: Mapped[int] = mapped_column(Integer, default=0, comment="年销量（辆）")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="active/inactive")
    source: Mapped[str] = mapped_column(String(64), default="seed", comment="数据来源")

    cars = relationship("Car", back_populates="brand_rel")
    aliases = relationship("BrandAlias", back_populates="brand_rel", cascade="all, delete-orphan")


class BrandAlias(TimestampMixin, Base):
    """品牌别名词典：比亚迪汽车/BYD → brand_id=1"""

    __tablename__ = "brand_aliases"
    __table_args__ = (UniqueConstraint("alias", name="uq_brand_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, comment="品牌 ID"
    )
    alias: Mapped[str] = mapped_column(String(128), index=True, comment="别名")
    source: Mapped[str] = mapped_column(String(64), default="manual", comment="别名来源")

    brand_rel = relationship("Brand", back_populates="aliases")
