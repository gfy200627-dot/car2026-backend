"""车型 API（对齐 src/api/cars.ts）"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, Brand, CarSales, ModelAlias, User
from app.schemas.car import CarList, CarDetail, CarSalesResponse, SimilarCar, ReviewList
from app.schemas.user import User
from app.utils.series import build_months, recent_months

router = APIRouter()


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
    pageSize: int = 20,
    sortBy: str = "sales_12m",
    sortOrder: str = "desc",
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    """支持 keyword,brandId,energyType,category,priceMin,priceMax,year,page,pageSize,sortBy,sortOrder"""
    query = db.query(Car).options(joinedload(Car.brand_rel))

    # 筛选条件
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(
            or_(
                Car.name.ilike(kw),
                Car.name_norm.ilike(kw),
                Car.model_code.ilike(kw),
                Car.brand.ilike(kw),
            )
        )
    if brandId:
        query = query.filter(Car.brand_id == brandId)
    if energyType:
        query = query.filter(Car.energy_type == energyType)
    if category:
        query = query.filter(Car.category == category)
    if priceMin is not None:
        query = query.filter(Car.price >= priceMin)
    if priceMax is not None:
        query = query.filter(Car.price <= priceMax)
    if year:
        query = query.filter(Car.launch_year == year)

    # 排序
    if sortBy == "sales_12m":
        query = query.order_by(desc(Car.sales_12m))
    elif sortBy == "price":
        query = query.order_by(desc(Car.price))
    elif sortBy == "rating":
        query = query.order_by(desc(Car.rating))
    elif sortBy == "launchYear":
        query = query.order_by(desc(Car.launch_year))
    elif sortBy == "range":
        query = query.order_by(desc(Car.range_km))
    elif sortBy == "power":
        query = query.order_by(desc(Car.power_kw))
    else:
        query = query.order_by(desc(Car.sales_12m))

    if sortOrder == "asc":
        query = query.order_by(getattr(Car, sortBy).asc())

    # 分页
    total = query.count()
    cars = query.offset((page - 1) * pageSize).limit(pageSize).all()

    return {
        "list": [CarList.from_orm(c) for c in cars],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/cars/options", summary="车型筛选选项")
def cars_options(db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    """返回 brands,energies,categories,years,priceBuckets,regions,months,updatedAt"""
    return {
        "brands": [
            {"id": b.id, "name": b.name, "nameEn": b.name_en}
            for b in db.query(Brand).filter(Brand.status == "active").all()
        ],
        "energies": [
            {"value": e, "label": e}
            for e in ["BEV", "PHEV", "HEV", "ICE"]
        ],
        "categories": [
            {"value": c, "label": c}
            for c in ["轿车", "SUV", "MPV", "跑车", "皮卡"]
        ],
        "years": list(range(2020, 2027)),
        "priceBuckets": [
            {"label": "10万以下", "min": 0, "max": 10},
            {"label": "10-15万", "min": 10, "max": 15},
            {"label": "15-20万", "min": 15, "max": 20},
            {"label": "20-30万", "min": 20, "max": 30},
            {"label": "30-50万", "min": 30, "max": 50},
            {"label": "50万以上", "min": 50, "max": 100000},
        ],
        "regions": [{"name": r.name} for r in db.query(Region).all()],
        "months": build_months(24),
        "updatedAt": "2026-09-01 09:30:00",
    }


@router.get("/cars/{id}", summary="获取车型详情")
def get_car(id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> CarDetail:
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    return CarDetail.from_orm(car)


@router.get("/cars/{id}/sales", summary="车型销量趋势")
def car_sales(
    id: int,
    span: int = 18,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> CarSalesResponse:
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")

    months = build_months(span)
    points = []
    for m in months:
        sales = db.query(CarSales).filter(CarSales.car_id == id, CarSales.month == m).first()
        points.append({"month": m, "value": sales.sales if sales else 0})

    # 计算同比（近12月 vs 前12月）
    recent = [p["value"] for p in points[-12:]]
    prev = [p["value"] for p in points[-24:-12]]
    yoy = round((sum(recent) - sum(prev)) / sum(prev) * 100, 1) if sum(prev) else 0

    return CarSalesResponse(points=points, yoy=yoy)


@router.get("/cars/{id}/similar", summary="同级推荐")
def similar_cars(
    id: int,
    limit: int = 4,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> List[SimilarCar]:
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")

    # 简化版：按价格±1.6万 + 类别 + 能源类型相似度排序
    query = db.query(Car).filter(
        Car.id != id,
        Car.category == car.category,
        Car.energy_type == car.energy_type,
    )
    similar = query.order_by(
        func.abs(Car.price - car.price)
    ).limit(limit).all()
    return [SimilarCar.from_orm(c) for c in similar]


@router.get("/cars/{id}/reviews", summary="车型评价列表")
def car_reviews(
    id: int,
    page: int = 1,
    pageSize: int = 10,
    sentiment: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")

    query = db.query(Review).filter(Review.car_id == id)

    if sentiment:
        query = query.filter(Review.sentiment_rel.label == sentiment)
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(Review.content.ilike(kw))

    total = query.count()
    reviews = query.offset((page - 1) * pageSize).limit(pageSize).all()

    return {
        "list": [ReviewList.from_orm(r) for r in reviews],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.post("/cars", summary="创建新车")
def create_car(body: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> CarDetail:
    # 仅管理员
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="无权限")
    # 实现略（需品牌ID、车型名、类别、能源类型、价格等）
    return CarDetail()


@router.put("/cars/{id}", summary="更新车型")
def update_car(id: int, body: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> CarDetail:
    # 仅管理员
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="无权限")
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    # 实现略
    return CarDetail.from_orm(car)


@router.delete("/cars/{id}", summary="删除车型")
def delete_car(id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    # 仅管理员
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="无权限")
    car = db.get(Car, id)
    if not car:
        raise HTTPException(status_code=404, detail="车型不存在")
    db.delete(car)
    db.commit()
    return {"success": True}