from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import enabled_modules_for_role
from app.core.security import decode_token
from app.models.entities import User, UserPlatformAccess
from app.models.enums import GenericStatus


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or user.status != GenericStatus.ENABLED.value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User disabled or not found")
    return user


def require_roles(roles: set[str]) -> Callable:
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission")
        return current_user

    return checker


def require_module(module_key: str, roles: set[str] | None = None) -> Callable:
    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if roles is not None and current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission")
        allowed_modules = set(enabled_modules_for_role(db, current_user.role))
        if module_key not in allowed_modules:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No module permission")
        return current_user

    return checker


def get_user_platform_ids(db: Session, user: User) -> list[int]:
    rows = db.execute(select(UserPlatformAccess.platform_id).where(UserPlatformAccess.user_id == user.id)).all()
    ids = [int(r[0]) for r in rows]
    if ids:
        return sorted(set(ids))
    if user.platform_id is not None:
        return [int(user.platform_id)]
    return []
