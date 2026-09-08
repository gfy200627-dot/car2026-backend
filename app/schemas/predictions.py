"""预测相关 Schema（对齐 src/types/business.ts PredictResult）"""

from typing import List, Optional

from pydantic import BaseModel


class PredictPoint(BaseModel):
    month: str
    value: int
    lower: Optional[int] = None
    upper: Optional[int] = None


class PredictResult(BaseModel):
    carId: Optional[int] = None
    carName: str
    brand: Optional[str] = None
    model: str
    accuracy: float  # 0~1
    horizon: int  # 3/6/12
    history: List[dict]  # [{month, value}]
    prediction: List[PredictPoint]
    updatedAt: str
    growthRate: Optional[float] = None
    peakMonth: Optional[str] = None
    lowMonth: Optional[str] = None
    isMock: bool = False
    features: Optional[List[dict]] = None  # [{name, importance}]
