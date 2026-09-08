"""端到端冒烟测试：对运行中的后端逐个调用前端会用到的接口"""

import json
import sys

import httpx

BASE = "http://127.0.0.1:8001/api"

failures = []


def check(name: str, resp: httpx.Response, keys=None, is_list=False):
    if resp.status_code != 200:
        failures.append(f"{name}: HTTP {resp.status_code} {resp.text[:200]}")
        print(f"✗ {name}: HTTP {resp.status_code}")
        return None
    data = resp.json()["data"]
    if is_list:
        if not isinstance(data, list) or not data:
            failures.append(f"{name}: 期望非空列表，实际 {type(data).__name__}")
            print(f"✗ {name}: 空或非列表")
            return None
        sample = data[0]
    else:
        sample = data
    if keys:
        missing = keys - set(sample)
        if missing:
            failures.append(f"{name}: 缺字段 {missing}")
            print(f"✗ {name}: 缺字段 {missing}")
            return None
    print(f"✓ {name}")
    return data


c = httpx.Client(timeout=30)

# 登录
r = c.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
token = r.json()["data"]["token"]
H = {"Authorization": f"Bearer {token}"}
print("✓ auth/login")

# 用户中心
check("users/me", c.get(f"{BASE}/users/me", headers=H),
      {"id", "username", "nickname", "email", "phone", "role", "status", "createdAt", "department"})

# 车型
CAR_FIELDS = {"id", "brandId", "brand", "name", "modelCode", "category", "energyType", "price",
              "priceMin", "priceMax", "range", "battery", "power", "torque", "wheelbase",
              "length", "width", "height", "seats", "launchDate", "launchYear", "sales",
              "lastMonthSales", "rating", "intelligenceScore", "comfortScore", "spaceScore",
              "performanceScore", "reviewCount", "tags", "rank"}

data = check("cars list", c.get(f"{BASE}/cars", params={"page": 1, "pageSize": 10}, headers=H),
             {"list", "total", "page", "pageSize"})
if data:
    missing = CAR_FIELDS - set(data["list"][0])
    if missing:
        failures.append(f"cars item: 缺 {missing}")
        print(f"✗ cars item: 缺 {missing}")
    else:
        print("✓ cars item 字段完整")

check("cars/options", c.get(f"{BASE}/cars/options", headers=H),
      {"brands", "energies", "categories", "years", "priceBuckets", "regions", "months"})
check("cars/1", c.get(f"{BASE}/cars/1", headers=H), CAR_FIELDS - {"tags"})
check("cars/1/sales", c.get(f"{BASE}/cars/1/sales", params={"span": 18}, headers=H),
      {"carId", "carName", "points", "yoy"})
check("cars/1/similar", c.get(f"{BASE}/cars/1/similar", headers=H), is_list=True)
check("cars/1/reviews", c.get(f"{BASE}/cars/1/reviews", headers=H), {"list", "total", "page", "pageSize"})

# Dashboard
data = check("dashboard/overview", c.get(f"{BASE}/dashboard/overview", headers=H),
             {"metrics", "hotBrands", "updatedAt"})
if data:
    assert len(data["metrics"]) == 5, "指标卡应为 5 个"
    assert {"name", "value", "share", "yoy"} <= set(data["hotBrands"][0])
    print("✓ dashboard overview 结构")

check("dashboard/trend", c.get(f"{BASE}/dashboard/trend", params={"span": 18}, headers=H),
      {"months", "total", "nev", "ice", "yoy"})
check("dashboard/brand-ranking", c.get(f"{BASE}/dashboard/brand-ranking", headers=H), is_list=True)
check("dashboard/car-ranking", c.get(f"{BASE}/dashboard/car-ranking", headers=H), is_list=True)
check("dashboard/energy", c.get(f"{BASE}/dashboard/energy", headers=H), {"proportion", "monthly"})
check("dashboard/region", c.get(f"{BASE}/dashboard/region", headers=H), {"regions", "topPenetration"})
check("dashboard/price", c.get(f"{BASE}/dashboard/price", headers=H), {"buckets"})
check("dashboard/growth", c.get(f"{BASE}/dashboard/growth", headers=H), {"months", "marketSize", "growth"})
check("dashboard/scatter", c.get(f"{BASE}/dashboard/scatter", headers=H), is_list=True)

# 市场
check("market/options", c.get(f"{BASE}/market/options", headers=H),
      {"years", "months", "brands", "energies", "categories", "regions", "updatedAt"})
check("market/trend", c.get(f"{BASE}/market/trend", headers=H), {"months", "series"})
check("market/share", c.get(f"{BASE}/market/share", headers=H), {"months", "series"})
check("market/penetration", c.get(f"{BASE}/market/penetration", headers=H), {"months", "values"})
check("market/region", c.get(f"{BASE}/market/region", headers=H), is_list=True)
check("market/energy", c.get(f"{BASE}/market/energy", headers=H), is_list=True)
check("market/price", c.get(f"{BASE}/market/price", headers=H), is_list=True)
check("market/brand-rank", c.get(f"{BASE}/market/brand-rank", headers=H), is_list=True)
check("market/category", c.get(f"{BASE}/market/category", headers=H), is_list=True)
check("market/category-trend", c.get(f"{BASE}/market/category-trend", headers=H), {"months", "series"})

