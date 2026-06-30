"""Authentication, JWT, and role-based access control (RBAC).

A demo user store seeds two tenants/roles so the permission model is visible
end-to-end. In production this would be backed by an identity provider; the
token contract (tenant_id + role claims) stays the same.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header
from passlib.context import CryptContext
from pydantic import BaseModel

from agent_common.errors import AuthError
from agent_common.errors import PermissionError_
from app.settings import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel):
    username: str
    tenant_id: str
    role: str  # "admin" | "member"


class _StoredUser(User):
    password_hash: str


# Seed users (demo). Passwords: admin->admin123, alice->alice123
_USERS: dict[str, _StoredUser] = {
    "admin": _StoredUser(
        username="admin",
        tenant_id="acme",
        role="admin",
        password_hash=_pwd.hash("admin123"),
    ),
    "alice": _StoredUser(
        username="alice",
        tenant_id="acme",
        role="member",
        password_hash=_pwd.hash("alice123"),
    ),
}


def authenticate(username: str, password: str) -> User:
    user = _USERS.get(username)
    if not user or not _pwd.verify(password, user.password_hash):
        raise AuthError("用户名或密码错误")
    return User(username=user.username, tenant_id=user.tenant_id, role=user.role)


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise AuthError("无效的令牌")


async def current_user(authorization: str = Header(default="")) -> User:
    if not authorization.lower().startswith("bearer "):
        raise AuthError("缺少 Bearer 令牌")
    payload = _decode(authorization.split(" ", 1)[1])
    return User(
        username=payload["sub"],
        tenant_id=payload["tenant_id"],
        role=payload["role"],
    )


def require_role(*roles: str):
    """Dependency factory enforcing RBAC on a route."""

    async def _checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise PermissionError_(
                f"需要角色 {roles} 之一，当前为 {user.role}"
            )
        return user

    return _checker
