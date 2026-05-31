from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_accessible_platform_ids, get_current_tenant_id, require_module, require_roles
from app.models.entities import (
    AuditLog,
    Category,
    DailySummary,
    HandoverPaymentSnapshot,
    HandoverSnapshot,
    PaymentMethod,
    Platform,
    Tenant,
    TenantPlatformAccess,
    Transaction,
)
from app.models.entities import User
from app.models.enums import UserRole
from app.schemas.common import DailySummaryOut, MonthlySummaryOut
from app.services.month_lock import assert_month_not_locked
from app.services.summary import rebuild_daily_summary


router = APIRouter(prefix="/reports", tags=["reports"])


def _scoped_platform_ids(db: Session, current_user: User) -> list[int] | None:
    if current_user.role == UserRole.SUPER_ADMIN.value:
        return None
    return get_accessible_platform_ids(db, current_user)


def _tenant_select(model, tenant_id: int | None):
    stmt = select(model)
    if tenant_id is not None:
        stmt = stmt.where(model.tenant_id == tenant_id)
    return stmt


def build_expense_items(db: Session, rows: list[tuple[int | None, str | None, float]], tenant_id: int | None) -> list[dict]:
    category_map = {c.id: c.name for c in db.execute(_tenant_select(Category, tenant_id)).scalars().all()}
    items = []
    for category_id_val, biz_type_label_val, amount_sum in rows:
        if category_id_val is None:
            name = (biz_type_label_val or "-").strip() or "-"
        else:
            name = category_map.get(category_id_val, f"项目#{category_id_val}")
        items.append({"name": name, "amount": float(amount_sum or 0)})
    return items


def format_expense_items(items: list[dict]) -> str:
    if not items:
        return "-"
    return "，".join(f"{it['name']}:{it['amount']:.2f}" for it in items)


@router.get("/super/tenant-summary")
def super_tenant_summary(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    tenant_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value})),
):
    stmt = (
        select(
            Tenant.id,
            Tenant.name,
            func.sum(DailySummary.total_income),
            func.sum(DailySummary.total_expense),
            func.sum(DailySummary.net_profit),
        )
        .select_from(Tenant)
        .join(TenantPlatformAccess, TenantPlatformAccess.tenant_id == Tenant.id)
        .join(DailySummary, DailySummary.platform_id == TenantPlatformAccess.platform_id)
    )
    if start_date:
        stmt = stmt.where(DailySummary.bill_date >= start_date)
    if end_date:
        stmt = stmt.where(DailySummary.bill_date <= end_date)
    if tenant_id:
        stmt = stmt.where(Tenant.id == tenant_id)
    rows = db.execute(stmt.group_by(Tenant.id, Tenant.name).order_by(Tenant.id.asc())).all()
    items = [
        {
            "tenant_id": r[0],
            "tenant_name": r[1],
            "income": float(r[2] or 0),
            "expense": float(r[3] or 0),
            "net": float(r[4] or 0),
        }
        for r in rows
    ]
    total_income = sum(x["income"] for x in items)
    total_expense = sum(x["expense"] for x in items)
    total_net = sum(x["net"] for x in items)
    return {
        "items": items,
        "summary": {"income": total_income, "expense": total_expense, "net": total_net},
        "start_date": start_date,
        "end_date": end_date,
        "tenant_id": tenant_id,
    }


