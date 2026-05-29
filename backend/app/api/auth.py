from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.permissions import MODULES, enabled_modules_for_role
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.entities import User
from app.models.enums import GenericStatus, UserRole
from app.schemas.common import LoginRequest, TokenOut


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/seed-admin")
def seed_admin(db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
    if user:
        return {"message": "admin already exists"}

    admin = User(
        username="admin",
        password_hash=get_password_hash("admin123456"),
        role=UserRole.ADMIN.value,
        status=GenericStatus.ENABLED.value,
    )
    db.add(admin)
    db.commit()
    return {"message": "admin created", "username": "admin"}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.status != GenericStatus.ENABLED.value:
        raise HTTPException(status_code=403, detail="User disabled")

    token = create_access_token(subject=user.username, role=user.role)
    return TokenOut(access_token=token, role=user.role, platform_id=user.platform_id)


@router.get("/me")
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    module_keys = enabled_modules_for_role(db, current_user.role)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "platform_id": current_user.platform_id,
        "module_keys": module_keys,
        "modules": MODULES,
    }
