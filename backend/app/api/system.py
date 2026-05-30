import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_module, require_roles
from app.core.time_utils import beijing_now
from app.models.entities import (
    AccountSnapshot,
    AuditLog,
    Category,
    DailySummary,
    HandoverPaymentSnapshot,
    HandoverSnapshot,
    MonthLock,
    PaymentMethod,
    Platform,
    Shift,
    Transaction,
    User,
    UserPlatformAccess,
)
from app.models.enums import UserRole
from app.services.month_lock import month_key


router = APIRouter(prefix="/system", tags=["system"])
BACKUP_DIR = Path("backups")


BACKUP_TABLES = [
    ("platforms", Platform),
    ("shifts", Shift),
    ("payment_methods", PaymentMethod),
    ("categories", Category),
    ("users", User),
    ("user_platform_access", UserPlatformAccess),
    ("transactions", Transaction),
    ("daily_summaries", DailySummary),
    ("account_snapshots", AccountSnapshot),
    ("handover_snapshots", HandoverSnapshot),
    ("handover_payment_snapshots", HandoverPaymentSnapshot),
    ("month_locks", MonthLock),
    ("audit_logs", AuditLog),
]


@router.get("/month-locks")
def list_month_locks(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("system.tools")),
):
    return db.execute(select(MonthLock).order_by(MonthLock.lock_month.desc())).scalars().all()


@router.post("/month-lock")
def lock_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="invalid month")
    key = month_key(datetime(year, month, 1).date())
    row = db.execute(select(MonthLock).where(MonthLock.lock_month == key)).scalar_one_or_none()
    if row is None:
        row = MonthLock(lock_month=key, is_locked=True, locked_by=current_user.id)
        db.add(row)
    else:
        row.is_locked = True
        row.locked_by = current_user.id
        row.locked_at = beijing_now()
    db.commit()
    return {"ok": True, "lock_month": key}


@router.delete("/month-lock")
def unlock_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="invalid month")
    key = month_key(datetime(year, month, 1).date())
    row = db.execute(select(MonthLock).where(MonthLock.lock_month == key)).scalar_one_or_none()
    if row is None:
        return {"ok": True, "lock_month": key}
    row.is_locked = False
    row.locked_by = current_user.id
    row.locked_at = beijing_now()
    db.commit()
    return {"ok": True, "lock_month": key}


def _serialize_rows(rows, model):
    cols = [c.name for c in model.__table__.columns]
    result = []
    for row in rows:
        data = {}
        for c in cols:
            val = getattr(row, c)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif isinstance(val, Decimal):
                val = float(val)
            data[c] = val
        result.append(data)
    return result


def _build_backup_payload(db: Session, exported_by: str):
    payload = {
        "meta": {"exported_at": beijing_now().isoformat(), "exported_by": exported_by},
        "tables": {},
    }
    for table_name, model in BACKUP_TABLES:
        rows = db.execute(select(model)).scalars().all()
        payload["tables"][table_name] = _serialize_rows(rows, model)
    return payload


def _write_server_backup(db: Session, exported_by: str, reason: str):
    payload = _build_backup_payload(db, exported_by)
    payload["meta"]["reason"] = reason
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"accounting-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
    path = BACKUP_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return filename


@router.get("/logs")
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_module("logs", {UserRole.ADMIN.value})),
):
    total = db.execute(select(func.count(AuditLog.id))).scalar_one()
    rows = db.execute(
        select(AuditLog).order_by(desc(AuditLog.id)).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/charts/profit-by-platform")
def profit_by_platform(
    platform_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_module("reports.charts")),
):
    rows = db.execute(
        select(Transaction.platform_id, func.sum(Transaction.amount), Transaction.type)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.platform_id == platform_id if platform_id else True,
        )
        .group_by(Transaction.platform_id, Transaction.type)
    ).all()
    platform_name_map = {r[0]: r[1] for r in db.execute(select(Platform.id, Platform.name)).all()}
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
        result.append(
            {
                "platform_id": platform_id,
                "platform_name": platform_name_map.get(platform_id, f"平台#{platform_id}"),
                "net": item["income"] - item["expense"],
            }
        )
    return result


@router.get("/charts/income-expense-trend")
def income_expense_trend(
    platform_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_module("reports.charts")),
):
    stmt = select(DailySummary.bill_date, func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit))
    if platform_id:
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    rows = db.execute(stmt.group_by(DailySummary.bill_date).order_by(DailySummary.bill_date.asc())).all()
    return [
        {"date": r[0].isoformat(), "income": float(r[1] or 0), "expense": float(r[2] or 0), "net": float(r[3] or 0)}
        for r in rows
    ]


@router.get("/backup/export")
def export_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    payload = _build_backup_payload(db, current_user.username)

    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"accounting-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/backup/create")
def create_server_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    filename = _write_server_backup(db, current_user.username, "manual_backup")
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="create_backup",
            before_data=None,
            after_data=f"file={filename}",
        )
    )
    db.commit()
    return {"ok": True, "backup_file": filename}


@router.get("/backup/files")
def list_backup_files(
    _: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if not BACKUP_DIR.exists():
        return []
    files = []
    for p in sorted(BACKUP_DIR.glob("accounting-backup-*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        files.append(
            {
                "filename": p.name,
                "size": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
            }
        )
    return files


@router.get("/backup/files/{filename}")
def download_backup_file(
    filename: str,
    _: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = BACKUP_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="backup file not found")
    content = path.read_bytes()
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete("/backup/files/{filename}")
def delete_backup_file(
    filename: str,
    _: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = BACKUP_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="backup file not found")
    path.unlink()
    return {"ok": True, "filename": filename}


@router.post("/backup/restore")
async def restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
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
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    backup_filename = _write_server_backup(db, current_user.username, f"delete_before_date:{before_date}")
    now = beijing_now().replace(tzinfo=None)
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
    return {"ok": True, "deleted_transactions": len(tx_rows), "backup_file": backup_filename}


@router.post("/data/delete-by-date")
def delete_data_by_date(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    backup_filename = _write_server_backup(db, current_user.username, f"delete_by_date:{bill_date}")
    now = beijing_now().replace(tzinfo=None)
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
    return {"ok": True, "deleted_transactions": len(tx_rows), "backup_file": backup_filename}