@router.get("/super/tenant-account-balances")
def super_tenant_account_balances(
    bill_date: str,
    tenant_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value})),
):
    tenants_stmt = select(Tenant).order_by(Tenant.id.asc())
    if tenant_id:
        tenants_stmt = tenants_stmt.where(Tenant.id == tenant_id)
    tenants = db.execute(tenants_stmt).scalars().all()
    items = []
    grand_total = 0.0
    for t in tenants:
        platform_ids = [
            r[0] for r in db.execute(select(TenantPlatformAccess.platform_id).where(TenantPlatformAccess.tenant_id == t.id)).all()
        ]
        method_ids = []
        if platform_ids:
            method_ids = [
                r[0]
                for r in db.execute(
                    select(Transaction.payment_method_id)
                    .where(
                        Transaction.platform_id.in_(platform_ids),
                        Transaction.bill_date <= bill_date,
                        Transaction.deleted_at.is_(None),
                        Transaction.payment_method_id.is_not(None),
                    )
                    .group_by(Transaction.payment_method_id)
                    .order_by(Transaction.payment_method_id.asc())
                ).all()
            ]
        methods = (
            db.execute(select(PaymentMethod).where(PaymentMethod.id.in_(method_ids))).scalars().all() if method_ids else []
        )
        account_items = []
        tenant_total = 0.0
        for pm in methods:
            balance = float(pm.initial_balance or 0)
            if platform_ids:
                rows = db.execute(
                    select(func.sum(Transaction.amount), Transaction.type)
                    .where(
                        Transaction.payment_method_id == pm.id,
                        Transaction.bill_date <= bill_date,
                        Transaction.deleted_at.is_(None),
                        Transaction.platform_id.in_(platform_ids),
                    )
                    .group_by(Transaction.type)
                ).all()
                for amount_sum, tx_type in rows:
                    if tx_type == "income":
                        balance += float(amount_sum or 0)
                    elif tx_type == "expense":
                        balance -= float(amount_sum or 0)
            account_items.append(
                {
                    "payment_method_id": pm.id,
                    "payment_method_name": pm.name,
                    "channel_kind": pm.channel_kind,
                    "balance": balance,
                }
            )
            tenant_total += balance

        items.append(
            {
                "tenant_id": t.id,
                "tenant_name": t.name,
                "accounts": account_items,
                "tenant_total": tenant_total,
            }
        )
        grand_total += tenant_total

    return {
        "bill_date": bill_date,
        "tenant_id": tenant_id,
        "items": items,
        "grand_total": grand_total,
    }


