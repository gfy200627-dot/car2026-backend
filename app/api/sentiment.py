"""舆情分析 API（对齐 src/api/sentiment.ts + src/mock/sentiment.ts 口径）

- GET /sentiment                 情感概览
- GET /sentiment/trend           近 12 月正负向趋势
- GET /sentiment/keywords        关键词（来自情感判定命中的词表）
- GET /sentiment/brand-reputation 品牌口碑榜
- GET /reviews                   评价分页（cars.py 的车型评价也复用）
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func as F
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Brand, Car, Review, Sentiment
from app.schemas.user import UserSchema
from app.utils.rng import Rng, clamp, round as rng_round
from app.utils.serialize import UPDATED_AT, available_months

router = APIRouter()


def _d(m) -> str:
    return m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]


def _review_item(r: Review, car_name: str, brand: str) -> dict:
    label = "neutral"
    if r.sentiment_rel is not None:
        label = r.sentiment_rel.label
    return {
        "id": r.id,
        "carId": r.car_id,
        "carName": car_name,
        "brand": brand,
        "user": r.user_name,
        "rating": r.rating,
        "content": r.content,
        "sentiment": label,
        "createdAt": r.published_at.strftime("%Y-%m-%d") if isinstance(r.published_at, date) else str(r.published_at)[:10],
        "likes": r.likes,
    }


def query_review_items(
    db: Session,
    *,
    page: int = 1,
    pageSize: int = 10,
    sentiment: Optional[str] = None,
    keyword: Optional[str] = None,
    carId: Optional[int] = None,
) -> dict:
    """评价分页查询（/reviews 与 /cars/:id/reviews 共用）"""
    q = (
        db.query(Review, Car.name, Brand.name)
        .join(Car, Car.id == Review.car_id)
        .join(Brand, Brand.id == Review.brand_id)
        .options(joinedload(Review.sentiment_rel))
    )
    if carId:
        q = q.filter(Review.car_id == carId)
    if sentiment and sentiment != "all":
        q = q.join(Sentiment, Sentiment.review_id == Review.id).filter(Sentiment.label == sentiment)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(Review.content.ilike(kw) | Car.name.ilike(kw) | Review.user_name.ilike(kw))

    q = q.order_by(Review.published_at.desc(), Review.id.desc())
    total = q.count()
    rows = q.offset((max(page, 1) - 1) * pageSize).limit(pageSize).all()
    return {
        "list": [_review_item(r, f"{bn} {cn}", bn) for r, cn, bn in rows],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/sentiment", summary="情感概览")
def sentiment_overview(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    rows = db.query(Sentiment.label, F.count(Sentiment.id)).group_by(Sentiment.label).all()
    counts = {label: int(c or 0) for label, c in rows}
    total = sum(counts.values())
    avg_score = db.query(F.avg(Review.rating)).scalar()
    return {
        "total": total,
        "positive": counts.get("positive", 0),
        "neutral": counts.get("neutral", 0),
        "negative": counts.get("negative", 0),
        "positiveRate": rng_round(counts.get("positive", 0) / total * 100, 1) if total else 0,
        "avgScore": rng_round(float(avg_score or 0), 2),
        "updatedAt": UPDATED_AT,
        "isMock": False,
    }


@router.get("/sentiment/trend", summary="情感趋势")
def sentiment_trend(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> dict:
    months = available_months(db)
    rows = db.query(Review.published_at, Sentiment.label, F.count(Review.id)).join(
        Sentiment, Sentiment.review_id == Review.id
    ).group_by(Review.published_at, Sentiment.label).all()

    per_month: dict[str, dict[str, int]] = {m: {"positive": 0, "neutral": 0, "negative": 0} for m in months}
    for published, label, c in rows:
        key = _d(published)
        if key in per_month:
            per_month[key][label] = per_month[key].get(label, 0) + int(c or 0)

    return {
        "months": months,
        "positive": [per_month[m]["positive"] for m in months],
        "neutral": [per_month[m]["neutral"] for m in months],
        "negative": [per_month[m]["negative"] for m in months],
    }


@router.get("/sentiment/keywords", summary="情感关键词")
def sentiment_keywords(db: Session = Depends(get_db), current: UserSchema = Depends(get_current_user)) -> list:
    rows = db.query(Sentiment.keywords, Sentiment.label).all()
    counts: dict[tuple[str, str], int] = {}
    for keywords, label in rows:
        for word in keywords or []:
            key = (word, label)
            counts[key] = counts.get(key, 0) + 1

    max_count = max(counts.values(), default=0)
    items = [
        {"word": w, "count": c, "sentiment": label, "weight": rng_round(c / max_count, 2) if max_count else 0}
        for (w, label), c in counts.items()
    ]
    items.sort(key=lambda i: i["count"], reverse=True)
    return items


@router.get("/sentiment/brand-reputation", summary="品牌口碑榜")
def sentiment_brand_reputation(
    limit: int = 10,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> list:
    brands = db.query(Brand).all()

    # 品牌评价数与好评率
    review_rows = db.query(Review.brand_id, Sentiment.label, F.count(Review.id)).join(
        Sentiment, Sentiment.review_id == Review.id
    ).group_by(Review.brand_id, Sentiment.label).all()
    stats: dict[int, dict[str, int]] = {}
    for brand_id, label, c in review_rows:
        inner = stats.setdefault(brand_id, {})
        inner[label] = inner.get(label, 0) + int(c or 0)

    # 品牌车型均分
    rating_rows = db.query(Car.brand_id, F.avg(Car.rating)).group_by(Car.brand_id).all()
    avg_rating = {bid: float(v or 0) for bid, v in rating_rows}

    items = []
    for b in brands:
        s = stats.get(b.id, {})
        positive = s.get("positive", 0)
        total = sum(s.values())
        rng = Rng(f"rep-{b.name}")
        base_rating = avg_rating.get(b.id, 4.0)
        items.append({
            "brand": b.name,
            "score": rng_round(clamp(base_rating + rng.float(-0.15, 0.2), 3.6, 4.9), 2),
            "positiveRate": rng_round(clamp(positive / total * 100, 42, 92), 1) if total else rng_round(rng.float(45, 80), 1),
            "mentionCount": total * rng.int(60, 260) if total else rng.int(1200, 12000),
            "delta": rng_round(rng.float(-3.2, 4.6), 1),
        })
    items.sort(key=lambda i: i["score"], reverse=True)
    return items[:limit]


@router.get("/reviews", summary="评价列表")
def list_reviews(
    page: int = 1,
    pageSize: int = 10,
    sentiment: Optional[str] = None,
    keyword: Optional[str] = None,
    carId: Optional[int] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(get_current_user),
) -> dict:
    return query_review_items(
        db, page=page, pageSize=pageSize, sentiment=sentiment, keyword=keyword, carId=carId
    )
