"""ORM 模型统一导出：`from app.models import Car, Brand, ...`

约定：SQLAlchemy 模型在本包直接导出；API 层如需别名避免与
Pydantic Schema 冲突，使用 `from app.models import User as UserModel`。
"""

from app.models.brand import Brand, BrandAlias
from app.models.car import Car, ModelAlias
from app.models.collection import CollectionLog
from app.models.mixins import TimestampMixin
from app.models.prediction import Recommendation, SalesPrediction
from app.models.review import Review, Sentiment
from app.models.sales import BrandSales, CarSales, EnergySales, Region, RegionalSales
from app.models.admin import (
    AlgorithmTask,
    DataFile,
    Inventory,
    OperationLog,
    Order,
    User,
)

__all__ = [
    "Brand",
    "BrandAlias",
    "Car",
    "ModelAlias",
    "CollectionLog",
    "TimestampMixin",
    "Recommendation",
    "SalesPrediction",
    "Review",
    "Sentiment",
    "BrandSales",
    "CarSales",
    "EnergySales",
    "Region",
    "RegionalSales",
    "User",
]
