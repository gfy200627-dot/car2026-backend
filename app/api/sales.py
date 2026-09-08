"""销量数据 API（对齐 src/api/market.ts 的 salesApi）

- GET /sales          明细分页（车型 × 月份）；brandId 经 Car.brand_id 筛选
- GET /sales/trend    趋势（与市场分析同口径；region 参数使用 RegionalSales 真实月度）
- GET /sales/ranking  品牌排行（CarSales 聚合）
- GET /sales/region   地区销量（RegionalSales 真实数据）
- GET /sales/energy   能源结构（预留）
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, Car, CarSales
from app.schemas.user import UserSchema
from app.api.market import _brand_rank, _region_items, _regional_monthly, fetch_sales_rows, match_rows, monthly_series
from app.utils.serialize import energy_out, month_window

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
    months = month_window(db, span)
    month_set = set(months)

    q = (
        db.query(CarSales, Car.price, Car.energy_type, Brand.name, Car.name)
        .join(Car, Car.id == CarSales.car_id)
        .join(Brand, Brand.id == Car.brand_id)
    )
    # brandId 是品牌维度，必须经 Car.brand_id 筛选，不能与 CarSales.car_id 混用
    if brandId:
        q = q.filter(Car.brand_id == brandId)
    rows = q.all()
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
    months = month_window(db, span, year, month)
    if not months:
        return {"months": [], "series": []}

    if region:
        # 指定地区：RegionalSales 真实月度（无能源/品牌细分维度）
        vals = _regional_monthly(db, region).get(region, {})
        return {
            "months": months,
            "series": [
                {"name": f"{region}·总销量", "data": [vals.get(m, 0) for m in months], "type": "line"}
            ],
        }

    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    total = monthly_series(rows, months)
    nev = monthly_series([r for r in rows if energy_out(r[4]) in ("BEV", "PHEV")], months)
    ice = monthly_series([r for r in rows if energy_out(r[4]) not in ("BEV", "PHEV")], months)
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
    months = month_window(db, span, year, month)
    return _brand_rank(db, months, limit)


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
    """地区销量统一 RegionalSales 口径（车型级筛选参数不参与地区聚合）"""
    months = month_window(db, span, year, month)
    items = _region_items(db, months)
    if region:
        hit = next((i for i in items if i["name"] == region), None)
        return [hit] if hit else items
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
