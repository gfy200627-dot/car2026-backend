"""Dashboard API（对齐 src/api/dashboard.ts）"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as F

from app.core.config import settings
from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, Brand, CarSales, EnergySales, RegionalSales, Region
from app.models.user import User
from app.utils.series import build_months, recent_months

router = APIRouter()


@router.get("/dashboard/overview", summary="驾驶舱概览")
def overview(db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    # KPI：全国总销量 / 新能源销量 / 渗透率 / 平均成交价 / 热门品牌
    months = build_months(12)
    total = db.query(F.sum(CarSales.sales)).filter(CarSales.month >= months[0]).scalar() or 0

    nev_energy = ["BEV", "PHEV"]
    nev = db.query(F.sum(EnergySales.sales)).filter(
        EnergySales.energy_type.in_(nev_energy), EnergySales.month >= months[0]
    ).scalar() or 0

    penetration = round(nev / total * 100, 1) if total else 0

    avg_price = db.execute(
        """SELECT ROUND(SUM(car_sales.sales * cars.price) / SUM(car_sales.sales), 2)
           FROM car_sales JOIN cars ON car_sales.car_id = cars.id
           WHERE car_sales.month >= %s""",
        (months[0],)
    ).scalar() or 0.0

    top_brand = db.query(Brand).order_by(Brand.annual_sales.desc()).first()
    hot_brands = (
        db.query(Brand)
        .order_by(Brand.annual_sales.desc())
        .limit(8)
        .all()
    )
    return {
        "metrics": [],
        "hotBrands": [{"name": b.name, "value": b.annual_sales or 0} for b in hot_brands],
        "updatedAt": "2026-09-01 09:30:00",
        "source": "示例数据集 · AutoInsight Backend",
        "isMock": False,
    }


@router.get("/dashboard/trend", summary="驾驶舱趋势")
def trend(span: int = 18, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    months = build_months(span)
    total = [db.query(F.sum(CarSales.sales)).filter(CarSales.month == m).scalar() or 0 for m in months]
    return {"months": months, "total": total, "nev": [], "ice": [], "yoy": []}


@router.get("/dashboard/brand-ranking", summary="品牌排行")
def brand_ranking(limit: int = 10, span: int = 12, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list:
    months = build_months(span)
    return []


@router.get("/dashboard/car-ranking", summary="车型排行")
def car_ranking(limit: int = 10, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list:
    return []


@router.get("/dashboard/energy", summary="能源结构")
def energy(db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    return {"proportion": [], "monthly": {"months": [], "series": []}}


@router.get("/dashboard/region", summary="地区销量")
def region(span: int = 12, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    return {"regions": [], "topPenetration": []}


@router.get("/dashboard/price", summary="价格分布")
def price(db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    return {"buckets": []}


@router.get("/dashboard/growth", summary="市场增长")
def growth(span: int = 12, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    return {"months": [], "marketSize": [], "growth": []}


@router.get("/dashboard/scatter", summary="车型散点")
def scatter(limit: int = 60, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list:
    return []