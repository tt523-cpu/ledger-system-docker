from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    PLATFORM_VIEWER = "platform_viewer"
    ADMIN = "admin"
    BOOKKEEPER = "bookkeeper"
    VIEWER = "viewer"


class GenericStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    ADJUST = "adjust"


class PaymentMethodType(StrEnum):
    WECHAT = "wechat"
    ALIPAY = "alipay"
    BANK_CARD = "bank_card"
    CASH = "cash"
    AGENT = "agent"
    OTHER = "other"


class ChannelKind(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
