from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_tenant_platform_ids, get_user_tenant_access, require_module, require_roles
from app.core.permissions import MODULES, DEFAULT_ROLE_MODULES, enabled_modules_for_role, replace_role_modules
from app.core.security import get_password_hash
from app.models.entities import Account, AuditLog, Category, DailySummary, EntryType, EntryTypeSetting, PaymentMethod, Platform, Shift, Tenant, TenantPlatformAccess, Transaction, User, UserPlatformAccess, UserTenantAccess
from app.models.enums import UserRole
from app.schemas.common import AccountCreate, CategoryCreate, EntryTypeCreate, MasterDataCreate, PaymentMethodCreate, ShiftCreate, TenantAccessUpdate, TenantAdminCreate, TenantCreate, TenantUpdate


router = APIRouter(prefix="/master", tags=["master"])

SUPER_ONLY_MODULE_KEYS = {
    "master.tenants",
    "super.users",
    "reports.query",
    "reports.balances",
    "reports.monthly",
    "reports.charts",
    "logs",
    "operation.logs",
    "system.tools",
}


def _normalize_platform_ids(platform_ids: list[int] | None, platform_id: int | None) -> list[int]:
    ids = [int(x) for x in (platform_ids or []) if x is not None]
    if not ids and platform_id is not None:
        ids = [int(platform_id)]
    return sorted(set(ids))


def _set_user_platforms(db: Session, user_id: int, platform_ids: list[int]) -> None:
    db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id == user_id))
    for pid in platform_ids:
        db.add(UserPlatformAccess(user_id=user_id, platform_id=pid))


def _platform_ids_map(db: Session) -> dict[int, list[int]]:
    rows = db.execute(select(UserPlatformAccess.user_id, UserPlatformAccess.platform_id)).all()
    result: dict[int, list[int]] = {}
    for uid, pid in rows:
        result.setdefault(int(uid), []).append(int(pid))
    for uid in result:
        result[uid] = sorted(set(result[uid]))
    return result


def _require_current_tenant_id(db: Session, current_user: User) -> int:
    access = get_user_tenant_access(db, current_user)
    if access is None:
        raise HTTPException(status_code=403, detail="current user not bound to tenant")
    return access.tenant_id


def _apply_common_update(obj, payload: MasterDataCreate):
    obj.name = payload.name
    obj.sort_order = payload.sort_order
    obj.status = payload.status
    if hasattr(obj, "remark"):
        obj.remark = payload.remark
    return obj