@router.get("/daily", response_model=list[DailySummaryOut])
def list_daily_summaries(
    bill_date: str | None = Query(default=None),
    shift_id: int | None = Query(default=None),
    platform_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return []
    stmt = select(DailySummary)
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if bill_date:
        stmt = stmt.where(DailySummary.bill_date == bill_date)
    if shift_id:
        stmt = stmt.where(DailySummary.shift_id == shift_id)
    if platform_id:
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    rows = db.execute(stmt.order_by(DailySummary.bill_date.desc())).scalars().all()
    return rows


@router.get("/monthly", response_model=MonthlySummaryOut)
def monthly_summary(
    year: int,
    month: int,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.monthly")),
):
    tenant_id = get_current_tenant_id(db, current_user)
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return MonthlySummaryOut(month=f"{year:04d}-{month:02d}", total_income=0, total_expense=0, net_profit=0)
    stmt = select(
        func.sum(DailySummary.total_income),
        func.sum(DailySummary.total_expense),
        func.sum(DailySummary.net_profit),
    ).where(
        extract("year", DailySummary.bill_date) == year,
        extract("month", DailySummary.bill_date) == month,
    )
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if platform_id:
        if allowed is not None and platform_id not in allowed:
            return MonthlySummaryOut(month=f"{year:04d}-{month:02d}", total_income=0, total_expense=0, net_profit=0)
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    row = db.execute(stmt).first()
    data = {
        "total_income": row[0] or 0,
        "total_expense": row[1] or 0,
        "net_profit": row[2] or 0,
    }
    return MonthlySummaryOut(month=f"{year:04d}-{month:02d}", **data)


@router.get("/monthly/detail")
def monthly_detail(
    year: int,
    month: int,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.monthly")),
):
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return {"month": f"{year:04d}-{month:02d}", "platform_id": platform_id, "platform_name": None, "summary": {"income": 0.0, "expense": 0.0, "net": 0.0}, "expense_items": [], "account_balances": [], "platform_summaries": []}
    summary_stmt = select(
        func.sum(DailySummary.total_income),
        func.sum(DailySummary.total_expense),
        func.sum(DailySummary.net_profit),
    ).where(
        extract("year", DailySummary.bill_date) == year,
        extract("month", DailySummary.bill_date) == month,
    )
    if allowed is not None:
        summary_stmt = summary_stmt.where(DailySummary.platform_id.in_(allowed))
    if platform_id:
        if allowed is not None and platform_id not in allowed:
            return {"month": f"{year:04d}-{month:02d}", "platform_id": platform_id, "platform_name": None, "summary": {"income": 0.0, "expense": 0.0, "net": 0.0}, "expense_items": [], "account_balances": [], "platform_summaries": []}
        summary_stmt = summary_stmt.where(DailySummary.platform_id == platform_id)
    summary_row = db.execute(summary_stmt).first()
    summary = {
        "total_income": summary_row[0] or 0,
        "total_expense": summary_row[1] or 0,
        "net_profit": summary_row[2] or 0,
    }

    expense_stmt = select(Transaction.category_id, func.sum(Transaction.amount)).where(
        extract("year", Transaction.bill_date) == year,
        extract("month", Transaction.bill_date) == month,
        Transaction.type == "expense",
        Transaction.deleted_at.is_(None),
        Transaction.category_id.is_not(None),
    )
    if allowed is not None:
        expense_stmt = expense_stmt.where(Transaction.platform_id.in_(allowed))
    if platform_id:
        expense_stmt = expense_stmt.where(Transaction.platform_id == platform_id)
    expense_rows = db.execute(expense_stmt.group_by(Transaction.category_id)).all()
    category_map = {c.id: c.name for c in db.execute(_tenant_select(Category, tenant_id)).scalars().all()}
    expense_items = [
        {
            "category_id": r[0],
            "category_name": category_map.get(r[0], f"项目#{r[0]}"),
            "amount": float(r[1] or 0),
        }
        for r in expense_rows
    ]

    month_start = date(year, month, 1)
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    methods = db.execute(_tenant_select(PaymentMethod, tenant_id).where(PaymentMethod.status == "enabled")).scalars().all()
    account_balances = []
    for pm in methods:
        before_rows = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date < month_start,
                Transaction.deleted_at.is_(None),
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
                Transaction.platform_id == platform_id if platform_id else True,
            )
            .group_by(Transaction.type)
        ).all()
        opening = float(pm.initial_balance or 0)
        for amount_sum, tx_type in before_rows:
            if tx_type == "income":
                opening += float(amount_sum or 0)
            elif tx_type == "expense":
                opening -= float(amount_sum or 0)

        month_rows = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date >= month_start,
                Transaction.bill_date < next_month_start,
                Transaction.deleted_at.is_(None),
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
                Transaction.platform_id == platform_id if platform_id else True,
            )
            .group_by(Transaction.type)
        ).all()
        income = 0.0
        expense = 0.0
        for amount_sum, tx_type in month_rows:
            if tx_type == "income":
                income += float(amount_sum or 0)
            elif tx_type == "expense":
                expense += float(amount_sum or 0)
        closing = opening + income - expense
        account_balances.append(
            {
                "payment_method_id": pm.id,
                "payment_method_name": pm.name,
                "channel_kind": pm.channel_kind,
                "opening_balance": opening,
                "income": income,
                "expense": expense,
                "closing_balance": closing,
            }
        )

    platform_rows_stmt = select(
        DailySummary.platform_id,
        func.sum(DailySummary.total_income),
        func.sum(DailySummary.total_expense),
        func.sum(DailySummary.net_profit),
    ).where(
        extract("year", DailySummary.bill_date) == year,
        extract("month", DailySummary.bill_date) == month,
    )
    if allowed is not None:
        platform_rows_stmt = platform_rows_stmt.where(DailySummary.platform_id.in_(allowed))
    if platform_id:
        platform_rows_stmt = platform_rows_stmt.where(DailySummary.platform_id == platform_id)
    platform_rows = db.execute(platform_rows_stmt.group_by(DailySummary.platform_id)).all()
    platform_name_stmt = select(Platform.id, Platform.name)
    if tenant_id is not None:
        platform_name_stmt = platform_name_stmt.where(Platform.tenant_id == tenant_id)
    platform_name_map = {r[0]: r[1] for r in db.execute(platform_name_stmt).all()}
    platform_summaries = [
        {
            "platform_id": r[0],
            "platform_name": platform_name_map.get(r[0], f"平台#{r[0]}"),
            "income": float(r[1] or 0),
            "expense": float(r[2] or 0),
            "net": float(r[3] or 0),
        }
        for r in platform_rows
    ]

    return {
        "month": f"{year:04d}-{month:02d}",
        "platform_id": platform_id,
        "platform_name": None if not platform_id else db.execute(select(Platform.name).where(Platform.id == platform_id, Platform.tenant_id == tenant_id) if tenant_id is not None else select(Platform.name).where(Platform.id == platform_id)).scalar_one_or_none(),
        "summary": {
            "income": float(summary["total_income"]),
            "expense": float(summary["total_expense"]),
            "net": float(summary["net_profit"]),
        },
        "expense_items": expense_items,
        "account_balances": account_balances,
        "platform_summaries": platform_summaries,
    }


