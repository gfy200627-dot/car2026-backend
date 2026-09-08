"""API 输出辅助：车型序列化、能源映射、月份窗口、价格分桶、分页排序

所有接口的输出字段命名与 src/types/business.ts 对齐（camelCase）。
数据库层 energy_type 含 EREV，输出层统一并入 PHEV（乘联会口径）。
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Car, CarSales

ENERGY_TYPES = ["BEV", "PHEV", "HEV", "ICE"]
ENERGY_LABEL = {"BEV": "纯电", "PHEV": "插电混动", "HEV": "油电混动", "ICE": "燃油"}
CAR_CATEGORIES = ["轿车", "SUV", "MPV", "跑车", "皮卡"]

PRICE_BUCKETS = [
    {"label": "10万以下", "min": 0.0, "max": 10.0},
    {"label": "10-15万", "min": 10.0, "max": 15.0},
    {"label": "15-20万", "min": 15.0, "max": 20.0},
    {"label": "20-30万", "min": 20.0, "max": 30.0},
    {"label": "30-50万", "min": 30.0, "max": 50.0},
    {"label": "50万以上", "min": 50.0, "max": 1e9},
]

UPDATED_AT = "2026-09-01 09:30:00"
SOURCE = "示例数据集 · AutoInsight Backend"


def energy_out(raw: Optional[str]) -> str:
    """数据库能源类型 → 前端枚举（EREV 并入 PHEV）"""
    if raw == "EREV":
        return "PHEV"
    return raw or "ICE"


def price_bucket_label(price: float) -> str:
    for b in PRICE_BUCKETS:
        if b["min"] <= price < b["max"]:
            return b["label"]
    return "50万以上"


def available_months(db: Session) -> list[str]:
    """CarSales 实际存在的月份（升序）——所有时间序列 API 的唯一时间轴来源。

    真实数据当前覆盖 2025-01 ~ 2026-06；随数据扩展自然延伸到 24 个月及以上，
    不会出现数据库中不存在的月份被当作 0 参与计算。
    """
    rows = db.query(CarSales.month).distinct().all()
    return sorted(
        m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]
        for (m,) in rows
    )


def month_window(
    db: Session,
    span: int = 12,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> list[str]:
    """月份窗口：指定 year(+month) 时取该期（须真实存在），否则取真实数据范围内最近 span 个月"""
    months = available_months(db)
    if year and month:
        target = f"{year}-{int(month):02d}"
        return [target] if target in months else []
    if year:
        hit = [m for m in months if m.startswith(str(year))]
        if hit:
            return hit
    return months[-min(max(span, 1), len(months)):] if months else []


def car_to_dict(car: Car) -> dict:
    """ORM Car → 前端 Car 契约（src/types/business.ts）"""
    return {
        "id": car.id,
        "brandId": car.brand_id,
        "brand": car.brand_rel.name if car.brand_rel is not None else "",
        "name": car.name,
        "modelCode": car.model_code,
        "category": car.category,
        "energyType": energy_out(car.energy_type),
        "price": round(float(car.price), 2),
        "priceMin": round(float(car.price_min), 2),
        "priceMax": round(float(car.price_max), 2),
        "range": car.range_km,
        "battery": round(float(car.battery_kwh), 1),
        "power": car.power_kw,
        "torque": car.torque_nm,
        "wheelbase": car.wheelbase,
        "length": car.length,
        "width": car.width,
        "height": car.height,
        "seats": car.seats,
        "launchDate": car.launch_date.strftime("%Y-%m") if isinstance(car.launch_date, date) else str(car.launch_date)[:7],
        "launchYear": car.launch_year,
        "sales": car.sales_12m,
        "lastMonthSales": car.last_month_sales,
        "rating": round(float(car.rating), 1),
        "intelligenceScore": car.intelligence_score,
        "comfortScore": car.comfort_score,
        "spaceScore": car.space_score,
        "performanceScore": car.performance_score,
        "reviewCount": car.review_count,
        "image": car.image,
        "tags": car.tags or [],
        "rank": car.rank,
    }


def paginate(items: list, page: int = 1, pageSize: int = 10) -> dict:
    """与 Mock paginate 一致的分页包装"""
    page = max(int(page or 1), 1)
    pageSize = max(int(pageSize or 10), 1)
    start = (page - 1) * pageSize
    return {
        "list": items[start:start + pageSize],
        "total": len(items),
        "page": page,
        "pageSize": pageSize,
    }


def sort_by(items: list, sortBy: Optional[str], sortOrder: Optional[str], default: str = "sales") -> list:
    """与 Mock sortBy 一致：支持 'asc'/'desc'，默认 desc"""
    key = sortBy or default
    reverse = (sortOrder or "desc") != "asc"

    def getter(item):
        if isinstance(item, dict):
            return item.get(key, 0)
        return getattr(item, key, 0)

    try:
        return sorted(items, key=getter, reverse=reverse)
    except TypeError:
        return items
