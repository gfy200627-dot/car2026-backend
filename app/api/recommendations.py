"""推荐 API（对齐 src/api/recommendations.ts）"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, CarSales, Recommendation
from app.schemas.recommendations import RecommendationList, RecommendationDetail, RecommendationRequest
from app.utils.series import build_months, recent_months

router = APIRouter()


@router.get("/recommendations", summary="推荐列表")
def list_recommendations(
    carId: Optional[int] = None,
    brandId: Optional[int] = None,
    type: str = "similar",
    page: int = 1,
    pageSize: int = 20,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    """支持 carId,brandId,type,page,pageSize"""
    query = db.query(Recommendation)

    if carId:
        query = query.filter(Recommendation.car_id == carId)
    if brandId:
        query = query.filter(Recommendation.brand_id == brandId)
    if type:
        query = query.filter(Recommendation.type == type)

    total = query.count()
    recommendations = query.order_by(desc(Recommendation.created_at)).offset((page - 1) * pageSize).limit(pageSize).all()

    return {
        "list": [RecommendationList.from_orm(r) for r in recommendations],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/recommendations/{id}", summary="推荐详情")
def get_recommendation(id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    recommendation = db.get(Recommendation, id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="推荐不存在")
    return {"detail": recommendation}


@router.post("/recommendations", summary="创建推荐")
def create_recommendation(
    body: RecommendationRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    # 简化版：基于相似度生成推荐
    cars = db.query(Car).filter(
        Car.id != body.carId,
        Car.category == body.category,
        Car.energy_type == body.energyType,
    ).order_by(func.abs(Car.price - body.price)).limit(5).all()

    recommendation = Recommendation(
        car_id=body.carId,
        type=body.type,
        model=body.model,
        status="success",
        cars=[c.id for c in cars],
        summary={
            "total": len(cars),
            "similarity": "high",
            "reason": "价格/类别/能源类型相似",
        },
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return {"detail": recommendation}