# 销量
check("sales", c.get(f"{BASE}/sales", headers=H), {"list", "total", "page", "pageSize"})
check("sales/trend", c.get(f"{BASE}/sales/trend", headers=H), {"months", "series"})
check("sales/ranking", c.get(f"{BASE}/sales/ranking", headers=H), is_list=True)
check("sales/region", c.get(f"{BASE}/sales/region", headers=H), is_list=True)

# 预测
data = check("predict/sales", c.get(f"{BASE}/predict/sales", params={"carId": 1, "horizon": 6}, headers=H),
             {"carId", "carName", "model", "accuracy", "horizon", "history", "prediction",
              "growthRate", "peakMonth", "lowMonth", "isMock", "features"})
r = c.get(f"{BASE}/predict/sales", params={"carId": 1, "horizon": 5}, headers=H)
if r.status_code == 400:
    print("✓ predict/sales horizon=5 → 400")
else:
    failures.append(f"predict horizon=5 应 400，实际 {r.status_code}")
    print(f"✗ predict horizon=5 → {r.status_code}")

# 推荐
check("recommend/options", c.get(f"{BASE}/recommend/options", headers=H),
      {"budgets", "usages", "concerns", "provinces", "cities", "energies"})
data = check("recommend POST", c.post(f"{BASE}/recommend", headers=H, json={
    "budget": "20-30", "energyTypes": ["BEV", "PHEV"], "scenarios": ["family"],
    "province": "广东省", "city": "深圳市",
    "weights": {"price": 70, "range": 60, "performance": 50, "space": 80, "intelligence": 60, "comfort": 55},
    "topN": 6,
}), {"requestId", "model", "generatedAt", "isMock", "recommendations"})
if data:
    rec = data["recommendations"][0]
    want_rec = {"carId", "carName", "brand", "score", "reason", "price", "energyType",
                "range", "rating", "dimensions", "highlights"}
    missing = want_rec - set(rec)
    if missing:
        failures.append(f"recommend item 缺 {missing}")
        print(f"✗ recommend item 缺 {missing}")
    else:
        print("✓ recommend item 字段完整")

# 舆情
check("sentiment", c.get(f"{BASE}/sentiment", headers=H),
      {"total", "positive", "neutral", "negative", "positiveRate", "avgScore", "updatedAt"})
check("sentiment/trend", c.get(f"{BASE}/sentiment/trend", headers=H),
      {"months", "positive", "neutral", "negative"})
check("sentiment/keywords", c.get(f"{BASE}/sentiment/keywords", headers=H), is_list=True)
check("sentiment/brand-reputation", c.get(f"{BASE}/sentiment/brand-reputation", headers=H), is_list=True)
check("reviews", c.get(f"{BASE}/reviews", headers=H), {"list", "total", "page", "pageSize"})

# 管理后台
check("admin/overview", c.get(f"{BASE}/admin/overview", headers=H),
      {"todaySales", "monthSales", "inventory", "newUsers", "newOrders", "recommendCount",
       "predictTasks", "deltas", "updatedAt"})
check("admin/sales-trend", c.get(f"{BASE}/admin/sales-trend", headers=H), {"months", "sales", "orders"})
check("admin/order-status", c.get(f"{BASE}/admin/order-status", headers=H), is_list=True)
check("admin/car-ranking", c.get(f"{BASE}/admin/car-ranking", headers=H), is_list=True)
check("admin/inventory-trend", c.get(f"{BASE}/admin/inventory-trend", headers=H), {"months", "data"})
check("admin/users", c.get(f"{BASE}/admin/users", headers=H), {"list", "total", "page", "pageSize"})
check("admin/brands", c.get(f"{BASE}/admin/brands", headers=H), {"list", "total", "page", "pageSize"})
check("admin/cars", c.get(f"{BASE}/admin/cars", headers=H), {"list", "total", "page", "pageSize"})
check("admin/sales", c.get(f"{BASE}/admin/sales", headers=H), {"list", "total", "page", "pageSize"})
check("admin/inventory", c.get(f"{BASE}/admin/inventory", headers=H), {"list", "total", "page", "pageSize"})
check("admin/orders", c.get(f"{BASE}/admin/orders", headers=H), {"list", "total", "page", "pageSize"})
check("admin/algorithms", c.get(f"{BASE}/admin/algorithms", headers=H), is_list=True)
check("admin/logs", c.get(f"{BASE}/admin/logs", headers=H), {"list", "total", "page", "pageSize"})
check("admin/data-files", c.get(f"{BASE}/admin/data-files", headers=H), is_list=True)

print()
if failures:
    print(f"❌ {len(failures)} 项失败：")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("🎉 全部冒烟通过")
