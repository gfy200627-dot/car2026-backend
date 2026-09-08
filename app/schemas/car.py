"""车型 Schema（对齐 src/types/business.ts Car / CarSalesHistory / ReviewItem）

接口层直接输出 dict（由 app/utils/serialize.car_to_dict 构造），
本模块作为契约文档与后续强类型化的基础。
"""

from typing import List, Optional

from pydantic import BaseModel


class CarItem(BaseModel):
    """车型（前端 Car 契约：range/battery/power/torque/sales 字段名）"""

    id: int
    brandId: int
    brand: str
    name: str
    modelCode: str
    category: str
    energyType: str
    price: float
    priceMin: float
    priceMax: float
    range: int
    battery: float
    power: int
    torque: int
    wheelbase: int
    length: int
    width: int
    height: int
    seats: int
    launchDate: str  # YYYY-MM
    launchYear: int
    sales: int
    lastMonthSales: int
    rating: float
    intelligenceScore: int
    comfortScore: int
    spaceScore: int
    performanceScore: int
    reviewCount: int
    image: Optional[str] = None
    tags: List[str] = []
    rank: Optional[int] = None


class CarSalesHistory(BaseModel):
    carId: int
    carName: str
    points: List[dict]  # [{month, value}]
    yoy: List[float]  # 与 points 等长的逐月同比 %


class ReviewItem(BaseModel):
    id: int
    carId: int
    carName: str
    brand: str
    user: str
    rating: int
    content: str
    sentiment: str
    createdAt: str
    likes: int
