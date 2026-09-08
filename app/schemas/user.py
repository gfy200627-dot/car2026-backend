"""用户相关 Schema（对齐 src/types/business.ts UserProfile / AdminUserItem）"""

from pydantic import BaseModel


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class UserProfile(BaseModel):
    id: int
    username: str
    nickname: str
    email: str
    phone: str = ""
    role: str  # admin/analyst/sales/user
    status: str  # active/disabled/pending
    avatar: str | None = None
    department: str = ""
    createdAt: str
    lastLoginAt: str | None = None
    lastLoginIp: str | None = None
    loginCount: int = 0
    # AdminUserItem 扩展字段
    carCount: int = 0

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False
    captcha: str | None = None


class LoginResult(BaseModel):
    token: str
    refreshToken: str
    expiresIn: int
    user: UserProfile


# API 层依赖注入注解使用 UserSchema；与 SQLAlchemy 的 User 模型区分
UserSchema = UserProfile
