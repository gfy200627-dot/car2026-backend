"""Dashboard API（对齐 src/api/dashboard.ts + src/types/dashboard.ts）

时间轴约定：所有序列以 CarSales 实际存在的月份为准（available_months），
不构造数据库中不存在的月份；同比仅在上一年同月有真实数据时计算。
车型/品牌排行基于 CarSales / BrandSales 真实月度聚合，不依赖 Car.sales_12m 缓存字段。
"""

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
    available_months,
    energy_out,
    price_bucket_label,
)
from app.utils.series import calc_yoy, parse_month, prev_month, prev_year_month

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


def _brand_monthly(db: Session) -> dict[int, dict[str, int]]:
    """brand_id → month → sales（BrandSales 真实月度）"""
    rows = db.query(BrandSales.brand_id, BrandSales.month, BrandSales.sales).all()
    out: dict[int, dict[str, int]] = {}
    for bid, m, s in rows:
        out.setdefault(bid, {})[_month_key(m)] = int(s or 0)
    return out


def _car_monthly(db: Session) -> dict[int, dict[str, int]]:
    """car_id → month → sales（CarSales 真实月度）"""
    rows = db.query(CarSales.car_id, CarSales.month, CarSales.sales).all()
    out: dict[int, dict[str, int]] = {}
    for cid, m, s in rows:
        out.setdefault(cid, {})[_month_key(m)] = int(s or 0)
    return out


def _monthly_yoy(monthly: dict[str, int], m: str) -> float:
    """单月同比：上一年同月无真实数据时返回 0，不把缺失月当 0 参与计算"""
    pm = prev_year_month(m)
    prev = monthly.get(pm, 0)
    return round((monthly.get(m, 0) - prev) / prev * 100, 1) if prev else 0


