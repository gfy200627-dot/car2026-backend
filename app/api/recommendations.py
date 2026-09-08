"""智能购车推荐 API（对齐 src/api/recommend.ts + src/mock/recommend.ts 算法口径）

硬约束过滤（预算/能源）→ 多维度打分 → 按用户关注因素加权排序，
结果快照写入 recommendations 表（request_hash 幂等）。
"""

import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, Recommendation
from app.schemas.user import UserSchema
from app.utils.rng import Rng, clamp, round as rng_round
from app.utils.serialize import ENERGY_LABEL, energy_out

router = APIRouter()

BUDGET_OPTIONS = [
    {"value": "lt10", "label": "10万以下", "min": 0.0, "max": 10.0},
    {"value": "10-15", "label": "10~15万", "min": 10.0, "max": 15.0},
    {"value": "15-20", "label": "15~20万", "min": 15.0, "max": 20.0},
    {"value": "20-30", "label": "20~30万", "min": 20.0, "max": 30.0},
    {"value": "gt30", "label": "30万以上", "min": 30.0, "max": 1000.0},
]

USAGE_OPTIONS = [
    {"value": "commute", "label": "通勤代步", "desc": "日常上下班、城市短途"},
    {"value": "family", "label": "家庭用车", "desc": "多人出行、儿童安全"},
    {"value": "business", "label": "商务接待", "desc": "形象气质、乘坐舒适"},
    {"value": "longtrip", "label": "长途自驾", "desc": "高速续航、可靠性"},
    {"value": "outdoor", "label": "户外越野", "desc": "通过性、装载能力"},
]

CONCERN_OPTIONS = [
    {"value": "price", "label": "价格", "desc": "购车预算与用车成本"},
    {"value": "range", "label": "续航", "desc": "续航里程与补能便利"},
    {"value": "performance", "label": "性能", "desc": "动力与操控表现"},
    {"value": "space", "label": "空间", "desc": "乘坐与装载空间"},
    {"value": "intelligence", "label": "智能化", "desc": "智能座舱与辅助驾驶"},
    {"value": "comfort", "label": "舒适性", "desc": "底盘滤震与静谧性"},
]

PROVINCES = [
    "广东省", "江苏省", "山东省", "浙江省", "河南省", "四川省", "河北省", "湖北省",
    "湖南省", "安徽省", "上海市", "北京市", "福建省", "陕西省", "重庆市", "天津市",
]

CITY_MAP = {
    "广东省": ["广州市", "深圳市", "东莞市", "佛山市"],
    "江苏省": ["南京市", "苏州市", "无锡市", "常州市"],
    "山东省": ["济南市", "青岛市", "烟台市", "潍坊市"],
    "浙江省": ["杭州市", "宁波市", "温州市", "嘉兴市"],
    "河南省": ["郑州市", "洛阳市", "南阳市"],
    "四川省": ["成都市", "绵阳市", "德阳市"],
    "河北省": ["石家庄市", "唐山市", "保定市"],
    "湖北省": ["武汉市", "宜昌市", "襄阳市"],
    "湖南省": ["长沙市", "株洲市", "湘潭市"],
    "安徽省": ["合肥市", "芜湖市"],
    "上海市": ["上海市"],
    "北京市": ["北京市"],
    "福建省": ["福州市", "厦门市", "泉州市"],
    "陕西省": ["西安市", "咸阳市"],
    "重庆市": ["重庆市"],
    "天津市": ["天津市"],
}


def _budget_range(budget: str) -> dict:
    return next((b for b in BUDGET_OPTIONS if b["value"] == budget), BUDGET_OPTIONS[2])


def _price_score(price: float, budget: str) -> float:
    b = _budget_range(budget)
    center = (b["min"] + min(b["max"], b["min"] + 20)) / 2
    span = max(1.0, min(b["max"], b["min"] + 20) - b["min"])
    return clamp(100 - abs(price - center) / span * 110, 42, 100)


