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
import subprocess
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

CRAWLED_MODEL = "真实模型预测（导入数据）"
CRAWL_REC_MODEL = "真实推荐知识库（导入数据）"

# 前端登录页提供的固定演示账号。生产环境中仍走真实 JWT + RBAC，绝不走 Mock 登录。
DEMO_USERS = (
    ("admin", "管理员", "admin"),
    ("analyst", "数据分析师", "analyst"),
    ("sales", "销售运营", "sales"),
    ("user", "普通用户", "user"),
)


def load_csv(name: str) -> list[dict[str, str]]:
    with open(REAL_DIR / name, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_month(value: str) -> date:
    value = str(value).strip()[:7]
    year, month = value.split("-")[:2]
    return date(int(year), int(month), 1)


def parse_dt(value: str):
    value = str(value).strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def match_region(value: str, names: list[str]) -> str | None:
    value = str(value).strip()
    if value in names:
        return value
    for name in names:
        if value in name or name.replace("省", "") == value.replace("省", ""):
            return name
    return None


def import_brands(db) -> int:
    if db.query(F.count(Brand.id)).scalar():
        return 0
    rows = []
    for r in load_csv("brand.csv"):
        rows.append(Brand(
            id=to_int(r.get("brand_id")),
            name=r.get("brand_name", ""),
            name_en=r.get("brand_name_en", ""),
            country=r.get("country", ""),
            group=r.get("group") or GROUP_MAP.get(r.get("brand_name", ""), "自主"),
            logo=r.get("logo") or None,
            founded_year=to_int(r.get("founded_year"), 0) or None,
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_cars(db) -> int:
    if db.query(F.count(Car.id)).scalar():
        return 0
    brands = {b.id for b in db.query(Brand.id).all()}
    rows = []
    for r in load_csv("car.csv"):
        brand_id = to_int(r.get("brand_id"))
        if brand_id not in brands:
            continue
        rows.append(Car(
            id=to_int(r.get("car_id")),
            brand_id=brand_id,
            name=r.get("car_name", ""),
            name_norm=r.get("car_name", "").strip().lower(),
            model_code=r.get("model_code") or None,
            category=r.get("category") or "轿车",
            price=to_float(r.get("price")),
            energy_type=ENERGY_MAP.get(r.get("energy_type", ""), r.get("energy_type") or "ICE"),
            seats=to_int(r.get("seats"), 5),
            image=r.get("image") or None,
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_car_sales(db) -> int:
    if db.query(F.count(CarSales.id)).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("car_monthly_sales.csv"):
        cid = to_int(r.get("car_id"))
        if cid not in car_ids:
            continue
        rows.append(CarSales(car_id=cid, month=parse_month(r["month"]), sales=to_int(r["sales"])))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_brand_sales(db) -> int:
    if db.query(F.count(BrandSales.id)).scalar():
        return 0
    brand_ids = {b.id for b in db.query(Brand.id).all()}
    rows = []
    for r in load_csv("brand_monthly_sales.csv"):
        bid = to_int(r.get("brand_id"))
        if bid not in brand_ids:
            continue
        rows.append(BrandSales(brand_id=bid, month=parse_month(r["month"]), sales=to_int(r["sales"])))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_energy_sales(db) -> int:
    if db.query(F.count(EnergySales.id)).scalar():
        return 0
    rows = [
        EnergySales(energy_type=ENERGY_MAP[r["energy_type"]], month=parse_month(r["month"]), sales=to_int(r["sales"])))
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


def ensure_demo_users(db) -> int:
    """确保登录页展示的四个演示账号始终存在且与 RBAC 角色一致。

    真实数据 user.csv 中只有 admin，且原密码是 MD5，无法直接用于 bcrypt。
    这里对四个固定演示账号做幂等 upsert：已有账号只修正密码/角色/状态，不创建重复用户。
    """
    changed = 0
    for username, nickname, role in DEMO_USERS:
        user = db.query(User).filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                nickname=nickname,
                email=f"{username}@autoinsight.com",
                password_hash=hash_password(f"{username}123"),
                role=role,
                status="active",
            )
            db.add(user)
            changed += 1
            continue

        dirty = False
        if user.password_hash and not verify_demo_password_placeholder(user.password_hash, username):
            user.password_hash = hash_password(f"{username}123")
            dirty = True
        if user.role != role:
            user.role = role
            dirty = True
        if user.status != "active":
            user.status = "active"
            dirty = True
        if not user.nickname:
            user.nickname = nickname
            dirty = True
        if not user.email:
            user.email = f"{username}@autoinsight.com"
            dirty = True
        if dirty:
            changed += 1

    db.commit()
    return changed


def verify_demo_password_placeholder(password_hash: str, username: str) -> bool:
    """判断当前哈希是否已经能验证固定演示密码。"""
    from app.core.security import verify_password
    return verify_password(f"{username}123", password_hash)


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
            password_hash=hash_password(f"{username}123"),
            role=r["role"] if r["role"] in ("admin", "analyst", "sales", "user") else "user",
            status="active",
        ))
        count += 1
    db.commit()
    return count + ensure_demo_users(db)


def import_reviews(db) -> int:
    if db.query(F.count(Review.id)).filter(Review.source == "crawl").scalar():
        return 0
    cars = {c.id for c in db.query(Car.id).all()}
    reviews = []
    for r in load_csv("user_review.csv"):
        cid = int(r["car_id"])
        if cid not in cars:
            continue
        reviews.append(Review(
            car_id=cid,
            user_id=int(r["user_id"]) if r["user_id"] else None,
            content=r["content"],
            rating=to_float(r["rating"], 4.0),
            source="crawl",
            created_at=parse_dt(r["created_at"]) if r["created_at"] else datetime.now(),
        ))
    db.bulk_save_objects(reviews)
    db.commit()

    src_by_content = {r["content"]: r for r in load_csv("user_review.csv")}
    for review in db.query(Review).filter(Review.source == "crawl").all():
        src = src_by_content.get(review.content)
        if not src:
            continue
        # 保持现有情感标注逻辑
        review.sentiment = src.get("sentiment") or None
    db.commit()
    return len(reviews)


def import_orders(db) -> int:
    if db.query(F.count(Order.id)).scalar():
        return 0
    user_ids = {u.id for u in db.query(User.id).all()}
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("order.csv"):
        uid = to_int(r.get("user_id"))
        cid = to_int(r.get("car_id"))
        if uid not in user_ids or cid not in car_ids:
            continue
        rows.append(Order(
            id=to_int(r.get("order_id")),
            user_id=uid,
            car_id=cid,
            amount=to_float(r.get("amount")) / 10000,
            status=ORDER_STATUS_MAP.get(r.get("status", ""), r.get("status") or "pending"),
            created_at=parse_dt(r.get("created_at")) or datetime.now(),
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_inventory(db) -> int:
    if db.query(F.count(Inventory.id)).scalar():
        return 0
    car_ids = {c.id for c in db.query(Car.id).all()}
    rows = []
    for r in load_csv("inventory.csv"):
        cid = to_int(r.get("car_id"))
        if cid not in car_ids:
            continue
        rows.append(Inventory(
            car_id=cid,
            warehouse=r.get("warehouse") or "总部仓",
            stock=to_int(r.get("stock")),
            updated_at=parse_dt(r.get("updated_at")) or datetime.now(),
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_logs(db) -> int:
    if db.query(F.count(OperationLog.id)).filter(OperationLog.source == "crawl").scalar():
        return 0
    user_ids = {u.id for u in db.query(User.id).all()}
    rows = []
    for r in load_csv("system_log.csv"):
        uid = to_int(r.get("user_id")) or None
        if uid not in user_ids:
            uid = None
        action = ACTION_MAP.get(r.get("action", ""), r.get("action") or "系统操作")
        module = MODULE_MAP.get(r.get("module", ""), r.get("module") or "系统")
        rows.append(OperationLog(
            user_id=uid,
            action=action,
            module=module,
            detail=r.get("detail") or None,
            ip=r.get("ip") or None,
            created_at=parse_dt(r.get("created_at")) or datetime.now(),
            source="crawl",
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
            score=round(to_float(r["match_score"]) * 10, 1),
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
    if not months:
        return
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


def migrate_schema() -> None:
    root = Path(__file__).resolve().parents[1]
    print("数据库结构迁移: alembic upgrade head")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description="导入真实爬取数据（data/real/*.csv）")
    parser.add_argument("--fresh", action="store_true", help="清空业务数据后重新导入")
    args = parser.parse_args()

    migrate_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.fresh:
            wipe(db)
        elif db.query(F.count(Car.id)).scalar():
            print("数据库已有车型数据（演示种子或已导入的真实数据）。")
            print("真实数据导入需要干净的业务表，请加 --fresh 重新导入。")
            # 即使业务数据已经导入，也必须保证登录页的四个固定账号存在。
            fixed = ensure_demo_users(db)
            print(f"演示账号校验: {fixed} 个账号已创建/修正")
            return

        if not db.query(F.count(Region.id)).scalar():
            from scripts.seed_demo import import_regions
            import_regions(db)
            print(f"地区维表: {db.query(F.count(Region.id)).scalar()} 条")

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
    print("✅ 真实数据接入完成")


if __name__ == "__main__":
    main()
