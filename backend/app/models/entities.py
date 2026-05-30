from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import beijing_now
from app.models.enums import ChannelKind, GenericStatus, PaymentMethodType, TransactionType, UserRole


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now, onupdate=beijing_now)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.BOOKKEEPER.value)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)


class UserTenantAccess(Base):
    __tablename__ = "user_tenant_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now, onupdate=beijing_now)


class TenantPlatformAccess(Base):
    __tablename__ = "tenant_platform_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class UserPlatformAccess(Base):
    __tablename__ = "user_platform_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)


class RoleModulePermission(Base):
    __tablename__ = "role_module_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    module_key: Mapped[str] = mapped_column(String(50), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(50))
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(30), default=PaymentMethodType.OTHER.value)
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    channel_kind: Mapped[str] = mapped_column(String(20), default=ChannelKind.INTERNAL.value)
    affect_balance: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20), default=TransactionType.EXPENSE.value)
    affect_profit: Mapped[bool] = mapped_column(Boolean, default=True)
    affect_balance: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)


class EntryType(Base):
    __tablename__ = "entry_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    effect: Mapped[str] = mapped_column(String(20), default=TransactionType.EXPENSE.value)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=GenericStatus.ENABLED.value)


class EntryTypeSetting(Base):
    __tablename__ = "entry_type_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_type_id: Mapped[int] = mapped_column(ForeignKey("entry_types.id"), unique=True, index=True)
    requires_category: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    biz_type_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True, nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    target_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    people_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    biz_group_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    shift: Mapped[Shift] = relationship("Shift")
    platform: Mapped[Platform] = relationship("Platform")
    category: Mapped[Category] = relationship("Category")
    payment_method: Mapped[PaymentMethod | None] = relationship("PaymentMethod")


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)
    total_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_other_in: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    net_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_people: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now, onupdate=beijing_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    module: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30))
    before_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    query_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    income_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    expense_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    transfer_in: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    transfer_out: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    adjust_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    theoretical_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    actual_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now, onupdate=beijing_now)


class HandoverSnapshot(Base):
    __tablename__ = "handover_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True)
    total_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    turnover: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    confirmed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class HandoverPaymentSnapshot(Base):
    __tablename__ = "handover_payment_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handover_id: Mapped[int] = mapped_column(ForeignKey("handover_snapshots.id"), index=True)
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"), index=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    recharge: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    payout: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))


class MonthLock(Base):
    __tablename__ = "month_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lock_month: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # YYYY-MM
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    locked_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
