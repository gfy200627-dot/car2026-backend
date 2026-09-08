"""智能推荐 Schema（对齐 src/types/business.ts RecommendResult / Recommendation）"""

from typing import List, Optional

from pydantic import BaseModel


class ScoreDimension(BaseModel):
    key: str
    label: str
    score: float  # 0~100
    desc: Optional[str] = None


class RecommendationItem(BaseModel):
    carId: int
    carName: str
    brand: str
    image: Optional[str] = None
    score: float  # 综合匹配度 0~100
    reason: str
    price: float
    energyType: str
    range: int
    rating: float
    dimensions: List[ScoreDimension]
    highlights: List[str]


class RecommendResult(BaseModel):
    requestId: str
    model: str
    generatedAt: str
    isMock: bool = False
    recommendations: List[RecommendationItem]


class RecommendOptions(BaseModel):
    budgets: List[dict]
    usages: List[dict]
    concerns: List[dict]
    provinces: List[str]
    cities: dict
    energies: List[dict]
