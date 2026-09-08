"""pytest 契约测试：以 sqlite 内存库跑种子数据，验证 API 与前端 Mock 数据结构兼容

字段命名与结构断言对齐 src/types/{api,business,dashboard}.ts 与 src/mock/*。
另覆盖生产前修复项：brandId 筛选、真实时间窗口、CarSales 排行口径、
RegionalSales 地区口径、预测 fallback 标识、Alembic 迁移。
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database.session import Base, get_db
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

# client fixture 内注入，供需要直查数据库断言的测试使用
_TestSession = None


@pytest.fixture(scope="module")
def client():
    global _TestSession
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _TestSession = TestingSession

    # 导入种子数据（确定性生成）
    from scripts.seed_demo import (
        import_algorithms,
        import_brands,
        import_cars,
        import_data_files,
        import_inventory,
        import_logs,
        import_orders,
        import_predictions,
        import_regional,
        import_reviews,
        import_sales,
        import_users,
    )

    with TestingSession() as db:
        from scripts.seed_demo import (
            import_algorithms,
            import_brands,
            import_cars,
            import_data_files,
            import_inventory,
            import_logs,
            import_orders,
            import_predictions,
            import_regions,
            import_regional,
            import_reviews,
            import_sales,
            import_users,
        )

        import_brands(db)
        import_regions(db)
        import_cars(db)
        import_users(db)
        import_sales(db)
        import_regional(db)
        import_inventory(db)
        import_orders(db)
        import_algorithms(db)
        import_logs(db)
        import_data_files(db)
        import_reviews(db)
        import_predictions(db)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"token", "refreshToken", "expiresIn", "user"} <= set(data)
    assert {"id", "username", "nickname", "email", "role", "status", "createdAt"} <= set(data["user"])
    return data["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ============================ 认证 ============================

def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 401


def test_users_me(client, token):
    resp = client.get("/api/users/me", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert "phone" in data and "department" in data


# ============================ 车型 ============================

CAR_KEYS = {
    "id", "brandId", "brand", "name", "modelCode", "category", "energyType",
    "price", "priceMin", "priceMax", "range", "battery", "power", "torque",
    "wheelbase", "length", "width", "height", "seats", "launchDate", "launchYear",
    "sales", "lastMonthSales", "rating", "intelligenceScore", "comfortScore",
    "spaceScore", "performanceScore", "reviewCount", "tags", "rank",
}


def test_cars_list(client, token):
    resp = client.get("/api/cars", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"list", "total", "page", "pageSize"} <= set(data)
    assert data["total"] >= 100
    assert CAR_KEYS <= set(data["list"][0])
    assert len(data["list"][0]["launchDate"]) == 7  # YYYY-MM


def test_cars_filters(client, token):
    resp = client.get("/api/cars", params={"keyword": "秦", "energyType": "PHEV"}, headers=auth(token))
    assert resp.status_code == 200
    for item in resp.json()["data"]["list"]:
        assert item["energyType"] in ("PHEV", "BEV")


def test_cars_options(client, token):
    resp = client.get("/api/cars/options", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"brands", "energies", "categories", "years", "priceBuckets", "regions", "months"} <= set(data)
    assert isinstance(data["regions"][0], str)
    assert isinstance(data["categories"][0], str)


def test_car_detail_and_sales(client, token):
    resp = client.get("/api/cars/1", headers=auth(token))
    assert resp.status_code == 200
    assert CAR_KEYS <= set(resp.json()["data"])

    resp = client.get("/api/cars/1/sales", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"carId", "carName", "points", "yoy"} <= set(data)
    assert len(data["points"]) == 18
    assert len(data["yoy"]) == 18  # 逐月同比数组


def test_car_similar(client, token):
    resp = client.get("/api/cars/1/similar", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list) and len(data) == 4
    assert CAR_KEYS <= set(data[0])


def test_car_reviews(client, token):
    resp = client.get("/api/cars/1/reviews", headers=auth(token))
    assert resp.status_code == 200
    assert {"list", "total", "page", "pageSize"} <= set(resp.json()["data"])


def test_car_crud(client, token):
    headers = auth(token)
    body = {"brandId": 1, "name": "测试车型", "category": "SUV", "energyType": "BEV", "price": 19.9}
    resp = client.post("/api/cars", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    car = resp.json()["data"]
    assert car["name"] == "测试车型" and car["brand"] == "比亚迪"

    resp = client.put(f"/api/cars/{car['id']}", json={"price": 18.8}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["price"] == 18.8

    resp = client.delete(f"/api/cars/{car['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == {"id": car["id"]}


# ============================ Dashboard ============================

def test_dashboard_overview(client, token):
    resp = client.get("/api/dashboard/overview", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"metrics", "hotBrands", "updatedAt"} <= set(data)
    assert len(data["metrics"]) == 5
    for m in data["metrics"]:
        assert {"key", "label", "value", "unit", "change", "trend", "tone"} <= set(m)
    assert len(data["hotBrands"]) == 8
    assert {"name", "value", "share", "yoy"} <= set(data["hotBrands"][0])


def test_dashboard_trend(client, token):
    resp = client.get("/api/dashboard/trend", params={"span": 18}, headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"months", "total", "nev", "ice", "yoy"} <= set(data)
    assert len(data["months"]) == 18
    assert all(len(data[k]) == 18 for k in ("total", "nev", "ice", "yoy"))


def test_dashboard_rankings(client, token):
    resp = client.get("/api/dashboard/brand-ranking", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 10
    assert {"name", "value", "share", "yoy"} <= set(items[0])

    resp = client.get("/api/dashboard/car-ranking", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 10
    assert {"name", "value", "extra"} <= set(items[0])


def test_dashboard_energy_region_price_growth_scatter(client, token):
    headers = auth(token)

    data = client.get("/api/dashboard/energy", headers=headers).json()["data"]
    assert {"proportion", "monthly"} <= set(data)
    assert len(data["proportion"]) == 4

    data = client.get("/api/dashboard/region", headers=headers).json()["data"]
    assert {"regions", "topPenetration"} <= set(data)
    assert {"name", "value", "yoy", "penetration"} <= set(data["regions"][0])

    data = client.get("/api/dashboard/price", headers=headers).json()["data"]
    assert len(data["buckets"]) == 6

    data = client.get("/api/dashboard/growth", headers=headers).json()["data"]
    assert {"months", "marketSize", "growth"} <= set(data)

    data = client.get("/api/dashboard/scatter", headers=headers).json()["data"]
    assert {"name", "brand", "price", "sales", "rating", "energyType"} <= set(data[0])


# ============================ 市场分析 ============================

def test_market_options(client, token):
    resp = client.get("/api/market/options", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"years", "months", "brands", "energies", "categories", "regions", "updatedAt"} <= set(data)


def test_market_trend(client, token):
    resp = client.get("/api/market/trend", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"months", "series"} <= set(data)
    assert [s["name"] for s in data["series"]] == ["总销量", "新能源", "燃油车"]


def test_market_share_penetration(client, token):
    data = client.get("/api/market/share", headers=auth(token)).json()["data"]
    assert {"months", "series"} <= set(data)
    assert data["series"][-1]["name"] == "其他"

    data = client.get("/api/market/penetration", headers=auth(token)).json()["data"]
    assert {"months", "values"} <= set(data)


def test_market_region_energy_price(client, token):
    headers = auth(token)
    data = client.get("/api/market/region", headers=headers).json()["data"]
    assert isinstance(data, list) and len(data) > 20
    assert {"name", "value", "yoy", "penetration"} <= set(data[0])

    data = client.get("/api/market/energy", headers=headers).json()["data"]
    assert {"name", "value", "ratio"} <= set(data[0])

    data = client.get("/api/market/price", headers=headers).json()["data"]
    assert {"label", "value"} <= set(data[0])


def test_market_brand_rank_category(client, token):
    headers = auth(token)
    data = client.get("/api/market/brand-rank", headers=headers).json()["data"]
    assert {"name", "value", "share", "yoy"} <= set(data[0])

    data = client.get("/api/market/category", headers=headers).json()["data"]
    assert {"name", "value", "ratio"} <= set(data[0])

    data = client.get("/api/market/category-trend", headers=headers).json()["data"]
    assert {"months", "series"} <= set(data)


# ============================ 销量 ============================

def test_sales_list(client, token):
    resp = client.get("/api/sales", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"list", "total", "page", "pageSize"} <= set(data)
    row = data["list"][0]
    assert {"id", "carId", "carName", "brand", "month", "sales", "revenue", "region", "energyType"} <= set(row)


def test_sales_trend_ranking_region(client, token):
    headers = auth(token)
    data = client.get("/api/sales/trend", headers=headers).json()["data"]
    assert {"months", "series"} <= set(data)

    data = client.get("/api/sales/ranking", headers=headers).json()["data"]
    assert {"name", "value", "share", "yoy"} <= set(data[0])

    data = client.get("/api/sales/region", headers=headers).json()["data"]
    assert {"name", "value"} <= set(data[0])


# ============================ 预测 ============================

def test_predict_sales(client, token):
    resp = client.get("/api/predict/sales", params={"carId": 1, "horizon": 6}, headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"carId", "carName", "brand", "model", "accuracy", "horizon", "history",
            "prediction", "growthRate", "peakMonth", "lowMonth", "isMock", "features"} <= set(data)
    assert len(data["history"]) == 12
    assert len(data["prediction"]) == 6
    point = data["prediction"][0]
    assert {"month", "value", "lower", "upper"} <= set(point)
    assert point["lower"] <= point["value"] <= point["upper"]


def test_predict_invalid_horizon(client, token):
    resp = client.get("/api/predict/sales", params={"carId": 1, "horizon": 5}, headers=auth(token))
    assert resp.status_code == 400


# ============================ 推荐 ============================

def test_recommend_options(client, token):
    resp = client.get("/api/recommend/options", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"budgets", "usages", "concerns", "provinces", "cities", "energies"} <= set(data)


def test_recommend(client, token):
    payload = {
        "budget": "15-20",
        "energyTypes": ["BEV", "PHEV"],
        "scenarios": ["family"],
        "province": "广东省",
        "city": "深圳市",
        "weights": {"price": 80, "range": 60, "performance": 40, "space": 70, "intelligence": 60, "comfort": 50},
        "topN": 5,
    }
    resp = client.post("/api/recommend", json=payload, headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"requestId", "model", "generatedAt", "isMock", "recommendations"} <= set(data)
    assert len(data["recommendations"]) == 5
    rec = data["recommendations"][0]
    assert {"carId", "carName", "brand", "score", "reason", "price", "energyType",
            "range", "rating", "dimensions", "highlights"} <= set(rec)
    assert rec["score"] >= data["recommendations"][-1]["score"]  # 降序


# ============================ 舆情 ============================

def test_sentiment_overview_trend_keywords(client, token):
    headers = auth(token)
    data = client.get("/api/sentiment", headers=headers).json()["data"]
    assert {"total", "positive", "neutral", "negative", "positiveRate", "avgScore", "updatedAt"} <= set(data)
    assert data["total"] == data["positive"] + data["neutral"] + data["negative"]

    data = client.get("/api/sentiment/trend", headers=headers).json()["data"]
    assert {"months", "positive", "neutral", "negative"} <= set(data)

    data = client.get("/api/sentiment/keywords", headers=headers).json()["data"]
    assert {"word", "count", "sentiment", "weight"} <= set(data[0])

    data = client.get("/api/sentiment/brand-reputation", headers=headers).json()["data"]
    assert {"brand", "score", "positiveRate", "mentionCount", "delta"} <= set(data[0])


def test_reviews(client, token):
    resp = client.get("/api/reviews", params={"sentiment": "positive"}, headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"list", "total", "page", "pageSize"} <= set(data)
    for item in data["list"]:
        assert item["sentiment"] == "positive"


# ============================ 管理后台 ============================

def test_admin_overview(client, token):
    resp = client.get("/api/admin/overview", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"todaySales", "monthSales", "inventory", "newUsers", "newOrders",
            "recommendCount", "predictTasks", "deltas", "updatedAt"} <= set(data)


def test_admin_charts(client, token):
    headers = auth(token)
    data = client.get("/api/admin/sales-trend", headers=headers).json()["data"]
    assert {"months", "sales", "orders"} <= set(data)
    assert len(data["months"]) == 12

    data = client.get("/api/admin/order-status", headers=headers).json()["data"]
    assert {"name", "value"} <= set(data[0])

    data = client.get("/api/admin/car-ranking", headers=headers).json()["data"]
    assert {"name", "value", "brand"} <= set(data[0])

    data = client.get("/api/admin/inventory-trend", headers=headers).json()["data"]
    assert {"months", "data"} <= set(data)


def test_admin_users_flow(client, token):
    headers = auth(token)
    resp = client.get("/api/admin/users", params={"role": "admin"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"list", "total", "page", "pageSize"} <= set(data)
    user = data["list"][0]
    assert {"id", "username", "nickname", "email", "role", "status", "createdAt", "carCount"} <= set(user)

    resp = client.put(f"/api/admin/users/{user['id']}", json={"department": "数据部"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["department"] == "数据部"

    resp = client.patch(f"/api/admin/users/{user['id']}/status", json={"status": "active"}, headers=headers)
    assert resp.status_code == 200


def test_admin_brands_cars_sales(client, token):
    headers = auth(token)
    data = client.get("/api/admin/brands", headers=headers).json()["data"]
    assert {"list", "total"} <= set(data)
    assert {"id", "name", "nameEn", "group", "annualSales"} <= set(data["list"][0])

    data = client.get("/api/admin/cars", headers=headers).json()["data"]
    assert {"list", "total"} <= set(data)
    assert CAR_KEYS <= set(data["list"][0])

    data = client.get("/api/admin/sales", headers=headers).json()["data"]
    row = data["list"][0]
    assert {"carId", "carName", "brand", "months", "values", "total"} <= set(row)
    assert len(row["months"]) == len(row["values"])


def test_admin_inventory_orders(client, token):
    headers = auth(token)
    data = client.get("/api/admin/inventory", headers=headers).json()["data"]
    assert {"id", "carId", "carName", "quantity", "turnoverDays", "warehouse", "status"} <= set(data["list"][0])

    data = client.get("/api/admin/orders", headers=headers).json()["data"]
    assert {"id", "orderNo", "carName", "customer", "amount", "status", "region", "createdAt", "salesperson"} <= set(data["list"][0])
    assert data["list"][0]["status"] in ("pending", "paid", "delivered", "cancelled")


def test_admin_algorithms_logs_data_files(client, token):
    headers = auth(token)
    data = client.get("/api/admin/algorithms", headers=headers).json()["data"]
    assert isinstance(data, list) and len(data) == 6
    assert {"id", "name", "type", "model", "version", "accuracy", "status", "lastRunAt", "calls", "owner"} <= set(data[0])
    assert data[0]["type"] in ("推荐", "预测", "舆情")

    task_id = data[0]["id"]
    resp = client.patch(f"/api/admin/algorithms/{task_id}/status", json={"status": "idle"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "idle"

    data = client.get("/api/admin/logs", headers=headers).json()["data"]
    assert {"id", "operator", "action", "module", "ip", "result", "createdAt"} <= set(data["list"][0])

    data = client.get("/api/admin/data-files", headers=headers).json()["data"]
    assert {"id", "name", "size", "type", "status", "progress", "uploadedAt"} <= set(data[0])

    resp = client.post("/api/admin/data/upload", json={"name": "t.csv", "size": 1024, "type": "销量数据"}, headers=headers)
    assert resp.status_code == 200
    file_id = resp.json()["data"]["id"]
    resp = client.delete(f"/api/admin/data-files/{file_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == {"id": file_id}


# ============================ 生产前修复项 ============================

from datetime import date  # noqa: E402

from sqlalchemy import func as F  # noqa: E402

from app.models import (
    Brand,
    Car,
    CarSales,
    Inventory,
    Order,
    Recommendation,
    Region,
    RegionalSales,
    SalesPrediction,
    User,
)  # noqa: E402


def _available_months() -> list[str]:
    """测试库中 CarSales 实际存在的月份（时间轴断言基准）"""
    with _TestSession() as db:
        rows = db.query(CarSales.month).distinct().all()
        return sorted(m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7] for (m,) in rows)


def test_sales_brandid_filters_by_car_brand(client, token):
    """P0-1：/sales 的 brandId 必须经 Car.brand_id 筛选；
    旧 bug 把 brandId 当 CarSales.car_id，brandId=2 时只会命中 car_id==2（属于品牌1）的行"""
    brand2_ids = {
        c["id"]
        for c in client.get("/api/cars", params={"brandId": 2, "pageSize": 100}, headers=auth(token)).json()["data"]["list"]
    }
    assert brand2_ids

    data = client.get("/api/sales", params={"brandId": 2, "span": 18, "pageSize": 500}, headers=auth(token)).json()["data"]
    assert data["total"] > 0
    ids = {r["carId"] for r in data["list"]}
    assert ids <= brand2_ids, f"brandId=2 返回了其他品牌的车型: {sorted(ids - brand2_ids)}"
    assert 2 not in ids or 2 in brand2_ids  # car_id==2 属于品牌1，不允许混入


def test_sales_trend_brandid_scope(client, token):
    """P0-1：/sales/trend 的 brandId 同样只统计该品牌车型（品牌量之和不超过全国量）"""
    nat = client.get("/api/sales/trend", params={"span": 12}, headers=auth(token)).json()["data"]["series"][0]["data"]
    b1 = client.get("/api/sales/trend", params={"span": 12, "brandId": 1}, headers=auth(token)).json()["data"]["series"][0]["data"]
    b2 = client.get("/api/sales/trend", params={"span": 12, "brandId": 2}, headers=auth(token)).json()["data"]["series"][0]["data"]
    assert len(nat) == len(b1) == len(b2)
    assert 0 < sum(b1) < sum(nat)
    assert 0 < sum(b2) < sum(nat)
    assert sum(b1) + sum(b2) <= sum(nat)


def test_time_window_contains_only_real_months(client, token):
    """P0-2：span 超过数据长度时不得构造不存在的月份（当前真实范围 2025-01~2026-06；
    测试库为种子数据 24 个月，断言一律等于 CarSales 实际月份集合）"""
    avail = _available_months()
    assert avail

    trend = client.get("/api/dashboard/trend", params={"span": 60}, headers=auth(token)).json()["data"]
    assert trend["months"] == avail
    assert len(trend["total"]) == len(avail)

    cat = client.get("/api/market/category-trend", params={"span": 60}, headers=auth(token)).json()["data"]
    assert cat["months"] == avail

    trend12 = client.get("/api/dashboard/trend", params={"span": 12}, headers=auth(token)).json()["data"]
    assert trend12["months"] == avail[-12:]


def test_dashboard_car_ranking_matches_carsales_aggregation(client, token):
    """P0-3：车型排行必须等于 CarSales 按最近 12 个真实月份聚合的结果"""
    months = _available_months()[-12:]
    with _TestSession() as db:
        rows = (
            db.query(Brand.name, Car.name, F.sum(CarSales.sales))
            .join(Car, Car.id == CarSales.car_id)
            .join(Brand, Brand.id == Car.brand_id)
            .filter(CarSales.month >= date(int(months[0][:4]), int(months[0][5:7]), 1))
            .filter(CarSales.month <= date(int(months[-1][:4]), int(months[-1][5:7]), 1))
            .group_by(Brand.name, Car.name)
            .all()
        )
    expected = sorted(
        ((f"{bn} {cn}", int(total)) for bn, cn, total in rows),
        key=lambda t: t[1],
        reverse=True,
    )[:10]

    api = client.get("/api/dashboard/car-ranking", headers=auth(token)).json()["data"]
    assert [(i["name"], i["value"]) for i in api] == expected


def test_region_endpoints_use_regional_sales(client, token):
    """P1-4：dashboard 与 market 的地区数据必须同源 RegionalSales，且与 DB 聚合一致"""
    months = set(_available_months()[-12:])
    with _TestSession() as db:
        region_names = {r.id: r.name for r in db.query(Region).all()}
        rows = (
            db.query(RegionalSales.region_id, RegionalSales.month, F.sum(RegionalSales.sales))
            .filter(RegionalSales.energy_type.is_(None), RegionalSales.brand_id.is_(None))
            .group_by(RegionalSales.region_id, RegionalSales.month)
            .all()
        )
    expected: dict[str, int] = {}
    for rid, m, s in rows:
        mk = m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]
        if mk in months:
            expected[region_names[rid]] = expected.get(region_names[rid], 0) + int(s or 0)
    expected = {k: v for k, v in expected.items() if v > 0}

    dash = client.get("/api/dashboard/region", params={"span": 12}, headers=auth(token)).json()["data"]["regions"]
    market = client.get("/api/market/region", params={"span": 12}, headers=auth(token)).json()["data"]

    dash_map = {i["name"]: i["value"] for i in dash}
    market_map = {i["name"]: i["value"] for i in market}
    assert dash_map == expected
    assert market_map == expected  # 同一地区同一窗口，两个页面同一套口径


def test_prediction_fallback_not_labeled_as_model(client, token):
    """P1-5：无真实模型结果时必须走 fallback 且不得冒充 XGBoost；落库标识可区分"""
    resp = client.get("/api/predict/sales", params={"carId": 1, "horizon": 6}, headers=auth(token)).json()["data"]
    assert resp["model"] == "趋势外推（Fallback）"
    assert "XGBoost" not in resp["model"]

    with _TestSession() as db:
        names = {r.model_name for r in db.query(SalesPrediction).filter(SalesPrediction.car_id == 1).all()}
    assert names == {"TrendSeasonal-Fallback"}


def test_alembic_upgrade_head_builds_schema(tmp_path):
    """Alembic：全新环境 alembic upgrade head 能建立完整库结构"""
    db_file = tmp_path / "migration_test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(db_file)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"brands", "cars", "car_sales", "brand_sales", "energy_sales", "regional_sales",
            "users", "orders", "inventories", "reviews", "sentiments",
            "sales_predictions", "operation_logs"} <= tables


def _month_range(month: str):
    from app.utils.series import next_month, parse_month

    return parse_month(month), parse_month(next_month(month))


def test_admin_overview_counts_anchored_to_data_months(client, token):
    """剩余问题①：新增用户/订单按数据月份统计并给出真实环比，不再恒为 0"""
    months = _available_months()
    last, prev = months[-1], (months[-2] if len(months) >= 2 else None)

    def count_in(model_col, month):
        if not month:
            return 0
        start, end = _month_range(month)
        with _TestSession() as db:
            return int(db.query(F.count(model_col)).filter(model_col >= start, model_col < end).scalar() or 0)

    u_last, u_prev = count_in(User.created_at, last), count_in(User.created_at, prev)
    o_last, o_prev = count_in(Order.created_at, last), count_in(Order.created_at, prev)

    api = client.get("/api/admin/overview", headers=auth(token)).json()["data"]
    assert api["newUsers"] == u_last
    assert api["newOrders"] == o_last

    def pct(cur, before):
        return round((cur - before) / before * 100, 1) if before else 0

    assert api["deltas"]["newUsers"] == pct(u_last, u_prev)
    assert api["deltas"]["newOrders"] == pct(o_last, o_prev)


def test_inventory_trend_follows_real_sales_curve(client, token):
    """剩余问题②：库存趋势由真实库存快照 × 真实月度销量比例回推，不再是任意递增系数"""
    months = _available_months()[-12:]
    with _TestSession() as db:
        total = int(db.query(F.sum(Inventory.quantity)).scalar() or 0)
        sales = {
            (m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]): int(s or 0)
            for m, s in db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
        }
    base = sales[months[-1]]
    expected = [round(total * sales[m] / base) for m in months]

    api = client.get("/api/admin/inventory-trend", headers=auth(token)).json()["data"]
    assert api["months"] == months
    assert api["data"] == expected


def test_recommend_prefers_crawled_real_data(client, token):
    """剩余问题③：命中爬虫推荐场景时返回真实排序（model=Crawl-Rec），
    未命中的场景仍走 Fallback，且 fallback 不冒充真实推荐数据"""
    import hashlib
    import json as _json

    scenario_hash = hashlib.md5(
        _json.dumps(["深圳", "10-20万", "家用"], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    with _TestSession() as db:
        db.query(Recommendation).filter(
            Recommendation.model_name == "Crawl-Rec", Recommendation.request_hash == scenario_hash
        ).delete()
        db.add(Recommendation(
            request_hash=scenario_hash,
            request_body={"city": "深圳", "budget": "10-20万", "purpose": "家用", "focus": "续航,智能化"},
            car_id=66, score=91.0, rank_no=1, model_name="Crawl-Rec",
        ))
        db.add(Recommendation(
            request_hash=scenario_hash,
            request_body={"city": "深圳", "budget": "10-20万", "purpose": "家用", "focus": "续航,智能化"},
            car_id=69, score=88.0, rank_no=2, model_name="Crawl-Rec",
        ))
        db.commit()

    payload = {
        "budget": "15-20", "energyTypes": ["BEV"], "scenarios": ["family"],
        "province": "广东省", "city": "深圳市",
        "weights": {"price": 10, "range": 90, "performance": 20, "space": 30, "intelligence": 80, "comfort": 20},
        "topN": 3,
    }
    data = client.post("/api/recommend", json=payload, headers=auth(token)).json()["data"]
    assert data["model"] == "Crawl-Rec（真实推荐数据）"
    assert [r["carId"] for r in data["recommendations"]][:2] == [66, 69]
    scores = [r["score"] for r in data["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert {"carName", "brand", "score", "reason", "dimensions", "highlights"} <= set(data["recommendations"][0])

    # 未命中场景（预算不映射到同一 crawl 档）→ Fallback 标识
    other = client.post("/api/recommend", json={
        "budget": "gt30", "energyTypes": ["BEV"], "scenarios": ["outdoor"],
        "province": "广东省", "city": "深圳市",
        "weights": {"price": 60, "range": 60, "performance": 60, "space": 60, "intelligence": 60, "comfort": 60},
        "topN": 3,
    }, headers=auth(token)).json()["data"]
    assert other["model"] == "AutoRec（Fallback）"
    assert other["model"] != data["model"]


# ============================ 最终验收回归 ============================

def test_sales_energy(client, token):
    """GET /sales/energy：能源占比结构"""
    data = client.get("/api/sales/energy", headers=auth(token)).json()["data"]
    assert isinstance(data, list) and data
    assert {"name", "value", "ratio"} <= set(data[0])
    assert sum(i["ratio"] for i in data) <= 1.01


def test_prediction_edge_cases(client, token):
    """预测：未登录 401 / 不存在 carId 404 / 默认 carId=1 / 非法 horizon 400"""
    assert client.get("/api/predict/sales", params={"carId": 1}).status_code == 401
    assert client.get(
        "/api/predict/sales", params={"carId": 99999, "horizon": 6}, headers=auth(token)
    ).status_code == 404
    default = client.get("/api/predict/sales", params={"horizon": 6}, headers=auth(token)).json()["data"]
    assert default["carId"] == 1
    assert client.get(
        "/api/predict/sales", params={"carId": 1, "horizon": 5}, headers=auth(token)
    ).status_code == 400


def test_auth_role_matrix(client, token):
    """无 token 401 / 普通用户正常访问业务接口 / admin 接口 403 / sales 仅限库存订单 / admin 全通"""
    # 无 token
    assert client.get("/api/cars").status_code == 401
    assert client.get("/api/admin/overview").status_code == 401

    # 普通用户（演示账号 user）
    ut = client.post("/api/auth/login", json={"username": "user", "password": "user123"}).json()["data"]["token"]
    uh = {"Authorization": f"Bearer {ut}"}
    assert client.get("/api/cars", headers=uh).status_code == 200
    assert client.get("/api/dashboard/overview", headers=uh).status_code == 200
    assert client.get("/api/admin/overview", headers=uh).status_code == 403
    assert client.get("/api/admin/users", headers=uh).status_code == 403
    assert client.get("/api/admin/orders", headers=uh).status_code == 403

    # sales 角色（前端 meta：库存/订单允许 admin+sales）
    st = client.post("/api/auth/login", json={"username": "sales", "password": "sales123"}).json()["data"]["token"]
    sh = {"Authorization": f"Bearer {st}"}
    assert client.get("/api/admin/orders", headers=sh).status_code == 200
    assert client.get("/api/admin/inventory", headers=sh).status_code == 200
    assert client.get("/api/admin/users", headers=sh).status_code == 403

    # 管理员全通
    assert client.get("/api/admin/overview", headers=auth(token)).status_code == 200


def test_time_window_literal_18_months(client, token):
    """真实数据范围 2025-01~2026-06：
    最近 12 个月 = 2025-07~2026-06；最近 18 个月 = 2025-01~2026-06；不得出现 2024"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with S() as db:
        db.add(Brand(id=1, name="窗口测试品牌", name_en="WIN"))
        db.add(User(
            id=1, username="admin", nickname="管理员", email="admin@t.local",
            password_hash=hash_password("admin123"), role="admin", status="active",
        ))
        db.add(Car(
            id=1, brand_id=1, name="窗口车型", name_norm="窗口车型", model_code="WIN-001",
            category="轿车", energy_type="BEV", price=10, price_min=9, price_max=11,
            launch_date=date(2024, 1, 1), launch_year=2024,
        ))
        months = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 7)]
        for m in months:
            db.add(CarSales(car_id=1, month=date(int(m[:4]), int(m[5:7]), 1), sales=100))
        db.commit()

    prev_override = app.dependency_overrides.get(get_db)

    def override():
        s = S()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    try:
        t60 = client.get("/api/dashboard/trend", params={"span": 60}, headers=auth(token)).json()["data"]
        assert t60["months"] == months  # 恰好 18 个真实月，无 2024
        t12 = client.get("/api/dashboard/trend", params={"span": 12}, headers=auth(token)).json()["data"]
        assert t12["months"] == months[-12:]  # 2025-07 ~ 2026-06
        assert all(not m.startswith("2024") for m in t60["months"])

        car_sales = client.get("/api/cars/1/sales", params={"span": 18}, headers=auth(token)).json()["data"]
        assert [p["month"] for p in car_sales["points"]] == months
        # 同比：2025 年无上一年数据 → 0；2026 年有 → 可计算（销量恒定则为 0.0，但不是缺失）
        assert car_sales["yoy"][0] == 0
    finally:
        app.dependency_overrides[get_db] = prev_override


def test_no_region_factor_in_source():
    """Region：地区销量唯一真实来源为 RegionalSales，禁止重新引入权重估算"""
    for rel in ("app/api/market.py", "app/api/sales.py", "app/api/dashboard.py", "app/utils/serialize.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "region_factor" not in src, f"{rel} 出现 region_factor"
        assert "Region.weight" not in src, f"{rel} 使用 Region.weight 估算地区销量"


def test_envelope_contract(client, token):
    """成功响应 = {code:0, message, data, timestamp}；401 不泄露内部信息"""
    resp = client.get("/api/cars/options", headers=auth(token))
    body = resp.json()
    assert body["code"] == 0 and "data" in body and "timestamp" in body
    assert resp.headers["content-type"].startswith("application/json")

    unauth = client.get("/api/cars")
    assert unauth.status_code == 401
    raw = unauth.text.lower()
    assert "traceback" not in raw and "sql" not in raw and "secret" not in raw
