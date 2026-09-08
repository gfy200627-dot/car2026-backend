"""种子数据导入：品牌 / 车型 / 地区 / 用户"""

import csv
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import Date
from datetime import date

from app.database.session import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models import (
    Brand,
    BrandAlias,
    Car,
    ModelAlias,
    Region,
    User,
    CarSales,
)


def import_brands(db: Session) -> int:
    """导入 30 个品牌（brands.ts 源数据）"""
    BRAND_SEEDS = [
        (1, "比亚迪", "BYD", "中国", "自主", "#d0202f", 1995, ["BEV", "PHEV"], 100),
        (2, "特斯拉", "Tesla", "美国", "新势力", "#e31937", 2003, ["BEV"], 58),
        (3, "大众", "Volkswagen", "德国", "德系", "#1c5faa", 1937, ["ICE", "BEV"], 86),
        (4, "丰田", "Toyota", "日本", "日系", "#d71920", 1937, ["ICE", "HEV"], 76),
        (5, "本田", "Honda", "日本", "日系", "#0f4da0", 1948, ["ICE", "HEV"], 50),
        (6, "日产", "Nissan", "日本", "日系", "#c3002f", 1933, ["ICE", "BEV"], 32),
        (7, "吉利", "Geely", "中国", "自主", "#0b3d91", 1997, ["ICE", "PHEV", "BEV"], 68),
        (8, "长安", "Changan", "中国", "自主", "#0d4c8b", 1862, ["ICE", "PHEV", "BEV"], 64),
        (9, "哈弗", "Haval", "中国", "自主", "#a01f24", 1984, ["ICE", "PHEV"], 46),
        (10, "奇瑞", "Chery", "中国", "自主", "#0f5c8c", 1997, ["ICE", "PHEV", "BEV"], 56),
        (11, "五菱", "Wuling", "中国", "自主", "#b8232f", 2002, ["BEV", "ICE"], 44),
        (12, "广汽埃安", "Aion", "中国", "新势力", "#17a2b8", 2017, ["BEV"], 38),
        (13, "理想", "Li Auto", "中国", "新势力", "#1a9c6b", 2015, ["PHEV", "BEV"], 41),
        (14, "蔚来", "NIO", "中国", "新势力", "#2b6cb0", 2014, ["BEV"], 29),
        (15, "小鹏", "XPeng", "中国", "新势力", "#00a19a", 2014, ["BEV"], 31),
        (16, "零跑", "Leapmotor", "中国", "新势力", "#00a0e9", 2015, ["BEV", "PHEV"], 25),
        (17, "问界", "AITO", "中国", "新势力", "#c8963e", 2021, ["PHEV", "BEV"], 37),
        (18, "小米", "Xiaomi", "中国", "新势力", "#ff6900", 2021, ["BEV"], 27),
        (19, "极氪", "ZEEKR", "中国", "新势力", "#6c7a89", 2021, ["BEV"], 21),
        (20, "深蓝", "Deepal", "中国", "自主", "#1f6feb", 2022, ["BEV", "PHEV"], 19),
        (21, "岚图", "Voyah", "中国", "自主", "#3b5bdb", 2019, ["BEV", "PHEV"], 11),
        (22, "领克", "Lynk & Co", "中国", "自主", "#5a6472", 2016, ["PHEV", "ICE"], 23),
        (23, "宝马", "BMW", "德国", "德系", "#0166b1", 1916, ["ICE", "BEV"], 43),
        (24, "奔驰", "Mercedes-Benz", "德国", "德系", "#2f6fb0", 1926, ["ICE", "BEV"], 41),
        (25, "奥迪", "Audi", "德国", "德系", "#bb0a30", 1909, ["ICE", "BEV"], 39),
        (26, "沃尔沃", "Volvo", "瑞典", "欧系", "#003057", 1927, ["ICE", "PHEV", "BEV"], 13),
        (27, "现代", "Hyundai", "韩国", "韩系", "#00205b", 1967, ["ICE", "BEV"], 15),
        (28, "起亚", "Kia", "韩国", "韩系", "#0b3d62", 1944, ["ICE", "BEV"], 9),
        (29, "别克", "Buick", "美国", "美系", "#003876", 1903, ["ICE", "PHEV", "BEV"], 28),
        (30, "福特", "Ford", "美国", "美系", "#00274c", 1903, ["ICE", "BEV"], 20),
    ]
    count = 0
    for bid, name, name_en, country, group, color, year, energy_focus, weight in BRAND_SEEDS:
        if db.get(Brand, bid):
            continue
        b = Brand(
            id=bid,
            name=name,
            name_en=name_en,
            country=country,
            group=group,
            color=color,
            founded_year=year,
            energy_focus=energy_focus,
            weight=weight,
        )
        db.add(b)
        count += 1
    db.commit()
    return count


