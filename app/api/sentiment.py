"""舆情分析 API（对齐 src/api/sentiment.ts）"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, Review, SentimentAnalysis
from app.schemas.sentiment import SentimentList, SentimentDetail, SentimentRequest
from app.utils.series import build_months, recent_months

router = APIRouter()


@router.get("/sentiment", summary="舆情列表")
def list_sentiment(
    carId: Optional[int] = None,
    brandId: Optional[int] = None,
    type: str = "overall",
    period: str = "12m",
    page: int = 1,
    pageSize: int = 20,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    """支持 carId,brandId,type,period,page,pageSize"""
    query = db.query(SentimentAnalysis)

    if carId:
        query = query.filter(SentimentAnalysis.car_id == carId)
    if brandId:
        query = query.filter(SentimentAnalysis.brand_id == brandId)
    if type:
        query = query.filter(SentimentAnalysis.type == type)
    if period:
        query = query.filter(SentimentAnalysis.period == period)

    total = query.count()
    sentiments = query.order_by(desc(SentimentAnalysis.created_at)).offset((page - 1) * pageSize).limit(pageSize).all()

    return {
        "list": [SentimentList.from_orm(s) for s in sentiments],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/sentiment/{id}", summary="舆情详情")
def get_sentiment(id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    sentiment = db.get(SentimentAnalysis, id)
    if not sentiment:
        raise HTTPException(status_code=404, detail="舆情分析不存在")
    return {"detail": sentiment}


@router.post("/sentiment", summary="创建舆情分析")
def create_sentiment(
    body: SentimentRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    # 简化版：基于评价生成舆情分析
    reviews = db.query(Review).filter(Review.car_id == body.carId).all()
    
    positive = sum(1 for r in reviews if r.rating >= 4)
    neutral = sum(1 for r in reviews if r.rating == 3)
    negative = sum(1 for r in reviews if r.rating <= 2)
    total = len(reviews)
    
    sentiment = SentimentAnalysis(
        car_id=body.carId,
        brand_id=body.brandId,
        type=body.type,
        period=body.period,
        model=body.model,
        status="success",
        summary={
            "total": total,
            "positive": positive,
            "neutral": neutral,
            "negative": negative,
            "positive_rate": round(positive / total * 100, 1) if total else 0,
            "overall_sentiment": "positive" if positive > negative else "negative",
        },
    )
    db.add(sentiment)
    db.commit()
    db.refresh(sentiment)
    return {"detail": sentiment}