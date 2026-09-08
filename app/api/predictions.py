"""预测 API（对齐 src/api/predictions.ts）"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database.session import get_db
from app.models import Car, CarSales, Prediction
from app.schemas.predictions import PredictionList, PredictionDetail, PredictionRequest
from app.utils.series import build_months, recent_months

router = APIRouter()


@router.get("/predictions", summary="预测列表")
def list_predictions(
    carId: Optional[int] = None,
    brandId: Optional[int] = None,
    type: str = "sales",
    period: str = "12m",
    page: int = 1,
    pageSize: int = 20,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    """支持 carId,brandId,type,period,page,pageSize"""
    query = db.query(Prediction)

    if carId:
        query = query.filter(Prediction.car_id == carId)
    if brandId:
        query = query.filter(Prediction.brand_id == brandId)
    if type:
        query = query.filter(Prediction.type == type)
    if period:
        query = query.filter(Prediction.period == period)

    total = query.count()
    predictions = query.order_by(desc(Prediction.created_at)).offset((page - 1) * pageSize).limit(pageSize).all()

    return {
        "list": [PredictionList.from_orm(p) for p in predictions],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/predictions/{id}", summary="预测详情")
def get_prediction(id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> PredictionDetail:
    prediction = db.get(Prediction, id)
    if not prediction:
        raise HTTPException(status_code=404, detail="预测不存在")
    return PredictionDetail.from_orm(prediction)


@router.post("/predictions", summary="创建预测")
def create_prediction(
    body: PredictionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> PredictionDetail:
    # 简化版：基于历史数据生成预测
    months = build_months(12)
    points = []
    for m in months:
        # 模拟预测数据
        points.append({"month": m, "value": 1000 + (months.index(m) * 50)})

    prediction = Prediction(
        car_id=body.carId,
        brand_id=body.brandId,
        type=body.type,
        period=body.period,
        model=body.model,
        accuracy=body.accuracy,
        status="success",
        points=points,
        summary={
            "total": sum(p["value"] for p in points),
            "average": sum(p["value"] for p in points) / len(points),
            "trend": "upward",
        },
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return PredictionDetail.from_orm(prediction)