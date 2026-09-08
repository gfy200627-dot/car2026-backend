"""销量数据 API（对齐 src/api/market.ts 的 salesApi）

- GET /sales          明细分页（车型 × 月份）
- GET /sales/trend    趋势（复用市场分析口径）
- GET /sales/ranking  品牌排行
- GET /sales/region   地区销量
- GET /sales/energy   能源结构（预留）
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, CarSales
from app.schemas.user import UserSchema
from app.api.market import _brand_rank, _region_items, fetch_sales_rows, match_rows, monthly_series, region_factor
from app.utils.serialize import energy_out, month_window
from app.utils.series import build_months

router = APIRouter()


@router.get("/sales", summary="销量明细（分页）")
def list_sales(
    span: int = 12,
    brandId: Optional[int] = None,
    page: int = 1,
    pageSize: int = 20,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = build_months(24)[-min(max(span, 1), 24):]
    month_set = set(months)

    from app.models import Car

    rows = (
        db.query(CarSales, Car.price, Car.energy_type, Brand.name, Car.name)
        .join(Car, Car.id == CarSales.car_id)
        .join(Brand, Brand.id == Car.brand_id)
        .all()
    )
    if brandId:
        rows = [r for r in rows if r[0].car_id == brandId]

    rows.sort(key=lambda r: (r[0].car_id, r[0].month))

    items = []
    for cs, price, energy, brand_name, car_name in rows:
        month = cs.month.strftime("%Y-%m") if cs.month else ""
        if month not in month_set:
            continue
        items.append({
            "id": cs.id,
            "carId": cs.car_id,
            "carName": f"{brand_name} {car_name}",
            "brand": brand_name,
            "month": month,
            "sales": cs.sales,
            "revenue": round(cs.sales * float(price), 2),
            "region": "全国",
            "energyType": energy_out(energy),
        })

    page = max(page, 1)
    pageSize = max(pageSize, 1)
    start = (page - 1) * pageSize
    return {
        "list": items[start:start + pageSize],
        "total": len(items),
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/sales/trend", summary="销量趋势")
def sales_trend(
    year: Optional[int] = None,
    month: Optional[int] = None,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    keyword: Optional[str] = None,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = month_window(span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    factor = region_factor(db, region)

    total = monthly_series(rows, months, factor)
    nev = monthly_series([r for r in rows if energy_out(r[4]) in ("BEV", "PHEV")], months, factor)
    ice = monthly_series([r for r in rows if energy_out(r[4]) not in ("BEV", "PHEV")], months, factor)
    return {
        "months": months,
        "series": [
            {"name": "总销量", "data": [round(total[m]) for m in months], "type": "line"},
            {"name": "新能源", "data": [round(nev[m]) for m in months], "type": "line"},
            {"name": "燃油车", "data": [round(ice[m]) for m in months], "type": "line"},
        ],
    }


@router.get("/sales/ranking", summary="品牌销量排行")
def sales_ranking(
    year: Optional[int] = None,
    month: Optional[int] = None,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    keyword: Optional[str] = None,
    span: int = 12,
    limit: int = 10,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    months = month_window(span, year, month)
    return _brand_rank(db, months, limit, region_factor(db, region))


@router.get("/sales/region", summary="地区销量")
def sales_region(
    year: Optional[int] = None,
    month: Optional[int] = None,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    keyword: Optional[str] = None,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    months = month_window(span, year, month)
    items = _region_items(db, months)
    if region:
        hit = next((i for i in items if i["name"] == region), None)
        return [hit] if hit else items
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    filtered = sum(int(r[2] or 0) for r in rows if r[1].strftime("%Y-%m") in months)
    national = sum(int(r[2] or 0) for r in fetch_sales_rows(db) if r[1].strftime("%Y-%m") in months)
    scale = filtered / national if national else 1.0
    for item in items:
        item["value"] = round(item["value"] * scale)
    items.sort(key=lambda x: x["value"], reverse=True)
    return items


@router.get("/sales/energy", summary="能源类型销量")
def sales_energy(
    year: Optional[int] = None,
    month: Optional[int] = None,
    brandId: Optional[int] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    keyword: Optional[str] = None,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    from app.api.market import market_energy

    return market_energy(
        year=year, month=month, brandId=brandId, energyType=None,
        category=category, region=region, keyword=keyword, span=span, db=db, current=current,
    )
