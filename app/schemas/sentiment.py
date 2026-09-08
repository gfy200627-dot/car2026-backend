"""舆情分析 Schema（对齐 src/types/business.ts Sentiment* 系列）"""

from typing import List, Optional

from pydantic import BaseModel


class SentimentOverview(BaseModel):
    total: int
    positive: int
    neutral: int
    negative: int
    positiveRate: float
    avgScore: float
    updatedAt: str
    isMock: bool = False


class SentimentTrend(BaseModel):
    months: List[str]
    positive: List[int]
    neutral: List[int]
    negative: List[int]


class KeywordItem(BaseModel):
    word: str
    count: int
    sentiment: str  # positive/neutral/negative
    weight: Optional[float] = None  # 0~1


class BrandReputation(BaseModel):
    brand: str
    score: float  # 口碑分 0~5
    positiveRate: float
    mentionCount: int
    delta: Optional[float] = None


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
