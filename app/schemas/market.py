"""市场分析相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class MarketOptions(BaseModel):
    brands: List[dict]
    energies: List[dict]
    categories: List[dict]
    years: List[int]
    priceBuckets: List[dict]
    regions: List[dict]
    months: List[str]
    updatedAt: str


class MarketTrendResponse(BaseModel):
    points: List[dict]
    yoy: float


class MarketShare(BaseModel):
    list: List[dict]
    total: int


class MarketPenetration(BaseModel):
    list: List[dict]
    total: int


class MarketPrice(BaseModel):
    list: List[dict]
    total: int


class MarketBrandRank(BaseModel):
    list: List[dict]
    total: int


class MarketCategory(BaseModel):
    list: List[dict]
    total: int


class MarketCategoryTrend(BaseModel):
    points: List[dict]
    yoy: float