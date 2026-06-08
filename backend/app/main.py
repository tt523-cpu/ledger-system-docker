from time import perf_counter

from fastapi import FastAPI
from fastapi import Request
from starlette.responses import Response

from app.api.auth import router as auth_router
from app.api.balances import router as balances_router
from app.api.exports import PUBLIC_ROUTER as public_exports_router
from app.api.exports import router as exports_router
from app.api.master_data import router as master_router
from app.api.reports import router as reports_router
from app.api.system import router as system_router
from app.api.transactions import router as transactions_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.permissions import ensure_role_permissions
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.entities import OperationLog, Tenant, TenantPlatformAccess, User, UserTenantAccess
from app.models.enums import UserRole
from app.services.auto_handover import start_auto_handover_worker, stop_auto_handover_worker
from sqlalchemy import select


Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    ensure_role_permissions(db)

    default_tenant = db.execute(select(Tenant).where(Tenant.name == "默认租户")).scalar_one_or_none()
    if default_tenant is not None:
        has_user_access = db.execute(
            select(UserTenantAccess.id).where(UserTenantAccess.tenant_id == default_tenant.id).limit(1)
        ).first() is not None
        has_platform_access = db.execute(
            select(TenantPlatformAccess.id).where(TenantPlatformAccess.tenant_id == default_tenant.id).limit(1)
        ).first() is not None
        if not has_user_access and not has_platform_access:
            db.delete(default_tenant)

    users = db.execute(select(User)).scalars().all()
    for u in users:
        if u.username == "admin" and u.role != UserRole.SUPER_ADMIN.value:
            u.role = UserRole.SUPER_ADMIN.value

    db.commit()
finally:
    db.close()

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def start_background_workers():
    start_auto_handover_worker()


@app.on_event("shutdown")
def stop_background_workers():
    stop_auto_handover_worker()


@app.middleware("http")
async def operation_log_middleware(request: Request, call_next):
    start = perf_counter()
    status_code = 500
    error_message = None
    response: Response | None = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        error_message = str(exc)
        raise
    finally:
        path = request.url.path
        if path not in {"/health"}:
            db = SessionLocal()
            try:
                auth = request.headers.get("authorization", "")
                token = auth[7:] if auth.lower().startswith("bearer ") else ""
                payload = decode_token(token) if token else None
                username = payload.get("sub") if payload else None
                user_id = None
                if username:
                    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                    if user is not None:
                        user_id = user.id
                duration_ms = int((perf_counter() - start) * 1000)
                db.add(
                    OperationLog(
                        user_id=user_id,
                        username=username,
                        method=request.method,
                        path=path,
                        query_string=request.url.query or None,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        ip=(request.client.host if request.client else None),
                        user_agent=request.headers.get("user-agent"),
                        error_message=error_message,
                    )
                )
                db.commit()
            finally:
                db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(master_router)
app.include_router(transactions_router)
app.include_router(reports_router)
app.include_router(balances_router)
app.include_router(exports_router)
app.include_router(system_router)
app.include_router(public_exports_router)