@router.post("/monthly/rebuild")
def rebuild_monthly(year: int, month: int, db: Session = Depends(get_db), current_user: User = Depends(require_module("reports.monthly", {UserRole.ADMIN.value}))):
    check_date = date(year, month, 1)
    try:
        assert_month_not_locked(db, check_date)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc

    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return {"rebuild_groups": 0}
    rows = db.execute(
        select(Transaction.bill_date, Transaction.shift_id, Transaction.platform_id)
        .where(
            extract("year", Transaction.bill_date) == year,
            extract("month", Transaction.bill_date) == month,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
        )
        .group_by(Transaction.bill_date, Transaction.shift_id, Transaction.platform_id)
    ).all()
    for row in rows:
        rebuild_daily_summary(db, row.bill_date, row.shift_id, row.platform_id)
    db.add(AuditLog(user_id=current_user.id, module="reports", action="rebuild_monthly", after_data=f"month={year:04d}-{month:02d},groups={len(rows)}"))
    db.commit()
    return {"rebuild_groups": len(rows)}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_module("dashboard"))):
    today = date.today()
    month_start = today.replace(day=1)
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return {"today": {"income": 0.0, "expense": 0.0, "net": 0.0}, "month": {"income": 0.0, "expense": 0.0, "net": 0.0}, "trend7": []}
    today_data = db.execute(
        select(
            func.sum(DailySummary.total_income),
            func.sum(DailySummary.total_expense),
            func.sum(DailySummary.net_profit),
        ).where(DailySummary.bill_date == today, DailySummary.platform_id.in_(allowed) if allowed is not None else True)
    ).first()
    month_data = db.execute(
        select(
            func.sum(DailySummary.total_income),
            func.sum(DailySummary.total_expense),
            func.sum(DailySummary.net_profit),
        ).where(DailySummary.bill_date >= month_start, DailySummary.bill_date <= today, DailySummary.platform_id.in_(allowed) if allowed is not None else True)
    ).first()

    trend_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    trend = []
    for d in trend_days:
        row = db.execute(
            select(
                func.sum(DailySummary.total_income),
                func.sum(DailySummary.total_expense),
                func.sum(DailySummary.net_profit),
            ).where(DailySummary.bill_date == d, DailySummary.platform_id.in_(allowed) if allowed is not None else True)
        ).first()
        trend.append(
            {
                "date": d.isoformat(),
                "income": float(row[0] or 0),
                "expense": float(row[1] or 0),
                "net": float(row[2] or 0),
            }
        )

    return {
        "today": {
            "income": float(today_data[0] or 0),
            "expense": float(today_data[1] or 0),
            "net": float(today_data[2] or 0),
        },
        "month": {
            "income": float(month_data[0] or 0),
            "expense": float(month_data[1] or 0),
            "net": float(month_data[2] or 0),
        },
        "trend7": trend,
    }


