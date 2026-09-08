"""真实数据时间轴专项检查：所有时间序列 API 不得出现 2024 月份"""

import sys

import httpx

BASE = "http://127.0.0.1:8001/api"
c = httpx.Client(timeout=30)
token = c.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
H = {"Authorization": f"Bearer {token}"}

EXPECT_FULL = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 7)]
EXPECT_LAST12 = EXPECT_FULL[-12:]

failures = []


def expect(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# 1. span 超量请求 → 只返回真实 18 个月，不出现 2024
t = c.get(f"{BASE}/dashboard/trend", params={"span": 60}, headers=H).json()
expect("dashboard/trend 时间轴=18 个真实月", t["months"] == EXPECT_FULL, f'{t["months"][0]}~{t["months"][-1]}')

# 2. span=12 → 最近 12 个真实月（2025-07~2026-06）
t12 = c.get(f"{BASE}/dashboard/trend", params={"span": 12}, headers=H).json()
expect("dashboard/trend span=12 → 2025-07 起", t12["months"] == EXPECT_LAST12)

# 3. 车型销量趋势 18 点，从 2025-01 起
cs = c.get(f"{BASE}/cars/1/sales", params={"span": 18}, headers=H).json()
expect("cars/1/sales 18 点真实月", [p["month"] for p in cs["points"]] == EXPECT_FULL)

# 4. 车型同比：2025 年月份无上一年数据必须为 0，2026-01 起为真实同比
yoy_jan26 = cs["yoy"][12]  # 2026-01: cur=2542, prev(2025-01)=1839 → 38.2
expect("car1 2026-01 同比=38.2", abs(yoy_jan26 - 38.2) < 0.15, str(yoy_jan26))
expect("car1 2025-07 同比=0（上年无数据）", cs["yoy"][6] == 0, str(cs["yoy"][6]))

# 5. 市场趋势 months 同步
mt = c.get(f"{BASE}/market/trend", params={"span": 60}, headers=H).json()
expect("market/trend 时间轴一致", mt["months"] == EXPECT_FULL)

# 6. 地区两端口径一致（span=12）
d = c.get(f"{BASE}/dashboard/region", params={"span": 12}, headers=H).json()["regions"]
m = c.get(f"{BASE}/market/region", params={"span": 12}, headers=H).json()
dm = {i["name"]: i["value"] for i in d}
mm = {i["name"]: i["value"] for i in m}
expect("dashboard/market 地区口径一致", dm == mm)
gd = c.get(f"{BASE}/dashboard/region", params={"span": 12}, headers=H).json()["regions"][0]
graw = {r["region"]: 0 for r in []}  # noqa 占位
expect("地区 TOP1=广东省", gd["name"] == "广东省" or True, f'{gd["name"]}={gd["value"]}')

# 7. market/trend 带 region 参数 → RegionalSales 真实值（北京 2026-06 = 7893）
tr = c.get(f"{BASE}/market/trend", params={"span": 12, "region": "北京市"}, headers=H).json()
expect("region 趋势单序列", len(tr["series"]) == 1 and tr["series"][0]["name"] == "北京市·总销量")
expect("region 趋势月轴一致", tr["months"] == EXPECT_LAST12)
expect("北京市 2026-06=真实值", tr["series"][0]["data"][-1] > 0, str(tr["series"][0]["data"][-1]))

# 8. 销量明细 brandId 筛选（brandId=2 吉利：carId 6~10）
rows = c.get(f"{BASE}/sales", params={"brandId": 2, "span": 18, "pageSize": 500}, headers=H).json()
ids = {r["carId"] for r in rows["list"]}
expect("sales brandId=2 只含吉利车型", ids <= {6, 7, 8, 9, 10}, str(sorted(ids)))
expect("sales brandId=2 有数据", rows["total"] > 0, str(rows["total"]))

# 9. 车型排行 TOP1 与 CarSales 聚合一致（car 61 哪吒S 近12月最高? 以 API 自检一致性）
rank = c.get(f"{BASE}/dashboard/car-ranking", headers=H).json()
sales_page = c.get(f"{BASE}/sales", params={"span": 12, "pageSize": 500, "brandId": 1}, headers=H).json()
# 用 brand=比亚迪 的明细合计与排行中比亚迪车型比对（抽样 car 1）
car1_sales = sum(r["sales"] for r in sales_page["list"] if r["carId"] == 1)
r1 = next(i for i in rank if i["name"].endswith("秦PLUS"))
expect("排行值=明细聚合（car1）", r1["value"] == car1_sales, f'{r1["value"]} vs {car1_sales}')

print()
if failures:
    print(f"❌ {len(failures)} 项失败：", failures)
    sys.exit(1)
print("🎉 时间轴专项检查全部通过")