def import_regions(db: Session) -> int:
    """导入 34 个省级行政区（sales.ts REGION_SEEDS）"""
    REGION_SEEDS = [
        ("广东省", 10.8, 56.2), ("江苏省", 8.2, 49.1), ("山东省", 7.6, 38.4),
        ("浙江省", 7.1, 54.8), ("河南省", 6.0, 41.2), ("四川省", 5.2, 45.6),
        ("河北省", 4.8, 36.8), ("湖北省", 4.1, 43.5), ("湖南省", 3.9, 42.1),
        ("安徽省", 3.8, 44.9), ("上海市", 3.2, 68.5), ("北京市", 3.0, 51.2),
        ("福建省", 3.0, 47.3), ("陕西省", 2.6, 44.1), ("江西省", 2.4, 39.7),
        ("重庆市", 2.4, 50.6), ("辽宁省", 2.3, 33.9), ("山西省", 2.0, 34.5),
        ("广西壮族自治区", 2.0, 46.8), ("云南省", 1.9, 37.6), ("天津市", 1.6, 46.2),
        ("贵州省", 1.6, 35.8), ("黑龙江省", 1.3, 26.4), ("吉林省", 1.2, 28.1),
        ("内蒙古自治区", 1.2, 27.5), ("新疆维吾尔自治区", 1.1, 25.9), ("甘肃省", 1.0, 30.2),
        ("海南省", 0.7, 62.4), ("宁夏回族自治区", 0.5, 29.6), ("青海省", 0.4, 28.3),
        ("西藏自治区", 0.2, 22.7), ("台湾省", 1.4, 21.5), ("香港特别行政区", 0.5, 58.3),
        ("澳门特别行政区", 0.2, 52.7),
    ]
    count = 0
    for name, weight, penetration in REGION_SEEDS:
        if db.query(Region).filter_by(name=name).first():
            continue
        r = Region(name=name, weight=weight, penetration=penetration)
        db.add(r)
        count += 1
    db.commit()
    return count


def import_cars(db: Session) -> int:
    """导入 158 款车型（cars.ts MODEL_SEEDS；其他字段后续从采集数据更新）"""
    # 简化版：只导入基础信息，销量/评分留待数据导入后回填
    CAR_SEEDS = [
        (1, 1, "秦PLUS", "轿车", 9.98, "PHEV"),
        (2, 1, "秦PLUS", "轿车", 9.98, "BEV"),
        (3, 1, "汉", "轿车", 20.98, "BEV"),
        (4, 1, "汉", "轿车", 20.98, "PHEV"),
        (5, 1, "宋PLUS", "SUV", 15.98, "BEV"),
        (6, 1, "宋PLUS", "SUV", 15.98, "PHEV"),
        # ... 其他种子省略，后续用脚本从 cars.ts 完整导出
    ]
    count = 0
    car_id = 1
    for bid, brand_id, name, category, price, energy in CAR_SEEDS:
        if db.get(Car, car_id):
            car_id += 1
            continue
        c = Car(
            id=car_id,
            brand_id=brand_id,
            name=f"{name} {energy}" if energy in ("PHEV", "BEV") else name,
            name_norm=name,
            model_code=f"{brand_id}-{car_id:03d}",
            category=category,
            energy_type=energy,
            price=price,
            price_min=price * 0.9,
            price_max=price * 1.1,
            launch_date=date(2024, 1, 1),
            launch_year=2024,
        )
        db.add(c)
        car_id += 1
        count += 1
    db.commit()
    return count


def import_users(db: Session) -> int:
    """导入 4 个演示账号（与 Mock DEMO_ACCOUNTS 对齐）"""
    DEMO_USERS = [
        ("admin", "赵启明", "admin", "active", "市场研究中心"),
        ("analyst", "孙以宁", "analyst", "active", "数据分析部"),
        ("sales", "周砚清", "sales", "active", "销售运营部"),
        ("user", "吴听澜", "user", "active", "销售运营部"),
    ]
    count = 0
    for i, (username, nickname, role, status, dept) in enumerate(DEMO_USERS):
        if db.query(User).filter_by(username=username).first():
            continue
        pwd_hash = hash_password(f"{username}123")
        u = User(
            id=i + 1,
            username=username,
            nickname=nickname,
            email=f"{username}@autoinsight.com",
            phone=f"13{str(100000000 + i * 100000000)[1:10]}",
            password_hash=pwd_hash,
            role=role,
            status=status,
            department=dept,
        )
        db.add(u)
        count += 1
    db.commit()
    return count


def seed_all():
    """执行全量种子导入"""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        print(f"品牌导入: {import_brands(db)} 条")
        print(f"地区导入: {import_regions(db)} 条")
        print(f"车型导入: {import_cars(db)} 条（简化版，后续补充）")
        print(f"用户导入: {import_users(db)} 条")


if __name__ == "__main__":
    seed_all()