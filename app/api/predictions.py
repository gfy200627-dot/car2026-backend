"""预测 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/predict/sales")
def predict_sales(): pass