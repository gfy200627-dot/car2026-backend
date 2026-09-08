"""市场分析 API（对齐 src/api/market.ts）

聚合口径：
- 时间窗口一律取自 CarSales 实际存在的月份（available_months），不构造不存在的月份
- 地区维度统一使用 RegionalSales 真实数据，不再用 全国销量 × Region.weight 估算
  （RegionalSales 无能源/品牌/价格维度，相关筛选参数保留但仅作用于车型级指标）
- 能源口径：EREV 并入 PHEV
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func as F
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, Car, CarSales, Region, RegionalSales
from app.schemas.user import UserSchema
from app.utils.serialize import (
    CAR_CATEGORIES,
    ENERGY_LABEL,
    ENERGY_TYPES,
    PRICE_BUCKETS,
    UPDATED_AT,
    available_months,
    energy_out,
    month_window,
    price_bucket_label,
)
from app.utils.series import calc_yoy, prev_year_month

router = APIRouter()

NEV = ("BEV", "PHEV")


def _mk(m) -> str:
    return m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]


def fetch_sales_rows(
    db: Session,
    *,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
):
    """按车型筛选条件取回 (carId, month, sales, price, energyType, category, brandId, name, nameNorm, modelCode) 明细"""
    q = (
        db.query(
            CarSales.car_id,
            CarSales.month,
            CarSales.sales,
            Car.price,
            Car.energy_type,
            Car.category,
            Car.brand_id,
            Car.name,
            Car.name_norm,
            Car.model_code,
        )
        .join(Car, Car.id == CarSales.car_id)
    )
    if brandId:
        q = q.filter(Car.brand_id == brandId)
    if energyType:
        if energyType == "PHEV":
            q = q.filter(Car.energy_type.in_(["PHEV", "EREV"]))
        else:
            q = q.filter(Car.energy_type == energyType)
    if category:
        q = q.filter(Car.category == category)
    return q.all()


def monthly_series(rows, months: list[str]) -> dict[str, float]:
    """明细行 → month → 总销量"""
    out = {m: 0.0 for m in months}
    for r in rows:
        key = _mk(r[1])
        if key in out:
            out[key] += int(r[2] or 0)
    return out


def match_rows(rows, keyword: Optional[str]):
    """keyword 在 Python 侧兜底过滤（口径：品牌+车型名+代号+类别）"""
    if not keyword:
        return rows
    kw = keyword.strip().lower()
    # r[7]=name, r[8]=name_norm, r[9]=model_code, r[5]=category
    return [r for r in rows if kw in f"{r[7]}{r[8]}{r[9]}{r[5]}".lower()]


def _regional_monthly(db: Session, region: Optional[str] = None) -> dict[str, dict[str, int]]:
    """RegionalSales 真实月度：region 名 → month → sales（NULL 维度行 = 全国分地区口径）"""
    q = (
        db.query(Region.name, RegionalSales.month, F.sum(RegionalSales.sales))
        .join(Region, Region.id == RegionalSales.region_id)
        .filter(RegionalSales.energy_type.is_(None), RegionalSales.brand_id.is_(None))
        .group_by(Region.name, RegionalSales.month)
    )
    if region:
        q = q.filter(Region.name == region)
    out: dict[str, dict[str, int]] = {}
    for name, m, s in q.all():
        out.setdefault(name, {})[_mk(m)] = int(s or 0)
    return out


@router.get("/market/options", summary="市场分析筛选选项")
def market_options(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = available_months(db)
    return {
        "years": sorted({m[:4] for m in months}),
        "months": list(range(1, 13)),
        "brands": [{"id": b.id, "name": b.name} for b in db.query(Brand).order_by(Brand.id).all()],
        "energies": [{"value": e, "label": ENERGY_LABEL[e]} for e in ENERGY_TYPES],
        "categories": CAR_CATEGORIES,
        "regions": [r.name for r in db.query(Region).order_by(Region.id).all()],
        "updatedAt": UPDATED_AT,
    }


@router.get("/market/trend", summary="市场销量趋势")
def market_trend(
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
        # 指定地区：直接使用 RegionalSales 真实月度（无能源/品牌细分维度）
        rmap = _regional_monthly(db, region)
        vals = rmap.get(region, {})
        return {
            "months": months,
            "series": [
                {"name": f"{region}·总销量", "data": [vals.get(m, 0) for m in months], "type": "line"}
            ],
        }

    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    total = monthly_series(rows, months)
    nev = monthly_series([r for r in rows if energy_out(r[4]) in NEV], months)
    ice = monthly_series([r for r in rows if energy_out(r[4]) not in NEV], months)

    return {
        "months": months,
        "series": [
            {"name": "总销量", "data": [round(total[m]) for m in months], "type": "line"},
            {"name": "新能源", "data": [round(nev[m]) for m in months], "type": "line"},
            {"name": "燃油车", "data": [round(ice[m]) for m in months], "type": "line"},
        ],
    }


@router.get("/market/share", summary="品牌市场份额")
def market_share(
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
    # 份额按全部品牌计算（与前端图表口径一致：忽略 brandId/region）
    rows = match_rows(fetch_sales_rows(db, energyType=energyType, category=category), keyword)
    brand_names = {b.id: b.name for b in db.query(Brand).all()}

    per_brand_month: dict[int, dict[str, int]] = {}
    for r in rows:
        key = _mk(r[1])
        if key not in months:
            continue
        per_brand_month.setdefault(r[6], {})
        per_brand_month[r[6]][key] = per_brand_month[r[6]].get(key, 0) + int(r[2] or 0)

    totals = sorted(((bid, sum(vals.values())) for bid, vals in per_brand_month.items()), key=lambda t: t[1], reverse=True)
    top_ids = [bid for bid, _ in totals[:6]]
    rest_ids = [bid for bid, _ in totals[6:]]

    def month_total(key: str) -> int:
        return sum(vals.get(key, 0) for vals in per_brand_month.values())

    series = [
        {
            "name": brand_names.get(bid, str(bid)),
            "type": "line",
            "data": [
                round(per_brand_month[bid].get(m, 0) / month_total(m) * 100, 2) if month_total(m) else 0
                for m in months
            ],
        }
        for bid in top_ids
    ]
    series.append({
        "name": "其他",
        "type": "line",
        "data": [
            round(sum(per_brand_month[bid].get(m, 0) for bid in rest_ids) / month_total(m) * 100, 2)
            if month_total(m) else 0
            for m in months
        ],
    })
    return {"months": months, "series": series}


@router.get("/market/penetration", summary="新能源渗透率趋势")
def market_penetration(
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
    # 渗透率依赖能源维度，RegionalSales 无该细分，region 参数不参与（全国口径）
    months = month_window(db, span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)

    values = []
    for m in months:
        total = sum(int(r[2] or 0) for r in rows if _mk(r[1]) == m)
        nev = sum(int(r[2] or 0) for r in rows if _mk(r[1]) == m and energy_out(r[4]) in NEV)
        values.append(round(nev / total * 100, 1) if total else 0)
    return {"months": months, "values": values}


def _region_items(db: Session, months: list[str]) -> list[dict]:
    """地区近 N 月销量（RegionalSales 真实数据），同比仅与上一年同月真实数据比较"""
    rmap = _regional_monthly(db)
    regions = {r.name: r for r in db.query(Region).all()}

    items = []
    for name, vals in rmap.items():
        value = sum(vals.get(m, 0) for m in months)
        region_row = regions.get(name)
        if region_row is None or value <= 0:
            continue
        items.append({
            "name": name,
            "value": value,
            "yoy": calc_yoy(vals, months),
            "penetration": round(float(region_row.penetration), 1),
        })
    items.sort(key=lambda x: x["value"], reverse=True)
    return items


@router.get("/market/region", summary="各地区销量")
def market_region(
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
    """地区销量统一 RegionalSales 口径；车型级筛选（brandId/energyType/keyword）
    在地区数据中无真实细分维度，不参与本接口计算"""
    months = month_window(db, span, year, month)
    items = _region_items(db, months)

    if region:
        hit = next((i for i in items if i["name"] == region), None)
        return [hit] if hit else items
    return items


@router.get("/market/energy", summary="各能源类型销量")
def market_energy(
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
    # 能源结构为全国口径（RegionalSales 无能源细分，region 不参与）
    months = month_window(db, span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, category=category), keyword)

    values: dict[str, float] = {e: 0.0 for e in ENERGY_TYPES}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            values[energy_out(r[4])] += int(r[2] or 0)
    total = sum(values.values())
    out = [
        {
            "name": ENERGY_LABEL[e],
            "value": round(values[e]),
            "ratio": round(values[e] / total, 4) if total else 0,
        }
        for e in ENERGY_TYPES
    ]
    return [i for i in out if i["value"] > 0]


@router.get("/market/price", summary="各价格区间销量")
def market_price(
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
    # 价格分布为全国口径（RegionalSales 无价格维度，region 不参与）
    months = month_window(db, span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)

    buckets = {b["label"]: 0.0 for b in PRICE_BUCKETS}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            buckets[price_bucket_label(float(r[3]))] += int(r[2] or 0)
    return [{"label": b["label"], "value": round(buckets[b["label"]])} for b in PRICE_BUCKETS]


def _brand_rank(db: Session, months: list[str], limit: int) -> list[dict]:
    """品牌销量排行：CarSales 聚合，同比仅与上一年同月真实数据比较"""
    rows = fetch_sales_rows(db)
    brand_names = {b.id: b.name for b in db.query(Brand).all()}

    brand_map: dict[int, dict[str, int]] = {}
    for r in rows:
        bucket = brand_map.setdefault(r[6], {})
        key = _mk(r[1])
        bucket[key] = bucket.get(key, 0) + int(r[2] or 0)

    total = sum(brand_map[bid].get(m, 0) for bid in brand_map for m in months)
    items = []
    for bid, vals in brand_map.items():
        if bid not in brand_names:
            continue
        value = sum(vals.get(m, 0) for m in months)
        if value <= 0:
            continue
        items.append({
            "name": brand_names[bid],
            "value": value,
            "share": round(value / total, 4) if total else 0,
            "yoy": calc_yoy(vals, months),
        })
    items.sort(key=lambda x: x["value"], reverse=True)
    return items[:limit]


@router.get("/market/brand-rank", summary="热门品牌排行")
def market_brand_rank(
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


@router.get("/market/category", summary="车型类别销量")
def market_category(
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
    months = month_window(db, span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType), keyword)

    values: dict[str, int] = {c: 0 for c in CAR_CATEGORIES}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            values[r[5]] = values.get(r[5], 0) + int(r[2] or 0)
    total = sum(values.values())
    return [
        {"name": c, "value": values[c], "ratio": round(values[c] / total, 4) if total else 0}
        for c in CAR_CATEGORIES
        if values[c] > 0
    ]


@router.get("/market/category-trend", summary="车型类别月度趋势")
def market_category_trend(
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = available_months(db)[-min(max(span, 1), 500):]
    rows = fetch_sales_rows(db)

    per_cat: dict[str, dict[str, int]] = {c: {m: 0 for m in months} for c in CAR_CATEGORIES}
    for r in rows:
        key = _mk(r[1])
        if key in months and r[5] in per_cat:
            per_cat[r[5]][key] += int(r[2] or 0)

    return {
        "months": months,
        "series": [
            {"name": c, "data": [per_cat[c][m] for m in months], "type": "bar"}
            for c in CAR_CATEGORIES
        ],
    }