@router.get("/query")
def report_query(
    start_date: str,
    end_date: str,
    shift_id: int | None = None,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    tenant_id = get_current_tenant_id(db, current_user)
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return {"items": [], "summary": {"income": 0.0, "expense": 0.0, "net": 0.0}, "platform_summaries": [], "expense_items": [], "start_date": start_date, "end_date": end_date}
    stmt = select(DailySummary).where(DailySummary.bill_date >= start_date, DailySummary.bill_date <= end_date)
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if shift_id:
        stmt = stmt.where(DailySummary.shift_id == shift_id)
    if platform_id:
        if allowed is not None and platform_id not in allowed:
            return {"items": [], "summary": {"income": 0.0, "expense": 0.0, "net": 0.0}, "platform_summaries": [], "expense_items": [], "start_date": start_date, "end_date": end_date}
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    rows = db.execute(stmt.order_by(DailySummary.bill_date.asc(), DailySummary.shift_id.asc(), DailySummary.platform_id.asc())).scalars().all()

    total_income = sum(float(r.total_income or 0) for r in rows)
    total_expense = sum(float(r.total_expense or 0) for r in rows)
    total_net = sum(float(r.net_profit or 0) for r in rows)

    category_map = {c.id: c.name for c in db.execute(_tenant_select(Category, tenant_id)).scalars().all()}

    expense_stmt = select(Transaction.category_id, func.sum(Transaction.amount)).where(
        Transaction.bill_date >= start_date,
        Transaction.bill_date <= end_date,
        Transaction.type == "expense",
        Transaction.deleted_at.is_(None),
    )
    if shift_id:
        expense_stmt = expense_stmt.where(Transaction.shift_id == shift_id)
    if allowed is not None:
        expense_stmt = expense_stmt.where(Transaction.platform_id.in_(allowed))
    if platform_id:
        expense_stmt = expense_stmt.where(Transaction.platform_id == platform_id)
    expense_rows = db.execute(expense_stmt.group_by(Transaction.category_id)).all()
    expense_items = [
        {
            "category_id": row[0],
            "category_name": "-" if row[0] is None else category_map.get(row[0], f"项目#{row[0]}"),
            "amount": float(row[1] or 0),
        }
        for row in expense_rows
    ]

    row_expense_stmt = select(
        Transaction.bill_date,
        Transaction.shift_id,
        Transaction.platform_id,
        Transaction.category_id,
        Transaction.biz_type_label,
        func.sum(Transaction.amount),
    ).where(
        Transaction.bill_date >= start_date,
        Transaction.bill_date <= end_date,
        Transaction.type == "expense",
        Transaction.deleted_at.is_(None),
    )
    if shift_id:
        row_expense_stmt = row_expense_stmt.where(Transaction.shift_id == shift_id)
    if allowed is not None:
        row_expense_stmt = row_expense_stmt.where(Transaction.platform_id.in_(allowed))
    if platform_id:
        row_expense_stmt = row_expense_stmt.where(Transaction.platform_id == platform_id)
    row_expense_rows = db.execute(
        row_expense_stmt.group_by(
            Transaction.bill_date,
            Transaction.shift_id,
            Transaction.platform_id,
            Transaction.category_id,
            Transaction.biz_type_label,
        )
    ).all()

    expense_detail_map: dict[tuple[str, int, int], list[str]] = {}
    for bill_date_val, shift_val, platform_val, category_id_val, biz_type_label_val, amount_sum in row_expense_rows:
        key = (bill_date_val.isoformat(), int(shift_val), int(platform_val))
        if category_id_val is None:
            item_name = (biz_type_label_val or "-").strip() or "-"
        else:
            item_name = category_map.get(category_id_val, f"项目#{category_id_val}")
        detail = f"{item_name}:{float(amount_sum or 0):.2f}"
        if key not in expense_detail_map:
            expense_detail_map[key] = []
        expense_detail_map[key].append(detail)

    items = []
    for r in rows:
        key = (r.bill_date.isoformat(), int(r.shift_id), int(r.platform_id))
        details = expense_detail_map.get(key, [])
        if details:
            expense_display = "，".join(details)
        else:
            expense_display = "-"

        items.append(
            {
                "bill_date": r.bill_date,
                "shift_id": r.shift_id,
                "platform_id": r.platform_id,
                "total_income": float(r.total_income or 0),
                "total_expense": float(r.total_expense or 0),
                "net_profit": float(r.net_profit or 0),
                "expense_display": expense_display,
            }
        )

    platform_summary_stmt = select(
        DailySummary.platform_id,
        func.sum(DailySummary.total_income),
        func.sum(DailySummary.total_expense),
        func.sum(DailySummary.net_profit),
    ).where(DailySummary.bill_date >= start_date, DailySummary.bill_date <= end_date)
    if allowed is not None:
        platform_summary_stmt = platform_summary_stmt.where(DailySummary.platform_id.in_(allowed))
    if shift_id:
        platform_summary_stmt = platform_summary_stmt.where(DailySummary.shift_id == shift_id)
    if platform_id:
        platform_summary_stmt = platform_summary_stmt.where(DailySummary.platform_id == platform_id)
    platform_summary_rows = db.execute(platform_summary_stmt.group_by(DailySummary.platform_id)).all()
    platform_name_stmt = select(Platform.id, Platform.name)
    if tenant_id is not None:
        platform_name_stmt = platform_name_stmt.where(Platform.tenant_id == tenant_id)
    platform_name_map = {r[0]: r[1] for r in db.execute(platform_name_stmt).all()}
    platform_summaries = [
        {
            "platform_id": r[0],
            "platform_name": platform_name_map.get(r[0], f"平台#{r[0]}"),
            "income": float(r[1] or 0),
            "expense": float(r[2] or 0),
            "net": float(r[3] or 0),
        }
        for r in platform_summary_rows
    ]

    return {
        "items": items,
        "summary": {"income": total_income, "expense": total_expense, "net": total_net},
        "platform_summaries": platform_summaries,
        "expense_items": expense_items,
        "start_date": start_date,
        "end_date": end_date,
    }


def _payment_balances_core(
    bill_date: str,
    tenant_id: int | None,
    allowed: list[int] | None,
    shift_id: int | None = None,
    payment_method_id: int | None = None,
):
    if allowed == []:
        return []
    stmt_methods = _tenant_select(PaymentMethod, tenant_id).where(PaymentMethod.status == "enabled")
    if payment_method_id:
        stmt_methods = stmt_methods.where(PaymentMethod.id == payment_method_id)
    methods = db.execute(stmt_methods).scalars().all()
    result = []
    for pm in methods:
        before_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date < bill_date,
                Transaction.deleted_at.is_(None),
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
            )
            .group_by(Transaction.type)
        ).all()
        opening = float(pm.initial_balance or 0)
        for amount_sum, tx_type in before_row:
            if tx_type == "income":
                opening += float(amount_sum or 0)
            elif tx_type == "expense":
                opening -= float(amount_sum or 0)

        today_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date == bill_date,
                Transaction.deleted_at.is_(None),
                Transaction.shift_id == shift_id if shift_id else True,
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
            )
            .group_by(Transaction.type)
        ).all()
        recharge = 0.0
        payout = 0.0
        for amount_sum, tx_type in today_row:
            if tx_type == "income":
                recharge += float(amount_sum or 0)
            elif tx_type == "expense":
                payout += float(amount_sum or 0)

        expense_detail_rows = db.execute(
            select(Transaction.category_id, Transaction.biz_type_label, func.sum(Transaction.amount))
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date == bill_date,
                Transaction.deleted_at.is_(None),
                Transaction.type == "expense",
                Transaction.shift_id == shift_id if shift_id else True,
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
            )
            .group_by(Transaction.category_id, Transaction.biz_type_label)
        ).all()
        payout_items = build_expense_items(db, expense_detail_rows, tenant_id)

        closing = opening + recharge - payout
        result.append(
            {
                "payment_method_id": pm.id,
                "payment_method_name": pm.name,
                "channel_kind": pm.channel_kind,
                "opening_balance": opening,
                "recharge": recharge,
                "payout": payout,
                "payout_display": format_expense_items(payout_items),
                "payout_items": payout_items,
                "closing_balance": closing,
            }
        )
    return result


