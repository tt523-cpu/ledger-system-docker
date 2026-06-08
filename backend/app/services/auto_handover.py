from __future__ import annotations

import threading
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time_utils import beijing_now
from app.models.entities import (
    AuditLog,
    DailySummary,
    HandoverPaymentSnapshot,
    HandoverSnapshot,
    Shift,
    TenantPlatformAccess,
    Transaction,
    User,
)
from app.models.enums import GenericStatus, UserRole
from app.api.reports import _payment_balances_core


_stop_event = threading.Event()
_worker: threading.Thread | None = None


def _find_auto_user_id(db: Session) -> int | None:
    row = db.execute(
        select(User.id)
        .where(
            User.status == GenericStatus.ENABLED.value,
            User.role.in_([UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value]),
        )
        .order_by(User.role.desc(), User.id.asc())
        .limit(1)
    ).first()
    return int(row[0]) if row else None


def _is_shift_due(now_time: time, shift: Shift) -> bool:
    if shift.end_time is None:
        return False
    return now_time >= shift.end_time


def _tenant_platform_ids(db: Session, tenant_id: int) -> list[int]:
    return [
        int(r[0])
        for r in db.execute(
            select(TenantPlatformAccess.platform_id).where(TenantPlatformAccess.tenant_id == tenant_id)
        ).all()
    ]


def _shift_summary(db: Session, bill_date: date, shift_id: int, platform_ids: list[int]) -> tuple[float, float, float]:
    if not platform_ids:
        return 0.0, 0.0, 0.0
    row = db.execute(
        select(
            func.sum(DailySummary.total_income),
            func.sum(DailySummary.total_expense),
            func.sum(DailySummary.net_profit),
        ).where(
            DailySummary.bill_date == bill_date,
            DailySummary.shift_id == shift_id,
            DailySummary.platform_id.in_(platform_ids),
        )
    ).first()
    return float(row[0] or 0), float(row[1] or 0), float(row[2] or 0)


def _has_shift_transactions(db: Session, bill_date: date, shift_id: int, platform_ids: list[int]) -> bool:
    if not platform_ids:
        return False
    return (
        db.execute(
            select(Transaction.id)
            .where(
                Transaction.bill_date == bill_date,
                Transaction.shift_id == shift_id,
                Transaction.platform_id.in_(platform_ids),
                Transaction.deleted_at.is_(None),
            )
            .limit(1)
        ).first()
        is not None
    )


def _create_shift_handover(db: Session, bill_date: date, shift: Shift, confirmed_by: int) -> bool:
    exists = db.execute(
        select(HandoverSnapshot.id)
        .where(HandoverSnapshot.bill_date == bill_date, HandoverSnapshot.shift_id == shift.id)
        .limit(1)
    ).first()
    if exists:
        return False

    platform_ids = _tenant_platform_ids(db, shift.tenant_id)
    if not _has_shift_transactions(db, bill_date, shift.id, platform_ids):
        return False

    income, expense, turnover = _shift_summary(db, bill_date, shift.id, platform_ids)
    snapshot = HandoverSnapshot(
        bill_date=bill_date,
        shift_id=shift.id,
        total_income=income,
        total_expense=expense,
        turnover=turnover,
        confirmed_by=confirmed_by,
    )
    db.add(snapshot)
    db.flush()

    balances = _payment_balances_core(
        bill_date=bill_date.isoformat(),
        tenant_id=shift.tenant_id,
        allowed=platform_ids,
        db=db,
        shift_id=shift.id,
    )
    for pm in balances:
        db.add(
            HandoverPaymentSnapshot(
                handover_id=snapshot.id,
                payment_method_id=pm["payment_method_id"],
                opening_balance=pm["opening_balance"],
                recharge=pm["recharge"],
                payout=pm["payout"],
                closing_balance=pm["closing_balance"],
            )
        )

    db.add(
        AuditLog(
            user_id=confirmed_by,
            module="handover",
            action="auto_confirm",
            before_data=None,
            after_data=f"date={bill_date.isoformat()},shift_id={shift.id}",
        )
    )
    return True


def run_auto_handover_once() -> int:
    now = beijing_now()
    bill_date = now.date()
    db = SessionLocal()
    try:
        auto_user_id = _find_auto_user_id(db)
        if auto_user_id is None:
            return 0

        shifts = db.execute(
            select(Shift)
            .where(Shift.status == GenericStatus.ENABLED.value, Shift.end_time.is_not(None))
            .order_by(Shift.tenant_id.asc(), Shift.sort_order.asc(), Shift.id.asc())
        ).scalars().all()

        created = 0
        for shift in shifts:
            if _is_shift_due(now.time(), shift) and _create_shift_handover(db, bill_date, shift, auto_user_id):
                created += 1
        if created:
            db.commit()
        else:
            db.rollback()
        return created
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _worker_loop():
    while not _stop_event.wait(settings.auto_handover_interval_seconds):
        try:
            run_auto_handover_once()
        except Exception:
            # The next interval will retry; avoid taking down the API process.
            pass


def start_auto_handover_worker():
    global _worker
    if not settings.auto_handover_enabled or _worker is not None:
        return
    _stop_event.clear()
    _worker = threading.Thread(target=_worker_loop, name="auto-handover", daemon=True)
    _worker.start()


def stop_auto_handover_worker():
    global _worker
    if _worker is None:
        return
    _stop_event.set()
    _worker.join(timeout=5)
    _worker = None
