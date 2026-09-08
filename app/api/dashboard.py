"""Dashboard API（对齐 src/api/dashboard.ts + src/types/dashboard.ts）"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func as F
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, BrandSales, Car, CarSales, EnergySales, Region, RegionalSales
from app.schemas.user import UserSchema
from app.utils.serialize import (
    UPDATED_AT,
    SOURCE,
    ENERGY_LABEL,
    PRICE_BUCKETS,
    energy_out,
    price_bucket_label,
)
from app.utils.series import build_months

router = APIRouter()

NEV_TYPES = ("BEV", "PHEV")


def _month_key(m) -> str:
    return m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]


def _energy_monthly(db: Session) -> dict[str, dict[str, int]]:
    """month → {energyType: sales}（EREV 并入 PHEV）"""
    rows = db.query(EnergySales.month, EnergySales.energy_type, F.sum(EnergySales.sales)).group_by(
        EnergySales.month, EnergySales.energy_type
    ).all()
    out: dict[str, dict[str, int]] = {}
    for m, et, s in rows:
        key = _month_key(m)
        bucket = out.setdefault(key, {})
        bucket[energy_out(et)] = bucket.get(energy_out(et), 0) + int(s or 0)
    return out


def _national_monthly(db: Session) -> dict[str, int]:
    rows = db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
    return {_month_key(m): int(s or 0) for m, s in rows}


def _avg_price_monthly(db: Session) -> dict[str, float]:
    """month → 销量加权平均成交价（万元）"""
    rows = (
        db.query(
            CarSales.month,
            F.sum(CarSales.sales * Car.price) / F.nullif(F.sum(CarSales.sales), 0),
        )
        .join(Car, Car.id == CarSales.car_id)
        .group_by(CarSales.month)
        .all()
    )
    return {_month_key(m): round(float(v or 0), 2) for m, v in rows}


def _yoy(cur: float, prev: float) -> float:
    return round((cur - prev) / prev * 100, 1) if prev else 0


@router.get("/dashboard/overview", summary="驾驶舱概览")
def overview(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = build_months(24)
    last12 = months[-12:]
    prev12 = months[-24:-12]

    national = _national_monthly(db)
    energy = _energy_monthly(db)
    avg_price = _avg_price_monthly(db)

    national12 = sum(national.get(m, 0) for m in last12)
    national_prev = sum(national.get(m, 0) for m in prev12)
    nev12 = sum(energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0) for m in last12)
    nev_prev = sum(energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0) for m in prev12)

    pen_series = []
    for m in months:
        total = national.get(m, 0)
        nev = energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0)
        pen_series.append(round(nev / total * 100, 1) if total else 0)

    # 销量加权平均成交价
    price12 = round(sum(avg_price.get(m, 0) for m in last12) / max(len(last12), 1), 2)
    price_prev = round(sum(avg_price.get(m, 0) for m in prev12) / max(len(prev12), 1), 2)

    brand12 = _brand_window(db, last12)
    brand_prev = _brand_window(db, prev12)
    brands = {b.id: b for b in db.query(Brand).all()}
    brand_rank = sorted(
        ((bid, int(val or 0)) for bid, val in brand12.items()), key=lambda t: t[1], reverse=True
    )
    top_brand_id, top_brand_sales = (brand_rank[0] if brand_rank else (0, 0))
    top_brand = brands.get(top_brand_id)

    hot_brands = [
        {
            "name": brands[bid].name,
            "value": val,
            "share": round(val / national12, 4) if national12 else 0,
            "yoy": _yoy(val, brand_prev.get(bid, 0)),
        }
        for bid, val in brand_rank[:8]
        if bid in brands
    ]

    metrics = [
        {
            "key": "national",
            "label": "全国汽车销量",
            "value": national12,
            "unit": "辆",
            "change": _yoy(national12, national_prev),
            "trend": [national.get(m, 0) for m in last12],
            "tone": "brand",
            "format": "int",
            "hint": "最近 12 个月累计",
        },
        {
            "key": "nev",
            "label": "新能源汽车销量",
            "value": nev12,
            "unit": "辆",
            "change": _yoy(nev12, nev_prev),
            "trend": [energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0) for m in last12],
            "tone": "nev",
            "format": "int",
            "hint": "纯电 + 插电混动",
        },
        {
            "key": "penetration",
            "label": "新能源渗透率",
            "value": pen_series[-1],
            "unit": "%",
            "change": round(pen_series[-1] - pen_series[-13], 1) if len(pen_series) >= 13 else 0,
            "trend": pen_series[-12:],
            "tone": "cyan",
            "format": "percent",
            "hint": "最近完整月",
        },
        {
            "key": "price",
            "label": "平均成交价格",
            "value": price12,
            "unit": "万元",
            "change": _yoy(price12, price_prev),
            "trend": [avg_price.get(m, 0) for m in last12],
            "tone": "warn",
            "format": "price",
            "hint": "销量加权",
        },
        {
            "key": "hotBrand",
            "label": "热门汽车品牌",
            "value": top_brand_sales,
            "unit": "辆",
            "change": round(top_brand_sales / national12 * 100, 1) if national12 else 0,
            "trend": [],
            "tone": "purple",
            "format": "text",
            "text": top_brand.name if top_brand else "-",
            "hint": "年销量领先品牌",
        },
    ]

    return {
        "metrics": metrics,
        "hotBrands": hot_brands,
        "updatedAt": UPDATED_AT,
        "source": SOURCE,
        "isMock": False,
    }


def _parse(month: str) -> date:
    from app.utils.series import parse_month

    return parse_month(month)


def _brand_window(db: Session, months: list[str]) -> dict[int, int]:
    if not months:
        return {}
    rows = (
        db.query(BrandSales.brand_id, F.sum(BrandSales.sales))
        .filter(BrandSales.month >= _parse(months[0]), BrandSales.month <= _parse(months[-1]))
        .group_by(BrandSales.brand_id)
        .all()
    )
    return {bid: int(s or 0) for bid, s in rows}


@router.get("/dashboard/trend", summary="驾驶舱趋势")
def trend(
    span: int = 18,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = build_months(24)[-min(max(span, 1), 24):]
    national = _national_monthly(db)
    energy = _energy_monthly(db)
    all_months = build_months(24)

    total, nev, ice, yoy = [], [], [], []
    for i, m in enumerate(months):
        t = national.get(m, 0)
        n = energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0)
        total.append(t)
        nev.append(n)
        ice.append(max(t - n, 0))
        prev_idx = all_months.index(m) - 12
        prev = national.get(all_months[prev_idx], 0) if prev_idx >= 0 else 0
        yoy.append(_yoy(t, prev))

    return {"months": months, "total": total, "nev": nev, "ice": ice, "yoy": yoy,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/brand-ranking", summary="品牌排行")
def brand_ranking(
    limit: int = 10,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    months = build_months(24)
    cur = months[-min(max(span, 1), 12):]
    prev = months[max(len(months) - len(cur) - 12, 0):len(months) - len(cur)]
    cur_map = _brand_window(db, cur)
    prev_map = _brand_window(db, prev)
    brands = {b.id: b for b in db.query(Brand).all()}
    national = _national_monthly(db)
    total = sum(national.get(m, 0) for m in cur)

    items = [
        {
            "name": brands[bid].name,
            "value": val,
            "share": round(val / total, 4) if total else 0,
            "yoy": _yoy(val, prev_map.get(bid, 0)),
        }
        for bid, val in cur_map.items()
        if bid in brands
    ]
    items.sort(key=lambda x: x["value"], reverse=True)
    return items[:limit]


@router.get("/dashboard/car-ranking", summary="车型排行")
def car_ranking(
    limit: int = 10,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    rows = (
        db.query(Car, Brand.name)
        .join(Brand, Car.brand_id == Brand.id)
        .order_by(Car.sales_12m.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name": f"{brand_name} {car.name}",
            "value": car.sales_12m,
            "yoy": 0,
            "extra": ENERGY_LABEL.get(energy_out(car.energy_type), energy_out(car.energy_type)),
        }
        for car, brand_name in rows
    ]


@router.get("/dashboard/energy", summary="能源结构")
def energy(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = build_months(24)
    emap = _energy_monthly(db)
    latest = months[-1]
    latest_total = sum(emap.get(latest, {}).values())

    proportion = [
        {"name": ENERGY_LABEL[e], "value": emap.get(latest, {}).get(e, 0),
         "ratio": round(emap.get(latest, {}).get(e, 0) / latest_total, 4) if latest_total else 0}
        for e in ["BEV", "PHEV", "HEV", "ICE"]
    ]

    recent = months[-12:]
    monthly = {
        "months": recent,
        "series": [
            {"name": ENERGY_LABEL[e], "data": [emap.get(m, {}).get(e, 0) for m in recent], "type": "line"}
            for e in ["BEV", "PHEV", "HEV", "ICE"]
        ],
    }
    return {"proportion": proportion, "monthly": monthly,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/region", summary="地区销量")
def region(
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = build_months(24)
    cur = months[-min(max(span, 1), 12):]
    prev = months[max(len(months) - len(cur) - 12, 0):len(months) - len(cur)]

    rows = (
        db.query(RegionalSales.region_id, RegionalSales.month, F.sum(RegionalSales.sales))
        .filter(
            RegionalSales.energy_type.is_(None),
            RegionalSales.brand_id.is_(None),
            RegionalSales.month >= _parse(prev[0] if prev else cur[0]),
        )
        .group_by(RegionalSales.region_id, RegionalSales.month)
        .all()
    )
    cur_map: dict[int, int] = {}
    prev_map: dict[int, int] = {}
    for rid, m, s in rows:
        key = _month_key(m)
        if key in cur:
            cur_map[rid] = cur_map.get(rid, 0) + int(s or 0)
        elif key in prev:
            prev_map[rid] = prev_map.get(rid, 0) + int(s or 0)

    regions = {r.id: r for r in db.query(Region).all()}
    items = [
        {
            "name": regions[rid].name,
            "value": val,
            "yoy": _yoy(val, prev_map.get(rid, 0)),
            "penetration": round(float(regions[rid].penetration), 1),
        }
        for rid, val in cur_map.items()
        if rid in regions
    ]
    items.sort(key=lambda x: x["value"], reverse=True)
    top_pen = sorted(items, key=lambda x: x["penetration"], reverse=True)[:8]
    return {"regions": items, "topPenetration": top_pen,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/price", summary="价格分布")
def price(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = build_months(12)
    rows = (
        db.query(Car.price, F.sum(CarSales.sales))
        .join(CarSales, CarSales.car_id == Car.id)
        .filter(CarSales.month >= _parse(months[0]))
        .group_by(Car.id)
        .all()
    )
    buckets = {b["label"]: 0 for b in PRICE_BUCKETS}
    for p, s in rows:
        buckets[price_bucket_label(float(p))] += int(s or 0)
    return {"buckets": [{"label": b["label"], "value": buckets[b["label"]]} for b in PRICE_BUCKETS],
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/growth", summary="市场增长")
def growth(
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = build_months(24)
    cur = months[-min(max(span, 1), 12):]
    national = _national_monthly(db)
    avg_price = _avg_price_monthly(db)

    market_size = [round(national.get(m, 0) * avg_price.get(m, 0) / 10000, 2) for m in cur]
    growth_rates = []
    for i, m in enumerate(cur):
        idx = months.index(m)
        prev = national.get(months[idx - 1], 0) if idx >= 1 else 0
        growth_rates.append(_yoy(national.get(m, 0), prev))

    return {"months": cur, "marketSize": market_size, "growth": growth_rates,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/scatter", summary="车型散点")
def scatter(
    limit: int = 60,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    rows = (
        db.query(Car, Brand.name)
        .join(Brand, Car.brand_id == Brand.id)
        .order_by(Car.sales_12m.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name": car.name,
            "brand": brand_name,
            "price": round(float(car.price), 2),
            "sales": car.sales_12m,
            "rating": round(float(car.rating), 1),
            "energyType": ENERGY_LABEL.get(energy_out(car.energy_type), energy_out(car.energy_type)),
        }
        for car, brand_name in rows
    ]
