"""管理后台相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel
from typing import List, Optional


class UserList(BaseModel):
    id: int
    username: str
    nickname: str
    email: str
    role: str
    status: str
    createdAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            username=obj.username,
            nickname=obj.nickname,
            email=obj.email,
            role=obj.role,
            status=obj.status,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class UserDetail(UserList):
    phone: str
    department: str
    lastLoginAt: str
    lastLoginIp: str
    loginCount: int
    carCount: int


class UserCreate(BaseModel):
    username: str
    nickname: str
    email: str
    phone: str
    password_hash: str
    role: str
    status: str
    department: str


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    department: Optional[str] = None


class InventoryList(BaseModel):
    id: int
    carId: int
    quantity: int
    inbound: int
    monthlySales: int
    turnoverDays: float
    warehouse: str
    status: str
    createdAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            carId=obj.car_id,
            quantity=obj.quantity,
            inbound=obj.inbound,
            monthlySales=obj.monthly_sales,
            turnoverDays=obj.turnover_days,
            warehouse=obj.warehouse,
            status=obj.status,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class InventoryCreate(BaseModel):
    carId: int
    quantity: int
    inbound: int
    warehouse: str


class OrderList(BaseModel):
    id: int
    orderNo: str
    carId: int
    customer: str
    amount: float
    status: str
    region: str
    salesperson: str
    createdAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            orderNo=obj.order_no,
            carId=obj.car_id,
            customer=obj.customer,
            amount=obj.amount,
            status=obj.status,
            region=obj.region,
            salesperson=obj.salesperson,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class OrderCreate(BaseModel):
    carId: int
    customer: str
    amount: float
    region: str
    salesperson: Optional[str] = None


class AlgorithmTaskList(BaseModel):
    id: int
    name: str
    type: str
    model: str
    version: str
    accuracy: float
    status: str
    lastRunAt: str
    calls: int
    owner: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            name=obj.name,
            type=obj.type,
            model=obj.model,
            version=obj.version,
            accuracy=obj.accuracy,
            status=obj.status,
            lastRunAt=obj.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if obj.last_run_at else None,
            calls=obj.calls,
            owner=obj.owner,
        )


class AlgorithmTaskCreate(BaseModel):
    name: str
    type: str
    model: str
    version: str = "1.0"
    accuracy: float = 0.0
    status: str = "idle"
    owner: str = "system"


class OperationLogList(BaseModel):
    id: int
    userId: int
    action: str
    module: str
    target: str
    ip: str
    result: str
    createdAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            userId=obj.user_id,
            action=obj.action,
            module=obj.module,
            target=obj.target,
            ip=obj.ip,
            result=obj.result,
            createdAt=obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class DataFileList(BaseModel):
    id: int
    name: str
    size: int
    type: str
    status: str
    progress: int
    rows: int
    uploadedAt: str

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            name=obj.name,
            size=obj.size,
            type=obj.type,
            status=obj.status,
            progress=obj.progress,
            rows=obj.rows,
            uploadedAt=obj.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


class DataFileCreate(BaseModel):
    name: str
    type: str
    file: bytes  # 实际使用时需要处理文件上传