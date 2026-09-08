"""真实爬取数据导入：把 data/real/ 下的 CSV 接入后端数据库

数据来源：sj.zip（爬虫采集，2025-01 ~ 2026-06）
- brand(1).csv / car(1).csv / car_images(1).csv   维表（品牌/车型/图片）
- car_monthly_sales / brand_monthly_sales / energy_market / region_market   月度事实表
- user.csv / user_review.csv / order.csv / inventory.csv / system_log.csv   业务数据
- sales_prediction.csv   真实模型预测（2026-07 ~ 2026-12，20 款车型）

约定：
- 金额 元 → 万元（/10000）；评分 0~10 → 0~100（×10）
- 能源中文 → 代码：纯电动→BEV 插电混动→PHEV 增程→EREV 油电混动→HEV 燃油→ICE
  （EREV 仅存 DB，API 输出层并入 PHEV）
- 订单 completed → delivered（前端枚举 pending/paid/delivered/cancelled）
- 地区短名（北京/广东…）补全为省级行政区全名后入库
- user.csv 的密码为 MD5，无法用 bcrypt 校验，统一重置为 用户名+123

用法：
    python scripts/import_real_data.py            # 导入（已导入则跳过）
    python scripts/import_real_data.py --fresh    # 清空业务数据后重新导入
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv

from sqlalchemy import func as F

from app.database.session import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    AlgorithmTask,
    Brand,
    BrandSales,
    Car,
    CarSales,
    CollectionLog,
    DataFile,
    EnergySales,
    Inventory,
    ModelAlias,
    OperationLog,
    Order,
    Recommendation,
    Region,
    RegionalSales,
    Review,
    SalesPrediction,
    Sentiment,
    User,
)

REAL_DIR = Path(__file__).resolve().parents[1] / "data" / "real"

ENERGY_MAP = {"纯电动": "BEV", "插电混动": "PHEV", "增程": "EREV", "油电混动": "HEV", "燃油": "ICE"}
ORDER_STATUS_MAP = {"completed": "delivered", "shipped": "delivered"}
ACTION_MAP = {
    "login": "登录系统", "logout": "退出登录", "view_car": "查看车型", "compare": "车型对比",
    "search": "搜索车型", "view_dashboard": "查看驾驶舱", "view_prediction": "查看销量预测",
    "view_review": "查看评价", "order_create": "创建订单", "export": "导出数据",
}
MODULE_MAP = {
    "auth": "认证", "car": "车型管理", "dashboard": "驾驶舱", "data": "数据管理",
    "ml": "算法任务", "order": "订单管理", "review": "舆情评价", "search": "搜索",
}
GROUP_MAP = {
    "比亚迪": "自主", "吉利": "自主", "长安": "自主", "长城": "自主", "奇瑞": "自主", "坦克": "自主",
    "蔚来": "新势力", "理想": "新势力", "小鹏": "新势力", "问界": "新势力", "极氪": "新势力",
    "零跑": "新势力", "哪吒": "新势力", "小米": "新势力", "仰望": "新势力",
    "丰田": "日系", "本田": "日系", "日产": "日系", "马自达": "日系", "雷克萨斯": "日系",
    "大众": "德系", "奔驰": "德系", "宝马": "德系", "奥迪": "德系", "保时捷": "德系",
    "特斯拉": "美系", "福特": "美系", "通用": "美系",
    "现代": "韩系", "起亚": "韩系",
}
FOUNDED_YEAR = {
    "比亚迪": 1995, "吉利": 1997, "长安": 1862, "长城": 1984, "奇瑞": 1997,
    "蔚来": 2014, "理想": 2015, "小鹏": 2014, "问界": 2021, "极氪": 2021, "坦克": 2021,
    "零跑": 2015, "哪吒": 2014, "小米": 2021, "仰望": 2022,
    "丰田": 1937, "本田": 1948, "日产": 1933, "马自达": 1920, "雷克萨斯": 1983,
    "大众": 1937, "奔驰": 1926, "宝马": 1916, "奥迪": 1909, "保时捷": 1931,
    "特斯拉": 2003, "福特": 1903, "通用": 1908, "现代": 1967, "起亚": 1944,
}
BRAND_COLORS = [
    "#d0202f", "#0b3d91", "#0d4c8b", "#a01f24", "#0f5c8c", "#2b6cb0", "#1a9c6b", "#00a19a",
    "#c8963e", "#6c7a89", "#5a6472", "#00a0e9", "#17a2b8", "#ff6900", "#7c3aed", "#1f6feb",
    "#3b5bdb", "#e31937", "#00274c", "#003876", "#1c5faa", "#2f6fb0", "#0166b1", "#bb0a30",
    "#b12a2a", "#111827", "#047857", "#b45309", "#1d4ed8", "#9333ea",
]
# 评价情感分（与评分联动，确定性取值）
SENTIMENT_SCORE = {"positive": 0.85, "neutral": 0.5, "negative": 0.2}

CRAWLED_MODEL = "Crawled-Model"
CRAWL_REC_MODEL = "Crawl-Rec"


def load_csv(name: str) -> list[dict]:
    path = REAL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少数据文件：{path}")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_month(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), 1)


def parse_dt(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.strptime(s[:10], "%Y-%m-%d")


def to_int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def match_region(name: str, region_names: list[str]) -> str | None:
    """爬虫地区短名 → Region 全名（北京→北京市，内蒙古→内蒙古自治区）"""
    if name in region_names:
        return name
    hits = [n for n in region_names if n.startswith(name)]
    return hits[0] if len(hits) == 1 else None


def import_brands(db) -> int:
    count = 0
    for r in load_csv("brand(1).csv"):
        bid = int(r["brand_id"])
        if db.get(Brand, bid):
            continue
        db.add(Brand(
            id=bid,
            name=r["brand_name"],
            name_en=r["brand_name_en"],
            country=r["country"] or "中国",
            group=GROUP_MAP.get(r["brand_name"], "自主"),
            color=BRAND_COLORS[(bid - 1) % len(BRAND_COLORS)],
            founded_year=FOUNDED_YEAR.get(r["brand_name"], 2000),
            energy_focus=[ENERGY_MAP[e.strip()] for e in r["energy_types"].split(",") if e.strip() in ENERGY_MAP],
            weight=10,
            status="active",
            source="crawl",
        ))
        count += 1
    db.commit()
    return count


def import_cars(db) -> int:
    images = {int(r["car_id"]): r["image"] for r in load_csv("car_images(1).csv")}
    brands = {b.id: b for b in db.query(Brand).all()}
    count = 0
    for r in load_csv("car(1).csv"):
        cid = int(r["car_id"])
        if db.get(Car, cid):
            continue
        brand = brands[int(r["brand_id"])]
        prefix = "".join(ch for ch in brand.name_en.upper() if ch.isalpha())[:4] or "CAR"
        launch_year = int(r["launch_year"] or 2024)
        db.add(Car(
            id=cid,
            brand_id=brand.id,
            name=r["car_name"],
            name_norm=r["car_name"].replace(" ", ""),
            model_code=f"{prefix}-{cid:03d}",
            category=r["category"],
            energy_type=ENERGY_MAP.get(r["energy_type"], "ICE"),
            price=to_float(r["price"]) / 10000,
            price_min=to_float(r["price_min"]) / 10000,
            price_max=to_float(r["price_max"]) / 10000,
            range_km=to_int(r["range"]),
            battery_kwh=to_float(r["battery"]),
            power_kw=to_int(r["power"]),
            torque_nm=to_int(r["torque"]),
            wheelbase=to_int(r["wheelbase"]),
            length=to_int(r["length"]),
            width=to_int(r["width"]),
            height=to_int(r["height"]),
            seats=to_int(r["seats"], 5),
            launch_date=date(launch_year, 1, 1),
            launch_year=launch_year,
            rating=to_float(r["rating"], 4.0),
            intelligence_score=round(to_float(r["intelligence_score"]) * 10),
            comfort_score=round(to_float(r["comfort_score"]) * 10),
            space_score=round(to_float(r["space_score"]) * 10),
            performance_score=round(to_float(r["performance_score"]) * 10),
            tags=[r["energy_type"], r["category"]],
            image=images.get(cid) or r["image"] or None,
            source="crawl",
        ))
        count += 1
    db.commit()
    return count


def import_car_sales(db) -> int:
    if db.query(F.count(CarSales.id)).filter(CarSales.source == "crawl").scalar():
        return 0
    cars = {c.id: c for c in db.query(Car).all()}
    rows = []
    for r in load_csv("car_monthly_sales(1).csv"):
        car = cars[int(r["car_id"])]
        sales = to_int(r["sales"])
        rows.append(CarSales(
            car_id=car.id,
            month=parse_month(r["month"]),
            sales=sales,
            revenue=round(sales * float(car.price), 2),
            source="crawl",
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_brand_sales(db) -> int:
    if db.query(F.count(BrandSales.id)).scalar():
        return 0
    rows = [
        BrandSales(brand_id=int(r["brand_id"]), month=parse_month(r["month"]), sales=to_int(r["sales"]))
        for r in load_csv("brand_monthly_sales(1).csv")
    ]
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_energy_sales(db) -> int:
    if db.query(F.count(EnergySales.id)).scalar():
        return 0
    rows = [
        EnergySales(energy_type=ENERGY_MAP[r["energy_type"]], month=parse_month(r["month"]), sales=to_int(r["sales"]))
        for r in load_csv("energy_market.csv")
    ]
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_regional_sales(db) -> int:
    if db.query(F.count(RegionalSales.id)).filter(RegionalSales.source == "crawl").scalar():
        return 0
    region_names = [r.name for r in db.query(Region).all()]
    if not region_names:
        from scripts.seed_demo import import_regions
        import_regions(db)
        region_names = [r.name for r in db.query(Region).all()]
    region_ids = {n: rid for rid, n in [(r.id, r.name) for r in db.query(Region).all()]}

    rows, skipped = [], []
    for r in load_csv("region_market.csv"):
        full = match_region(r["region"], region_names)
        if full is None:
            skipped.append(r["region"])
            continue
        rows.append(RegionalSales(
            region_id=region_ids[full],
            month=parse_month(r["month"]),
            energy_type=None,
            brand_id=None,
            sales=to_int(r["sales"]),
            source="crawl",
        ))
    db.bulk_save_objects(rows)
    db.commit()
    if skipped:
        print(f"  ⚠ 未匹配地区：{sorted(set(skipped))}")
    return len(rows)


def import_users(db) -> int:
    count = 0
    for r in load_csv("user.csv"):
        username = r["username"]
        if db.query(User).filter_by(username=username).first():
            continue
        db.add(User(
            id=int(r["user_id"]),
            username=username,
            nickname=r["nickname"] or username,
            email=f"{username}@autoinsight.com",
            password_hash=hash_password(f"{username}123"),  # 源数据为 MD5，统一重置
            role=r["role"] if r["role"] in ("admin", "analyst", "sales", "user") else "user",
            status="active" if r["status"] == "1" else "disabled",
            created_at=parse_dt(r["created_at"]) if r["created_at"] else None,
            last_login_at=parse_dt(r["last_login_at"]) if r["last_login_at"] else None,
        ))
        count += 1
    db.commit()

    # 补齐前端角色演示账号（爬虫数据只有 admin/user 两种角色）
    demo = [("analyst", "孙以宁", "analyst"), ("sales", "周砚清", "sales")]
    for username, nickname, role in demo:
        if db.query(User).filter_by(username=username).first():
            continue
        db.add(User(
            username=username, nickname=nickname, email=f"{username}@autoinsight.com",
            password_hash=hash_password(f"{username}123"), role=role, status="active",
            department="演示账号",
        ))
        count += 1
    db.commit()
    return count


def import_reviews(db) -> int:
    if db.query(F.count(Review.id)).filter(Review.source == "crawl").scalar():
        return 0
    cars = {c.id: c for c in db.query(Car).all()}
    users = {u.id: u.nickname for u in db.query(User).all()}
    reviews = []
    for r in load_csv("user_review.csv"):
        car = cars.get(int(r["car_id"]))
        if car is None:
            continue
        rating = max(1, min(5, to_int(r["score"], 3)))
        reviews.append(Review(
            car_id=car.id,
            brand_id=car.brand_id,
            user_name=users.get(int(r["user_id"]), "匿名用户"),
            rating=rating,
            content=r["content"],
            published_at=parse_dt(r["created_at"]).date(),
            likes=0,
            source="crawl",
        ))
    db.bulk_save_objects(reviews)
    db.commit()

    # 情感标注以爬虫结果为准（label/keywords），情感分由 label 确定性映射
    src_by_content = {r["content"]: r for r in load_csv("user_review.csv")}
    for review in db.query(Review).filter(Review.source == "crawl").all():
        src = src_by_content.get(review.content)
        label = (src["sentiment"] if src else "neutral") or "neutral"
        label = label if label in ("positive", "neutral", "negative") else "neutral"
        keywords = [k for k in (src["keywords"] or "").replace("，", ",").split(",") if k] if src else []
        db.add(Sentiment(
            review_id=review.id,
            label=label,
            score=SENTIMENT_SCORE[label],
            keywords=keywords,
            model_name="crawl",
        ))
    db.commit()

    # 回填车型评价数
    counts = dict(db.query(Review.car_id, F.count(Review.id)).group_by(Review.car_id).all())
    for cid, cnt in counts.items():
        car = db.get(Car, cid)
        if car:
            car.review_count = int(cnt)
    db.commit()
    return len(reviews)


def import_orders(db) -> int:
    if db.query(F.count(Order.id)).scalar():
        return 0
    users = {u.id: u.nickname for u in db.query(User).all()}
    rows = []
    for r in load_csv("order.csv"):
        created = parse_dt(r["created_at"])
        rows.append(Order(
            order_no=f"AI{created:%Y%m}{int(r['order_id']):05d}",
            car_id=int(r["car_id"]),
            customer=users.get(int(r["user_id"]), f"用户{r['user_id']}"),
            amount=to_float(r["amount"]) / 10000,
            status=ORDER_STATUS_MAP.get(r["status"], r["status"]),
            region="",
            salesperson=None,
            created_at=created,
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_inventory(db) -> int:
    if db.query(F.count(Inventory.id)).scalar():
        return 0
    cars = {c.id: c for c in db.query(Car).all()}
    rows = []
    for r in load_csv("inventory.csv"):
        car = cars.get(int(r["car_id"]))
        if car is None:
            continue
        stock = to_int(r["stock"])
        monthly = max(car.last_month_sales or 0, 1)
        turnover = round(stock / monthly * 30, 1)
        rows.append(Inventory(
            car_id=car.id,
            quantity=stock,
            inbound=0,
            monthly_sales=car.last_month_sales or 0,
            turnover_days=turnover,
            warehouse=r["city"],
            status="紧张" if turnover < 25 else "偏低" if turnover < 45 else "充足",
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_logs(db) -> int:
    if db.query(F.count(OperationLog.id)).scalar():
        return 0
    rows = []
    for r in load_csv("system_log.csv"):
        rows.append(OperationLog(
            user_id=int(r["user_id"]) if r["user_id"] else None,
            action=ACTION_MAP.get(r["action"], r["action"]),
            module=MODULE_MAP.get(r["module"], r["module"]),
            target="",
            ip=r["ip"] or None,
            result="success",
            detail=r["description"] or None,
            created_at=parse_dt(r["created_at"]) if r["created_at"] else None,
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_predictions(db) -> int:
    if db.query(F.count(SalesPrediction.id)).filter(SalesPrediction.model_name == CRAWLED_MODEL).scalar():
        return 0
    rows = []
    for r in load_csv("sales_prediction.csv"):
        rows.append(SalesPrediction(
            car_id=int(r["car_id"]),
            prediction_month=parse_month(r["month"]),
            predicted_sales=to_int(r["predicted_sales"]),
            lower=to_int(r["lower_bound"]),
            upper=to_int(r["upper_bound"]),
            model_name=CRAWLED_MODEL,
            accuracy=to_float(r["confidence"], 0.9),
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_recommendations(db) -> int:
    """爬虫推荐知识库：场景（城市+预算+用途）→ 真实车型排序，供 /recommend 命中返回"""
    if db.query(F.count(Recommendation.id)).filter(Recommendation.model_name == CRAWL_REC_MODEL).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("recommendation_data.csv"):
        cid = int(r["car_id"])
        if cid not in car_ids:
            continue
        scenario_hash = hashlib.md5(
            json.dumps([r["city"], r["budget"], r["purpose"]], ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        rows.append(Recommendation(
            request_hash=scenario_hash,
            request_body={"city": r["city"], "budget": r["budget"], "purpose": r["purpose"], "focus": r["focus"]},
            car_id=cid,
            score=round(to_float(r["match_score"]) * 10, 1),  # 0~10 → 0~100
            rank_no=max(to_int(r["rank"], 1), 1),
            model_name=CRAWL_REC_MODEL,
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def backfill(db) -> None:
    """回填聚合快照：车型销量/排名、品牌车型数/年销/权重"""
    cars = db.query(Car).all()
    series: dict[int, dict[str, int]] = {}
    for car_id, m, s in db.query(CarSales.car_id, CarSales.month, CarSales.sales).all():
        series.setdefault(car_id, {})[m.strftime("%Y-%m")] = int(s or 0)
    months = sorted({m for vals in series.values() for m in vals})
    last12 = months[-12:]
    last_month = months[-1]

    ranked = sorted(cars, key=lambda c: sum(series.get(c.id, {}).get(m, 0) for m in last12), reverse=True)
    for rank, car in enumerate(ranked, start=1):
        car.sales_12m = sum(series.get(car.id, {}).get(m, 0) for m in last12)
        car.last_month_sales = series.get(car.id, {}).get(last_month, 0)
        car.rank = rank
    db.commit()

    brand_series: dict[int, dict[str, int]] = {}
    for bid, m, s in db.query(BrandSales.brand_id, BrandSales.month, BrandSales.sales).all():
        brand_series.setdefault(bid, {})[m.strftime("%Y-%m")] = int(s or 0)
    total_annual = 0
    for brand in db.query(Brand).all():
        vals = brand_series.get(brand.id, {})
        annual = sum(vals.get(m, 0) for m in last12)
        brand.annual_sales = annual
        brand.model_count = sum(1 for c in cars if c.brand_id == brand.id)
        total_annual += annual
    db.commit()
    for brand in db.query(Brand).all():
        if total_annual:
            brand.weight = round(brand.annual_sales / total_annual * 1000, 1)
    db.commit()


def wipe(db) -> None:
    print("⚠ 清空业务数据表…")
    for model in (Sentiment, Review, SalesPrediction, Recommendation, Order, Inventory,
                  OperationLog, RegionalSales, EnergySales, BrandSales, CarSales,
                  ModelAlias, Car, User, Brand):
        db.query(model).delete()
    db.commit()


def main():
    parser = argparse.ArgumentParser(description="导入真实爬取数据（data/real/*.csv）")
    parser.add_argument("--fresh", action="store_true", help="清空业务数据后重新导入")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.fresh:
            wipe(db)
        elif db.query(F.count(Car.id)).scalar():
            print("数据库已有车型数据（演示种子或已导入的真实数据）。")
            print("真实数据导入需要干净的业务表，请加 --fresh 重新导入。")
            return

        # 地区维表沿用种子数据（34 省级行政区 + 权重/渗透率）
        if not db.query(F.count(Region.id)).scalar():
            from scripts.seed_demo import import_regions
            import_regions(db)
            print(f"地区维表: {db.query(F.count(Region.id)).scalar()} 条")

        # 算法任务/数据文件登记为系统演示数据，空表时补齐
        if not db.query(F.count(AlgorithmTask.id)).scalar():
            from scripts.seed_demo import import_algorithms
            import_algorithms(db)
            print(f"算法任务: {db.query(F.count(AlgorithmTask.id)).scalar()} 条（系统演示）")
        if not db.query(F.count(DataFile.id)).scalar():
            from scripts.seed_demo import import_data_files
            import_data_files(db)
            print(f"数据文件: {db.query(F.count(DataFile.id)).scalar()} 条（系统演示）")

        print(f"品牌导入: {import_brands(db)} 条")
        print(f"车型导入: {import_cars(db)} 款")
        print(f"车型月销: {import_car_sales(db)} 行")
        print(f"品牌月销: {import_brand_sales(db)} 行")
        print(f"能源月销: {import_energy_sales(db)} 行")
        print(f"地区月销: {import_regional_sales(db)} 行")
        print(f"用户导入: {import_users(db)} 条（密码统一重置为 用户名+123）")
        print(f"评价导入: {import_reviews(db)} 条（含情感标注）")
        print(f"订单导入: {import_orders(db)} 条（completed→delivered）")
        print(f"库存导入: {import_inventory(db)} 条")
        print(f"操作日志: {import_logs(db)} 条")
        print(f"预测导入: {import_predictions(db)} 行（20 款车型 × 6 个月）")
        print(f"推荐导入: {import_recommendations(db)} 行（真实推荐知识库）")

        backfill(db)
        print("聚合回填: 车型销量/排名、品牌年销/车型数 完成")

        db.add(CollectionLog(
            source="sj.zip 爬虫采集",
            collected_at=datetime.now(),
            data_period="2025-01 ~ 2026-06",
            record_count=(
                db.query(F.count(CarSales.id)).scalar()
                + db.query(F.count(Review.id)).scalar()
                + db.query(F.count(Order.id)).scalar()
            ),
            passed_count=db.query(F.count(Car.id)).scalar(),
            status="success",
        ))
        db.commit()
    print("✅ 真实数据接入完成（admin/admin123 登录）")


if __name__ == "__main__":
    main()
