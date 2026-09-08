"""推荐相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class RecommendationList(BaseModel):
    id: int
    carId: int
    brandId: int
    type: str
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
            model=obj.model,
            status=obj.status,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class RecommendationDetail(BaseModel):
    id: int
    carId: int
    brandId: int
    type: str
    model: str
    status: str
    cars: List[int]
    summary: dict


class RecommendationRequest(BaseModel):
    carId: int
    brandId: int
    type: str
    model: str
    category: str
    energyType: str
    price: float