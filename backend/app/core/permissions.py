from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import RoleModulePermission
from app.models.enums import UserRole


MODULES = [
    {"key": "dashboard", "label": "首页仪表盘"},
    {"key": "transactions.entry", "label": "流水录入"},
    {"key": "transactions.list", "label": "流水查询"},
    {"key": "reports.query", "label": "报表查询"},
    {"key": "reports.balances", "label": "账户余额"},
    {"key": "reports.monthly", "label": "月度汇总"},
    {"key": "reports.charts", "label": "图表分析"},
    {"key": "master.platforms", "label": "平台管理"},
    {"key": "master.payment_methods", "label": "账户管理"},
    {"key": "master.categories", "label": "项目管理"},
    {"key": "master.entry_types", "label": "录入类型管理"},
    {"key": "master.shifts", "label": "班次管理"},
    {"key": "master.users", "label": "用户管理"},
    {"key": "logs", "label": "修改日志"},
    {"key": "system.tools", "label": "系统工具"},
]


DEFAULT_ROLE_MODULES = {
    UserRole.ADMIN.value: [m["key"] for m in MODULES],
    UserRole.BOOKKEEPER.value: [
        "dashboard",
        "transactions.entry",
        "transactions.list",
        "reports.query",
        "reports.balances",
        "reports.monthly",
        "reports.charts",
    ],
    UserRole.VIEWER.value: [
        "dashboard",
        "transactions.list",
        "reports.query",
        "reports.balances",
        "reports.monthly",
        "reports.charts",
        "logs",
    ],
}


def ensure_role_permissions(db: Session) -> None:
    existing = db.execute(select(RoleModulePermission)).scalars().all()
    if existing:
        return
    for role, modules in DEFAULT_ROLE_MODULES.items():
        for module_key in modules:
            db.add(RoleModulePermission(role=role, module_key=module_key, enabled=True))
    db.commit()


def enabled_modules_for_role(db: Session, role: str) -> list[str]:
    rows = db.execute(
        select(RoleModulePermission.module_key).where(
            RoleModulePermission.role == role,
            RoleModulePermission.enabled.is_(True),
        )
    ).all()
    return [r[0] for r in rows]


def replace_role_modules(db: Session, role: str, module_keys: list[str]) -> None:
    db.execute(delete(RoleModulePermission).where(RoleModulePermission.role == role))
    for module_key in module_keys:
        db.add(RoleModulePermission(role=role, module_key=module_key, enabled=True))
    db.commit()
