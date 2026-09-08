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
    data = resp.json()
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
    data = resp.json()
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
    data = resp.json()
    assert {"list", "total", "page", "pageSize"} <= set(data)
    assert data["total"] >= 100
    assert CAR_KEYS <= set(data["list"][0])
    assert len(data["list"][0]["launchDate"]) == 7  # YYYY-MM


def test_cars_filters(client, token):
    resp = client.get("/api/cars", params={"keyword": "秦", "energyType": "PHEV"}, headers=auth(token))
    assert resp.status_code == 200
    for item in resp.json()["list"]:
        assert item["energyType"] in ("PHEV", "BEV")


def test_cars_options(client, token):
    resp = client.get("/api/cars/options", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"brands", "energies", "categories", "years", "priceBuckets", "regions", "months"} <= set(data)
    assert isinstance(data["regions"][0], str)
    assert isinstance(data["categories"][0], str)


def test_car_detail_and_sales(client, token):
    resp = client.get("/api/cars/1", headers=auth(token))
    assert resp.status_code == 200
    assert CAR_KEYS <= set(resp.json())

    resp = client.get("/api/cars/1/sales", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"carId", "carName", "points", "yoy"} <= set(data)
    assert len(data["points"]) == 18
    assert len(data["yoy"]) == 18  # 逐月同比数组


