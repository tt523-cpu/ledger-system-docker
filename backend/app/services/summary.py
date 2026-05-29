from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models.entities import DailySummary, Transaction
from app.models.enums import TransactionType


def rebuild_daily_summary(db: Session, bill_date: date, shift_id: int, platform_id: int) -> DailySummary:
    stmt = (
        select(
            Transaction.type,
            func.sum(Transaction.amount).label("amount_sum"),
        )
        .where(
            Transaction.bill_date == bill_date,
            Transaction.shift_id == shift_id,
            Transaction.platform_id == platform_id,
            Transaction.deleted_at.is_(None),
        )
        .group_by(Transaction.type)
    )

    income = Decimal("0.00")
    expense = Decimal("0.00")
    people = 0
    for row in db.execute(stmt):
        amount = row.amount_sum or Decimal("0.00")
        if row.type == TransactionType.INCOME.value:
            income += amount
        elif row.type == TransactionType.EXPENSE.value:
            expense += amount

    net = income - expense

    existing = db.execute(
        select(DailySummary).where(
            DailySummary.bill_date == bill_date,
            DailySummary.shift_id == shift_id,
            DailySummary.platform_id == platform_id,
        )
    ).scalar_one_or_none()

    if income == Decimal("0.00") and expense == Decimal("0.00"):
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    if existing is None:
        existing = DailySummary(
            bill_date=bill_date,
            shift_id=shift_id,
            platform_id=platform_id,
            total_income=income,
            total_expense=expense,
            net_profit=net,
            total_people=people,
        )
        db.add(existing)
    else:
        existing.total_income = income
        existing.total_expense = expense
        existing.net_profit = net
        existing.total_people = people

    db.flush()
    return existing


def get_monthly_summary(db: Session, year: int, month: int):
    stmt = select(
        func.sum(DailySummary.total_income),
        func.sum(DailySummary.total_expense),
        func.sum(DailySummary.net_profit),
    ).where(
        extract("year", DailySummary.bill_date) == year,
        extract("month", DailySummary.bill_date) == month,
    )

    row = db.execute(stmt).first()
    return {
        "total_income": row[0] or Decimal("0.00"),
        "total_expense": row[1] or Decimal("0.00"),
        "net_profit": row[2] or Decimal("0.00"),
    }


def rebuild_daily_summary_for_date(db: Session, bill_date: date):
    db.execute(DailySummary.__table__.delete().where(DailySummary.bill_date == bill_date))
    groups = db.execute(
        select(Transaction.shift_id, Transaction.platform_id)
        .where(Transaction.bill_date == bill_date, Transaction.deleted_at.is_(None))
        .group_by(Transaction.shift_id, Transaction.platform_id)
    ).all()
    for shift_id, platform_id in groups:
        rebuild_daily_summary(db, bill_date, shift_id, platform_id)
