from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.balances import router as balances_router
from app.api.exports import router as exports_router
from app.api.master_data import router as master_router
from app.api.reports import router as reports_router
from app.api.system import router as system_router
from app.api.transactions import router as transactions_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.permissions import ensure_role_permissions
from app.core.database import SessionLocal


Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    ensure_role_permissions(db)
finally:
    db.close()

app = FastAPI(title=settings.app_name)


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
