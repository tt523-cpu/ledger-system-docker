from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Account, AccountSnapshot, PaymentMethod, Transaction
from app.models.enums import TransactionType


def rebuild_account_snapshot(db: Session, bill_date: date, shift_id: int, account_id: int, operator_id: int):
    account = db.get(Account, account_id)
    if account is None:
        return None

    opening = account.initial_balance or Decimal("0.00")
    income = Decimal("0.00")
    expense = Decimal("0.00")
    transfer_in = Decimal("0.00")
    transfer_out = Decimal("0.00")
    adjust = Decimal("0.00")

    tx_stmt = select(Transaction).where(
        Transaction.bill_date == bill_date,
        Transaction.shift_id == shift_id,
        Transaction.deleted_at.is_(None),
    )
    tx_list = db.execute(tx_stmt).scalars().all()

    for tx in tx_list:
        if tx.payment_method_id:
            pm = db.get(PaymentMethod, tx.payment_method_id)
            if pm and not pm.affect_balance:
                continue

        if tx.type == TransactionType.INCOME.value and tx.account_id == account_id:
            income += tx.amount
        elif tx.type == TransactionType.EXPENSE.value and tx.account_id == account_id:
            expense += tx.amount
        elif tx.type == TransactionType.TRANSFER.value:
            if tx.account_id == account_id:
                transfer_out += tx.amount
            if tx.target_account_id == account_id:
                transfer_in += tx.amount
        elif tx.type == TransactionType.ADJUST.value and tx.account_id == account_id:
            adjust += tx.amount

    theoretical = opening + income - expense + transfer_in - transfer_out + adjust

    existing = db.execute(
        select(AccountSnapshot).where(
            AccountSnapshot.bill_date == bill_date,
            AccountSnapshot.shift_id == shift_id,
            AccountSnapshot.account_id == account_id,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = AccountSnapshot(
            bill_date=bill_date,
            shift_id=shift_id,
            account_id=account_id,
            opening_balance=opening,
            income_amount=income,
            expense_amount=expense,
            transfer_in=transfer_in,
            transfer_out=transfer_out,
            adjust_amount=adjust,
            theoretical_balance=theoretical,
            actual_balance=None,
            difference=Decimal("0.00"),
            operator_id=operator_id,
        )
        db.add(existing)
    else:
        existing.opening_balance = opening
        existing.income_amount = income
        existing.expense_amount = expense
        existing.transfer_in = transfer_in
        existing.transfer_out = transfer_out
        existing.adjust_amount = adjust
        existing.theoretical_balance = theoretical
        if existing.actual_balance is not None:
            existing.difference = existing.actual_balance - theoretical

    db.flush()
    return existing