@router.get("/dashboard/overview", summary="驾驶舱概览")
def overview(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = available_months(db)
    if not months:
        return {"metrics": [], "hotBrands": [], "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}
    last12 = months[-12:]

    national = _national_monthly(db)
    energy = _energy_monthly(db)
    avg_price = _avg_price_monthly(db)

    national12 = sum(national.get(m, 0) for m in last12)
    nev_map = {m: energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0) for m in months}
    nev12 = sum(nev_map[m] for m in last12)

    pen_map = {
        m: round(nev_map[m] / national[m] * 100, 1) if national.get(m) else 0
        for m in months
    }
    latest = months[-1]
    pen_prev = prev_year_month(latest)
    pen_change = round(pen_map[latest] - pen_map[pen_prev], 1) if pen_prev in pen_map else 0

    price12 = round(sum(avg_price.get(m, 0) for m in last12) / len(last12), 2)

    brand_map = _brand_monthly(db)
    brands = {b.id: b for b in db.query(Brand).all()}
    brand_cur = {
        bid: sum(vals.get(m, 0) for m in last12)
        for bid, vals in brand_map.items()
    }
    brand_rank = sorted(brand_cur.items(), key=lambda t: t[1], reverse=True)
    top_brand_id, top_brand_sales = brand_rank[0] if brand_rank else (0, 0)
    top_brand = brands.get(top_brand_id)

    hot_brands = [
        {
            "name": brands[bid].name,
            "value": val,
            "share": round(val / national12, 4) if national12 else 0,
            "yoy": calc_yoy(brand_map[bid], last12),
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
            "change": calc_yoy(national, last12),
            "trend": [national.get(m, 0) for m in last12],
            "tone": "brand",
            "format": "int",
            "hint": "真实数据最近 12 个月累计",
        },
        {
            "key": "nev",
            "label": "新能源汽车销量",
            "value": nev12,
            "unit": "辆",
            "change": calc_yoy(nev_map, last12),
            "trend": [nev_map[m] for m in last12],
            "tone": "nev",
            "format": "int",
            "hint": "纯电 + 插电混动",
        },
        {
            "key": "penetration",
            "label": "新能源渗透率",
            "value": pen_map[latest],
            "unit": "%",
            "change": pen_change,
            "trend": [pen_map[m] for m in last12],
            "tone": "cyan",
            "format": "percent",
            "hint": "最近完整月",
        },
        {
            "key": "price",
            "label": "平均成交价格",
            "value": price12,
            "unit": "万元",
            "change": calc_yoy(avg_price, last12),
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


@router.get("/dashboard/trend", summary="驾驶舱趋势")
def trend(
    span: int = 18,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    months = available_months(db)[-min(max(span, 1), 500):]
    national = _national_monthly(db)
    energy = _energy_monthly(db)

    total, nev, ice, yoy = [], [], [], []
    for m in months:
        t = national.get(m, 0)
        n = energy.get(m, {}).get("BEV", 0) + energy.get(m, {}).get("PHEV", 0)
        total.append(t)
        nev.append(n)
        ice.append(max(t - n, 0))
        yoy.append(_monthly_yoy(national, m))

    return {"months": months, "total": total, "nev": nev, "ice": ice, "yoy": yoy,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/brand-ranking", summary="品牌排行")
def brand_ranking(
    limit: int = 10,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    months = available_months(db)[-min(max(span, 1), 500):]
    brand_map = _brand_monthly(db)
    brands = {b.id: b for b in db.query(Brand).all()}
    national = _national_monthly(db)
    total = sum(national.get(m, 0) for m in months)

    items = [
        {
            "name": brands[bid].name,
            "value": sum(vals.get(m, 0) for m in months),
            "share": round(sum(vals.get(m, 0) for m in months) / total, 4) if total else 0,
            "yoy": calc_yoy(vals, months),
        }
        for bid, vals in brand_map.items()
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
    """基于 CarSales 真实月度聚合（当前数据范围内最近 12 个月），不使用 Car.sales_12m 缓存"""
    months = available_months(db)[-12:]
    car_map = _car_monthly(db)
    totals = {
        cid: sum(vals.get(m, 0) for m in months)
        for cid, vals in car_map.items()
    }
    cars = {c.id: c for c in db.query(Car).filter(Car.id.in_(totals.keys())) if totals.get(c.id)}
    brand_names = {b.id: b.name for b in db.query(Brand).all()}

    items = []
    for cid, value in sorted(totals.items(), key=lambda t: t[1], reverse=True)[:limit]:
        car = cars.get(cid)
        if not car:
            continue
        items.append({
            "name": f"{brand_names.get(car.brand_id, '')} {car.name}",
            "value": value,
            "yoy": calc_yoy(car_map[cid], months),
            "extra": ENERGY_LABEL.get(energy_out(car.energy_type), energy_out(car.energy_type)),
        })
    return items


@router.get("/dashboard/energy", summary="能源结构")
def energy(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = available_months(db)
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
    """地区销量统一口径：RegionalSales（energy_type/brand_id 均为 NULL 的全国分地区行）"""
    months = available_months(db)[-min(max(span, 1), 500):]

    rows = (
        db.query(RegionalSales.region_id, RegionalSales.month, F.sum(RegionalSales.sales))
        .filter(
            RegionalSales.energy_type.is_(None),
            RegionalSales.brand_id.is_(None),
        )
        .group_by(RegionalSales.region_id, RegionalSales.month)
        .all()
    )
    rmap: dict[int, dict[str, int]] = {}
    for rid, m, s in rows:
        rmap.setdefault(rid, {})[_month_key(m)] = int(s or 0)

    regions = {r.id: r for r in db.query(Region).all()}
    items = []
    for rid, vals in rmap.items():
        if rid not in regions:
            continue
        value = sum(vals.get(m, 0) for m in months)
        if value <= 0:
            continue
        items.append({
            "name": regions[rid].name,
            "value": value,
            "yoy": calc_yoy(vals, months),
            "penetration": round(float(regions[rid].penetration), 1),
        })
    items.sort(key=lambda x: x["value"], reverse=True)
    top_pen = sorted(items, key=lambda x: x["penetration"], reverse=True)[:8]
    return {"regions": items, "topPenetration": top_pen,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/price", summary="价格分布")
def price(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = available_months(db)[-12:]
    rows = (
        db.query(Car.price, F.sum(CarSales.sales))
        .join(CarSales, CarSales.car_id == Car.id)
        .filter(CarSales.month >= parse_month(months[0]), CarSales.month <= parse_month(months[-1]))
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
    months = available_months(db)[-min(max(span, 1), 500):]
    national = _national_monthly(db)
    avg_price = _avg_price_monthly(db)

    market_size = [round(national.get(m, 0) * avg_price.get(m, 0) / 10000, 2) for m in months]
    growth_rates = []
    for m in months:
        pm = prev_month(m)
        if pm in national and national[pm]:
            growth_rates.append(round((national.get(m, 0) - national[pm]) / national[pm] * 100, 1))
        else:
            growth_rates.append(0)

    return {"months": months, "marketSize": market_size, "growth": growth_rates,
            "updatedAt": UPDATED_AT, "source": SOURCE, "isMock": False}


@router.get("/dashboard/scatter", summary="车型散点")
def scatter(
    limit: int = 60,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    """基于 CarSales 真实月度聚合（最近 12 个月），不使用 Car.sales_12m 缓存"""
    months = available_months(db)[-12:]
    car_map = _car_monthly(db)
    totals = {
        cid: sum(vals.get(m, 0) for m in months)
        for cid, vals in car_map.items()
    }
    cars = {
        c.id: c
        for c in db.query(Car).filter(Car.id.in_(totals.keys()))
    }
    brand_names = {b.id: b.name for b in db.query(Brand).all()}

    items = []
    for cid, value in sorted(totals.items(), key=lambda t: t[1], reverse=True)[:limit]:
        car = cars.get(cid)
        if not car:
            continue
        items.append({
            "name": car.name,
            "brand": brand_names.get(car.brand_id, ""),
            "price": round(float(car.price), 2),
            "sales": value,
            "rating": round(float(car.rating), 1),
            "energyType": ENERGY_LABEL.get(energy_out(car.energy_type), energy_out(car.energy_type)),
        })
    return items
