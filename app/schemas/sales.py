"""销量相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class SalesTrend(BaseModel):
    points: List[dict]
    yoy: float


class SalesRanking(BaseModel):
    list: List[dict]
    total: int


class SalesRegion(BaseModel):
    list: List[dict]
    total: int


class SalesEnergy(BaseModel):
    list: List[dict]
    total: int