def _range_score(energy: str, range_km: int) -> float:
    if energy == "BEV":
        return clamp(range_km / 620 * 100, 30, 100)
    if energy == "PHEV":
        return clamp(55 + range_km / 240 * 40, 55, 96)
    return 58


def _scenario_score(car: Car, scenarios: list) -> float:
    if not scenarios:
        return 70.0
    total = 0.0
    for s in scenarios:
        v = 60.0
        if s == "commute":
            v = 88 if car.category == "轿车" else 74 if car.category == "SUV" else 55
            if float(car.price) <= 18:
                v += 6
            if energy_out(car.energy_type) in ("BEV", "PHEV"):
                v += 6
        elif s == "family":
            v = 92 if car.category == "MPV" else 88 if car.category == "SUV" else 62
            v += (car.space_score - 60) * 0.28
            if car.seats >= 6:
                v += 6
        elif s == "business":
            v = 90 if car.category == "MPV" else 84 if car.category == "轿车" else 66
            v += (float(car.price) - 20) * 0.55
            v += (car.comfort_score - 60) * 0.22
        elif s == "longtrip":
            v = 52 + (32 if car.range_km >= 600 else car.range_km / 20)
            v += (car.comfort_score - 60) * 0.18
            if car.category == "SUV":
                v += 5
        elif s == "outdoor":
            v = 88 if car.category == "SUV" else 90 if car.category == "皮卡" else 48
            v += (car.performance_score - 60) * 0.24
        total += clamp(v, 30, 100)
    return rng_round(total / len(scenarios), 1)


@router.get("/recommend/options", summary="推荐筛选选项")
def recommend_options(current: UserSchema = Depends(get_current_user)) -> dict:
    return {
        "budgets": [{"value": b["value"], "label": b["label"]} for b in BUDGET_OPTIONS],
        "usages": USAGE_OPTIONS,
        "concerns": CONCERN_OPTIONS,
        "provinces": PROVINCES,
        "cities": CITY_MAP,
        "energies": [{"value": e, "label": ENERGY_LABEL[e]} for e in ("BEV", "PHEV", "HEV", "ICE")],
    }


