"""车型 API（对齐 src/api/cars.ts + src/types/business.ts Car 契约）"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as F, or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, require_roles
from app.database.session import get_db
from app.models import Brand, Car, CarSales, Region
from app.schemas.user import UserSchema
from app.utils.serialize import (
    CAR_CATEGORIES,
    ENERGY_LABEL,
    ENERGY_TYPES,
    PRICE_BUCKETS,
    car_to_dict,
)
from app.utils.series import build_months, parse_month

router = APIRouter()

# 前端 sortBy → Car 模型列
_SORT_COLUMNS = {
    "sales": Car.sales_12m,
    "price": Car.price,
    "rating": Car.rating,
    "launchYear": Car.launch_year,
    "range": Car.range_km,
    "power": Car.power_kw,
    "lastMonthSales": Car.last_month_sales,
    "intelligenceScore": Car.intelligence_score,
    "reviewCount": Car.review_count,
}


def _apply_car_filters(query, keyword, brandId, energyType, category, priceMin, priceMax, year):
    """与 Mock filterCars 一致：keyword 命中 品牌+车型名+代号+类别"""
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.join(Brand, Car.brand_id == Brand.id).filter(
            or_(
                Car.name.ilike(kw),
                Car.name_norm.ilike(kw),
                Car.model_code.ilike(kw),
                Car.category.ilike(kw),
                Brand.name.ilike(kw),
                Brand.name_en.ilike(kw),
            )
        )
    if brandId:
        query = query.filter(Car.brand_id == brandId)
    if energyType:
        if energyType == "PHEV":
            query = query.filter(Car.energy_type.in_(["PHEV", "EREV"]))
        else:
            query = query.filter(Car.energy_type == energyType)
    if category:
        query = query.filter(Car.category == category)
    if priceMin is not None and priceMin > 0:
        query = query.filter(Car.price >= priceMin)
    if priceMax is not None and priceMax > 0:
        query = query.filter(Car.price <= priceMax)
    if year:
        query = query.filter(Car.launch_year == year)
    return query


@router.get("/cars", summary="车型列表（分页/筛选/排序）")
def list_cars(
    keyword: Optional[str] = None,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
    priceMin: Optional[float] = None,
    priceMax: Optional[float] = None,
    year: Optional[int] = None,
    page: int = 1,
    pageSize: int = 10,
    sortBy: str = "sales",
    sortOrder: str = "desc",
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    query = _apply_car_filters(
        db.query(Car).options(joinedload(Car.brand_rel)),
        keyword, brandId, energyType, category, priceMin, priceMax, year,
    )
    col = _SORT_COLUMNS.get(sortBy, Car.sales_12m)
    query = query.order_by(col.asc() if sortOrder == "asc" else col.desc())

    total = query.count()
    rows = query.offset((max(page, 1) - 1) * pageSize).limit(pageSize).all()
    return {"list": [car_to_dict(c) for c in rows], "total": total, "page": page, "pageSize": pageSize}


@router.get("/cars/options", summary="车型筛选选项")
def cars_options(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    years = [y for (y,) in db.query(Car.launch_year).distinct().all() if y]
    return {
        "brands": [{"id": b.id, "name": b.name} for b in db.query(Brand).order_by(Brand.id).all()],
        "energies": [{"value": e, "label": ENERGY_LABEL[e]} for e in ENERGY_TYPES],
        "categories": CAR_CATEGORIES,
        "years": sorted(years, reverse=True),
        "priceBuckets": [{"label": b["label"], "min": b["min"], "max": b["max"]} for b in PRICE_BUCKETS],
        "regions": [r.name for r in db.query(Region).order_by(Region.id).all()],
        "months": build_months(24),
    }


@router.get("/cars/{car_id}", summary="获取车型详情")
def get_car(car_id: int, db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    car = db.query(Car).options(joinedload(Car.brand_rel)).filter(Car.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    return car_to_dict(car)


@router.get("/cars/{car_id}/sales", summary="车型销量趋势")
def car_sales(
    car_id: int,
    span: int = 18,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")

    months = build_months(24)
    rows = db.query(CarSales.month, CarSales.sales).filter(CarSales.car_id == car_id).all()
    series_map = {(m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]): s for m, s in rows}
    series = [series_map.get(m, 0) for m in months]

    use = months[-min(max(span, 1), 24):]
    start = len(months) - len(use)
    points = [{"month": m, "value": series[start + i]} for i, m in enumerate(use)]
    yoy = []
    for i in range(len(use)):
        prev_idx = len(series) - len(use) - 12 + i
        prev = series[prev_idx] if prev_idx >= 0 else 0
        yoy.append(round((series[start + i] - prev) / prev * 100, 1) if prev else 0)

    brand_name = car.brand_rel.name if car.brand_rel else ""
    return {"carId": car_id, "carName": f"{brand_name} {car.name}", "points": points, "yoy": yoy}


@router.get("/cars/{car_id}/similar", summary="同级推荐")
def similar_cars(
    car_id: int,
    limit: int = 4,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> List[dict]:
    car = db.get(Car, car_id)
    if not car:
        return []

    candidates = db.query(Car).options(joinedload(Car.brand_rel)).filter(Car.id != car_id).all()
    scored = []
    for c in candidates:
        score = (
            100
            - abs(float(c.price) - float(car.price)) * 1.6
            - (0 if c.category == car.category else 14)
            - (0 if energy_out_eq(c.energy_type, car.energy_type) else 8)
            + (float(c.rating) - 4) * 10
        )
        scored.append((score, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [car_to_dict(c) for _, c in scored[:limit]]


def energy_out_eq(a: str, b: str) -> bool:
    from app.utils.serialize import energy_out

    return energy_out(a) == energy_out(b)


@router.get("/cars/{car_id}/reviews", summary="车型评价列表")
def car_reviews(
    car_id: int,
    page: int = 1,
    pageSize: int = 5,
    sentiment: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    from app.api.sentiment import query_review_items

    return query_review_items(
        db, page=page, pageSize=pageSize, sentiment=sentiment, keyword=keyword, carId=car_id
    )


# ---- 管理 CRUD（仅 admin） ----

_CAR_FIELDS = {
    "name": "name",
    "category": "category",
    "energyType": "energy_type",
    "price": "price",
    "priceMin": "price_min",
    "priceMax": "price_max",
    "range": "range_km",
    "battery": "battery_kwh",
    "power": "power_kw",
    "torque": "torque_nm",
    "wheelbase": "wheelbase",
    "length": "length",
    "width": "width",
    "height": "height",
    "seats": "seats",
    "launchDate": "launch_date",
    "image": "image",
    "tags": "tags",
    "rating": "rating",
}


def _next_model_code(db: Session, brand: Brand, next_id: int) -> str:
    prefix = "".join(ch for ch in brand.name_en.upper() if ch.isalpha())[:3] or "CAR"
    return f"{prefix}-{next_id:03d}"


@router.post("/cars", summary="创建车型（仅管理员）")
def create_car(
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    brand = db.get(Brand, int(body.get("brandId") or 1))
    if not brand:
        raise HTTPException(status_code=400, detail="品牌不存在")
    next_id = (db.query(F.max(Car.id)).scalar() or 0) + 1
    price = float(body.get("price") or 15)
    energy = body.get("energyType") or "BEV"
    launch = str(body.get("launchDate") or f"{date.today().year}-{date.today().month:02d}")
    launch_date = parse_month(launch)

    car = Car(
        brand_id=brand.id,
        name=str(body.get("name") or "未命名车型"),
        name_norm=str(body.get("name") or "未命名车型"),
        model_code=body.get("modelCode") or _next_model_code(db, brand, next_id),
        category=body.get("category") or "轿车",
        energy_type=energy,
        price=price,
        price_min=float(body.get("priceMin") or price * 0.9),
        price_max=float(body.get("priceMax") or price * 1.1),
        range_km=int(body.get("range") or 0),
        battery_kwh=float(body.get("battery") or 0),
        power_kw=int(body.get("power") or 0),
        torque_nm=int(body.get("torque") or 0),
        wheelbase=int(body.get("wheelbase") or 0),
        length=int(body.get("length") or 0),
        width=int(body.get("width") or 0),
        height=int(body.get("height") or 0),
        seats=int(body.get("seats") or 5),
        launch_date=launch_date,
        launch_year=launch_date.year,
        rating=float(body.get("rating") or 4.5),
        intelligence_score=80,
        comfort_score=78,
        space_score=78,
        performance_score=72,
        tags=body.get("tags") or ["新入库"],
    )
    db.add(car)
    db.commit()
    db.refresh(car)
    return car_to_dict(car)


@router.put("/cars/{car_id}", summary="更新车型（仅管理员）")
def update_car(
    car_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    for k, attr in _CAR_FIELDS.items():
        if k in body and body[k] is not None:
            setattr(car, attr, body[k])
    if "launchDate" in body and body["launchDate"]:
        launch_date = parse_month(str(body["launchDate"]))
        car.launch_date = launch_date
        car.launch_year = launch_date.year
    if "brandId" in body and body["brandId"]:
        car.brand_id = int(body["brandId"])
    db.commit()
    db.refresh(car)
    return car_to_dict(car)


@router.delete("/cars/{car_id}", summary="删除车型（仅管理员）")
def delete_car(
    car_id: int,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    db.delete(car)
    db.commit()
    return {"id": car_id}
