"""Schema 统一导出：`from app.schemas import UserProfile, ...`"""

from app.schemas.user import LoginRequest, LoginResult, UserProfile, UserSchema
from app.schemas.car import CarItem, CarSalesHistory, ReviewItem
from app.schemas.market import (
    MarketOptions,
    MultiSeries,
    ProportionItem,
    RankingItem,
    RegionSalesItem,
    SalesRecord,
    SeriesItem,
)
from app.schemas.predictions import PredictPoint, PredictResult
from app.schemas.recommendations import RecommendOptions, RecommendResult, RecommendationItem, ScoreDimension
from app.schemas.sentiment import (
    BrandReputation,
    KeywordItem,
    SentimentOverview,
    SentimentTrend,
)
from app.schemas.admin import (
    AdminOverview,
    AdminUserItem,
    AlgorithmTaskItem,
    BrandItem,
    DataFileItem,
    InventoryItem,
    OperationLogItem,
    OrderItem,
)

__all__ = [
    "LoginRequest", "LoginResult", "UserProfile", "UserSchema",
    "CarItem", "CarSalesHistory", "ReviewItem",
    "MarketOptions", "MultiSeries", "ProportionItem", "RankingItem", "RegionSalesItem", "SalesRecord", "SeriesItem",
    "PredictPoint", "PredictResult",
    "RecommendOptions", "RecommendResult", "RecommendationItem", "ScoreDimension",
    "BrandReputation", "KeywordItem", "SentimentOverview", "SentimentTrend",
    "AdminOverview", "AdminUserItem", "AlgorithmTaskItem", "BrandItem",
    "DataFileItem", "InventoryItem", "OperationLogItem", "OrderItem",
]
