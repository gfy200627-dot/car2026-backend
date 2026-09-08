"""管理后台 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/admin/overview")
def admin_overview(): pass

@router.get("/admin/sales-trend")
def admin_sales_trend(): pass

@router.get("/admin/order-status")
def admin_order_status(): pass

@router.get("/admin/car-ranking")
def admin_car_ranking(): pass

@router.get("/admin/inventory-trend")
def admin_inventory_trend(): pass

@router.get("/admin/users")
def admin_users(): pass

@router.get("/admin/brands")
def admin_brands(): pass

@router.get("/admin/cars")
def admin_cars(): pass

@router.get("/admin/sales")
def admin_sales(): pass

@router.get("/admin/inventory")
def admin_inventory(): pass

@router.get("/admin/orders")
def admin_orders(): pass

@router.get("/admin/algorithms")
def admin_algorithms(): pass

@router.get("/admin/logs")
def admin_logs(): pass

@router.get("/admin/data-files")
def admin_data_files(): pass

@router.post("/admin/data/upload")
def admin_data_upload(): pass

@router.delete("/admin/data-files/{id}")
def admin_data_files_delete(): pass