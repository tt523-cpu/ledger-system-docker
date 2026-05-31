import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_accessible_platform_ids, get_user_tenant_access, require_module, require_roles
from app.core.time_utils import beijing_now
from app.models.entities import (
    Account,
    AccountSnapshot,
    AuditLog,
    Category,
    DailySummary,
    EntryType,
    EntryTypeSetting,
    HandoverPaymentSnapshot,
    HandoverSnapshot,
    MonthLock,
    OperationLog,
    PaymentMethod,
    Platform,
    RoleModulePermission,
    Shift,
    Tenant,
    TenantPlatformAccess,
    Transaction,
    User,
    UserPlatformAccess,
    UserTenantAccess,
)
from app.models.enums import UserRole
from app.services.month_lock import month_key


router = APIRouter(prefix="/system", tags=["system"])
BACKUP_DIR = Path("backups")


BACKUP_TABLES = [
    ("tenants", Tenant),
    ("platforms", Platform),
    ("shifts", Shift),
    ("accounts", Account),
    ("payment_methods", PaymentMethod),
    ("categories", Category),
    ("entry_types", EntryType),
    ("entry_type_settings", EntryTypeSetting),
    ("users", User),
    ("role_module_permissions", RoleModulePermission),
    ("user_tenant_access", UserTenantAccess),
    ("tenant_platform_access", TenantPlatformAccess),
    ("user_platform_access", UserPlatformAccess),
    ("transactions", Transaction),
    ("daily_summaries", DailySummary),
    ("account_snapshots", AccountSnapshot),
    ("handover_snapshots", HandoverSnapshot),
    ("handover_payment_snapshots", HandoverPaymentSnapshot),
    ("month_locks", MonthLock),
    ("audit_logs", AuditLog),
    ("operation_logs", OperationLog),
]


def _sanitize_user_fk_rows(tables: dict):
    users = tables.get("users", [])
    if not isinstance(users, list):
        return {}

    user_ids = {row.get("id") for row in users if isinstance(row, dict) and row.get("id") is not None}
    if not user_ids:
        return {}

    admin_id = next(
        (row.get("id") for row in users if isinstance(row, dict) and row.get("username") == "admin" and row.get("id") is not None),
        None,
    )
    fallback_user_id = admin_id if admin_id in user_ids else min(user_ids)

    fixed_counts = {
        "transactions.operator_id": 0,
        "month_locks.locked_by": 0,
        "audit_logs.user_id": 0,
        "operation_logs.user_id": 0,
    }

    tx_rows = tables.get("transactions", [])
    if isinstance(tx_rows, list):
        for row in tx_rows:
            if not isinstance(row, dict):
                continue
            operator_id = row.get("operator_id")
            if operator_id is not None and operator_id not in user_ids:
                row["operator_id"] = fallback_user_id
                fixed_counts["transactions.operator_id"] += 1

    lock_rows = tables.get("month_locks", [])
    if isinstance(lock_rows, list):
        for row in lock_rows:
            if not isinstance(row, dict):
                continue
            locked_by = row.get("locked_by")
            if locked_by is not None and locked_by not in user_ids:
                row["locked_by"] = fallback_user_id
                fixed_counts["month_locks.locked_by"] += 1

    audit_rows = tables.get("audit_logs", [])
    if isinstance(audit_rows, list):
        for row in audit_rows:
            if not isinstance(row, dict):
                continue
            user_id = row.get("user_id")
            if user_id is not None and user_id not in user_ids:
                row["user_id"] = fallback_user_id
                fixed_counts["audit_logs.user_id"] += 1

    op_rows = tables.get("operation_logs", [])
    if isinstance(op_rows, list):
        for row in op_rows:
            if not isinstance(row, dict):
                continue
            user_id = row.get("user_id")
            if user_id is not None and user_id not in user_ids:
                row["user_id"] = fallback_user_id
                fixed_counts["operation_logs.user_id"] += 1

    return {k: v for k, v in fixed_counts.items() if v > 0}


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