@router.post("/tenants")
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="tenant name is required")
    existing = db.execute(select(Tenant).where(Tenant.name == name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="tenant name exists")
    obj = Tenant(name=name, status=payload.status)
    db.add(obj)
    db.flush()

    admin_username = (payload.admin_username or "").strip()
    admin_password = payload.admin_password or ""
    if not admin_username:
        raise HTTPException(status_code=400, detail="admin_username is required")
    if len(admin_password) < 6:
        raise HTTPException(status_code=400, detail="admin_password must be at least 6 chars")
    created_admin_id = None
    exists = db.execute(select(User).where(User.username == admin_username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="admin username exists")
    admin_user = User(
        username=admin_username,
        password_hash=get_password_hash(admin_password),
        role=UserRole.ADMIN.value,
        status="enabled",
    )
    db.add(admin_user)
    db.flush()
    db.add(UserTenantAccess(user_id=admin_user.id, tenant_id=obj.id, status="enabled", expire_at=payload.admin_expire_at))
    created_admin_id = admin_user.id

    db.commit()
    db.refresh(obj)
    return {
        "id": obj.id,
        "name": obj.name,
        "status": obj.status,
        "created_at": obj.created_at,
        "admin_user_id": created_admin_id,
        "admin_username": admin_username or None,
    }


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    tenants = db.execute(select(Tenant).order_by(Tenant.id.asc())).scalars().all()
    admin_rows = db.execute(
        select(UserTenantAccess.tenant_id, User.username, UserTenantAccess.expire_at)
        .join(User, User.id == UserTenantAccess.user_id)
        .where(User.role == UserRole.ADMIN.value)
        .order_by(UserTenantAccess.id.asc())
    ).all()
    admin_map: dict[int, tuple[str, str | None]] = {}
    for tid, username, expire_at in admin_rows:
        if int(tid) not in admin_map:
            admin_map[int(tid)] = (username, expire_at.isoformat() if expire_at else None)
    return [
        {
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "created_at": t.created_at,
            "admin_username": admin_map.get(t.id, (None, None))[0],
            "tenant_expire_at": admin_map.get(t.id, (None, None))[1],
        }
        for t in tenants
    ]


@router.put("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    row = db.get(Tenant, tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    row.name = (payload.name or "").strip() or row.name
    row.status = payload.status

    admin_accesses = db.execute(
        select(UserTenantAccess).join(User, User.id == UserTenantAccess.user_id).where(
            UserTenantAccess.tenant_id == tenant_id,
            User.role == UserRole.ADMIN.value,
        ).order_by(UserTenantAccess.id.asc())
    ).scalars().all()
    primary_admin_access = admin_accesses[0] if admin_accesses else None
    primary_admin = db.get(User, primary_admin_access.user_id) if primary_admin_access else None

    admin_username = (payload.admin_username or "").strip()
    admin_password = payload.admin_password or ""
    if admin_username:
        if primary_admin is None:
            exists = db.execute(select(User).where(User.username == admin_username)).scalar_one_or_none()
            if exists is not None:
                raise HTTPException(status_code=400, detail="admin username exists")
            if len(admin_password) < 6:
                raise HTTPException(status_code=400, detail="admin_password must be at least 6 chars")
            primary_admin = User(
                username=admin_username,
                password_hash=get_password_hash(admin_password),
                role=UserRole.ADMIN.value,
                status="enabled",
            )
            db.add(primary_admin)
            db.flush()
            db.add(UserTenantAccess(user_id=primary_admin.id, tenant_id=tenant_id, status="enabled", expire_at=payload.admin_expire_at))
        elif primary_admin.username != admin_username:
            exists = db.execute(select(User).where(User.username == admin_username, User.id != primary_admin.id)).scalar_one_or_none()
            if exists is not None:
                raise HTTPException(status_code=400, detail="admin username exists")
            primary_admin.username = admin_username

    if primary_admin is not None and admin_password:
        if len(admin_password) < 6:
            raise HTTPException(status_code=400, detail="admin_password must be at least 6 chars")
        primary_admin.password_hash = get_password_hash(admin_password)

    if primary_admin_access is not None:
        primary_admin_access.expire_at = payload.admin_expire_at

    if len(admin_accesses) > 1:
        for extra in admin_accesses[1:]:
            db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id == extra.user_id))
            db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.user_id == extra.user_id))
            extra_user = db.get(User, extra.user_id)
            if extra_user is not None:
                db.delete(extra_user)

    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "created_at": row.created_at,
        "admin_username": primary_admin.username if primary_admin is not None else None,
        "tenant_expire_at": primary_admin_access.expire_at.isoformat() if primary_admin_access and primary_admin_access.expire_at else None,
    }


@router.put("/users/{user_id}/tenant-access")
def update_user_tenant_access(
    user_id: int,
    payload: TenantAccessUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    row = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="tenant access not found")
    row.status = payload.status
    row.expire_at = datetime.fromisoformat(payload.expire_at) if payload.expire_at else None
    db.commit()
    return {"ok": True}


@router.post("/tenants/migrate-default")
def migrate_default_tenant(
    target_tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    default_tenant = db.execute(select(Tenant).where(Tenant.name == "默认租户")).scalar_one_or_none()
    if default_tenant is None:
        raise HTTPException(status_code=404, detail="default tenant not found")
    if default_tenant.id == target_tenant_id:
        raise HTTPException(status_code=400, detail="target tenant cannot be default tenant")
    target_tenant = db.get(Tenant, target_tenant_id)
    if target_tenant is None:
        raise HTTPException(status_code=404, detail="target tenant not found")

    user_rows = db.execute(select(UserTenantAccess).where(UserTenantAccess.tenant_id == default_tenant.id)).scalars().all()
    moved_users = 0
    for row in user_rows:
        exists = db.execute(
            select(UserTenantAccess)
            .where(UserTenantAccess.user_id == row.user_id, UserTenantAccess.tenant_id == target_tenant_id)
        ).scalar_one_or_none()
        if exists is None:
            row.tenant_id = target_tenant_id
            moved_users += 1
        else:
            db.delete(row)

    platform_rows = db.execute(select(TenantPlatformAccess).where(TenantPlatformAccess.tenant_id == default_tenant.id)).scalars().all()
    moved_platforms = 0
    for row in platform_rows:
        exists = db.execute(
            select(TenantPlatformAccess)
            .where(TenantPlatformAccess.platform_id == row.platform_id, TenantPlatformAccess.tenant_id == target_tenant_id)
        ).scalar_one_or_none()
        if exists is None:
            row.tenant_id = target_tenant_id
            moved_platforms += 1
        else:
            db.delete(row)

    db.delete(default_tenant)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="tenants",
            action="migrate_default_tenant",
            before_data=f"default_tenant_id={default_tenant.id}",
            after_data=f"target_tenant_id={target_tenant_id},moved_users={moved_users},moved_platforms={moved_platforms}",
        )
    )
    db.commit()
    return {"ok": True, "moved_users": moved_users, "moved_platforms": moved_platforms}


