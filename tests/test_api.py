"""pytest 契约测试：验证 API 与前端 Mock 数据兼容性"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.database.session import get_db, Base
from app.models import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 创建测试客户端
client = TestClient(app)

# 测试用户
test_user = {
    "username": "testuser",
    "password": "test123",
    "role": "analyst"
}

# 创建测试数据库
test_engine = create_engine("sqlite:///test.db")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


@pytest.fixture
def db_session():
    """创建测试数据库会话"""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_token(db_session):
    """获取认证 token"""
    # 创建测试用户
    user = User(
        username=test_user["username"],
        password_hash="testhash",  # 实际应用中应该用 bcrypt 哈希
        role=test_user["role"],
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    
    # 生成 token
    token = create_access_token(data={"sub": test_user["username"]})
    return token


def test_auth_login(db_session):
    """测试登录接口"""
    response = client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "refreshToken" in data
    assert "expiresIn" in data
    assert "user" in data


def test_cars_list(auth_token):
    """测试车型列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data
    assert len(data["list"]) > 0


def test_cars_options(auth_token):
    """测试车型选项接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars/options", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "brands" in data
    assert "energies" in data
    assert "categories" in data
    assert "years" in data
    assert "priceBuckets" in data
    assert "regions" in data
    assert "months" in data
    assert "updatedAt" in data


def test_cars_detail(auth_token):
    """测试车型详情接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars/1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "brandId" in data
    assert "brand" in data
    assert "name" in data
    assert "modelCode" in data
    assert "category" in data
    assert "energyType" in data
    assert "price" in data
    assert "priceMin" in data
    assert "priceMax" in data
    assert "rangeKm" in data
    assert "batteryKwh" in data
    assert "powerKw" in data
    assert "torqueNm" in data
    assert "wheelbase" in data
    assert "length" in data
    assert "width" in data
    assert "height" in data
    assert "seats" in data
    assert "launchDate" in data
    assert "launchYear" in data
    assert "sales12m" in data
    assert "lastMonthSales" in data
    assert "rating" in data
    assert "intelligenceScore" in data
    assert "comfortScore" in data
    assert "spaceScore" in data
    assert "performanceScore" in data
    assert "reviewCount" in data
    assert "rank" in data
    assert "tags" in data


def test_cars_sales(auth_token):
    """测试车型销量趋势接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars/1/sales", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    assert "yoy" in data
    assert len(data["points"]) > 0


def test_cars_similar(auth_token):
    """测试同级推荐接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars/1/similar", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_cars_reviews(auth_token):
    """测试车型评价列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/cars/1/reviews", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_sales_trend(auth_token):
    """测试销量趋势接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/sales/trend", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    assert "yoy" in data
    assert len(data["points"]) > 0


def test_sales_ranking(auth_token):
    """测试销量排名接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/sales/ranking", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_sales_region(auth_token):
    """测试区域销量分布接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/sales/region", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_sales_energy(auth_token):
    """测试能源类型销量分布接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/sales/energy", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_trend(auth_token):
    """测试市场趋势接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/trend", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    assert "yoy" in data
    assert len(data["points"]) > 0


def test_market_share(auth_token):
    """测试市场份额接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/share", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_penetration(auth_token):
    """测试市场渗透率接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/penetration", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_price(auth_token):
    """测试价格分布接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/price", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_brand_rank(auth_token):
    """测试品牌排名接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/brand-rank", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_category(auth_token):
    """测试车型类别分布接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/category", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert len(data["list"]) > 0


def test_market_category_trend(auth_token):
    """测试类别趋势接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/market/category-trend?category=轿车", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    assert "yoy" in data
    assert len(data["points"]) > 0


def test_predictions_list(auth_token):
    """测试预测列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/predictions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_recommendations_list(auth_token):
    """测试推荐列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/recommendations", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_sentiment_list(auth_token):
    """测试舆情列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/sentiment", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_users_list(auth_token):
    """测试用户列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_inventory_list(auth_token):
    """测试库存列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/inventory", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_orders_list(auth_token):
    """测试订单列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/orders", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_algorithm_tasks_list(auth_token):
    """测试算法任务列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/algorithm-tasks", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_operation_logs_list(auth_token):
    """测试操作日志列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/operation-logs", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


def test_admin_data_files_list(auth_token):
    """测试数据文件列表接口"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/admin/data-files", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data


if __name__ == "__main__":
    pytest.main(["-v"])