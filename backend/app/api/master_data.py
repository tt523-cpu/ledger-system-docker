from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_module, require_roles
from app.core.permissions import MODULES, DEFAULT_ROLE_MODULES, enabled_modules_for_role, replace_role_modules
from app.core.security import get_password_hash
from app.models.entities import Account, AuditLog, Category, EntryType, EntryTypeSetting, PaymentMethod, Platform, Shift, User, UserPlatformAccess
from app.models.enums import UserRole
from app.schemas.common import AccountCreate, CategoryCreate, EntryTypeCreate, MasterDataCreate, PaymentMethodCreate, ShiftCreate


router = APIRouter(prefix="/master", tags=["master"])


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


def _apply_common_update(obj, payload: MasterDataCreate):
    obj.name = payload.name
    obj.sort_order = payload.sort_order
    obj.status = payload.status
    if hasattr(obj, "remark"):
        obj.remark = payload.remark
    return obj


@router.post("/platforms")
def create_platform(
    payload: MasterDataCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.platforms")),
):
    obj = Platform(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/platforms")
def list_platforms(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.platforms")),
):
    return db.execute(select(Platform).order_by(Platform.sort_order.asc(), Platform.id.asc())).scalars().all()


@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int,
    payload: MasterDataCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.platforms")),
):
    obj = db.get(Platform, platform_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="platform not found")
    _apply_common_update(obj, payload)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/platforms/{platform_id}")
def delete_platform(
    platform_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.platforms")),
):
    obj = db.get(Platform, platform_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="platform not found")
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
    pmap = _platform_ids_map(db)
    result = []
    for u in users:
        item = {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "status": u.status,
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
    platform_id: int | None = None,
    platform_ids: str | None = None,
    status: str = "enabled",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="username exists")
    parsed_platform_ids = [int(x) for x in (platform_ids or "").split(",") if x.strip().isdigit()]
    final_platform_ids = _normalize_platform_ids(parsed_platform_ids, platform_id)
    user = User(username=username, password_hash=get_password_hash(password), role=role, platform_id=(final_platform_ids[0] if final_platform_ids else None), status=status)
    db.add(user)
    db.flush()
    _set_user_platforms(db, user.id, final_platform_ids)
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
    platform_id: int | None = None,
    platform_ids: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.role = role
    user.status = status
    parsed_platform_ids = [int(x) for x in (platform_ids or "").split(",") if x.strip().isdigit()]
    final_platform_ids = _normalize_platform_ids(parsed_platform_ids, platform_id)
    user.platform_id = final_platform_ids[0] if final_platform_ids else None
    _set_user_platforms(db, user.id, final_platform_ids)
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
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


@router.get("/role-permissions")
def list_role_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    valid_roles = {UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value}
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail="invalid role")
    module_keys = payload.get("module_keys") or []
    valid_module_keys = {m["key"] for m in MODULES}
    if any(k not in valid_module_keys for k in module_keys):
        raise HTTPException(status_code=400, detail="invalid module key")
    replace_role_modules(db, role, module_keys)
    return {"ok": True}
