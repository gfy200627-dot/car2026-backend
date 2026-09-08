"""舆情分析 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/sentiment")
def sentiment_overview(): pass

@router.get("/sentiment/trend")
def sentiment_trend(): pass

@router.get("/sentiment/keywords")
def sentiment_keywords(): pass

@router.get("/sentiment/brand-reputation")
def sentiment_brand_reputation(): pass

@router.get("/reviews")
def list_reviews(): pass