from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# When this file is executed as `python scripts/import_real_data.py`, Python puts
# `scripts/` on sys.path instead of the repository root. Add the project root so
# imports such as `from app...` work both locally and on Render.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func as F
from sqlalchemy.orm import Session

DATA_DIR = ROOT / "data" / "real"

from app.database.session import SessionLocal
from app.models import *
from app.core.security import get_password_hash, verify_password

ENERGY_MAP = {
    "燃油": "fuel", "汽油": "fuel", "纯电": "ev", "纯电动": "ev",
    "插混": "phev", "插电混动": "phev", "增程": "erev", "增程式": "erev",
    "混动": "hev", "油电混合": "hev", "氢能": "hydrogen",
}

DEMO_USERS = (
    ("admin", "管理员", "admin"),
    ("analyst", "数据分析师", "analyst"),
    ("sales", "销售运营", "sales"),
    ("user", "普通用户", "user"),
)


def load_csv(name: str):
    path = DATA_DIR / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_int(value, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def to_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def parse_month(value: str):
    value = str(value).strip()
    for fmt in ("%Y-%m", "%Y/%m", "%Y%m"):
        try:
            return datetime.strptime(value, fmt).date().replace(day=1)
        except ValueError:
            pass
    return datetime.fromisoformat(value).date().replace(day=1)


def clean_text(value: Optional[str], max_len: Optional[int] = None) -> str:
    text = str(value or "").strip()
    return text[:max_len] if max_len else text


def import_brands(db: Session) -> int:
    if db.query(F.count(Brand.id)).scalar():
        return 0
    rows = [Brand(id=to_int(r.get("id")) or None, name=clean_text(r.get("name"), 100),
                 logo=clean_text(r.get("logo"), 255) or None,
                 country=clean_text(r.get("country"), 50) or None)
            for r in load_csv("brand.csv")]
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_cars(db: Session) -> int:
    if db.query(F.count(Car.id)).scalar():
        return 0
    brand_ids = {b.id for b in db.query(Brand.id).all()}
    rows = []
    for r in load_csv("car_model.csv"):
        brand_id = to_int(r.get("brand_id"))
        if brand_id not in brand_ids:
            continue
        rows.append(Car(id=to_int(r.get("id")) or None, brand_id=brand_id,
                        name=clean_text(r.get("name"), 100),
                        series=clean_text(r.get("series"), 100) or None,
                        energy_type=ENERGY_MAP.get(clean_text(r.get("energy_type")), clean_text(r.get("energy_type"), 30)),
                        price_min=to_float(r.get("price_min")), price_max=to_float(r.get("price_max")),
                        image=clean_text(r.get("image"), 255) or None))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_car_sales(db: Session) -> int:
    if db.query(F.count(CarSales.id)).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("car_monthly_sales.csv"):
        car_id = to_int(r.get("car_id"))
        if car_id in car_ids:
            rows.append(CarSales(car_id=car_id, month=parse_month(r["month"]), sales=to_int(r["sales"])))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_brand_sales(db: Session) -> int:
    if db.query(F.count(BrandSales.id)).scalar():
        return 0
    brand_ids = {b.id for b in db.query(Brand.id).all()}
    rows = []
    for r in load_csv("brand_monthly_sales.csv"):
        bid = to_int(r.get("brand_id"))
        if bid in brand_ids:
            rows.append(BrandSales(brand_id=bid, month=parse_month(r["month"]), sales=to_int(r["sales"])))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_energy_sales(db: Session) -> int:
    if db.query(F.count(EnergySales.id)).scalar():
        return 0
    rows = [
        EnergySales(
            energy_type=ENERGY_MAP.get(r["energy_type"], clean_text(r["energy_type"], 30)),
            month=parse_month(r["month"]),
            sales=to_int(r["sales"]),
        )
        for r in load_csv("energy_market.csv")
    ]
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_regional_sales(db: Session) -> int:
    if db.query(F.count(RegionalSales.id)).filter(RegionalSales.source == "crawl").scalar():
        return 0
    region_names = [r.name for r in db.query(Region).all()]
    if not region_names:
        try:
            from scripts.seed_demo import import_regions
            import_regions(db)
            region_names = [r.name for r in db.query(Region).all()]
        except Exception:
            region_names = []
    region_map = {name: idx for idx, name in enumerate(region_names, start=1)}
    rows = []
    for r in load_csv("regional_sales.csv"):
        region_id = to_int(r.get("region_id")) or region_map.get(clean_text(r.get("region")))
        if region_id:
            rows.append(RegionalSales(region_id=region_id, month=parse_month(r["month"]),
                                      sales=to_int(r["sales"]), penetration=to_float(r.get("penetration")),
                                      source="crawl"))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_reviews(db: Session) -> int:
    if db.query(F.count(Review.id)).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("reviews.csv"):
        car_id = to_int(r.get("car_id"))
        if car_id in car_ids:
            rows.append(Review(car_id=car_id, user_name=clean_text(r.get("user_name"), 100) or "匿名用户",
                               rating=to_float(r.get("rating"), 5.0), content=clean_text(r.get("content"), 2000),
                               sentiment=clean_text(r.get("sentiment"), 30) or None,
                               created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.now()))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_predictions(db: Session) -> int:
    if db.query(F.count(SalesPrediction.id)).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("predictions.csv"):
        car_id = to_int(r.get("car_id"))
        if car_id in car_ids:
            rows.append(SalesPrediction(car_id=car_id, month=parse_month(r["month"]),
                                        predicted_sales=to_int(r.get("predicted_sales")),
                                        model_name=clean_text(r.get("model_name"), 100) or "真实模型预测（导入数据）"))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def ensure_demo_users(db: Session) -> int:
    changed = 0
    for username, nickname, role in DEMO_USERS:
        user = db.query(UserModel).filter_by(username=username).first()
        if not user:
            db.add(UserModel(username=username, password_hash=get_password_hash(f"{username}123"),
                             nickname=nickname, email=f"{username}@car2026.local", role=role, status="active"))
            changed += 1
            continue
        if not verify_password(f"{username}123", user.password_hash):
            user.password_hash = get_password_hash(f"{username}123")
            changed += 1
        if user.role != role:
            user.role = role
            changed += 1
        if user.status != "active":
            user.status = "active"
            changed += 1
        if not user.nickname:
            user.nickname = nickname
            changed += 1
        if not user.email:
            user.email = f"{username}@car2026.local"
            changed += 1
    db.commit()
    return changed


def import_users(db: Session) -> int:
    imported = 0
    for r in load_csv("user.csv"):
        username = clean_text(r.get("username"), 50)
        if not username or db.query(UserModel).filter_by(username=username).first():
            continue
        db.add(UserModel(username=username, password_hash=get_password_hash(f"{username}123"),
                         nickname=clean_text(r.get("nickname"), 100) or username,
                         email=clean_text(r.get("email"), 120) or None,
                         role=clean_text(r.get("role"), 30) or "user", status="active"))
        imported += 1
    db.commit()
    return imported + ensure_demo_users(db)


def run_alembic():
    result = os.system("alembic upgrade head")
    if result != 0:
        raise RuntimeError("Alembic migration failed")


def main():
    fresh = "--fresh" in sys.argv
    run_alembic()
    db = SessionLocal()
    try:
        if fresh:
            for table in [SalesPrediction, Review, RegionalSales, EnergySales, BrandSales, CarSales, Car, Brand, Region, UserModel]:
                db.query(table).delete()
            db.commit()
        if db.query(F.count(Car.id)).scalar():
            fixed = ensure_demo_users(db)
            print(f"数据库已有车型数据，跳过真实业务数据重复导入。演示账号校验: {fixed} 个账号已创建/修正")
            return
        results = {
            "brands": import_brands(db), "cars": import_cars(db), "car_sales": import_car_sales(db),
            "brand_sales": import_brand_sales(db), "energy": import_energy_sales(db),
            "regional": import_regional_sales(db), "reviews": import_reviews(db),
            "predictions": import_predictions(db), "users": import_users(db),
        }
        print("真实数据导入完成:", results)
    finally:
        db.close()


if __name__ == "__main__":
    main()
