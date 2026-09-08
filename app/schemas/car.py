"""车型相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class CarList(BaseModel):
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
    rangeKm: int
    batteryKwh: float
    powerKw: int
    torqueNm: int
    wheelbase: int
    length: int
    width: int
    height: int
    seats: int
    launchDate: str
    launchYear: int
    sales12m: int
    lastMonthSales: int
    rating: float
    intelligenceScore: int
    comfortScore: int
    spaceScore: int
    performanceScore: int
    reviewCount: int
    rank: Optional[int]
    tags: List[str]

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            brandId=obj.brand_id,
            brand=obj.brand,
            name=obj.name,
            modelCode=obj.model_code,
            category=obj.category,
            energyType=obj.energy_type,
            price=obj.price,
            priceMin=obj.price_min,
            priceMax=obj.price_max,
            rangeKm=obj.range_km,
            batteryKwh=obj.battery_kwh,
            powerKw=obj.power_kw,
            torqueNm=obj.torque_nm,
            wheelbase=obj.wheelbase,
            length=obj.length,
            width=obj.width,
            height=obj.height,
            seats=obj.seats,
            launchDate=obj.launch_date.strftime("%Y-%m-%d"),
            launchYear=obj.launch_year,
            sales12m=obj.sales_12m,
            lastMonthSales=obj.last_month_sales,
            rating=obj.rating,
            intelligenceScore=obj.intelligence_score,
            comfortScore=obj.comfort_score,
            spaceScore=obj.space_score,
            performanceScore=obj.performance_score,
            reviewCount=obj.review_count,
            rank=obj.rank,
            tags=obj.tags,
        )


class CarDetail(CarList):
    """车型详情（含图片、源）"""
    image: Optional[str]
    source: str


class CarSalesResponse(BaseModel):
    points: List[dict]
    yoy: float


class SimilarCar(BaseModel):
    id: int
    brandId: int
    brand: str
    name: str
    modelCode: str
    category: str
    energyType: str
    price: float
    rangeKm: int
    rating: float

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            brandId=obj.brand_id,
            brand=obj.brand,
            name=obj.name,
            modelCode=obj.model_code,
            category=obj.category,
            energyType=obj.energy_type,
            price=obj.price,
            rangeKm=obj.range_km,
            rating=obj.rating,
        )


class ReviewList(BaseModel):
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

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            carId=obj.car_id,
            carName=obj.car_name,
            brand=obj.brand,
            user=obj.user_name,
            rating=obj.rating,
            content=obj.content,
            sentiment=obj.sentiment_rel.label if obj.sentiment_rel else "neutral",
            createdAt=obj.published_at.strftime("%Y-%m-%d"),
            likes=obj.likes,
        )