@router.get("/tenants/{tenant_id}/admins")
def list_tenant_admins(
    tenant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    rows = db.execute(
        select(User)
        .join(UserTenantAccess, UserTenantAccess.user_id == User.id)
        .where(UserTenantAccess.tenant_id == tenant_id, User.role == UserRole.ADMIN.value)
        .order_by(User.id.asc())
    ).scalars().all()
    return rows


@router.post("/tenants/{tenant_id}/admins")
def create_tenant_admin(
    tenant_id: int,
    payload: TenantAdminCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="username exists")

    user = User(username=username, password_hash=get_password_hash(payload.password), role=UserRole.ADMIN.value, status="enabled")
    db.add(user)
    db.flush()
    db.add(UserTenantAccess(user_id=user.id, tenant_id=tenant_id, status=payload.status or "enabled", expire_at=payload.expire_at))
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="tenants",
            action="create_tenant_admin",
            before_data=None,
            after_data=f"tenant_id={tenant_id},user_id={user.id},username={username}",
        )
    )
    db.commit()
    return {"ok": True, "user_id": user.id}


@router.get("/tenants/{tenant_id}/stats")
def tenant_stats(
    tenant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    platform_ids = [r[0] for r in db.execute(select(TenantPlatformAccess.platform_id).where(TenantPlatformAccess.tenant_id == tenant_id)).all()]
    user_count = db.execute(select(func.count(UserTenantAccess.id)).where(UserTenantAccess.tenant_id == tenant_id)).scalar_one()
    platform_count = len(platform_ids)
    tx_count = 0
    net_amount = 0.0
    last_bill_date = None
    if platform_ids:
        tx_count = db.execute(select(func.count(Transaction.id)).where(Transaction.platform_id.in_(platform_ids), Transaction.deleted_at.is_(None))).scalar_one()
        last_bill_date = db.execute(select(func.max(Transaction.bill_date)).where(Transaction.platform_id.in_(platform_ids), Transaction.deleted_at.is_(None))).scalar_one()
        income = db.execute(select(func.sum(Transaction.amount)).where(Transaction.platform_id.in_(platform_ids), Transaction.type == "income", Transaction.deleted_at.is_(None))).scalar_one() or 0
        expense = db.execute(select(func.sum(Transaction.amount)).where(Transaction.platform_id.in_(platform_ids), Transaction.type == "expense", Transaction.deleted_at.is_(None))).scalar_one() or 0
        net_amount = float(income) - float(expense)
    summary_days = 0
    if platform_ids:
        summary_days = db.execute(select(func.count(DailySummary.id)).where(DailySummary.platform_id.in_(platform_ids))).scalar_one()
    return {
        "tenant_id": tenant_id,
        "user_count": int(user_count or 0),
        "platform_count": int(platform_count or 0),
        "transaction_count": int(tx_count or 0),
        "summary_days": int(summary_days or 0),
        "net_amount": net_amount,
        "last_bill_date": last_bill_date.isoformat() if last_bill_date else None,
    }


@router.put("/tenants/{tenant_id}/admins/{user_id}/password")
def reset_tenant_admin_password(
    tenant_id: int,
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    if len(new_password or "") < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 chars")
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=404, detail="tenant admin not found")
    access = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user_id, UserTenantAccess.tenant_id == tenant_id)).scalar_one_or_none()
    if access is None:
        raise HTTPException(status_code=404, detail="tenant admin not in tenant")
    user.password_hash = get_password_hash(new_password)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="tenants",
            action="reset_tenant_admin_password",
            before_data=None,
            after_data=f"tenant_id={tenant_id},user_id={user_id}",
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/platforms")
def create_platform(
    payload: MasterDataCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.platforms")),
    tenant_id: int | None = None,
):
    obj = Platform(**payload.model_dump())
    db.add(obj)
    db.flush()
    if current_user.role == UserRole.SUPER_ADMIN.value:
        if tenant_id is not None:
            db.add(TenantPlatformAccess(tenant_id=tenant_id, platform_id=obj.id))
    else:
        current_tenant_id = _require_current_tenant_id(db, current_user)
        db.add(TenantPlatformAccess(tenant_id=current_tenant_id, platform_id=obj.id))
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/platforms")
def list_platforms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.platforms")),
):
    stmt = select(Platform)
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        platform_ids = get_tenant_platform_ids(db, tenant_id)
        if not platform_ids:
            return []
        stmt = stmt.where(Platform.id.in_(platform_ids))
    return db.execute(stmt.order_by(Platform.sort_order.asc(), Platform.id.asc())).scalars().all()