def _build_tenant_backup_payload(db: Session, exported_by: str, tenant_id: int):
    platform_ids = [r[0] for r in db.execute(select(TenantPlatformAccess.platform_id).where(TenantPlatformAccess.tenant_id == tenant_id)).all()]
    user_ids = [r[0] for r in db.execute(select(UserTenantAccess.user_id).where(UserTenantAccess.tenant_id == tenant_id)).all()]

    payload = {
        "meta": {"exported_at": beijing_now().isoformat(), "exported_by": exported_by, "tenant_id": tenant_id},
        "tables": {},
    }
    payload["tables"]["tenants"] = _serialize_rows(db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalars().all(), Tenant)
    payload["tables"]["platforms"] = _serialize_rows(
        db.execute(select(Platform).where(Platform.id.in_(platform_ids) if platform_ids else False)).scalars().all(), Platform
    )
    payload["tables"]["users"] = _serialize_rows(
        db.execute(select(User).where(User.id.in_(user_ids) if user_ids else False)).scalars().all(), User
    )
    payload["tables"]["user_tenant_access"] = _serialize_rows(
        db.execute(select(UserTenantAccess).where(UserTenantAccess.tenant_id == tenant_id)).scalars().all(), UserTenantAccess
    )
    payload["tables"]["user_platform_access"] = _serialize_rows(
        db.execute(select(UserPlatformAccess).where(UserPlatformAccess.user_id.in_(user_ids) if user_ids else False)).scalars().all(), UserPlatformAccess
    )
    payload["tables"]["tenant_platform_access"] = _serialize_rows(
        db.execute(select(TenantPlatformAccess).where(TenantPlatformAccess.tenant_id == tenant_id)).scalars().all(), TenantPlatformAccess
    )
    payload["tables"]["transactions"] = _serialize_rows(
        db.execute(select(Transaction).where(Transaction.platform_id.in_(platform_ids) if platform_ids else False)).scalars().all(), Transaction
    )
    payload["tables"]["daily_summaries"] = _serialize_rows(
        db.execute(select(DailySummary).where(DailySummary.platform_id.in_(platform_ids) if platform_ids else False)).scalars().all(), DailySummary
    )
    payload["tables"]["account_snapshots"] = _serialize_rows(db.execute(select(AccountSnapshot)).scalars().all(), AccountSnapshot)
    payload["tables"]["handover_snapshots"] = _serialize_rows(db.execute(select(HandoverSnapshot)).scalars().all(), HandoverSnapshot)
    payload["tables"]["handover_payment_snapshots"] = _serialize_rows(db.execute(select(HandoverPaymentSnapshot)).scalars().all(), HandoverPaymentSnapshot)
    return payload


def _write_server_backup(db: Session, exported_by: str, reason: str):
    payload = _build_backup_payload(db, exported_by)
    payload["meta"]["reason"] = reason
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"accounting-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
    path = BACKUP_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return filename


def _write_tenant_backup(db: Session, exported_by: str, tenant_id: int, reason: str):
    payload = _build_tenant_backup_payload(db, exported_by, tenant_id)
    payload["meta"]["reason"] = reason
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"tenant-{tenant_id}-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
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


@router.delete("/logs")
def clear_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("logs", {UserRole.ADMIN.value})),
):
    count = db.execute(select(func.count(AuditLog.id))).scalar_one()
    db.execute(AuditLog.__table__.delete())
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="clear_audit_logs",
            before_data=f"count={count}",
            after_data="cleared",
        )
    )
    db.commit()
    return {"ok": True, "cleared": count}


