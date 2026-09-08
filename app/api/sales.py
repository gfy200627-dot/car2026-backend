"""销量 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/sales")
def list_sales(): pass

@router.get("/sales/trend")
def sales_trend(): pass

@router.get("/sales/ranking")
def sales_ranking(): pass

@router.get("/sales/region")
def sales_region(): pass

@router.get("/sales/energy")
def sales_energy(): pass