@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int,
    payload: MasterDataCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.platforms")),
):
    obj = db.get(Platform, platform_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="platform not found")
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        platform_ids = set(get_tenant_platform_ids(db, tenant_id))
        if platform_id not in platform_ids:
            raise HTTPException(status_code=403, detail="no permission for this platform")
    _apply_common_update(obj, payload)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/platforms/{platform_id}")
def delete_platform(
    platform_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.platforms")),
):
    obj = db.get(Platform, platform_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="platform not found")
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        platform_ids = set(get_tenant_platform_ids(db, tenant_id))
        if platform_id not in platform_ids:
            raise HTTPException(status_code=403, detail="no permission for this platform")
    db.execute(TenantPlatformAccess.__table__.delete().where(TenantPlatformAccess.platform_id == platform_id))
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/shifts")
def create_shift(
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.shifts")),
):
    obj = Shift(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/shifts")
def list_shifts(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.shifts")),
):
    return db.execute(select(Shift).order_by(Shift.sort_order.asc(), Shift.id.asc())).scalars().all()


@router.put("/shifts/{shift_id}")
def update_shift(
    shift_id: int,
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.shifts")),
):
    obj = db.get(Shift, shift_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="shift not found")
    obj.name = payload.name
    obj.sort_order = payload.sort_order
    obj.start_time = payload.start_time
    obj.end_time = payload.end_time
    obj.status = payload.status
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/shifts/{shift_id}")
def delete_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.shifts")),
):
    obj = db.get(Shift, shift_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="shift not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/categories")
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.categories")),
):
    obj = Category(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/entry-types")
def create_entry_type(
    payload: EntryTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.entry_types")),
):
    obj = EntryType(name=payload.name, effect=payload.effect, sort_order=payload.sort_order, status=payload.status)
    db.add(obj)
    db.flush()
    db.add(EntryTypeSetting(entry_type_id=obj.id, requires_category=payload.requires_category))
    db.commit()
    db.refresh(obj)
    return {
        "id": obj.id,
        "name": obj.name,
        "effect": obj.effect,
        "sort_order": obj.sort_order,
        "status": obj.status,
        "requires_category": payload.requires_category,
    }


@router.get("/entry-types")
def list_entry_types(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.entry_types")),
):
    rows = db.execute(select(EntryType).order_by(EntryType.sort_order.asc(), EntryType.id.asc())).scalars().all()
    setting_map = {s.entry_type_id: s.requires_category for s in db.execute(select(EntryTypeSetting)).scalars().all()}
    result = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "name": r.name,
                "effect": r.effect,
                "sort_order": r.sort_order,
                "status": r.status,
                "requires_category": setting_map.get(r.id, r.name == "支出"),
            }
        )
    return result


@router.put("/entry-types/{entry_type_id}")
def update_entry_type(
    entry_type_id: int,
    payload: EntryTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.entry_types")),
):
    obj = db.get(EntryType, entry_type_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="entry type not found")
    obj.name = payload.name
    obj.effect = payload.effect
    obj.sort_order = payload.sort_order
    obj.status = payload.status
    setting = db.execute(select(EntryTypeSetting).where(EntryTypeSetting.entry_type_id == obj.id)).scalar_one_or_none()
    if setting is None:
        setting = EntryTypeSetting(entry_type_id=obj.id, requires_category=payload.requires_category)
        db.add(setting)
    else:
        setting.requires_category = payload.requires_category
    db.commit()
    return {
        "id": obj.id,
        "name": obj.name,
        "effect": obj.effect,
        "sort_order": obj.sort_order,
        "status": obj.status,
        "requires_category": payload.requires_category,
    }