@router.get("/payment-balances")
def payment_balances(
    bill_date: str,
    shift_id: int | None = None,
    payment_method_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.balances")),
):
    tenant_id = get_current_tenant_id(db, current_user)
    allowed = _scoped_platform_ids(db, current_user)
    return _payment_balances_core(
        bill_date=bill_date,
        tenant_id=tenant_id,
        allowed=allowed,
        shift_id=shift_id,
        payment_method_id=payment_method_id,
        db=db,
    )


@router.get("/handover")
def handover_report(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    tenant_id = get_current_tenant_id(db, current_user)
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        return {"bill_date": bill_date, "shifts": [], "payment_balances": []}
    shift_rows = db.execute(
        select(DailySummary.shift_id, func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit))
        .where(DailySummary.bill_date == bill_date, DailySummary.platform_id.in_(allowed) if allowed is not None else True)
        .group_by(DailySummary.shift_id)
        .order_by(DailySummary.shift_id.asc())
    ).all()
    shift_expense_rows = db.execute(
        select(Transaction.shift_id, Transaction.category_id, Transaction.biz_type_label, func.sum(Transaction.amount))
        .where(
            Transaction.bill_date == bill_date,
            Transaction.type == "expense",
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
        )
        .group_by(Transaction.shift_id, Transaction.category_id, Transaction.biz_type_label)
    ).all()
    shift_expense_map = {}
    by_shift = {}
    for shift_id_val, category_id_val, biz_type_label_val, amount_sum in shift_expense_rows:
        by_shift.setdefault(int(shift_id_val), []).append((category_id_val, biz_type_label_val, float(amount_sum or 0)))
    for sid, rows in by_shift.items():
        items = build_expense_items(db, rows, tenant_id)
        shift_expense_map[sid] = format_expense_items(items)

    shifts = []
    for r in shift_rows:
        sid = int(r[0])
        shifts.append(
            {
                "shift_id": sid,
                "recharge": float(r[1] or 0),
                "expense": float(r[2] or 0),
                "expense_display": shift_expense_map.get(sid, "-"),
                "turnover": float(r[3] or 0),
            }
        )
    balances = _payment_balances_core(bill_date=bill_date, tenant_id=tenant_id, allowed=allowed, db=db)
    return {"bill_date": bill_date, "shifts": shifts, "payment_balances": balances}


