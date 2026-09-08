"""种子数据导入：生成与前端 Mock 同口径的全量演示数据

数据生成逻辑移植自 src/mock/{brands,cars,sales,admin,sentiment}.ts，
确定性随机（mulberry32）保证可复现。重复执行自动跳过已导入部分。

用法：
    python scripts/seed_demo.py            # 增量导入
    python scripts/seed_demo.py --fresh    # 清空业务数据后重新导入
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func as F
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, Base, engine
from app.core.config import settings
from app.core.security import hash_password
from app.models import (
    AlgorithmTask,
    Brand,
    BrandSales,
    Car,
    CarSales,
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
from app.utils.rng import Rng, clamp, round as rng_round
from app.utils.series import build_months

LATEST_YEAR = settings.LATEST_YEAR
LATEST_MONTH = settings.LATEST_MONTH
MONTHS = build_months(24, LATEST_YEAR, LATEST_MONTH)

SEASONAL = [0.88, 0.64, 1.02, 1.0, 1.05, 1.09, 0.94, 0.98, 1.08, 1.06, 1.13, 1.24]
TARGET_ANNUAL = 23_600_000

ENERGY_SUFFIX = {"BEV": "纯电版", "PHEV": "插混版", "HEV": "双擎版", "ICE": ""}
ENERGY_PRICE_DELTA = {"BEV": 0.0, "PHEV": 0.8, "HEV": 1.4, "ICE": 0.0}
CATEGORY_FACTOR = {"轿车": 1.0, "SUV": 1.16, "MPV": 0.42, "跑车": 0.08, "皮卡": 0.18}
ENERGY_FACTOR = {"BEV": 1.16, "PHEV": 1.26, "HEV": 0.84, "ICE": 0.9}
CATEGORY_SEATS = {"轿车": 5, "SUV": 5, "MPV": 7, "跑车": 4, "皮卡": 5}

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

# (品牌ID, 车型名, 类别, 指导价, [能源版本])——与 src/mock/cars.ts MODEL_SEEDS 一致
MODEL_SEEDS = {
    1: [("秦PLUS", "轿车", 9.98, ["PHEV", "BEV"]), ("汉", "轿车", 20.98, ["BEV", "PHEV"]),
        ("宋PLUS", "SUV", 15.98, ["BEV", "PHEV"]), ("元PLUS", "SUV", 13.98, ["BEV"]),
        ("海豚", "轿车", 11.68, ["BEV"]), ("唐", "SUV", 24.98, ["PHEV"]), ("海鸥", "轿车", 7.38, ["BEV"])],
    2: [("Model Y", "SUV", 26.39, ["BEV"]), ("Model 3", "轿车", 24.59, ["BEV"]),
        ("Model X", "SUV", 83.89, ["BEV"]), ("Model S", "轿车", 78.89, ["BEV"])],
    3: [("朗逸", "轿车", 12.09, ["ICE"]), ("帕萨特", "轿车", 18.99, ["ICE"]),
        ("途观L", "SUV", 22.38, ["ICE"]), ("探岳", "SUV", 20.49, ["ICE"]),
        ("ID.4 CROZZ", "SUV", 19.39, ["BEV"]), ("ID.3", "轿车", 16.29, ["BEV"])],
    4: [("卡罗拉", "轿车", 11.98, ["ICE", "HEV"]), ("凯美瑞", "轿车", 19.98, ["ICE", "HEV"]),
        ("RAV4荣放", "SUV", 17.68, ["ICE", "HEV"]), ("锋兰达", "SUV", 12.58, ["ICE"]),
        ("亚洲龙", "轿车", 20.98, ["HEV"]), ("格瑞维亚", "MPV", 31.98, ["HEV"])],
    5: [("雅阁", "轿车", 17.98, ["ICE"]), ("思域", "轿车", 12.99, ["ICE"]),
        ("CR-V", "SUV", 18.59, ["ICE", "HEV"]), ("皓影", "SUV", 18.99, ["ICE", "HEV"]),
        ("艾力绅", "MPV", 27.98, ["HEV"])],
    6: [("轩逸", "轿车", 10.86, ["ICE"]), ("天籁", "轿车", 17.98, ["ICE"]),
        ("逍客", "SUV", 12.59, ["ICE"]), ("奇骏", "SUV", 18.19, ["ICE"]),
        ("ARIYA艾睿雅", "SUV", 19.99, ["BEV"])],
    7: [("星越L", "SUV", 13.72, ["ICE"]), ("帝豪", "轿车", 6.99, ["ICE"]),
        ("银河E8", "轿车", 17.58, ["BEV"]), ("银河L7", "SUV", 13.87, ["PHEV"]),
        ("星愿", "轿车", 7.98, ["BEV"])],
    8: [("CS75 PLUS", "SUV", 12.49, ["ICE"]), ("逸动", "轿车", 7.29, ["ICE"]),
        ("深蓝SL03", "轿车", 15.69, ["BEV", "PHEV"]), ("UNI-V", "轿车", 10.89, ["ICE"]),
        ("Lumin", "轿车", 4.99, ["BEV"])],
    9: [("H6", "SUV", 11.79, ["ICE", "PHEV"]), ("大狗", "SUV", 12.98, ["ICE"]),
        ("猛龙", "SUV", 16.58, ["PHEV"]), ("枭龙MAX", "SUV", 15.98, ["PHEV"])],
    10: [("瑞虎8", "SUV", 10.99, ["ICE"]), ("艾瑞泽8", "轿车", 9.99, ["ICE"]),
         ("捷途旅行者", "SUV", 13.99, ["ICE"]), ("星纪元ET", "SUV", 22.98, ["BEV", "PHEV"]),
         ("风云A8", "轿车", 11.99, ["PHEV"]), ("iCAR 03", "SUV", 12.98, ["BEV"])],
    11: [("宏光MINIEV", "轿车", 3.28, ["BEV"]), ("缤果", "轿车", 5.98, ["BEV"]),
         ("星光", "轿车", 8.88, ["BEV", "PHEV"]), ("星辰", "SUV", 6.98, ["ICE"])],
    12: [("AION S", "轿车", 14.98, ["BEV"]), ("AION Y", "SUV", 12.98, ["BEV"]),
         ("AION V", "SUV", 17.98, ["BEV"]), ("昊铂HT", "SUV", 22.98, ["BEV"])],
    13: [("L6", "SUV", 24.98, ["PHEV"]), ("L7", "SUV", 30.18, ["PHEV"]),
         ("L8", "SUV", 32.18, ["PHEV"]), ("L9", "SUV", 42.98, ["PHEV"]),
         ("MEGA", "MPV", 52.98, ["BEV"])],
    14: [("ES6", "SUV", 33.8, ["BEV"]), ("ET5", "轿车", 29.8, ["BEV"]),
         ("ES8", "SUV", 49.8, ["BEV"]), ("EC6", "SUV", 35.8, ["BEV"]),
         ("ET7", "轿车", 42.8, ["BEV"])],
    15: [("G6", "SUV", 20.99, ["BEV"]), ("P7", "轿车", 22.39, ["BEV"]),
         ("G9", "SUV", 26.39, ["BEV"]), ("X9", "MPV", 35.98, ["BEV"]),
         ("MONA M03", "轿车", 11.98, ["BEV"])],
    16: [("C11", "SUV", 15.58, ["BEV", "PHEV"]), ("C10", "SUV", 12.88, ["BEV", "PHEV"]),
         ("T03", "轿车", 5.99, ["BEV"]), ("C16", "SUV", 15.58, ["BEV", "PHEV"])],
    17: [("M5", "SUV", 24.98, ["PHEV", "BEV"]), ("M7", "SUV", 28.98, ["PHEV", "BEV"]),
         ("M9", "SUV", 46.98, ["PHEV", "BEV"])],
    18: [("SU7", "轿车", 21.59, ["BEV"]), ("SU7 Pro", "轿车", 24.59, ["BEV"]),
         ("SU7 Max", "轿车", 29.99, ["BEV"]), ("YU7", "SUV", 25.35, ["BEV"])],
    19: [("001", "轿车", 26.9, ["BEV"]), ("007", "轿车", 20.99, ["BEV"]),
         ("009", "MPV", 43.9, ["BEV"]), ("7X", "SUV", 22.99, ["BEV"])],
    20: [("S7", "SUV", 14.99, ["BEV", "PHEV"]), ("L07", "轿车", 15.19, ["BEV", "PHEV"]),
         ("S05", "SUV", 11.99, ["BEV"]), ("G318", "SUV", 17.59, ["PHEV"])],
    21: [("梦想家", "MPV", 33.99, ["PHEV", "BEV"]), ("FREE", "SUV", 26.69, ["PHEV"]),
         ("追光", "轿车", 28.99, ["PHEV"])],
    22: [("08", "SUV", 20.88, ["PHEV"]), ("03", "轿车", 15.68, ["ICE"]),
         ("09", "SUV", 26.59, ["PHEV"]), ("01", "SUV", 16.58, ["ICE"])],
    23: [("3系", "轿车", 31.99, ["ICE"]), ("5系", "轿车", 43.99, ["ICE", "BEV"]),
         ("X3", "SUV", 39.99, ["ICE"]), ("X5", "SUV", 61.5, ["ICE"]),
         ("i3", "轿车", 35.39, ["BEV"])],
    24: [("C级", "轿车", 33.48, ["ICE"]), ("E级", "轿车", 44.9, ["ICE"]),
         ("GLC", "SUV", 42.78, ["ICE"]), ("S级", "轿车", 96.26, ["ICE"]),
         ("EQS", "轿车", 88.1, ["BEV"])],
    25: [("A4L", "轿车", 32.18, ["ICE"]), ("A6L", "轿车", 42.79, ["ICE"]),
         ("Q5L", "SUV", 39.88, ["ICE"]), ("Q3", "SUV", 27.98, ["ICE"]),
         ("e-tron GT", "轿车", 99.98, ["BEV"])],
    26: [("XC60", "SUV", 39.19, ["ICE"]), ("S60", "轿车", 30.69, ["ICE"]),
         ("XC90", "SUV", 63.89, ["PHEV"]), ("EX30", "SUV", 20.08, ["BEV"])],
    27: [("伊兰特", "轿车", 9.98, ["ICE"]), ("途胜", "SUV", 16.18, ["ICE"]),
         ("胜达", "SUV", 20.28, ["ICE"]), ("菲斯塔", "轿车", 13.88, ["ICE"])],
    28: [("狮铂拓界", "SUV", 17.98, ["ICE"]), ("赛图斯", "SUV", 10.99, ["ICE"]),
         ("EV5", "SUV", 14.98, ["BEV"])],
    29: [("君威", "轿车", 17.58, ["ICE"]), ("昂科威", "SUV", 21.99, ["ICE"]),
         ("GL8", "MPV", 23.29, ["ICE"]), ("E5", "SUV", 16.99, ["BEV"])],
    30: [("锐界", "SUV", 24.98, ["ICE"]), ("蒙迪欧", "轿车", 15.98, ["ICE"]),
         ("探险者", "SUV", 30.98, ["ICE"]), ("电马", "SUV", 23.98, ["BEV"])],
}

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

DEPARTMENTS = ["市场研究中心", "数据分析部", "销售运营部", "算法平台部", "供应链管理部"]

NAMES = [
    "赵启明", "钱嘉树", "孙以宁", "李知微", "周砚清", "吴听澜", "郑云舟", "王砚书",
    "冯叙白", "陈砚舟", "褚望舒", "卫南乔", "蒋星阑", "沈知白", "韩明轩", "杨清让",
    "朱景行", "秦临风", "尤未晞", "许砚洲", "何向东", "吕思远", "施远山", "张澈",
    "孔繁星", "曹砚青", "严听雨", "华子墨", "金若谷", "魏长风",
]

POSITIVE_WORDS = [
    "续航扎实", "加速平顺", "内饰质感好", "智能座舱流畅", "空间宽敞",
    "静谧性优秀", "辅助驾驶好用", "底盘稳健", "外观耐看", "用车成本低",
    "充电速度快", "性价比高", "座椅舒适", "车机响应快", "售后服务好",
]
NEGATIVE_WORDS = [
    "车机卡顿", "风噪偏大", "后排空间局促", "续航虚标", "交付周期长",
    "底盘偏硬", "内饰异味", "辅助驾驶保守", "充电网络不足", "保值率一般",
    "轮胎磨损快", "雨刮异响", "后排座椅偏短", "中控反光", "售后服务慢",
]
NEUTRAL_WORDS = [
    "配置够用", "中规中矩", "价格稳定", "等待观望", "对比竞品",
    "试驾体验中", "关注优惠", "考虑置换", "关注改款", "等待补贴",
]
REVIEW_TEMPLATES = {
    "positive": [
        "提车三个月，{w}，整体超出预期，家用非常合适。",
        "最满意的一点是{w}，日常通勤成本比之前的燃油车低很多。",
        "跑了趟长途，{w}，高速表现稳定，值得推荐。",
        "对比了同级别几款车，最终选择它主要因为{w}。",
    ],
    "neutral": [
        "目前{w}，还在观望后续改款信息。",
        "整体{w}，没有明显短板也没有特别惊喜。",
        "试驾后感觉{w}，准备再对比一下竞品。",
    ],
    "negative": [
        "目前遇到{w}的问题，希望厂家后续能优化。",
        "不太满意的地方是{w}，与宣传有一定差距。",
        "开了半年，{w}，建议有意向的朋友先试驾。",
    ],
}
USER_NAMES = [
    "陈默", "林知远", "苏晚", "周牧", "顾南舟", "沈砚", "许星野", "江照白",
    "温言", "裴屿", "陆行舟", "叶知秋", "柏川", "祁夜", "宋清和", "罗与之",
]


def month_date(m: str) -> date:
    return date(int(m[:4]), int(m[5:7]), 1)


def build_dimensions(category: str, price: float, rng: Rng) -> dict:
    p = clamp(price, 4, 100)
    if category == "SUV":
        return {
            "length": round(4500 + p * 9.5 + rng.float(-40, 60)),
            "width": round(1860 + p * 1.6 + rng.float(-15, 20)),
            "height": round(1620 + p * 2.2 + rng.float(-20, 30)),
            "wheelbase": round(2660 + p * 7.2 + rng.float(-20, 40)),
        }
    if category == "MPV":
        return {
            "length": round(4900 + p * 6 + rng.float(-40, 60)),
            "width": round(1880 + p * 1.4 + rng.float(-15, 20)),
            "height": round(1760 + p * 1.6 + rng.float(-20, 30)),
            "wheelbase": round(2930 + p * 5.4 + rng.float(-20, 40)),
        }
    if category == "皮卡":
        return {
            "length": round(5350 + p * 4 + rng.float(-40, 60)),
            "width": round(1880 + p * 1.5 + rng.float(-15, 20)),
            "height": round(1860 + p * 1.2 + rng.float(-20, 30)),
            "wheelbase": round(3150 + p * 3 + rng.float(-20, 40)),
        }
    if category == "跑车":
        return {
            "length": round(4400 + p * 6 + rng.float(-40, 60)),
            "width": round(1900 + p * 1.2 + rng.float(-15, 20)),
            "height": round(1280 + rng.float(0, 60)),
            "wheelbase": round(2620 + p * 5 + rng.float(-20, 40)),
        }
    return {
        "length": round(4620 + p * 9 + rng.float(-40, 60)),
        "width": round(1800 + p * 1.5 + rng.float(-15, 20)),
        "height": round(1450 + p * 1.1 + rng.float(-20, 30)),
        "wheelbase": round(2650 + p * 7.6 + rng.float(-20, 40)),
    }


def build_tags(car: dict) -> list:
    tags = []
    if car["price"] <= 12:
        tags.append("高性价比")
    if car["range_km"] >= 600:
        tags.append("超长续航")
    elif car["range_km"] >= 450:
        tags.append("长续航")
    if car["power_kw"] >= 300:
        tags.append("强动力")
    if car["category"] == "SUV" and car["wheelbase"] >= 2900:
        tags.append("大空间")
    if car["category"] == "MPV":
        tags.append("宜商宜家")
    if car["intelligence_score"] >= 86:
        tags.append("智能座舱")
    if car["launch_year"] >= 2025:
        tags.append("年度新车")
    if car["energy_type"] == "PHEV":
        tags.append("可油可电")
    if car["rating"] >= 4.7:
        tags.append("口碑优良")
    return tags[:3]


class CarDerived:
    """车型派生数据：销量序列生成所需的静态字段"""

    def __init__(self, car_id, brand_id, name, category, energy, price):
        self.id = car_id
        self.brand_id = brand_id
        self.name = name
        self.category = category
        self.energy = energy
        self.price = price


def import_brands(db: Session) -> int:
    count = 0
    for bid, name, name_en, country, group, color, year, energy_focus, weight in BRAND_SEEDS:
        if db.get(Brand, bid):
            continue
        db.add(Brand(
            id=bid, name=name, name_en=name_en, country=country, group=group,
            color=color, founded_year=year, energy_focus=energy_focus, weight=weight,
        ))
        count += 1
    db.commit()
    return count


def import_regions(db: Session) -> int:
    count = 0
    for name, weight, penetration in REGION_SEEDS:
        if db.query(Region).filter_by(name=name).first():
            continue
        db.add(Region(name=name, weight=weight, penetration=penetration))
        count += 1
    db.commit()
    return count


def build_car_plan() -> list[CarDerived]:
    """与 mock/cars.ts buildCars 相同顺序生成车型计划（id 连续）"""
    plan = []
    car_id = 1
    for bid, _name, _en, _c, _g, _color, _y, _ef, _w in BRAND_SEEDS:
        seeds = MODEL_SEEDS.get(bid, [])
        for seed_name, category, base_price, energies in seeds:
            multi = len(energies) > 1
            for energy in energies:
                display = f"{seed_name} {ENERGY_SUFFIX[energy]}" if multi else seed_name
                price = rng_round(base_price + (ENERGY_PRICE_DELTA[energy] if multi else 0), 2)
                plan.append(CarDerived(car_id, bid, display, category, energy, price))
                car_id += 1
    return plan


def import_cars(db: Session) -> int:
    if db.query(F.count(Car.id)).scalar():
        return 0
    count = 0
    for p in build_car_plan():
        rng = Rng(f"{p.brand_id}-{p.name}")
        if p.energy == "BEV":
            range_km = round(clamp(300 + p.price * 11 + rng.float(-30, 70), 300, 780))
            battery = rng_round(range_km / 6.2 + rng.float(-3, 6), 1)
        elif p.energy == "PHEV":
            range_km = round(clamp(55 + p.price * 4.2 + rng.float(-15, 25), 55, 240))
            battery = rng_round(clamp(9 + p.price * 0.7 + rng.float(-2, 4), 8, 45), 1)
        else:
            range_km, battery = 0, 0.0

        if p.energy == "BEV":
            power = round(clamp(120 + p.price * 6.6 + rng.float(-20, 45), 70, 780))
        elif p.energy == "PHEV":
            power = round(clamp(110 + p.price * 5.8 + rng.float(-15, 35), 70, 780))
        else:
            power = round(clamp(85 + p.price * 3.9 + rng.float(-10, 30), 70, 780))
        torque = round(power * rng.float(1.7, 2.2))

        dims = build_dimensions(p.category, p.price, rng)
        launch_year = rng.int(2020, 2026)
        launch_month = rng.int(1, 12)

        is_nev = p.energy in ("BEV", "PHEV")
        intelligence = round(clamp((74 if is_nev else 56) + p.price * 0.42 + rng.float(-6, 12), 40, 99))
        comfort = round(clamp(52 + p.price * 0.45 + rng.float(-8, 14), 40, 99))
        space = round(clamp(48 + (dims["wheelbase"] - 2600) * 0.06 + (14 if p.category == "MPV" else 0) + rng.float(-8, 12), 40, 99))
        performance = round(clamp(38 + power * 0.075 + rng.float(-8, 12), 30, 99))
        rating = rng_round(clamp(3.9 + (intelligence + comfort) / 700 + rng.float(-0.12, 0.22), 3.6, 4.9), 1)

        base = {
            "price": p.price, "range_km": range_km, "power_kw": power,
            "category": p.category, "wheelbase": dims["wheelbase"],
            "intelligence_score": intelligence, "energy_type": p.energy,
            "launch_year": launch_year, "rating": rating,
        }
        brand_en = next(b[2] for b in BRAND_SEEDS if b[0] == p.brand_id)
        code_prefix = "".join(ch for ch in brand_en.upper() if ch.isalpha())[:4]

        db.add(Car(
            id=p.id,
            brand_id=p.brand_id,
            name=p.name,
            name_norm=p.name,
            model_code=f"{code_prefix}-{p.id:03d}",
            category=p.category,
            energy_type=p.energy,
            price=p.price,
            price_min=rng_round(p.price * rng.float(0.86, 0.94), 2),
            price_max=rng_round(p.price * rng.float(1.02, 1.12), 2),
            range_km=range_km,
            battery_kwh=battery,
            power_kw=power,
            torque_nm=torque,
            wheelbase=dims["wheelbase"],
            length=dims["length"],
            width=dims["width"],
            height=dims["height"],
            seats=CATEGORY_SEATS[p.category],
            launch_date=date(launch_year, launch_month, 1),
            launch_year=launch_year,
            rating=rating,
            intelligence_score=intelligence,
            comfort_score=comfort,
            space_score=space,
            performance_score=performance,
            review_count=rng.int(120, 8600),
            tags=build_tags(base),
            source="seed",
        ))
        count += 1
    db.commit()
    return count


def generate_series(db: Session) -> dict[int, list[int]]:
    """车型 24 月销量序列（校准到全国年销约 2360 万辆）"""
    cars = db.query(Car).all()
    brands = {b.id: b for b in db.query(Brand).all()}

    raw: dict[int, list[float]] = {}
    for car in cars:
        brand = brands.get(car.brand_id)
        rng = Rng(f"base-{car.id}")
        price_factor = clamp(1.65 - float(car.price) / 42, 0.32, 1.65)
        base = (
            (brand.weight if brand else 20)
            * CATEGORY_FACTOR.get(car.category, 1.0)
            * price_factor
            * ENERGY_FACTOR.get(energy_of(car.energy_type), 0.9)
            * rng.float(0.55, 1.5)
            * 100
        )
        rng2 = Rng(f"series-{car.id}")
        is_nev = energy_of(car.energy_type) in ("BEV", "PHEV")
        growth = rng2.float(0.12, 0.52) if is_nev else rng2.float(-0.22, 0.06)
        arr = []
        for i, m in enumerate(MONTHS):
            month_num = int(m[5:7])
            trend = 1 + (growth * i) / len(MONTHS)
            noise = rng2.float(0.86, 1.14)
            ramp = 0.72 + i * 0.1 if i < 3 else 1.0
            arr.append(base * trend * SEASONAL[month_num - 1] * noise * ramp)
        raw[car.id] = arr

    last12_raw = sum(sum(v[-12:]) for v in raw.values())
    scale = TARGET_ANNUAL / last12_raw if last12_raw else 1
    return {cid: [max(30, round(v * scale)) for v in arr] for cid, arr in raw.items()}


def energy_of(raw: str) -> str:
    return "PHEV" if raw == "EREV" else raw


def import_sales(db: Session) -> int:
    if db.query(F.count(CarSales.id)).scalar():
        return 0
    series = generate_series(db)
    cars = {c.id: c for c in db.query(Car).all()}

    rows = []
    for cid, arr in series.items():
        car = cars[cid]
        for i, m in enumerate(MONTHS):
            rows.append(CarSales(
                car_id=cid,
                month=month_date(m),
                sales=arr[i],
                revenue=round(arr[i] * float(car.price), 2),
                source="seed",
            ))
    db.bulk_save_objects(rows)
    db.commit()

    # 回填车型聚合
    ranked = sorted(series.items(), key=lambda t: sum(t[1][-12:]), reverse=True)
    for rank, (cid, arr) in enumerate(ranked, start=1):
        car = cars[cid]
        car.sales_12m = sum(arr[-12:])
        car.last_month_sales = arr[-1]
        car.rank = rank
    db.commit()

    # 品牌聚合
    brand_agg: dict[int, dict[int, int]] = {}
    for cid, arr in series.items():
        bid = cars[cid].brand_id
        brand_agg.setdefault(bid, {})
        for i, m in enumerate(MONTHS):
            brand_agg[bid][i] = brand_agg[bid].get(i, 0) + arr[i]
    db.bulk_save_objects([
        BrandSales(brand_id=bid, month=month_date(m), sales=month_vals[i])
        for bid, month_vals in brand_agg.items()
        for i, m in enumerate(MONTHS)
    ])
    for bid, month_vals in brand_agg.items():
        brand = db.get(Brand, bid)
        if brand:
            brand.model_count = sum(1 for c in cars.values() if c.brand_id == bid)
            brand.annual_sales = sum(month_vals.values())
    db.commit()

    # 能源聚合
    energy_agg: dict[str, dict[int, int]] = {}
    for cid, arr in series.items():
        e = energy_of(cars[cid].energy_type)
        energy_agg.setdefault(e, {})
        for i, m in enumerate(MONTHS):
            energy_agg[e][i] = energy_agg[e].get(i, 0) + arr[i]
    db.bulk_save_objects([
        EnergySales(energy_type=e, month=month_date(m), sales=month_vals[i])
        for e, month_vals in energy_agg.items()
        for i, m in enumerate(MONTHS)
    ])
    db.commit()
    return len(rows)


def import_regional(db: Session) -> int:
    if db.query(F.count(RegionalSales.id)).scalar():
        return 0
    regions = db.query(Region).all()
    total_weight = sum(float(r.weight) for r in regions)
    national = dict(
        (m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7], int(s or 0))
        for m, s in db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
    )
    rows = []
    for region in regions:
        rng = Rng(f"region-{region.name}")
        for m in MONTHS:
            rows.append(RegionalSales(
                region_id=region.id,
                month=month_date(m),
                energy_type=None,
                brand_id=None,
                sales=round(national.get(m, 0) * float(region.weight) / total_weight * rng.float(0.94, 1.06)),
                source="seed",
            ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_users(db: Session) -> int:
    if db.query(F.count(User.id)).scalar() > 4:
        return 0
    rng = Rng("users")
    fixed = [
        ("admin", "赵启明", "admin", "市场研究中心"),
        ("analyst", "孙以宁", "analyst", "数据分析部"),
        ("sales", "周砚清", "sales", "销售运营部"),
        ("user", "吴听澜", "user", "销售运营部"),
    ]
    for i, (username, nickname, role, dept) in enumerate(fixed):
        if db.query(User).filter_by(username=username).first():
            continue
        db.add(User(
            id=i + 1,
            username=username,
            nickname=nickname,
            email=f"{username}@autoinsight.com",
            phone=f"13{str(rng.int(100000000, 999999999))[:9]}",
            password_hash=hash_password(f"{username}123"),
            role=role,
            status="active",
            department=dept,
            created_at=datetime(2025, 1, 12, 9, 20, 31),
            last_login_at=datetime(2026, 9, 2, 20, 41, 5),
            last_login_ip="10.12.33.21",
            login_count=rng.int(120, 860),
            car_count=rng.int(0, 12),
        ))
    db.commit()

    # 普通用户批量生成
    count = 0
    for i in range(4, 46):
        role = rng.pick(["analyst", "sales", "user", "user", "sales"])
        status = rng.pick(["active", "active", "active", "disabled", "pending"])
        username = f"{role}{1000 + i}"
        if db.query(User).filter_by(username=username).first():
            continue
        nickname = NAMES[i % len(NAMES)]
        created = datetime(rng.int(2024, 2026), rng.int(1, 12), rng.int(1, 28), rng.int(9, 20), rng.int(10, 59))
        last_login = (
            datetime(2026, rng.int(7, 9), rng.int(1, 30), rng.int(8, 22), rng.int(10, 59))
            if status != "pending" else None
        )
        db.add(User(
            username=username,
            nickname=nickname,
            email=f"{username}@autoinsight.com",
            phone=f"13{str(rng.int(100000000, 999999999))[:9]}",
            password_hash=hash_password(f"{role}123"),
            role=role,
            status=status,
            department=rng.pick(DEPARTMENTS),
            created_at=created,
            last_login_at=last_login,
            last_login_ip=f"10.{rng.int(10, 60)}.{rng.int(1, 200)}.{rng.int(1, 250)}",
            login_count=rng.int(3, 520),
            car_count=rng.int(0, 20),
        ))
        count += 1
    db.commit()
    return count


def import_inventory(db: Session) -> int:
    if db.query(F.count(Inventory.id)).scalar():
        return 0
    rng = Rng("inventory")
    warehouses = ["华东中心仓", "华南中心仓", "华北中心仓", "西南分仓", "华中分仓"]
    cars = db.query(Car).order_by(Car.id).limit(60).all()
    rows = []
    for i, car in enumerate(cars):
        monthly = max(50, car.last_month_sales or 50)
        quantity = round(monthly * rng.float(0.6, 2.4))
        turnover = rng_round(quantity / monthly * 30, 1)
        rows.append(Inventory(
            car_id=car.id,
            quantity=quantity,
            inbound=round(monthly * rng.float(0.1, 0.8)),
            monthly_sales=monthly,
            turnover_days=turnover,
            warehouse=rng.pick(warehouses),
            status="紧张" if turnover < 25 else "偏低" if turnover < 45 else "充足",
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_orders(db: Session) -> int:
    if db.query(F.count(Order.id)).scalar():
        return 0
    rng = Rng("orders")
    salespeople = NAMES[:12]
    regions = ["华东", "华南", "华北", "华中", "西南", "西北", "东北"]
    cars = db.query(Car).all()
    brand_names = {b.id: b.name for b in db.query(Brand).all()}
    rows = []
    for i in range(160):
        car = rng.pick(cars)
        status = rng.pick(["pending", "paid", "delivered", "delivered", "cancelled"])
        month_idx = rng.int(len(MONTHS) - 3, len(MONTHS) - 1)
        month = MONTHS[month_idx]
        rows.append(Order(
            order_no=f"AI{month.replace('-', '')}{rng.int(10000, 99999)}",
            car_id=car.id,
            customer=rng.pick(NAMES),
            amount=rng_round(float(car.price) * rng.float(0.9, 1.08), 2),
            status=status,
            region=rng.pick(regions),
            salesperson=rng.pick(salespeople),
            created_at=datetime(
                int(month[:4]), int(month[5:7]), rng.int(1, 28), rng.int(9, 20), rng.int(10, 59)
            ),
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_algorithms(db: Session) -> int:
    if db.query(F.count(AlgorithmTask.id)).scalar():
        return 0
    seeds = [
        ("智能购车推荐排序", "recommendation", "AutoRec-CarRanking", "v2.3.1", 0.913, "running", datetime(2026, 9, 3, 8, 0), 184320, "算法平台部 · 陈砚舟"),
        ("车型销量时序预测", "prediction", "XGBoost", "v1.8.0", 0.906, "running", datetime(2026, 9, 3, 6, 30), 46780, "算法平台部 · 秦临风"),
        ("中长期销量预测", "prediction", "LSTM + 季节融合", "v0.9.4", 0.872, "training", datetime(2026, 9, 2, 22, 15), 3260, "算法平台部 · 秦临风"),
        ("舆情情感分类", "sentiment", "BERT-wwm", "v3.0.2", 0.941, "running", datetime(2026, 9, 3, 7, 45), 92150, "算法平台部 · 尤未晞"),
        ("价格弹性预估", "prediction", "LightGBM", "v1.2.0", 0.848, "idle", datetime(2026, 8, 29, 3, 0), 12040, "市场研究中心 · 孙以宁"),
        ("相似车型召回", "recommendation", "Item2Vec", "v1.1.5", 0.886, "failed", datetime(2026, 9, 1, 4, 20), 8930, "算法平台部 · 陈砚舟"),
    ]
    for i, (name, type_, model, version, acc, status, last_run, calls, owner) in enumerate(seeds, start=1):
        db.add(AlgorithmTask(
            id=i, name=name, type=type_, model=model, version=version,
            accuracy=acc, status=status, last_run_at=last_run, calls=calls, owner=owner,
            config={},
        ))
    db.commit()
    return len(seeds)


def import_logs(db: Session) -> int:
    if db.query(F.count(OperationLog.id)).scalar():
        return 0
    rng = Rng("logs")
    actions = [
        ("登录系统", "认证", "success"), ("导出市场分析报表", "市场分析", "success"),
        ("新增车型", "车型管理", "success"), ("编辑车型参数", "车型管理", "success"),
        ("删除车型", "车型管理", "failed"), ("执行销量预测", "销量预测", "success"),
        ("调用智能推荐", "智能推荐", "success"), ("导入销量数据", "数据管理", "success"),
        ("禁用用户账号", "用户管理", "success"), ("更新算法版本", "算法管理", "success"),
        ("导出用户列表", "用户管理", "success"), ("调整库存阈值", "库存管理", "failed"),
    ]
    cars = db.query(Car.name).all()
    users = db.query(User.id).all()
    rows = []
    for i in range(120):
        action, module, result = rng.pick(actions)
        month_idx = rng.int(len(MONTHS) - 2, len(MONTHS) - 1)
        month = MONTHS[month_idx]
        rows.append(OperationLog(
            user_id=rng.pick(users)[0],
            action=action,
            module=module,
            target=rng.pick(cars)[0],
            ip=f"10.{rng.int(10, 60)}.{rng.int(1, 200)}.{rng.int(1, 250)}",
            result=result,
            detail="目标资源被占用，操作已回滚" if result == "failed" else None,
            created_at=datetime(
                int(month[:4]), int(month[5:7]), rng.int(1, 28), rng.int(8, 22), rng.int(10, 59), rng.int(10, 59)
            ),
        ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def import_data_files(db: Session) -> int:
    if db.query(F.count(DataFile.id)).scalar():
        return 0
    seeds = [
        ("car_models_2026Q3.csv", 2480128, "车型数据", "success", 100, datetime(2026, 9, 1, 9, 12), 158, None),
        ("sales_monthly_2024_2026.xlsx", 8912384, "销量数据", "success", 100, datetime(2026, 9, 1, 9, 20), 3792, None),
        ("customer_reviews_2026Q3.csv", 1240576, "评价数据", "success", 100, datetime(2026, 8, 30, 16, 40), 240, None),
        ("brand_master.csv", 86016, "车型数据", "failed", 62, datetime(2026, 8, 28, 11, 2), 0, "第 31 行品牌编码重复，导入中断"),
        ("region_sales_2026Q3.xlsx", 3670016, "销量数据", "success", 100, datetime(2026, 8, 27, 14, 35), 408, None),
    ]
    for i, (name, size, type_, status, progress, uploaded, rows, message) in enumerate(seeds, start=1):
        db.add(DataFile(
            id=i, name=name, size=size, type=type_, status=status,
            progress=progress, rows=rows, message=message, uploaded_at=uploaded,
        ))
    db.commit()
    return len(seeds)


def import_reviews(db: Session) -> int:
    if db.query(F.count(Review.id)).scalar():
        return 0
    rng = Rng("reviews")
    cars = db.query(Car).order_by(Car.id).limit(80).all()
    rows = []
    for i in range(240):
        car = rng.pick(cars)
        positive_prob = clamp((float(car.rating) - 3.6) / 1.2, 0.25, 0.78)
        roll = rng.next()
        if roll < positive_prob:
            label = "positive"
        elif roll < positive_prob + 0.2:
            label = "negative"
        else:
            label = "neutral"
        words = {"positive": POSITIVE_WORDS, "negative": NEGATIVE_WORDS, "neutral": NEUTRAL_WORDS}[label]
        word = rng.pick(words)
        content = rng.pick(REVIEW_TEMPLATES[label]).replace("{w}", word)
        rating = {"positive": rng.int(4, 5), "negative": rng.int(2, 3), "neutral": rng.int(3, 4)}[label]
        month = MONTHS[rng.int(len(MONTHS) - 12, len(MONTHS) - 1)]
        published = date(int(month[:4]), int(month[5:7]), rng.int(1, 28))
        score = {"positive": rng.float(0.75, 0.98), "neutral": rng.float(0.4, 0.6), "negative": rng.float(0.02, 0.3)}[label]
        review = Review(
            car_id=car.id,
            brand_id=car.brand_id,
            user_name=rng.pick(USER_NAMES),
            rating=rating,
            content=content,
            published_at=published,
            likes=rng.int(0, 320),
            source="seed",
        )
        rows.append(review)
    db.bulk_save_objects(rows)
    db.commit()

    sentiments = [
        Sentiment(
            review_id=r.id,
            label=label_of_rating(r.rating, r.content),
            score=rng_round(0.8 if r.rating >= 4 else 0.5 if r.rating == 3 else 0.2, 2),
            keywords=[w for w in (POSITIVE_WORDS + NEGATIVE_WORDS + NEUTRAL_WORDS) if w in r.content],
            model_name="BERT-wwm",
        )
        for r in db.query(Review).all()
    ]
    db.bulk_save_objects(sentiments)
    db.commit()
    return len(rows)


def label_of_rating(rating: int, content: str) -> str:
    neg = any(w in content for w in NEGATIVE_WORDS)
    pos = any(w in content for w in POSITIVE_WORDS)
    if neg and not pos:
        return "negative"
    if pos:
        return "positive"
    return "neutral" if rating == 3 else ("positive" if rating > 3 else "negative")


def import_predictions(db: Session) -> int:
    if db.query(F.count(SalesPrediction.id)).scalar():
        return 0
    series = generate_series(db)
    next_months = []
    y, m = LATEST_YEAR, LATEST_MONTH
    for _ in range(6):
        m += 1
        if m == 13:
            m = 1
            y += 1
        next_months.append(f"{y}-{m:02d}")

    rows = []
    for cid, arr in series.items():
        recent = arr[-6:]
        first_half = sum(recent[:3]) / 3
        second_half = sum(recent[3:]) / 3
        trend_rate = clamp((second_half - first_half) / (first_half or 1), -0.28, 0.36)
        base = second_half
        rng = Rng(f"seed-pred-{cid}")
        accuracy = rng_round(clamp(0.9 - 6 * 0.004 + rng.float(-0.02, 0.035), 0.78, 0.96), 3)
        for i, month in enumerate(next_months, start=1):
            seasonal = SEASONAL[int(month[5:7]) - 1]
            value = max(60, round(base * seasonal * (1 + trend_rate * i / 6) * rng.float(0.94, 1.06)))
            band = clamp(0.045 + i * 0.012, 0.05, 0.22)
            rows.append(SalesPrediction(
                car_id=cid,
                prediction_month=month_date(month),
                predicted_sales=value,
                lower=max(30, round(value * (1 - band))),
                upper=round(value * (1 + band)),
                model_name="XGBoost",
                accuracy=accuracy,
            ))
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def seed_all(fresh: bool = False):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if fresh:
            print("⚠ 清空业务数据表…")
            for model in (Sentiment, Review, SalesPrediction, Recommendation, Order, Inventory,
                          OperationLog, DataFile, AlgorithmTask, RegionalSales, EnergySales,
                          BrandSales, CarSales, ModelAlias, Car, User, Region, Brand):
                db.query(model).delete()
            db.commit()

        print(f"品牌导入: {import_brands(db)} 条")
        print(f"地区导入: {import_regions(db)} 条")
        print(f"车型导入: {import_cars(db)} 款")
        print(f"用户导入: {import_users(db)} 条")
        print(f"车型月销导入: {import_sales(db)} 行（含品牌/能源聚合）")
        print(f"地区月销导入: {import_regional(db)} 行")
        print(f"库存导入: {import_inventory(db)} 条")
        print(f"订单导入: {import_orders(db)} 条")
        print(f"算法任务导入: {import_algorithms(db)} 条")
        print(f"操作日志导入: {import_logs(db)} 条")
        print(f"数据文件导入: {import_data_files(db)} 条")
        print(f"评价导入: {import_reviews(db)} 条（含情感标注）")
        print(f"预测快照导入: {import_predictions(db)} 行")
    print("✅ 种子数据就绪（演示账号 admin/admin123）")


if __name__ == "__main__":
    seed_all(fresh="--fresh" in sys.argv)
