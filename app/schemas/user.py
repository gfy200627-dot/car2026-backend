"""用户相关 Schema（对齐 src/types/api.ts）"""

from pydantic import BaseModel


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class UserProfile(BaseModel):
    id: int
    username: str
    nickname: str
    email: str
    role: str  # admin/analyst/sales/user
    status: str
    createdAt: str

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