@router.delete("/entry-types/{entry_type_id}")
def delete_entry_type(
    entry_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.entry_types")),
):
    obj = db.get(EntryType, entry_type_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="entry type not found")
    setting = db.execute(select(EntryTypeSetting).where(EntryTypeSetting.entry_type_id == obj.id)).scalar_one_or_none()
    if setting is not None:
        db.delete(setting)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.categories")),
):
    return db.execute(select(Category).order_by(Category.sort_order.asc(), Category.id.asc())).scalars().all()


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.categories")),
):
    obj = db.get(Category, category_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="category not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.categories")),
):
    obj = db.get(Category, category_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="category not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/payment-methods")
def create_payment_method(
    payload: PaymentMethodCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.payment_methods")),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    exists = db.execute(select(PaymentMethod.id).where(PaymentMethod.name == name)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="账户名称已存在")
    payload.name = name
    obj = PaymentMethod(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/payment-methods")
def list_payment_methods(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.payment_methods")),
):
    return db.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order.asc(), PaymentMethod.id.asc())).scalars().all()


@router.put("/payment-methods/{payment_method_id}")
def update_payment_method(
    payment_method_id: int,
    payload: PaymentMethodCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.payment_methods")),
):
    obj = db.get(PaymentMethod, payment_method_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="payment method not found")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    exists = db.execute(
        select(PaymentMethod.id).where(PaymentMethod.name == name, PaymentMethod.id != payment_method_id)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="账户名称已存在")
    payload.name = name
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/payment-methods/{payment_method_id}")
def delete_payment_method(
    payment_method_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.payment_methods")),
):
    obj = db.get(PaymentMethod, payment_method_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="payment method not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/accounts")
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = Account(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/accounts")
def list_accounts(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(Account).order_by(Account.id.asc())).scalars().all()


@router.put("/accounts/{account_id}")
def update_account(
    account_id: int,
    payload: AccountCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = db.get(Account, account_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="account not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = db.get(Account, account_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="account not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    stmt = select(User).order_by(User.id.asc())
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        user_ids = [r[0] for r in db.execute(select(UserTenantAccess.user_id).where(UserTenantAccess.tenant_id == tenant_id)).all()]
        if not user_ids:
            return []
        stmt = stmt.where(User.id.in_(user_ids))
    users = db.execute(stmt).scalars().all()
    pmap = _platform_ids_map(db)
    tenant_map = {r.user_id: r for r in db.execute(select(UserTenantAccess)).scalars().all()}
    result = []
    for u in users:
        ta = tenant_map.get(u.id)
        item = {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "status": u.status,
            "tenant_id": ta.tenant_id if ta else None,
            "tenant_status": ta.status if ta else None,
            "tenant_expire_at": ta.expire_at.isoformat() if ta and ta.expire_at else None,
            "platform_id": u.platform_id,
            "platform_ids": pmap.get(u.id, ([int(u.platform_id)] if u.platform_id is not None else [])),
        }
        result.append(item)
    return result


@router.post("/users")
def create_user(
    username: str,
    password: str,
    role: str,
    tenant_id: int | None = None,
    platform_id: int | None = None,
    platform_ids: str | None = None,
    status: str = "enabled",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    if current_user.role != UserRole.SUPER_ADMIN.value and role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        raise HTTPException(status_code=403, detail="tenant admin can only create bookkeeper/viewer")
    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="username exists")
    parsed_platform_ids = [int(x) for x in (platform_ids or "").split(",") if x.strip().isdigit()]
    final_platform_ids = _normalize_platform_ids(parsed_platform_ids, platform_id)
    if role != UserRole.SUPER_ADMIN.value:
        if current_user.role == UserRole.SUPER_ADMIN.value:
            if tenant_id is None:
                raise HTTPException(status_code=400, detail="tenant_id is required")
        else:
            tenant_id = _require_current_tenant_id(db, current_user)
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
    user = User(username=username, password_hash=get_password_hash(password), role=role, platform_id=(final_platform_ids[0] if final_platform_ids else None), status=status)
    db.add(user)
    db.flush()
    _set_user_platforms(db, user.id, final_platform_ids)
    if role != UserRole.SUPER_ADMIN.value:
        db.add(UserTenantAccess(user_id=user.id, tenant_id=tenant_id, status="enabled", expire_at=None))
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "platform_id": user.platform_id,
        "platform_ids": final_platform_ids,
    }


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    role: str,
    status: str,
    tenant_id: int | None = None,
    platform_id: int | None = None,
    platform_ids: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if current_user.role != UserRole.SUPER_ADMIN.value and role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        raise HTTPException(status_code=403, detail="tenant admin can only set bookkeeper/viewer")
    user.role = role
    user.status = status
    parsed_platform_ids = [int(x) for x in (platform_ids or "").split(",") if x.strip().isdigit()]
    final_platform_ids = _normalize_platform_ids(parsed_platform_ids, platform_id)
    user.platform_id = final_platform_ids[0] if final_platform_ids else None
    _set_user_platforms(db, user.id, final_platform_ids)
    if role != UserRole.SUPER_ADMIN.value:
        if current_user.role == UserRole.SUPER_ADMIN.value:
            if tenant_id is None:
                row0 = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user.id)).scalar_one_or_none()
                tenant_id = row0.tenant_id if row0 else None
            if tenant_id is None:
                raise HTTPException(status_code=400, detail="tenant_id is required")
        else:
            tenant_id = _require_current_tenant_id(db, current_user)
        row = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user.id)).scalar_one_or_none()
        if row is None:
            db.add(UserTenantAccess(user_id=user.id, tenant_id=tenant_id, status="enabled", expire_at=None))
        else:
            row.tenant_id = tenant_id
    else:
        db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.user_id == user.id))
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "platform_id": user.platform_id,
        "platform_ids": final_platform_ids,
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        ta = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user_id)).scalar_one_or_none()
        if ta is None or ta.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="cannot delete user from another tenant")
    db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.user_id == user_id))
    db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id == user_id))
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.put("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    if len(new_password or "") < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 chars")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_id = _require_current_tenant_id(db, current_user)
        ta = db.execute(select(UserTenantAccess).where(UserTenantAccess.user_id == user_id)).scalar_one_or_none()
        if ta is None or ta.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="cannot reset password for another tenant")
    user.password_hash = get_password_hash(new_password)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="users",
            action="reset_password",
            before_data=None,
            after_data=f"target_user_id={user.id}",
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/super-users")
def list_super_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value})),
):
    rows = db.execute(
        select(User)
        .where(User.role.in_([UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value]))
        .order_by(User.id.asc())
    ).scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role, "status": u.status} for u in rows]