@router.post("/recommend", summary="智能购车推荐")
def recommend(
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    budget = str(body.get("budget") or "15-20")
    energy_types = body.get("energyTypes") or ["BEV", "PHEV"]
    scenarios = body.get("scenarios") or ["commute"]
    top_n = int(body.get("topN") or 6)
    weights = body.get("weights") or {}

    request_json = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    request_hash = hashlib.md5(request_json.encode("utf-8")).hexdigest()
    request_id = f"RC{int(hashlib.sha1(request_json.encode('utf-8')).hexdigest(), 16) % 100000000:08d}"
    rng = Rng(f"rec-{request_id}")

    b = _budget_range(budget)
    energy_set = set(energy_types) or {"BEV", "PHEV", "HEV", "ICE"}

    cars = db.query(Car).options(joinedload(Car.brand_rel)).filter(
        Car.price >= b["min"], Car.price < b["max"]
    ).all()
    candidates = [c for c in cars if energy_out(c.energy_type) in energy_set]

    w = {
        "price": float(weights.get("price", 60)),
        "range": float(weights.get("range", 60)),
        "performance": float(weights.get("performance", 60)),
        "space": float(weights.get("space", 60)),
        "intelligence": float(weights.get("intelligence", 60)),
        "comfort": float(weights.get("comfort", 60)),
    }
    w_total = sum(w.values()) or 1

    scored = []
    for car in candidates:
        p_score = _price_score(float(car.price), budget)
        r_score = _range_score(energy_out(car.energy_type), car.range_km)
        s_score = _scenario_score(car, scenarios)

        factor_scores = {
            "price": p_score,
            "range": r_score,
            "performance": float(car.performance_score),
            "space": float(car.space_score),
            "intelligence": float(car.intelligence_score),
            "comfort": float(car.comfort_score),
        }
        weighted = sum(factor_scores[k] * w[k] for k in w) / w_total
        score = clamp(weighted * 0.82 + (float(car.rating) / 5) * 100 * 0.1 + s_score * 0.08 + rng.float(-1.6, 1.6), 40, 99)

        highlights = []
        if p_score >= 82:
            highlights.append("价格契合预算")
        if r_score >= 80:
            highlights.append("续航表现优秀")
        if car.category == "SUV" and "family" in scenarios:
            highlights.append("适配家庭出行")
        if car.intelligence_score >= 85:
            highlights.append("智能化配置领先")
        if car.performance_score >= 82:
            highlights.append("动力储备充足")
        if car.space_score >= 85:
            highlights.append("乘坐空间宽敞")
        if float(car.price) <= 15 and energy_out(car.energy_type) == "BEV":
            highlights.append("用车成本低")
        if not highlights:
            highlights.append("综合表现均衡")

        dimensions = [
            {"key": "price", "label": "价格匹配", "score": rng_round(p_score, 1)},
            {"key": "range", "label": "续航匹配", "score": rng_round(r_score, 1)},
            {"key": "energy", "label": "能源匹配", "score": 100},
            {"key": "usage", "label": "用途匹配", "score": rng_round(s_score, 1)},
            {"key": "intelligence", "label": "智能化", "score": car.intelligence_score},
            {"key": "space", "label": "空间", "score": car.space_score},
            {"key": "performance", "label": "性能", "score": car.performance_score},
            {"key": "comfort", "label": "舒适性", "score": car.comfort_score},
        ]

        top_factor = max(w, key=lambda k: w[k])
        top_label = next((o["label"] for o in CONCERN_OPTIONS if o["value"] == top_factor), "综合")
        brand_name = car.brand_rel.name if car.brand_rel else ""
        car_name = f"{brand_name} {car.name}"
        final_score = rng_round(score, 1)
        reason = _build_reason(car_name, top_label, dimensions, car.range_km, final_score, scenarios)

        scored.append({
            "car": car,
            "item": {
                "carId": car.id,
                "carName": car_name,
                "brand": brand_name,
                "image": car.image,
                "score": final_score,
                "reason": reason,
                "price": round(float(car.price), 2),
                "energyType": energy_out(car.energy_type),
                "range": car.range_km,
                "rating": round(float(car.rating), 1),
                "dimensions": dimensions,
                "highlights": highlights[:3],
            },
        })

    scored.sort(key=lambda t: t["item"]["score"], reverse=True)
    top = scored[:top_n]

    # 推荐快照入库（幂等：同 request_hash 覆盖）
    db.query(Recommendation).filter(Recommendation.request_hash == request_hash).delete()
    for rank, entry in enumerate(top, start=1):
        db.add(Recommendation(
            request_hash=request_hash,
            request_body=body,
            car_id=entry["car"].id,
            score=entry["item"]["score"],
            rank_no=rank,
            reason=entry["item"]["reason"],
            model_name="AutoRec-CarRanking v2.3",
        ))
    db.commit()

    return {
        "requestId": request_id,
        "model": "AutoRec-CarRanking v2.3",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "isMock": False,
        "recommendations": [entry["item"] for entry in top],
    }


def _build_reason(car_name: str, top_label: str, dimensions: list, range_km: int, score: float, scenarios: list) -> str:
    def dim(key: str) -> float:
        return next((d["score"] for d in dimensions if d["key"] == key), 0)

    parts = [f"{car_name} 在您关注的「{top_label}」维度表现突出"]
    if dim("price") >= 82:
        parts.append("价格落在预算核心区间")
    if dim("range") >= 78:
        parts.append(f"续航 {range_km}km 满足日常与中长途出行")
    if dim("usage") >= 80:
        parts.append("与所选用车场景高度契合")
    if dim("intelligence") >= 85:
        parts.append("智能化配置处于同价位第一梯队")
    scenario = "、".join(
        o["label"] for o in USAGE_OPTIONS if o["value"] in scenarios
    )
    if scenario:
        parts.append(f"适配{scenario}场景")
    return f"{('，').join(parts)}。综合匹配度 {score}%。"
