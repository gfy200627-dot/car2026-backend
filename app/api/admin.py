"""企业管理后台 API（对齐 src/api/admin.ts + src/mock/handlers.ts 行为）"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as F
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, require_roles
from app.database.session import get_db
from app.models import (
    AlgorithmTask,
    Brand,
    Car,
    CarSales,
    DataFile,
    Inventory,
    OperationLog,
    Order,
    User,
)
from app.schemas.user import UserSchema
from app.utils.serialize import UPDATED_AT, available_months, car_to_dict, paginate, sort_by
from app.utils.series import next_month, parse_month

router = APIRouter()


def _mk(m) -> str:
    if isinstance(m, date):
        return m.strftime("%Y-%m")
    if isinstance(m, datetime):
        return m.strftime("%Y-%m")
    return str(m)[:7]


def _dt_str(d: Optional[datetime]) -> Optional[str]:
    return d.strftime("%Y-%m-%d %H:%M:%S") if isinstance(d, datetime) else None


# ============================ 概览 ============================

@router.get("/admin/overview", summary="后台概览")
def admin_overview(db: Session = Depends(get_db), current: UserSchema = Depends(require_roles("admin"))) -> dict:
    months = available_months(db)
    if not months:
        return {
            "todaySales": 0, "monthSales": 0, "inventory": 0, "newUsers": 0, "newOrders": 0,
            "recommendCount": 0, "predictTasks": 0, "deltas": {}, "updatedAt": UPDATED_AT, "isMock": False,
        }
    last_month = months[-1]
    prev_month = months[-2] if len(months) >= 2 else None

    month_rows = dict(
        (m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7], int(s or 0))
        for m, s in db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
    )
    month_sales = month_rows.get(last_month, 0)

    inventory_total = db.query(F.sum(Inventory.quantity)).scalar() or 0
    prev_inventory = inventory_total  # 无历史快照，环比按 0 处理

    # 新增用户/订单按数据月份统计（真实 created_at），环比对上一个数据月份
    def _count_in_month(col, month: Optional[str]) -> int:
        if not month:
            return 0
        start, end = parse_month(month), parse_month(next_month(month))
        return int(db.query(F.count(col)).filter(col >= start, col < end).scalar() or 0)

    new_users = _count_in_month(User.created_at, last_month)
    prev_users = _count_in_month(User.created_at, prev_month)
    new_orders = _count_in_month(Order.created_at, last_month)
    prev_orders = _count_in_month(Order.created_at, prev_month)

    calls = dict(
        db.query(AlgorithmTask.type, F.sum(AlgorithmTask.calls)).group_by(AlgorithmTask.type).all()
    )
    recommend_count = int(calls.get("recommendation") or 0)
    predict_tasks = int(calls.get("prediction") or 0)

    def pct(cur: float, prev: float) -> float:
        return round((cur - prev) / prev * 100, 1) if prev else 0

    prev_sales = month_rows.get(prev_month, 0) if prev_month else 0

    return {
        "todaySales": round(month_sales / 30),
        "monthSales": month_sales,
        "inventory": int(inventory_total),
        "newUsers": new_users,
        "newOrders": new_orders,
        "recommendCount": recommend_count,
        "predictTasks": predict_tasks,
        "deltas": {
            "todaySales": pct(month_sales, prev_sales),
            "monthSales": pct(month_sales, prev_sales),
            "inventory": pct(inventory_total, prev_inventory),
            "newUsers": pct(new_users, prev_users),
            "newOrders": pct(new_orders, prev_orders),
            "recommendCount": 0,
            "predictTasks": 0,
        },
        "updatedAt": UPDATED_AT,
        "isMock": False,
    }


@router.get("/admin/sales-trend", summary="后台销售趋势")
def admin_sales_trend(db: Session = Depends(get_db), current: UserSchema = Depends(require_roles("admin"))) -> dict:
    months = available_months(db)[-12:]
    sales_rows = dict(
        (m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7], int(s or 0))
        for m, s in db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
    )
    order_rows = _orders_by_month(db)

    return {
        "months": months,
        "sales": [sales_rows.get(m, 0) for m in months],
        "orders": [order_rows.get(m, 0) for m in months],
    }


def _orders_by_month(db: Session) -> dict[str, int]:
    rows = db.query(Order.created_at).all()
    out: dict[str, int] = {}
    for (created,) in rows:
        if isinstance(created, datetime):
            out.setdefault(created.strftime("%Y-%m"), 0)
            out[created.strftime("%Y-%m")] += 1
    return out


@router.get("/admin/order-status", summary="订单状态分布")
def admin_order_status(db: Session = Depends(get_db), current: UserSchema = Depends(require_roles("admin"))) -> list:
    rows = db.query(Order.status, F.count(Order.id)).group_by(Order.status).all()
    counts = {status: int(c or 0) for status, c in rows}
    return [
        {"name": "待处理", "value": counts.get("pending", 0)},
        {"name": "已付款", "value": counts.get("paid", 0)},
        {"name": "已交付", "value": counts.get("delivered", 0) + counts.get("shipped", 0) + counts.get("completed", 0)},
        {"name": "已取消", "value": counts.get("cancelled", 0)},
    ]


@router.get("/admin/car-ranking", summary="后台车型销量排行")
def admin_car_ranking(
    limit: int = 8,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> list:
    """基于 CarSales 真实月度聚合（最近 12 个月），不使用 Car.sales_12m 缓存字段"""
    months = available_months(db)[-12:]
    if not months:
        return []
    rows = (
        db.query(Car.id, Car.name, Brand.name, F.sum(CarSales.sales))
        .join(CarSales, CarSales.car_id == Car.id)
        .join(Brand, Brand.id == Car.brand_id)
        .filter(CarSales.month >= parse_month(months[0]), CarSales.month <= parse_month(months[-1]))
        .group_by(Car.id, Car.name, Brand.name)
        .order_by(F.sum(CarSales.sales).desc())
        .limit(limit)
        .all()
    )
    return [
        {"name": f"{brand_name} {car_name}", "value": int(total or 0), "brand": brand_name}
        for _car_id, car_name, brand_name, total in rows
    ]


@router.get("/admin/inventory-trend", summary="库存趋势")
def admin_inventory_trend(db: Session = Depends(get_db), current: UserSchema = Depends(require_roles("admin"))) -> dict:
    months = available_months(db)[-12:]
    if not months:
        return {"months": [], "data": []}
    total = int(db.query(F.sum(Inventory.quantity)).scalar() or 0)
    sales = {
        (m.strftime("%Y-%m") if isinstance(m, date) else str(m)[:7]): int(s or 0)
        for m, s in db.query(CarSales.month, F.sum(CarSales.sales)).group_by(CarSales.month).all()
    }
    base = sales.get(months[-1], 0)
    if base:
        # 真实库存仅一个期末快照：以真实月度销量比例回推各月末库存估计值
        data = [round(total * sales.get(m, 0) / base) for m in months]
    else:
        data = [total] * len(months)
    return {"months": months, "data": data}


# ============================ 用户 ============================

def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "email": u.email,
        "phone": u.phone,
        "role": u.role,
        "status": u.status,
        "department": u.department,
        "createdAt": _dt_str(u.created_at) or "",
        "lastLoginAt": _dt_str(u.last_login_at),
        "lastLoginIp": u.last_login_ip,
        "loginCount": u.login_count,
        "carCount": u.car_count,
    }


@router.get("/admin/users", summary="用户列表")
def admin_users(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    q = db.query(User)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(User.username.ilike(kw) | User.nickname.ilike(kw) | User.email.ilike(kw))
    if role and role != "all":
        q = q.filter(User.role == role)
    if status and status != "all":
        q = q.filter(User.status == status)
    total = q.count()
    rows = q.order_by(User.id).offset((max(page, 1) - 1) * pageSize).limit(pageSize).all()
    return {"list": [_user_to_dict(u) for u in rows], "total": total, "page": page, "pageSize": pageSize}


@router.put("/admin/users/{user_id}", summary="更新用户")
def admin_user_update(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    for k in ("nickname", "email", "phone", "role", "status", "department"):
        if k in body and body[k] is not None:
            setattr(u, k, body[k])
    db.commit()
    db.refresh(u)
    return _user_to_dict(u)


@router.patch("/admin/users/{user_id}/status", summary="更新用户状态")
def admin_user_status(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    u.status = str(body.get("status") or "active")
    db.commit()
    db.refresh(u)
    return _user_to_dict(u)


# ============================ 品牌 / 车型 / 销量 ============================

def _brand_to_dict(b: Brand) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "nameEn": b.name_en,
        "country": b.country,
        "group": b.group,
        "color": b.color,
        "foundedYear": b.founded_year,
        "energyFocus": b.energy_focus or [],
        "modelCount": b.model_count,
        "annualSales": b.annual_sales,
        "status": b.status,
    }


@router.get("/admin/brands", summary="品牌管理列表")
def admin_brands(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    group: Optional[str] = None,
    sortBy: Optional[str] = None,
    sortOrder: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    items = [_brand_to_dict(b) for b in db.query(Brand).all()]
    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items if kw in f"{i['name']}{i['nameEn']}".lower()]
    if group and group != "all":
        items = [i for i in items if i["group"] == group]
    items = sort_by(items, sortBy, sortOrder, default="annualSales")
    return paginate(items, page, pageSize)


@router.get("/admin/cars", summary="车型管理列表")
def admin_cars(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    brandId: Optional[int] = None,
    energyType: Optional[str] = None,
    category: Optional[str] = None,
    sortBy: Optional[str] = None,
    sortOrder: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    q = db.query(Car).options(joinedload(Car.brand_rel))
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(Car.name.ilike(kw) | Car.name_norm.ilike(kw) | Car.model_code.ilike(kw))
    if brandId:
        q = q.filter(Car.brand_id == brandId)
    if energyType:
        if energyType == "PHEV":
            q = q.filter(Car.energy_type.in_(["PHEV", "EREV"]))
        else:
            q = q.filter(Car.energy_type == energyType)
    if category:
        q = q.filter(Car.category == category)
    total = q.count()
    rows = q.all()
    items = [car_to_dict(c) for c in rows]
    items = sort_by(items, sortBy, sortOrder, default="sales")
    page = max(page, 1)
    start = (page - 1) * pageSize
    return {"list": items[start:start + pageSize], "total": total, "page": page, "pageSize": pageSize}


@router.get("/admin/sales", summary="车型销量管理（按车月度序列）")
def admin_sales(
    page: int = 1,
    pageSize: int = 10,
    span: int = 12,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    months = available_months(db)[-min(max(span, 1), 500):]

    series_rows = db.query(CarSales.car_id, CarSales.month, CarSales.sales).all()
    per_car: dict[int, dict[str, int]] = {}
    for car_id, m, s in series_rows:
        per_car.setdefault(car_id, {})[_mk(m)] = int(s or 0)

    # TOP60 按当前窗口内 CarSales 聚合销量排序，不依赖 Car.sales_12m 缓存字段
    totals = {cid: sum(vals.get(m, 0) for m in months) for cid, vals in per_car.items()}
    top_ids = [cid for cid, _ in sorted(totals.items(), key=lambda t: t[1], reverse=True)[:60]]
    car_rows = (
        db.query(Car, Brand.name)
        .join(Brand, Car.brand_id == Brand.id)
        .filter(Car.id.in_(top_ids))
        .all()
    )
    cars = {car.id: (car, brand_name) for car, brand_name in car_rows}

    items = []
    for cid in top_ids:
        car, brand_name = cars[cid]
        values = [per_car.get(cid, {}).get(m, 0) for m in months]
        items.append({
            "carId": cid,
            "carName": f"{brand_name} {car.name}",
            "brand": brand_name,
            "months": months,
            "values": values,
            "total": sum(values),
        })
    return paginate(items, page, pageSize)


# ============================ 库存 / 订单 ============================

def _inventory_to_dict(inv: Inventory, car_name: str, brand: str) -> dict:
    return {
        "id": inv.id,
        "carId": inv.car_id,
        "carName": car_name,
        "brand": brand,
        "quantity": inv.quantity,
        "inbound": inv.inbound,
        "monthlySales": inv.monthly_sales,
        "turnoverDays": round(float(inv.turnover_days), 1),
        "warehouse": inv.warehouse,
        "status": inv.status,
    }


@router.get("/admin/inventory", summary="库存列表")
def admin_inventory(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    sortBy: Optional[str] = None,
    sortOrder: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin", "sales")),
) -> dict:
    rows = db.query(Inventory, Car, Brand.name).join(Car, Car.id == Inventory.car_id).join(
        Brand, Brand.id == Car.brand_id
    ).all()
    items = [_inventory_to_dict(inv, f"{brand} {car.name}", brand) for inv, car, brand in rows]
    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items if kw in f"{i['carName']}{i['brand']}".lower()]
    if status and status != "all":
        items = [i for i in items if i["status"] == status]
    items = sort_by(items, sortBy, sortOrder, default="quantity")
    return paginate(items, page, pageSize)


_ORDER_STATUS_MAP = {"shipped": "delivered", "completed": "delivered"}


def _order_to_dict(o: Order, car_name: str, brand: str) -> dict:
    return {
        "id": o.id,
        "orderNo": o.order_no,
        "carId": o.car_id,
        "carName": car_name,
        "brand": brand,
        "customer": o.customer,
        "amount": round(float(o.amount), 2),
        "status": _ORDER_STATUS_MAP.get(o.status, o.status),
        "region": o.region,
        "createdAt": _dt_str(o.created_at) or "",
        "salesperson": o.salesperson or "",
    }


@router.get("/admin/orders", summary="订单列表")
def admin_orders(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin", "sales")),
) -> dict:
    q = db.query(Order, Car, Brand.name).join(Car, Car.id == Order.car_id).join(Brand, Brand.id == Car.brand_id)
    rows = q.all()
    items = [_order_to_dict(o, f"{brand} {car.name}", brand) for o, car, brand in rows]
    items.sort(key=lambda i: i["createdAt"], reverse=True)
    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items if kw in f"{i['orderNo']}{i['carName']}{i['customer']}".lower()]
    if status and status != "all":
        items = [i for i in items if i["status"] == status]
    return paginate(items, page, pageSize)


# ============================ 算法 / 日志 / 数据文件 ============================

_ALGO_TYPE_LABEL = {"prediction": "预测", "recommendation": "推荐", "sentiment": "舆情"}
_ALGO_STATUS_MAP = {"success": "running"}


def _algo_to_dict(t: AlgorithmTask) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "type": _ALGO_TYPE_LABEL.get(t.type, t.type),
        "model": t.model,
        "version": t.version,
        "accuracy": round(float(t.accuracy), 3),
        "status": _ALGO_STATUS_MAP.get(t.status, t.status),
        "lastRunAt": _dt_str(t.last_run_at) or "",
        "calls": t.calls,
        "owner": t.owner,
    }


@router.get("/admin/algorithms", summary="算法任务列表")
def admin_algorithms(
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> list:
    return [_algo_to_dict(t) for t in db.query(AlgorithmTask).order_by(AlgorithmTask.id).all()]


@router.patch("/admin/algorithms/{task_id}/status", summary="更新算法任务状态")
def admin_algorithm_status(
    task_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    t = db.get(AlgorithmTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="算法任务不存在")
    t.status = str(body.get("status") or "idle")
    t.last_run_at = datetime.now()
    db.commit()
    db.refresh(t)
    return _algo_to_dict(t)


def _log_to_dict(log: OperationLog) -> dict:
    operator = log.user_rel.nickname if log.user_rel is not None else "系统"
    return {
        "id": log.id,
        "operator": operator,
        "action": log.action,
        "module": log.module,
        "target": log.target,
        "ip": log.ip or "",
        "result": "failed" if log.result == "failure" else log.result,
        "createdAt": _dt_str(log.created_at) or "",
        "detail": log.detail,
    }


@router.get("/admin/logs", summary="操作日志列表")
def admin_logs(
    page: int = 1,
    pageSize: int = 10,
    keyword: Optional[str] = None,
    module: Optional[str] = None,
    result: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    q = db.query(OperationLog).options(joinedload(OperationLog.user_rel))
    rows = q.order_by(OperationLog.id.desc()).all()
    items = [_log_to_dict(l) for l in rows]
    if keyword:
        kw = keyword.strip().lower()
        items = [i for i in items if kw in f"{i['operator']}{i['action']}{i['module']}".lower()]
    if module and module != "all":
        items = [i for i in items if i["module"] == module]
    if result and result != "all":
        items = [i for i in items if i["result"] == result]
    return paginate(items, page, pageSize)


_DATA_STATUS_MAP = {"loaded": "success", "parsing": "uploading", "error": "failed"}


def _file_to_dict(f: DataFile) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "size": f.size,
        "type": f.type,
        "status": _DATA_STATUS_MAP.get(f.status, f.status),
        "progress": f.progress,
        "uploadedAt": _dt_str(f.uploaded_at) or "",
        "rows": f.rows,
        "message": f.message,
    }


@router.get("/admin/data-files", summary="数据文件列表")
def admin_data_files(
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> list:
    q = db.query(DataFile)
    if type and type != "all":
        q = q.filter(DataFile.type == type)
    return [_file_to_dict(f) for f in q.order_by(DataFile.id).all()]


@router.post("/admin/data/upload", summary="登记上传数据文件")
def admin_data_upload(
    body: dict,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    f = DataFile(
        name=str(body.get("name") or "unknown.csv"),
        size=int(body.get("size") or 102400),
        type=str(body.get("type") or "车型数据"),
        status="success",
        progress=100,
        rows=128,
        uploaded_at=datetime.now(),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return _file_to_dict(f)


@router.delete("/admin/data-files/{file_id}", summary="删除数据文件")
def admin_data_files_delete(
    file_id: int,
    db: Session = Depends(get_db),
    current: UserSchema = Depends(require_roles("admin")),
) -> dict:
    f = db.get(DataFile, file_id)
    if f:
        db.delete(f)
        db.commit()
    return {"id": file_id}
