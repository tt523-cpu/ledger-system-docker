from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_tenant_id, require_roles
from app.models.entities import Account, AccountSnapshot, AuditLog, User
from app.models.enums import UserRole
from app.schemas.common import AccountSnapshotOut, ActualBalanceUpdate
from app.services.balance import rebuild_account_snapshot


router = APIRouter(prefix="/balances", tags=["balances"])


@router.post("/rebuild")
def rebuild_snapshots(
    bill_date: date,
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tenant_id = get_current_tenant_id(db, current_user)
    account_stmt = select(Account)
    if tenant_id is not None:
        account_stmt = account_stmt.where(Account.tenant_id == tenant_id)
    accounts = db.execute(account_stmt).scalars().all()
    count = 0
    for account in accounts:
        snapshot = rebuild_account_snapshot(db, bill_date, shift_id, account.id, current_user.id, tenant_id)
        if snapshot:
            count += 1

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="balances",
            action="rebuild",
            after_data=f"date={bill_date},shift={shift_id},count={count}",
        )
    )
    db.commit()
    return {"rebuild_count": count}


@router.get("/daily", response_model=list[AccountSnapshotOut])
def list_daily_snapshots(
    bill_date: date,
    shift_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    rows = db.execute(
        select(AccountSnapshot).where(AccountSnapshot.bill_date == bill_date, AccountSnapshot.shift_id == shift_id)
    ).scalars().all()
    return rows


@router.patch("/{snapshot_id}/actual")
def update_actual_balance(
    snapshot_id: int,
    payload: ActualBalanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    snapshot = db.get(AccountSnapshot, snapshot_id)
    if snapshot is None:
        return {"error": "snapshot not found"}
    before = snapshot.actual_balance
    snapshot.actual_balance = payload.actual_balance
    snapshot.difference = payload.actual_balance - snapshot.theoretical_balance
    snapshot.operator_id = current_user.id

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="balances",
            action="update_actual",
            before_data=f"actual={before}",
            after_data=f"actual={payload.actual_balance}",
        )
    )
    db.commit()
    return {"snapshot_id": snapshot_id, "difference": snapshot.difference}