def test_car_similar(client, token):
    resp = client.get("/api/cars/1/similar", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 4
    assert CAR_KEYS <= set(data[0])


def test_car_reviews(client, token):
    resp = client.get("/api/cars/1/reviews", headers=auth(token))
    assert resp.status_code == 200
    assert {"list", "total", "page", "pageSize"} <= set(resp.json())


def test_car_crud(client, token):
    headers = auth(token)
    body = {"brandId": 1, "name": "测试车型", "category": "SUV", "energyType": "BEV", "price": 19.9}
    resp = client.post("/api/cars", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    car = resp.json()
    assert car["name"] == "测试车型" and car["brand"] == "比亚迪"

    resp = client.put(f"/api/cars/{car['id']}", json={"price": 18.8}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["price"] == 18.8

    resp = client.delete(f"/api/cars/{car['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"id": car["id"]}


# ============================ Dashboard ============================

def test_dashboard_overview(client, token):
    resp = client.get("/api/dashboard/overview", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"metrics", "hotBrands", "updatedAt"} <= set(data)
    assert len(data["metrics"]) == 5
    for m in data["metrics"]:
        assert {"key", "label", "value", "unit", "change", "trend", "tone"} <= set(m)
    assert len(data["hotBrands"]) == 8
    assert {"name", "value", "share", "yoy"} <= set(data["hotBrands"][0])


def test_dashboard_trend(client, token):
    resp = client.get("/api/dashboard/trend", params={"span": 18}, headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"months", "total", "nev", "ice", "yoy"} <= set(data)
    assert len(data["months"]) == 18
    assert all(len(data[k]) == 18 for k in ("total", "nev", "ice", "yoy"))


def test_dashboard_rankings(client, token):
    resp = client.get("/api/dashboard/brand-ranking", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 10
    assert {"name", "value", "share", "yoy"} <= set(items[0])

    resp = client.get("/api/dashboard/car-ranking", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 10
    assert {"name", "value", "extra"} <= set(items[0])


def test_dashboard_energy_region_price_growth_scatter(client, token):
    headers = auth(token)

    data = client.get("/api/dashboard/energy", headers=headers).json()
    assert {"proportion", "monthly"} <= set(data)
    assert len(data["proportion"]) == 4

    data = client.get("/api/dashboard/region", headers=headers).json()
    assert {"regions", "topPenetration"} <= set(data)
    assert {"name", "value", "yoy", "penetration"} <= set(data["regions"][0])

    data = client.get("/api/dashboard/price", headers=headers).json()
    assert len(data["buckets"]) == 6

    data = client.get("/api/dashboard/growth", headers=headers).json()
    assert {"months", "marketSize", "growth"} <= set(data)

    data = client.get("/api/dashboard/scatter", headers=headers).json()
    assert {"name", "brand", "price", "sales", "rating", "energyType"} <= set(data[0])


# ============================ 市场分析 ============================

def test_market_options(client, token):
    resp = client.get("/api/market/options", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"years", "months", "brands", "energies", "categories", "regions", "updatedAt"} <= set(data)


def test_market_trend(client, token):
    resp = client.get("/api/market/trend", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"months", "series"} <= set(data)
    assert [s["name"] for s in data["series"]] == ["总销量", "新能源", "燃油车"]


def test_market_share_penetration(client, token):
    data = client.get("/api/market/share", headers=auth(token)).json()
    assert {"months", "series"} <= set(data)
    assert data["series"][-1]["name"] == "其他"

    data = client.get("/api/market/penetration", headers=auth(token)).json()
    assert {"months", "values"} <= set(data)


def test_market_region_energy_price(client, token):
    headers = auth(token)
    data = client.get("/api/market/region", headers=headers).json()
    assert isinstance(data, list) and len(data) > 20
    assert {"name", "value", "yoy", "penetration"} <= set(data[0])

    data = client.get("/api/market/energy", headers=headers).json()
    assert {"name", "value", "ratio"} <= set(data[0])

    data = client.get("/api/market/price", headers=headers).json()
    assert {"label", "value"} <= set(data[0])


def test_market_brand_rank_category(client, token):
    headers = auth(token)
    data = client.get("/api/market/brand-rank", headers=headers).json()
    assert {"name", "value", "share", "yoy"} <= set(data[0])

    data = client.get("/api/market/category", headers=headers).json()
    assert {"name", "value", "ratio"} <= set(data[0])

    data = client.get("/api/market/category-trend", headers=headers).json()
    assert {"months", "series"} <= set(data)


# ============================ 销量 ============================

def test_sales_list(client, token):
    resp = client.get("/api/sales", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"list", "total", "page", "pageSize"} <= set(data)
    row = data["list"][0]
    assert {"id", "carId", "carName", "brand", "month", "sales", "revenue", "region", "energyType"} <= set(row)


def test_sales_trend_ranking_region(client, token):
    headers = auth(token)
    data = client.get("/api/sales/trend", headers=headers).json()
    assert {"months", "series"} <= set(data)

    data = client.get("/api/sales/ranking", headers=headers).json()
    assert {"name", "value", "share", "yoy"} <= set(data[0])

    data = client.get("/api/sales/region", headers=headers).json()
    assert {"name", "value"} <= set(data[0])


# ============================ 预测 ============================

def test_predict_sales(client, token):
    resp = client.get("/api/predict/sales", params={"carId": 1, "horizon": 6}, headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
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
    data = resp.json()
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
    data = resp.json()
    assert {"requestId", "model", "generatedAt", "isMock", "recommendations"} <= set(data)
    assert len(data["recommendations"]) == 5
    rec = data["recommendations"][0]
    assert {"carId", "carName", "brand", "score", "reason", "price", "energyType",
            "range", "rating", "dimensions", "highlights"} <= set(rec)
    assert rec["score"] >= data["recommendations"][-1]["score"]  # 降序


# ============================ 舆情 ============================

def test_sentiment_overview_trend_keywords(client, token):
    headers = auth(token)
    data = client.get("/api/sentiment", headers=headers).json()
    assert {"total", "positive", "neutral", "negative", "positiveRate", "avgScore", "updatedAt"} <= set(data)
    assert data["total"] == data["positive"] + data["neutral"] + data["negative"]

    data = client.get("/api/sentiment/trend", headers=headers).json()
    assert {"months", "positive", "neutral", "negative"} <= set(data)

    data = client.get("/api/sentiment/keywords", headers=headers).json()
    assert {"word", "count", "sentiment", "weight"} <= set(data[0])

    data = client.get("/api/sentiment/brand-reputation", headers=headers).json()
    assert {"brand", "score", "positiveRate", "mentionCount", "delta"} <= set(data[0])


def test_reviews(client, token):
    resp = client.get("/api/reviews", params={"sentiment": "positive"}, headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"list", "total", "page", "pageSize"} <= set(data)
    for item in data["list"]:
        assert item["sentiment"] == "positive"


# ============================ 管理后台 ============================

def test_admin_overview(client, token):
    resp = client.get("/api/admin/overview", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert {"todaySales", "monthSales", "inventory", "newUsers", "newOrders",
            "recommendCount", "predictTasks", "deltas", "updatedAt"} <= set(data)


def test_admin_charts(client, token):
    headers = auth(token)
    data = client.get("/api/admin/sales-trend", headers=headers).json()
    assert {"months", "sales", "orders"} <= set(data)
    assert len(data["months"]) == 12

    data = client.get("/api/admin/order-status", headers=headers).json()
    assert {"name", "value"} <= set(data[0])

    data = client.get("/api/admin/car-ranking", headers=headers).json()
    assert {"name", "value", "brand"} <= set(data[0])

    data = client.get("/api/admin/inventory-trend", headers=headers).json()
    assert {"months", "data"} <= set(data)


def test_admin_users_flow(client, token):
    headers = auth(token)
    resp = client.get("/api/admin/users", params={"role": "admin"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert {"list", "total", "page", "pageSize"} <= set(data)
    user = data["list"][0]
    assert {"id", "username", "nickname", "email", "role", "status", "createdAt", "carCount"} <= set(user)

    resp = client.put(f"/api/admin/users/{user['id']}", json={"department": "数据部"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["department"] == "数据部"

    resp = client.patch(f"/api/admin/users/{user['id']}/status", json={"status": "active"}, headers=headers)
    assert resp.status_code == 200


def test_admin_brands_cars_sales(client, token):
    headers = auth(token)
    data = client.get("/api/admin/brands", headers=headers).json()
    assert {"list", "total"} <= set(data)
    assert {"id", "name", "nameEn", "group", "annualSales"} <= set(data["list"][0])

    data = client.get("/api/admin/cars", headers=headers).json()
    assert {"list", "total"} <= set(data)
    assert CAR_KEYS <= set(data["list"][0])

    data = client.get("/api/admin/sales", headers=headers).json()
    row = data["list"][0]
    assert {"carId", "carName", "brand", "months", "values", "total"} <= set(row)
    assert len(row["months"]) == len(row["values"])


def test_admin_inventory_orders(client, token):
    headers = auth(token)
    data = client.get("/api/admin/inventory", headers=headers).json()
    assert {"id", "carId", "carName", "quantity", "turnoverDays", "warehouse", "status"} <= set(data["list"][0])

    data = client.get("/api/admin/orders", headers=headers).json()
    assert {"id", "orderNo", "carName", "customer", "amount", "status", "region", "createdAt", "salesperson"} <= set(data["list"][0])
    assert data["list"][0]["status"] in ("pending", "paid", "delivered", "cancelled")


def test_admin_algorithms_logs_data_files(client, token):
    headers = auth(token)
    data = client.get("/api/admin/algorithms", headers=headers).json()
    assert isinstance(data, list) and len(data) == 6
    assert {"id", "name", "type", "model", "version", "accuracy", "status", "lastRunAt", "calls", "owner"} <= set(data[0])
    assert data[0]["type"] in ("推荐", "预测", "舆情")

    task_id = data[0]["id"]
    resp = client.patch(f"/api/admin/algorithms/{task_id}/status", json={"status": "idle"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"

    data = client.get("/api/admin/logs", headers=headers).json()
    assert {"id", "operator", "action", "module", "ip", "result", "createdAt"} <= set(data["list"][0])

    data = client.get("/api/admin/data-files", headers=headers).json()
    assert {"id", "name", "size", "type", "status", "progress", "uploadedAt"} <= set(data[0])

    resp = client.post("/api/admin/data/upload", json={"name": "t.csv", "size": 1024, "type": "销量数据"}, headers=headers)
    assert resp.status_code == 200
    file_id = resp.json()["id"]
    resp = client.delete(f"/api/admin/data-files/{file_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"id": file_id}


# ============================ 生产前修复项 ============================

from datetime import date  # noqa: E402

from sqlalchemy import func as F  # noqa: E402

from app.models import Brand, Car, CarSales, Region, RegionalSales, SalesPrediction  # noqa: E402


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
        for c in client.get("/api/cars", params={"brandId": 2, "pageSize": 100}, headers=auth(token)).json()["list"]
    }
    assert brand2_ids

    data = client.get("/api/sales", params={"brandId": 2, "span": 18, "pageSize": 500}, headers=auth(token)).json()
    assert data["total"] > 0
    ids = {r["carId"] for r in data["list"]}
    assert ids <= brand2_ids, f"brandId=2 返回了其他品牌的车型: {sorted(ids - brand2_ids)}"
    assert 2 not in ids or 2 in brand2_ids  # car_id==2 属于品牌1，不允许混入


def test_sales_trend_brandid_scope(client, token):
    """P0-1：/sales/trend 的 brandId 同样只统计该品牌车型（品牌量之和不超过全国量）"""
    nat = client.get("/api/sales/trend", params={"span": 12}, headers=auth(token)).json()["series"][0]["data"]
    b1 = client.get("/api/sales/trend", params={"span": 12, "brandId": 1}, headers=auth(token)).json()["series"][0]["data"]
    b2 = client.get("/api/sales/trend", params={"span": 12, "brandId": 2}, headers=auth(token)).json()["series"][0]["data"]
    assert len(nat) == len(b1) == len(b2)
    assert 0 < sum(b1) < sum(nat)
    assert 0 < sum(b2) < sum(nat)
    assert sum(b1) + sum(b2) <= sum(nat)


def test_time_window_contains_only_real_months(client, token):
    """P0-2：span 超过数据长度时不得构造不存在的月份（当前真实范围 2025-01~2026-06；
    测试库为种子数据 24 个月，断言一律等于 CarSales 实际月份集合）"""
    avail = _available_months()
    assert avail

    trend = client.get("/api/dashboard/trend", params={"span": 60}, headers=auth(token)).json()
    assert trend["months"] == avail
    assert len(trend["total"]) == len(avail)

    cat = client.get("/api/market/category-trend", params={"span": 60}, headers=auth(token)).json()
    assert cat["months"] == avail

    trend12 = client.get("/api/dashboard/trend", params={"span": 12}, headers=auth(token)).json()
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

    api = client.get("/api/dashboard/car-ranking", headers=auth(token)).json()
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

    dash = client.get("/api/dashboard/region", params={"span": 12}, headers=auth(token)).json()["regions"]
    market = client.get("/api/market/region", params={"span": 12}, headers=auth(token)).json()

    dash_map = {i["name"]: i["value"] for i in dash}
    market_map = {i["name"]: i["value"] for i in market}
    assert dash_map == expected
    assert market_map == expected  # 同一地区同一窗口，两个页面同一套口径


def test_prediction_fallback_not_labeled_as_model(client, token):
    """P1-5：无真实模型结果时必须走 fallback 且不得冒充 XGBoost；落库标识可区分"""
    resp = client.get("/api/predict/sales", params={"carId": 1, "horizon": 6}, headers=auth(token)).json()
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
