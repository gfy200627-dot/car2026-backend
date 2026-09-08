"""预测相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class PredictionList(BaseModel):
    id: int
    carId: int
    brandId: int
    type: str
    period: str
    model: str
    accuracy: float
    status: str
    createdAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            carId=obj.car_id,
            brandId=obj.brand_id,
            type=obj.type,
            period=obj.period,
            model=obj.model,
            accuracy=obj.accuracy,
            status=obj.status,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class PredictionDetail(PredictionList):
    points: List[dict]
    summary: dict


class PredictionRequest(BaseModel):
    carId: int
    brandId: int
    type: str
    period: str
    model: str
    accuracy: float