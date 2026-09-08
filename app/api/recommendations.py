"""推荐 API 占位符"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/recommend/options")
def recommend_options(): pass

@router.post("/recommend")
def recommend(): pass