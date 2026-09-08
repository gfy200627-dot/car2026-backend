"""认证与用户 API（对齐 src/api/auth.ts / users.ts）"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResult, UserProfile

router = APIRouter()


@router.post("/auth/login", summary="登录", response_model=LoginResult)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResult:
    user = db.query(User).filter_by(username=body.username).first()
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
        user=UserProfile(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            role=user.role,
            status=user.status,
            createdAt=user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


@router.post("/auth/register", summary="注册")
def register(body: dict, db: Session = Depends(get_db)) -> UserProfile:
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少 3 个字符")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 个字符")

    u = User(
        username=username,
        nickname=body.get("nickname", username),
        email=body.get("email", ""),
        password_hash=hash_password(password),
        role="user",
        status="active",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserProfile(
        id=u.id,
        username=u.username,
        nickname=u.nickname,
        email=u.email,
        role=u.role,
        status=u.status,
        createdAt=u.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


@router.post("/auth/logout", summary="退出登录")
def logout() -> dict:
    return {"success": True}


@router.get("/users/me", summary="获取当前用户", response_model=UserProfile)
def get_me(current: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        id=current.id,
        username=current.username,
        nickname=current.nickname,
        email=current.email,
        role=current.role,
        status=current.status,
        createdAt=current.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


@router.put("/users/me", summary="更新当前用户资料")
def update_me(body: dict, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserProfile:
    for k in ("nickname", "email", "phone"):
        if k in body:
            setattr(current, k, body[k])
    db.commit()
    db.refresh(current)
    return UserProfile(
        id=current.id,
        username=current.username,
        nickname=current.nickname,
        email=current.email,
        role=current.role,
        status=current.status,
        createdAt=current.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    )