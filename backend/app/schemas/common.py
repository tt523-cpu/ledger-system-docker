from datetime import date, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class MasterDataCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0
    status: str = "enabled"
    remark: str | None = None


class PaymentMethodCreate(BaseModel):
    name: str
    type: str = "other"
    initial_balance: Decimal = Decimal("0.00")
    channel_kind: str = "internal"
    affect_balance: bool = True
    sort_order: int = 0
    status: str = "enabled"
    remark: str | None = None


class CategoryCreate(BaseModel):
    name: str
    type: str
    affect_profit: bool = True
    affect_balance: bool = True
    sort_order: int = 0
    status: str = "enabled"


class EntryTypeCreate(BaseModel):
    name: str
    effect: str
    requires_category: bool = False
    sort_order: int = 0
    status: str = "enabled"


class ShiftCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0
    start_time: time | None = None
    end_time: time | None = None
    status: str = "enabled"


class TransactionLineCreate(BaseModel):
    type: str
    type_label: str | None = None
    platform_id: int | None = None
    category_id: int | None = None
    amount: Decimal = Field(gt=0)
    account_id: int | None = None
    target_account_id: int | None = None
    payment_method_id: int | None = None
    remark: str | None = None


class BatchTransactionCreate(BaseModel):
    bill_date: date
    shift_id: int
    platform_id: int | None = None
    lines: list[TransactionLineCreate]


class TransactionAIParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class TransactionImportNormalizeRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class ImportAliasCreate(BaseModel):
    alias_type: str = Field(pattern="^(platform|entry_type|category|payment_method)$")
    alias_name: str = Field(min_length=1, max_length=100)
    target_id: int


class DailySummaryOut(BaseModel):
    bill_date: date
    shift_id: int
    platform_id: int
    total_income: Decimal
    total_expense: Decimal
    net_profit: Decimal


class MonthlySummaryOut(BaseModel):
    month: str
    total_income: Decimal
    total_expense: Decimal
    net_profit: Decimal


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: int | None = None
    tenant_name: str | None = None
    tenant_expire_at: str | None = None
    platform_id: int | None = None
    platform_ids: list[int] = Field(default_factory=list)


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    status: str = "enabled"
    admin_username: str | None = None
    admin_password: str | None = None
    admin_expire_at: str | None = None


class TenantUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    status: str = "enabled"
    admin_username: str | None = None
    admin_password: str | None = None
    admin_expire_at: str | None = None


class TenantAccessUpdate(BaseModel):
    expire_at: str | None = None
    status: str = "enabled"


class TenantAdminCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    status: str = "enabled"
    expire_at: str | None = None


class AccountCreate(BaseModel):
    name: str
    type: str
    initial_balance: Decimal = Decimal("0.00")
    status: str = "enabled"
    remark: str | None = None


class AccountSnapshotOut(BaseModel):
    bill_date: date
    shift_id: int
    account_id: int
    opening_balance: Decimal
    income_amount: Decimal
    expense_amount: Decimal
    transfer_in: Decimal
    transfer_out: Decimal
    adjust_amount: Decimal
    theoretical_balance: Decimal
    actual_balance: Decimal | None
    difference: Decimal


class ActualBalanceUpdate(BaseModel):
    actual_balance: Decimal


class OffsetTransactionCreate(BaseModel):
    bill_date: date
    shift_id: int
    platform_id: int | None = None
    recharge_category_id: int | None = None
    payout_category_id: int | None = None
    payment_method_id: int
    amount: Decimal = Field(gt=0)
    remark: str = Field(min_length=2)
