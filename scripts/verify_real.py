"""真实数据抽查：对照 CSV 已知值验证 API 输出"""

import sys

import httpx

BASE = "http://127.0.0.1:8001/api"
c = httpx.Client(timeout=30)
token = c.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
H = {"Authorization": f"Bearer {token}"}

failures = []


def expect(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# 1. 车型 1 = 秦PLUS 插电混动，指导价 139800 元 → 13.98 万
car1 = c.get(f"{BASE}/cars/1", headers=H).json()
expect("car1=秦PLUS", car1["name"] == "秦PLUS", f'{car1["brand"]} {car1["name"]}')
expect("car1 price=13.98万", abs(car1["price"] - 13.98) < 1e-6, str(car1["price"]))
expect("car1 energy=PHEV(增程/插混映射)", car1["energyType"] in ("PHEV", "BEV"), car1["energyType"])
expect("car1 有真实图片", bool(car1["image"]))

# sales_12m = 2025-07~2026-06 月销之和 = 36196；上月 3138
expect("car1 sales12m=36196", car1["sales"] == 36196, str(car1["sales"]))
expect("car1 lastMonth=3138", car1["lastMonthSales"] == 3138, str(car1["lastMonthSales"]))

# 2. 预测：carId=61 在爬虫预测的 20 款车型里 → 应直接返回爬虫结果
pred = c.get(f"{BASE}/predict/sales", params={"carId": 61, "horizon": 6}, headers=H).json()
expect("pred61 用爬虫模型", "爬虫" in pred["model"], pred["model"])
expect("pred61 首月=2026-07", pred["prediction"][0]["month"] == "2026-07", pred["prediction"][0]["month"])
expect("pred61 首月值=3936", pred["prediction"][0]["value"] == 3936, str(pred["prediction"][0]["value"]))
expect("pred61 置信区间", pred["prediction"][0]["lower"] == 3345 and pred["prediction"][0]["upper"] == 4526)

# 不在爬虫预测名单的车型（车 3 不在 20 款名单内）→ 回退在线算法
pred2 = c.get(f"{BASE}/predict/sales", params={"carId": 3, "horizon": 6}, headers=H).json()
expect("pred3 回退在线算法", "爬虫" not in pred2["model"], pred2["model"])
expect("pred3 月份顺延 2026-07 起", pred2["prediction"][0]["month"] == "2026-07")

# 3. 地区：31 个省级行政区（爬虫 31 短名补全）
regions = c.get(f"{BASE}/dashboard/region", headers=H).json()["regions"]
expect("region 数量=31", len(regions) == 31, str(len(regions)))
names = {r["name"] for r in regions}
expect("region 全名为省级", "北京市" in names and "广东省" in names and "内蒙古自治区" in names)

# 4. 舆情：总评价数 = 1302
overview = c.get(f"{BASE}/sentiment", headers=H).json()
expect("reviews 总数=1302", overview["total"] == 1302, str(overview["total"]))

# 5. 订单：状态只允许前端枚举，completed 已映射 delivered
orders = c.get(f"{BASE}/admin/orders", params={"pageSize": 100}, headers=H).json()
statuses = {o["status"] for o in orders["list"]}
expect("orders 状态合法", statuses <= {"pending", "paid", "delivered", "cancelled"}, str(statuses))
expect("orders 总数=100", orders["total"] == 100, str(orders["total"]))
sample = orders["list"][0]
expect("orders 金额为万元", sample["amount"] < 200, str(sample["amount"]))

# 6. 品牌：30 个，含阵营映射
brands = c.get(f"{BASE}/admin/brands", params={"pageSize": 50}, headers=H).json()
groups = {b["group"] for b in brands["list"]}
expect("brands 总数=30", brands["total"] == 30, str(brands["total"]))
expect("brands 阵营映射", {"自主", "新势力", "日系", "德系", "美系", "韩系"} <= groups, str(groups))

# 7. 用户：10 爬虫用户 + analyst/sales 演示账号
users = c.get(f"{BASE}/admin/users", params={"pageSize": 50}, headers=H).json()
expect("users 总数=12", users["total"] == 12, str(users["total"]))

# 8. 能源结构：EREV 并入 PHEV 输出
energy = c.get(f"{BASE}/dashboard/energy", headers=H).json()["proportion"]
enames = {e["name"] for e in energy}
expect("能源输出无增程", "增程" not in enames, str(enames))
expect("能源 4 类", len(energy) == 4, str(len(energy)))

# 9. 库存：100 条，仓库为真实城市
inv = c.get(f"{BASE}/admin/inventory", params={"pageSize": 1}, headers=H).json()
expect("inventory 总数=100", inv["total"] == 100, str(inv["total"]))

# 10. 车型月销明细与 CSV 一致（car 1 @ 2026-06 = 3138）
sales_rows = c.get(f"{BASE}/sales", params={"span": 18, "pageSize": 100, "brandId": 1}, headers=H).json()
row = next(r for r in sales_rows["list"] if r["carId"] == 1 and r["month"] == "2026-06")
expect("sales 明细 car1@2026-06=3138", row["sales"] == 3138, str(row["sales"]))

print()
if failures:
    print(f"❌ {len(failures)} 项抽查失败：", failures)
    sys.exit(1)
print("🎉 真实数据抽查全部通过")