@router.post("/handover/confirm")
def confirm_handover(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query", {UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    report = handover_report(bill_date=bill_date, db=db, _=None)

    old_rows = db.execute(select(HandoverSnapshot).where(HandoverSnapshot.bill_date == bill_date)).scalars().all()
    for old in old_rows:
        db.execute(
            HandoverPaymentSnapshot.__table__.delete().where(HandoverPaymentSnapshot.handover_id == old.id)
        )
        db.delete(old)
    db.flush()

    created = 0
    for shift in report["shifts"]:
        row = HandoverSnapshot(
            bill_date=bill_date,
            shift_id=shift["shift_id"],
            total_income=shift["recharge"],
            total_expense=shift["expense"],
            turnover=shift["turnover"],
            confirmed_by=current_user.id,
        )
        db.add(row)
        db.flush()
        for pm in report["payment_balances"]:
            db.add(
                HandoverPaymentSnapshot(
                    handover_id=row.id,
                    payment_method_id=pm["payment_method_id"],
                    opening_balance=pm["opening_balance"],
                    recharge=pm["recharge"],
                    payout=pm["payout"],
                    closing_balance=pm["closing_balance"],
                )
            )
        created += 1

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="handover",
            action="confirm",
            before_data=None,
            after_data=f"date={bill_date},shifts={created}",
        )
    )
    db.commit()
    return {"ok": True, "confirmed_shifts": created}


@router.get("/handover/confirmed")
def get_confirmed_handover(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    allowed = _scoped_platform_ids(db, current_user)
    shifts = db.execute(select(HandoverSnapshot).where(HandoverSnapshot.bill_date == bill_date).order_by(HandoverSnapshot.shift_id.asc())).scalars().all()
    if not shifts:
        return {"confirmed": False, "bill_date": bill_date, "shifts": [], "payment_balances": []}

    if allowed is not None:
        shift_ids = [s.shift_id for s in shifts]
        check = db.execute(
            select(DailySummary.shift_id)
            .where(
                DailySummary.bill_date == bill_date,
                DailySummary.shift_id.in_(shift_ids),
                DailySummary.platform_id.in_(allowed),
            )
            .group_by(DailySummary.shift_id)
        ).all()
        allowed_shift_ids = {int(r[0]) for r in check}
        shifts = [s for s in shifts if int(s.shift_id) in allowed_shift_ids]
        if not shifts:
            return {"confirmed": False, "bill_date": bill_date, "shifts": [], "payment_balances": []}

    pm_rows = db.execute(
        select(HandoverPaymentSnapshot)
        .where(HandoverPaymentSnapshot.handover_id == shifts[0].id)
        .order_by(HandoverPaymentSnapshot.payment_method_id.asc())
    ).scalars().all()
    return {
        "confirmed": True,
        "bill_date": bill_date,
        "confirmed_at": shifts[0].confirmed_at,
        "shifts": shifts,
        "payment_balances": pm_rows,
    }
