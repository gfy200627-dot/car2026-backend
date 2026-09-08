"""市场与销量 Schema（对齐 src/types/api.ts MultiSeries / ProportionItem / RankingItem 等）"""

from typing import List, Optional

from pydantic import BaseModel


class SeriesItem(BaseModel):
    name: str
    data: List[float]
    type: Optional[str] = None  # line/bar
    unit: Optional[str] = None


class MultiSeries(BaseModel):
    months: List[str]
    series: List[SeriesItem]


class RankingItem(BaseModel):
    name: str
    value: float
    share: Optional[float] = None  # 0~1
    yoy: Optional[float] = None
    extra: Optional[str] = None


class ProportionItem(BaseModel):
    name: str
    value: float
    ratio: Optional[float] = None  # 0~1


class RegionSalesItem(BaseModel):
    name: str
    value: int
    yoy: Optional[float] = None
    penetration: Optional[float] = None


class SalesRecord(BaseModel):
    """销量明细行（前端 SalesRecord 契约）"""

    id: int
    carId: int
    carName: str
    brand: str
    month: str
    sales: int
    revenue: float
    region: str
    energyType: str


class MarketOptions(BaseModel):
    years: List[str]
    months: List[int]
    brands: List[dict]
    energies: List[dict]
    categories: List[str]
    regions: List[str]
    updatedAt: str
