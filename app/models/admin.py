"""用户、库存、订单、算法、日志、数据文件"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    """系统用户（演示账号：admin/analyst/sales/user，密码固定为对应123）"""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_user_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, comment="登录账号")
    nickname: Mapped[str] = mapped_column(String(64), comment="昵称")
    email: Mapped[str] = mapped_column(String(128), default="", comment="邮箱")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="手机号")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt 哈希")
    role: Mapped[str] = mapped_column(String(16), index=True, comment="admin/analyst/sales/user")
    status: Mapped[str] = mapped_column(String(16), index=True, default="active", comment="active/disabled/pending")
    department: Mapped[str] = mapped_column(String(64), default="", comment="部门")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, comment="最后登录时间")
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="最后登录 IP")
    login_count: Mapped[int] = mapped_column(Integer, default=0, comment="登录次数")
    car_count: Mapped[int] = mapped_column(Integer, default=0, comment="关注的车型数")

    operation_logs = relationship("OperationLog", back_populates="user_rel")


class Inventory(TimestampMixin, Base):
    """车型库存（与订单、月销量联动）"""

    __tablename__ = "inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, comment="车型 ID"
    )
    quantity: Mapped[int] = mapped_column(Integer, comment="当前库存（辆）")
    inbound: Mapped[int] = mapped_column(Integer, default=0, comment="本月入库")
    monthly_sales: Mapped[int] = mapped_column(Integer, default=0, comment="上月销量")
    turnover_days: Mapped[float] = mapped_column(comment="周转天数")
    warehouse: Mapped[str] = mapped_column(String(64), comment="仓库名称")
    status: Mapped[str] = mapped_column(String(16), comment="紧张/偏低/充足")

    car_rel = relationship("Car")


class Order(TimestampMixin, Base):
    """订单"""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("order_no", name="uq_order_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, comment="订单号")
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="RESTRICT"), index=True, comment="车型 ID"
    )
    customer: Mapped[str] = mapped_column(String(128), comment="客户名")
    amount: Mapped[float] = mapped_column(comment="金额（万元）")
    status: Mapped[str] = mapped_column(String(16), index=True, comment="pending/paid/shipped/completed/cancelled")
    region: Mapped[str] = mapped_column(String(32), comment="地区")
    salesperson: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="销售员")

    car_rel = relationship("Car")


class AlgorithmTask(TimestampMixin, Base):
    """算法任务（预测/推荐/舆情等）"""

    __tablename__ = "algorithm_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), comment="任务名称")
    type: Mapped[str] = mapped_column(String(32), index=True, comment="prediction/recommendation/sentiment")
    model: Mapped[str] = mapped_column(String(64), comment="模型标识")
    version: Mapped[str] = mapped_column(String(32), default="1.0", comment="版本号")
    accuracy: Mapped[float] = mapped_column(default=0.0, comment="准确率/评分")
    status: Mapped[str] = mapped_column(String(16), index=True, comment="idle/running/success/failed")
    last_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, comment="最后执行时间")
    calls: Mapped[int] = mapped_column(Integer, default=0, comment="调用次数")
    owner: Mapped[str] = mapped_column(String(64), default="system", comment="负责人")
    config: Mapped[dict] = mapped_column(JSON, default=dict, comment="参数配置")


class OperationLog(TimestampMixin, Base):
    """操作日志（用户关键操作记录）"""

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, comment="用户 ID"
    )
    action: Mapped[str] = mapped_column(String(64), index=True, comment="操作类型")
    module: Mapped[str] = mapped_column(String(32), index=True, comment="模块")
    target: Mapped[str] = mapped_column(String(128), comment="目标对象")
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="客户端 IP")
    result: Mapped[str] = mapped_column(String(16), index=True, comment="success/failure")
    detail: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="详情")

    user_rel = relationship("User", back_populates="operation_logs")


class DataFile(TimestampMixin, Base):
    """数据文件登记（手动导入或采集后入库的文件）"""

    __tablename__ = "data_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), comment="文件名")
    size: Mapped[int] = mapped_column(Integer, comment="文件大小（字节）")
    type: Mapped[str] = mapped_column(String(32), comment="文件类型：csv/json/xlsx")
    status: Mapped[str] = mapped_column(String(16), comment="pending/parsing/loaded/error")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度 %")
    rows: Mapped[int] = mapped_column(Integer, default=0, comment="入库行数")
    message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="错误消息")
    uploaded_at: Mapped[datetime] = mapped_column(comment="上传时间")