@router.post("/super-users")
def create_super_user(
    username: str,
    password: str,
    role: str,
    status: str = "enabled",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value})),
):
    if role not in {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value}:
        raise HTTPException(status_code=400, detail="invalid role")
    if len(password or "") < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 chars")
    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="username exists")
    u = User(username=username, password_hash=get_password_hash(password), role=role, status=status)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role, "status": u.status}


@router.put("/super-users/{user_id}")
def update_super_user(
    user_id: int,
    role: str,
    status: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value})),
):
    if role not in {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value}:
        raise HTTPException(status_code=400, detail="invalid role")
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="user not found")
    u.role = role
    u.status = status
    db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.user_id == u.id))
    db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id == u.id))
    db.commit()
    return {"ok": True}


@router.delete("/super-users/{user_id}")
def delete_super_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value})),
):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="user not found")
    if u.role not in {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value}:
        raise HTTPException(status_code=400, detail="not a super user")
    if u.role == UserRole.SUPER_ADMIN.value:
        super_count = db.execute(select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN.value)).scalar_one()
        if int(super_count or 0) <= 1:
            raise HTTPException(status_code=400, detail="cannot delete last super_admin")
    db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.user_id == u.id))
    db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id == u.id))
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/role-permissions")
def list_role_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value})),
):
    if current_user.role == UserRole.SUPER_ADMIN.value:
        roles = [UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value, UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value]
    else:
        roles = [UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value]
    role_modules = {role: enabled_modules_for_role(db, role) for role in roles}
    for role in roles:
        if not role_modules[role]:
            role_modules[role] = DEFAULT_ROLE_MODULES.get(role, [])
    return {"modules": MODULES, "role_modules": role_modules}


@router.put("/role-permissions/{role}")
def update_role_permissions(
    role: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value})),
):
    valid_roles = {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value, UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value}
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail="invalid role")
    if current_user.role != UserRole.SUPER_ADMIN.value and role == UserRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="only super admin can edit super admin permissions")
    module_keys = payload.get("module_keys") or []
    valid_module_keys = {m["key"] for m in MODULES}
    if any(k not in valid_module_keys for k in module_keys):
        raise HTTPException(status_code=400, detail="invalid module key")
    if role in {UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value}:
        if any(k not in SUPER_ONLY_MODULE_KEYS for k in module_keys):
            raise HTTPException(status_code=400, detail="super role can only set super modules")
    replace_role_modules(db, role, module_keys)
    return {"ok": True}
