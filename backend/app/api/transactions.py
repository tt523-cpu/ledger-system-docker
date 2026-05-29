from uuid import uuid4

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.entities import AuditLog, Category, Transaction, User
from app.models.enums import TransactionType, UserRole
from app.schemas.common import BatchTransactionCreate, OffsetTransactionCreate
from app.services.summary import rebuild_daily_summary_for_date


router = APIRouter(prefix="/transactions", tags=["transactions"])


def normalize_tx_type(raw_type: str) -> str:
    if raw_type in {"redeem", "exchange", "兑奖", "mischarge", "误上"}:
        return TransactionType.EXPENSE.value
    if raw_type in {"reversal", "回冲", "调账"}:
        return TransactionType.ADJUST.value
    return raw_type


def default_type_label(raw_type: str, normalized: str) -> str:
    if raw_type in {"redeem", "exchange", "兑奖"}:
        return "兑奖"
    if raw_type in {"mischarge", "误上"}:
        return "误上"
    if raw_type in {"reversal", "回冲", "调账"}:
        return "回冲"
    if normalized == TransactionType.INCOME.value:
        return "充值"
    if normalized == TransactionType.EXPENSE.value:
        return "支出"
    if normalized == TransactionType.ADJUST.value:
        return "回冲"
    return raw_type


@router.post("/batch")
def create_batch_transactions(
    payload: BatchTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    if not payload.lines:
        raise HTTPException(status_code=400, detail="lines cannot be empty")

    if current_user.role == UserRole.BOOKKEEPER.value:
        if current_user.platform_id is None:
            raise HTTPException(status_code=400, detail="bookkeeper has no platform binding")
        effective_platform_id = current_user.platform_id
    else:
        if payload.platform_id is None:
            raise HTTPException(status_code=400, detail="platform_id is required")
        effective_platform_id = payload.platform_id

    biz_group_no = uuid4().hex[:16]
    created = []

    for line in payload.lines:
        normalized_type = normalize_tx_type(line.type)
        type_label = (line.type_label or "").strip() or default_type_label(line.type, normalized_type)

        if normalized_type == TransactionType.TRANSFER.value:
            raise HTTPException(status_code=400, detail="transfer is disabled")

        if normalized_type == TransactionType.EXPENSE.value and not line.category_id:
            raise HTTPException(status_code=400, detail="category_id is required for expense")

        if line.category_id is not None:
            category = db.execute(select(Category).where(Category.id == line.category_id)).scalar_one_or_none()
            if category is None:
                raise HTTPException(status_code=404, detail=f"Category {line.category_id} not found")

        tx = Transaction(
            bill_date=payload.bill_date,
            shift_id=payload.shift_id,
            platform_id=effective_platform_id,
            type=normalized_type,
            biz_type_label=type_label,
            category_id=line.category_id,
            account_id=line.account_id,
            target_account_id=line.target_account_id,
            payment_method_id=line.payment_method_id,
            amount=line.amount,
            remark=line.remark,
            biz_group_no=biz_group_no,
            operator_id=current_user.id,
        )
        db.add(tx)
        created.append(tx)

    db.flush()
    rebuild_daily_summary_for_date(db, payload.bill_date)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="create_batch",
            before_data=None,
            after_data=f"count={len(created)},group={biz_group_no}",
        )
    )

    db.commit()
    return {"created_count": len(created), "biz_group_no": biz_group_no}


