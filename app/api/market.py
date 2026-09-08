"""市场分析 API（对齐 src/api/market.ts + src/mock/market.ts 口径）

聚合逻辑与前端 Mock 保持一致：
- 月份窗口：指定 year(+month) 取该期，否则取最近 span 个月
- 地区筛选：按 Region.weight 份额折算
- 能源口径：EREV 并入 PHEV
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func as F
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, Car, CarSales, Region
from app.schemas.user import UserSchema
from app.utils.serialize import (
    CAR_CATEGORIES,
    ENERGY_LABEL,
    ENERGY_TYPES,
    PRICE_BUCKETS,
    UPDATED_AT,
    energy_out,
    month_window,
    price_bucket_label,
)
from app.utils.series import build_months

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


def region_factor(db: Session, region: Optional[str]) -> float:
    """地区筛选 → 全国份额缩放系数"""
    if not region:
        return 1.0
    total = sum(float(r[0] or 0) for r in db.query(Region.weight).all())
    seed = db.query(Region.weight).filter(Region.name == region).scalar()
    if seed is None or not total:
        return 1.0
    return float(seed) / total


def monthly_series(rows, months: list[str], factor: float = 1.0) -> dict[str, float]:
    """明细行 → month → 总销量（含缩放）"""
    out = {m: 0.0 for m in months}
    for r in rows:
        key = _mk(r[1])
        if key in out:
            out[key] += int(r[2] or 0)
    if factor != 1.0:
        out = {k: v * factor for k, v in out.items()}
    return out


def match_rows(rows, keyword: Optional[str]):
    """keyword 在 Python 侧兜底过滤（与 Mock hay 口径一致：品牌+车型名+代号+类别）"""
    if not keyword:
        return rows
    kw = keyword.strip().lower()
    # r[7]=name, r[8]=name_norm, r[9]=model_code, r[5]=category
    return [r for r in rows if kw in f"{r[7]}{r[8]}{r[9]}{r[5]}".lower()]


@router.get("/market/options", summary="市场分析筛选选项")
def market_options(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = build_months(18)
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
    months = month_window(span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    factor = region_factor(db, region)

    total = monthly_series(rows, months, factor)
    nev = monthly_series([r for r in rows if energy_out(r[4]) in NEV], months, factor)
    ice = monthly_series([r for r in rows if energy_out(r[4]) not in NEV], months, factor)

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
    months = month_window(span, year, month)
    # 份额按全部品牌计算（与 Mock 一致：忽略 brandId）
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
    months = month_window(span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    factor = region_factor(db, region)

    values = []
    for m in months:
        total = sum(int(r[2] or 0) for r in rows if _mk(r[1]) == m) * factor
        nev = sum(int(r[2] or 0) for r in rows if _mk(r[1]) == m and energy_out(r[4]) in NEV) * factor
        values.append(round(nev / total * 100, 1) if total else 0)
    return {"months": months, "values": values}


def _region_items(db: Session, months: list[str], scale: float = 1.0) -> list[dict]:
    """地区近 N 月销量（NULL 维度行 = 全国口径），yoy 与上一窗口比较"""
    from app.models import RegionalSales

    rows = (
        db.query(RegionalSales.region_id, RegionalSales.month, F.sum(RegionalSales.sales))
        .filter(RegionalSales.energy_type.is_(None), RegionalSales.brand_id.is_(None))
        .group_by(RegionalSales.region_id, RegionalSales.month)
        .all()
    )
    regions = {r.id: r for r in db.query(Region).all()}
    prev_months = build_months(24)
    cur_start = prev_months.index(months[0]) if months and months[0] in prev_months else len(prev_months) - len(months)
    prev_window = prev_months[max(cur_start - len(months), 0):cur_start]

    cur_map: dict[int, int] = {}
    prev_map: dict[int, int] = {}
    for rid, m, s in rows:
        key = _mk(m)
        if key in months:
            cur_map[rid] = cur_map.get(rid, 0) + int(s or 0)
        elif key in prev_window:
            prev_map[rid] = prev_map.get(rid, 0) + int(s or 0)

    def _yoy(cur: int, prev: int) -> float:
        return round((cur - prev) / prev * 100, 1) if prev else 0

    items = [
        {
            "name": regions[rid].name,
            "value": round(val * scale),
            "yoy": _yoy(val, prev_map.get(rid, 0)),
            "penetration": round(float(regions[rid].penetration), 1),
        }
        for rid, val in cur_map.items()
        if rid in regions
    ]
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
    months = month_window(span, year, month)
    items = _region_items(db, months)

    if region:
        hit = next((i for i in items if i["name"] == region), None)
        return [hit] if hit else items

    # 其他筛选联动：按筛选量级 / 全国量级 缩放（与 Mock 一致）
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    filtered = sum(int(r[2] or 0) for r in rows if _mk(r[1]) in months)
    national = sum(int(r[2] or 0) for r in fetch_sales_rows(db) if _mk(r[1]) in months)
    scale = filtered / national if national else 1.0
    for item in items:
        item["value"] = round(item["value"] * scale)
    items.sort(key=lambda x: x["value"], reverse=True)
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
    months = month_window(span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, category=category), keyword)
    factor = region_factor(db, region)

    values: dict[str, float] = {e: 0.0 for e in ENERGY_TYPES}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            values[energy_out(r[4])] += int(r[2] or 0)
    total = sum(values.values()) * factor
    out = [
        {
            "name": ENERGY_LABEL[e],
            "value": round(values[e] * factor),
            "ratio": round(values[e] * factor / total, 4) if total else 0,
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
    months = month_window(span, year, month)
    rows = match_rows(fetch_sales_rows(db, brandId=brandId, energyType=energyType, category=category), keyword)
    factor = region_factor(db, region)

    buckets = {b["label"]: 0.0 for b in PRICE_BUCKETS}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            buckets[price_bucket_label(float(r[3]))] += int(r[2] or 0)
    return [{"label": b["label"], "value": round(buckets[b["label"]] * factor)} for b in PRICE_BUCKETS]


def _brand_rank(db: Session, months: list[str], limit: int, factor: float = 1.0) -> list[dict]:
    """品牌销量排行：当前窗口 vs 上一窗口 yoy"""
    rows = fetch_sales_rows(db)
    brand_names = {b.id: b.name for b in db.query(Brand).all()}
    prev_months = build_months(24)
    cur_start = prev_months.index(months[0]) if months and months[0] in prev_months else len(prev_months) - len(months)
    prev_window = prev_months[max(cur_start - len(months), 0):cur_start]

    cur_map: dict[int, int] = {}
    prev_map: dict[int, int] = {}
    for r in rows:
        key = _mk(r[1])
        if key in months:
            cur_map[r[6]] = cur_map.get(r[6], 0) + int(r[2] or 0)
        elif key in prev_window:
            prev_map[r[6]] = prev_map.get(r[6], 0) + int(r[2] or 0)

    total = sum(cur_map.values()) * factor
    items = []
    for bid, val in cur_map.items():
        if bid not in brand_names or val <= 0:
            continue
        prev = prev_map.get(bid, 0)
        items.append({
            "name": brand_names[bid],
            "value": round(val * factor),
            "share": round(val / total, 4) if total else 0,
            "yoy": round((val - prev) / prev * 100, 1) if prev else 0,
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
    months = month_window(span, year, month)
    return _brand_rank(db, months, limit, region_factor(db, region))


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
    months = month_window(span, year, month)
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
    months = build_months(24)[-min(max(span, 1), 24):]
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
