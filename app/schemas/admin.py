"""管理后台 Schema（对齐 src/types/business.ts Admin* 系列）"""

from typing import List, Optional

from pydantic import BaseModel


class AdminOverview(BaseModel):
    todaySales: int
    monthSales: int
    inventory: int
    newUsers: int
    newOrders: int
    recommendCount: int
    predictTasks: int
    deltas: dict
    updatedAt: str
    isMock: bool = False


class AdminUserItem(BaseModel):
    id: int
    username: str
    nickname: str
    email: str
    phone: Optional[str] = None
    role: str
    status: str
    department: Optional[str] = None
    createdAt: str
    lastLoginAt: Optional[str] = None
    lastLoginIp: Optional[str] = None
    loginCount: Optional[int] = None
    carCount: Optional[int] = None


class BrandItem(BaseModel):
    id: int
    name: str
    nameEn: str
    country: str
    group: str
    color: str
    foundedYear: int
    energyFocus: List[str] = []
    modelCount: Optional[int] = None
    annualSales: Optional[int] = None
    status: Optional[str] = None


class InventoryItem(BaseModel):
    id: int
    carId: int
    carName: str
    brand: str
    quantity: int
    inbound: int
    monthlySales: int
    turnoverDays: float
    warehouse: str
    status: str  # 充足/偏低/紧张


class OrderItem(BaseModel):
    id: int
    orderNo: str
    carId: int
    carName: str
    brand: str
    customer: str
    amount: float
    status: str  # pending/paid/delivered/cancelled
    region: str
    createdAt: str
    salesperson: str


class AlgorithmTaskItem(BaseModel):
    id: int
    name: str
    type: str  # 推荐/预测/舆情
    model: str
    version: str
    accuracy: float
    status: str  # running/idle/failed/training
    lastRunAt: str
    calls: int
    owner: str


class OperationLogItem(BaseModel):
    id: int
    operator: str
    action: str
    module: str
    target: Optional[str] = None
    ip: str
    result: str  # success/failed
    createdAt: str
    detail: Optional[str] = None


class DataFileItem(BaseModel):
    id: int
    name: str
    size: int
    type: str  # 车型数据/销量数据/评价数据
    status: str  # success/uploading/failed/pending
    progress: int
    uploadedAt: str
    rows: Optional[int] = None
    message: Optional[str] = None
