import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.entities import (
    AccountSnapshot,
    AuditLog,
    Category,
    DailySummary,
    HandoverPaymentSnapshot,
    HandoverSnapshot,
    PaymentMethod,
    Platform,
    Shift,
    Transaction,
    User,
)
from app.models.enums import UserRole


router = APIRouter(prefix="/system", tags=["system"])


BACKUP_TABLES = [
    ("platforms", Platform),
    ("shifts", Shift),
    ("payment_methods", PaymentMethod),
    ("categories", Category),
    ("users", User),
    ("transactions", Transaction),
    ("daily_summaries", DailySummary),
    ("account_snapshots", AccountSnapshot),
    ("handover_snapshots", HandoverSnapshot),
    ("handover_payment_snapshots", HandoverPaymentSnapshot),
    ("audit_logs", AuditLog),
]


def _serialize_rows(rows, model):
    cols = [c.name for c in model.__table__.columns]
    result = []
    for row in rows:
        data = {}
        for c in cols:
            val = getattr(row, c)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            data[c] = val
        result.append(data)
    return result


@router.get("/logs")
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    total = db.execute(select(func.count(AuditLog.id))).scalar_one()
    rows = db.execute(
        select(AuditLog).order_by(desc(AuditLog.id)).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/charts/profit-by-platform")
def profit_by_platform(db: Session = Depends(get_db), _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value}))):
    rows = db.execute(
        select(Transaction.platform_id, func.sum(Transaction.amount), Transaction.type)
        .where(Transaction.deleted_at.is_(None))
        .group_by(Transaction.platform_id, Transaction.type)
    ).all()
    data: dict[int, dict[str, float]] = {}
    for platform_id, amount_sum, tx_type in rows:
        if platform_id not in data:
            data[platform_id] = {"income": 0.0, "expense": 0.0}
        if tx_type == "income":
            data[platform_id]["income"] += float(amount_sum or 0)
        elif tx_type == "expense":
            data[platform_id]["expense"] += float(amount_sum or 0)
    result = []
    for platform_id, item in data.items():
        result.append({"platform_id": platform_id, "net": item["income"] - item["expense"]})
    return result


@router.get("/charts/income-expense-trend")
def income_expense_trend(db: Session = Depends(get_db), _: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value}))):
    rows = db.execute(
        select(DailySummary.bill_date, func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit))
        .group_by(DailySummary.bill_date)
        .order_by(DailySummary.bill_date.asc())
    ).all()
    return [
        {"date": r[0].isoformat(), "income": float(r[1] or 0), "expense": float(r[2] or 0), "net": float(r[3] or 0)}
        for r in rows
    ]


@router.get("/backup/export")
def export_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    payload = {
        "meta": {"exported_at": datetime.utcnow().isoformat(), "exported_by": current_user.username},
        "tables": {},
    }
    for table_name, model in BACKUP_TABLES:
        rows = db.execute(select(model)).scalars().all()
        payload["tables"][table_name] = _serialize_rows(rows, model)

    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"accounting-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/backup/restore")
async def restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="backup file must be json")
    raw = await file.read()
    data = json.loads(raw.decode("utf-8"))
    tables = data.get("tables", {})

    for _, model in reversed(BACKUP_TABLES):
        db.execute(model.__table__.delete())
    db.flush()

    for table_name, model in BACKUP_TABLES:
        rows = tables.get(table_name, [])
        if rows:
            db.execute(model.__table__.insert(), rows)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="restore_backup",
            before_data=None,
            after_data=f"file={file.filename}",
        )
    )
    db.commit()
    return {"ok": True, "restored_file": file.filename}


@router.post("/data/delete-before")
def delete_data_before_date(
    before_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    now = datetime.utcnow()
    tx_rows = db.execute(select(Transaction).where(Transaction.bill_date < before_date, Transaction.deleted_at.is_(None))).scalars().all()
    for tx in tx_rows:
        tx.deleted_at = now

    db.execute(DailySummary.__table__.delete().where(DailySummary.bill_date < before_date))
    db.execute(AccountSnapshot.__table__.delete().where(AccountSnapshot.bill_date < before_date))

    h_rows = db.execute(select(HandoverSnapshot).where(HandoverSnapshot.bill_date < before_date)).scalars().all()
    for h in h_rows:
        db.execute(HandoverPaymentSnapshot.__table__.delete().where(HandoverPaymentSnapshot.handover_id == h.id))
        db.delete(h)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="delete_before_date",
            before_data=None,
            after_data=f"before_date={before_date},tx={len(tx_rows)}",
        )
    )
    db.commit()
    return {"ok": True, "deleted_transactions": len(tx_rows)}


@router.post("/data/delete-by-date")
def delete_data_by_date(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value})),
):
    now = datetime.utcnow()
    tx_rows = db.execute(select(Transaction).where(Transaction.bill_date == bill_date, Transaction.deleted_at.is_(None))).scalars().all()
    for tx in tx_rows:
        tx.deleted_at = now

    db.execute(DailySummary.__table__.delete().where(DailySummary.bill_date == bill_date))
    db.execute(AccountSnapshot.__table__.delete().where(AccountSnapshot.bill_date == bill_date))

    h_rows = db.execute(select(HandoverSnapshot).where(HandoverSnapshot.bill_date == bill_date)).scalars().all()
    for h in h_rows:
        db.execute(HandoverPaymentSnapshot.__table__.delete().where(HandoverPaymentSnapshot.handover_id == h.id))
        db.delete(h)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="delete_by_date",
            before_data=None,
            after_data=f"bill_date={bill_date},tx={len(tx_rows)}",
        )
    )
    db.commit()
    return {"ok": True, "deleted_transactions": len(tx_rows)}
