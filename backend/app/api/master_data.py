from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.permissions import MODULES, DEFAULT_ROLE_MODULES, enabled_modules_for_role, replace_role_modules
from app.core.security import get_password_hash
from app.models.entities import Account, Category, EntryType, PaymentMethod, Platform, Shift, User
from app.models.enums import UserRole
from app.schemas.common import AccountCreate, CategoryCreate, EntryTypeCreate, MasterDataCreate, PaymentMethodCreate, ShiftCreate


router = APIRouter(prefix="/master", tags=["master"])


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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = Platform(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/platforms")
def list_platforms(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(Platform).order_by(Platform.sort_order.asc(), Platform.id.asc())).scalars().all()


@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int,
    payload: MasterDataCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = Shift(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/shifts")
def list_shifts(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(Shift).order_by(Shift.sort_order.asc(), Shift.id.asc())).scalars().all()


@router.put("/shifts/{shift_id}")
def update_shift(
    shift_id: int,
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = EntryType(name=payload.name, effect=payload.effect, sort_order=payload.sort_order, status=payload.status)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/entry-types")
def list_entry_types(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(EntryType).order_by(EntryType.sort_order.asc(), EntryType.id.asc())).scalars().all()


@router.put("/entry-types/{entry_type_id}")
def update_entry_type(
    entry_type_id: int,
    payload: EntryTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = db.get(EntryType, entry_type_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="entry type not found")
    obj.name = payload.name
    obj.effect = payload.effect
    obj.sort_order = payload.sort_order
    obj.status = payload.status
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/entry-types/{entry_type_id}")
def delete_entry_type(
    entry_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = db.get(EntryType, entry_type_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="entry type not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(Category).order_by(Category.sort_order.asc(), Category.id.asc())).scalars().all()


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = PaymentMethod(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/payment-methods")
def list_payment_methods(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    return db.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order.asc(), PaymentMethod.id.asc())).scalars().all()


@router.put("/payment-methods/{payment_method_id}")
def update_payment_method(
    payment_method_id: int,
    payload: PaymentMethodCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    obj = db.get(PaymentMethod, payment_method_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="payment method not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/payment-methods/{payment_method_id}")
def delete_payment_method(
    payment_method_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
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
    return db.execute(select(User).order_by(User.id.asc())).scalars().all()


@router.post("/users")
def create_user(
    username: str,
    password: str,
    role: str,
    platform_id: int | None = None,
    status: str = "enabled",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="username exists")
    user = User(username=username, password_hash=get_password_hash(password), role=role, platform_id=platform_id, status=status)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    role: str,
    status: str,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.role = role
    user.status = status
    user.platform_id = platform_id
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    db.delete(user)
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