@router.get("/operation-logs")
def list_operation_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    username: str | None = Query(default=None),
    method: str | None = Query(default=None),
    path_keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_module("operation.logs", {UserRole.ADMIN.value})),
):
    stmt = select(OperationLog)
    count_stmt = select(func.count(OperationLog.id))
    if username:
        stmt = stmt.where(OperationLog.username == username)
        count_stmt = count_stmt.where(OperationLog.username == username)
    if method:
        stmt = stmt.where(OperationLog.method == method.upper())
        count_stmt = count_stmt.where(OperationLog.method == method.upper())
    if path_keyword:
        stmt = stmt.where(OperationLog.path.like(f"%{path_keyword}%"))
        count_stmt = count_stmt.where(OperationLog.path.like(f"%{path_keyword}%"))
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.order_by(desc(OperationLog.id)).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.delete("/operation-logs")
def clear_operation_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("operation.logs", {UserRole.ADMIN.value})),
):
    count = db.execute(select(func.count(OperationLog.id))).scalar_one()
    db.execute(OperationLog.__table__.delete())
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="clear_operation_logs",
            before_data=f"count={count}",
            after_data="cleared",
        )
    )
    db.commit()
    return {"ok": True, "cleared": count}


@router.get("/charts/profit-by-platform")
def profit_by_platform(
    platform_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.charts")),
):
    allowed = None if current_user.role == UserRole.SUPER_ADMIN.value else get_accessible_platform_ids(db, current_user)
    if allowed == []:
        return []
    rows = db.execute(
        select(Transaction.platform_id, func.sum(Transaction.amount), Transaction.type)
        .where(
            Transaction.deleted_at.is_(None),
            Transaction.platform_id == platform_id if platform_id else True,
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
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
    current_user: User = Depends(require_module("reports.charts")),
):
    allowed = None if current_user.role == UserRole.SUPER_ADMIN.value else get_accessible_platform_ids(db, current_user)
    if allowed == []:
        return []
    stmt = select(DailySummary.bill_date, func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit))
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if platform_id:
        if allowed is not None and platform_id not in allowed:
            return []
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
    if current_user.role == UserRole.SUPER_ADMIN.value:
        payload = _build_backup_payload(db, current_user.username)
        filename = f"accounting-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
    else:
        tenant_access = get_user_tenant_access(db, current_user)
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        payload = _build_tenant_backup_payload(db, current_user.username, tenant_access.tenant_id)
        filename = f"tenant-{tenant_access.tenant_id}-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"

    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/backup/tenant-export")
def export_tenant_backup(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    payload = _build_tenant_backup_payload(db, current_user.username, tenant_id)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"tenant-{tenant_id}-backup-{beijing_now().strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/backup/tenant-restore")
async def restore_tenant_backup(
    tenant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if current_user.role != UserRole.SUPER_ADMIN.value:
        tenant_access = get_user_tenant_access(db, current_user)
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        if tenant_id != tenant_access.tenant_id:
            raise HTTPException(status_code=403, detail="cannot restore other tenant")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="backup file must be json")
    raw = await file.read()
    data = json.loads(raw.decode("utf-8"))
    tables = data.get("tables", {})
    fk_fixes = _sanitize_user_fk_rows(tables)
    restored_counts: dict[str, int] = {}

    platform_rows = db.execute(select(TenantPlatformAccess).where(TenantPlatformAccess.tenant_id == tenant_id)).scalars().all()
    platform_ids = [r.platform_id for r in platform_rows]
    user_rows = db.execute(select(UserTenantAccess).where(UserTenantAccess.tenant_id == tenant_id)).scalars().all()
    user_ids = [r.user_id for r in user_rows]

    if platform_ids:
        db.execute(Transaction.__table__.delete().where(Transaction.platform_id.in_(platform_ids)))
        db.execute(DailySummary.__table__.delete().where(DailySummary.platform_id.in_(platform_ids)))
    if user_ids:
        db.execute(UserPlatformAccess.__table__.delete().where(UserPlatformAccess.user_id.in_(user_ids)))
    db.execute(UserTenantAccess.__table__.delete().where(UserTenantAccess.tenant_id == tenant_id))
    db.execute(TenantPlatformAccess.__table__.delete().where(TenantPlatformAccess.tenant_id == tenant_id))

    restore_pairs = [
        ("platforms", Platform),
        ("users", User),
        ("user_platform_access", UserPlatformAccess),
        ("transactions", Transaction),
        ("daily_summaries", DailySummary),
        ("account_snapshots", AccountSnapshot),
        ("handover_snapshots", HandoverSnapshot),
        ("handover_payment_snapshots", HandoverPaymentSnapshot),
    ]
    for table_name, model in restore_pairs:
        rows = tables.get(table_name, [])
        if rows:
            db.execute(model.__table__.insert().prefix_with("OR REPLACE"), rows)
        restored_counts[table_name] = len(rows)

    user_tenant_rows = tables.get("user_tenant_access", [])
    for row in user_tenant_rows:
        row["tenant_id"] = tenant_id
    if user_tenant_rows:
        db.execute(UserTenantAccess.__table__.insert().prefix_with("OR REPLACE"), user_tenant_rows)
    restored_counts["user_tenant_access"] = len(user_tenant_rows)

    tenant_platform_rows = tables.get("tenant_platform_access", [])
    for row in tenant_platform_rows:
        row["tenant_id"] = tenant_id
    if tenant_platform_rows:
        db.execute(TenantPlatformAccess.__table__.insert().prefix_with("OR REPLACE"), tenant_platform_rows)
    restored_counts["tenant_platform_access"] = len(tenant_platform_rows)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="system",
            action="restore_tenant_backup",
            before_data=None,
            after_data=f"tenant_id={tenant_id},file={file.filename}",
        )
    )
    db.commit()
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "restored_file": file.filename,
        "restored_counts": restored_counts,
        "fk_fixes": fk_fixes,
        "total_rows": int(sum(restored_counts.values())),
    }


