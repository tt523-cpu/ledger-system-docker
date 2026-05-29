from datetime import UTC, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    SHANGHAI_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


def utc_now() -> datetime:
    return datetime.now(UTC)
