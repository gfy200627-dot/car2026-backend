"""认证与用户 API（对齐 src/api/auth.ts / users.ts + UserProfile 契约）"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database.session import get_db
from app.models import User as UserModel
from app.schemas.user import LoginRequest, LoginResult, UserProfile

router = APIRouter()


def _profile(u: UserModel) -> UserProfile:
    """ORM 用户 → 前端 UserProfile 契约"""
    return UserProfile(
        id=u.id,
        username=u.username,
        nickname=u.nickname,
        email=u.email or "",
        phone=u.phone or "",
        role=u.role,
        status=u.status,
        department=u.department or "",
        createdAt=u.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        lastLoginAt=u.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if u.last_login_at else None,
        lastLoginIp=u.last_login_ip,
        loginCount=u.login_count or 0,
        carCount=u.car_count or 0,
    )


@router.post("/auth/login", summary="登录", response_model=LoginResult)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResult:
    user = db.query(UserModel).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    # 更新登录记录
    user.last_login_at = datetime.now()
    user.login_count = (user.login_count or 0) + 1
    db.commit()

    token = create_access_token(user.id, user.username, user.role)
    return LoginResult(
        token=token,
        refreshToken=token,  # 简化版暂用同一 token
        expiresIn=60 * 60 * 12,  # 12h
        user=_profile(user),
    )


@router.post("/auth/register", summary="注册")
def register(body: dict, db: Session = Depends(get_db)) -> UserProfile:
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少 3 个字符")
    if db.query(UserModel).filter_by(username=username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 个字符")

    u = UserModel(
        username=username,
        nickname=body.get("nickname") or username,
        email=body.get("email") or "",
        password_hash=hash_password(password),
        role="user",
        status="active",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return _profile(u)


@router.post("/auth/logout", summary="退出登录")
def logout() -> dict:
    return {"success": True}


@router.get("/users/me", summary="获取当前用户", response_model=UserProfile)
def get_me(current: UserModel = Depends(get_current_user)) -> UserProfile:
    return _profile(current)


@router.put("/users/me", summary="更新当前用户资料")
def update_me(
    body: dict,
    current: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfile:
    for k in ("nickname", "email", "phone", "department"):
        if k in body and body[k] is not None:
            setattr(current, k, body[k])
    db.commit()
    db.refresh(current)
    return _profile(current)
