"""车型 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/cars")
def list_cars(): pass

@router.get("/cars/options")
def cars_options(): pass

@router.get("/cars/{id}")
def get_car(): pass

@router.get("/cars/{id}/sales")
def car_sales(): pass

@router.get("/cars/{id}/similar")
def similar_cars(): pass

@router.get("/cars/{id}/reviews")
def car_reviews(): pass

@router.post("/cars")
def create_car(): pass

@router.put("/cars/{id}")
def update_car(): pass

@router.delete("/cars/{id}")
def delete_car(): pass

@router.get("/brands")
def list_brands(): pass