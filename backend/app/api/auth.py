from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_user_platform_ids, get_user_tenant_access
from app.core.permissions import MODULES, enabled_modules_for_role
from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.time_utils import beijing_now
from app.models.entities import Tenant, User
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
        role=UserRole.SUPER_ADMIN.value,
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

    tenant_access = get_user_tenant_access(db, user)
    tenant_id = None
    tenant_name = None
    tenant_expire_at = None
    if user.role not in {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value}:
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        if tenant_access.status != GenericStatus.ENABLED.value:
            raise HTTPException(status_code=403, detail="Tenant access disabled")
        if tenant_access.expire_at and tenant_access.expire_at < beijing_now():
            raise HTTPException(status_code=403, detail="Tenant access expired")
        tenant = db.get(Tenant, tenant_access.tenant_id)
        if tenant is None or tenant.status != GenericStatus.ENABLED.value:
            raise HTTPException(status_code=403, detail="Tenant disabled or not found")
        tenant_id = tenant.id
        tenant_name = tenant.name
        tenant_expire_at = tenant_access.expire_at.isoformat() if tenant_access.expire_at else None

    token = create_access_token(subject=user.username, role=user.role)
    platform_ids = get_user_platform_ids(db, user)
    return TokenOut(
        access_token=token,
        role=user.role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_expire_at=tenant_expire_at,
        platform_id=(platform_ids[0] if platform_ids else None),
        platform_ids=platform_ids,
    )


@router.get("/me")
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    module_keys = enabled_modules_for_role(db, current_user.role)
    platform_ids = get_user_platform_ids(db, current_user)
    tenant_access = get_user_tenant_access(db, current_user)
    tenant = db.get(Tenant, tenant_access.tenant_id) if tenant_access else None
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "tenant_id": tenant.id if tenant else None,
        "tenant_name": tenant.name if tenant else None,
        "tenant_expire_at": tenant_access.expire_at.isoformat() if tenant_access and tenant_access.expire_at else None,
        "platform_id": platform_ids[0] if platform_ids else None,
        "platform_ids": platform_ids,
        "module_keys": module_keys,
        "modules": MODULES,
    }
