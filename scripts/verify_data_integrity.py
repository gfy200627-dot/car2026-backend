"""真实数据完整性统计（只读，不做任何修改）

检查项：各事实表月份范围、重复键、负值/非法值、空名称、异常日期、置信区间越界。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'real.db').as_posix()}")

from sqlalchemy import func as F  # noqa: E402

from app.models import (  # noqa: E402
    Brand,
    Car,
    CarSales,
    BrandSales,
    EnergySales,
    Order,
    RegionalSales,
    Review,
    SalesPrediction,
    User,
)

problems = []


def scan():
    from app.database.session import SessionLocal

    with SessionLocal() as db:
        print("== 月份范围 ==")
        for name, model, col in [
            ("CarSales", CarSales, CarSales.month),
            ("BrandSales", BrandSales, BrandSales.month),
            ("EnergySales", EnergySales, EnergySales.month),
            ("RegionalSales", RegionalSales, RegionalSales.month),
            ("SalesPrediction", SalesPrediction, SalesPrediction.prediction_month),
        ]:
            lo, hi = db.query(F.min(col), F.max(col)).first()
            lo = lo.strftime("%Y-%m") if lo else None
            hi = hi.strftime("%Y-%m") if hi else None
            print(f"  {name:16s} {lo} ~ {hi}")

        print("== 重复键 ==")
        d1 = db.query(CarSales.car_id, CarSales.month, F.count()).group_by(
            CarSales.car_id, CarSales.month).having(F.count() > 1).all()
        d2 = db.query(BrandSales.brand_id, BrandSales.month, F.count()).group_by(
            BrandSales.brand_id, BrandSales.month).having(F.count() > 1).all()
        d3 = db.query(SalesPrediction.car_id, SalesPrediction.prediction_month,
                      SalesPrediction.model_name, F.count()).group_by(
            SalesPrediction.car_id, SalesPrediction.prediction_month,
            SalesPrediction.model_name).having(F.count() > 1).all()
        d4 = db.query(RegionalSales.region_id, RegionalSales.month,
                      RegionalSales.energy_type, RegionalSales.brand_id, F.count()).group_by(
            RegionalSales.region_id, RegionalSales.month,
            RegionalSales.energy_type, RegionalSales.brand_id).having(F.count() > 1).all()
        for label, d in [("car_sales(car_id,month)", d1), ("brand_sales(brand_id,month)", d2),
                         ("sales_predictions(car,month,model)", d3),
                         ("regional_sales(region,month,energy,brand)", d4)]:
            print(f"  {label}: {len(d)} 组重复")
            if d:
                yield ("dup", label, d[:5])

        print("== 非法值 ==")
        neg = db.query(F.count(CarSales.id)).filter(CarSales.sales < 0).scalar()
        negb = db.query(F.count(BrandSales.id)).filter(BrandSales.sales < 0).scalar()
        bad_price = db.query(F.count(Car.id)).filter(Car.price <= 0).scalar()
        bad_range = db.query(F.count(Car.id)).filter(Car.range_km < 0).scalar()
        bad_rating = db.query(F.count(Car.id)).filter((Car.rating < 0) | (Car.rating > 5)).scalar()
        pred_band = db.query(F.count(SalesPrediction.id)).filter(
            (SalesPrediction.lower > SalesPrediction.predicted_sales)
            | (SalesPrediction.upper < SalesPrediction.predicted_sales)
        ).scalar()
        bad_review = db.query(F.count(Review.id)).filter((Review.rating < 1) | (Review.rating > 5)).scalar()
        bad_order = db.query(F.count(Order.id)).filter(Order.amount <= 0).scalar()
        bad_order_status = db.query(F.count(Order.id)).filter(
            ~Order.status.in_(["pending", "paid", "delivered", "cancelled", "shipped", "completed"])
        ).scalar()
        bad_user_role = db.query(F.count(User.id)).filter(
            ~User.role.in_(["admin", "analyst", "sales", "user"])
        ).scalar()
        for label, v in [("car_sales 销量<0", neg), ("brand_sales 销量<0", negb),
                         ("cars 价格<=0", bad_price), ("cars 续航<0", bad_range),
                         ("cars 评分越界", bad_rating), ("预测置信区间越界", pred_band),
                         ("评价评分越界", bad_review), ("订单金额<=0", bad_order),
                         ("订单状态非法", bad_order_status), ("用户角色非法", bad_user_role)]:
            flag = "✗" if v else "✓"
            print(f"  {flag} {label}: {v}")
            if v:
                yield ("bad-value", label, v)

        print("== 空引用/空名称 ==")
        null_brand = db.query(F.count(Brand.id)).filter((Brand.name.is_(None)) | (Brand.name == "")).scalar()
        null_car = db.query(F.count(Car.id)).filter((Car.name.is_(None)) | (Car.name == "")).scalar()
        orphan_car = db.query(F.count(Car.id)).filter(
            ~Car.brand_id.in_(db.query(Brand.id))).scalar()
        orphan_sales = db.query(F.count(CarSales.id)).filter(
            ~CarSales.car_id.in_(db.query(Car.id))).scalar()
        orphan_review = db.query(F.count(Review.id)).filter(
            ~Review.car_id.in_(db.query(Car.id))).scalar()
        orphan_order = db.query(F.count(Order.id)).filter(
            ~Order.car_id.in_(db.query(Car.id))).scalar()
        for label, v in [("空品牌名", null_brand), ("空车型名", null_car),
                         ("车型挂在不存在品牌", orphan_car), ("销量挂在不存在车型", orphan_sales),
                         ("评价挂在不存在车型", orphan_review), ("订单挂在不存在车型", orphan_order)]:
            flag = "✗" if v else "✓"
            print(f"  {flag} {label}: {v}")
            if v:
                yield ("orphan", label, v)

        print("== 日期异常 ==")
        bad_month = db.query(F.count(CarSales.id)).filter(
            (CarSales.month < "2024-01-01") | (CarSales.month > "2027-12-31")).scalar()
        bad_launch = db.query(F.count(Car.id)).filter(
            (Car.launch_year < 1990) | (Car.launch_year > 2027)).scalar()
        for label, v in [("销量月份越合理窗口", bad_month), ("上市年份异常", bad_launch)]:
            flag = "✗" if v else "✓"
            print(f"  {flag} {label}: {v}")
            if v:
                yield ("date", label, v)


issues = list(scan())
print()
if issues:
    print(f"⚠ 发现 {len(issues)} 类数据问题（只报告，不修改）")
    for i in issues:
        print("  -", i)
else:
    print("🎉 数据完整性检查未发现异常")