@router.get("/health/tenant-consistency")
def tenant_consistency(
    db: Session = Depends(get_db),
    _: User = Depends(require_module("master.tenants", {UserRole.SUPER_ADMIN.value})),
):
    tenant_ids = [r[0] for r in db.execute(select(Tenant.id)).all()]
    invalid_user_access = db.execute(
        select(func.count(UserTenantAccess.id)).where(UserTenantAccess.tenant_id.not_in(tenant_ids) if tenant_ids else True)
    ).scalar_one()
    invalid_platform_access = db.execute(
        select(func.count(TenantPlatformAccess.id)).where(TenantPlatformAccess.tenant_id.not_in(tenant_ids) if tenant_ids else True)
    ).scalar_one()
    users_without_tenant = db.execute(
        select(func.count(User.id))
        .where(User.role != UserRole.SUPER_ADMIN.value)
        .where(~User.id.in_(select(UserTenantAccess.user_id)))
    ).scalar_one()
    return {
        "tenant_count": len(tenant_ids),
        "invalid_user_access": int(invalid_user_access or 0),
        "invalid_platform_access": int(invalid_platform_access or 0),
        "users_without_tenant": int(users_without_tenant or 0),
        "ok": int(invalid_user_access or 0) == 0 and int(invalid_platform_access or 0) == 0 and int(users_without_tenant or 0) == 0,
    }


@router.post("/backup/create")
def create_server_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if current_user.role == UserRole.SUPER_ADMIN.value:
        filename = _write_server_backup(db, current_user.username, "manual_backup")
    else:
        tenant_access = get_user_tenant_access(db, current_user)
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        filename = _write_tenant_backup(db, current_user.username, tenant_access.tenant_id, "manual_tenant_backup")
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
    _: User = Depends(require_module("system.tools", {UserRole.SUPER_ADMIN.value})),
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
    _: User = Depends(require_module("system.tools", {UserRole.SUPER_ADMIN.value})),
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
    _: User = Depends(require_module("system.tools", {UserRole.SUPER_ADMIN.value})),
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
    current_user: User = Depends(require_module("system.tools", {UserRole.SUPER_ADMIN.value})),
):
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="backup file must be json")
    raw = await file.read()
    data = json.loads(raw.decode("utf-8"))
    tables = data.get("tables", {})
    fk_fixes = _sanitize_user_fk_rows(tables)
    restored_counts: dict[str, int] = {}

    for _, model in reversed(BACKUP_TABLES):
        db.execute(model.__table__.delete())
    db.flush()

    for table_name, model in BACKUP_TABLES:
        rows = tables.get(table_name, [])
        if rows:
            db.execute(model.__table__.insert(), rows)
        restored_counts[table_name] = len(rows)

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
    return {
        "ok": True,
        "restored_file": file.filename,
        "restored_counts": restored_counts,
        "fk_fixes": fk_fixes,
        "total_rows": int(sum(restored_counts.values())),
    }


