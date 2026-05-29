from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import MonthLock


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def assert_month_not_locked(db: Session, d: date) -> None:
    key = month_key(d)
    locked = db.execute(
        select(MonthLock).where(MonthLock.lock_month == key, MonthLock.is_locked.is_(True))
    ).scalar_one_or_none()
    if locked is not None:
        raise ValueError(f"month {key} is locked")