@router.get("")
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    bill_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    shift_id: int | None = None,
    platform_id: int | None = None,
    tx_type: str | None = None,
    category_id: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    stmt = select(Transaction).where(Transaction.deleted_at.is_(None))
    count_stmt = select(func.count(Transaction.id)).where(Transaction.deleted_at.is_(None))
    if bill_date:
        stmt = stmt.where(Transaction.bill_date == bill_date)
        count_stmt = count_stmt.where(Transaction.bill_date == bill_date)
    else:
        if start_date:
            stmt = stmt.where(Transaction.bill_date >= start_date)
            count_stmt = count_stmt.where(Transaction.bill_date >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.bill_date <= end_date)
            count_stmt = count_stmt.where(Transaction.bill_date <= end_date)
    if shift_id:
        stmt = stmt.where(Transaction.shift_id == shift_id)
        count_stmt = count_stmt.where(Transaction.shift_id == shift_id)
    if platform_id:
        stmt = stmt.where(Transaction.platform_id == platform_id)
        count_stmt = count_stmt.where(Transaction.platform_id == platform_id)
    if tx_type:
        stmt = stmt.where(Transaction.type == tx_type)
        count_stmt = count_stmt.where(Transaction.type == tx_type)
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
        count_stmt = count_stmt.where(Transaction.category_id == category_id)
    if keyword:
        stmt = stmt.where(Transaction.remark.like(f"%{keyword}%"))
        count_stmt = count_stmt.where(Transaction.remark.like(f"%{keyword}%"))

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Transaction.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.put("/{tx_id}")
def update_transaction(
    tx_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="transaction not found")
    old_bill_date = tx.bill_date
    old_shift_id = tx.shift_id
    old_platform_id = tx.platform_id

    before = {
        "amount": str(tx.amount),
        "type": tx.type,
        "category_id": tx.category_id,
        "remark": tx.remark,
        "biz_type_label": tx.biz_type_label,
    }
    updatable = {
        "type",
        "platform_id",
        "category_id",
        "account_id",
        "target_account_id",
        "payment_method_id",
        "amount",
        "remark",
        "biz_type_label",
    }
    for k, v in payload.items():
        if k in updatable:
            if k == "type":
                v = normalize_tx_type(v)
            setattr(tx, k, v)

    db.flush()
    rebuild_daily_summary_for_date(db, tx.bill_date)
    if old_bill_date != tx.bill_date:
        rebuild_daily_summary_for_date(db, old_bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="update",
            before_data=str(before),
            after_data=str(payload),
        )
    )
    db.commit()
    return {"ok": True}


@router.delete("/{tx_id}")
def soft_delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="transaction not found")

    tx.deleted_at = datetime.utcnow()
    db.flush()
    rebuild_daily_summary_for_date(db, tx.bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="delete",
            before_data=f"id={tx.id}",
            after_data=None,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/offset")
def create_offset_transactions(
    payload: OffsetTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    if current_user.role == UserRole.BOOKKEEPER.value:
        if current_user.platform_id is None:
            raise HTTPException(status_code=400, detail="bookkeeper has no platform binding")
        effective_platform_id = current_user.platform_id
    else:
        if payload.platform_id is None:
            raise HTTPException(status_code=400, detail="platform_id is required")
        effective_platform_id = payload.platform_id

    biz_group_no = uuid4().hex[:16]

    recharge = Transaction(
        bill_date=payload.bill_date,
        shift_id=payload.shift_id,
        platform_id=effective_platform_id,
        type=TransactionType.INCOME.value,
        category_id=payload.recharge_category_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        remark=f"[offset-in] {payload.remark}",
        biz_group_no=biz_group_no,
        operator_id=current_user.id,
    )
    payout = Transaction(
        bill_date=payload.bill_date,
        shift_id=payload.shift_id,
        platform_id=effective_platform_id,
        type=TransactionType.EXPENSE.value,
        category_id=payload.payout_category_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        people_count=None,
        remark=f"[offset-out] {payload.remark}",
        biz_group_no=biz_group_no,
        operator_id=current_user.id,
    )
    db.add(recharge)
    db.add(payout)

    db.flush()
    rebuild_daily_summary_for_date(db, payload.bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="create_offset",
            before_data=None,
            after_data=f"amount={payload.amount},group={biz_group_no}",
        )
    )
    db.commit()
    return {"created_count": 2, "biz_group_no": biz_group_no}