@router.post("/data/delete-before")
def delete_data_before_date(
    before_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if current_user.role == UserRole.SUPER_ADMIN.value:
        backup_filename = _write_server_backup(db, current_user.username, f"delete_before_date:{before_date}")
        allowed_platform_ids = None
    else:
        tenant_access = get_user_tenant_access(db, current_user)
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        backup_filename = _write_tenant_backup(db, current_user.username, tenant_access.tenant_id, f"tenant_delete_before_date:{before_date}")
        allowed_platform_ids = get_accessible_platform_ids(db, current_user)
        if not allowed_platform_ids:
            return {"ok": True, "deleted_transactions": 0, "deleted_daily_summaries": 0, "backup_file": backup_filename}

    now = beijing_now().replace(tzinfo=None)
    tx_rows = db.execute(
        select(Transaction).where(
            Transaction.bill_date < before_date,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed_platform_ids) if allowed_platform_ids is not None else True,
        )
    ).scalars().all()
    for tx in tx_rows:
        tx.deleted_at = now

    daily_delete_stmt = DailySummary.__table__.delete().where(
        DailySummary.bill_date < before_date,
        DailySummary.platform_id.in_(allowed_platform_ids) if allowed_platform_ids is not None else True,
    )
    daily_deleted = db.execute(daily_delete_stmt).rowcount or 0

    if current_user.role == UserRole.SUPER_ADMIN.value:
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
            after_data=f"before_date={before_date},tx={len(tx_rows)},daily={daily_deleted},scope={'all' if allowed_platform_ids is None else 'tenant'}",
        )
    )
    db.commit()
    return {"ok": True, "deleted_transactions": len(tx_rows), "deleted_daily_summaries": int(daily_deleted), "backup_file": backup_filename}


@router.post("/data/delete-by-date")
def delete_data_by_date(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("system.tools", {UserRole.ADMIN.value})),
):
    if current_user.role == UserRole.SUPER_ADMIN.value:
        backup_filename = _write_server_backup(db, current_user.username, f"delete_by_date:{bill_date}")
        allowed_platform_ids = None
    else:
        tenant_access = get_user_tenant_access(db, current_user)
        if tenant_access is None:
            raise HTTPException(status_code=403, detail="User not bound to tenant")
        backup_filename = _write_tenant_backup(db, current_user.username, tenant_access.tenant_id, f"tenant_delete_by_date:{bill_date}")
        allowed_platform_ids = get_accessible_platform_ids(db, current_user)
        if not allowed_platform_ids:
            return {"ok": True, "deleted_transactions": 0, "deleted_daily_summaries": 0, "backup_file": backup_filename}

    now = beijing_now().replace(tzinfo=None)
    tx_rows = db.execute(
        select(Transaction).where(
            Transaction.bill_date == bill_date,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed_platform_ids) if allowed_platform_ids is not None else True,
        )
    ).scalars().all()
    for tx in tx_rows:
        tx.deleted_at = now

    daily_delete_stmt = DailySummary.__table__.delete().where(
        DailySummary.bill_date == bill_date,
        DailySummary.platform_id.in_(allowed_platform_ids) if allowed_platform_ids is not None else True,
    )
    daily_deleted = db.execute(daily_delete_stmt).rowcount or 0

    if current_user.role == UserRole.SUPER_ADMIN.value:
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
            after_data=f"bill_date={bill_date},tx={len(tx_rows)},daily={daily_deleted},scope={'all' if allowed_platform_ids is None else 'tenant'}",
        )
    )
    db.commit()
    return {"ok": True, "deleted_transactions": len(tx_rows), "deleted_daily_summaries": int(daily_deleted), "backup_file": backup_filename}
