"""舆情分析相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class SentimentList(BaseModel):
    id: int
    carId: int
    brandId: int
    type: str
    period: str
    model: str
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
            status=obj.status,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class SentimentDetail(SentimentList):
    summary: dict


class SentimentRequest(BaseModel):
    carId: int
    brandId: int
    type: str
    period: str
    model: str